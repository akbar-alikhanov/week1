"""Тесты формирования итогового файла Excel."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from tests.conftest import make_certificate

openpyxl = pytest.importorskip("openpyxl")

from app.config.settings import ExportSettings  # noqa: E402
from app.models.matching import (  # noqa: E402
    MatchCandidate,
    MatchResult,
    MatchSource,
    MatchStatus,
    ScoreBreakdown,
)
from app.models.order import OrderDocument, OrderRow  # noqa: E402
from app.parsers.column_mapper import ROLE_PRODUCT  # noqa: E402
from app.services.excel_writer_service import ExcelWriterService  # noqa: E402


def _build_order_file(path: Path) -> None:
    """Создаёт минимальный файл заказа для тестов записи."""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Заказ"
    sheet.append(["№", "Наименование товара"])
    sheet.append([1, "Лечебные травы 100 мл"])
    sheet.append([2, "Товар без сертификата"])
    workbook.save(path)


def _document(path: Path) -> OrderDocument:
    """Строит объект заказа, соответствующий файлу из _build_order_file."""
    document = OrderDocument(
        path=path, sheet_name="Заказ", header_row=1, column_map={ROLE_PRODUCT: 1}
    )
    document.rows = [
        OrderRow(row_number=2, product_name="Лечебные травы 100 мл"),
        OrderRow(row_number=3, product_name="Товар без сертификата"),
    ]
    return document


def _matched_result(row: OrderRow) -> MatchResult:
    """Создаёт результат с найденным сертификатом."""
    certificate = make_certificate(
        row.product_name,
        certificate_number="UZ.183255",
        expiry_date=dt.date(2029, 3, 22),
    )
    score = ScoreBreakdown(name=1.0, volume=1.0, expiry=1.0, total=0.97)
    candidate = MatchCandidate(certificate=certificate, score=score, source=MatchSource.LEXICAL)
    return MatchResult(
        row=row, status=MatchStatus.MATCHED, candidates=[candidate], selected_index=0
    )


def _not_found_result(row: OrderRow) -> MatchResult:
    """Создаёт результат без найденного сертификата."""
    return MatchResult(row=row, status=MatchStatus.NOT_FOUND)


class TestBuildOutputPath:
    """Проверки формирования пути итогового файла."""

    def test_adds_suffix_to_stem(self, tmp_path: Path) -> None:
        """Итоговый файл получает суффикс из настроек."""
        writer = ExcelWriterService(ExportSettings())
        order_path = tmp_path / "Заказ.xlsx"
        output = writer.build_output_path(order_path)
        assert output.stem == "Заказ_с_сертификатами"
        assert output.parent == tmp_path

    def test_avoids_overwriting_existing_file(self, tmp_path: Path) -> None:
        """При существующем файле результата подбирается уникальное имя."""
        writer = ExcelWriterService(ExportSettings())
        order_path = tmp_path / "Заказ.xlsx"
        existing = writer.build_output_path(order_path)
        existing.write_text("занято")

        second = writer.build_output_path(order_path)
        assert second != existing
        assert not second.exists()

    def test_respects_custom_output_dir(self, tmp_path: Path) -> None:
        """Каталог результата можно задать отдельно от файла заказа."""
        writer = ExcelWriterService(ExportSettings())
        order_path = tmp_path / "orders" / "Заказ.xlsx"
        output_dir = tmp_path / "results"
        output = writer.build_output_path(order_path, output_dir)
        assert output.parent == output_dir


class TestWrite:
    """Проверки записи результатов в копию файла заказа."""

    def test_writes_certificate_and_expiry(self, tmp_path: Path) -> None:
        """Найденный сертификат и срок записываются в соответствующие ячейки."""
        order_path = tmp_path / "order.xlsx"
        _build_order_file(order_path)
        document = _document(order_path)
        results = [_matched_result(document.rows[0]), _not_found_result(document.rows[1])]

        writer = ExcelWriterService(ExportSettings())
        destination = writer.build_output_path(order_path)
        writer.write(document, results, destination)

        workbook = openpyxl.load_workbook(destination)
        sheet = workbook["Заказ"]
        assert sheet.cell(row=2, column=3).value == "UZ.183255"
        assert sheet.cell(row=2, column=4).value == "22.03.2029"
        assert sheet.cell(row=3, column=3).value in ("", None)
        workbook.close()

    def test_original_file_untouched(self, tmp_path: Path) -> None:
        """Исходный файл заказа не изменяется в процессе записи."""
        order_path = tmp_path / "order.xlsx"
        _build_order_file(order_path)
        original_bytes = order_path.read_bytes()

        document = _document(order_path)
        results = [_matched_result(document.rows[0]), _not_found_result(document.rows[1])]
        writer = ExcelWriterService(ExportSettings())
        writer.write(document, results, writer.build_output_path(order_path))

        assert order_path.read_bytes() == original_bytes

    def test_highlight_colors_applied(self, tmp_path: Path) -> None:
        """Строки подсвечиваются цветом согласно статусу."""
        order_path = tmp_path / "order.xlsx"
        _build_order_file(order_path)
        document = _document(order_path)
        settings = ExportSettings(highlight_rows=True)
        results = [_matched_result(document.rows[0]), _not_found_result(document.rows[1])]

        writer = ExcelWriterService(settings)
        destination = writer.build_output_path(order_path)
        writer.write(document, results, destination)

        workbook = openpyxl.load_workbook(destination)
        sheet = workbook["Заказ"]
        matched_fill = sheet.cell(row=2, column=2).fill.fgColor.rgb
        not_found_fill = sheet.cell(row=3, column=2).fill.fgColor.rgb
        assert matched_fill != not_found_fill
        workbook.close()

    def test_highlight_disabled_leaves_no_fill(self, tmp_path: Path) -> None:
        """При выключенной подсветке заливка не применяется."""
        order_path = tmp_path / "order.xlsx"
        _build_order_file(order_path)
        document = _document(order_path)
        settings = ExportSettings(highlight_rows=False)
        results = [_matched_result(document.rows[0])]

        writer = ExcelWriterService(settings)
        destination = writer.build_output_path(order_path)
        writer.write(document, results, destination)

        workbook = openpyxl.load_workbook(destination)
        sheet = workbook["Заказ"]
        fill_type = sheet.cell(row=2, column=2).fill.fill_type
        assert fill_type is None
        workbook.close()
