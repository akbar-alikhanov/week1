"""Формирование итогового файла Excel.

Исходный файл заказа никогда не изменяется — создаётся копия. Это требование
не только удобства, но и учётной дисциплины: оригинал документа поставщика
должен оставаться неприкосновенным.

Копия делается средствами openpyxl с сохранением форматирования, формул,
объединённых ячеек и ширины колонок: пользователь получает свой привычный
документ, в котором просто заполнены две колонки.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

from app.config.settings import ExportSettings
from app.core.constants import STATUS_AMBIGUOUS, STATUS_MATCHED, STATUS_NOT_FOUND
from app.core.exceptions import ExportError
from app.models.matching import MatchResult, MatchStatus
from app.models.order import OrderDocument
from app.parsers.column_mapper import ROLE_CERTIFICATE, ROLE_EXPIRY

_LOGGER = logging.getLogger(__name__)


class ExcelWriterService:
    """Записывает результаты подбора в копию файла заказа."""

    def __init__(self, settings: ExportSettings) -> None:
        """Создаёт сервис записи.

        Args:
            settings: Параметры выгрузки (цвета, названия колонок, формат дат).
        """
        self._settings = settings

    def build_output_path(self, order_path: Path, output_dir: Path | None = None) -> Path:
        """Определяет путь итогового файла.

        Args:
            order_path: Путь исходного файла заказа.
            output_dir: Каталог результата; ``None`` — рядом с заказом.

        Returns:
            Путь итогового файла, гарантированно не совпадающий с исходным.
        """
        directory = output_dir or order_path.parent
        stem = f"{order_path.stem}{self._settings.filename_suffix}"
        candidate = directory / f"{stem}.xlsx"

        index = 2
        while candidate.exists() or candidate.resolve() == order_path.resolve():
            candidate = directory / f"{stem}_{index}.xlsx"
            index += 1
        return candidate

    def write(
        self,
        document: OrderDocument,
        results: list[MatchResult],
        destination: Path,
    ) -> Path:
        """Создаёт копию заказа с заполненными сертификатами.

        Args:
            document: Разобранный заказ (нужен для карты колонок).
            results: Результаты подбора по строкам.
            destination: Путь итогового файла.

        Returns:
            Путь созданного файла.

        Raises:
            ExportError: Если файл не удалось записать.
        """
        try:
            from openpyxl import load_workbook
            from openpyxl.styles import Alignment, Font, PatternFill
        except ImportError as error:  # pragma: no cover — зависимость обязательна
            raise ExportError("Библиотека openpyxl недоступна", details=str(error)) from error

        try:
            workbook = load_workbook(document.path)
        except Exception as error:
            raise ExportError(
                f"Не удалось открыть файл заказа: {document.path.name}", details=str(error)
            ) from error

        try:
            if document.sheet_name not in workbook.sheetnames:
                raise ExportError(f"Лист «{document.sheet_name}» отсутствует в книге")
            sheet = workbook[document.sheet_name]

            certificate_column = self._resolve_column(
                sheet, document, ROLE_CERTIFICATE, self._settings.certificate_column_title
            )
            expiry_column = self._resolve_column(
                sheet, document, ROLE_EXPIRY, self._settings.expiry_column_title
            )
            score_column = (
                self._resolve_column(sheet, document, "score", "Совпадение, %")
                if self._settings.add_score_column
                else None
            )

            fills = {
                STATUS_MATCHED: PatternFill("solid", fgColor=self._settings.color_matched),
                STATUS_AMBIGUOUS: PatternFill("solid", fgColor=self._settings.color_ambiguous),
                STATUS_NOT_FOUND: PatternFill("solid", fgColor=self._settings.color_not_found),
            }
            alignment = Alignment(horizontal="center", vertical="center")

            written = 0
            for result in results:
                if result.status is MatchStatus.SKIPPED:
                    continue
                row_index = result.row.row_number

                certificate_cell = sheet.cell(row=row_index, column=certificate_column)
                certificate_cell.value = result.certificate_number or ""
                certificate_cell.alignment = alignment

                expiry_cell = sheet.cell(row=row_index, column=expiry_column)
                expiry_cell.value = self._format_expiry(result.expiry_date)
                expiry_cell.alignment = alignment

                if score_column is not None:
                    score_cell = sheet.cell(row=row_index, column=score_column)
                    score_cell.value = round(result.score * 100) if result.score else ""
                    score_cell.alignment = alignment

                if self._settings.highlight_rows:
                    fill = fills.get(_status_key(result.status))
                    if fill is not None:
                        self._highlight_row(sheet, row_index, fill, document)

                written += 1

            self._style_header(sheet, document.header_row, certificate_column, expiry_column, Font)
            self._autosize(sheet, (certificate_column, expiry_column))

            destination.parent.mkdir(parents=True, exist_ok=True)
            workbook.save(destination)
            _LOGGER.info("Создан файл результата: %s (заполнено строк: %s)", destination, written)
            return destination
        except ExportError:
            raise
        except Exception as error:
            raise ExportError(
                "Не удалось сформировать файл результата", details=str(error)
            ) from error
        finally:
            workbook.close()

    # ------------------------------------------------------------- внутреннее
    def _resolve_column(self, sheet: Any, document: OrderDocument, role: str, title: str) -> int:
        """Находит существующую колонку или создаёт новую.

        Args:
            sheet: Лист книги.
            document: Разобранный заказ.
            role: Роль колонки в карте заказа.
            title: Заголовок создаваемой колонки.

        Returns:
            Номер колонки (1-based).
        """
        index = document.column_map.get(role)
        if index is not None:
            return index + 1

        # Колонка отсутствует — добавляем справа от последней заполненной.
        # openpyxl не типизирован, поэтому max_column имеет тип Any — явное
        # приведение к int нужно, чтобы не «протащить» Any в сигнатуру метода.
        target = int(max(sheet.max_column + 1, len(document.headers) + 1))
        if document.header_row > 0:
            header_cell = sheet.cell(row=document.header_row, column=target)
            header_cell.value = title
        document.column_map[role] = target - 1
        _LOGGER.debug("Добавлена колонка «%s» (позиция %s)", title, target)
        return target

    def _highlight_row(
        self, sheet: Any, row_index: int, fill: Any, document: OrderDocument
    ) -> None:
        """Заливает цветом значимые ячейки строки."""
        last_column = max(sheet.max_column, len(document.headers))
        for column in range(1, last_column + 1):
            sheet.cell(row=row_index, column=column).fill = fill

    def _style_header(
        self,
        sheet: Any,
        header_row: int,
        certificate_column: int,
        expiry_column: int,
        font_class: Any,
    ) -> None:
        """Выделяет заголовки добавленных колонок."""
        if header_row <= 0:
            return
        for column in (certificate_column, expiry_column):
            cell = sheet.cell(row=header_row, column=column)
            if cell.value:
                cell.font = font_class(bold=True)

    def _autosize(self, sheet: Any, columns: tuple[int, ...]) -> None:
        """Задаёт разумную ширину заполненным колонкам."""
        from openpyxl.utils import get_column_letter

        for column in columns:
            letter = get_column_letter(column)
            current = sheet.column_dimensions[letter].width or 0
            sheet.column_dimensions[letter].width = max(current, 22)

    def _format_expiry(self, value: date | None) -> str:
        """Форматирует срок действия для ячейки Excel."""
        if value is None:
            return ""
        return value.strftime(self._settings.date_format)


def _status_key(status: MatchStatus) -> str:
    """Приводит статус к ключу цветовой схемы."""
    if status in (MatchStatus.MATCHED, MatchStatus.MANUAL):
        return STATUS_MATCHED
    if status is MatchStatus.AMBIGUOUS:
        return STATUS_AMBIGUOUS
    return STATUS_NOT_FOUND
