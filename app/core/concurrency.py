"""Утилиты многопоточности для десктопного приложения.

Tkinter однопоточен: любое обращение к виджетам из фонового потока рано или
поздно приводит к аварийному завершению. Здесь собраны примитивы, которые
позволяют выполнять тяжёлую работу в пуле потоков и безопасно возвращать
результат в поток интерфейса.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Generic, TypeVar

from app.core.constants import APP_SLUG

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")


def default_worker_count(*, io_bound: bool = True, cap: int = 16) -> int:
    """Подбирает разумное число рабочих потоков.

    Индексация PDF ограничена вводом-выводом и C-кодом MuPDF (который
    освобождает GIL), поэтому потоков имеет смысл брать больше числа ядер.

    Args:
        io_bound: Задача ограничена вводом-выводом.
        cap: Жёсткий верхний предел.

    Returns:
        Рекомендуемое количество потоков (не меньше двух).
    """
    cpu_count = os.cpu_count() or 4
    suggested = cpu_count * 2 if io_bound else cpu_count
    return max(2, min(cap, suggested))


class ManagedThreadPool:
    """Пул потоков с именованными потоками и корректным завершением.

    Именование критично при разборе журналов инцидентов: в трассировке видно,
    какая именно подсистема выполняла операцию.
    """

    def __init__(self, max_workers: int | None = None, *, name: str = "worker") -> None:
        """Создаёт пул.

        Args:
            max_workers: Количество потоков; ``None`` — автоопределение.
            name: Префикс имени потоков.
        """
        self._max_workers = max_workers or default_worker_count()
        self._executor = ThreadPoolExecutor(
            max_workers=self._max_workers, thread_name_prefix=f"{APP_SLUG}-{name}"
        )
        self._closed = False

    @property
    def max_workers(self) -> int:
        """Число потоков в пуле."""
        return self._max_workers

    def submit(self, fn: Callable[..., R], /, *args: Any, **kwargs: Any) -> Future[R]:
        """Ставит задачу в очередь пула.

        Args:
            fn: Вызываемый объект.
            *args: Позиционные аргументы.
            **kwargs: Именованные аргументы.

        Returns:
            :class:`concurrent.futures.Future` с результатом.

        Raises:
            RuntimeError: Если пул уже закрыт.
        """
        if self._closed:
            raise RuntimeError("Пул потоков уже закрыт")
        return self._executor.submit(fn, *args, **kwargs)

    def map_unordered(
        self, fn: Callable[[T], R], items: Iterable[T], *, chunk_size: int = 0
    ) -> Iterator[tuple[T, R | None, BaseException | None]]:
        """Выполняет функцию для каждого элемента, отдавая результаты по мере готовности.

        В отличие от :meth:`concurrent.futures.Executor.map`, исключение
        отдельного элемента не прерывает обработку остальных — это обязательное
        свойство при индексации тысяч PDF, среди которых встречаются битые.

        Args:
            fn: Функция-обработчик одного элемента.
            items: Входные элементы.
            chunk_size: Максимальное число одновременно поставленных задач
                (0 — поставить все сразу). Ограничение бережёт память при
                десятках тысяч файлов.

        Yields:
            Кортежи ``(элемент, результат, исключение)``.
        """
        from concurrent.futures import as_completed

        materialized = list(items)
        if not materialized:
            return

        window = chunk_size if chunk_size > 0 else len(materialized)
        pending: dict[Future[R], T] = {}
        index = 0

        while index < len(materialized) and len(pending) < window:
            item = materialized[index]
            pending[self.submit(fn, item)] = item
            index += 1

        while pending:
            done = next(as_completed(pending))
            item = pending.pop(done)
            try:
                yield item, done.result(), None
            except Exception as error:
                yield item, None, error

            if index < len(materialized):
                next_item = materialized[index]
                pending[self.submit(fn, next_item)] = next_item
                index += 1

    def shutdown(self, *, wait: bool = True, cancel_pending: bool = True) -> None:
        """Завершает работу пула.

        Args:
            wait: Дожидаться ли завершения активных задач.
            cancel_pending: Отменять ли задачи, ещё не начавшие выполняться.
        """
        if self._closed:
            return
        self._closed = True
        self._executor.shutdown(wait=wait, cancel_futures=cancel_pending)

    def __enter__(self) -> ManagedThreadPool:
        """Поддержка протокола контекстного менеджера."""
        return self

    def __exit__(self, *_: object) -> None:
        """Гарантирует завершение пула при выходе из блока ``with``."""
        self.shutdown()


class ThreadSafeCounter:
    """Атомарный счётчик для агрегации результатов из нескольких потоков."""

    __slots__ = ("_lock", "_value")

    def __init__(self, initial: int = 0) -> None:
        """Создаёт счётчик с заданным начальным значением."""
        self._value = initial
        self._lock = threading.Lock()

    def increment(self, amount: int = 1) -> int:
        """Увеличивает счётчик и возвращает новое значение.

        Args:
            amount: Приращение.

        Returns:
            Значение после увеличения.
        """
        with self._lock:
            self._value += amount
            return self._value

    @property
    def value(self) -> int:
        """Текущее значение счётчика."""
        with self._lock:
            return self._value


class Debouncer:
    """Откладывает выполнение обратного вызова до «тишины» заданной длительности.

    Применяется для поиска по мере ввода и для реакции на события файловой
    системы (сохранение PDF порождает серию событий изменения).
    """

    def __init__(self, delay: float, callback: Callable[[], None]) -> None:
        """Создаёт дебаунсер.

        Args:
            delay: Длительность «тишины» в секундах.
            callback: Функция, вызываемая после паузы.
        """
        self._delay = delay
        self._callback = callback
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def trigger(self) -> None:
        """Сбрасывает таймер и планирует вызов заново."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._delay, self._run)
            self._timer.daemon = True
            self._timer.start()

    def cancel(self) -> None:
        """Отменяет запланированный вызов."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

    def _run(self) -> None:
        """Выполняет обратный вызов, изолируя исключения."""
        try:
            self._callback()
        except Exception:
            _LOGGER.exception("Ошибка в отложенном обработчике")


class Lazy(Generic[T]):
    """Потокобезопасная ленивая инициализация значения.

    Используется для дорогих ресурсов (модель эмбеддингов весит сотни мегабайт
    и загружается несколько секунд) — приложение должно стартовать мгновенно.
    """

    __slots__ = ("_factory", "_initialized", "_lock", "_value")

    def __init__(self, factory: Callable[[], T]) -> None:
        """Запоминает фабрику значения.

        Args:
            factory: Вызывается один раз при первом обращении.
        """
        self._factory = factory
        self._value: T | None = None
        self._lock = threading.Lock()
        self._initialized = False

    @property
    def initialized(self) -> bool:
        """Признак того, что значение уже создано."""
        return self._initialized

    def get(self) -> T:
        """Возвращает значение, создавая его при первом обращении.

        Returns:
            Инициализированное значение.
        """
        if self._initialized:
            # Быстрый путь опирается на инвариант класса «_initialized истинно
            # означает _value заполнено фабрикой» — сам по себе флаг _initialized
            # не даёт mypy формальных оснований сузить `T | None` до `T`.
            return self._value  # type: ignore[return-value]
        with self._lock:
            if not self._initialized:
                self._value = self._factory()
                self._initialized = True
        return self._value

    def reset(self) -> None:
        """Сбрасывает значение, чтобы оно было создано заново."""
        with self._lock:
            self._value = None
            self._initialized = False
