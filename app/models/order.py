"""Модели файла заказа и его строк."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Final

from app.core.text import alpha_signature, collapse_whitespace, normalize, token_key, transliterate
from app.core.units import Volume, extract_primary_volume

#: Код товара в начале системного наименования: «61004628 TP Dr Rabbit...».
#: Сертификаты такого кода не содержат, поэтому для подбора он лишний шум.
_RE_LEADING_CODE: Final[re.Pattern[str]] = re.compile(r"^\s*\d{4,}\s+")

#: Количество в коробке в конце наименования: «...50ml [48]». Как и код
#: товара, в тексте сертификата этой отметки нет.
_RE_TRAILING_BRACKETS: Final[re.Pattern[str]] = re.compile(r"(?:\s*\[[^\]]*\]\s*)+$")


def _clean_search_name(product_name: str) -> str:
    """Убирает код товара и отметку «[кол-во в коробке]» для подбора.

    Системное наименование в заказе оформлено как «61004628 TP Dr Rabbit
    Kids Bubblegum 50ml [48]»: числовой код товара спереди и количество в
    коробке в квадратных скобках в конце — ни того, ни другого нет в тексте
    сертификата, и код вдобавок мог бы перевесить совпадение по смыслу при
    нечётком и семантическом сравнении. ``product_name`` при этом не
    меняется — он остаётся как в исходном файле для отчёта.

    Args:
        product_name: Наименование товара как в файле заказа.

    Returns:
        Наименование без кода товара и отметки количества в коробке.
    """
    text = _RE_LEADING_CODE.sub("", product_name)
    text = _RE_TRAILING_BRACKETS.sub("", text)
    return collapse_whitespace(text)


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

        Наименование сперва очищается от кода товара и отметки количества в
        коробке (см. :func:`_clean_search_name`). Если объём вынесен в
        отдельную колонку заказа, он приклеивается к очищенному наименованию
        — иначе алгоритм не сможет отличить 100 мл от 150 мл.
        """
        core = _clean_search_name(self.product_name)
        if self.declared_volume and self.declared_volume.lower() not in core.lower():
            return f"{core} {self.declared_volume}".strip()
        return core

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
