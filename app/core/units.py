"""Разбор и сравнение объёма/фасовки товара.

Объём — второй по важности признак после наименования (вес 30 % в общей
оценке). «Лечебные травы 100 мл» и «Лечебные травы 150 мл» — это разные товары
с разными сертификатами, поэтому ошибка в объёме недопустима.

Модуль умеет:

* извлекать объём из произвольного текста («0,5 л», «100мл», «2 х 50 мл»);
* приводить значения к базовым единицам (мл, г, шт);
* сравнивать два объёма с учётом допуска и размерности.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from app.core.text import normalize

# --------------------------------------------------------------------------- #
# Размерности
# --------------------------------------------------------------------------- #
DIMENSION_VOLUME: Final[str] = "volume"
DIMENSION_MASS: Final[str] = "mass"
DIMENSION_COUNT: Final[str] = "count"

#: Единица → (базовая единица, коэффициент, размерность).
_UNIT_DEFINITIONS: Final[dict[str, tuple[str, float, str]]] = {
    "ml": ("ml", 1.0, DIMENSION_VOLUME),
    "l": ("ml", 1000.0, DIMENSION_VOLUME),
    "mcg": ("g", 1e-6, DIMENSION_MASS),
    "mg": ("g", 0.001, DIMENSION_MASS),
    "g": ("g", 1.0, DIMENSION_MASS),
    "kg": ("g", 1000.0, DIMENSION_MASS),
    "pcs": ("pcs", 1.0, DIMENSION_COUNT),
    "tab": ("pcs", 1.0, DIMENSION_COUNT),
    "caps": ("pcs", 1.0, DIMENSION_COUNT),
    "amp": ("pcs", 1.0, DIMENSION_COUNT),
    "sachet": ("pcs", 1.0, DIMENSION_COUNT),
}

#: Человекочитаемые подписи базовых единиц.
UNIT_LABELS: Final[dict[str, str]] = {"ml": "мл", "g": "г", "pcs": "шт"}

_UNIT_PATTERN: Final[str] = "|".join(sorted(_UNIT_DEFINITIONS, key=len, reverse=True))

#: «2 x 100 ml», «2х100ml» — многоштучная фасовка.
_RE_PACK: Final[re.Pattern[str]] = re.compile(
    rf"(?P<count>\d{{1,3}})\s*[x*х]\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>{_UNIT_PATTERN})\b",
    re.IGNORECASE,
)

#: «100 ml», «0.5 l».
_RE_SIMPLE: Final[re.Pattern[str]] = re.compile(
    rf"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>{_UNIT_PATTERN})\b",
    re.IGNORECASE,
)

#: Значения объёма, встречающиеся в номерах/датах и почти наверняка ложные.
_MAX_PLAUSIBLE_BASE_VALUE: Final[float] = 500_000.0


@dataclass(frozen=True, slots=True)
class Volume:
    """Нормализованный объём/фасовка товара.

    Attributes:
        value: Числовое значение в исходных единицах.
        unit: Исходная единица в канонической записи (``ml``, ``mg``, ``tab``…).
        base_value: Значение, приведённое к базовой единице размерности.
        base_unit: Базовая единица (``ml``, ``g``, ``pcs``).
        dimension: Размерность (``volume``, ``mass``, ``count``).
        pack_count: Количество единиц в упаковке (для записей вида «2 x 100 мл»).
        raw: Фрагмент исходного текста, из которого извлечено значение.
    """

    value: float
    unit: str
    base_value: float
    base_unit: str
    dimension: str
    pack_count: int = 1
    raw: str = ""

    @property
    def total_base_value(self) -> float:
        """Суммарный объём упаковки в базовых единицах."""
        return self.base_value * self.pack_count

    def format(self) -> str:
        """Возвращает компактное представление для интерфейса.

        Значение приводится к базовой единице, чтобы «0,5 л» и «500 мл»
        выглядели одинаково и пользователь видел сопоставимые величины.

        Returns:
            Строка вида ``100 мл`` или ``2 x 100 мл``.
        """
        label = UNIT_LABELS.get(self.base_unit, self.base_unit)
        number = f"{self.base_value:g}"
        if self.pack_count > 1:
            return f"{self.pack_count} x {number} {label}"
        return f"{number} {label}"

    def __str__(self) -> str:
        """Возвращает компактное представление объёма."""
        return self.format()


def _build(value: float, unit: str, *, pack_count: int, raw: str) -> Volume | None:
    """Создаёт :class:`Volume`, отбрасывая заведомо ложные значения."""
    definition = _UNIT_DEFINITIONS.get(unit.lower())
    if definition is None or value <= 0:
        return None
    base_unit, factor, dimension = definition
    base_value = value * factor
    if base_value > _MAX_PLAUSIBLE_BASE_VALUE:
        return None
    return Volume(
        value=value,
        unit=unit.lower(),
        base_value=base_value,
        base_unit=base_unit,
        dimension=dimension,
        pack_count=pack_count,
        raw=raw.strip(),
    )


def extract_volumes(text: str | None) -> list[Volume]:
    """Извлекает все объёмы, встречающиеся в тексте.

    Args:
        text: Произвольный текст (наименование товара или фрагмент PDF).

    Returns:
        Список объёмов в порядке появления, без дубликатов.

    Examples:
        >>> [v.format() for v in extract_volumes("Сироп 2 х 100 мл")]
        ['2 x 100 мл']
        >>> [v.format() for v in extract_volumes("Настойка 0,5 л")]
        ['500 мл']
    """
    if not text:
        return []

    normalized = normalize(text)
    volumes: list[Volume] = []
    consumed_spans: list[tuple[int, int]] = []

    for match in _RE_PACK.finditer(normalized):
        volume = _build(
            float(match.group("value")),
            match.group("unit"),
            pack_count=int(match.group("count")),
            raw=match.group(0),
        )
        if volume is not None:
            volumes.append(volume)
            consumed_spans.append(match.span())

    for match in _RE_SIMPLE.finditer(normalized):
        if any(start <= match.start() < end for start, end in consumed_spans):
            continue
        volume = _build(
            float(match.group("value")), match.group("unit"), pack_count=1, raw=match.group(0)
        )
        if volume is not None:
            volumes.append(volume)

    unique: list[Volume] = []
    seen: set[tuple[float, str, int]] = set()
    for volume in volumes:
        key = (volume.base_value, volume.base_unit, volume.pack_count)
        if key not in seen:
            seen.add(key)
            unique.append(volume)
    return unique


def extract_primary_volume(text: str | None) -> Volume | None:
    """Возвращает наиболее вероятный «основной» объём товара.

    Приоритет отдаётся объёму жидкости/массы (мл, г) — именно он различает
    товарные позиции; количество таблеток обычно вторично.

    Args:
        text: Наименование товара или фрагмент текста сертификата.

    Returns:
        Объект :class:`Volume` либо ``None``, если объём не найден.
    """
    volumes = extract_volumes(text)
    if not volumes:
        return None
    for dimension in (DIMENSION_VOLUME, DIMENSION_MASS, DIMENSION_COUNT):
        for volume in volumes:
            if volume.dimension == dimension:
                return volume
    return volumes[0]


def volume_similarity(
    left: Volume | None,
    right: Volume | None,
    *,
    tolerance_ratio: float = 0.02,
    missing_score: float = 0.55,
) -> float:
    """Оценивает совпадение двух объёмов в диапазоне ``[0.0, 1.0]``.

    Правила:

    * оба значения отсутствуют или одно из них отсутствует → нейтральная оценка
      ``missing_score`` (нельзя ни поощрять, ни наказывать за отсутствие данных);
    * разные размерности (мл против шт) → ``0.0``;
    * расхождение в пределах ``tolerance_ratio`` → ``1.0``;
    * далее оценка линейно убывает и достигает нуля при трёхкратной разнице.

    Args:
        left: Объём из заказа.
        right: Объём из сертификата.
        tolerance_ratio: Относительный допуск, внутри которого объёмы считаются
            идентичными (округления в прайс-листах).
        missing_score: Оценка при отсутствии данных с одной из сторон.

    Returns:
        Оценка совпадения объёма.
    """
    if left is None or right is None:
        return missing_score
    if left.dimension != right.dimension:
        return 0.0

    left_value = left.total_base_value
    right_value = right.total_base_value
    if left_value <= 0 or right_value <= 0:
        return missing_score

    larger = max(left_value, right_value)
    smaller = min(left_value, right_value)
    relative_difference = (larger - smaller) / larger
    if relative_difference <= tolerance_ratio:
        return 1.0

    ratio = larger / smaller
    if ratio >= 3.0:
        return 0.0
    return max(0.0, 1.0 - (ratio - 1.0) / 2.0)


def format_optional(volume: Volume | None) -> str:
    """Форматирует объём для таблиц интерфейса.

    Args:
        volume: Объём либо ``None``.

    Returns:
        Строковое представление или ``"—"``.
    """
    return volume.format() if volume is not None else "—"
