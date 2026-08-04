"""Доменная модель сертификата соответствия."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.core.dates import format_date, parse_date
from app.core.text import alpha_signature, normalize, token_key, transliterate
from app.core.units import Volume


@dataclass(slots=True)
class Certificate:
    """Сертификат соответствия, извлечённый из PDF-файла.

    Экземпляр создаётся парсером PDF, сохраняется в SQLite и далее живёт как
    неизменяемая (по соглашению) запись справочника. Все производные поля
    (``normalized_name``, ``translit_name``, ``name_signature``) вычисляются
    один раз при индексации, поэтому подбор не тратит время на нормализацию.

    Attributes:
        id: Первичный ключ в базе (``None`` до сохранения).
        product_name: Наименование товара, как в сертификате.
        normalized_name: Каноническое наименование для сравнения.
        translit_name: Латинизированное наименование для кросс-скриптового поиска.
        name_signature: Наименование без чисел и единиц измерения.
        token_signature: Токены наименования, инвариантные к порядку слов.
        brand: Торговая марка/бренд.
        manufacturer: Изготовитель.
        applicant: Заявитель (обычно импортёр).
        country: Страна происхождения.
        certificate_number: Номер сертификата.
        certificate_date: Дата выдачи.
        valid_from: Начало срока действия.
        expiry_date: Окончание срока действия/срок годности.
        issued_by: Орган по сертификации.
        volume_value: Числовое значение объёма в базовых единицах.
        volume_unit: Базовая единица (``ml``, ``g``, ``pcs``).
        volume_raw: Исходный фрагмент текста с объёмом.
        pack_count: Количество единиц в упаковке.
        pdf_name: Имя PDF-файла.
        pdf_path: Полный путь к PDF-файлу.
        page_count: Количество страниц в PDF.
        file_hash: SHA-256 содержимого файла.
        file_size: Размер файла в байтах.
        file_mtime: Время последнего изменения файла (Unix time).
        indexed_at: Момент индексации.
        updated_at: Момент последнего обновления записи.
        raw_text: Фрагмент текста PDF (для полнотекстового поиска).
        extraction_confidence: Оценка полноты извлечения полей ``[0..1]``.
        is_active: Признак того, что файл существует и запись актуальна.
    """

    product_name: str
    pdf_path: str
    pdf_name: str = ""
    id: int | None = None
    normalized_name: str = ""
    translit_name: str = ""
    name_signature: str = ""
    token_signature: str = ""
    brand: str = ""
    manufacturer: str = ""
    applicant: str = ""
    country: str = ""
    certificate_number: str = ""
    certificate_date: date | None = None
    valid_from: date | None = None
    expiry_date: date | None = None
    issued_by: str = ""
    volume_value: float | None = None
    volume_unit: str = ""
    volume_raw: str = ""
    pack_count: int = 1
    page_count: int = 0
    file_hash: str = ""
    file_size: int = 0
    file_mtime: float = 0.0
    indexed_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    raw_text: str = ""
    extraction_confidence: float = 0.0
    is_active: bool = True

    def __post_init__(self) -> None:
        """Достраивает производные поля, если они не заданы явно."""
        if not self.pdf_name and self.pdf_path:
            self.pdf_name = Path(self.pdf_path).name
        if not self.normalized_name:
            self.normalized_name = normalize(self.product_name)
        if not self.translit_name:
            self.translit_name = transliterate(self.product_name)
        if not self.name_signature:
            self.name_signature = alpha_signature(self.product_name)
        if not self.token_signature:
            self.token_signature = token_key(self.product_name)

    # ------------------------------------------------------------- свойства
    @property
    def path(self) -> Path:
        """Путь к PDF-файлу в виде объекта :class:`pathlib.Path`."""
        return Path(self.pdf_path)

    @property
    def volume(self) -> Volume | None:
        """Объём товара в виде доменного объекта.

        Returns:
            :class:`~app.core.units.Volume` либо ``None``, если объём неизвестен.
        """
        if self.volume_value is None or not self.volume_unit:
            return None
        dimension = {"ml": "volume", "g": "mass", "pcs": "count"}.get(self.volume_unit, "volume")
        return Volume(
            value=self.volume_value,
            unit=self.volume_unit,
            base_value=self.volume_value,
            base_unit=self.volume_unit,
            dimension=dimension,
            pack_count=self.pack_count,
            raw=self.volume_raw,
        )

    @property
    def is_expired(self) -> bool:
        """Признак истёкшего срока действия на текущую дату."""
        return self.expiry_date is not None and self.expiry_date < date.today()

    @property
    def days_until_expiry(self) -> int | None:
        """Количество дней до окончания срока действия."""
        if self.expiry_date is None:
            return None
        return (self.expiry_date - date.today()).days

    @property
    def display_number(self) -> str:
        """Номер сертификата для показа пользователю.

        Если номер не удалось извлечь из текста, используется имя файла без
        расширения — на практике оно почти всегда и есть номер.
        """
        return self.certificate_number or Path(self.pdf_name).stem

    def summary(self) -> str:
        """Возвращает однострочное описание сертификата для интерфейса."""
        parts = [self.product_name]
        if self.volume_value:
            parts.append(str(self.volume))
        if self.expiry_date:
            parts.append(f"до {format_date(self.expiry_date)}")
        return " · ".join(part for part in parts if part)

    # ----------------------------------------------------- (де)сериализация
    def to_row(self) -> dict[str, Any]:
        """Преобразует запись в словарь для вставки в SQLite.

        Returns:
            Словарь, ключи которого совпадают с колонками таблицы
            ``certificates``.
        """
        return {
            "id": self.id,
            "product_name": self.product_name,
            "normalized_name": self.normalized_name,
            "translit_name": self.translit_name,
            "name_signature": self.name_signature,
            "token_signature": self.token_signature,
            "brand": self.brand,
            "manufacturer": self.manufacturer,
            "applicant": self.applicant,
            "country": self.country,
            "certificate_number": self.certificate_number,
            "certificate_date": (
                self.certificate_date.isoformat() if self.certificate_date else None
            ),
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "issued_by": self.issued_by,
            "volume_value": self.volume_value,
            "volume_unit": self.volume_unit,
            "volume_raw": self.volume_raw,
            "pack_count": self.pack_count,
            "pdf_name": self.pdf_name,
            "pdf_path": self.pdf_path,
            "page_count": self.page_count,
            "file_hash": self.file_hash,
            "file_size": self.file_size,
            "file_mtime": self.file_mtime,
            "indexed_at": self.indexed_at.isoformat(timespec="seconds"),
            "updated_at": self.updated_at.isoformat(timespec="seconds"),
            "raw_text": self.raw_text,
            "extraction_confidence": self.extraction_confidence,
            "is_active": int(self.is_active),
        }

    @classmethod
    def from_row(cls, row: Any) -> Certificate:
        """Восстанавливает объект из строки SQLite.

        Args:
            row: :class:`sqlite3.Row` или совместимое отображение.

        Returns:
            Экземпляр :class:`Certificate`.
        """
        data = dict(row)
        return cls(
            id=data.get("id"),
            product_name=data.get("product_name") or "",
            normalized_name=data.get("normalized_name") or "",
            translit_name=data.get("translit_name") or "",
            name_signature=data.get("name_signature") or "",
            token_signature=data.get("token_signature") or "",
            brand=data.get("brand") or "",
            manufacturer=data.get("manufacturer") or "",
            applicant=data.get("applicant") or "",
            country=data.get("country") or "",
            certificate_number=data.get("certificate_number") or "",
            certificate_date=parse_date(data.get("certificate_date")),
            valid_from=parse_date(data.get("valid_from")),
            expiry_date=parse_date(data.get("expiry_date")),
            issued_by=data.get("issued_by") or "",
            volume_value=data.get("volume_value"),
            volume_unit=data.get("volume_unit") or "",
            volume_raw=data.get("volume_raw") or "",
            pack_count=int(data.get("pack_count") or 1),
            pdf_name=data.get("pdf_name") or "",
            pdf_path=data.get("pdf_path") or "",
            page_count=int(data.get("page_count") or 0),
            file_hash=data.get("file_hash") or "",
            file_size=int(data.get("file_size") or 0),
            file_mtime=float(data.get("file_mtime") or 0.0),
            indexed_at=_parse_datetime(data.get("indexed_at")),
            updated_at=_parse_datetime(data.get("updated_at")),
            raw_text=data.get("raw_text") or "",
            extraction_confidence=float(data.get("extraction_confidence") or 0.0),
            is_active=bool(data.get("is_active", 1)),
        )


def _parse_datetime(value: Any) -> datetime:
    """Разбирает отметку времени из базы, возвращая текущий момент при сбое."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return datetime.now()
    return datetime.now()
