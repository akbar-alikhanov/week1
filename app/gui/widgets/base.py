"""Общие помощники для виджетов интерфейса."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from typing import Any

_LOGGER = logging.getLogger(__name__)


def iter_descendants(widget: Any) -> Iterator[Any]:
    """Перебирает виджет и всех его потомков.

    Args:
        widget: Корневой виджет.

    Yields:
        Виджеты дерева, включая исходный.
    """
    yield widget
    try:
        children = widget.winfo_children()
    except Exception:
        return
    for child in children:
        yield from iter_descendants(child)


def bind_recursive(widget: Any, sequence: str, handler: Callable[[Any], Any]) -> None:
    """Привязывает обработчик к виджету и всем его потомкам.

    Композитные виджеты CustomTkinter состоят из нескольких элементов Tk,
    и события мыши получает верхний из них. Чтобы карточка целиком
    реагировала на наведение и щелчок, обработчик вешается на всё поддерево.

    Args:
        widget: Корневой виджет.
        sequence: Последовательность событий Tk (например, ``"<Button-1>"``).
        handler: Обработчик события.
    """
    for item in iter_descendants(widget):
        try:
            item.bind(sequence, handler, add="+")
        except Exception:
            continue


def set_cursor(widget: Any, cursor: str = "hand2") -> None:
    """Устанавливает вид курсора для виджета и его потомков.

    Args:
        widget: Корневой виджет.
        cursor: Имя курсора Tk.
    """
    for item in iter_descendants(widget):
        try:
            item.configure(cursor=cursor)
        except Exception:
            continue


def safe_destroy(widget: Any) -> None:
    """Уничтожает виджет, подавляя ошибки уже разрушенного дерева.

    Args:
        widget: Уничтожаемый виджет.
    """
    try:
        widget.destroy()
    except Exception:
        pass


def clear_children(widget: Any) -> None:
    """Удаляет всех потомков виджета.

    Args:
        widget: Контейнер.
    """
    try:
        children = widget.winfo_children()
    except Exception:
        return
    for child in children:
        safe_destroy(child)


def center_on_parent(window: Any, parent: Any, width: int, height: int) -> None:
    """Центрирует окно относительно родительского.

    Args:
        window: Позиционируемое окно.
        parent: Родительское окно.
        width: Ширина окна.
        height: Высота окна.
    """
    try:
        parent.update_idletasks()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        x = parent_x + max(0, (parent_width - width) // 2)
        y = parent_y + max(0, (parent_height - height) // 3)
        window.geometry(f"{width}x{height}+{x}+{y}")
    except Exception:
        window.geometry(f"{width}x{height}")


def format_bytes(value: int) -> str:
    """Форматирует размер в байтах для отображения.

    Args:
        value: Размер в байтах.

    Returns:
        Строка вида ``12,4 МБ``.
    """
    size = float(value)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if size < 1024 or unit == "ГБ":
            formatted = f"{size:.1f}".rstrip("0").rstrip(".")
            return f"{formatted.replace('.', ',')} {unit}"
        size /= 1024
    return f"{value} Б"


def format_duration(seconds: float) -> str:
    """Форматирует длительность для отображения.

    Args:
        seconds: Длительность в секундах.

    Returns:
        Строка вида ``1 мин 20 с`` либо ``0,8 с``.
    """
    if seconds < 1:
        return f"{seconds:.1f} с".replace(".", ",")
    if seconds < 60:
        return f"{seconds:.1f} с".replace(".", ",")
    minutes, remainder = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes} мин {remainder} с"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} ч {minutes} мин"
