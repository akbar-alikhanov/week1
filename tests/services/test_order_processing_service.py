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
from app.repositories.history_repository import HistoryRepository  # noqa: E402
from app.repositories.product_repository import ProductRepository  # noqa: E402
from app.services.alias_service import AliasService  # noqa: E402
from app.services.matching_service import MatchingService  # noqa: E402
from app.services.order_processing_service import (  # noqa: E402
    OrderProcessingService,
    ProcessingRequest,
)
from app.services.report_service import ReportService  # noqa: E402
from tests.conftest import make_certificate  # noqa: E402

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

        assert alias_repository.count() == 1
