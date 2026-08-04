"""Репозиторий кэша и векторных представлений наименований."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from app.repositories.base import BaseRepository

_LOGGER = logging.getLogger(__name__)


class CacheRepository(BaseRepository[dict[str, Any]]):
    """Универсальный кэш «ключ → значение» с временем жизни.

    Используется для хранения дорогих промежуточных результатов: векторов
    наименований, разобранных структур PDF, статистики панели мониторинга.
    """

    @property
    def table(self) -> str:
        """Имя таблицы кэша."""
        return "cache"

    def _to_model(self, row: sqlite3.Row) -> dict[str, Any]:
        """Преобразует строку результата в словарь."""
        return dict(row)

    # ----------------------------------------------------------- значения
    def set_bytes(
        self, namespace: str, key: str, value: bytes, *, ttl_seconds: int | None = None
    ) -> None:
        """Сохраняет двоичное значение.

        Args:
            namespace: Пространство имён кэша.
            key: Ключ.
            value: Двоичные данные.
            ttl_seconds: Время жизни в секундах (``None`` — бессрочно).
        """
        expires = (
            (datetime.now() + timedelta(seconds=ttl_seconds)).isoformat(timespec="seconds")
            if ttl_seconds
            else None
        )
        self._db.execute(
            "INSERT INTO cache (namespace, key, value, text_value, created_at, expires_at) "
            "VALUES (?, ?, ?, NULL, ?, ?) "
            "ON CONFLICT (namespace, key) DO UPDATE SET "
            "value = excluded.value, text_value = NULL, created_at = excluded.created_at, "
            "expires_at = excluded.expires_at",
            (namespace, key, value, datetime.now().isoformat(timespec="seconds"), expires),
        )

    def get_bytes(self, namespace: str, key: str) -> bytes | None:
        """Возвращает двоичное значение из кэша.

        Args:
            namespace: Пространство имён.
            key: Ключ.

        Returns:
            Данные либо ``None``, если запись отсутствует или устарела.
        """
        row = self._db.query_one(
            "SELECT value, expires_at FROM cache WHERE namespace = ? AND key = ?",
            (namespace, key),
        )
        if row is None:
            return None
        if _is_expired(row["expires_at"]):
            self.delete(namespace, key)
            return None
        value = row["value"]
        return bytes(value) if value is not None else None

    def set_json(
        self, namespace: str, key: str, value: Any, *, ttl_seconds: int | None = None
    ) -> None:
        """Сохраняет значение в формате JSON.

        Args:
            namespace: Пространство имён.
            key: Ключ.
            value: Сериализуемое значение.
            ttl_seconds: Время жизни в секундах.
        """
        expires = (
            (datetime.now() + timedelta(seconds=ttl_seconds)).isoformat(timespec="seconds")
            if ttl_seconds
            else None
        )
        self._db.execute(
            "INSERT INTO cache (namespace, key, value, text_value, created_at, expires_at) "
            "VALUES (?, ?, NULL, ?, ?, ?) "
            "ON CONFLICT (namespace, key) DO UPDATE SET "
            "value = NULL, text_value = excluded.text_value, created_at = excluded.created_at, "
            "expires_at = excluded.expires_at",
            (
                namespace,
                key,
                json.dumps(value, ensure_ascii=False, default=str),
                datetime.now().isoformat(timespec="seconds"),
                expires,
            ),
        )

    def get_json(self, namespace: str, key: str, default: Any = None) -> Any:
        """Возвращает значение, сохранённое в формате JSON.

        Args:
            namespace: Пространство имён.
            key: Ключ.
            default: Значение по умолчанию.

        Returns:
            Десериализованное значение либо ``default``.
        """
        row = self._db.query_one(
            "SELECT text_value, expires_at FROM cache WHERE namespace = ? AND key = ?",
            (namespace, key),
        )
        if row is None or row["text_value"] is None:
            return default
        if _is_expired(row["expires_at"]):
            self.delete(namespace, key)
            return default
        try:
            return json.loads(str(row["text_value"]))
        except json.JSONDecodeError:  # pragma: no cover — повреждённая запись кэша
            return default

    def delete(self, namespace: str, key: str) -> None:
        """Удаляет запись кэша.

        Args:
            namespace: Пространство имён.
            key: Ключ.
        """
        self._db.execute("DELETE FROM cache WHERE namespace = ? AND key = ?", (namespace, key))

    def clear_namespace(self, namespace: str) -> int:
        """Очищает пространство имён целиком.

        Args:
            namespace: Пространство имён.

        Returns:
            Количество удалённых записей.
        """
        cursor = self._db.execute("DELETE FROM cache WHERE namespace = ?", (namespace,))
        return cursor.rowcount

    def purge_expired(self) -> int:
        """Удаляет устаревшие записи кэша.

        Returns:
            Количество удалённых записей.
        """
        cursor = self._db.execute(
            "DELETE FROM cache WHERE expires_at IS NOT NULL AND expires_at < ?",
            (datetime.now().isoformat(timespec="seconds"),),
        )
        return cursor.rowcount

    # -------------------------------------------------------- эмбеддинги
    def save_embeddings(
        self, model: str, dimension: int, vectors: dict[int, bytes], source_hashes: dict[int, str]
    ) -> int:
        """Сохраняет векторные представления наименований сертификатов.

        Args:
            model: Идентификатор модели.
            dimension: Размерность вектора.
            vectors: Отображение «идентификатор сертификата → байты вектора».
            source_hashes: Отображение «идентификатор → хэш исходного текста».

        Returns:
            Количество сохранённых векторов.
        """
        if not vectors:
            return 0
        now = datetime.now().isoformat(timespec="seconds")
        with self._db.transaction(exclusive=True) as connection:
            connection.executemany(
                "INSERT INTO embeddings "
                "(certificate_id, model, dimension, vector, source_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (certificate_id, model) DO UPDATE SET "
                "dimension = excluded.dimension, vector = excluded.vector, "
                "source_hash = excluded.source_hash, created_at = excluded.created_at",
                [
                    (
                        certificate_id,
                        model,
                        dimension,
                        vector,
                        source_hashes.get(certificate_id, ""),
                        now,
                    )
                    for certificate_id, vector in vectors.items()
                ],
            )
        _LOGGER.debug("Сохранено векторов: %s (модель %s)", len(vectors), model)
        return len(vectors)

    def load_embeddings(self, model: str) -> dict[int, tuple[bytes, str]]:
        """Загружает сохранённые векторы для модели.

        Args:
            model: Идентификатор модели.

        Returns:
            Отображение «идентификатор сертификата → (вектор, хэш текста)».
        """
        rows = self._db.query_all(
            "SELECT certificate_id, vector, source_hash FROM embeddings WHERE model = ?", (model,)
        )
        return {
            int(row["certificate_id"]): (bytes(row["vector"]), str(row["source_hash"] or ""))
            for row in rows
        }

    def clear_embeddings(self, model: str = "") -> int:
        """Удаляет сохранённые векторы.

        Args:
            model: Идентификатор модели (пусто — все модели).

        Returns:
            Количество удалённых записей.
        """
        if model:
            cursor = self._db.execute("DELETE FROM embeddings WHERE model = ?", (model,))
        else:
            cursor = self._db.execute("DELETE FROM embeddings")
        return cursor.rowcount


def _is_expired(value: Any) -> bool:
    """Проверяет, истёк ли срок жизни записи кэша."""
    if not value:
        return False
    try:
        return datetime.fromisoformat(str(value)) < datetime.now()
    except ValueError:  # pragma: no cover — повреждённая отметка времени
        return True
