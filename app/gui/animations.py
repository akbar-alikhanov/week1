"""Анимации интерфейса.

Tkinter не имеет собственной системы анимации. Здесь она реализована на
основе таймера ``after``: значение интерполируется между начальной и конечной
точкой с применением функции сглаживания, а каждый кадр передаётся виджету.

Анимации намеренно короткие (150–300 мс) и подчинены смыслу: они показывают
происхождение элемента и связь между состояниями, а не украшают интерфейс.
Все анимации отключаются одним флагом в настройках — на слабых терминалах и
в удалённых сессиях RDP это критично.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from typing import Any, Final

_LOGGER = logging.getLogger(__name__)

#: Интервал кадра в миллисекундах (примерно 60 кадров в секунду).
FRAME_INTERVAL_MS: Final[int] = 16

#: Стандартные длительности анимаций.
DURATION_FAST: Final[float] = 0.14
DURATION_NORMAL: Final[float] = 0.22
DURATION_SLOW: Final[float] = 0.36


# --------------------------------------------------------------------------- #
# Функции сглаживания
# --------------------------------------------------------------------------- #
def linear(t: float) -> float:
    """Равномерное движение.

    Args:
        t: Нормированное время ``[0..1]``.

    Returns:
        Нормированное значение ``[0..1]``.
    """
    return t


def ease_out_cubic(t: float) -> float:
    """Быстрый старт с плавным замедлением — основная кривая интерфейса.

    Args:
        t: Нормированное время ``[0..1]``.

    Returns:
        Нормированное значение ``[0..1]``.
    """
    return 1.0 - pow(1.0 - t, 3)


def ease_in_out_cubic(t: float) -> float:
    """Симметричное ускорение и замедление.

    Args:
        t: Нормированное время ``[0..1]``.

    Returns:
        Нормированное значение ``[0..1]``.
    """
    if t < 0.5:
        return 4 * t * t * t
    return 1.0 - pow(-2 * t + 2, 3) / 2


def ease_out_back(t: float) -> float:
    """Лёгкий «перелёт» за конечное значение — для появления диалогов.

    Args:
        t: Нормированное время ``[0..1]``.

    Returns:
        Значение, кратковременно выходящее за ``1.0``.
    """
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * pow(t - 1, 3) + c1 * pow(t - 1, 2)


def ease_out_expo(t: float) -> float:
    """Резкое замедление в конце.

    Args:
        t: Нормированное время ``[0..1]``.

    Returns:
        Нормированное значение ``[0..1]``.
    """
    return 1.0 if t >= 1.0 else 1.0 - pow(2, -10 * t)


# --------------------------------------------------------------------------- #
# Работа с цветом
# --------------------------------------------------------------------------- #
def hex_to_rgb(value: str) -> tuple[int, int, int]:
    """Преобразует цвет ``#RRGGBB`` в кортеж компонент.

    Args:
        value: Строка цвета.

    Returns:
        Кортеж ``(r, g, b)``.
    """
    text = value.lstrip("#")
    if len(text) == 3:
        text = "".join(character * 2 for character in text)
    if len(text) != 6:
        return (0, 0, 0)
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError:
        return (0, 0, 0)


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """Преобразует кортеж компонент в строку ``#RRGGBB``.

    Args:
        rgb: Кортеж ``(r, g, b)``.

    Returns:
        Строка цвета.
    """
    red = max(0, min(255, rgb[0]))
    green = max(0, min(255, rgb[1]))
    blue = max(0, min(255, rgb[2]))
    return f"#{red:02X}{green:02X}{blue:02X}"


def blend(start: str, end: str, factor: float) -> str:
    """Смешивает два цвета в заданной пропорции.

    Args:
        start: Начальный цвет.
        end: Конечный цвет.
        factor: Доля конечного цвета ``[0..1]``.

    Returns:
        Результирующий цвет.
    """
    ratio = max(0.0, min(1.0, factor))
    first = hex_to_rgb(start)
    second = hex_to_rgb(end)
    return rgb_to_hex(
        (
            int(first[0] + (second[0] - first[0]) * ratio),
            int(first[1] + (second[1] - first[1]) * ratio),
            int(first[2] + (second[2] - first[2]) * ratio),
        )
    )


# --------------------------------------------------------------------------- #
# Механизм анимации
# --------------------------------------------------------------------------- #
class Animation:
    """Одна выполняющаяся анимация.

    Attributes:
        finished: Признак завершения.
    """

    def __init__(
        self,
        widget: Any,
        *,
        start: float,
        end: float,
        duration: float,
        on_frame: Callable[[float], None],
        easing: Callable[[float], float] = ease_out_cubic,
        on_complete: Callable[[], None] | None = None,
    ) -> None:
        """Запускает анимацию.

        Args:
            widget: Виджет, чей планировщик ``after`` используется.
            start: Начальное значение.
            end: Конечное значение.
            duration: Длительность в секундах.
            on_frame: Вызывается с текущим значением на каждом кадре.
            easing: Функция сглаживания.
            on_complete: Вызывается по завершении.
        """
        self._widget = widget
        self._start = start
        self._end = end
        self._duration = max(0.01, duration)
        self._on_frame = on_frame
        self._easing = easing
        self._on_complete = on_complete
        self._started_at = time.perf_counter()
        self._after_id: str | None = None
        self.finished = False
        self._tick()

    def _tick(self) -> None:
        """Рассчитывает и применяет очередной кадр."""
        if self.finished:
            return

        elapsed = time.perf_counter() - self._started_at
        progress = min(1.0, elapsed / self._duration)
        value = self._start + (self._end - self._start) * self._easing(progress)

        try:
            self._on_frame(value)
        except Exception:
            self.stop()
            return

        if progress >= 1.0:
            self.finished = True
            if self._on_complete is not None:
                try:
                    self._on_complete()
                except Exception:
                    _LOGGER.debug("Ошибка обработчика завершения анимации", exc_info=True)
            return

        try:
            self._after_id = self._widget.after(FRAME_INTERVAL_MS, self._tick)
        except Exception:
            self.finished = True

    def stop(self) -> None:
        """Прерывает анимацию."""
        self.finished = True
        if self._after_id is not None:
            try:
                self._widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None


class Animator:
    """Управляет анимациями одного окна.

    Хранит активные анимации по ключу, что позволяет корректно перезапускать
    анимацию того же свойства (например, при быстром наведении и уводе курсора)
    без «дрожания» из-за наложения нескольких таймеров.
    """

    def __init__(self, enabled: bool = True) -> None:
        """Создаёт менеджер анимаций.

        Args:
            enabled: Разрешены ли анимации.
        """
        self._enabled = enabled
        self._active: dict[str, Animation] = {}
        self._pulses: dict[str, dict[str, bool]] = {}

    @property
    def enabled(self) -> bool:
        """Разрешены ли анимации."""
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        """Включает или выключает анимации.

        Args:
            value: Новое состояние.
        """
        self._enabled = value
        if not value:
            self.stop_all()

    def animate(
        self,
        widget: Any,
        key: str,
        *,
        start: float,
        end: float,
        on_frame: Callable[[float], None],
        duration: float = DURATION_NORMAL,
        easing: Callable[[float], float] = ease_out_cubic,
        on_complete: Callable[[], None] | None = None,
    ) -> None:
        """Запускает анимацию значения.

        При выключенных анимациях конечное значение применяется сразу —
        интерфейс остаётся полностью функциональным.

        Args:
            widget: Виджет-владелец таймера.
            key: Уникальный ключ анимации (обычно ``id(widget)`` + свойство).
            start: Начальное значение.
            end: Конечное значение.
            on_frame: Обработчик кадра.
            duration: Длительность в секундах.
            easing: Функция сглаживания.
            on_complete: Обработчик завершения.
        """
        existing = self._active.pop(key, None)
        if existing is not None:
            existing.stop()

        if not self._enabled:
            try:
                on_frame(end)
                if on_complete is not None:
                    on_complete()
            except Exception:
                pass
            return

        def _complete() -> None:
            self._active.pop(key, None)
            if on_complete is not None:
                on_complete()

        self._active[key] = Animation(
            widget,
            start=start,
            end=end,
            duration=duration,
            on_frame=on_frame,
            easing=easing,
            on_complete=_complete,
        )

    def fade_color(
        self,
        widget: Any,
        key: str,
        *,
        start_color: str,
        end_color: str,
        apply: Callable[[str], None],
        duration: float = DURATION_FAST,
    ) -> None:
        """Плавно меняет цвет.

        Args:
            widget: Виджет-владелец таймера.
            key: Ключ анимации.
            start_color: Начальный цвет.
            end_color: Конечный цвет.
            apply: Применяет цвет к виджету.
            duration: Длительность в секундах.
        """
        self.animate(
            widget,
            key,
            start=0.0,
            end=1.0,
            duration=duration,
            on_frame=lambda value: apply(blend(start_color, end_color, value)),
        )

    def pulse(
        self, widget: Any, key: str, *, apply: Callable[[float], None], period: float = 1.4
    ) -> None:
        """Запускает пульсацию значения (для индикации фоновой работы).

        Args:
            widget: Виджет-владелец таймера.
            key: Ключ анимации.
            apply: Получает значение ``[0..1]``.
            period: Длительность полного цикла в секундах.
        """
        if not self._enabled:
            apply(1.0)
            return

        started = time.perf_counter()
        state = {"running": True}

        def _tick() -> None:
            if not state["running"] or key not in self._pulses:
                return
            phase = ((time.perf_counter() - started) % period) / period
            try:
                apply(0.5 + 0.5 * math.sin(phase * math.tau))
                widget.after(FRAME_INTERVAL_MS * 2, _tick)
            except Exception:
                state["running"] = False
                self._pulses.pop(key, None)

        self._pulses[key] = state
        _tick()

    def stop_pulse(self, key: str) -> None:
        """Останавливает пульсацию.

        Args:
            key: Ключ анимации.
        """
        state = self._pulses.pop(key, None)
        if state is not None:
            state["running"] = False

    def stop(self, key: str) -> None:
        """Останавливает анимацию по ключу.

        Args:
            key: Ключ анимации.
        """
        animation = self._active.pop(key, None)
        if animation is not None:
            animation.stop()

    def stop_all(self) -> None:
        """Останавливает все активные анимации."""
        for animation in list(self._active.values()):
            animation.stop()
        self._active.clear()
        for state in self._pulses.values():
            state["running"] = False
        self._pulses.clear()
