"""Слой доступа к SQLite: соединения, схема, миграции."""

from app.database.connection import Database
from app.database.schema import TARGET_VERSION, apply_migrations

__all__ = ["TARGET_VERSION", "Database", "apply_migrations"]
