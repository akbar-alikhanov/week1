"""Интеграционные тесты полного сценария обработки заказа.

Это тесты сценария «выбрать Excel → нажать кнопку» — главного требования
продукта. Они проверяют не отдельный модуль, а весь путь: разбор заказа,
подбор сертификатов по базе (Excel, проиндексированной в SQLite), запись
Excel, копирование PDF по номеру сертификата, формирование отчёта и историю,
— так, как это происходит при реальном нажатии кнопки в интерфейсе.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")
pytest.importorskip("pandas")

from app.ai.embeddings import EmbeddingBackend  # noqa: E402
from app.ai.vector_index import VectorIndex  # noqa: E402
from app.config.settings import SettingsService  # noqa: E402
from app.core.events import EventBus  # noqa: E402
from app.database.connection import Database  # noqa: E402
from app.models.matching import MatchResult, MatchStatus  # noqa: E402
from app.parsers.excel_order_parser import ExcelOrderParser  # noqa: E402
from app.repositories.alias_repository import AliasRepository  # noqa: E402
from app.repositories.certificate_product_repository import (  # noqa: E402
    CertificateProductRepository,
)
from app.repositories.expiry_stock_repository import ExpiryStockRepository  # noqa: E402
from app.repositories.history_repository import HistoryRepository  # noqa: E402
from app.repositories.product_repository import ProductRepository  # noqa: E402
from app.services.alias_service import AliasService  # noqa: E402
from app.services.expiry_resolution_service import ExpiryResolutionService  # noqa: E402
from app.services.matching_service import MatchingService  # noqa: E402
from app.services.order_processing_service import (  # noqa: E402
    OrderProcessingService,
    ProcessingRequest,
)
from app.services.report_service import ReportService  # noqa: E402
from tests.conftest import make_certificate, make_expiry_entry  # noqa: E402

_FUTURE = dt.date.today() + dt.timedelta(days=365 * 3)


def _build_order_file(path: Path, rows: list[tuple[str, int]]) -> None:
    """Создаёт файл заказа с указанными позициями."""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Заказ"
    sheet.append(["№", "Наименование товара", "Кол-во", "Сертификат", "Срок сертификата"])
    for index, (name, quantity) in enumerate(rows, start=1):
        sheet.append([index, name, quantity, None, None])
    workbook.save(path)


def _build_order_file_with_expiry_column(path: Path, rows: list[tuple[str, int]]) -> None:
    """Создаёт файл заказа с колонкой требуемого срока годности, изначально пустой.

    Используется тестами интеграции нового этапа подбора срока годности —
    именно такую пустую колонку он и должен заполнить до поиска сертификата.
    """
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Заказ"
    sheet.append(
        [
            "№",
            "Наименование товара",
            "Кол-во",
            "Требуемый срок годности",
            "Сертификат",
            "Срок сертификата",
        ]
    )
    for index, (name, quantity) in enumerate(rows, start=1):
        sheet.append([index, name, quantity, None, None, None])
    workbook.save(path)


@pytest.fixture
def order_service(tmp_path: Path, database: Database) -> Iterator[OrderProcessingService]:
    """Полностью собранный оркестратор обработки заказа."""
    certificates = CertificateProductRepository(database)
    aliases = AliasRepository(database)
    products = ProductRepository(database)
    history = HistoryRepository(database)
    settings_service = SettingsService(tmp_path / "settings.json")
    settings_service.load()
    settings_service.update(
        lambda settings: setattr(settings.export, "output_dir", str(tmp_path / "output"))
    )
    settings_service.update(
        lambda settings: setattr(settings.certificates, "pdf_dir", str(tmp_path / "certs"))
    )

    backend = EmbeddingBackend(enabled=False)
    vector_index = VectorIndex(backend, None)
    matching = MatchingService(certificates, aliases, settings_service, backend, vector_index)
    alias_service = AliasService(aliases, certificates, matching, EventBus())

    service = OrderProcessingService(
        matching,
        ExcelOrderParser(),
        history,
        products,
        ReportService(),
        settings_service,
        EventBus(),
        alias_service=alias_service,
    )

    # Наполняем базу сертификатов, как если бы Excel-файл уже импортировали.
    certificates.replace_all(
        [
            make_certificate(
                "Лечебные травы, сироп 100 мл",
                expiry_date=_FUTURE,
                certificate_number="UZ.180001",
            ),
            make_certificate(
                "Масло облепиховое 100 мл",
                expiry_date=_FUTURE,
                certificate_number="UZ.180002",
            ),
        ]
    )
    # Файлы должны реально существовать — их будет копировать CertificateCopyService,
    # находя по номеру сертификата в имени файла.
    (tmp_path / "certs").mkdir()
    (tmp_path / "certs" / "UZ.180001.pdf").write_bytes(b"%PDF-1.4 fake")
    (tmp_path / "certs" / "UZ.180002.pdf").write_bytes(b"%PDF-1.4 fake")

    yield service


@pytest.fixture
def order_service_with_expiry(
    tmp_path: Path, database: Database
) -> Iterator[tuple[OrderProcessingService, ExpiryStockRepository, CertificateProductRepository]]:
    """Оркестратор с подключённым новым этапом подбора срока годности.

    В остальном идентичен ``order_service`` — то же самое, только с
    ``expiry_resolution_service``, что и включает новый этап (см.
    :class:`~app.services.expiry_resolution_service.ExpiryResolutionService`).
    Без базы сроков годности (``expiry_stock`` пуст) поведение обязано
    остаться прежним — это тоже часть проверок.
    """
    certificates = CertificateProductRepository(database)
    aliases = AliasRepository(database)
    products = ProductRepository(database)
    history = HistoryRepository(database)
    expiry_stock = ExpiryStockRepository(database)
    settings_service = SettingsService(tmp_path / "settings.json")
    settings_service.load()
    settings_service.update(
        lambda settings: setattr(settings.export, "output_dir", str(tmp_path / "output"))
    )
    settings_service.update(lambda settings: setattr(settings.export, "write_report", False))

    backend = EmbeddingBackend(enabled=False)
    vector_index = VectorIndex(backend, None)
    matching = MatchingService(certificates, aliases, settings_service, backend, vector_index)
    expiry_resolution = ExpiryResolutionService(expiry_stock, matching)

    service = OrderProcessingService(
        matching,
        ExcelOrderParser(),
        history,
        products,
        ReportService(),
        settings_service,
        EventBus(),
        expiry_resolution_service=expiry_resolution,
    )

    yield service, expiry_stock, certificates


class TestFullScenario:
    """Проверки сценария «Excel заказа → кнопка → результат»."""

    def test_process_creates_output_excel_with_certificates(
        self, order_service: OrderProcessingService, tmp_path: Path
    ) -> None:
        """Обработка создаёт копию Excel с заполненными сертификатами."""
        order_path = tmp_path / "Заказ.xlsx"
        _build_order_file(
            order_path,
            [("Лечебные травы, сироп 100 мл", 10), ("Масло облепиховое 100 мл", 20)],
        )

        outcome = order_service.process(ProcessingRequest(order_path=order_path))

        assert outcome.output_file is not None
        assert outcome.output_file.exists()
        assert outcome.output_file != order_path
        assert outcome.matched == 2
        assert outcome.not_found == 0

    def test_process_copies_certificate_pdfs(
        self, order_service: OrderProcessingService, tmp_path: Path
    ) -> None:
        """Найденные сертификаты копируются в папку Certificates по номеру."""
        order_path = tmp_path / "Заказ.xlsx"
        _build_order_file(order_path, [("Лечебные травы, сироп 100 мл", 10)])

        outcome = order_service.process(ProcessingRequest(order_path=order_path))

        assert outcome.copy_report is not None
        assert outcome.copy_report.copied == 1
        copied_files = list(outcome.copy_report.destination.glob("*.pdf"))
        assert len(copied_files) == 1

    def test_process_generates_report(
        self, order_service: OrderProcessingService, tmp_path: Path
    ) -> None:
        """Формируется отчёт со сводкой и детализацией по позициям."""
        order_path = tmp_path / "Заказ.xlsx"
        _build_order_file(order_path, [("Лечебные травы, сироп 100 мл", 10)])

        outcome = order_service.process(ProcessingRequest(order_path=order_path))

        assert outcome.report_file is not None
        assert outcome.report_file.exists()

    def test_process_records_history(
        self,
        order_service: OrderProcessingService,
        tmp_path: Path,
        history_repository: HistoryRepository,
    ) -> None:
        """Обработка записывается в историю с корректными показателями."""
        order_path = tmp_path / "Заказ.xlsx"
        _build_order_file(order_path, [("Лечебные травы, сироп 100 мл", 10)])

        outcome = order_service.process(ProcessingRequest(order_path=order_path))

        run = history_repository.get_run(outcome.run.run_id)
        assert run is not None
        assert run.status == "success"
        assert run.matched == 1

    def test_unknown_product_marked_not_found(
        self, order_service: OrderProcessingService, tmp_path: Path
    ) -> None:
        """Товар, отсутствующий в базе, помечается как не найденный."""
        order_path = tmp_path / "Заказ.xlsx"
        _build_order_file(order_path, [("Совершенно неизвестный товар XYZ", 5)])

        outcome = order_service.process(ProcessingRequest(order_path=order_path))

        assert outcome.not_found == 1
        assert outcome.results[0].status is MatchStatus.NOT_FOUND

    def test_ambiguity_resolver_receives_manual_choice(
        self,
        order_service: OrderProcessingService,
        tmp_path: Path,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Ручной выбор пользователя в окне неоднозначности применяется к результату."""
        # Добавляем второй, менее подходящий вариант того же товара,
        # чтобы гарантированно получить неоднозначность.
        rival = make_certificate(
            "Лечебные травы, сироп 200 мл",
            expiry_date=_FUTURE,
            certificate_number="UZ.180099",
        )
        certificate_repository.replace_all([*certificate_repository.list_all(), rival])
        (tmp_path / "certs" / "UZ.180099.pdf").write_bytes(b"%PDF-1.4 fake")

        order_path = tmp_path / "Заказ.xlsx"
        _build_order_file(order_path, [("Лечебные травы, сироп", 5)])

        calls: list[int] = []

        def _resolver(result: object, remaining: int) -> int:
            calls.append(remaining)
            return 0  # выбираем первого кандидата

        outcome = order_service.process(
            ProcessingRequest(order_path=order_path, resolve_ambiguities=_resolver)
        )

        assert calls  # резолвер был вызван хотя бы раз
        assert outcome.results[0].status in (MatchStatus.MANUAL, MatchStatus.MATCHED)

    def test_ambiguity_resolver_skip_marks_not_found(
        self,
        order_service: OrderProcessingService,
        tmp_path: Path,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Пропуск позиции в окне неоднозначности переводит её в «не найдено»."""
        rival = make_certificate(
            "Лечебные травы, сироп 200 мл", expiry_date=_FUTURE, certificate_number="UZ.180099"
        )
        certificate_repository.replace_all([*certificate_repository.list_all(), rival])

        order_path = tmp_path / "Заказ.xlsx"
        _build_order_file(order_path, [("Лечебные травы, сироп", 5)])

        outcome = order_service.process(
            ProcessingRequest(
                order_path=order_path, resolve_ambiguities=lambda result, remaining: -1
            )
        )

        assert outcome.results[0].status is MatchStatus.NOT_FOUND

    def test_process_updates_product_repository(
        self,
        order_service: OrderProcessingService,
        tmp_path: Path,
        product_repository: ProductRepository,
    ) -> None:
        """Обработка регистрирует позиции в справочнике товаров."""
        order_path = tmp_path / "Заказ.xlsx"
        _build_order_file(order_path, [("Лечебные травы, сироп 100 мл", 10)])

        order_service.process(ProcessingRequest(order_path=order_path))

        product = product_repository.find_by_name("Лечебные травы, сироп 100 мл")
        assert product is not None
        assert product.seen_count == 1
        assert product.matched_count == 1


class TestSelfLearningConsent:
    """Проверки: отказ пользователя запоминать выбор должен соблюдаться.

    Регрессия: окно неоднозначного выбора помечает результат
    (``note`` + ``alias_applied=True``), когда пользователь снимает галочку
    «Запомнить выбор», но оркестратор раньше не проверял этот признак и всё
    равно создавал псевдоним — отказ пользователя тихо игнорировался.
    """

    def _add_rival(self, certificate_repository: CertificateProductRepository) -> None:
        """Добавляет второй вариант товара, чтобы гарантировать неоднозначность."""
        rival = make_certificate("Лечебные травы, сироп 200 мл", expiry_date=_FUTURE)
        certificate_repository.replace_all([*certificate_repository.list_all(), rival])

    def test_declining_to_remember_skips_alias_creation(
        self,
        order_service: OrderProcessingService,
        tmp_path: Path,
        certificate_repository: CertificateProductRepository,
        alias_repository: AliasRepository,
    ) -> None:
        """Признак отказа, выставленный резолвером, должен блокировать самообучение."""
        self._add_rival(certificate_repository)
        order_path = tmp_path / "Заказ.xlsx"
        _build_order_file(order_path, [("Лечебные травы, сироп", 5)])

        def _resolver(result: MatchResult, remaining: int) -> int:
            result.note = "Выбор не сохранён в псевдонимы"
            result.alias_applied = True
            return 0

        order_service.process(
            ProcessingRequest(order_path=order_path, resolve_ambiguities=_resolver)
        )

        assert alias_repository.count() == 0

    def test_default_consent_creates_alias(
        self,
        order_service: OrderProcessingService,
        tmp_path: Path,
        certificate_repository: CertificateProductRepository,
        alias_repository: AliasRepository,
    ) -> None:
        """Без отказа ручной выбор в окне неоднозначности запоминается как обычно."""
        self._add_rival(certificate_repository)
        order_path = tmp_path / "Заказ.xlsx"
        _build_order_file(order_path, [("Лечебные травы, сироп", 5)])

        order_service.process(
            ProcessingRequest(
                order_path=order_path, resolve_ambiguities=lambda result, remaining: 0
            )
        )


class TestExpiryResolutionIntegration:
    """Проверки интеграции нового этапа подбора срока годности в общий сценарий.

    В отличие от ``tests/services/test_expiry_resolution_service.py`` (все
    ветки самого алгоритма в изоляции), здесь проверяется, что новый этап
    правильно встроен в оркестратор целиком: выполняется ДО поиска
    сертификата, не переписывает и не заменяет существующий алгоритм подбора,
    а исключённые им строки не попадают в обычный подбор вовсе.
    """

    def test_resolved_expiry_written_to_output_column_and_certificate_matched(
        self,
        order_service_with_expiry: tuple[
            OrderProcessingService, ExpiryStockRepository, CertificateProductRepository
        ],
        tmp_path: Path,
    ) -> None:
        """Товар без требуемого срока в заказе получает его от нового этапа целиком.

        Сквозная проверка: колонка «Требуемый срок годности» в исходном
        заказе пуста → новый этап подбирает срок по базе остатков → строка
        уходит в уже существующий, нетронутый алгоритм подбора → найденный
        сертификат и подобранный срок оба оказываются в итоговом Excel.
        """
        service, expiry_stock, certificates = order_service_with_expiry
        certificates.replace_all(
            [make_certificate("Крем детский 100 мл", expiry_date=dt.date(2028, 6, 1))]
        )
        expiry_stock.replace_all(
            [
                make_expiry_entry(
                    "Крем детский 100 мл", expiry_date=dt.date(2028, 6, 1), quantity=100
                )
            ]
        )

        order_path = tmp_path / "Заказ.xlsx"
        _build_order_file_with_expiry_column(order_path, [("Крем детский 100 мл", 10)])

        outcome = service.process(ProcessingRequest(order_path=order_path))

        assert outcome.results[0].status is MatchStatus.MATCHED
        assert outcome.results[0].expiry_auto_resolved is True

        workbook = openpyxl.load_workbook(outcome.output_file)
        sheet = workbook["Заказ"]
        cell = sheet.cell(row=2, column=4).value
        written_date = cell.date() if isinstance(cell, dt.datetime) else cell
        assert written_date == dt.date(2028, 6, 1)
        assert sheet.cell(row=2, column=5).value  # номер сертификата записан
        workbook.close()

    def test_product_missing_from_stock_database_bypasses_normal_matching(
        self,
        order_service_with_expiry: tuple[
            OrderProcessingService, ExpiryStockRepository, CertificateProductRepository
        ],
        tmp_path: Path,
    ) -> None:
        """Товар вне базы сроков не доходит до обычного подбора сертификата.

        Регрессия: даже если подходящий сертификат для товара ЕСТЬ в базе,
        отсутствие товара в базе сроков годности должно исключить строку из
        обычного подбора целиком (см. ``ExpiryResolutionService``), а не
        просто понизить её приоритет.
        """
        service, expiry_stock, certificates = order_service_with_expiry
        certificates.replace_all(
            [
                make_certificate(
                    "Крем детский 100 мл", expiry_date=_FUTURE, certificate_number="UZ.1"
                )
            ]
        )
        # В базе сроков годности есть данные — но не для этого товара.
        expiry_stock.replace_all(
            [make_expiry_entry("Другой товар", expiry_date=dt.date(2028, 1, 1), quantity=100)]
        )

        order_path = tmp_path / "Заказ.xlsx"
        _build_order_file_with_expiry_column(order_path, [("Крем детский 100 мл", 10)])

        outcome = service.process(ProcessingRequest(order_path=order_path))

        result = outcome.results[0]
        assert result.status is MatchStatus.NOT_FOUND
        assert result.expiry_not_in_database is True
        assert result.certificate is None

        workbook = openpyxl.load_workbook(outcome.output_file)
        sheet = workbook["Заказ"]
        assert sheet.cell(row=2, column=2).font.strike is True
        assert sheet.cell(row=2, column=2).fill.fill_type == "solid"
        workbook.close()

    def test_row_with_preexisting_requested_expiry_skips_new_stage(
        self,
        order_service_with_expiry: tuple[
            OrderProcessingService, ExpiryStockRepository, CertificateProductRepository
        ],
        tmp_path: Path,
    ) -> None:
        """Заказ с уже указанным требуемым сроком не проходит через новый этап.

        База сроков годности настроена (не пуста — иначе сработал бы общий
        «выключенный» путь), но для этого товара в ней нет ни одной записи.
        Без короткого замыкания по уже заполненной колонке строка была бы
        ошибочно исключена как «товар отсутствует в базе сроков» — этого не
        должно произойти, раз человек уже указал срок сам.
        """
        service, expiry_stock, certificates = order_service_with_expiry
        certificates.replace_all(
            [
                make_certificate(
                    "Крем детский 100 мл", expiry_date=_FUTURE, certificate_number="UZ.1"
                )
            ]
        )
        expiry_stock.replace_all(
            [make_expiry_entry("Другой товар", expiry_date=dt.date(2028, 1, 1), quantity=100)]
        )

        order_path = tmp_path / "Заказ.xlsx"
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Заказ"
        sheet.append(["№", "Наименование товара", "Кол-во", "Требуемый срок годности"])
        sheet.append([1, "Крем детский 100 мл", 10, dt.date(2029, 1, 1)])
        workbook.save(order_path)

        outcome = service.process(ProcessingRequest(order_path=order_path))

        result = outcome.results[0]
        assert result.expiry_not_in_database is False
        assert result.expiry_auto_resolved is False

        workbook = openpyxl.load_workbook(outcome.output_file)
        sheet = workbook["Заказ"]
        cell = sheet.cell(row=2, column=4).value
        written_date = cell.date() if isinstance(cell, dt.datetime) else cell
        assert written_date == dt.date(2029, 1, 1)
        workbook.close()

    def test_empty_stock_database_leaves_existing_algorithm_untouched(
        self,
        order_service_with_expiry: tuple[
            OrderProcessingService, ExpiryStockRepository, CertificateProductRepository
        ],
        tmp_path: Path,
    ) -> None:
        """Неподключённая (пустая) база сроков годности не меняет поведения вообще.

        С сервисом, подключённым в контейнере, но без единого импорта — итог
        обработки должен быть в точности таким же, как без этой функции.
        """
        service, _expiry_stock, certificates = order_service_with_expiry
        certificates.replace_all(
            [
                make_certificate(
                    "Крем детский 100 мл", expiry_date=_FUTURE, certificate_number="UZ.1"
                )
            ]
        )

        order_path = tmp_path / "Заказ.xlsx"
        _build_order_file_with_expiry_column(order_path, [("Крем детский 100 мл", 10)])

        outcome = service.process(ProcessingRequest(order_path=order_path))

        result = outcome.results[0]
        assert result.status is MatchStatus.MATCHED
        assert result.expiry_not_in_database is False
        assert result.expiry_auto_resolved is False


class TestBatchCombinationIntegration:
    """Этап 2 целиком: заказ, который не покрывается одной партией, доходит до Excel.

    Сквозная проверка всего пути — от заказа без указанного срока годности
    до готового файла с несколькими сертификатами и колонкой распределения,
    — а не отдельного модуля: именно так это будет выглядеть при реальном
    нажатии кнопки в интерфейсе.
    """

    def test_order_fulfilled_by_two_batches_writes_multiline_excel(
        self,
        order_service_with_expiry: tuple[
            OrderProcessingService, ExpiryStockRepository, CertificateProductRepository
        ],
        tmp_path: Path,
    ) -> None:
        """Ни одна партия не покрывает заказ — используются две, обе видны в итоговом файле."""
        service, expiry_stock, certificates = order_service_with_expiry
        certificates.replace_all(
            [
                make_certificate(
                    "Крем детский 100 мл",
                    expiry_date=dt.date(2029, 5, 25),
                    certificate_number="UZ.1001",
                ),
                make_certificate(
                    "Крем детский 100 мл",
                    expiry_date=dt.date(2027, 1, 1),
                    certificate_number="UZ.1002",
                ),
            ]
        )
        expiry_stock.replace_all(
            [
                make_expiry_entry(
                    "Крем детский 100 мл", expiry_date=dt.date(2029, 5, 25), quantity=60
                ),
                make_expiry_entry(
                    "Крем детский 100 мл", expiry_date=dt.date(2027, 1, 1), quantity=50
                ),
            ]
        )

        order_path = tmp_path / "Заказ.xlsx"
        _build_order_file_with_expiry_column(order_path, [("Крем детский 100 мл", 100)])

        outcome = service.process(ProcessingRequest(order_path=order_path))

        result = outcome.results[0]
        assert result.status is MatchStatus.MATCHED
        assert len(result.batch_allocations) == 2
        assert [a.quantity for a in result.batch_allocations] == [60, 40]
        # Комбинация — не единый срок, колонка D (требуемый срок) остаётся
        # нетронутой (пустой), в отличие от случая с одной подобранной датой.
        assert result.expiry_auto_resolved is False
        assert result.row.requested_expiry is None

        workbook = openpyxl.load_workbook(outcome.output_file)
        sheet = workbook["Заказ"]
        # Колонки файла: №(1), Наименование(2), Кол-во(3), Требуемый срок(4),
        # Сертификат(5), Срок сертификата(6) — все существуют в исходном
        # файле; колонка распределения (7) новая, дописана writer'ом.
        certificate_cell = sheet.cell(row=2, column=5).value
        expiry_cell = sheet.cell(row=2, column=6).value
        allocation_cell = sheet.cell(row=2, column=7).value
        assert certificate_cell == "UZ.1001\nUZ.1002"
        assert expiry_cell == "25.05.2029\n01.01.2027"
        assert allocation_cell is not None and "60" in allocation_cell and "40" in allocation_cell
        assert sheet.cell(row=2, column=4).value is None
        workbook.close()

    def test_batch_without_certificate_excluded_from_order_total(
        self,
        order_service_with_expiry: tuple[
            OrderProcessingService, ExpiryStockRepository, CertificateProductRepository
        ],
        tmp_path: Path,
    ) -> None:
        """Партия без сертификата не засчитывается — заказ остаётся невыполненным.

        Сквозная проверка критического случая требования: физический остаток
        партии без сертификата (1000 шт.) не спасает заказ на 100 шт., если
        доступный (подтверждённый сертификатом) остаток — всего 60.
        """
        service, expiry_stock, certificates = order_service_with_expiry
        certificates.replace_all(
            [
                make_certificate(
                    "Крем детский 100 мл",
                    expiry_date=dt.date(2029, 5, 25),
                    certificate_number="UZ.1001",
                )
            ]
        )
        expiry_stock.replace_all(
            [
                make_expiry_entry(
                    "Крем детский 100 мл", expiry_date=dt.date(2029, 5, 25), quantity=60
                ),
                make_expiry_entry(
                    "Крем детский 100 мл", expiry_date=dt.date(2024, 1, 1), quantity=1000
                ),
            ]
        )

        order_path = tmp_path / "Заказ.xlsx"
        _build_order_file_with_expiry_column(order_path, [("Крем детский 100 мл", 100)])

        outcome = service.process(ProcessingRequest(order_path=order_path))

        result = outcome.results[0]
        assert result.status is MatchStatus.NOT_FOUND
        assert result.batch_allocations == []
        assert result.expiry_not_in_database is False
        assert result.expiry_no_certificate_available is False
        assert "Недостаточно остатка" in result.note
