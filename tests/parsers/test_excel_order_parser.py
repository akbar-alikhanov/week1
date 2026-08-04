"""Тесты парсера файлов заказа Excel."""

from __future__ import annotations

from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")

from app.core.exceptions import ColumnMappingError  # noqa: E402
from app.parsers.excel_order_parser import ExcelOrderParser  # noqa: E402


def _build_order(path: Path, *, header_row: int = 1) -> None:
    """Создаёт тестовый файл заказа."""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Заказ"

    offset = header_row - 1
    headers = ["№", "Наименование товара", "Кол-во"]
    for column, title in enumerate(headers, start=1):
        sheet.cell(row=header_row, column=column, value=title)

    rows = [
        (1, "Лечебные травы, сироп 100 мл", 10),
        (2, "Масло облепиховое 100 мл", 20),
        (3, "", None),  # пустая строка — должна быть пропущена
        (4, "Витамин C, таблетки жевательные", 30),
    ]
    for row_index, (number, name, quantity) in enumerate(rows, start=header_row + 1):
        sheet.cell(row=row_index, column=1, value=number)
        sheet.cell(row=row_index, column=2, value=name)
        sheet.cell(row=row_index, column=3, value=quantity)

    _ = offset
    workbook.save(path)


class TestExcelOrderParser:
    """Проверки разбора файла заказа."""

    def test_parses_standard_order(self, tmp_path: Path) -> None:
        """Стандартный заказ разбирается с корректным количеством позиций."""
        path = tmp_path / "order.xlsx"
        _build_order(path)

        document = ExcelOrderParser().parse(path)
        assert document.sheet_name == "Заказ"
        # Пустая строка пропущена — должно остаться 3 позиции.
        assert document.row_count == 3
        assert document.rows[0].product_name == "Лечебные травы, сироп 100 мл"

    def test_parses_order_with_shifted_header(self, tmp_path: Path) -> None:
        """Заказ со смещённой шапкой (шапка компании сверху) разбирается корректно."""
        path = tmp_path / "order_shifted.xlsx"
        _build_order(path, header_row=4)

        document = ExcelOrderParser().parse(path)
        assert document.header_row == 4
        assert document.row_count == 3

    def test_missing_product_column_raises(self, tmp_path: Path) -> None:
        """Файл без распознаваемой колонки наименования порождает ошибку."""
        path = tmp_path / "invalid.xlsx"
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.append(["1", "2", "3"])
        sheet.append(["4", "5", "6"])
        workbook.save(path)

        with pytest.raises(ColumnMappingError):
            ExcelOrderParser().parse(path)

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        """Отсутствующий файл порождает ожидаемое исключение."""
        from app.core.exceptions import ExcelParsingError

        with pytest.raises(ExcelParsingError):
            ExcelOrderParser().parse(tmp_path / "missing.xlsx")

    def test_xls_format_rejected_with_clear_message(self, tmp_path: Path) -> None:
        """Устаревший формат .xls отклоняется с понятным сообщением."""
        from app.core.exceptions import ExcelParsingError

        path = tmp_path / "legacy.xls"
        path.write_bytes(b"not a real xls")

        with pytest.raises(ExcelParsingError, match="xlsx"):
            ExcelOrderParser().parse(path)

    def test_list_sheets(self, tmp_path: Path) -> None:
        """Список листов книги читается корректно."""
        path = tmp_path / "order.xlsx"
        _build_order(path)
        assert ExcelOrderParser().list_sheets(path) == ["Заказ"]
