"""Чтение PDF-сертификатов и построение доменных объектов.

Используется PyMuPDF (fitz) — самая быстрая из доступных библиотек: разбор
типового двухстраничного сертификата занимает единицы миллисекунд, а C-ядро
освобождает GIL, что позволяет эффективно распараллеливать индексацию.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.constants import PDF_MAX_PAGES_TO_PARSE, RAW_TEXT_EXCERPT_LIMIT
from app.core.exceptions import PdfParsingError
from app.core.units import extract_primary_volume
from app.models.certificate import Certificate
from app.parsers.field_extractors import ExtractedFields, extract_all

_LOGGER = logging.getLogger(__name__)

#: Размер блока при вычислении хэша файла.
_HASH_CHUNK_SIZE = 1 << 20  # 1 МБ


@dataclass(frozen=True, slots=True)
class PdfDocumentInfo:
    """Технические сведения о PDF-файле.

    Attributes:
        text: Извлечённый текст.
        page_count: Количество страниц.
        file_size: Размер файла в байтах.
        file_mtime: Время последнего изменения.
        file_hash: SHA-256 содержимого.
        has_text_layer: Признак наличия текстового слоя.
    """

    text: str
    page_count: int
    file_size: int
    file_mtime: float
    file_hash: str
    has_text_layer: bool


def compute_file_hash(path: Path) -> str:
    """Вычисляет SHA-256 содержимого файла.

    Хэш — надёжный критерий «файл изменился»: время модификации меняется при
    копировании папки, а содержимое остаётся прежним, и переиндексация
    десятков тысяч неизменных файлов была бы напрасной.

    Args:
        path: Путь к файлу.

    Returns:
        Хэш в шестнадцатеричном виде.

    Raises:
        PdfParsingError: Если файл недоступен для чтения.
    """
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(_HASH_CHUNK_SIZE):
                digest.update(chunk)
    except OSError as error:
        raise PdfParsingError(
            f"Не удалось прочитать файл {path.name}", path=path, details=str(error)
        ) from error
    return digest.hexdigest()


class PdfParser:
    """Извлекает текст и поля сертификата из PDF-файла.

    Класс не обращается к базе данных и не знает о настройках приложения —
    это чистый преобразователь «файл → доменный объект», что делает его
    тривиально тестируемым.
    """

    def __init__(self, *, max_pages: int = PDF_MAX_PAGES_TO_PARSE) -> None:
        """Создаёт парсер.

        Args:
            max_pages: Максимум страниц, читаемых из одного документа.
                Сертификаты редко длиннее двух страниц, а ограничение
                защищает от аномально больших файлов.
        """
        self._max_pages = max(1, max_pages)

    # ------------------------------------------------------------ извлечение
    def read_document(self, path: Path, *, compute_hash: bool = True) -> PdfDocumentInfo:
        """Читает PDF и возвращает его текст и технические характеристики.

        Args:
            path: Путь к PDF-файлу.
            compute_hash: Вычислять ли хэш содержимого.

        Returns:
            Сведения о документе.

        Raises:
            PdfParsingError: Если файл повреждён, зашифрован или недоступен.
        """
        try:
            import fitz  # PyMuPDF
        except ImportError as error:  # pragma: no cover — зависимость обязательна
            raise PdfParsingError(
                "Библиотека PyMuPDF недоступна", path=path, details=str(error)
            ) from error

        try:
            stat = path.stat()
        except OSError as error:
            raise PdfParsingError(
                f"Файл недоступен: {path.name}", path=path, details=str(error)
            ) from error

        text_parts: list[str] = []
        page_count = 0
        try:
            with fitz.open(path) as document:
                if document.is_encrypted and not document.authenticate(""):
                    raise PdfParsingError(f"PDF защищён паролем: {path.name}", path=path)
                page_count = document.page_count
                for index in range(min(page_count, self._max_pages)):
                    page = document.load_page(index)
                    text_parts.append(page.get_text("text"))
        except PdfParsingError:
            raise
        except Exception as error:
            raise PdfParsingError(
                f"Не удалось прочитать PDF: {path.name}", path=path, details=str(error)
            ) from error

        text = "\n".join(text_parts)
        return PdfDocumentInfo(
            text=text,
            page_count=page_count,
            file_size=stat.st_size,
            file_mtime=stat.st_mtime,
            file_hash=compute_file_hash(path) if compute_hash else "",
            has_text_layer=len(text.strip()) >= 40,
        )

    def extract_fields(self, path: Path, text: str) -> ExtractedFields:
        """Извлекает поля сертификата из текста.

        Args:
            path: Путь к файлу (используется как источник запасного номера).
            text: Текст документа.

        Returns:
            Извлечённые поля.
        """
        return extract_all(text, filename=path.name)

    def parse(self, path: Path) -> Certificate:
        """Полностью разбирает PDF-файл в объект сертификата.

        Args:
            path: Путь к PDF-файлу.

        Returns:
            Готовый к сохранению :class:`Certificate`.

        Raises:
            PdfParsingError: Если файл не удалось прочитать.
        """
        info = self.read_document(path)
        fields = self.extract_fields(path, info.text)

        volume = extract_primary_volume(fields.product_name)
        if volume is None:
            # Объём может быть указан отдельной строкой в теле документа.
            volume = extract_primary_volume(info.text[:1200])

        now = datetime.now()
        certificate = Certificate(
            product_name=fields.product_name or path.stem,
            pdf_path=str(path),
            pdf_name=path.name,
            brand=fields.brand,
            manufacturer=fields.manufacturer,
            applicant=fields.applicant,
            country=fields.country,
            certificate_number=fields.certificate_number,
            certificate_date=fields.certificate_date,
            valid_from=fields.valid_from,
            expiry_date=fields.expiry_date,
            issued_by=fields.issued_by,
            volume_value=volume.base_value if volume else None,
            volume_unit=volume.base_unit if volume else "",
            volume_raw=volume.raw if volume else "",
            pack_count=volume.pack_count if volume else 1,
            page_count=info.page_count,
            file_hash=info.file_hash,
            file_size=info.file_size,
            file_mtime=info.file_mtime,
            indexed_at=now,
            updated_at=now,
            raw_text=info.text[:RAW_TEXT_EXCERPT_LIMIT],
            extraction_confidence=fields.confidence,
            is_active=True,
        )

        if fields.warnings:
            _LOGGER.debug("%s: %s", path.name, "; ".join(fields.warnings))
        return certificate

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

    def describe(self, path: Path) -> dict[str, Any]:
        """Возвращает сводку о документе для панели свойств.

        Args:
            path: Путь к PDF-файлу.

        Returns:
            Словарь «характеристика → значение».
        """
        info = self.read_document(path, compute_hash=False)
        return {
            "Файл": path.name,
            "Страниц": info.page_count,
            "Размер": f"{info.file_size / 1024:.1f} КБ",
            "Изменён": datetime.fromtimestamp(info.file_mtime).strftime("%d.%m.%Y %H:%M"),
            "Текстовый слой": "есть" if info.has_text_layer else "отсутствует (скан)",
        }
