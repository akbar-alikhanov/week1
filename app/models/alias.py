"""Модель псевдонима — механизм самообучения приложения."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.text import normalize, token_key


@dataclass(slots=True)
class Alias:
    """Запомненное соответствие «наименование из заказа → сертификат».

    Псевдоним создаётся, когда пользователь вручную выбирает сертификат в окне
    неоднозначности или исправляет автоматический подбор. При следующей
    обработке заказа этап псевдонимов срабатывает раньше нечёткого и
    семантического поиска, что даёт мгновенный и стопроцентно предсказуемый
    результат.

    Attributes:
        id: Первичный ключ (``None`` до сохранения).
        source_text: Наименование, как его написал пользователь/заказ.
        normalized_source: Каноническая форма исходного наименования — ключ поиска.
        token_source: Токен-ключ, инвариантный к порядку слов.
        certificate_id: Идентификатор сертификата-цели.
        target_name: Наименование товара в сертификате (для отображения).
        target_pdf_name: Имя PDF-файла (сохраняется, чтобы связь пережила
            переиндексацию с изменением идентификаторов).
        weight: Приоритет псевдонима при конфликте (больше — важнее).
        hit_count: Сколько раз псевдоним применялся.
        is_manual: Создан пользователем (``True``) или автоматически.
        created_at: Момент создания.
        updated_at: Момент последнего применения/изменения.
        note: Произвольный комментарий.
    """

    source_text: str
    certificate_id: int | None = None
    id: int | None = None
    normalized_source: str = ""
    token_source: str = ""
    target_name: str = ""
    target_pdf_name: str = ""
    weight: float = 1.0
    hit_count: int = 0
    is_manual: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
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
        return bool(self.normalized_source) and self.certificate_id is not None

    def describe(self) -> str:
        """Возвращает представление вида ``источник = цель`` для интерфейса."""
        return f"{self.source_text} = {self.target_name or self.target_pdf_name}"

    def to_row(self) -> dict[str, Any]:
        """Преобразует псевдоним в словарь для SQLite."""
        return {
            "id": self.id,
            "source_text": self.source_text,
            "normalized_source": self.normalized_source,
            "token_source": self.token_source,
            "certificate_id": self.certificate_id,
            "target_name": self.target_name,
            "target_pdf_name": self.target_pdf_name,
            "weight": self.weight,
            "hit_count": self.hit_count,
            "is_manual": int(self.is_manual),
            "created_at": self.created_at.isoformat(timespec="seconds"),
            "updated_at": self.updated_at.isoformat(timespec="seconds"),
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
            certificate_id=data.get("certificate_id"),
            target_name=data.get("target_name") or "",
            target_pdf_name=data.get("target_pdf_name") or "",
            weight=float(data.get("weight") or 1.0),
            hit_count=int(data.get("hit_count") or 0),
            is_manual=bool(data.get("is_manual", 1)),
            created_at=_parse(data.get("created_at")),
            updated_at=_parse(data.get("updated_at")),
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
