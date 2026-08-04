"""Поддержка перетаскивания файлов из проводника.

Tkinter не поддерживает приём файлов из системного проводника штатно —
требуется расширение ``tkdnd``, доступное через пакет ``tkinterdnd2``.
Пакет необязателен: при его отсутствии зоны приёма продолжают работать как
кнопки выбора файла, и пользователь не теряет ни одной возможности.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)

#: Событие приёма файлов, определяемое расширением tkdnd.
DND_FILES = "DND_Files"
DROP_EVENT = "<<Drop>>"
DROP_ENTER_EVENT = "<<DropEnter>>"
DROP_LEAVE_EVENT = "<<DropLeave>>"

#: Пути в событии tkdnd разделены пробелами, а содержащие пробелы —
#: заключены в фигурные скобки.
_RE_PATHS = re.compile(r"\{([^}]*)\}|(\S+)")

_available: bool | None = None


def is_available() -> bool:
    """Проверяет доступность расширения перетаскивания.

    Returns:
        ``True``, если ``tkinterdnd2`` установлен.
    """
    global _available
    if _available is None:
        try:
            import importlib.util

            _available = importlib.util.find_spec("tkinterdnd2") is not None
        except (ImportError, ValueError):  # pragma: no cover
            _available = False
    return bool(_available)


def parse_drop_paths(raw: str) -> list[Path]:
    """Разбирает список путей из события перетаскивания.

    Args:
        raw: Значение ``event.data``.

    Returns:
        Список существующих путей.
    """
    if not raw:
        return []
    paths: list[Path] = []
    for braced, plain in _RE_PATHS.findall(raw):
        value = (braced or plain).strip()
        if not value:
            continue
        candidate = Path(value)
        if candidate.exists():
            paths.append(candidate)
    return paths


def enable_dnd(root: Any) -> bool:
    """Подключает расширение перетаскивания к корневому окну.

    Вызывается один раз после создания окна. Библиотека ``tkinterdnd2``
    предоставляет собственный класс окна, но подмешивание расширения к уже
    созданному окну ``CTk`` работает надёжнее и не конфликтует с
    CustomTkinter.

    Args:
        root: Корневое окно приложения.

    Returns:
        ``True``, если перетаскивание доступно.
    """
    if not is_available():
        return False
    try:
        from tkinterdnd2 import TkinterDnD

        root.tk.eval("package require tkdnd")
        root.TkdndVersion = TkinterDnD._require(root)
    except Exception as error:
        _LOGGER.info("Перетаскивание файлов недоступно: %s", error)
        return False

    _LOGGER.debug("Перетаскивание файлов подключено")
    return True


def register_drop_target(
    widget: Any,
    on_drop: Callable[[list[Path]], None],
    *,
    on_enter: Callable[[], None] | None = None,
    on_leave: Callable[[], None] | None = None,
    extensions: Iterable[str] = (),
) -> bool:
    """Делает виджет приёмником перетаскиваемых файлов.

    Args:
        widget: Виджет-приёмник.
        on_drop: Вызывается со списком принятых путей.
        on_enter: Вызывается при наведении перетаскиваемого файла.
        on_leave: Вызывается при уходе курсора.
        extensions: Допустимые расширения (пусто — любые).

    Returns:
        ``True``, если приёмник зарегистрирован.
    """
    if not is_available():
        return False

    allowed = {extension.lower() for extension in extensions}

    def _handle_drop(event: Any) -> str:
        paths = parse_drop_paths(getattr(event, "data", ""))
        if allowed:
            paths = [path for path in paths if path.suffix.lower() in allowed or path.is_dir()]
        if on_leave is not None:
            on_leave()
        if paths:
            try:
                on_drop(paths)
            except Exception:
                _LOGGER.exception("Ошибка обработки перетаскивания")
        return "break"

    def _handle_enter(_: Any) -> str:
        if on_enter is not None:
            on_enter()
        return "break"

    def _handle_leave(_: Any) -> str:
        if on_leave is not None:
            on_leave()
        return "break"

    try:
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind(DROP_EVENT, _handle_drop)
        widget.dnd_bind(DROP_ENTER_EVENT, _handle_enter)
        widget.dnd_bind(DROP_LEAVE_EVENT, _handle_leave)
    except Exception as error:
        _LOGGER.debug("Не удалось зарегистрировать приёмник перетаскивания: %s", error)
        return False
    return True
