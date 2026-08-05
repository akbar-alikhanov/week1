"""Отрисовка страниц PDF-сертификатов для встроенного просмотрщика.

PDF больше не являются источником данных — данные о сертификатах берутся
только из Excel-базы (см. ``app.services.certificate_import_service``).
Единственная оставшаяся роль этого модуля — показать пользователю страницу
документа как изображение, чтобы он мог визуально сверить найденный
сертификат; текст PDF нигде не читается и не разбирается.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.exceptions import PdfParsingError

_LOGGER = logging.getLogger(__name__)


class PdfParser:
    """Отрисовывает страницы PDF-сертификата в растровое изображение.

    Использует PyMuPDF (fitz) — самая быстрая из доступных библиотек для
    рендеринга. Класс не обращается к базе данных и не знает о настройках
    приложения.
    """

    # -------------------------------------------------------------- рендеринг
    def render_page(
        self, path: Path, page_number: int = 0, *, zoom: float = 1.5
    ) -> tuple[bytes, int, int]:
        """Отрисовывает страницу PDF в растровое изображение.

        Используется встроенным просмотрщиком: показать документ прямо в
        приложении быстрее и безопаснее, чем запускать внешнюю программу.

        Args:
            path: Путь к PDF-файлу.
            page_number: Индекс страницы (с нуля).
            zoom: Коэффициент масштабирования (1.0 ≈ 72 dpi).

        Returns:
            Кортеж ``(данные PNG, ширина, высота)``.

        Raises:
            PdfParsingError: Если страницу не удалось отрисовать.
        """
        try:
            import fitz
        except ImportError as error:  # pragma: no cover
            raise PdfParsingError("Библиотека PyMuPDF недоступна", path=path) from error

        try:
            with fitz.open(path) as document:
                if document.page_count == 0:
                    raise PdfParsingError(f"Документ пуст: {path.name}", path=path)
                index = max(0, min(page_number, document.page_count - 1))
                page = document.load_page(index)
                matrix = fitz.Matrix(zoom, zoom)
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                return (pixmap.tobytes("png"), pixmap.width, pixmap.height)
        except PdfParsingError:
            raise
        except Exception as error:
            raise PdfParsingError(
                f"Не удалось отрисовать страницу {page_number + 1} файла {path.name}",
                path=path,
                details=str(error),
            ) from error

    def page_count(self, path: Path) -> int:
        """Возвращает количество страниц в документе.

        Args:
            path: Путь к PDF-файлу.

        Returns:
            Количество страниц; ``0`` при ошибке чтения.
        """
        try:
            import fitz

            with fitz.open(path) as document:
                return int(document.page_count)
        except Exception:
            return 0
