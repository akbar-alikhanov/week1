"""Тесты формирования итогового файла Excel."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

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
from app.parsers.column_mapper import (  # noqa: E402
    ROLE_CERTIFICATE,
    ROLE_CERTIFICATE_EXPIRY,
    ROLE_EXPIRY,
    ROLE_PRODUCT,
    ROLE_QUANTITY,
)
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


def _build_order_file_with_requested_expiry(path: Path) -> None:
    """Создаёт файл заказа с колонкой требуемого срока годности (роль ROLE_EXPIRY).

    Именно такой файл воспроизводит критическую ошибку из отчёта: колонка D
    «Требуемый срок годности» уже заполнена значениями из заказа и не должна
    измениться после записи результата подбора.
    """
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Заказ"
    sheet.append(["№", "Наименование товара", "Кол-во", "Требуемый срок годности"])
    sheet.append([1, "Лечебные травы 100 мл", 10, dt.date(2029, 4, 1)])
    sheet.append([2, "Товар без сертификата", 5, dt.date(2028, 1, 15)])
    workbook.save(path)


def _document_with_requested_expiry(path: Path) -> OrderDocument:
    """Строит объект заказа, соответствующий _build_order_file_with_requested_expiry."""
    document = OrderDocument(
        path=path,
        sheet_name="Заказ",
        header_row=1,
        column_map={ROLE_PRODUCT: 1, ROLE_QUANTITY: 2, ROLE_EXPIRY: 3},
    )
    document.rows = [
        OrderRow(
            row_number=2,
            product_name="Лечебные травы 100 мл",
            quantity=10,
            requested_expiry=dt.date(2029, 4, 1),
        ),
        OrderRow(
            row_number=3,
            product_name="Товар без сертификата",
            quantity=5,
            requested_expiry=dt.date(2028, 1, 15),
        ),
    ]
    return document


def _cell_date(sheet: Any, row: int, column: int) -> dt.date | None:
    """Приводит значение ячейки к ``date`` (openpyxl округляет date до datetime)."""
    value = sheet.cell(row=row, column=column).value
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return None


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


class TestRequestedExpiryNeverOverwritten:
    """Регрессия критической ошибки: требуемый срок годности заказа (роль
    ``ROLE_EXPIRY``) раньше затирался сроком годности НАЙДЕННОГО сертификата,
    потому что обе даты писались в одну и ту же колонку. Теперь у срока
    найденного сертификата отдельная роль (``ROLE_CERTIFICATE_EXPIRY``), и
    колонка с требуемым сроком заказа никогда не участвует в записи.
    """

    def test_requested_expiry_column_untouched_after_write(self, tmp_path: Path) -> None:
        """Значения в колонке требуемого срока годности не меняются после write()."""
        order_path = tmp_path / "order.xlsx"
        _build_order_file_with_requested_expiry(order_path)
        document = _document_with_requested_expiry(order_path)
        results = [_matched_result(document.rows[0]), _not_found_result(document.rows[1])]

        writer = ExcelWriterService(ExportSettings())
        destination = writer.build_output_path(order_path)
        writer.write(document, results, destination)

        workbook = openpyxl.load_workbook(destination)
        sheet = workbook["Заказ"]
        assert _cell_date(sheet, 2, 4) == dt.date(2029, 4, 1)
        assert _cell_date(sheet, 3, 4) == dt.date(2028, 1, 15)
        workbook.close()

    def test_certificate_number_and_expiry_written_to_new_columns(self, tmp_path: Path) -> None:
        """Найденный сертификат и его срок пишутся в новые колонки E/F с нужными заголовками."""
        order_path = tmp_path / "order.xlsx"
        _build_order_file_with_requested_expiry(order_path)
        document = _document_with_requested_expiry(order_path)
        results = [_matched_result(document.rows[0]), _not_found_result(document.rows[1])]

        writer = ExcelWriterService(ExportSettings())
        destination = writer.build_output_path(order_path)
        writer.write(document, results, destination)

        workbook = openpyxl.load_workbook(destination)
        sheet = workbook["Заказ"]
        assert sheet.cell(row=1, column=5).value == "Сертификат"
        assert sheet.cell(row=2, column=5).value == "UZ.183255"
        assert sheet.cell(row=1, column=6).value == "С.Г. сертификата"
        assert sheet.cell(row=2, column=6).value == "22.03.2029"
        workbook.close()

    def test_order_number_name_and_quantity_untouched(self, tmp_path: Path) -> None:
        """Колонки A/B/C (номер, наименование, количество) не изменяются."""
        order_path = tmp_path / "order.xlsx"
        _build_order_file_with_requested_expiry(order_path)
        document = _document_with_requested_expiry(order_path)
        results = [_matched_result(document.rows[0]), _not_found_result(document.rows[1])]

        writer = ExcelWriterService(ExportSettings())
        destination = writer.build_output_path(order_path)
        writer.write(document, results, destination)

        workbook = openpyxl.load_workbook(destination)
        sheet = workbook["Заказ"]
        assert sheet.cell(row=2, column=1).value == 1
        assert sheet.cell(row=2, column=2).value == "Лечебные травы 100 мл"
        assert sheet.cell(row=2, column=3).value == 10
        assert sheet.cell(row=3, column=1).value == 2
        assert sheet.cell(row=3, column=2).value == "Товар без сертификата"
        assert sheet.cell(row=3, column=3).value == 5
        workbook.close()

    def test_existing_certificate_expiry_column_is_reused_not_duplicated(
        self, tmp_path: Path
    ) -> None:
        """Повторная обработка уже обработанного файла не плодит дублирующих колонок.

        Файл уже содержит колонки «Сертификат» и «С.Г. сертификата» (как
        будто это результат прошлой обработки) — writer обязан их
        переиспользовать, а не сдвигать/дублировать существующие колонки.
        """
        order_path = tmp_path / "order.xlsx"
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
                "С.Г. сертификата",
            ]
        )
        sheet.append([1, "Лечебные травы 100 мл", 10, dt.date(2029, 4, 1), None, None])
        workbook.save(order_path)

        document = OrderDocument(
            path=order_path,
            sheet_name="Заказ",
            header_row=1,
            column_map={
                ROLE_PRODUCT: 1,
                ROLE_QUANTITY: 2,
                ROLE_EXPIRY: 3,
                ROLE_CERTIFICATE: 4,
                ROLE_CERTIFICATE_EXPIRY: 5,
            },
        )
        row = OrderRow(
            row_number=2,
            product_name="Лечебные травы 100 мл",
            quantity=10,
            requested_expiry=dt.date(2029, 4, 1),
        )
        document.rows = [row]

        writer = ExcelWriterService(ExportSettings())
        destination = writer.build_output_path(order_path)
        writer.write(document, [_matched_result(row)], destination)

        result_workbook = openpyxl.load_workbook(destination)
        result_sheet = result_workbook["Заказ"]
        assert result_sheet.max_column == 6
        assert _cell_date(result_sheet, 2, 4) == dt.date(2029, 4, 1)
        assert result_sheet.cell(row=2, column=5).value == "UZ.183255"
        assert result_sheet.cell(row=2, column=6).value == "22.03.2029"
        result_workbook.close()
