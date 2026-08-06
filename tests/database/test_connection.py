"""Тесты жизненного цикла соединений с базой данных."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.exceptions import DatabaseError
from app.database.connection import Database


class TestClose:
    """Проверки закрытия соединений."""

    def test_close_is_idempotent(self, tmp_path: Path) -> None:
        """Повторный вызов close() не бросает исключений."""
        database = Database(tmp_path / "test.db")
        database.initialize()

        database.close()
        database.close()

    def test_connection_raises_after_close(self, tmp_path: Path) -> None:
        """Обращение к соединению после close() — ожидаемая, а не тихая ошибка.

        В отличие от checkpoint() (см. TestCheckpoint ниже), это осознанная
        защита: обычный код репозиториев не должен молча продолжать работать
        с закрытой базой — такую ошибку важно увидеть, а не проглотить.
        """
        database = Database(tmp_path / "test.db")
        database.initialize()
        database.close()

        with pytest.raises(DatabaseError):
            _ = database.connection


class TestCheckpoint:
    """Регрессия: checkpoint() после close() не должен бросать исключений.

    Раньше ``ApplicationContainer.shutdown()`` вызывался дважды за одно
    закрытие приложения (из ``ApplicationWindow.on_close()`` и повторно из
    ``finally`` в ``app.main.run_gui_mode()``): второй вызов вызывал
    ``checkpoint()`` уже после того, как первый вызов закрыл соединение, и
    падал с ``DatabaseError: База данных закрыта`` прямо на выходе из
    приложения.
    """

    def test_checkpoint_before_close_works(self, tmp_path: Path) -> None:
        """В штатной работе checkpoint() не бросает исключений."""
        database = Database(tmp_path / "test.db")
        database.initialize()

        database.checkpoint()
        database.close()

    def test_checkpoint_after_close_is_a_safe_no_op(self, tmp_path: Path) -> None:
        """checkpoint(), вызванный после close(), тихо ничего не делает."""
        database = Database(tmp_path / "test.db")
        database.initialize()
        database.close()

        database.checkpoint()

    def test_checkpoint_close_checkpoint_close_is_safe(self, tmp_path: Path) -> None:
        """Точный сценарий двойного shutdown(): checkpoint→close, затем снова."""
        database = Database(tmp_path / "test.db")
        database.initialize()

        database.checkpoint()
        database.close()
        database.checkpoint()
        database.close()
