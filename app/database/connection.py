"""Управление соединениями SQLite.

Приложение многопоточное: индексация работает в пуле, интерфейс — в главном
потоке. Объекты соединения SQLite не переносятся между потоками, поэтому
:class:`Database` выдаёт каждому потоку собственное соединение и закрывает их
централизованно при завершении работы.

Режим WAL обязателен: он позволяет читать данные для интерфейса, пока фоновая
индексация выполняет запись, без блокировок и «подвисаний» окна.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.exceptions import DatabaseError
from app.database.schema import apply_migrations, current_version

_LOGGER = logging.getLogger(__name__)

#: PRAGMA, применяемые к каждому новому соединению.
_CONNECTION_PRAGMAS: tuple[str, ...] = (
    "PRAGMA journal_mode = WAL",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA foreign_keys = ON",
    "PRAGMA temp_store = MEMORY",
    "PRAGMA cache_size = -32000",  # ~32 МБ страничного кэша
    "PRAGMA busy_timeout = 10000",
    "PRAGMA mmap_size = 268435456",  # 256 МБ отображения файла в память
)


class Database:
    """Пул соединений SQLite «по одному на поток».

    Класс не содержит бизнес-логики: он отвечает только за жизненный цикл
    соединений, транзакции и обслуживание файла базы. Доступ к данным
    инкапсулируют репозитории.
    """

    def __init__(self, path: Path, *, timeout: float = 15.0) -> None:
        """Создаёт менеджер базы данных.

        Args:
            path: Путь к файлу базы (каталог создаётся автоматически).
            timeout: Таймаут ожидания снятия блокировки, в секундах.
        """
        self._path = path
        self._timeout = timeout
        self._local = threading.local()
        self._connections: list[sqlite3.Connection] = []
        self._lock = threading.RLock()
        self._write_lock = threading.RLock()
        self._closed = False
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------------------- свойства
    @property
    def path(self) -> Path:
        """Путь к файлу базы данных."""
        return self._path

    @property
    def schema_version(self) -> int:
        """Текущая версия схемы базы."""
        return current_version(self.connection)

    @property
    def connection(self) -> sqlite3.Connection:
        """Соединение, принадлежащее текущему потоку.

        Returns:
            Открытое соединение SQLite.

        Raises:
            DatabaseError: Если база уже закрыта или соединение не создаётся.
        """
        if self._closed:
            raise DatabaseError("База данных закрыта")
        connection: sqlite3.Connection | None = getattr(self._local, "connection", None)
        if connection is None:
            connection = self._create_connection()
            self._local.connection = connection
            with self._lock:
                self._connections.append(connection)
        return connection

    # ------------------------------------------------------------ жизненный цикл
    def _create_connection(self) -> sqlite3.Connection:
        """Открывает и настраивает новое соединение."""
        try:
            connection = sqlite3.connect(
                self._path,
                timeout=self._timeout,
                check_same_thread=False,
                isolation_level=None,  # ручное управление транзакциями
            )
        except sqlite3.Error as error:
            raise DatabaseError(
                f"Не удалось открыть базу данных {self._path}", details=str(error)
            ) from error

        connection.row_factory = sqlite3.Row
        for pragma in _CONNECTION_PRAGMAS:
            try:
                connection.execute(pragma)
            except sqlite3.Error as error:  # pragma: no cover — зависит от платформы
                _LOGGER.debug("PRAGMA не применён (%s): %s", pragma, error)
        connection.create_function("REGEXP", 2, _regexp, deterministic=True)
        connection.create_function("LOWER", 1, _lower_unicode, deterministic=True)
        return connection

    def initialize(self) -> int:
        """Создаёт схему и применяет миграции.

        Returns:
            Версия схемы после инициализации.
        """
        version = apply_migrations(self.connection)
        _LOGGER.info("База данных готова: %s (схема версии %s)", self._path, version)
        return version

    def close(self) -> None:
        """Закрывает все открытые соединения."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for connection in self._connections:
                try:
                    connection.close()
                except sqlite3.Error:  # pragma: no cover — соединение уже закрыто
                    continue
            self._connections.clear()
        _LOGGER.debug("Соединения с базой данных закрыты")

    def __enter__(self) -> Database:
        """Поддержка протокола контекстного менеджера."""
        return self

    def __exit__(self, *_: object) -> None:
        """Закрывает соединения при выходе из блока ``with``."""
        self.close()

    # -------------------------------------------------------------- транзакции
    @contextmanager
    def transaction(self, *, exclusive: bool = False) -> Iterator[sqlite3.Connection]:
        """Выполняет блок кода в транзакции.

        Args:
            exclusive: Сериализовать ли запись через внутреннюю блокировку.
                Полезно при массовых вставках из нескольких потоков.

        Yields:
            Соединение внутри активной транзакции.

        Raises:
            DatabaseError: При ошибке SQLite (транзакция откатывается).
        """
        connection = self.connection
        lock = self._write_lock if exclusive else _NullLock()
        with lock:
            try:
                connection.execute("BEGIN IMMEDIATE" if exclusive else "BEGIN")
            except sqlite3.OperationalError as error:
                raise DatabaseError("Не удалось начать транзакцию", details=str(error)) from error
            try:
                yield connection
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()

    # ---------------------------------------------------------------- запросы
    def execute(self, sql: str, parameters: Sequence[Any] | dict[str, Any] = ()) -> sqlite3.Cursor:
        """Выполняет одиночный запрос.

        Args:
            sql: Текст SQL-запроса.
            parameters: Параметры запроса.

        Returns:
            Курсор с результатом.

        Raises:
            DatabaseError: При ошибке выполнения.
        """
        try:
            return self.connection.execute(sql, parameters)
        except sqlite3.Error as error:
            raise DatabaseError("Ошибка выполнения запроса", details=f"{sql}\n{error}") from error

    def query_one(
        self, sql: str, parameters: Sequence[Any] | dict[str, Any] = ()
    ) -> sqlite3.Row | None:
        """Возвращает первую строку результата.

        Args:
            sql: Текст SQL-запроса.
            parameters: Параметры запроса.

        Returns:
            Строка результата либо ``None``.
        """
        # У sqlite3.Cursor.fetchone() в тайп-стабе возвращаемый тип — Any
        # (реальный тип строки зависит от row_factory, который стаб не видит).
        # Явно аннотированная локальная переменная фиксирует ожидаемый тип,
        # не пряча при этом настоящую ошибку типа через cast().
        row: sqlite3.Row | None = self.execute(sql, parameters).fetchone()
        return row

    def query_all(
        self, sql: str, parameters: Sequence[Any] | dict[str, Any] = ()
    ) -> list[sqlite3.Row]:
        """Возвращает все строки результата.

        Args:
            sql: Текст SQL-запроса.
            parameters: Параметры запроса.

        Returns:
            Список строк результата.
        """
        return self.execute(sql, parameters).fetchall()

    def query_scalar(self, sql: str, parameters: Sequence[Any] | dict[str, Any] = ()) -> Any:
        """Возвращает первое значение первой строки результата.

        Args:
            sql: Текст SQL-запроса.
            parameters: Параметры запроса.

        Returns:
            Скалярное значение либо ``None``.
        """
        row = self.query_one(sql, parameters)
        return row[0] if row is not None else None

    # ------------------------------------------------------------ обслуживание
    def vacuum(self) -> None:
        """Дефрагментирует файл базы данных."""
        try:
            self.connection.execute("VACUUM")
            _LOGGER.info("Выполнена дефрагментация базы данных")
        except sqlite3.Error as error:
            _LOGGER.warning("Не удалось выполнить VACUUM: %s", error)

    def analyze(self) -> None:
        """Обновляет статистику планировщика запросов."""
        try:
            self.connection.execute("ANALYZE")
        except sqlite3.Error as error:  # pragma: no cover
            _LOGGER.debug("ANALYZE не выполнен: %s", error)

    def checkpoint(self) -> None:
        """Переносит содержимое WAL-журнала в основной файл базы.

        Контрольная точка — вспомогательная операция для надёжности хранения,
        а не обязательный шаг: ошибка здесь никогда не должна прерывать
        завершение работы приложения, поэтому исключения гасятся так же, как
        и при обычных сбоях SQLite. В частности, вызов после :meth:`close`
        (например, при повторном ``shutdown()`` — см.
        :class:`~app.core.container.ApplicationContainer`) тихо ничего не
        делает вместо того, чтобы бросить :class:`DatabaseError`: та же
        блокировка, что и у :meth:`close`, исключает состояние гонки между
        ними в многопоточном сценарии.
        """
        with self._lock:
            if self._closed:
                return
            try:
                self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.Error as error:  # pragma: no cover
                _LOGGER.debug("Контрольная точка WAL не выполнена: %s", error)

    def backup_to(self, destination: Path) -> Path:
        """Создаёт согласованную резервную копию базы.

        Используется онлайн-API SQLite: копия корректна даже во время записи.

        Args:
            destination: Путь файла резервной копии.

        Returns:
            Путь созданной копии.

        Raises:
            DatabaseError: Если копию создать не удалось.
        """
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with sqlite3.connect(destination) as target:
                self.connection.backup(target)
        except (sqlite3.Error, OSError) as error:
            raise DatabaseError(
                "Не удалось создать резервную копию базы данных", details=str(error)
            ) from error
        _LOGGER.info("Создана резервная копия базы данных: %s", destination)
        return destination

    def restore_from(self, source: Path) -> None:
        """Восстанавливает базу из резервной копии.

        Текущий файл базы предварительно сохраняется с суффиксом
        ``.before-restore``, чтобы неудачное восстановление можно было отменить.

        Args:
            source: Путь к файлу резервной копии.

        Raises:
            DatabaseError: Если файл копии отсутствует или повреждён.
        """
        if not source.exists():
            raise DatabaseError(f"Файл резервной копии не найден: {source}")
        try:
            with sqlite3.connect(source) as probe:
                probe.execute("SELECT count(*) FROM sqlite_master").fetchone()
        except sqlite3.Error as error:
            raise DatabaseError("Файл резервной копии повреждён", details=str(error)) from error

        self.close()
        try:
            if self._path.exists():
                shutil.copy2(self._path, self._path.with_suffix(".db.before-restore"))
            shutil.copy2(source, self._path)
        except OSError as error:
            raise DatabaseError(
                "Не удалось восстановить базу данных", details=str(error)
            ) from error

        with self._lock:
            self._closed = False
            self._local = threading.local()
        self.initialize()
        _LOGGER.info("База данных восстановлена из %s", source)

    def statistics(self) -> dict[str, Any]:
        """Собирает сводку по содержимому базы для панели мониторинга.

        Returns:
            Словарь с количеством записей и размером файла.
        """
        stats: dict[str, Any] = {
            "path": str(self._path),
            "size_bytes": self._path.stat().st_size if self._path.exists() else 0,
            "schema_version": self.schema_version,
            "modified_at": (
                datetime.fromtimestamp(self._path.stat().st_mtime) if self._path.exists() else None
            ),
        }
        for table in ("certificate_products", "products", "aliases", "history", "history_items"):
            try:
                stats[table] = int(self.query_scalar(f"SELECT count(*) FROM {table}") or 0)
            except DatabaseError:  # pragma: no cover — таблица может отсутствовать
                stats[table] = 0
        stats["certificates"] = stats["certificate_products"]
        return stats


