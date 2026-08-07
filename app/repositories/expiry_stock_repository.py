"""Репозиторий Excel-базы сроков годности и остатков (SQLite — индекс над Excel)."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Sequence
from typing import Any

from app.models.expiry_stock import ExpiryStockEntry
from app.repositories.base import BaseRepository

_LOGGER = logging.getLogger(__name__)


class ExpiryStockRepository(BaseRepository[ExpiryStockEntry]):
    """Хранит и ищет партии товаров из Excel-базы сроков годности.

    Как и база сертификатов, база сроков полностью переимпортируется при
    каждом обновлении Excel-файла — инкрементальных обновлений нет (см.
    :class:`~app.services.expiry_import_service.ExpiryImportService`).
    """

    @property
    def table(self) -> str:
        """Имя таблицы базы сроков годности."""
        return "expiry_stock"

    def _to_model(self, row: sqlite3.Row) -> ExpiryStockEntry:
        """Преобразует строку результата в :class:`ExpiryStockEntry`."""
        return ExpiryStockEntry.from_row(row)

    # ------------------------------------------------------------- запись
    def replace_all(self, entries: Sequence[ExpiryStockEntry]) -> int:
        """Полностью заменяет содержимое базы новыми данными из Excel.

        Args:
            entries: Строки, прочитанные из Excel-файла базы сроков годности.

        Returns:
            Количество сохранённых строк.
        """
        with self._db.transaction(exclusive=True) as connection:
            connection.execute("DELETE FROM expiry_stock")
            for entry in entries:
                entry.id = self._insert(connection, entry.to_row())
        _LOGGER.info("База сроков годности переимпортирована: %s строк", len(entries))
        return len(entries)

    # ------------------------------------------------------------- чтение
    def find_by_product_name(self, normalized_name: str) -> list[ExpiryStockEntry]:
        """Находит все партии товара по точному совпадению названия.

        В отличие от подбора сертификата, здесь нет допуска или нечёткого
        сравнения: строка заказа должна совпасть с записью базы дословно
        (после нормализации) — см. докстринг :class:`ExpiryStockEntry`.

        Args:
            normalized_name: Нормализованное полное системное название товара.

        Returns:
            Все партии товара (обычно несколько — разные сроки годности).
        """
        if not normalized_name:
            return []
        rows = self._db.query_all(
            "SELECT * FROM expiry_stock WHERE normalized_name = ?", (normalized_name,)
        )
        return self._rows_to_models(rows)

    def list_all(self) -> list[ExpiryStockEntry]:
        """Загружает всю базу сроков годности.

        Returns:
            Все партии из базы.
        """
        rows = self._db.query_all("SELECT * FROM expiry_stock ORDER BY id")
        return self._rows_to_models(rows)

    # ------------------------------------------------------------ сводка
    def statistics(self) -> dict[str, Any]:
        """Собирает статистику базы сроков годности для панели мониторинга.

        Returns:
            Словарь с показателями: всего партий, уникальных товаров.
        """
        return {
            "total": self.count(),
            "unique_products": int(
                self._db.query_scalar("SELECT count(DISTINCT normalized_name) FROM expiry_stock")
                or 0
            ),
        }
