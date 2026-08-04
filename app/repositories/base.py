"""Базовый репозиторий и общие помощники доступа к данным.

Слой репозиториев — единственное место в приложении, где присутствует SQL.
Сервисы оперируют доменными объектами и ничего не знают ни о SQLite,
ни о структуре таблиц (Repository Pattern, принцип инверсии зависимостей).
"""

from __future__ import annotations

import logging
import sqlite3
from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from typing import Any, Generic, TypeVar

from app.core.exceptions import DatabaseError
from app.database.connection import Database

_LOGGER = logging.getLogger(__name__)

TModel = TypeVar("TModel")


class BaseRepository(ABC, Generic[TModel]):
    """Общая функциональность репозиториев поверх :class:`Database`.

    Наследники объявляют имя таблицы и способ преобразования строки в модель,
    получая взамен типовые операции вставки, обновления и удаления.
    """

    def __init__(self, database: Database) -> None:
        """Сохраняет ссылку на менеджер базы данных.

        Args:
            database: Менеджер соединений SQLite.
        """
        self._db = database

    # ---------------------------------------------------------- контракт
    @property
    @abstractmethod
    def table(self) -> str:
        """Имя таблицы, обслуживаемой репозиторием."""

    @abstractmethod
    def _to_model(self, row: sqlite3.Row) -> TModel:
        """Преобразует строку результата в доменную модель.

        Args:
            row: Строка результата запроса.

        Returns:
            Доменный объект.
        """

    # ---------------------------------------------------------- помощники
    @property
    def database(self) -> Database:
        """Менеджер базы данных, используемый репозиторием."""
        return self._db

    def count(self, where: str = "", parameters: Sequence[Any] = ()) -> int:
        """Возвращает количество записей, удовлетворяющих условию.

        Args:
            where: Условие ``WHERE`` без ключевого слова (пусто — все записи).
            parameters: Параметры условия.

        Returns:
            Количество записей.
        """
        clause = f" WHERE {where}" if where else ""
        return int(
            self._db.query_scalar(f"SELECT count(*) FROM {self.table}{clause}", parameters) or 0
        )

    def exists(self, where: str, parameters: Sequence[Any] = ()) -> bool:
        """Проверяет наличие хотя бы одной подходящей записи.

        Args:
            where: Условие ``WHERE`` без ключевого слова.
            parameters: Параметры условия.

        Returns:
            ``True``, если запись существует.
        """
        row = self._db.query_one(f"SELECT 1 FROM {self.table} WHERE {where} LIMIT 1", parameters)
        return row is not None

    def delete_by_id(self, identifier: int) -> bool:
        """Удаляет запись по первичному ключу.

        Args:
            identifier: Значение первичного ключа.

        Returns:
            ``True``, если запись была удалена.
        """
        cursor = self._db.execute(f"DELETE FROM {self.table} WHERE id = ?", (identifier,))
        return cursor.rowcount > 0

    def clear(self) -> int:
        """Удаляет все записи таблицы.

        Returns:
            Количество удалённых записей.
        """
        total = self.count()
        self._db.execute(f"DELETE FROM {self.table}")
        _LOGGER.info("Таблица %s очищена (%s записей)", self.table, total)
        return total

    def _rows_to_models(self, rows: Iterable[sqlite3.Row]) -> list[TModel]:
        """Преобразует набор строк в список моделей."""
        return [self._to_model(row) for row in rows]

    def _insert(
        self, connection: sqlite3.Connection, data: dict[str, Any], *, table: str | None = None
    ) -> int:
        """Вставляет запись и возвращает её идентификатор.

        Args:
            connection: Соединение внутри активной транзакции.
            data: Значения колонок (ключ ``id`` со значением ``None`` игнорируется).
            table: Имя таблицы; по умолчанию — таблица репозитория.

        Returns:
            Идентификатор вставленной записи.

        Raises:
            DatabaseError: При нарушении ограничений целостности.
        """
        payload = {key: value for key, value in data.items() if not (key == "id" and value is None)}
        columns = ", ".join(payload)
        placeholders = ", ".join(f":{key}" for key in payload)
        sql = f"INSERT INTO {table or self.table} ({columns}) VALUES ({placeholders})"
        try:
            cursor = connection.execute(sql, payload)
        except sqlite3.Error as error:
            raise DatabaseError("Не удалось добавить запись", details=f"{sql}\n{error}") from error
        return int(cursor.lastrowid or 0)

    def _update(
        self,
        connection: sqlite3.Connection,
        data: dict[str, Any],
        *,
        where: str,
        parameters: dict[str, Any],
        table: str | None = None,
    ) -> int:
        """Обновляет записи по условию.

        Args:
            connection: Соединение внутри активной транзакции.
            data: Новые значения колонок.
            where: Условие ``WHERE`` без ключевого слова.
            parameters: Параметры условия.
            table: Имя таблицы; по умолчанию — таблица репозитория.

        Returns:
            Количество изменённых записей.

        Raises:
            DatabaseError: При ошибке выполнения запроса.
        """
        payload = {key: value for key, value in data.items() if key != "id"}
        assignments = ", ".join(f"{key} = :{key}" for key in payload)
        sql = f"UPDATE {table or self.table} SET {assignments} WHERE {where}"
        try:
            cursor = connection.execute(sql, {**payload, **parameters})
        except sqlite3.Error as error:
            raise DatabaseError("Не удалось обновить запись", details=f"{sql}\n{error}") from error
        return cursor.rowcount
