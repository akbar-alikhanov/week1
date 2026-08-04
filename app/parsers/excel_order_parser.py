"""Чтение файла заказа в формате Excel."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.core.dates import parse_date
from app.core.exceptions import ColumnMappingError, ExcelParsingError
from app.models.order import OrderDocument, OrderRow
from app.parsers.column_mapper import (
    ROLE_BRAND,
    ROLE_CERTIFICATE,
    ROLE_CODE,
    ROLE_EXPIRY,
    ROLE_PRICE,
    ROLE_PRODUCT,
    ROLE_QUANTITY,
    ROLE_UNIT,
    ROLE_VOLUME,
    ColumnMapping,
    detect_mapping,
)

_LOGGER = logging.getLogger(__name__)

#: Сколько подряд идущих пустых строк считается концом таблицы.
_EMPTY_ROW_LIMIT = 25

#: Сколько строк читается для распознавания структуры.
_PROBE_ROWS = 40


class ExcelOrderParser:
    """Разбирает файл заказа и возвращает доменный объект.

    Парсер работает в режиме ``read_only`` библиотеки openpyxl: файл заказа
    может содержать десятки тысяч строк, и потоковое чтение экономит память
    и время старта.
    """

    def __init__(self, *, max_rows: int = 200_000) -> None:
        """Создаёт парсер.

        Args:
            max_rows: Верхняя граница числа читаемых строк (защита от
                повреждённых файлов с миллионами пустых строк).
        """
        self._max_rows = max_rows

    def list_sheets(self, path: Path) -> list[str]:
        """Возвращает имена листов книги.

        Args:
            path: Путь к файлу заказа.

        Returns:
            Список имён листов.

        Raises:
            ExcelParsingError: Если файл не удалось открыть.
        """
        workbook = self._open(path)
        try:
            return list(workbook.sheetnames)
        finally:
            workbook.close()

    def parse(self, path: Path, *, sheet_name: str | None = None) -> OrderDocument:
        """Читает заказ из файла.

        Если имя листа не указано, выбирается лист с наибольшим количеством
        распознанных колонок — это надёжнее, чем брать первый попавшийся
        (в реальных файлах первым часто идёт лист «Титульный»).

        Args:
            path: Путь к файлу заказа.
            sheet_name: Имя листа; ``None`` — выбрать автоматически.

        Returns:
            Разобранный заказ.

        Raises:
            ExcelParsingError: Если файл нечитаем.
            ColumnMappingError: Если колонка с наименованием не найдена.
        """
        workbook = self._open(path)
        try:
            target_sheets = [sheet_name] if sheet_name else list(workbook.sheetnames)
            best: tuple[OrderDocument, float] | None = None

            for name in target_sheets:
                if name not in workbook.sheetnames:
                    raise ExcelParsingError(f"Лист «{name}» отсутствует в файле", path=path)
                worksheet = workbook[name]
                document, confidence = self._parse_sheet(path, worksheet, name)
                if document is None:
                    continue
                if best is None or confidence > best[1]:
                    best = (document, confidence)
                if sheet_name:
                    break

            if best is None:
                raise ColumnMappingError(
                    "В файле заказа не найдена колонка с наименованием товара. "
                    "Убедитесь, что таблица содержит заголовок «Наименование» или «Товар».",
                    path=path,
                )

            document = best[0]
            _LOGGER.info(
                "Заказ %s: лист «%s», позиций %s, %s",
                path.name,
                document.sheet_name,
                document.row_count,
                _describe_columns(document.column_map),
            )
            return document
        finally:
            workbook.close()

    # ------------------------------------------------------------- внутреннее
    def _open(self, path: Path) -> Any:
        """Открывает книгу Excel в потоковом режиме."""
        if not path.exists():
            raise ExcelParsingError(f"Файл не найден: {path}", path=path)
        if path.suffix.lower() == ".xls":
            raise ExcelParsingError(
                "Формат .xls не поддерживается. Сохраните файл как .xlsx "
                "(Файл → Сохранить как → Книга Excel).",
                path=path,
            )
        try:
            from openpyxl import load_workbook

            return load_workbook(path, read_only=True, data_only=True)
        except ExcelParsingError:
            raise
        except Exception as error:
            raise ExcelParsingError(
                f"Не удалось открыть файл заказа: {path.name}", path=path, details=str(error)
            ) from error

    def _parse_sheet(
        self, path: Path, worksheet: Any, sheet_name: str
    ) -> tuple[OrderDocument | None, float]:
        """Разбирает отдельный лист книги."""
        rows_iterator = worksheet.iter_rows(values_only=True)
        probe: list[list[Any]] = []
        for index, row in enumerate(rows_iterator):
            probe.append(list(row))
            if index + 1 >= _PROBE_ROWS:
                break

        if not probe:
            return (None, 0.0)

        mapping = detect_mapping(probe)
        if not mapping.is_valid:
            return (None, 0.0)

        product_index = mapping.columns[ROLE_PRODUCT]
        document = OrderDocument(
            path=path,
            sheet_name=sheet_name,
            header_row=mapping.header_row,
            column_map=dict(mapping.columns),
            headers=mapping.headers,
        )

        empty_streak = 0
        row_number = 0
        for values in self._iterate_rows(worksheet, probe, mapping):
            row_number += 1
            if row_number > self._max_rows:
                _LOGGER.warning("Достигнут предел в %s строк — чтение остановлено", self._max_rows)
                break

            absolute_row = mapping.header_row + row_number
            product = _text(values, product_index)
            if not product:
                empty_streak += 1
                if empty_streak >= _EMPTY_ROW_LIMIT:
                    break
                continue
            empty_streak = 0

            document.rows.append(
                OrderRow(
                    row_number=absolute_row,
                    product_name=product,
                    quantity=_number(values, mapping.index_of(ROLE_QUANTITY)),
                    requested_expiry=parse_date(_value(values, mapping.index_of(ROLE_EXPIRY))),
                    declared_volume=_text(values, mapping.index_of(ROLE_VOLUME)),
                    brand=_text(values, mapping.index_of(ROLE_BRAND)),
                    extra={
                        "code": _text(values, mapping.index_of(ROLE_CODE)),
                        "unit": _text(values, mapping.index_of(ROLE_UNIT)),
                        "price": _number(values, mapping.index_of(ROLE_PRICE)),
                    },
                )
            )

        document.total_sheet_rows = mapping.header_row + row_number
        if not document.rows:
            return (None, 0.0)
        return (document, mapping.confidence + min(0.5, len(document.rows) / 200))

    def _iterate_rows(self, worksheet: Any, probe: list[list[Any]], mapping: ColumnMapping) -> Any:
        """Итерирует строки данных, продолжая уже прочитанный фрагмент.

        Лист в режиме ``read_only`` можно обойти повторно, но это означает
        второе чтение файла. Вместо этого используется уже загруженный
        фрагмент, а итератор продолжает с того места, где он остановился.
        """
        yield from probe[mapping.header_row :]
        if len(probe) < _PROBE_ROWS:
            return
        for row in worksheet.iter_rows(min_row=_PROBE_ROWS + 1, values_only=True):
            yield list(row)


def _value(values: list[Any], index: int | None) -> Any:
    """Возвращает значение ячейки по индексу, безопасно обрабатывая границы."""
    if index is None or index < 0 or index >= len(values):
        return None
    return values[index]


def _text(values: list[Any], index: int | None) -> str:
    """Возвращает строковое значение ячейки."""
    value = _value(values, index)
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"none", "nan", "-", "—"} else text


def _number(values: list[Any], index: int | None) -> float | None:
    """Возвращает числовое значение ячейки."""
    value = _value(values, index)
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", ".").replace(" ", ""))
    except ValueError:
        return None


def _describe_columns(column_map: dict[str, int]) -> str:
    """Формирует читаемое описание сопоставления колонок для журнала."""
    labels = {
        ROLE_PRODUCT: "товар",
        ROLE_QUANTITY: "количество",
        ROLE_VOLUME: "объём",
        ROLE_BRAND: "бренд",
        ROLE_CERTIFICATE: "сертификат",
        ROLE_EXPIRY: "срок",
        ROLE_CODE: "код",
    }
    parts = [labels.get(role, role) for role in column_map if role in labels]
    return "колонки: " + ", ".join(parts) if parts else "колонки не размечены"
