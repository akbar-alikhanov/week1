"""Модель товара — накопительный справочник позиций из обработанных заказов."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.text import alpha_signature, normalize, transliterate


@dataclass(slots=True)
class Product:
    """Товарная позиция, встречавшаяся в заказах.

    Справочник товаров решает три задачи: подсказки в строке поиска,
    статистика «самые проблемные позиции» и ускорение подбора за счёт
    кэширования ранее принятого решения.

    Attributes:
        id: Первичный ключ.
        name: Наименование товара, как оно встречалось в заказе.
        normalized_name: Каноническое наименование.
        translit_name: Латинизированное наименование.
        name_signature: Наименование без чисел и единиц.
        brand: Бренд, если удалось определить.
        volume_value: Объём в базовых единицах.
        volume_unit: Базовая единица объёма.
        last_certificate_id: Сертификат, выбранный для товара в последний раз.
        seen_count: Сколько раз товар встречался в заказах.
        matched_count: Сколько раз для него был найден сертификат.
        first_seen_at: Первое появление.
        last_seen_at: Последнее появление.
    """

    name: str
    id: int | None = None
    normalized_name: str = ""
    translit_name: str = ""
    name_signature: str = ""
    brand: str = ""
    volume_value: float | None = None
    volume_unit: str = ""
    last_certificate_id: int | None = None
    seen_count: int = 1
    matched_count: int = 0
    first_seen_at: datetime = field(default_factory=datetime.now)
    last_seen_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        """Вычисляет производные поля наименования."""
        if not self.normalized_name:
            self.normalized_name = normalize(self.name)
        if not self.translit_name:
            self.translit_name = transliterate(self.name)
        if not self.name_signature:
            self.name_signature = alpha_signature(self.name)

    @property
    def match_rate(self) -> float:
        """Доля успешных подборов для товара в диапазоне ``[0..1]``."""
        if self.seen_count <= 0:
            return 0.0
        return min(1.0, self.matched_count / self.seen_count)

    def to_row(self) -> dict[str, Any]:
        """Преобразует товар в словарь для SQLite."""
        return {
            "id": self.id,
            "name": self.name,
            "normalized_name": self.normalized_name,
            "translit_name": self.translit_name,
            "name_signature": self.name_signature,
            "brand": self.brand,
            "volume_value": self.volume_value,
            "volume_unit": self.volume_unit,
            "last_certificate_id": self.last_certificate_id,
            "seen_count": self.seen_count,
            "matched_count": self.matched_count,
            "first_seen_at": self.first_seen_at.isoformat(timespec="seconds"),
            "last_seen_at": self.last_seen_at.isoformat(timespec="seconds"),
        }

    @classmethod
    def from_row(cls, row: Any) -> Product:
        """Восстанавливает товар из строки SQLite.

        Args:
            row: :class:`sqlite3.Row` или совместимое отображение.

        Returns:
            Экземпляр :class:`Product`.
        """
        data = dict(row)
        return cls(
            id=data.get("id"),
            name=data.get("name") or "",
            normalized_name=data.get("normalized_name") or "",
            translit_name=data.get("translit_name") or "",
            name_signature=data.get("name_signature") or "",
            brand=data.get("brand") or "",
            volume_value=data.get("volume_value"),
            volume_unit=data.get("volume_unit") or "",
            last_certificate_id=data.get("last_certificate_id"),
            seen_count=int(data.get("seen_count") or 0),
            matched_count=int(data.get("matched_count") or 0),
            first_seen_at=_parse(data.get("first_seen_at")),
            last_seen_at=_parse(data.get("last_seen_at")),
        )


def _parse(value: Any) -> datetime:
    """Разбирает отметку времени, подставляя текущий момент при ошибке."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return datetime.now()
    return datetime.now()
