"""Формирование итогового файла Excel.

Исходный файл заказа никогда не изменяется — создаётся копия. Это требование
не только удобства, но и учётной дисциплины: оригинал документа поставщика
должен оставаться неприкосновенным. Это касается не только самого файла
(копия вместо правки на месте), но и КОЛОНОК внутри копии: программа только
ДОБАВЛЯЕТ результат подбора в две свои колонки (номер найденного сертификата
и его срок годности), не трогая ни одну из колонок исходного заказа —
порядковый номер, наименование, количество и, что особенно важно, требуемый
срок годности заказа (:attr:`~app.models.order.OrderRow.requested_expiry`,
роль :data:`~app.parsers.column_mapper.ROLE_EXPIRY`). Раньше срок найденного
сертификата ошибочно писался в ту же колонку, что и требуемый срок заказа —
это стирало исходные данные и было критической ошибкой; теперь у срока
найденного сертификата отдельная роль
(:data:`~app.parsers.column_mapper.ROLE_CERTIFICATE_EXPIRY`), которая не
пересекается с ролью требуемого срока ни по смыслу, ни по ключевым словам
заголовка.

Единственное исключение из «колонка требуемого срока никогда не изменяется» —
строки, где этой колонки в заказе изначально не было заполнено вообще: для
них новый этап подбора (:class:`~app.services.expiry_resolution_service.ExpiryResolutionService`)
сам определяет подходящий срок ДО поиска сертификата, и требование продукта
явно предписывает записать подобранный срок в эту же колонку заказа. Такая
запись выполняется, только если строка помечена
:attr:`~app.models.matching.MatchResult.expiry_auto_resolved` — то есть срок
был подобран, а не взят из заказа, — и только в уже существующую колонку;
если такой колонки в заказе нет вообще, она не создаётся, а колонка
пропускается.

Если для строки заказа одной партии не хватило и подбор срока годности
собрал её из нескольких партий сразу (Этап 2 —
:attr:`~app.models.matching.MatchResult.batch_allocations`), колонки E и F
получают не одно, а все использованные значения — каждое на отдельной
строке внутри той же ячейки (перенос строки), — а третья, новая колонка G
(:data:`~app.parsers.column_mapper.ROLE_BATCH_ALLOCATION`) построчно
показывает, сколько именно взято из какой партии. Для обычных, однопартийных
строк колонка G остаётся пустой.

Копия делается средствами openpyxl с сохранением форматирования, формул,
объединённых ячеек и ширины колонок: пользователь получает свой привычный
документ, в котором просто добавлены (или обновлены, если уже существуют)
колонки «Сертификат», «С.Г. сертификата» и «Распределение количества».
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
from app.parsers.column_mapper import (
    ROLE_BATCH_ALLOCATION,
    ROLE_CERTIFICATE,
    ROLE_CERTIFICATE_EXPIRY,
    ROLE_EXPIRY,
)

_LOGGER = logging.getLogger(__name__)


class ExcelWriterService:
    """Записывает результаты подбора в копию файла заказа.

    Пишет в свои колонки — номер найденного сертификата, его срок годности
    и (только для строк, выполненных несколькими партиями сразу)
    распределение количества по ним (роли
    :data:`~app.parsers.column_mapper.ROLE_CERTIFICATE`,
    :data:`~app.parsers.column_mapper.ROLE_CERTIFICATE_EXPIRY`,
    :data:`~app.parsers.column_mapper.ROLE_BATCH_ALLOCATION`) — и никогда не
    создаёт новых колонок сверх этих трёх. Колонка требуемого срока годности
    (:data:`~app.parsers.column_mapper.ROLE_EXPIRY`) не создаётся и не
    перезаписывается, если в ней уже было значение; единственное исключение —
    строки с :attr:`~app.models.matching.MatchResult.expiry_auto_resolved`
    (колонка была пуста, срок подобран новым этапом до поиска сертификата) —
    см. докстринг модуля.
    """

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
            # ВАЖНО: срок НАЙДЕННОГО сертификата пишется по роли
            # ROLE_CERTIFICATE_EXPIRY, а не ROLE_EXPIRY — последняя относится
            # к требуемому сроку годности заказа и никогда не должна
            # затрагиваться записью результата (см. докстринг модуля).
            expiry_column = self._resolve_column(
                sheet, document, ROLE_CERTIFICATE_EXPIRY, self._settings.expiry_column_title
            )
            allocation_column = self._resolve_column(
                sheet,
                document,
                ROLE_BATCH_ALLOCATION,
                self._settings.batch_allocation_column_title,
            )
            score_column = (
                self._resolve_column(sheet, document, "score", "Совпадение, %")
                if self._settings.add_score_column
                else None
            )
            # Только чтение позиции существующей колонки — в отличие от
            # certificate_column/expiry_column, колонка требуемого срока
            # никогда не создаётся заново: у неё особый смысл (согласована с
            # поставщиком в самом заказе), и её отсутствие не повод её
            # придумывать.
            requested_expiry_index = document.column_map.get(ROLE_EXPIRY)
            requested_expiry_column = (
                requested_expiry_index + 1 if requested_expiry_index is not None else None
            )

            fills = {
                STATUS_MATCHED: PatternFill("solid", fgColor=self._settings.color_matched),
                STATUS_AMBIGUOUS: PatternFill("solid", fgColor=self._settings.color_ambiguous),
                STATUS_NOT_FOUND: PatternFill("solid", fgColor=self._settings.color_not_found),
            }
            expiry_missing_fill = PatternFill("solid", fgColor=self._settings.color_expiry_missing)
            alignment = Alignment(horizontal="center", vertical="center")
            wrap_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

            written = 0
            for result in results:
                if result.status is MatchStatus.SKIPPED:
                    continue
                row_index = result.row.row_number

                certificate_cell = sheet.cell(row=row_index, column=certificate_column)
                expiry_cell = sheet.cell(row=row_index, column=expiry_column)
                allocation_cell = sheet.cell(row=row_index, column=allocation_column)

                if result.batch_allocations:
                    # Этап 2: одной партии не хватило, заказ выполнен
                    # несколькими сразу — каждая партия на отдельной строке
                    # внутри той же ячейки (см. докстринг модуля).
                    certificate_cell.value = "\n".join(
                        allocation.certificate.display_number
                        for allocation in result.batch_allocations
                    )
                    certificate_cell.alignment = wrap_alignment

                    expiry_cell.value = "\n".join(
                        self._format_expiry(allocation.expiry_date)
                        for allocation in result.batch_allocations
                    )
                    expiry_cell.alignment = wrap_alignment

                    allocation_cell.value = "\n".join(
                        f"{_format_quantity(allocation.quantity)} шт. → "
                        f"{self._format_expiry(allocation.expiry_date)}"
                        for allocation in result.batch_allocations
                    )
                    allocation_cell.alignment = wrap_alignment
                else:
                    certificate_cell.value = result.certificate_number or ""
                    certificate_cell.alignment = alignment

                    expiry_cell.value = self._format_expiry(result.expiry_date)
                    expiry_cell.alignment = alignment

                    # Строка могла быть выполнена несколькими партиями при
                    # предыдущей обработке того же файла — очищаем колонку,
                    # чтобы не оставлять устаревшее распределение.
                    allocation_cell.value = ""
                    allocation_cell.alignment = alignment

                if score_column is not None:
                    score_cell = sheet.cell(row=row_index, column=score_column)
                    score_cell.value = round(result.score * 100) if result.score else ""
                    score_cell.alignment = alignment

                # Единственный случай записи в колонку требуемого срока:
                # в заказе она была пуста, и новый этап сам подобрал срок
                # (см. докстринг модуля и MatchResult.expiry_auto_resolved).
                # Если срок уже был в заказе, expiry_auto_resolved не
                # выставляется — колонка остаётся нетронутой. В отличие от
                # E/F (текстовые колонки, создаваемые этим сервисом), сюда
                # пишется настоящая дата, а не отформатированная строка: это
                # существующая колонка исходного заказа, и для остальных
                # строк в ней уже лежат обычные даты Excel — значение должно
                # остаться сортируемой/фильтруемой датой, а не текстом.
                if (
                    result.expiry_auto_resolved
                    and requested_expiry_column is not None
                    and result.row.requested_expiry is not None
                ):
                    requested_expiry_cell = sheet.cell(
                        row=row_index, column=requested_expiry_column
                    )
                    requested_expiry_cell.value = result.row.requested_expiry
                    requested_expiry_cell.number_format = "DD.MM.YYYY"
                    requested_expiry_cell.alignment = alignment

                # Товар вне базы сроков годности либо в базе есть, но ни для
                # одной его партии не подтверждён сертификат — в обоих
                # случаях подбор сертификата для строки вообще не выполнялся
                # (см. ExpiryResolutionService), поэтому строка выделяется
                # безусловно, независимо от highlight_rows: это не
                # декоративная подсветка статуса, а сигнал «сюда программа
                # даже не заглядывала».
                if result.expiry_not_in_database or result.expiry_no_certificate_available:
                    self._highlight_row(sheet, row_index, expiry_missing_fill, document)
                    self._strike_row(sheet, row_index, Font, document)
                elif self._settings.highlight_rows:
                    fill = fills.get(_status_key(result.status))
                    if fill is not None:
                        self._highlight_row(sheet, row_index, fill, document)

                written += 1

            self._style_header(
                sheet,
                document.header_row,
                (certificate_column, expiry_column, allocation_column),
                Font,
            )
            self._autosize(sheet, (certificate_column, expiry_column, allocation_column))

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

    def _strike_row(
        self, sheet: Any, row_index: int, font_class: Any, document: OrderDocument
    ) -> None:
        """Зачёркивает текст всей строки (товар отсутствует в базе сроков годности)."""
        last_column = max(sheet.max_column, len(document.headers))
        for column in range(1, last_column + 1):
            sheet.cell(row=row_index, column=column).font = font_class(strike=True)

    def _style_header(
        self, sheet: Any, header_row: int, columns: tuple[int, ...], font_class: Any
    ) -> None:
        """Выделяет заголовки добавленных колонок."""
        if header_row <= 0:
            return
        for column in columns:
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


def _format_quantity(value: float) -> str:
    """Форматирует количество для колонки распределения без лишних нулей после запятой."""
    return f"{value:g}"
