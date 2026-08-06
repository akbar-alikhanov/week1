"""Разбор системного наименования товара на составные части.

Системное наименование в заказе устроено по шаблону поставщика: «61004628 TP
Dr Rabbit Kids Bubblegum 50ml [48]» — числовой код товара, короткий код типа,
собственно название, объём и количество в коробке в квадратных скобках. Это
чисто отображаемый разбор для карточки словаря соответствий («не нужно вводить
эти данные вручную» — пользователь видит, что программа поняла его ввод
правильно); сам подбор сертификата по системному названию использует другой,
уже проверенный путь очистки (:func:`app.models.order.OrderRow.search_text`),
этот модуль его не заменяет и с ним не связан.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from app.core.text import collapse_whitespace
from app.core.units import Volume, extract_primary_volume

#: Числовой код товара в начале строки: «61004628 TP ...».
_RE_LEADING_CODE: Final[re.Pattern[str]] = re.compile(r"^\s*(\d{4,})\s+")

#: Короткий код типа сразу после кода товара: «TP Dr Rabbit ...». Отличается
#: от бренда/названия тем, что состоит только из заглавных латинских букв.
_RE_LEADING_TYPE: Final[re.Pattern[str]] = re.compile(r"^\s*([A-Z]{2,6})\s+")

#: Количество в коробке в конце строки: «...50ml [48]».
_RE_TRAILING_BRACKETS: Final[re.Pattern[str]] = re.compile(r"\s*\[([^\]]*)\]\s*$")

#: Первое целое число внутри отметки количества в коробке.
_RE_DIGITS: Final[re.Pattern[str]] = re.compile(r"\d+")

#: Объём внутри названия («50ml», «0.5 l») — вырезается из отображаемого
#: названия отдельно от :func:`extract_primary_volume`, которая работает с
#: нормализованной копией текста и не годится для правки строки на месте.
_RE_INLINE_VOLUME: Final[re.Pattern[str]] = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:ml|мл|l|л|kg|кг|mg|мг|mcg|мкг|g|г|pcs|шт|tab|таб|caps|капс)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ParsedProductName:
    """Разобранное системное наименование товара.

    Attributes:
        raw: Исходная строка без изменений.
        code: Числовой код товара (пусто, если не найден).
        product_type: Короткий код типа товара, например ``TP`` (пусто, если
            не найден).
        name: Название товара без кода, типа, объёма и количества в коробке.
        volume: Распознанный объём/фасовка (``None``, если не найден).
        box_quantity: Количество единиц в коробке (``None``, если не указано).
    """

    raw: str
    code: str = ""
    product_type: str = ""
    name: str = ""
    volume: Volume | None = None
    box_quantity: int | None = None


def parse_product_name(text: str) -> ParsedProductName:
    """Разбирает системное наименование на код, тип, название, объём и упаковку.

    Разбор лучший из возможных, а не строгий: если код или тип не
    распознаются (например, наименование введено в свободной форме), поле
    просто остаётся пустым — название при этом не портится.

    Args:
        text: Системное наименование, как его ввёл пользователь.

    Returns:
        Разобранные составные части.

    Examples:
        >>> parsed = parse_product_name("61004628 TP Dr Rabbit Kids Bubblegum 50ml [48]")
        >>> parsed.code, parsed.product_type, parsed.box_quantity
        ('61004628', 'TP', 48)
        >>> parsed.name
        'Dr Rabbit Kids Bubblegum'
    """
    working = text.strip()

    box_quantity: int | None = None
    brackets = _RE_TRAILING_BRACKETS.search(working)
    if brackets:
        digits = _RE_DIGITS.search(brackets.group(1))
        if digits:
            box_quantity = int(digits.group())
        working = working[: brackets.start()].rstrip()

    code = ""
    leading_code = _RE_LEADING_CODE.match(working)
    if leading_code:
        code = leading_code.group(1)
        working = working[leading_code.end() :]

    product_type = ""
    leading_type = _RE_LEADING_TYPE.match(working)
    if leading_type:
        product_type = leading_type.group(1)
        working = working[leading_type.end() :]

    volume = extract_primary_volume(working)
    name = collapse_whitespace(_RE_INLINE_VOLUME.sub(" ", working))

    return ParsedProductName(
        raw=text,
        code=code,
        product_type=product_type,
        name=name,
        volume=volume,
        box_quantity=box_quantity,
    )


__all__ = ["ParsedProductName", "parse_product_name"]
