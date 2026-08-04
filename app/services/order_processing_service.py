"""Оркестратор обработки заказа — сценарий кнопки «Подобрать сертификаты».

Сервис связывает все остальные: разбирает файл заказа, подбирает сертификаты,
при необходимости спрашивает пользователя, формирует Excel, копирует PDF,
строит отчёт и записывает историю.

Единственная точка, где сценарий целиком виден как последовательность шагов, —
метод :meth:`OrderProcessingService.process`. Это осознанное решение: сценарий
должен читаться сверху вниз без переходов по файлам.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.config.settings import SettingsService
from app.core.events import AppEvent, EventBus, ProgressReporter
from app.core.exceptions import CertMatcherError, OperationCancelledError
from app.models.history import ProcessingItem, ProcessingRun
from app.models.matching import MatchResult, MatchStatus
from app.models.order import OrderDocument
from app.parsers.excel_order_parser import ExcelOrderParser
from app.repositories.history_repository import HistoryRepository
from app.repositories.product_repository import ProductRepository
from app.services.alias_service import AliasService
from app.services.certificate_copy_service import CertificateCopyService, CopyReport
from app.services.excel_writer_service import ExcelWriterService
from app.services.matching_service import MatchingService
from app.services.report_service import ReportService

_LOGGER = logging.getLogger(__name__)

#: Обработчик неоднозначного результата.
#:
#: Принимает результат подбора и количество ещё не разобранных позиций
#: (нужно, чтобы окно выбора показывало пользователю оставшийся объём работы).
#: Возвращает индекс выбранного кандидата, ``-1`` для пропуска строки или
#: ``None``, если пользователь отказался разбирать оставшиеся неоднозначности.
AmbiguityResolver = Callable[[MatchResult, int], "int | None"]


@dataclass(slots=True)
class ProcessingRequest:
    """Параметры запуска обработки заказа.

    Attributes:
        order_path: Путь к файлу заказа.
        sheet_name: Имя листа; ``None`` — определить автоматически.
        output_dir: Каталог результата; ``None`` — рядом с заказом.
        copy_certificates: Копировать ли PDF в папку результата.
        write_report: Формировать ли отчёт.
        resolve_ambiguities: Обработчик окна неоднозначного выбора.
        learn_from_choices: Создавать ли псевдонимы по ручным выборам.
    """

    order_path: Path
    sheet_name: str | None = None
    output_dir: Path | None = None
    copy_certificates: bool = True
    write_report: bool = True
    resolve_ambiguities: AmbiguityResolver | None = None
    learn_from_choices: bool = True


@dataclass(slots=True)
class ProcessingOutcome:
    """Итог обработки заказа.

    Attributes:
        run: Запись истории обработки.
        document: Разобранный заказ.
        results: Результаты подбора по строкам.
        output_file: Путь созданного файла Excel.
        report_file: Путь отчёта.
        copy_report: Итог копирования сертификатов.
        cancelled: Признак отмены пользователем.
    """

    run: ProcessingRun
    document: OrderDocument
    results: list[MatchResult] = field(default_factory=list)
    output_file: Path | None = None
    report_file: Path | None = None
    copy_report: CopyReport | None = None
    cancelled: bool = False

    @property
    def matched(self) -> int:
        """Количество автоматически подобранных позиций."""
        return sum(1 for result in self.results if result.status is MatchStatus.MATCHED)

    @property
    def manual(self) -> int:
        """Количество позиций, выбранных вручную."""
        return sum(1 for result in self.results if result.status is MatchStatus.MANUAL)

    @property
    def ambiguous(self) -> int:
        """Количество позиций, требующих проверки."""
        return sum(1 for result in self.results if result.status is MatchStatus.AMBIGUOUS)

    @property
    def not_found(self) -> int:
        """Количество неподобранных позиций."""
        return sum(1 for result in self.results if result.status is MatchStatus.NOT_FOUND)

    def summary(self) -> str:
        """Возвращает сводку для уведомления."""
        return (
            f"Обработано {len(self.results)} позиций: "
            f"найдено {self.matched + self.manual}, "
            f"требует проверки {self.ambiguous}, не найдено {self.not_found}"
        )


class OrderProcessingService:
    """Выполняет полный сценарий обработки заказа."""

    def __init__(
        self,
        matching_service: MatchingService,
        excel_parser: ExcelOrderParser,
        history_repository: HistoryRepository,
        product_repository: ProductRepository,
        report_service: ReportService,
        settings_service: SettingsService,
        event_bus: EventBus,
        alias_service: AliasService | None = None,
    ) -> None:
        """Создаёт оркестратор.

        Args:
            matching_service: Сервис подбора.
            excel_parser: Парсер файлов заказа.
            history_repository: Журнал обработки.
            product_repository: Справочник товаров.
            report_service: Сервис отчётов.
            settings_service: Конфигурация приложения.
            event_bus: Шина событий.
            alias_service: Сервис псевдонимов (для самообучения).
        """
        self._matching = matching_service
        self._parser = excel_parser
        self._history = history_repository
        self._products = product_repository
        self._reports = report_service
        self._settings = settings_service
        self._events = event_bus
        self._aliases = alias_service

    def process(
        self, request: ProcessingRequest, *, reporter: ProgressReporter | None = None
    ) -> ProcessingOutcome:
        """Выполняет обработку заказа целиком.

        Args:
            request: Параметры запуска.
            reporter: Приёмник прогресса и токен отмены.

        Returns:
            Итог обработки со ссылками на созданные файлы.

        Raises:
            CertMatcherError: При ошибке разбора или формирования результата.
        """
        started = time.perf_counter()
        export_settings = self._settings.current.export

        self._events.publish(AppEvent.ORDER_STARTED, order=str(request.order_path))
        if reporter is not None:
            reporter.note("Чтение файла заказа…", "reading")

        document = self._parser.parse(request.order_path, sheet_name=request.sheet_name)

        run = ProcessingRun(
            order_file=str(request.order_path),
            started_at=datetime.now(),
            total_rows=document.row_count,
        )
        self._history.start_run(run)

        outcome = ProcessingOutcome(run=run, document=document)

        try:
            # --- Шаг 1. Подготовка индексов ---------------------------------
            if reporter is not None:
                reporter.note("Подготовка справочника сертификатов…", "preparing")
            self._matching.prepare(reporter=reporter)

            # --- Шаг 2. Подбор ----------------------------------------------
            outcome.results = self._matching.match_rows(document.rows, reporter=reporter)

            # --- Шаг 3. Разбор неоднозначностей -----------------------------
            if request.resolve_ambiguities is not None:
                self._resolve_ambiguities(outcome, request)

            # --- Шаг 4. Файл результата -------------------------------------
            if reporter is not None:
                reporter.note("Формирование файла результата…", "writing")
            writer = ExcelWriterService(export_settings)
            output_dir = request.output_dir or (
                Path(export_settings.output_dir) if export_settings.output_dir else None
            )
            output_file = writer.build_output_path(request.order_path, output_dir)
            outcome.output_file = writer.write(document, outcome.results, output_file)
            run.output_file = str(outcome.output_file)

            # --- Шаг 5. Копирование сертификатов ----------------------------
            if request.copy_certificates and export_settings.copy_certificates:
                copier = CertificateCopyService(dirname=export_settings.certificates_dirname)
                outcome.copy_report = copier.copy_for_results(
                    outcome.results, outcome.output_file, reporter=reporter
                )
                run.certificates_dir = str(outcome.copy_report.destination)
                run.copied_files = outcome.copy_report.copied

            # --- Шаг 6. Отчёт -----------------------------------------------
            # Длительность фиксируется до формирования отчёта: она входит
            # в сводный лист, и нулевое значение выглядело бы дефектом.
            run.duration_ms = (time.perf_counter() - started) * 1000
            if request.write_report and export_settings.write_report:
                if reporter is not None:
                    reporter.note("Формирование отчёта…", "reporting")
                report_path = outcome.output_file.with_name(f"{outcome.output_file.stem}_отчёт")
                outcome.report_file = self._reports.write(
                    outcome.results,
                    report_path,
                    run=run,
                    report_format=export_settings.report_format,
                )
                run.report_file = str(outcome.report_file)

            # --- Шаг 7. История и справочник товаров ------------------------
            self._finalize(run, outcome, started, status="success")
            if reporter is not None:
                reporter.finish(outcome.summary(), "done")

        except OperationCancelledError:
            outcome.cancelled = True
            self._finalize(
                run, outcome, started, status="cancelled", message="Отменено пользователем"
            )
            _LOGGER.info("Обработка заказа отменена пользователем")
        except CertMatcherError as error:
            self._finalize(run, outcome, started, status="failed", message=error.message)
            _LOGGER.error("Обработка заказа завершилась ошибкой: %s", error.message)
            raise

        self._events.publish(AppEvent.ORDER_FINISHED, outcome=outcome)
        return outcome

    # ------------------------------------------------------------- шаги
    def _resolve_ambiguities(self, outcome: ProcessingOutcome, request: ProcessingRequest) -> None:
        """Передаёт неоднозначные результаты на разрешение пользователю."""
        resolver = request.resolve_ambiguities
        if resolver is None:
            return

        pending = [result for result in outcome.results if result.status is MatchStatus.AMBIGUOUS]
        if not pending:
            return

        _LOGGER.info("Требуют проверки позиций: %s", len(pending))
        for position, result in enumerate(pending):
            choice = resolver(result, len(pending) - position - 1)
            if choice is None:
                _LOGGER.info("Пользователь прекратил разбор неоднозначностей")
                break
            if choice < 0:
                result.status = MatchStatus.NOT_FOUND
                result.selected_index = None
                result.note = "Пропущено пользователем"
                continue
            result.select(choice, manual=True)
            # ``alias_applied`` уже могло быть выставлено вызывающей стороной
            # (окно выбора) как сигнал «пользователь снял галочку "Запомнить
            # выбор"» — в этом случае самообучение нужно пропустить, иначе
            # отказ запоминать соответствие тихо игнорируется.
            if (
                request.learn_from_choices
                and self._aliases is not None
                and not result.alias_applied
            ):
                try:
                    self._aliases.learn_from_result(result, note="Выбор в окне неоднозначности")
                except Exception:
                    _LOGGER.exception("Не удалось сохранить псевдоним")

    def _finalize(
        self,
        run: ProcessingRun,
        outcome: ProcessingOutcome,
        started: float,
        *,
        status: str,
        message: str = "",
    ) -> None:
        """Записывает историю обработки и обновляет справочник товаров."""
        run.finished_at = datetime.now()
        run.duration_ms = (time.perf_counter() - started) * 1000
        run.total_rows = len(outcome.results)
        run.matched = outcome.matched
        run.manual = outcome.manual
        run.ambiguous = outcome.ambiguous
        run.not_found = outcome.not_found
        run.status = status
        run.message = message

        try:
            self._history.finish_run(run)
            self._history.save_items(
                [_to_history_item(run.run_id, result) for result in outcome.results]
            )
        except Exception:
            _LOGGER.exception("Не удалось записать историю обработки")

        try:
            for result in outcome.results:
                if result.status is MatchStatus.SKIPPED:
                    continue
                certificate = result.certificate
                self._products.record_occurrence(
                    result.row.product_name,
                    certificate_id=certificate.id if certificate else None,
                    matched=result.status.is_resolved,
                )
        except Exception:
            _LOGGER.exception("Не удалось обновить справочник товаров")

        _LOGGER.info("Обработка завершена за %.2f с: %s", run.duration_seconds, outcome.summary())


def _to_history_item(run_id: str, result: MatchResult) -> ProcessingItem:
    """Преобразует результат подбора в запись журнала."""
    certificate = result.certificate
    candidate = result.selected or result.best
    return ProcessingItem(
        run_id=run_id,
        row_number=result.row.row_number,
        product_name=result.row.product_name,
        status=result.status.value,
        certificate_id=certificate.id if certificate else None,
        certificate_number=result.certificate_number,
        certificate_expiry=result.expiry_date.isoformat() if result.expiry_date else "",
        pdf_name=certificate.pdf_name if certificate else "",
        score=result.score,
        method=candidate.source.label if candidate else "",
        candidates_count=len(result.candidates),
        duration_ms=result.duration_ms,
        note=result.note,
    )