class _NullLock:
    """Заглушка блокировки для случаев, когда сериализация не требуется."""

    def __enter__(self) -> None:
        """Ничего не делает."""

    def __exit__(self, *_: object) -> None:
        """Ничего не делает."""


def _regexp(pattern: str, value: str | None) -> bool:
    """Реализация оператора ``REGEXP`` для SQLite.

    Args:
        pattern: Регулярное выражение.
        value: Проверяемое значение.

    Returns:
        ``True``, если значение соответствует выражению.
    """
    import re

    if value is None:
        return False
    try:
        return re.search(pattern, value, re.IGNORECASE) is not None
    except re.error:  # pragma: no cover — некорректный шаблон от пользователя
        return False


def _lower_unicode(value: str | None) -> str | None:
    """Реализация ``LOWER()``, корректно работающая с кириллицей.

    Встроенная функция ``lower()`` в SQLite приводит к нижнему регистру
    только ASCII-символы — «Товар» остаётся «Товар». Поскольку весь текст в
    приложении русскоязычный, а поиск обязан быть нечувствителен к регистру,
    функция регистрируется под тем же именем и подменяет встроенную во всех
    запросах, использующих ``lower(...)`` для сравнения без учёта регистра.

    Args:
        value: Проверяемое значение.

    Returns:
        Значение в нижнем регистре либо ``None``.
    """
    return value.lower() if value is not None else None
