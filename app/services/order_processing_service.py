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
from app.models.matching import BatchAllocation, MatchResult, MatchSource, MatchStatus
from app.models.order import OrderDocument, OrderRow
from app.parsers.excel_order_parser import ExcelOrderParser
from app.repositories.history_repository import HistoryRepository
from app.repositories.product_repository import ProductRepository
from app.services.alias_service import AliasService
from app.services.certificate_copy_service import CertificateCopyService, CopyReport
from app.services.excel_writer_service import ExcelWriterService
from app.services.expiry_resolution_service import (
    ExpiryResolutionService,
    ExpirySuggestion,
    ManualExpiryReview,
)
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

#: Обработчик ручного подтверждения сертификата для партий срока годности
#: (Этап 3 подбора срока годности — см. ``ExpiryResolutionService``).
#:
#: Принимает обзор партий с предложениями и количество ещё не разобранных
#: позиций (как и ``AmbiguityResolver``). Возвращает словарь «индекс партии
#: в ``review.batches`` → подтверждённый вариант» — партии, отсутствующие в
#: словаре, считаются неподтверждёнными (пустой словарь — ничего не
#: подтверждено для этой строки, переход к следующей); ``None`` — пользователь
#: отказался разбирать оставшиеся позиции.
ExpiryManualResolver = Callable[[ManualExpiryReview, int], "dict[int, ExpirySuggestion] | None"]


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
        resolve_expiry_manually: Обработчик ручного подтверждения сертификата
            для партий срока годности (Этап 3). ``None`` — строки, для
            которых нечего подобрать автоматически, помечаются обычным
            исключением «нет сертификата», как и до появления этого этапа.
        learn_from_choices: Создавать ли псевдонимы по ручным выборам.
    """

    order_path: Path
    sheet_name: str | None = None
    output_dir: Path | None = None
    copy_certificates: bool = True
    write_report: bool = True
    resolve_ambiguities: AmbiguityResolver | None = None
    resolve_expiry_manually: ExpiryManualResolver | None = None
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
        expiry_resolution_service: ExpiryResolutionService | None = None,
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
            expiry_resolution_service: Сервис подбора срока годности —
                новый этап, выполняемый до поиска сертификата (см.
                :class:`~app.services.expiry_resolution_service.ExpiryResolutionService`).
                ``None`` полностью отключает этот этап (поведение не
                отличается от того, что было до его появления).
        """
        self._matching = matching_service
        self._parser = excel_parser
        self._history = history_repository
        self._products = product_repository
        self._reports = report_service
        self._settings = settings_service
        self._events = event_bus
        self._aliases = alias_service
        self._expiry = expiry_resolution_service

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

            # --- Шаг 1а. Подбор срока годности (новый этап, до сертификата) -
            # Выполняется целиком до подбора сертификата и не изменяет сам
            # MatchingService: для строк без указанного срока подбирает его
            # по отдельной базе сроков годности и остатков (одной партией
            # либо, если ни одна не покрывает заказ в одиночку, комбинацией
            # нескольких — Этап 2), пробными вызовами уже существующего
            # MatchingService.match_row проверяя, находится ли сертификат на
            # каждую партию. Отсутствие сервиса (не настроен) или пустая
            # база — этот шаг не делает ничего, поведение не отличается от
            # прежнего. Результат для строк, чей срок(и) подобрал этот этап
            # (исключённых или выполненных комбинацией партий) — готов уже
            # здесь и в шаг 2 (обычный подбор) эти строки не передаются.
            #
            # Строки без требуемого срока запоминаются ДО вызова, чтобы затем
            # (после подбора сертификата) отличить срок, который подобрал
            # новый этап ОДНОЙ партией, от срока, изначально указанного в
            # заказе, — только первый разрешено дописать в колонку
            # «требуемый срок» итогового файла (см. ExcelWriterService и
            # MatchResult.expiry_auto_resolved). Комбинация нескольких партий
            # под это не подпадает: единого срока для записи в эту колонку
            # у неё нет — вместо этого полная раскладка идёт в колонки E/F/G.
            rows_missing_expiry = {
                row.row_number for row in document.rows if row.requested_expiry is None
            }
            expiry_stage_results = self._resolve_expiries(
                document.rows, reporter, request.resolve_expiry_manually
            )
            auto_resolved_rows = {
                row.row_number
                for row in document.rows
                if row.row_number in rows_missing_expiry
                and row.requested_expiry is not None
                and row.row_number not in expiry_stage_results
            }

            # --- Шаг 2. Подбор ----------------------------------------------
            eligible_rows = [
                row for row in document.rows if row.row_number not in expiry_stage_results
            ]
            matched_by_row = {
                result.row.row_number: result
                for result in self._matching.match_rows(eligible_rows, reporter=reporter)
            }
            for row_number in auto_resolved_rows:
                matched_result = matched_by_row.get(row_number)
                if matched_result is not None:
                    matched_result.expiry_auto_resolved = True
            outcome.results = [
                (
                    expiry_stage_results[row.row_number]
                    if row.row_number in expiry_stage_results
                    else matched_by_row[row.row_number]
                )
                for row in document.rows
            ]

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
                certificates_settings = self._settings.current.certificates
                pdf_dir = (
                    Path(certificates_settings.pdf_dir) if certificates_settings.pdf_dir else None
                )
                copier = CertificateCopyService(
                    source_dir=pdf_dir,
                    dirname=export_settings.certificates_dirname,
                    recursive=certificates_settings.recursive_pdf_search,
                )
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
    def _resolve_expiries(
        self,
        rows: list[OrderRow],
        reporter: ProgressReporter | None,
        resolver: ExpiryManualResolver | None,
    ) -> dict[int, MatchResult]:
        """Подбирает срок годности и строит результаты для строк, минующих обычный подбор.

        Три категории строк не должны попадать в обычный подбор сертификата
        (см. :class:`~app.services.expiry_resolution_service.ExpiryResolutionService`):

        * исключённые — товар отсутствует в базе сроков, ни для одной его
          партии не подтверждён (и нечего предложить вручную) сертификат,
          либо суммарного подтверждённого остатка недостаточно — обычный
          подбор проигнорировал бы причину исключения и мог случайно
          подобрать сертификат партии, которой физически не хватает на
          складе;
        * выполненные комбинацией нескольких партий (Этап 2) — сертификаты
          для них уже найдены по каждой партии отдельно, обычному подбору
          там искать больше нечего, а сам он умеет выбрать только один
          сертификат на строку;
        * ожидающие ручного подтверждения (Этап 3) — сертификат не
          подтверждён ни для одной партии автоматически, но есть варианты
          на выбор пользователю (:meth:`_resolve_expiry_manually`).

        Для всех трёх категорий здесь же формируется финальный результат.

        Args:
            rows: Строки заказа.
            reporter: Приёмник прогресса.
            resolver: Обработчик ручного подтверждения (Этап 3). ``None`` —
                строки третьей категории получают то же исключение, что и
                строки первой (см. :meth:`_resolve_expiry_manually`).

        Returns:
            Отображение «номер строки → готовый результат» для всех трёх
            категорий выше. Пустой словарь, если сервис не подключён, база
            сроков годности не настроена или обычный подбор нужен для всех
            строк как есть.
        """
        if self._expiry is None:
            return {}

        excluded, combined, pending_review = self._expiry.resolve_rows(rows, reporter=reporter)
        if not excluded and not combined and not pending_review:
            return {}

        rows_by_number = {row.row_number: row for row in rows}
        results: dict[int, MatchResult] = {
            row_number: MatchResult(
                row=rows_by_number[row_number],
                status=MatchStatus.NOT_FOUND,
                note=exclusion.note,
                expiry_not_in_database=exclusion.not_in_database,
                expiry_no_certificate_available=exclusion.no_certificate_available,
            )
            for row_number, exclusion in excluded.items()
        }
        for row_number, allocations in combined.items():
            results[row_number] = _build_combined_result(rows_by_number[row_number], allocations)
        if pending_review:
            self._resolve_expiry_manually(pending_review, resolver, results)
        return results

    def _resolve_expiry_manually(
        self,
        pending_review: dict[int, ManualExpiryReview],
        resolver: ExpiryManualResolver | None,
        results: dict[int, MatchResult],
    ) -> None:
        """Разбирает партии, ожидающие ручного подтверждения (Этап 3).

        Без резолвера (CLI, либо GUI без подключённого разбора) поведение
        не отличается от того, что было бы без Этапа 3 вообще: строка
        получает то же исключение «нет сертификата», что и раньше — этап
        полностью незаметен, если его не используют, как и остальные этапы
        подбора срока годности.

        Args:
            pending_review: Строки, ожидающие подтверждения (третий словарь
                из ``ExpiryResolutionService.resolve_rows``) — номер строки
                → обзор партий с предложениями.
            resolver: Обработчик окна ручного подтверждения.
            results: Отображение «номер строки → результат» — заполняется
                на месте.
        """
        assert self._expiry is not None
        reviews = list(pending_review.values())

        if resolver is None:
            for review in reviews:
                self._apply_expiry_choice(review, {}, results)
            return

        _LOGGER.info("Ожидают ручного подтверждения срока годности позиций: %s", len(reviews))
        for position, review in enumerate(reviews):
            choices = resolver(review, len(reviews) - position - 1)
            if choices is None:
                _LOGGER.info("Пользователь прекратил разбор партий срока годности")
                for remaining in reviews[position:]:
                    self._apply_expiry_choice(remaining, {}, results)
                break
            self._apply_expiry_choice(review, choices, results)

    def _apply_expiry_choice(
        self,
        review: ManualExpiryReview,
        choices: dict[int, ExpirySuggestion],
        results: dict[int, MatchResult],
    ) -> None:
        """Строит итоговый результат по подтверждённым пользователем партиям.

        Пустой ``choices`` (ничего не подтверждено — нет резолвера,
        пользователь прекратил разбор или явно не выбрал ни одного варианта
        для этой строки) закономерно приводит к тому же исключению «нет
        сертификата», что и без Этапа 3 вообще — это гарантирует сам
        ``ExpiryResolutionService.apply_manual_selections``, а не отдельный
        код здесь.
        """
        assert self._expiry is not None
        outcome = self._expiry.apply_manual_selections(review, choices)
        row_number = review.row.row_number
        if isinstance(outcome, list):
            results[row_number] = _build_combined_result(review.row, outcome)
        else:
            results[row_number] = MatchResult(
                row=review.row,
                status=MatchStatus.NOT_FOUND,
                note=outcome.note,
                expiry_no_certificate_available=outcome.no_certificate_available,
            )

    def _resolve_ambiguities(self, outcome: ProcessingOutcome, request: ProcessingRequest) -> None:
        """Передаёт неоднозначные результаты на разрешение пользователю.

        Помимо обычной неоднозначности (несколько близких кандидатов), сюда
        же попадают результаты с ``alias_stale`` — официальный товар из
        словаря сейчас отсутствует в базе, и резервный поиск нашёл замену
        через обычный конвейер (см.
        :meth:`~app.services.matching_service.MatchingService._fallback_after_stale_alias`).
        Такое решение нельзя молча подставлять вместо того, что хранится в
        словаре, — пользователь должен подтвердить его так же, как обычный
        неоднозначный выбор; галочка «Запомнить выбор» в том же диалоге и
        есть предложение обновить словарь (``learn_from_result`` обновит
        существующую запись новым товаром).
        """
        resolver = request.resolve_ambiguities
        if resolver is None:
            return

        pending = [
            result
            for result in outcome.results
            if result.status is MatchStatus.AMBIGUOUS
            or (result.alias_stale and result.status is MatchStatus.MATCHED)
        ]
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


