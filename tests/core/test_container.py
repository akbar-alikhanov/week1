"""Тесты жизненного цикла контейнера зависимостей."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.container import ApplicationContainer
from app.core.exceptions import DatabaseError


class TestShutdown:
    """Проверки идемпотентности завершения работы приложения.

    Регрессия: в реальном приложении ``shutdown()`` вызывается дважды за
    одно закрытие — сначала из ``ApplicationWindow.on_close()``, затем
    повторно из ``finally`` в ``app.main.run_gui_mode()`` (второй вызов —
    подстраховка на случай, если окно было уничтожено в обход
    ``on_close()``). Второй вызов обязан быть безопасным безусловно.
    """

    def test_shutdown_is_idempotent(self, tmp_path: Path) -> None:
        """Повторный вызов shutdown() не бросает исключений."""
        container = ApplicationContainer.create(data_dir=tmp_path, configure_logs=False)
        container.startup()

        container.shutdown()
        container.shutdown()

    def test_shutdown_without_startup_is_safe(self, tmp_path: Path) -> None:
        """shutdown() без предшествующего startup() не трогает несозданные ресурсы.

        Например, если инициализация упала раньше, чем создалась база
        данных, — shutdown() в обработчике этой ошибки не должен упасть ещё
        раз поверх исходной проблемы.
        """
        container = ApplicationContainer.create(data_dir=tmp_path, configure_logs=False)

        container.shutdown()

    def test_shutdown_actually_closes_database(self, tmp_path: Path) -> None:
        """После shutdown() соединение с базой действительно закрыто."""
        container = ApplicationContainer.create(data_dir=tmp_path, configure_logs=False)
        container.startup()
        database = container.database

        container.shutdown()

        with pytest.raises(DatabaseError):
            _ = database.connection

    def test_triple_shutdown_is_safe(self, tmp_path: Path) -> None:
        """Более двух вызовов подряд тоже не должны бросать исключений."""
        container = ApplicationContainer.create(data_dir=tmp_path, configure_logs=False)
        container.startup()

        container.shutdown()
        container.shutdown()
        container.shutdown()
