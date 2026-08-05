"""Прогресс, отмена и слабосвязанная шина событий.

Слой сервисов не имеет права знать о существовании графического интерфейса —
это нарушило бы правило зависимостей Clean Architecture. Взаимодействие
строится на трёх примитивах, объявленных здесь:

* :class:`CancellationToken` — кооперативная отмена долгих операций;
* :class:`ProgressReporter` — публикация хода выполнения;
* :class:`EventBus` — публикация доменных событий подписчикам.

Все примитивы потокобезопасны: сервисы работают в пуле потоков, интерфейс —
в главном потоке Tk.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Final

from app.core.exceptions import OperationCancelledError


class CancellationToken:
    """Кооперативный признак отмены длительной операции.

    Сервис обязан периодически вызывать :meth:`raise_if_cancelled` в местах,
    где прерывание безопасно (между файлами, между строками заказа).
    """

    __slots__ = ("_event",)

    def __init__(self) -> None:
        """Создаёт токен в неотменённом состоянии."""
        self._event = threading.Event()

    @property
    def cancelled(self) -> bool:
        """Признак того, что отмена запрошена."""
        return self._event.is_set()

    def cancel(self) -> None:
        """Запрашивает отмену операции."""
        self._event.set()

    def reset(self) -> None:
        """Возвращает токен в исходное состояние для повторного использования."""
        self._event.clear()

    def raise_if_cancelled(self) -> None:
        """Прерывает выполнение, если отмена была запрошена.

        Raises:
            OperationCancelledError: Если :meth:`cancel` уже вызывался.
        """
        if self._event.is_set():
            raise OperationCancelledError

    def wait(self, timeout: float | None = None) -> bool:
        """Блокирует поток до запроса отмены или истечения таймаута.

        Args:
            timeout: Максимальное время ожидания в секундах.

        Returns:
            ``True``, если отмена запрошена.
        """
        return self._event.wait(timeout)


#: Токен-заглушка для вызовов, не поддерживающих отмену.
NULL_TOKEN: Final[CancellationToken] = CancellationToken()


@dataclass(frozen=True, slots=True)
class ProgressUpdate:
    """Снимок хода выполнения операции.

    Attributes:
        current: Количество обработанных элементов.
        total: Общее количество элементов (0, если неизвестно).
        message: Краткое описание текущего шага.
        stage: Машиночитаемый идентификатор этапа.
        elapsed: Время с начала операции в секундах.
        payload: Дополнительные данные для интерфейса.
    """

    current: int
    total: int
    message: str = ""
    stage: str = ""
    elapsed: float = 0.0
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def fraction(self) -> float:
        """Доля выполнения в диапазоне ``[0.0, 1.0]``."""
        if self.total <= 0:
            return 0.0
        return min(1.0, max(0.0, self.current / self.total))

    @property
    def percent(self) -> int:
        """Процент выполнения, округлённый до целого."""
        return round(self.fraction * 100)

    @property
    def eta_seconds(self) -> float | None:
        """Оценка оставшегося времени в секундах.

        Returns:
            Прогноз либо ``None``, если данных для оценки недостаточно.
        """
        if self.current <= 0 or self.total <= 0 or self.elapsed <= 0:
            return None
        rate = self.current / self.elapsed
        if rate <= 0:
            return None
        return max(0.0, (self.total - self.current) / rate)


ProgressCallback = Callable[[ProgressUpdate], None]


class ProgressReporter:
    """Публикует ход выполнения операции с ограничением частоты обновлений.

    Интерфейс не способен перерисовываться 1000 раз в секунду, поэтому
    репортёр «прореживает» поток обновлений (по умолчанию — не чаще 20 Гц),
    всегда пропуская первое и последнее событие.
    """

    def __init__(
        self,
        callback: ProgressCallback | None = None,
        *,
        token: CancellationToken | None = None,
        min_interval: float = 0.05,
    ) -> None:
        """Создаёт репортёр.

        Args:
            callback: Приёмник обновлений; ``None`` отключает публикацию.
            token: Токен отмены, связанный с операцией.
            min_interval: Минимальный интервал между обновлениями в секундах.
        """
        self._callback = callback
        self._token = token or CancellationToken()
        self._min_interval = min_interval
        self._last_emit = 0.0
        self._started = time.monotonic()
        self._current = 0
        self._total = 0
        self._lock = threading.Lock()

    @property
    def token(self) -> CancellationToken:
        """Токен отмены, связанный с операцией."""
        return self._token

    @property
    def elapsed(self) -> float:
        """Время с момента создания репортёра в секундах."""
        return time.monotonic() - self._started

    def start(self, total: int, message: str = "", stage: str = "") -> None:
        """Объявляет начало операции с известным объёмом работы.

        Args:
            total: Общее количество элементов.
            message: Описание операции.
            stage: Идентификатор этапа.
        """
        with self._lock:
            self._total = total
            self._current = 0
            self._started = time.monotonic()
            self._last_emit = 0.0
        self._emit(message, stage, force=True)

    def advance(self, step: int = 1, message: str = "", stage: str = "") -> None:
        """Увеличивает счётчик выполненных элементов.

        Args:
            step: Приращение счётчика.
            message: Описание текущего шага.
            stage: Идентификатор этапа.

        Raises:
            OperationCancelledError: Если операция отменена пользователем.
        """
        self._token.raise_if_cancelled()
        with self._lock:
            self._current += step
        self._emit(message, stage)

    def set_progress(self, current: int, total: int | None = None, message: str = "") -> None:
        """Устанавливает абсолютное значение прогресса.

        Args:
            current: Количество обработанных элементов.
            total: Новое общее количество (если изменилось).
            message: Описание текущего шага.
        """
        with self._lock:
            self._current = current
            if total is not None:
                self._total = total
        self._emit(message, "")

    def finish(self, message: str = "", stage: str = "done") -> None:
        """Объявляет завершение операции (прогресс выставляется в 100 %).

        Args:
            message: Итоговое сообщение.
            stage: Идентификатор завершающего этапа.
        """
        with self._lock:
            if self._total:
                self._current = self._total
        self._emit(message, stage, force=True)

    def note(self, message: str, stage: str = "", **payload: Any) -> None:
        """Публикует сообщение, не изменяя счётчик прогресса.

        Args:
            message: Текст сообщения.
            stage: Идентификатор этапа.
            **payload: Дополнительные данные для интерфейса.
        """
        self._emit(message, stage, force=True, payload=payload)

    def child(self, weight: float = 1.0) -> ProgressReporter:  # noqa: ARG002
        """Создаёт вложенный репортёр, разделяющий токен отмены.

        Args:
            weight: Зарезервировано для взвешенной агрегации подзадач.

        Returns:
            Новый репортёр с тем же приёмником и токеном.
        """
        return ProgressReporter(self._callback, token=self._token, min_interval=self._min_interval)

    def _emit(
        self,
        message: str,
        stage: str,
        *,
        force: bool = False,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Отправляет обновление подписчику с учётом ограничения частоты."""
        if self._callback is None:
            return
        now = time.monotonic()
        if not force and (now - self._last_emit) < self._min_interval:
            return
        self._last_emit = now
        with self._lock:
            update = ProgressUpdate(
                current=self._current,
                total=self._total,
                message=message,
                stage=stage,
                elapsed=now - self._started,
                payload=payload or {},
            )
        self._callback(update)


