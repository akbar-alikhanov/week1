"""Репозиторий справочника товаров из обработанных заказов."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from app.core.text import normalize
from app.models.product import Product
from app.repositories.base import BaseRepository


class ProductRepository(BaseRepository[Product]):
    """Накопительный справочник товарных позиций.

    Наполняется автоматически при каждой обработке заказа и служит источником
    подсказок в строке поиска, а также аналитики «проблемные позиции».
    """

    @property
    def table(self) -> str:
        """Имя таблицы товаров."""
        return "products"

    def _to_model(self, row: sqlite3.Row) -> Product:
        """Преобразует строку результата в :class:`Product`."""
        return Product.from_row(row)

    def record_occurrence(
        self, name: str, *, certificate_id: int | None = None, matched: bool = False
    ) -> None:
        """Регистрирует появление товара в заказе.

        Args:
            name: Наименование товара из заказа.
            certificate_id: Сертификат, выбранный для позиции.
            matched: Признак успешного подбора.
        """
        normalized = normalize(name)
        if not normalized:
            return
        now = datetime.now().isoformat(timespec="seconds")
        with self._db.transaction(exclusive=True) as connection:
            existing = connection.execute(
                "SELECT id FROM products WHERE normalized_name = ?", (normalized,)
            ).fetchone()
            if existing is None:
                product = Product(name=name, last_certificate_id=certificate_id)
                product.seen_count = 1
                product.matched_count = 1 if matched else 0
                self._insert(connection, product.to_row())
            else:
                connection.execute(
                    "UPDATE products SET seen_count = seen_count + 1, "
                    "matched_count = matched_count + ?, "
                    "last_certificate_id = COALESCE(?, last_certificate_id), "
                    "last_seen_at = ? WHERE id = ?",
                    (1 if matched else 0, certificate_id, now, int(existing["id"])),
                )

    def record_many(self, entries: list[tuple[str, int | None, bool]]) -> None:
        """Массово регистрирует появления товаров.

        Args:
            entries: Кортежи ``(наименование, идентификатор сертификата, успех)``.
        """
        for name, certificate_id, matched in entries:
            self.record_occurrence(name, certificate_id=certificate_id, matched=matched)

    def find_by_name(self, name: str) -> Product | None:
        """Находит товар по наименованию.

        Args:
            name: Наименование (нормализуется автоматически).

        Returns:
            Товар либо ``None``.
        """
        row = self._db.query_one(
            "SELECT * FROM products WHERE normalized_name = ?", (normalize(name),)
        )
        return self._to_model(row) if row else None

    def suggest(self, prefix: str, limit: int = 10) -> list[Product]:
        """Возвращает подсказки для строки поиска.

        Args:
            prefix: Введённый пользователем префикс.
            limit: Максимальное количество подсказок.

        Returns:
            Список товаров, отсортированный по частоте появления.
        """
        pattern = f"{normalize(prefix)}%"
        rows = self._db.query_all(
            "SELECT * FROM products WHERE normalized_name LIKE ? "
            "ORDER BY seen_count DESC, last_seen_at DESC LIMIT ?",
            (pattern, limit),
        )
        return self._rows_to_models(rows)

    def problematic(self, limit: int = 50) -> list[Product]:
        """Возвращает позиции с наихудшей долей успешных подборов.

        Такой список — прямое указание оператору, для каких товаров стоит
        создать псевдонимы вручную.

        Args:
            limit: Максимальное количество записей.

        Returns:
            Список товаров.
        """
        rows = self._db.query_all(
            "SELECT * FROM products WHERE seen_count > 0 "
            "AND (CAST(matched_count AS REAL) / seen_count) < 0.9 "
            "ORDER BY (CAST(matched_count AS REAL) / seen_count) ASC, seen_count DESC LIMIT ?",
            (limit,),
        )
        return self._rows_to_models(rows)

    def statistics(self) -> dict[str, Any]:
        """Собирает статистику справочника товаров.

        Returns:
            Словарь с количеством товаров и средней долей успешных подборов.
        """
        row = self._db.query_one(
            "SELECT count(*) AS total, "
            "COALESCE(sum(seen_count), 0) AS occurrences, "
            "COALESCE(sum(matched_count), 0) AS matches FROM products"
        )
        total = int(row["total"]) if row else 0
        occurrences = int(row["occurrences"]) if row else 0
        matches = int(row["matches"]) if row else 0
        return {
            "total": total,
            "occurrences": occurrences,
            "matches": matches,
            "match_rate": (matches / occurrences) if occurrences else 0.0,
        }