def _build_combined_result(row: OrderRow, allocations: list[BatchAllocation]) -> MatchResult:
    """Строит итоговый результат для строки, выполненной несколькими партиями сразу.

    Сертификаты для всех использованных партий уже найдены
    (:class:`~app.services.expiry_resolution_service.ExpiryResolutionService`)
    — здесь они лишь оборачиваются в обычный :class:`MatchResult`, как если
    бы их нашёл обычный подбор. ``candidates``/``selected_index`` указывают
    на первую (самую новую) партию — через них ``certificate``,
    ``certificate_number`` и ``expiry_date`` остаются осмысленными для
    отчёта и истории; полную раскладку по всем партиям несёт
    ``batch_allocations`` — именно её читает
    :class:`~app.services.excel_writer_service.ExcelWriterService`.

    Статус — :attr:`~app.models.matching.MatchStatus.MANUAL`, если хотя бы
    одна из использованных партий подтверждена вручную (Этап 3,
    :attr:`~app.models.matching.MatchSource.MANUAL`), иначе
    :attr:`~app.models.matching.MatchStatus.MATCHED`, как и раньше — не
    декоративное различие: отчёт и история отдельно считают позиции,
    подтверждённые человеком (:attr:`ProcessingOutcome.manual`).

    Args:
        row: Строка заказа.
        allocations: Партии, использованные для её выполнения (Этап 2), в
            порядке использования — от новой к старой.

    Returns:
        Результат со статусом ``MATCHED`` либо ``MANUAL``.
    """
    manual = any(allocation.candidate.source is MatchSource.MANUAL for allocation in allocations)
    return MatchResult(
        row=row,
        status=MatchStatus.MANUAL if manual else MatchStatus.MATCHED,
        candidates=[allocation.candidate for allocation in allocations],
        selected_index=0,
        note="Заказ выполнен несколькими партиями с разными сроками годности",
        batch_allocations=allocations,
    )


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
        score=result.score,
        method=candidate.source.label if candidate else "",
        candidates_count=len(result.candidates),
        duration_ms=result.duration_ms,
        note=result.note,
    )
