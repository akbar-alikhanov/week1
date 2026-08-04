"""Репозиторий истории обработки заказов."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any

from app.core.constants import STATUS_AMBIGUOUS, STATUS_MATCHED, STATUS_NOT_FOUND
from app.models.history import ProcessingItem, ProcessingRun
from app.repositories.base import BaseRepository


class HistoryRepository(BaseRepository[ProcessingRun]):
    """Хранение журнала обработки заказов.

    История — не только удобство: она обеспечивает воспроизводимость решений
    (какой сертификат был подставлен в конкретную поставку) и служит основой
    аналитики качества подбора.
    """

    @property
    def table(self) -> str:
        """Имя таблицы истории."""
        return "history"

    def _to_model(self, row: sqlite3.Row) -> ProcessingRun:
        """Преобразует строку результата в :class:`ProcessingRun`."""
        return ProcessingRun.from_row(row)

    # ------------------------------------------------------------- запись
    def start_run(self, run: ProcessingRun) -> ProcessingRun:
        """Создаёт запись о начале обработки.

        Args:
            run: Описание запуска.

        Returns:
            Запуск с заполненным ``id``.
        """
        with self._db.transaction(exclusive=True) as connection:
            run.id = self._insert(connection, run.to_row())
        return run

    def finish_run(self, run: ProcessingRun) -> None:
        """Обновляет запись о завершении обработки.

        Args:
            run: Запуск с заполненными итоговыми показателями.
        """
        run.finished_at = run.finished_at or datetime.now()
        with self._db.transaction(exclusive=True) as connection:
            self._update(
                connection,
                run.to_row(),
                where="run_id = :run_key",
                parameters={"run_key": run.run_id},
            )

    def save_items(self, items: list[ProcessingItem]) -> int:
        """Массово сохраняет строки журнала обработки.

        Args:
            items: Записи по строкам заказа.

        Returns:
            Количество сохранённых записей.
        """
        if not items:
            return 0
        with self._db.transaction(exclusive=True) as connection:
            for item in items:
                self._insert(connection, item.to_row(), table="history_items")
        return len(items)

    def delete_run(self, run_id: str) -> bool:
        """Удаляет запуск и связанные с ним строки.

        Args:
            run_id: Идентификатор запуска.

        Returns:
            ``True``, если запись была удалена.
        """
        with self._db.transaction(exclusive=True) as connection:
            connection.execute("DELETE FROM history_items WHERE run_id = ?", (run_id,))
            cursor = connection.execute("DELETE FROM history WHERE run_id = ?", (run_id,))
            return cursor.rowcount > 0

    def prune(self, keep_days: int) -> int:
        """Удаляет записи старше заданного срока.

        Args:
            keep_days: Сколько дней хранить историю.

        Returns:
            Количество удалённых запусков.
        """
        threshold = (datetime.now() - timedelta(days=keep_days)).isoformat(timespec="seconds")
        with self._db.transaction(exclusive=True) as connection:
            connection.execute(
                "DELETE FROM history_items WHERE run_id IN "
                "(SELECT run_id FROM history WHERE started_at < ?)",
                (threshold,),
            )
            cursor = connection.execute("DELETE FROM history WHERE started_at < ?", (threshold,))
            return cursor.rowcount

    # ------------------------------------------------------------- чтение
    def recent(self, limit: int = 50) -> list[ProcessingRun]:
        """Возвращает последние запуски обработки.

        Args:
            limit: Максимальное количество записей.

        Returns:
            Список запусков, начиная с самого свежего.
        """
        rows = self._db.query_all(
            "SELECT * FROM history ORDER BY started_at DESC LIMIT ?", (limit,)
        )
        return self._rows_to_models(rows)

    def get_run(self, run_id: str) -> ProcessingRun | None:
        """Возвращает запуск по идентификатору.

        Args:
            run_id: Идентификатор запуска.

        Returns:
            Запуск либо ``None``.
        """
        row = self._db.query_one("SELECT * FROM history WHERE run_id = ?", (run_id,))
        return self._to_model(row) if row else None

    def items_for_run(self, run_id: str, *, status: str = "") -> list[ProcessingItem]:
        """Возвращает строки журнала конкретного запуска.

        Args:
            run_id: Идентификатор запуска.
            status: Фильтр по статусу (пусто — все).

        Returns:
            Список записей, отсортированный по номеру строки.
        """
        sql = "SELECT * FROM history_items WHERE run_id = ?"
        parameters: list[Any] = [run_id]
        if status:
            sql += " AND status = ?"
            parameters.append(status)
        sql += " ORDER BY row_number"
        return [ProcessingItem.from_row(row) for row in self._db.query_all(sql, parameters)]

    def unmatched_products(self, limit: int = 100) -> list[tuple[str, int]]:
        """Возвращает товары, которые чаще всего не удаётся подобрать.

        Args:
            limit: Максимальное количество позиций.

        Returns:
            Список пар ``(наименование, количество неудач)``.
        """
        rows = self._db.query_all(
            "SELECT product_name, count(*) AS failures FROM history_items "
            "WHERE status = ? GROUP BY product_name ORDER BY failures DESC LIMIT ?",
            (STATUS_NOT_FOUND, limit),
        )
        return [(str(row["product_name"]), int(row["failures"])) for row in rows]

    def statistics(self, *, days: int = 30) -> dict[str, Any]:
        """Собирает сводку качества подбора за период.

        Args:
            days: Глубина анализа в днях.

        Returns:
            Словарь показателей для панели мониторинга.
        """
        threshold = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        row = self._db.query_one(
            "SELECT count(*) AS runs, COALESCE(sum(total_rows), 0) AS rows_total, "
            "COALESCE(sum(matched), 0) AS matched, COALESCE(sum(manual), 0) AS manual, "
            "COALESCE(sum(ambiguous), 0) AS ambiguous, COALESCE(sum(not_found), 0) AS not_found, "
            "COALESCE(avg(duration_ms), 0) AS avg_duration "
            "FROM history WHERE started_at >= ?",
            (threshold,),
        )
        rows_total = int(row["rows_total"]) if row else 0
        resolved = (int(row["matched"]) + int(row["manual"])) if row else 0
        return {
            "runs": int(row["runs"]) if row else 0,
            "rows_total": rows_total,
            "matched": int(row["matched"]) if row else 0,
            "manual": int(row["manual"]) if row else 0,
            "ambiguous": int(row["ambiguous"]) if row else 0,
            "not_found": int(row["not_found"]) if row else 0,
            "avg_duration_ms": float(row["avg_duration"]) if row else 0.0,
            "success_rate": (resolved / rows_total) if rows_total else 0.0,
            "status_labels": {
                STATUS_MATCHED: "Найдено",
                STATUS_AMBIGUOUS: "Требует проверки",
                STATUS_NOT_FOUND: "Не найдено",
            },
        }
