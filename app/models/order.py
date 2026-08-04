"""Модели файла заказа и его строк."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from app.core.text import alpha_signature, normalize, token_key, transliterate
from app.core.units import Volume, extract_primary_volume


@dataclass(slots=True)
class OrderRow:
    """Одна товарная позиция заказа.

    Attributes:
        row_number: Номер строки в исходном листе Excel (1-based).
        product_name: Наименование товара из заказа.
        normalized_name: Каноническое наименование.
        translit_name: Латинизированное наименование.
        name_signature: Наименование без чисел и единиц.
        token_signature: Токены, инвариантные к порядку слов.
        quantity: Заказанное количество.
        requested_expiry: Требуемый срок годности (если указан в заказе).
        declared_volume: Объём, указанный в отдельной колонке заказа.
        brand: Бренд, указанный в отдельной колонке.
        extra: Прочие значения строки (код товара, цена и т. п.).
    """

    row_number: int
    product_name: str
    normalized_name: str = ""
    translit_name: str = ""
    name_signature: str = ""
    token_signature: str = ""
    quantity: float | None = None
    requested_expiry: date | None = None
    declared_volume: str = ""
    brand: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Достраивает производные поля наименования."""
        source = self.search_text
        if not self.normalized_name:
            self.normalized_name = normalize(source)
        if not self.translit_name:
            self.translit_name = transliterate(source)
        if not self.name_signature:
            self.name_signature = alpha_signature(source)
        if not self.token_signature:
            self.token_signature = token_key(source)

    @property
    def search_text(self) -> str:
        """Текст, используемый для подбора.

        Если объём вынесен в отдельную колонку заказа, он приклеивается к
        наименованию — иначе алгоритм не сможет отличить 100 мл от 150 мл.
        """
        if self.declared_volume and self.declared_volume.lower() not in self.product_name.lower():
            return f"{self.product_name} {self.declared_volume}".strip()
        return self.product_name

    @property
    def volume(self) -> Volume | None:
        """Объём позиции, извлечённый из наименования или отдельной колонки."""
        return extract_primary_volume(self.search_text)

    @property
    def is_empty(self) -> bool:
        """Признак пустой (технической) строки заказа."""
        return not self.product_name.strip()


@dataclass(slots=True)
class OrderDocument:
    """Разобранный файл заказа.

    Attributes:
        path: Путь к исходному файлу.
        sheet_name: Имя обработанного листа.
        header_row: Номер строки заголовка (1-based).
        rows: Товарные позиции.
        column_map: Соответствие «роль → индекс колонки» (0-based).
        headers: Заголовки колонок в исходном порядке.
        total_sheet_rows: Всего строк на листе.
    """

    path: Path
    sheet_name: str
    header_row: int
    rows: list[OrderRow] = field(default_factory=list)
    column_map: dict[str, int] = field(default_factory=dict)
    headers: list[str] = field(default_factory=list)
    total_sheet_rows: int = 0

    @property
    def name(self) -> str:
        """Имя файла заказа."""
        return self.path.name

    @property
    def row_count(self) -> int:
        """Количество товарных позиций."""
        return len(self.rows)

    def __len__(self) -> int:
        """Количество товарных позиций."""
        return len(self.rows)
