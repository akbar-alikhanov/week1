"""Векторные иконки, отрисовываемые во время выполнения.

Иконки не хранятся файлами, а рисуются программно средствами Pillow. Это
решение продиктовано тремя причинами:

* сборка остаётся одним EXE без внешних ресурсов;
* иконки автоматически перекрашиваются под светлую и тёмную тему;
* любой масштаб интерфейса (мониторы 4K) даёт чёткое изображение, поскольку
  растр строится под нужный размер, а не масштабируется из готового файла.

Рисование выполняется с четырёхкратным разрешением и последующим уменьшением
по алгоритму Ланцоша — это даёт качественное сглаживание, недоступное
примитивам Pillow напрямую.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Sequence
from typing import Any, Final

_LOGGER = logging.getLogger(__name__)

#: Коэффициент избыточной выборки при отрисовке.
_SUPERSAMPLE: Final[int] = 4

#: Толщина штриха относительно размера иконки.
_STROKE_RATIO: Final[float] = 0.085

Point = tuple[float, float]
IconDrawer = Callable[[Any, float, float, Any], None]


# --------------------------------------------------------------------------- #
# Примитивы рисования (координаты нормированы в диапазоне 0..1)
# --------------------------------------------------------------------------- #
def _scale(points: Sequence[Point], size: float) -> list[tuple[float, float]]:
    """Переводит нормированные координаты в пиксельные."""
    return [(x * size, y * size) for x, y in points]


def _stroke(draw: Any, points: Sequence[Point], size: float, width: float, color: Any) -> None:
    """Рисует ломаную линию со скруглёнными соединениями."""
    scaled = _scale(points, size)
    draw.line(scaled, fill=color, width=max(1, round(width)), joint="curve")
    radius = width / 2
    for x, y in (scaled[0], scaled[-1]):
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)


def _polygon(draw: Any, points: Sequence[Point], size: float, color: Any) -> None:
    """Заливает многоугольник."""
    draw.polygon(_scale(points, size), fill=color)


def _circle(
    draw: Any,
    center: Point,
    radius: float,
    size: float,
    width: float,
    color: Any,
    *,
    fill: bool = False,
) -> None:
    """Рисует окружность или круг."""
    cx, cy = center[0] * size, center[1] * size
    r = radius * size
    box = (cx - r, cy - r, cx + r, cy + r)
    if fill:
        draw.ellipse(box, fill=color)
    else:
        draw.ellipse(box, outline=color, width=max(1, round(width)))


def _rect(
    draw: Any,
    box: tuple[float, float, float, float],
    size: float,
    width: float,
    color: Any,
    *,
    radius: float = 0.12,
    fill: bool = False,
) -> None:
    """Рисует прямоугольник со скруглёнными углами."""
    scaled = (box[0] * size, box[1] * size, box[2] * size, box[3] * size)
    corner = radius * size
    if fill:
        draw.rounded_rectangle(scaled, radius=corner, fill=color)
    else:
        draw.rounded_rectangle(scaled, radius=corner, outline=color, width=max(1, round(width)))


def _arc(
    draw: Any,
    center: Point,
    radius: float,
    start: float,
    end: float,
    size: float,
    width: float,
    color: Any,
) -> None:
    """Рисует дугу окружности."""
    cx, cy = center[0] * size, center[1] * size
    r = radius * size
    draw.arc(
        (cx - r, cy - r, cx + r, cy + r),
        start=start,
        end=end,
        fill=color,
        width=max(1, round(width)),
    )


# --------------------------------------------------------------------------- #
# Определения иконок
# --------------------------------------------------------------------------- #
def _icon_dashboard(draw: Any, size: float, width: float, color: Any) -> None:
    """Панель мониторинга: четыре плитки."""
    _rect(draw, (0.14, 0.14, 0.45, 0.45), size, width, color)
    _rect(draw, (0.55, 0.14, 0.86, 0.45), size, width, color)
    _rect(draw, (0.14, 0.55, 0.45, 0.86), size, width, color)
    _rect(draw, (0.55, 0.55, 0.86, 0.86), size, width, color)


def _icon_certificate(draw: Any, size: float, width: float, color: Any) -> None:
    """Сертификат: лист с печатью."""
    _stroke(
        draw,
        [(0.22, 0.12), (0.68, 0.12), (0.68, 0.62), (0.22, 0.62), (0.22, 0.12)],
        size,
        width,
        color,
    )
    _stroke(draw, [(0.32, 0.26), (0.58, 0.26)], size, width, color)
    _stroke(draw, [(0.32, 0.38), (0.52, 0.38)], size, width, color)
    _circle(draw, (0.68, 0.70), 0.16, size, width, color)
    _stroke(
        draw,
        [(0.62, 0.84), (0.62, 0.96), (0.68, 0.90), (0.74, 0.96), (0.74, 0.84)],
        size,
        width,
        color,
    )


def _icon_alias(draw: Any, size: float, width: float, color: Any) -> None:
    """Псевдоним: два звена цепи."""
    _stroke(draw, [(0.40, 0.34), (0.30, 0.24)], size, width, color)
    _arc(draw, (0.30, 0.30), 0.20, 90, 300, size, width, color)
    _arc(draw, (0.70, 0.70), 0.20, 270, 120, size, width, color)
    _stroke(draw, [(0.42, 0.58), (0.58, 0.42)], size, width, color)


def _icon_history(draw: Any, size: float, width: float, color: Any) -> None:
    """История: циферблат со стрелками."""
    _circle(draw, (0.5, 0.5), 0.36, size, width, color)
    _stroke(draw, [(0.5, 0.30), (0.5, 0.52), (0.66, 0.62)], size, width, color)


def _icon_log(draw: Any, size: float, width: float, color: Any) -> None:
    """Журнал: строки списка."""
    for offset in (0.26, 0.46, 0.66):
        _circle(draw, (0.22, offset), 0.045, size, width, color, fill=True)
        _stroke(draw, [(0.36, offset), (0.80, offset)], size, width, color)


def _icon_settings(draw: Any, size: float, width: float, color: Any) -> None:
    """Настройки: шестерня."""
    _circle(draw, (0.5, 0.5), 0.17, size, width, color)
    for index in range(8):
        angle = math.radians(index * 45)
        inner = 0.28
        outer = 0.40
        start = (0.5 + math.cos(angle) * inner, 0.5 + math.sin(angle) * inner)
        end = (0.5 + math.cos(angle) * outer, 0.5 + math.sin(angle) * outer)
        _stroke(draw, [start, end], size, width, color)


def _icon_search(draw: Any, size: float, width: float, color: Any) -> None:
    """Поиск: лупа."""
    _circle(draw, (0.44, 0.44), 0.26, size, width, color)
    _stroke(draw, [(0.63, 0.63), (0.84, 0.84)], size, width, color)


def _icon_folder(draw: Any, size: float, width: float, color: Any) -> None:
    """Папка."""
    _stroke(
        draw,
        [
            (0.12, 0.76),
            (0.12, 0.26),
            (0.42, 0.26),
            (0.50, 0.38),
            (0.88, 0.38),
            (0.88, 0.76),
            (0.12, 0.76),
        ],
        size,
        width,
        color,
    )


def _icon_excel(draw: Any, size: float, width: float, color: Any) -> None:
    """Файл таблицы."""
    _stroke(
        draw,
        [(0.24, 0.10), (0.60, 0.10), (0.78, 0.28), (0.78, 0.90), (0.24, 0.90), (0.24, 0.10)],
        size,
        width,
        color,
    )
    _stroke(draw, [(0.60, 0.10), (0.60, 0.28), (0.78, 0.28)], size, width, color)
    _stroke(draw, [(0.36, 0.48), (0.62, 0.76)], size, width, color)
    _stroke(draw, [(0.62, 0.48), (0.36, 0.76)], size, width, color)


def _icon_refresh(draw: Any, size: float, width: float, color: Any) -> None:
    """Обновление: круговая стрелка."""
    _arc(draw, (0.5, 0.5), 0.32, 300, 210, size, width, color)
    _polygon(draw, [(0.62, 0.10), (0.86, 0.22), (0.62, 0.34)], size, color)


def _icon_play(draw: Any, size: float, _width: float, color: Any) -> None:
    """Запуск: треугольник."""
    _polygon(draw, [(0.30, 0.18), (0.84, 0.50), (0.30, 0.82)], size, color)


def _icon_sun(draw: Any, size: float, width: float, color: Any) -> None:
    """Светлая тема: солнце."""
    _circle(draw, (0.5, 0.5), 0.20, size, width, color)
    for index in range(8):
        angle = math.radians(index * 45)
        start = (0.5 + math.cos(angle) * 0.30, 0.5 + math.sin(angle) * 0.30)
        end = (0.5 + math.cos(angle) * 0.42, 0.5 + math.sin(angle) * 0.42)
        _stroke(draw, [start, end], size, width, color)


def _icon_moon(draw: Any, size: float, width: float, color: Any) -> None:
    """Тёмная тема: месяц."""
    _arc(draw, (0.52, 0.50), 0.36, 40, 320, size, width, color)
    _arc(draw, (0.34, 0.50), 0.36, 300, 60, size, width, color)


def _icon_check(draw: Any, size: float, width: float, color: Any) -> None:
    """Успех: галочка."""
    _stroke(draw, [(0.20, 0.53), (0.42, 0.74), (0.80, 0.28)], size, width * 1.15, color)


def _icon_alert(draw: Any, size: float, width: float, color: Any) -> None:
    """Предупреждение: треугольник с восклицательным знаком."""
    _stroke(draw, [(0.50, 0.14), (0.90, 0.84), (0.10, 0.84), (0.50, 0.14)], size, width, color)
    _stroke(draw, [(0.50, 0.40), (0.50, 0.60)], size, width, color)
    _circle(draw, (0.50, 0.72), 0.045, size, width, color, fill=True)


def _icon_close(draw: Any, size: float, width: float, color: Any) -> None:
    """Закрытие: крестик."""
    _stroke(draw, [(0.24, 0.24), (0.76, 0.76)], size, width, color)
    _stroke(draw, [(0.76, 0.24), (0.24, 0.76)], size, width, color)


def _icon_chevron_right(draw: Any, size: float, width: float, color: Any) -> None:
    """Стрелка вправо."""
    _stroke(draw, [(0.40, 0.22), (0.66, 0.50), (0.40, 0.78)], size, width, color)


def _icon_chevron_down(draw: Any, size: float, width: float, color: Any) -> None:
    """Стрелка вниз."""
    _stroke(draw, [(0.24, 0.40), (0.50, 0.66), (0.76, 0.40)], size, width, color)


def _icon_download(draw: Any, size: float, width: float, color: Any) -> None:
    """Экспорт: стрелка вниз в лоток."""
    _stroke(draw, [(0.50, 0.14), (0.50, 0.62)], size, width, color)
    _stroke(draw, [(0.32, 0.46), (0.50, 0.64), (0.68, 0.46)], size, width, color)
    _stroke(draw, [(0.18, 0.80), (0.82, 0.80)], size, width, color)


def _icon_upload(draw: Any, size: float, width: float, color: Any) -> None:
    """Импорт: стрелка вверх."""
    _stroke(draw, [(0.50, 0.62), (0.50, 0.14)], size, width, color)
    _stroke(draw, [(0.32, 0.32), (0.50, 0.14), (0.68, 0.32)], size, width, color)
    _stroke(draw, [(0.18, 0.80), (0.82, 0.80)], size, width, color)


def _icon_external(draw: Any, size: float, width: float, color: Any) -> None:
    """Открыть во внешней программе."""
    _stroke(
        draw,
        [(0.46, 0.20), (0.20, 0.20), (0.20, 0.80), (0.80, 0.80), (0.80, 0.54)],
        size,
        width,
        color,
    )
    _stroke(draw, [(0.52, 0.48), (0.84, 0.16)], size, width, color)
    _stroke(draw, [(0.60, 0.16), (0.84, 0.16), (0.84, 0.40)], size, width, color)


def _icon_trash(draw: Any, size: float, width: float, color: Any) -> None:
    """Удаление: корзина."""
    _stroke(draw, [(0.18, 0.26), (0.82, 0.26)], size, width, color)
    _stroke(draw, [(0.40, 0.26), (0.40, 0.16), (0.60, 0.16), (0.60, 0.26)], size, width, color)
    _stroke(draw, [(0.26, 0.26), (0.30, 0.86), (0.70, 0.86), (0.74, 0.26)], size, width, color)
    _stroke(draw, [(0.44, 0.40), (0.44, 0.72)], size, width, color)
    _stroke(draw, [(0.56, 0.40), (0.56, 0.72)], size, width, color)


def _icon_plus(draw: Any, size: float, width: float, color: Any) -> None:
    """Добавление."""
    _stroke(draw, [(0.50, 0.20), (0.50, 0.80)], size, width, color)
    _stroke(draw, [(0.20, 0.50), (0.80, 0.50)], size, width, color)


def _icon_edit(draw: Any, size: float, width: float, color: Any) -> None:
    """Редактирование: карандаш."""
    _stroke(draw, [(0.18, 0.82), (0.28, 0.82), (0.72, 0.38)], size, width, color)
    _polygon(draw, [(0.72, 0.38), (0.82, 0.24), (0.90, 0.32), (0.80, 0.46)], size, color)
    _stroke(draw, [(0.16, 0.84), (0.22, 0.84)], size, width * 0.9, color)


def _icon_undo(draw: Any, size: float, width: float, color: Any) -> None:
    """Отмена последнего действия: стрелка против часовой стрелки."""
    _arc(draw, (0.5, 0.5), 0.32, 200, 340, size, width, color)
    _polygon(draw, [(0.24, 0.24), (0.16, 0.42), (0.36, 0.40)], size, color)


def _icon_database(draw: Any, size: float, width: float, color: Any) -> None:
    """База данных."""
    _arc(draw, (0.50, 0.24), 0.30, 0, 360, size, width, color)
    _stroke(draw, [(0.20, 0.24), (0.20, 0.74)], size, width, color)
    _stroke(draw, [(0.80, 0.24), (0.80, 0.74)], size, width, color)
    _arc(draw, (0.50, 0.74), 0.30, 0, 180, size, width, color)
    _arc(draw, (0.50, 0.49), 0.30, 0, 180, size, width, color)


def _icon_chart(draw: Any, size: float, width: float, color: Any) -> None:
    """Статистика: столбцы."""
    _stroke(draw, [(0.16, 0.84), (0.84, 0.84)], size, width, color)
    _stroke(draw, [(0.30, 0.84), (0.30, 0.56)], size, width * 1.4, color)
    _stroke(draw, [(0.50, 0.84), (0.50, 0.32)], size, width * 1.4, color)
    _stroke(draw, [(0.70, 0.84), (0.70, 0.46)], size, width * 1.4, color)


def _icon_info(draw: Any, size: float, width: float, color: Any) -> None:
    """Информация."""
    _circle(draw, (0.5, 0.5), 0.36, size, width, color)
    _circle(draw, (0.5, 0.32), 0.045, size, width, color, fill=True)
    _stroke(draw, [(0.50, 0.44), (0.50, 0.70)], size, width, color)


def _icon_eye(draw: Any, size: float, width: float, color: Any) -> None:
    """Просмотр."""
    _arc(draw, (0.50, 0.62), 0.36, 200, 340, size, width, color)
    _arc(draw, (0.50, 0.38), 0.36, 20, 160, size, width, color)
    _circle(draw, (0.50, 0.50), 0.12, size, width, color)


def _icon_copy(draw: Any, size: float, width: float, color: Any) -> None:
    """Копирование."""
    _rect(draw, (0.16, 0.16, 0.62, 0.62), size, width, color)
    _rect(draw, (0.38, 0.38, 0.84, 0.84), size, width, color)


def _icon_sparkles(draw: Any, size: float, _width: float, color: Any) -> None:
    """Искусственный интеллект: искры."""
    _polygon(
        draw,
        [
            (0.42, 0.14),
            (0.50, 0.36),
            (0.72, 0.44),
            (0.50, 0.52),
            (0.42, 0.74),
            (0.34, 0.52),
            (0.12, 0.44),
            (0.34, 0.36),
        ],
        size,
        color,
    )
    _polygon(
        draw,
        [
            (0.76, 0.58),
            (0.81, 0.70),
            (0.93, 0.75),
            (0.81, 0.80),
            (0.76, 0.92),
            (0.71, 0.80),
            (0.59, 0.75),
            (0.71, 0.70),
        ],
        size,
        color,
    )


def _icon_shield(draw: Any, size: float, width: float, color: Any) -> None:
    """Защита: щит."""
    _stroke(
        draw,
        [
            (0.50, 0.12),
            (0.82, 0.26),
            (0.82, 0.54),
            (0.50, 0.88),
            (0.18, 0.54),
            (0.18, 0.26),
            (0.50, 0.12),
        ],
        size,
        width,
        color,
    )


def _icon_filter(draw: Any, size: float, width: float, color: Any) -> None:
    """Фильтр."""
    _stroke(
        draw,
        [
            (0.14, 0.24),
            (0.86, 0.24),
            (0.58, 0.54),
            (0.58, 0.84),
            (0.42, 0.76),
            (0.42, 0.54),
            (0.14, 0.24),
        ],
        size,
        width,
        color,
    )


def _icon_pdf(draw: Any, size: float, width: float, color: Any) -> None:
    """Файл PDF."""
    _stroke(
        draw,
        [(0.24, 0.10), (0.60, 0.10), (0.78, 0.28), (0.78, 0.90), (0.24, 0.90), (0.24, 0.10)],
        size,
        width,
        color,
    )
    _stroke(draw, [(0.60, 0.10), (0.60, 0.28), (0.78, 0.28)], size, width, color)
    _stroke(
        draw,
        [(0.36, 0.72), (0.36, 0.46), (0.46, 0.46), (0.46, 0.58), (0.36, 0.58)],
        size,
        width,
        color,
    )
    _stroke(
        draw,
        [(0.56, 0.72), (0.56, 0.46), (0.66, 0.52), (0.66, 0.66), (0.56, 0.72)],
        size,
        width,
        color,
    )


#: Реестр иконок: имя → функция отрисовки.
ICONS: Final[dict[str, IconDrawer]] = {
    "dashboard": _icon_dashboard,
    "certificate": _icon_certificate,
    "alias": _icon_alias,
    "history": _icon_history,
    "log": _icon_log,
    "settings": _icon_settings,
    "search": _icon_search,
    "folder": _icon_folder,
    "excel": _icon_excel,
    "refresh": _icon_refresh,
    "play": _icon_play,
    "sun": _icon_sun,
    "moon": _icon_moon,
    "check": _icon_check,
    "alert": _icon_alert,
    "close": _icon_close,
    "chevron_right": _icon_chevron_right,
    "chevron_down": _icon_chevron_down,
    "download": _icon_download,
    "upload": _icon_upload,
    "external": _icon_external,
    "trash": _icon_trash,
    "plus": _icon_plus,
    "edit": _icon_edit,
    "undo": _icon_undo,
    "database": _icon_database,
    "chart": _icon_chart,
    "info": _icon_info,
    "eye": _icon_eye,
    "copy": _icon_copy,
    "sparkles": _icon_sparkles,
    "shield": _icon_shield,
    "filter": _icon_filter,
    "pdf": _icon_pdf,
}


class IconFactory:
    """Создаёт и кэширует иконки для интерфейса.

    Кэш обязателен: Tk удерживает ссылку на изображение только через объект
    Python, и потеря ссылки приводит к исчезновению иконки с экрана.
    """

    def __init__(self) -> None:
        """Создаёт пустую фабрику иконок."""
        self._cache: dict[tuple[str, int, str, str], Any] = {}

    def _render(self, name: str, size: int, color: str) -> Any:
        """Отрисовывает иконку в изображение Pillow."""
        from PIL import Image, ImageDraw

        drawer = ICONS.get(name)
        canvas_size = size * _SUPERSAMPLE
        image = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
        if drawer is None:
            _LOGGER.debug("Иконка «%s» не найдена", name)
            return image.resize((size, size), Image.Resampling.LANCZOS)

        draw = ImageDraw.Draw(image)
        stroke_width = max(1.0, canvas_size * _STROKE_RATIO)
        try:
            drawer(draw, float(canvas_size), stroke_width, color)
        except Exception:
            _LOGGER.debug("Ошибка отрисовки иконки «%s»", name, exc_info=True)
        return image.resize((size, size), Image.Resampling.LANCZOS)

    def render_image(self, name: str, size: int, color: str) -> Any:
        """Отрисовывает иконку как изображение Pillow.

        Нужен для случаев, когда требуется не ``CTkImage``, а исходный растр:
        иконка окна, экспорт, системный трей.

        Args:
            name: Имя иконки.
            size: Размер в пикселях.
            color: Цвет штриха.

        Returns:
            Изображение ``PIL.Image.Image``.
        """
        return self._render(name, size, color)

    def get(
        self,
        name: str,
        size: int = 20,
        *,
        light_color: str = "#12161B",
        dark_color: str = "#EEF1F5",
    ) -> Any:
        """Возвращает иконку, готовую к использованию в виджете.

        Args:
            name: Имя иконки из :data:`ICONS`.
            size: Размер в пикселях.
            light_color: Цвет штриха для светлой темы.
            dark_color: Цвет штриха для тёмной темы.

        Returns:
            Экземпляр ``customtkinter.CTkImage``.
        """
        import customtkinter as ctk

        key = (name, size, light_color, dark_color)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        image = ctk.CTkImage(
            light_image=self._render(name, size, light_color),
            dark_image=self._render(name, size, dark_color),
            size=(size, size),
        )
        self._cache[key] = image
        return image

    def accent(self, name: str, theme: Any, size: int = 20) -> Any:
        """Возвращает иконку акцентного цвета.

        Args:
            name: Имя иконки.
            theme: Активная тема оформления.
            size: Размер в пикселях.

        Returns:
            Экземпляр ``customtkinter.CTkImage``.
        """
        light, dark = theme.color("accent")
        return self.get(name, size, light_color=light, dark_color=dark)

    def colored(self, name: str, theme: Any, role: str, size: int = 20) -> Any:
        """Возвращает иконку цвета указанной роли палитры.

        Args:
            name: Имя иконки.
            theme: Активная тема оформления.
            role: Имя цвета в палитре (``text``, ``danger``, ``success``…).
            size: Размер в пикселях.

        Returns:
            Экземпляр ``customtkinter.CTkImage``.
        """
        light, dark = theme.color(role)
        return self.get(name, size, light_color=light, dark_color=dark)

    def clear(self) -> None:
        """Очищает кэш (после смены палитры)."""
        self._cache.clear()


#: Единственный экземпляр фабрики на приложение.
icons: Final[IconFactory] = IconFactory()