# --------------------------------------------------------------------------- #
# Шина доменных событий
# --------------------------------------------------------------------------- #
class AppEvent:
    """Имена доменных событий приложения."""

    CERTIFICATES_IMPORT_STARTED: Final[str] = "certificates_import.started"
    CERTIFICATES_IMPORT_FINISHED: Final[str] = "certificates_import.finished"
    ORDER_STARTED: Final[str] = "order.started"
    ORDER_FINISHED: Final[str] = "order.finished"
    ALIAS_CREATED: Final[str] = "alias.created"
    SETTINGS_CHANGED: Final[str] = "settings.changed"
    DATABASE_CHANGED: Final[str] = "database.changed"
    NOTIFICATION: Final[str] = "ui.notification"


class EventBus:
    """Простая потокобезопасная шина «издатель — подписчик».

    Намеренно минималистична: события — строки, полезная нагрузка — словарь.
    Этого достаточно для десктопного приложения и не тянет за собой
    инфраструктуру уровня микросервисов.
    """

    def __init__(self) -> None:
        """Создаёт пустую шину событий."""
        self._subscribers: dict[str, list[Callable[..., None]]] = defaultdict(list)
        self._lock = threading.RLock()

    def subscribe(self, event: str, handler: Callable[..., None]) -> Callable[[], None]:
        """Подписывает обработчик на событие.

        Args:
            event: Имя события (см. :class:`AppEvent`).
            handler: Вызывается с именованными аргументами события.

        Returns:
            Функция отписки.
        """
        with self._lock:
            self._subscribers[event].append(handler)

        def _unsubscribe() -> None:
            with self._lock:
                handlers = self._subscribers.get(event, [])
                if handler in handlers:
                    handlers.remove(handler)

        return _unsubscribe

    def publish(self, event: str, **payload: Any) -> None:
        """Публикует событие всем подписчикам.

        Исключения подписчиков подавляются: сбой одного обработчика не должен
        прерывать бизнес-операцию.

        Args:
            event: Имя события.
            **payload: Данные события.
        """
        with self._lock:
            handlers = tuple(self._subscribers.get(event, ()))
        for handler in handlers:
            try:
                handler(**payload)
            except Exception:
                import logging

                logging.getLogger(__name__).exception("Ошибка обработчика события %s", event)

    def clear(self) -> None:
        """Удаляет всех подписчиков (используется при закрытии приложения)."""
        with self._lock:
            self._subscribers.clear()
