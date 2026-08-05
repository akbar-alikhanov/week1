"""Репозиторий настроек, хранимых в базе данных.

JSON-файл настроек редактируется пользователем и переносится между машинами,
а таблица ``settings`` хранит служебное состояние приложения: время последней
индексации, версию модели, состояние окна. Разделение намеренное — служебное
состояние не должно попадать в экспортируемую конфигурацию.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from app.repositories.base import BaseRepository

#: Ключи служебного состояния.
KEY_LAST_CERTIFICATES_IMPORT_AT = "last_certificates_import_at"
KEY_LAST_CERTIFICATES_EXCEL_PATH = "last_certificates_excel_path"
KEY_CERTIFICATES_EXCEL_FINGERPRINT = "certificates_excel_fingerprint"
KEY_EMBEDDING_MODEL = "embedding_model"
KEY_WINDOW_STATE = "window_state"
KEY_FIRST_RUN_COMPLETED = "first_run_completed"
KEY_LAST_BACKUP_AT = "last_backup_at"


class SettingsRepository(BaseRepository[dict[str, Any]]):
    """Хранилище пар «ключ → значение» в таблице ``settings``."""

    @property
    def table(self) -> str:
        """Имя таблицы настроек."""
        return "settings"

    def _to_model(self, row: sqlite3.Row) -> dict[str, Any]:
        """Преобразует строку результата в словарь."""
        return dict(row)

    def get(self, key: str, default: str = "") -> str:
        """Возвращает строковое значение настройки.

        Args:
            key: Ключ настройки.
            default: Значение по умолчанию.

        Returns:
            Сохранённое значение либо ``default``.
        """
        row = self._db.query_one("SELECT value FROM settings WHERE key = ?", (key,))
        return str(row["value"]) if row else default

    def set(self, key: str, value: str) -> None:
        """Сохраняет строковое значение настройки.

        Args:
            key: Ключ настройки.
            value: Сохраняемое значение.
        """
        self._db.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT (key) DO UPDATE SET "
            "value = excluded.value, updated_at = excluded.updated_at",
            (key, value, datetime.now().isoformat(timespec="seconds")),
        )

    def get_json(self, key: str, default: Any = None) -> Any:
        """Возвращает значение настройки, сохранённое в формате JSON.

        Args:
            key: Ключ настройки.
            default: Значение по умолчанию.

        Returns:
            Десериализованное значение либо ``default``.
        """
        raw = self.get(key)
        if not raw:
            return default
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return default

    def set_json(self, key: str, value: Any) -> None:
        """Сохраняет значение настройки в формате JSON.

        Args:
            key: Ключ настройки.
            value: Сериализуемое значение.
        """
        self.set(key, json.dumps(value, ensure_ascii=False, default=str))

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Возвращает логическое значение настройки.

        Args:
            key: Ключ настройки.
            default: Значение по умолчанию.

        Returns:
            Логическое значение.
        """
        raw = self.get(key, "1" if default else "0")
        return raw.strip().lower() in {"1", "true", "yes", "да"}

    def set_bool(self, key: str, value: bool) -> None:
        """Сохраняет логическое значение настройки.

        Args:
            key: Ключ настройки.
            value: Сохраняемое значение.
        """
        self.set(key, "1" if value else "0")

    def get_datetime(self, key: str) -> datetime | None:
        """Возвращает отметку времени, сохранённую в настройках.

        Args:
            key: Ключ настройки.

        Returns:
            Дата и время либо ``None``.
        """
        raw = self.get(key)
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    def set_now(self, key: str) -> None:
        """Записывает в настройку текущий момент времени.

        Args:
            key: Ключ настройки.
        """
        self.set(key, datetime.now().isoformat(timespec="seconds"))

    def all_settings(self) -> dict[str, str]:
        """Возвращает все сохранённые настройки.

        Returns:
            Отображение «ключ → значение».
        """
        return {
            str(row["key"]): str(row["value"])
            for row in self._db.query_all("SELECT key, value FROM settings")
        }
