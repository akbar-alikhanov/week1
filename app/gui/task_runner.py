"""Выполнение длительных операций без блокировки интерфейса.

Главное правило Tkinter: любое обращение к виджету допустимо только из потока,
создавшего окно. Нарушение приводит к произвольным сбоям, которые невозможно
воспроизвести. Поэтому вся тяжёлая работа выполняется в пуле потоков, а
результаты и обновления прогресса возвращаются в поток интерфейса через
``widget.after(0, ...)``.

Класс :class:`TaskRunner` — единственный разрешённый способ запуска фоновой
работы из графического слоя.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from app.core.concurrency import ManagedThreadPool
from app.core.events import CancellationToken, ProgressReporter, ProgressUpdate
from app.core.exceptions import CertMatcherError, OperationCancelledError

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(slots=True)
class TaskHandle(Generic[T]):
    """Управление запущенной фоновой задачей.

    Attributes:
        name: Имя задачи (для журнала и интерфейса).
        token: Токен отмены.
        cancelled: Признак запрошенной отмены.
        finished: Признак завершения.
    """

    name: str
    token: CancellationToken = field(default_factory=CancellationToken)
    cancelled: bool = False
    finished: bool = False

    def cancel(self) -> None:
        """Запрашивает отмену задачи."""
        self.cancelled = True
        self.token.cancel()


class TaskRunner:
    """Запускает фоновые задачи и возвращает результат в поток интерфейса."""

    def __init__(self, widget: Any, pool: ManagedThreadPool) -> None:
        """Создаёт исполнитель задач.

        Args:
            widget: Любой виджет окна — источник планировщика ``after``.
            pool: Пул фоновых потоков.
        """
        self._widget = widget
        self._pool = pool
        self._active: dict[str, TaskHandle[Any]] = {}

    @property
    def active_tasks(self) -> list[str]:
        """Имена выполняющихся задач."""
        return [name for name, handle in self._active.items() if not handle.finished]

    def is_running(self, name: str) -> bool:
        """Проверяет, выполняется ли задача с указанным именем.

        Args:
            name: Имя задачи.

        Returns:
            ``True``, если задача активна.
        """
        handle = self._active.get(name)
        return handle is not None and not handle.finished

    def run(
        self,
        name: str,
        work: Callable[[ProgressReporter], T],
        *,
        on_success: Callable[[T], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        on_progress: Callable[[ProgressUpdate], None] | None = None,
        on_cancelled: Callable[[], None] | None = None,
        on_finally: Callable[[], None] | None = None,
    ) -> TaskHandle[T] | None:
        """Запускает задачу в фоновом потоке.

        Args:
            name: Уникальное имя задачи. Повторный запуск задачи с тем же
                именем игнорируется — это защищает от двойного нажатия кнопки.
            work: Функция, выполняемая в фоне; получает репортёр прогресса.
            on_success: Обработчик результата (в потоке интерфейса).
            on_error: Обработчик ошибки (в потоке интерфейса).
            on_progress: Обработчик прогресса (в потоке интерфейса).
            on_cancelled: Обработчик отмены (в потоке интерфейса).
            on_finally: Вызывается в любом случае (в потоке интерфейса).

        Returns:
            Дескриптор задачи либо ``None``, если задача уже выполняется.
        """
        if self.is_running(name):
            _LOGGER.debug("Задача «%s» уже выполняется — повторный запуск пропущен", name)
            return None

        handle: TaskHandle[T] = TaskHandle(name=name)
        self._active[name] = handle

        def _dispatch(callback: Callable[..., None], *args: Any) -> None:
            """Переносит вызов в поток интерфейса."""
            try:
                self._widget.after(0, lambda: callback(*args))
            except Exception:
                _LOGGER.debug("Обновление интерфейса пропущено: окно закрыто")

        def _progress(update: ProgressUpdate) -> None:
            if on_progress is not None:
                _dispatch(on_progress, update)

        reporter = ProgressReporter(_progress, token=handle.token)

        def _finish() -> None:
            handle.finished = True
            self._active.pop(name, None)
            if on_finally is not None:
                on_finally()

        def _worker() -> None:
            try:
                result = work(reporter)
            except OperationCancelledError:
                _LOGGER.info("Задача «%s» отменена", name)
                if on_cancelled is not None:
                    _dispatch(on_cancelled)
                _dispatch(_finish)
            except CertMatcherError as error:
                _LOGGER.error("Задача «%s» завершилась ошибкой: %s", name, error.message)
                if error.details:
                    _LOGGER.debug("Подробности: %s", error.details)
                if on_error is not None:
                    _dispatch(on_error, error)
                _dispatch(_finish)
            except Exception as error:
                _LOGGER.exception("Непредвиденная ошибка в задаче «%s»", name)
                if on_error is not None:
                    _dispatch(on_error, error)
                _dispatch(_finish)
            else:
                if on_success is not None:
                    _dispatch(on_success, result)
                _dispatch(_finish)

        self._pool.submit(_worker)
        _LOGGER.debug("Запущена фоновая задача «%s»", name)
        return handle

    def cancel(self, name: str) -> bool:
        """Отменяет задачу по имени.

        Args:
            name: Имя задачи.

        Returns:
            ``True``, если отмена запрошена.
        """
        handle = self._active.get(name)
        if handle is None or handle.finished:
            return False
        handle.cancel()
        _LOGGER.info("Запрошена отмена задачи «%s»", name)
        return True

    def cancel_all(self) -> None:
        """Отменяет все активные задачи."""
        for handle in list(self._active.values()):
            if not handle.finished:
                handle.cancel()
