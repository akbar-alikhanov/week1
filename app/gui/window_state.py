"""Сохранение и восстановление состояния окна.

Пользователь настраивает окно один раз: размер, положение, раскрытость боковой
панели, активный раздел. Терять эти настройки при каждом запуске недопустимо
для программы, которую открывают ежедневно.

Отдельное внимание уделено защите от «потерянного окна»: если конфигурация
мониторов изменилась (ноутбук отключили от док-станции), сохранённые
координаты могут оказаться за пределами видимой области — в этом случае окно
центрируется на основном экране.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.gui.theme import Sizes

_LOGGER = logging.getLogger(__name__)

_RE_GEOMETRY = re.compile(r"^(?P<w>\d+)x(?P<h>\d+)(?:\+(?P<x>-?\d+)\+(?P<y>-?\d+))?$")


@dataclass(slots=True)
class WindowState:
    """Сохраняемое состояние главного окна.

    Attributes:
        width: Ширина окна.
        height: Высота окна.
        x: Координата левого края.
        y: Координата верхнего края.
        maximized: Признак развёрнутого окна.
        sidebar_expanded: Раскрыта ли боковая панель.
        active_view: Идентификатор активного раздела.
    """

    width: int = Sizes.DEFAULT_WINDOW[0]
    height: int = Sizes.DEFAULT_WINDOW[1]
    x: int | None = None
    y: int | None = None
    maximized: bool = False
    sidebar_expanded: bool = True
    active_view: str = "dashboard"

    def geometry(self) -> str:
        """Формирует строку геометрии для Tk.

        Returns:
            Строка вида ``1360x860+120+60``.
        """
        if self.x is None or self.y is None:
            return f"{self.width}x{self.height}"
        return f"{self.width}x{self.height}+{self.x}+{self.y}"


class WindowStateStore:
    """Читает и записывает состояние окна в JSON-файл."""

    def __init__(self, path: Path) -> None:
        """Создаёт хранилище состояния.

        Args:
            path: Путь к файлу состояния.
        """
        self._path = path

    def load(self) -> WindowState:
        """Читает сохранённое состояние.

        Returns:
            Состояние окна; значения по умолчанию при отсутствии файла.
        """
        if not self._path.exists():
            return WindowState()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            _LOGGER.debug("Состояние окна не прочитано: %s", error)
            return WindowState()

        state = WindowState()
        for key, value in data.items():
            if hasattr(state, key):
                try:
                    setattr(state, key, value)
                except (TypeError, ValueError):  # pragma: no cover
                    continue
        return state

    def save(self, state: WindowState) -> None:
        """Сохраняет состояние окна.

        Args:
            state: Сохраняемое состояние.
        """
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(asdict(state), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as error:  # pragma: no cover — диск может быть недоступен
            _LOGGER.debug("Состояние окна не сохранено: %s", error)

    def capture(self, window: Any, *, sidebar_expanded: bool, active_view: str) -> WindowState:
        """Считывает текущее состояние окна.

        Args:
            window: Главное окно приложения.
            sidebar_expanded: Раскрыта ли боковая панель.
            active_view: Идентификатор активного раздела.

        Returns:
            Состояние, пригодное для сохранения.
        """
        state = WindowState(sidebar_expanded=sidebar_expanded, active_view=active_view)
        try:
            state.maximized = window.state() == "zoomed"
        except Exception:
            state.maximized = False

        try:
            match = _RE_GEOMETRY.match(window.geometry())
        except Exception:
            return state

        if match is None:
            return state

        # У развёрнутого окна геометрия равна размеру экрана — сохранять её
        # бессмысленно: при восстановлении окно должно вернуться к обычному
        # размеру, а признак развёрнутости хранится отдельно.
        if not state.maximized:
            state.width = int(match.group("w"))
            state.height = int(match.group("h"))
            if match.group("x") is not None:
                state.x = int(match.group("x"))
                state.y = int(match.group("y"))
        return state

    def apply(self, window: Any, state: WindowState) -> None:
        """Применяет состояние к окну с проверкой видимости.

        Args:
            window: Главное окно приложения.
            state: Восстанавливаемое состояние.
        """
        minimum = Sizes.MIN_WINDOW
        width = max(minimum[0], state.width)
        height = max(minimum[1], state.height)

        try:
            screen_width = window.winfo_screenwidth()
            screen_height = window.winfo_screenheight()
        except Exception:
            window.geometry(f"{width}x{height}")
            return

        width = min(width, screen_width)
        height = min(height, screen_height)

        x, y = state.x, state.y
        visible = (
            x is not None
            and y is not None
            and -50 <= x <= screen_width - 200
            and -20 <= y <= screen_height - 150
        )
        if not visible:
            x = max(0, (screen_width - width) // 2)
            y = max(0, (screen_height - height) // 3)
            _LOGGER.debug("Сохранённое положение окна вне экрана — окно центрировано")

        window.geometry(f"{width}x{height}+{x}+{y}")
        if state.maximized:
            try:
                window.after(60, lambda: window.state("zoomed"))
            except Exception:
                pass
