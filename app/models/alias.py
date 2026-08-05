"""Модель псевдонима — механизм самообучения приложения."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final

from app.core.text import normalize, token_key
from app.core.units import Volume

#: Сколько раз псевдоним, созданный не пользователем, должен быть применён,
#: прежде чем его уровень доверия поднимется с 80 % до 95 % («подтверждено
#: несколько раз»). Само число попаданий уже хранится в ``hit_count`` —
#: отдельного счётчика подтверждений не требуется.
CONFIRM_HIT_THRESHOLD: Final[int] = 3

#: Уровни доверия (в процентах) для трёх источников псевдонима.
CONFIDENCE_MANUAL: Final[float] = 100.0
CONFIDENCE_CONFIRMED: Final[float] = 95.0
CONFIDENCE_AI: Final[float] = 80.0

#: SQL-выражение, вычисляющее тот же уровень доверия на стороне базы —
#: используется для сортировки «сначала записи с максимальным доверием»
#: без выгрузки всей таблицы в Python.
CONFIDENCE_SQL: Final[str] = (
    "(CASE WHEN is_manual = 1 THEN 100.0 "
    f"WHEN hit_count >= {CONFIRM_HIT_THRESHOLD} THEN 95.0 ELSE 80.0 END)"
)


@dataclass(slots=True)
class Alias:
    """Запомненное соответствие «наименование из заказа → товар».

    Псевдоним создаётся, когда пользователь вручную выбирает сертификат в окне
    неоднозначности, исправляет автоматический подбор или добавляет запись
    напрямую в словаре соответствий. При следующей обработке заказа этап
    псевдонимов срабатывает раньше нечёткого и семантического поиска и
    является абсолютным источником истины: наименование и объём из записи
    ищутся в базе сертификатов строгим равенством, без права на откат к
    нечёткому/семантическому подбору.

    Запись не привязана к конкретной строке базы сертификатов (нет
    ``certificate_id``): при каждом подборе она заново разрешается в текущие
    строки базы по паре «нормализованное наименование + объём», поэтому
    связь никогда не устаревает после переимпорта Excel.

    Attributes:
        id: Первичный ключ (``None`` до сохранения).
        source_text: Наименование, как его написал пользователь/заказ.
        normalized_source: Каноническая форма исходного наименования — ключ поиска.
        token_source: Токен-ключ, инвариантный к порядку слов.
        target_name: Русское наименование товара (как в базе сертификатов).
        brand: Бренд товара (произвольная заметка пользователя).
        volume_ml: Объём товара в базовых единицах (обычно мл).
        weight: Приоритет псевдонима при конфликте (больше — важнее).
        hit_count: Сколько раз псевдоним применялся при подборе.
        is_manual: Создан пользователем (``True``) или автоматически.
        created_at: Момент создания.
        updated_at: Момент последнего редактирования.
        last_used_at: Момент последнего применения при подборе сертификата.
        created_by: Имя пользователя ОС, создавшего запись (если известно).
        note: Произвольный комментарий.
    """

    source_text: str
    id: int | None = None
    normalized_source: str = ""
    token_source: str = ""
    target_name: str = ""
    brand: str = ""
    volume_ml: float | None = None
    weight: float = 1.0
    hit_count: int = 0
    is_manual: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    last_used_at: datetime | None = None
    created_by: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        """Вычисляет ключи поиска по исходному тексту."""
        if not self.normalized_source:
            self.normalized_source = normalize(self.source_text)
        if not self.token_source:
            self.token_source = token_key(self.source_text)

    @property
    def is_valid(self) -> bool:
        """Признак пригодности псевдонима к сохранению."""
        return bool(self.normalized_source) and bool(self.target_name.strip())

    @property
    def normalized_target(self) -> str:
        """Нормализованное русское наименование — ключ строгого поиска в базе."""
        return normalize(self.target_name)

    @property
    def confidence(self) -> float:
        """Уровень доверия к псевдониму в процентах ``[80, 95, 100]``.

        Правило: запись, созданная пользователем напрямую (в диалоге
        добавления или в окне неоднозначного выбора), заслуживает полного
        доверия. Запись, появившаяся не от прямого решения пользователя,
        начинает с 80 % и поднимается до 95 %, когда применяется достаточно
        часто, чтобы считаться подтверждённой.
        """
        if self.is_manual:
            return CONFIDENCE_MANUAL
        if self.hit_count >= CONFIRM_HIT_THRESHOLD:
            return CONFIDENCE_CONFIRMED
        return CONFIDENCE_AI

    @property
    def source_label(self) -> str:
        """Человекочитаемое описание происхождения записи."""
        if self.is_manual:
            return "Пользователь"
        if self.hit_count >= CONFIRM_HIT_THRESHOLD:
            return "ИИ (подтверждено)"
        return "ИИ"

    @property
    def volume(self) -> Volume | None:
        """Объём, зафиксированный в словаре, в виде доменного объекта.

        Returns:
            :class:`~app.core.units.Volume` либо ``None``, если объём не указан.
        """
        if self.volume_ml is None:
            return None
        return Volume(
            value=self.volume_ml,
            unit="ml",
            base_value=self.volume_ml,
            base_unit="ml",
            dimension="volume",
        )

    @property
    def volume_label(self) -> str:
        """Отформатированный объём для отображения в таблице."""
        if self.volume_ml is None:
            return ""
        return f"{self.volume_ml:g} мл"

    def describe(self) -> str:
        """Возвращает представление вида ``источник = цель`` для интерфейса."""
        return f"{self.source_text} = {self.target_name}"

    def to_row(self) -> dict[str, Any]:
        """Преобразует псевдоним в словарь для SQLite."""
        return {
            "id": self.id,
            "source_text": self.source_text,
            "normalized_source": self.normalized_source,
            "token_source": self.token_source,
            "target_name": self.target_name,
            "brand": self.brand,
            "volume_ml": self.volume_ml,
            "weight": self.weight,
            "hit_count": self.hit_count,
            "is_manual": int(self.is_manual),
            "created_at": self.created_at.isoformat(timespec="seconds"),
            "updated_at": self.updated_at.isoformat(timespec="seconds"),
            "last_used_at": (
                self.last_used_at.isoformat(timespec="seconds") if self.last_used_at else None
            ),
            "created_by": self.created_by,
            "note": self.note,
        }

    @classmethod
    def from_row(cls, row: Any) -> Alias:
        """Восстанавливает псевдоним из строки SQLite.

        Args:
            row: :class:`sqlite3.Row` или совместимое отображение.

        Returns:
            Экземпляр :class:`Alias`.
        """
        data = dict(row)
        return cls(
            id=data.get("id"),
            source_text=data.get("source_text") or "",
            normalized_source=data.get("normalized_source") or "",
            token_source=data.get("token_source") or "",
            target_name=data.get("target_name") or "",
            brand=data.get("brand") or "",
            volume_ml=data.get("volume_ml"),
            weight=float(data.get("weight") or 1.0),
            hit_count=int(data.get("hit_count") or 0),
            is_manual=bool(data.get("is_manual", 1)),
            created_at=_parse(data.get("created_at")),
            updated_at=_parse(data.get("updated_at")),
            last_used_at=_parse_optional(data.get("last_used_at")),
            created_by=data.get("created_by") or "",
            note=data.get("note") or "",
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


def _parse_optional(value: Any) -> datetime | None:
    """Разбирает необязательную отметку времени, допуская отсутствие значения."""
    if value is None or value == "":
        return None
    return _parse(value)
