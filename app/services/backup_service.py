"""Резервное копирование и обслуживание базы данных.

Накопленные псевдонимы — это результат месяцев ручной работы оператора, и их
потеря недопустима. Поэтому копия создаётся автоматически при запуске (не чаще
одного раза в сутки), а также по требованию пользователя.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from app.core.exceptions import DatabaseError
from app.database.connection import Database
from app.repositories.settings_repository import KEY_LAST_BACKUP_AT, SettingsRepository

_LOGGER = logging.getLogger(__name__)

#: Шаблон имени файла резервной копии.
BACKUP_NAME_TEMPLATE = "certmatcher-%Y%m%d-%H%M%S.db"


@dataclass(frozen=True, slots=True)
class BackupInfo:
    """Сведения о файле резервной копии.

    Attributes:
        path: Путь к файлу.
        created_at: Дата и время создания.
        size_bytes: Размер файла.
    """

    path: Path
    created_at: datetime
    size_bytes: int

    @property
    def display_name(self) -> str:
        """Имя копии для отображения в интерфейсе."""
        return f"{self.created_at:%d.%m.%Y %H:%M} · {self.size_bytes / 1024 / 1024:.1f} МБ"


class BackupService:
    """Создаёт, перечисляет и восстанавливает резервные копии базы."""

    def __init__(
        self,
        database: Database,
        backup_dir: Path,
        settings_repository: SettingsRepository,
        *,
        retention: int = 10,
    ) -> None:
        """Создаёт сервис резервного копирования.

        Args:
            database: Менеджер базы данных.
            backup_dir: Каталог хранения копий.
            settings_repository: Служебное состояние (время последней копии).
            retention: Сколько копий хранить.
        """
        self._database = database
        self._backup_dir = backup_dir
        self._state = settings_repository
        self._retention = max(1, retention)

    @property
    def directory(self) -> Path:
        """Каталог хранения резервных копий."""
        return self._backup_dir

    def create(self, *, reason: str = "manual") -> BackupInfo:
        """Создаёт резервную копию базы данных.

        Args:
            reason: Причина создания (попадает в журнал).

        Returns:
            Сведения о созданной копии.

        Raises:
            DatabaseError: Если копию создать не удалось.
        """
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        target = self._backup_dir / datetime.now().strftime(BACKUP_NAME_TEMPLATE)
        self._database.checkpoint()
        self._database.backup_to(target)
        self._state.set_now(KEY_LAST_BACKUP_AT)
        self.prune()

        stat = target.stat()
        _LOGGER.info("Резервная копия создана (%s): %s", reason, target.name)
        return BackupInfo(
            path=target,
            created_at=datetime.fromtimestamp(stat.st_mtime),
            size_bytes=stat.st_size,
        )

    def create_if_due(self, *, interval_hours: int = 24) -> BackupInfo | None:
        """Создаёт копию, если с прошлой прошло достаточно времени.

        Args:
            interval_hours: Минимальный интервал между копиями.

        Returns:
            Сведения о созданной копии либо ``None``, если копия не нужна.
        """
        last = self._state.get_datetime(KEY_LAST_BACKUP_AT)
        if last is not None and datetime.now() - last < timedelta(hours=interval_hours):
            return None
        try:
            return self.create(reason="auto")
        except DatabaseError as error:
            _LOGGER.warning("Автоматическая резервная копия не создана: %s", error.message)
            return None

    def list_backups(self) -> list[BackupInfo]:
        """Возвращает список доступных копий.

        Returns:
            Копии, отсортированные от новых к старым.
        """
        if not self._backup_dir.exists():
            return []
        items: list[BackupInfo] = []
        for path in self._backup_dir.glob("*.db"):
            try:
                stat = path.stat()
            except OSError:  # pragma: no cover
                continue
            items.append(
                BackupInfo(
                    path=path,
                    created_at=datetime.fromtimestamp(stat.st_mtime),
                    size_bytes=stat.st_size,
                )
            )
        items.sort(key=lambda item: item.created_at, reverse=True)
        return items

    def restore(self, backup: Path) -> None:
        """Восстанавливает базу из резервной копии.

        Args:
            backup: Путь к файлу копии.

        Raises:
            DatabaseError: Если копия повреждена или недоступна.
        """
        self._database.restore_from(backup)
        _LOGGER.info("База восстановлена из копии %s", backup.name)

    def prune(self) -> int:
        """Удаляет копии сверх установленного лимита хранения.

        Returns:
            Количество удалённых файлов.
        """
        backups = self.list_backups()
        excess = backups[self._retention :]
        removed = 0
        for item in excess:
            try:
                item.path.unlink()
                removed += 1
            except OSError:  # pragma: no cover
                continue
        if removed:
            _LOGGER.debug("Удалено устаревших резервных копий: %s", removed)
        return removed

    def last_backup_at(self) -> datetime | None:
        """Возвращает время последней резервной копии.

        Returns:
            Дата и время либо ``None``.
        """
        return self._state.get_datetime(KEY_LAST_BACKUP_AT)
