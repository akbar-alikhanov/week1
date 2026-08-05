"""Доменная модель товарной позиции из Excel-базы сертификатов."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.core.dates import format_date, parse_date
from app.core.text import alpha_signature, normalize, transliterate
from app.core.units import Volume, extract_primary_volume


@dataclass(slots=True)
class CertificateProduct:
    """Товарная позиция Excel-базы сертификатов.

    Единственный источник данных о сертификатах — таблица, которую ведёт
    пользователь: порядковый номер, наименование, срок годности, номер
    сертификата. Эта модель — построчное отражение той таблицы, а SQLite —
    лишь быстрый индекс над ней (см. :class:`CertificateImportService`).
    Сам PDF-файл сертификата в базе не хранится: он находится по номеру в
    имени файла только в момент копирования результата
    (:class:`~app.services.certificate_copy_service.CertificateCopyService`).

    ``normalized_name`` хранится в базе (участвует в строгом SQL-поиске по
    словарю псевдонимов), а ``translit_name``/``name_signature`` — нет: они
    нужны только нечёткому поиску, который сравнивает объекты в памяти, и
    вычисляются заново при каждой загрузке строки — так же дёшево, как и
    хранение, но без лишней колонки.

    Attributes:
        product_name: Наименование товара, как в Excel-базе.
        certificate_number: Номер сертификата (используется для поиска
            PDF-файла по имени и для колонки заказа).
        id: Первичный ключ в SQLite (``None`` до сохранения).
        normalized_name: Каноническое наименование для сравнения.
        translit_name: Латинизированное наименование (для нечёткого поиска).
        name_signature: Наименование без чисел и единиц измерения.
        volume_ml: Объём/фасовка товара в базовых единицах (обычно мл).
        expiry_date: Срок годности.
        source_row: Порядковый номер строки в исходном Excel-файле.
    """

    product_name: str
    certificate_number: str = ""
    id: int | None = None
    normalized_name: str = ""
    translit_name: str = ""
    name_signature: str = ""
    volume_ml: float | None = None
    expiry_date: date | None = None
    source_row: int = 0

    def __post_init__(self) -> None:
        """Достраивает производные поля, если они не заданы явно."""
        if not self.normalized_name:
            self.normalized_name = normalize(self.product_name)
        if not self.translit_name:
            self.translit_name = transliterate(self.product_name)
        if not self.name_signature:
            self.name_signature = alpha_signature(self.product_name)
        if self.volume_ml is None:
            extracted = extract_primary_volume(self.product_name)
            if extracted is not None:
                self.volume_ml = extracted.base_value

    # ------------------------------------------------------------- свойства
    @property
    def volume(self) -> Volume | None:
        """Объём товара в виде доменного объекта (единица определяется по тексту).

        Вычисляется заново из ``product_name`` при каждом обращении — это не
        чтение файла, а разбор уже загруженной в память строки, поэтому
        требование «не анализировать PDF» здесь ни при чём. Так сохраняется
        точная размерность (мл/г/шт) для сравнения объёмов в резервном
        (нечётком/семантическом) подборе, при этом в базе остаётся только
        одно числовое поле ``volume_ml``, как и задано схемой.

        Returns:
            :class:`~app.core.units.Volume` либо ``None``, если объём не
            определяется по тексту наименования.
        """
        return extract_primary_volume(self.product_name)

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
        """Номер сертификата для показа пользователю."""
        return self.certificate_number or "—"

    def summary(self) -> str:
        """Возвращает однострочное описание позиции для интерфейса."""
        parts = [self.product_name]
        if self.expiry_date:
            parts.append(f"до {format_date(self.expiry_date)}")
        if self.certificate_number:
            parts.append(f"№ {self.certificate_number}")
        return " · ".join(part for part in parts if part)

    # ----------------------------------------------------- (де)сериализация
    def to_row(self) -> dict[str, Any]:
        """Преобразует запись в словарь для вставки в SQLite.

        Returns:
            Словарь, ключи которого совпадают с колонками таблицы
            ``certificate_products``.
        """
        return {
            "id": self.id,
            "product_name": self.product_name,
            "normalized_name": self.normalized_name,
            "volume_ml": self.volume_ml,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "certificate_number": self.certificate_number,
            "source_row": self.source_row,
        }

    @classmethod
    def from_row(cls, row: Any) -> CertificateProduct:
        """Восстанавливает объект из строки SQLite.

        Args:
            row: :class:`sqlite3.Row` или совместимое отображение.

        Returns:
            Экземпляр :class:`CertificateProduct`.
        """
        data = dict(row)
        return cls(
            id=data.get("id"),
            product_name=data.get("product_name") or "",
            certificate_number=data.get("certificate_number") or "",
            normalized_name=data.get("normalized_name") or "",
            volume_ml=data.get("volume_ml"),
            expiry_date=parse_date(data.get("expiry_date")),
            source_row=int(data.get("source_row") or 0),
        )
