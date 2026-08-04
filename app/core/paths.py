r"""Определение путей приложения для установленного и портативного режимов.

Приложение поставляется одним EXE и должно корректно работать в двух сценариях,
типичных для корпоративной среды:

1. **Портативный режим** — EXE лежит в сетевой или локальной папке, рядом с ним
   создаются ``data``/``logs``/``cache``. Включается наличием файла
   ``portable.flag`` рядом с EXE либо автоматически, если каталог доступен на
   запись.
2. **Установленный режим** — каталог программы защищён от записи (Program
   Files), данные размещаются в ``%LOCALAPPDATA%\BaltonCertMatcher``.

Все каталоги создаются лениво, один раз, при первом обращении.
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from app.core.constants import (
    APP_SLUG,
    DATABASE_FILENAME,
    ERROR_LOG_FILENAME,
    LOG_FILENAME,
    PORTABLE_MARKER,
    SETTINGS_FILENAME,
    WINDOW_STATE_FILENAME,
)


def is_frozen() -> bool:
    """Сообщает, запущено ли приложение из собранного PyInstaller EXE.

    Returns:
        ``True`` для собранного приложения, ``False`` при запуске из исходников.
    """
    return bool(getattr(sys, "frozen", False))


def executable_dir() -> Path:
    """Возвращает каталог исполняемого файла (или корень проекта в dev-режиме).

    Returns:
        Абсолютный путь к каталогу.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def bundled_resources_dir() -> Path:
    """Возвращает каталог ресурсов, вшитых в сборку.

    В собранном приложении PyInstaller распаковывает ресурсы во временный
    каталог ``sys._MEIPASS``.

    Returns:
        Путь к каталогу ``resources``.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "app" / "resources"
    return Path(__file__).resolve().parents[1] / "resources"


def _is_writable(directory: Path) -> bool:
    """Проверяет фактическую возможность записи в каталог."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".write-probe-", delete=True):
            return True
    except OSError:
        return False


def _user_data_root() -> Path:
    """Возвращает пользовательский каталог данных, специфичный для платформы."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / APP_SLUG
        return Path.home() / "AppData" / "Local" / APP_SLUG
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_SLUG
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_SLUG


@dataclass(frozen=True, slots=True)
class AppPaths:
    """Набор путей приложения.

    Attributes:
        base: Корневой каталог данных приложения.
        portable: Признак портативного размещения (данные рядом с EXE).
    """

    base: Path
    portable: bool = False
    _created: set[Path] = field(default_factory=set, repr=False, compare=False)

    # ---------------------------------------------------------------- фабрика
    @classmethod
    def resolve(cls, override: Path | str | None = None) -> AppPaths:
        """Определяет расположение данных приложения.

        Args:
            override: Явно заданный корневой каталог (аргумент командной строки
                ``--data-dir``); имеет наивысший приоритет.

        Returns:
            Готовый экземпляр :class:`AppPaths`.
        """
        if override is not None:
            return cls(base=Path(override).expanduser().resolve(), portable=True)

        exe_dir = executable_dir()
        marker = exe_dir / PORTABLE_MARKER
        if marker.exists() and _is_writable(exe_dir):
            return cls(base=exe_dir, portable=True)

        if not is_frozen():
            # В режиме разработки данные держим внутри проекта — так удобнее
            # отлаживать и не засорять систему.
            return cls(base=exe_dir, portable=True)

        if _is_writable(exe_dir / "data"):
            return cls(base=exe_dir, portable=True)

        return cls(base=_user_data_root(), portable=False)

    # ---------------------------------------------------------------- каталоги
    def _ensure(self, path: Path) -> Path:
        """Создаёт каталог при первом обращении и возвращает его путь."""
        if path not in self._created:
            path.mkdir(parents=True, exist_ok=True)
            self._created.add(path)
        return path

    @property
    def data_dir(self) -> Path:
        """Каталог базы данных и пользовательских настроек."""
        return self._ensure(self.base / "data")

    @property
    def logs_dir(self) -> Path:
        """Каталог журналов работы."""
        return self._ensure(self.base / "logs")

    @property
    def cache_dir(self) -> Path:
        """Каталог кэша (эмбеддинги, миниатюры PDF)."""
        return self._ensure(self.base / "cache")

    @property
    def output_dir(self) -> Path:
        """Каталог результатов обработки заказов по умолчанию."""
        return self._ensure(self.base / "output")

    @property
    def backup_dir(self) -> Path:
        """Каталог резервных копий базы данных."""
        return self._ensure(self.base / "backups")

    @property
    def models_dir(self) -> Path:
        """Каталог локально сохранённых ML-моделей."""
        return self._ensure(self.cache_dir / "models")

    @property
    def config_dir(self) -> Path:
        """Каталог файлов конфигурации."""
        return self._ensure(self.base / "config")

    # ------------------------------------------------------------------ файлы
    @property
    def database_file(self) -> Path:
        """Путь к файлу базы SQLite."""
        return self.data_dir / DATABASE_FILENAME

    @property
    def settings_file(self) -> Path:
        """Путь к файлу пользовательских настроек."""
        return self.config_dir / SETTINGS_FILENAME

    @property
    def window_state_file(self) -> Path:
        """Путь к файлу сохранённого состояния окна."""
        return self.config_dir / WINDOW_STATE_FILENAME

    @property
    def log_file(self) -> Path:
        """Путь к основному файлу журнала."""
        return self.logs_dir / LOG_FILENAME

    @property
    def error_log_file(self) -> Path:
        """Путь к файлу журнала ошибок."""
        return self.logs_dir / ERROR_LOG_FILENAME

    @property
    def resources_dir(self) -> Path:
        """Путь к каталогу встроенных ресурсов."""
        return bundled_resources_dir()

    def describe(self) -> dict[str, str]:
        """Возвращает сводку путей для диагностики и окна «О программе».

        Returns:
            Отображение «человекочитаемое имя → путь».
        """
        return {
            "Режим": "портативный" if self.portable else "установленный",
            "Данные": str(self.data_dir),
            "База данных": str(self.database_file),
            "Журналы": str(self.logs_dir),
            "Кэш": str(self.cache_dir),
            "Результаты": str(self.output_dir),
            "Резервные копии": str(self.backup_dir),
            "Настройки": str(self.settings_file),
        }
