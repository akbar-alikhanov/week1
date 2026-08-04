"""Модель записи журнала изменений словаря соответствий."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class AliasAuditAction(StrEnum):
    """Тип действия, зафиксированного в журнале изменений."""

    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    RESTORED = "restored"

    @property
    def label(self) -> str:
        """Человекочитаемое название действия."""
        return {
            AliasAuditAction.CREATED: "Добавлено",
            AliasAuditAction.UPDATED: "Изменено",
            AliasAuditAction.DELETED: "Удалено",
            AliasAuditAction.RESTORED: "Восстановлено (отмена)",
        }[self]


@dataclass(slots=True)
class AliasAuditEntry:
    """Одна запись журнала изменений словаря соответствий.

    Каждое создание, изменение или удаление псевдонима фиксируется здесь со
    снимком состояния «до» и «после» — это одновременно и человекочитаемый
    журнал (раздел «Журнал изменений»), и основа для отмены последнего
    действия (:meth:`~app.services.alias_service.AliasService.undo_last`).

    Attributes:
        id: Первичный ключ (``None`` до сохранения).
        alias_id: Идентификатор псевдонима (сохраняется и после его удаления).
        action: Тип действия.
        source_text: Наименование из заказа на момент записи (для отображения,
            даже если сам псевдоним уже удалён).
        before: Снимок состояния до изменения (``None`` для создания).
        after: Снимок состояния после изменения (``None`` для удаления).
        actor: Имя пользователя ОС, выполнившего действие.
        at: Момент записи.
        undone: Признак того, что действие уже было отменено.
    """

    alias_id: int
    action: AliasAuditAction
    id: int | None = None
    source_text: str = ""
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    actor: str = ""
    at: datetime = field(default_factory=datetime.now)
    undone: bool = False

    def to_row(self) -> dict[str, Any]:
        """Преобразует запись в словарь для SQLite."""
        return {
            "id": self.id,
            "alias_id": self.alias_id,
            "action": self.action.value,
            "source_text": self.source_text,
            "before_json": json.dumps(self.before, ensure_ascii=False) if self.before else None,
            "after_json": json.dumps(self.after, ensure_ascii=False) if self.after else None,
            "actor": self.actor,
            "at": self.at.isoformat(timespec="seconds"),
            "undone": int(self.undone),
        }

    @classmethod
    def from_row(cls, row: Any) -> AliasAuditEntry:
        """Восстанавливает запись журнала из строки SQLite.

        Args:
            row: :class:`sqlite3.Row` или совместимое отображение.

        Returns:
            Экземпляр :class:`AliasAuditEntry`.
        """
        data = dict(row)
        before_raw = data.get("before_json")
        after_raw = data.get("after_json")
        at_raw = data.get("at")
        try:
            at = datetime.fromisoformat(at_raw) if at_raw else datetime.now()
        except ValueError:
            at = datetime.now()
        return cls(
            id=data.get("id"),
            alias_id=int(data.get("alias_id") or 0),
            action=AliasAuditAction(data.get("action") or AliasAuditAction.UPDATED.value),
            source_text=data.get("source_text") or "",
            before=json.loads(before_raw) if before_raw else None,
            after=json.loads(after_raw) if after_raw else None,
            actor=data.get("actor") or "",
            at=at,
            undone=bool(data.get("undone", 0)),
        )
