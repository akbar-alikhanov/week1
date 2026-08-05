"""Централизованная настройка журналирования.

Требования продукта:

* журнал пишется в файл с ротацией (корпоративные машины работают месяцами);
* ошибки дублируются в отдельный файл — служба поддержки смотрит только его;
* последние записи доступны интерфейсу мгновенно, без чтения файла;
* сторонние библиотеки (PyMuPDF, sentence-transformers, PIL) не должны
  засорять журнал отладочными сообщениями.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import threading
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from app.core.constants import APP_NAME, APP_VERSION

#: Формат записей в файле журнала.
FILE_FORMAT: Final[str] = "%(asctime)s | %(levelname)-8s | %(name)-38s | %(message)s"
CONSOLE_FORMAT: Final[str] = "%(asctime)s | %(levelname)-8s | %(message)s"
DATE_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S"

#: Сколько записей хранится в оперативной памяти для окна «Журнал».
MEMORY_BUFFER_SIZE: Final[int] = 5000

#: Библиотеки, которым принудительно понижается уровень журналирования.
_NOISY_LOGGERS: Final[tuple[str, ...]] = (
    "PIL",
    "fitz",
    "matplotlib",
    "urllib3",
    "filelock",
    "sentence_transformers",
    "transformers",
    "torch",
    "huggingface_hub",
    "numexpr",
)


@dataclass(frozen=True, slots=True)
class LogRecordView:
    """Неизменяемое представление записи журнала для интерфейса.

    Attributes:
        timestamp: Момент события.
        level: Название уровня (``INFO``, ``ERROR``…).
        level_number: Числовой уровень для фильтрации и раскраски.
        logger: Имя логгера-источника.
        message: Отформатированное сообщение.
    """

    timestamp: datetime
    level: str
    level_number: int
    logger: str
    message: str

    def format(self) -> str:
        """Возвращает строку для отображения в журнале интерфейса."""
        stamp = self.timestamp.strftime("%H:%M:%S")
        return f"{stamp}  {self.level:<8}  {self.message}"


class MemoryLogHandler(logging.Handler):
    """Обработчик, хранящий последние записи в кольцевом буфере.

    Позволяет окну «Журнал операций» показывать историю мгновенно и получать
    новые записи через подписку, без опроса файловой системы.
    """

    def __init__(self, capacity: int = MEMORY_BUFFER_SIZE) -> None:
        """Создаёт обработчик с буфером заданной ёмкости."""
        super().__init__()
        self._records: deque[LogRecordView] = deque(maxlen=capacity)
        self._listeners: list[Callable[[LogRecordView], None]] = []
        self._lock = threading.RLock()

    def emit(self, record: logging.LogRecord) -> None:
        """Сохраняет запись в буфер и оповещает подписчиков."""
        try:
            view = LogRecordView(
                timestamp=datetime.fromtimestamp(record.created),
                level=record.levelname,
                level_number=record.levelno,
                logger=record.name,
                message=record.getMessage(),
            )
        except Exception:
            return

        with self._lock:
            self._records.append(view)
            listeners = tuple(self._listeners)

        for listener in listeners:
            try:
                listener(view)
            except Exception:
                continue

    def snapshot(self, *, min_level: int = logging.NOTSET) -> list[LogRecordView]:
        """Возвращает копию буфера, отфильтрованную по уровню.

        Args:
            min_level: Минимальный числовой уровень записи.

        Returns:
            Список записей от старых к новым.
        """
        with self._lock:
            return [record for record in self._records if record.level_number >= min_level]

    def subscribe(self, listener: Callable[[LogRecordView], None]) -> Callable[[], None]:
        """Подписывает функцию на новые записи журнала.

        Args:
            listener: Вызывается для каждой новой записи. Может выполняться
                в фоновом потоке — интерфейс обязан делать ``after(0, ...)``.

        Returns:
            Функция отписки.
        """
        with self._lock:
            self._listeners.append(listener)

        def _unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return _unsubscribe

    def clear(self) -> None:
        """Очищает буфер записей."""
        with self._lock:
            self._records.clear()


class _MaxLevelFilter(logging.Filter):
    """Пропускает записи строго ниже заданного уровня."""

    def __init__(self, max_level: int) -> None:
        """Запоминает верхнюю границу уровня."""
        super().__init__()
        self._max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        """Возвращает ``True``, если запись ниже установленной границы."""
        return record.levelno < self._max_level


_memory_handler: MemoryLogHandler | None = None
_configured = threading.Event()


def configure_logging(
    *,
    log_file: Path,
    error_log_file: Path,
    level: int | str = logging.INFO,
    console: bool = True,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 5,
) -> MemoryLogHandler:
    """Настраивает корневой логгер приложения.

    Повторный вызов безопасен: конфигурация применяется один раз, последующие
    вызовы возвращают уже созданный буферный обработчик.

    Args:
        log_file: Файл основного журнала.
        error_log_file: Файл журнала ошибок (уровень ``WARNING`` и выше).
        level: Уровень журналирования приложения.
        console: Дублировать ли вывод в консоль (полезно в dev-режиме).
        max_bytes: Размер файла журнала до ротации.
        backup_count: Количество хранимых архивных файлов.

    Returns:
        Обработчик оперативного буфера — источник данных для окна «Журнал».
    """
    global _memory_handler

    if _configured.is_set() and _memory_handler is not None:
        return _memory_handler

    numeric_level = logging.getLevelName(level) if isinstance(level, str) else level
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    file_formatter = logging.Formatter(FILE_FORMAT, datefmt=DATE_FORMAT)

    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(file_formatter)
    root.addHandler(file_handler)

    error_handler = logging.handlers.RotatingFileHandler(
        error_log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    error_handler.setLevel(logging.WARNING)
    error_handler.setFormatter(file_formatter)
    root.addHandler(error_handler)

    if console and sys.stderr is not None:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(logging.Formatter(CONSOLE_FORMAT, datefmt=DATE_FORMAT))
        root.addHandler(console_handler)

    memory_handler = MemoryLogHandler()
    memory_handler.setLevel(logging.DEBUG)
    root.addHandler(memory_handler)
    _memory_handler = memory_handler

    silence_noisy_loggers()
    _configured.set()

    logging.getLogger(__name__).info(
        "%s %s — журналирование инициализировано (%s)", APP_NAME, APP_VERSION, log_file
    )
    return memory_handler


def silence_noisy_loggers(names: Iterable[str] = _NOISY_LOGGERS) -> None:
    """Понижает уровень журналирования сторонних библиотек.

    Args:
        names: Имена логгеров, для которых устанавливается уровень ``WARNING``.
    """
    for name in names:
        logging.getLogger(name).setLevel(logging.WARNING)


def get_memory_handler() -> MemoryLogHandler | None:
    """Возвращает активный буферный обработчик, если журналирование настроено.

    Returns:
        :class:`MemoryLogHandler` либо ``None``.
    """
    return _memory_handler


def get_logger(name: str) -> logging.Logger:
    """Возвращает именованный логгер приложения.

    Args:
        name: Обычно ``__name__`` вызывающего модуля.

    Returns:
        Настроенный логгер.
    """
    return logging.getLogger(name)


def install_excepthook() -> None:
    """Перехватывает необработанные исключения главного и фоновых потоков.

    Без этого в собранном без консоли EXE исключение исчезает бесследно.
    """
    logger = logging.getLogger("app.unhandled")

    def _hook(exc_type: type[BaseException], exc: BaseException, traceback: object) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, traceback)  # type: ignore[arg-type]
            return
        logger.critical("Необработанное исключение", exc_info=(exc_type, exc, traceback))  # type: ignore[arg-type]

    sys.excepthook = _hook

    def _thread_hook(args: threading.ExceptHookArgs) -> None:
        if issubclass(args.exc_type, KeyboardInterrupt):
            return
        logger.critical(
            "Необработанное исключение в потоке %s",
            args.thread.name if args.thread else "?",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),  # type: ignore[arg-type]
        )

    threading.excepthook = _thread_hook
