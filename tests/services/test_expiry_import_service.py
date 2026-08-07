"""Тесты сервиса импорта Excel-базы сроков годности и остатков."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pytest

openpyxl = pytest.importorskip("openpyxl")

from app.core.events import AppEvent, EventBus  # noqa: E402
from app.repositories.expiry_stock_repository import ExpiryStockRepository  # noqa: E402
from app.repositories.settings_repository import SettingsRepository  # noqa: E402
from app.services.expiry_import_service import ExpiryImportService  # noqa: E402


def _build_expiry_stock_file(
    path: Path, rows: list[tuple[Any, Any, Any]], *, with_header: bool = True
) -> None:
    """Создаёт тестовый файл базы сроков годности (A=название, B=срок, C=количество)."""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    if with_header:
        sheet.append(["Наименование", "Срок годности", "Количество"])
    for row in rows:
        sheet.append(list(row))
    workbook.save(path)


@pytest.fixture
def event_bus() -> EventBus:
    """Шина событий для перехвата публикаций сервиса импорта."""
    return EventBus()


@pytest.fixture
def expiry_import_service(
    expiry_stock_repository: ExpiryStockRepository,
    settings_repository: SettingsRepository,
    event_bus: EventBus,
) -> ExpiryImportService:
    """Собранный сервис импорта базы сроков годности поверх временной базы."""
    return ExpiryImportService(expiry_stock_repository, settings_repository, event_bus)


class TestImportFile:
    """Проверки чтения файла и переноса его содержимого в SQLite."""

    def test_imports_all_valid_rows(
        self,
        expiry_import_service: ExpiryImportService,
        expiry_stock_repository: ExpiryStockRepository,
        tmp_path: Path,
    ) -> None:
        """Каждая строка с названием товара попадает в базу."""
        path = tmp_path / "stock.xlsx"
        _build_expiry_stock_file(
            path,
            [
                ("Товар A", dt.date(2026, 1, 1), 10),
                ("Товар B", dt.date(2027, 1, 1), 20),
            ],
        )

        result = expiry_import_service.import_file(path)

        assert result.failed is False
        assert result.imported == 2
        assert expiry_stock_repository.count() == 2

    def test_file_without_header_reads_first_row_as_data(
        self, expiry_import_service: ExpiryImportService, tmp_path: Path
    ) -> None:
        """Файл без строки заголовка не теряет первую строку данных."""
        path = tmp_path / "stock.xlsx"
        _build_expiry_stock_file(path, [("Товар", dt.date(2026, 1, 1), 5)], with_header=False)

        result = expiry_import_service.import_file(path)
        assert result.imported == 1

    def test_row_without_product_name_is_skipped_and_counted(
        self, expiry_import_service: ExpiryImportService, tmp_path: Path
    ) -> None:
        """Строка без названия товара, но с другими данными, считается пропущенной."""
        path = tmp_path / "stock.xlsx"
        _build_expiry_stock_file(
            path,
            [
                ("Товар A", dt.date(2026, 1, 1), 10),
                ("", dt.date(2026, 1, 1), 5),
            ],
        )

        result = expiry_import_service.import_file(path)
        assert result.imported == 1
        assert result.skipped_rows == 1

    def test_fully_blank_row_is_not_counted_as_skipped(
        self, expiry_import_service: ExpiryImportService, tmp_path: Path
    ) -> None:
        """Полностью пустая строка (не строка с данными) не портит статистику."""
        path = tmp_path / "stock.xlsx"
        _build_expiry_stock_file(
            path,
            [
                ("Товар A", dt.date(2026, 1, 1), 10),
                (None, None, None),
            ],
        )

        result = expiry_import_service.import_file(path)
        assert result.imported == 1
        assert result.skipped_rows == 0

    def test_quantity_accepts_comma_decimal_separator(
        self,
        expiry_import_service: ExpiryImportService,
        expiry_stock_repository: ExpiryStockRepository,
        tmp_path: Path,
    ) -> None:
        """Количество с запятой вместо точки распознаётся (частый формат Excel в РФ)."""
        path = tmp_path / "stock.xlsx"
        _build_expiry_stock_file(path, [("Товар", dt.date(2026, 1, 1), "10,5")])

        expiry_import_service.import_file(path)
        entries = expiry_stock_repository.list_all()
        assert entries[0].quantity == 10.5

    def test_missing_file_returns_failed_result(
        self, expiry_import_service: ExpiryImportService, tmp_path: Path
    ) -> None:
        """Отсутствующий файл не роняет сервис, а возвращает результат с ошибкой."""
        result = expiry_import_service.import_file(tmp_path / "missing.xlsx")
        assert result.failed is True
        assert "не найден" in result.error

    def test_failed_import_does_not_update_last_path(
        self, expiry_import_service: ExpiryImportService, tmp_path: Path
    ) -> None:
        """Неудачный импорт не запоминает путь как «последний импортированный»."""
        expiry_import_service.import_file(tmp_path / "missing.xlsx")
        assert expiry_import_service.last_path() == ""

    def test_reimport_replaces_previous_data(
        self,
        expiry_import_service: ExpiryImportService,
        expiry_stock_repository: ExpiryStockRepository,
        tmp_path: Path,
    ) -> None:
        """Повторный импорт заменяет содержимое базы, а не дополняет его."""
        first = tmp_path / "stock_v1.xlsx"
        _build_expiry_stock_file(first, [("Товар A", dt.date(2026, 1, 1), 10)])
        expiry_import_service.import_file(first)

        second = tmp_path / "stock_v2.xlsx"
        _build_expiry_stock_file(second, [("Товар B", dt.date(2026, 1, 1), 20)])
        expiry_import_service.import_file(second)

        entries = expiry_stock_repository.list_all()
        assert len(entries) == 1
        assert entries[0].product_name == "Товар B"

    def test_publishes_started_and_finished_events(
        self, expiry_import_service: ExpiryImportService, event_bus: EventBus, tmp_path: Path
    ) -> None:
        """Импорт публикует оба события шины в правильном порядке."""
        received: list[str] = []
        event_bus.subscribe(
            AppEvent.EXPIRY_STOCK_IMPORT_STARTED, lambda **_: received.append("started")
        )
        event_bus.subscribe(
            AppEvent.EXPIRY_STOCK_IMPORT_FINISHED, lambda **_: received.append("finished")
        )

        path = tmp_path / "stock.xlsx"
        _build_expiry_stock_file(path, [("Товар", dt.date(2026, 1, 1), 5)])
        expiry_import_service.import_file(path)

        assert received == ["started", "finished"]

    def test_publishes_finished_event_even_on_failure(
        self, expiry_import_service: ExpiryImportService, event_bus: EventBus, tmp_path: Path
    ) -> None:
        """Событие завершения публикуется и при ошибке — интерфейс не должен зависать."""
        received: list[str] = []
        event_bus.subscribe(
            AppEvent.EXPIRY_STOCK_IMPORT_FINISHED, lambda **_: received.append("finished")
        )
        expiry_import_service.import_file(tmp_path / "missing.xlsx")
        assert received == ["finished"]


class TestNeedsReimport:
    """Проверки обнаружения изменений файла базы."""

    def test_true_when_never_imported(
        self, expiry_import_service: ExpiryImportService, tmp_path: Path
    ) -> None:
        """Ещё не импортированный файл всегда требует импорта."""
        path = tmp_path / "stock.xlsx"
        _build_expiry_stock_file(path, [("Товар", dt.date(2026, 1, 1), 5)])
        assert expiry_import_service.needs_reimport(path) is True

    def test_false_immediately_after_import(
        self, expiry_import_service: ExpiryImportService, tmp_path: Path
    ) -> None:
        """Только что импортированный, неизменившийся файл не требует переимпорта."""
        path = tmp_path / "stock.xlsx"
        _build_expiry_stock_file(path, [("Товар", dt.date(2026, 1, 1), 5)])
        expiry_import_service.import_file(path)
        assert expiry_import_service.needs_reimport(path) is False

    def test_true_after_file_content_changes(
        self, expiry_import_service: ExpiryImportService, tmp_path: Path
    ) -> None:
        """Изменение содержимого файла (другой размер) снова требует импорта."""
        path = tmp_path / "stock.xlsx"
        _build_expiry_stock_file(path, [("Товар", dt.date(2026, 1, 1), 5)])
        expiry_import_service.import_file(path)

        _build_expiry_stock_file(
            path,
            [("Товар", dt.date(2026, 1, 1), 5), ("Товар 2", dt.date(2027, 1, 1), 6)],
        )
        assert expiry_import_service.needs_reimport(path) is True

    def test_false_for_missing_file(
        self, expiry_import_service: ExpiryImportService, tmp_path: Path
    ) -> None:
        """Несуществующий файл не запрашивает импорт — его нечем импортировать."""
        assert expiry_import_service.needs_reimport(tmp_path / "missing.xlsx") is False


class TestState:
    """Проверки служебного состояния (путь и время последнего импорта)."""

    def test_last_path_empty_before_first_import(
        self, expiry_import_service: ExpiryImportService
    ) -> None:
        """До первого импорта путь пуст."""
        assert expiry_import_service.last_path() == ""

    def test_last_path_after_import(
        self, expiry_import_service: ExpiryImportService, tmp_path: Path
    ) -> None:
        """После успешного импорта путь запоминается дословно."""
        path = tmp_path / "stock.xlsx"
        _build_expiry_stock_file(path, [("Товар", dt.date(2026, 1, 1), 5)])
        expiry_import_service.import_file(path)
        assert expiry_import_service.last_path() == str(path)

    def test_last_imported_at_empty_before_first_import(
        self, expiry_import_service: ExpiryImportService
    ) -> None:
        """До первого импорта отметка времени пуста."""
        assert expiry_import_service.last_imported_at() == ""

    def test_last_imported_at_set_after_import(
        self, expiry_import_service: ExpiryImportService, tmp_path: Path
    ) -> None:
        """После импорта отметка времени заполняется."""
        path = tmp_path / "stock.xlsx"
        _build_expiry_stock_file(path, [("Товар", dt.date(2026, 1, 1), 5)])
        expiry_import_service.import_file(path)
        assert expiry_import_service.last_imported_at() != ""
