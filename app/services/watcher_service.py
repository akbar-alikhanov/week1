"""Фоновое наблюдение за папкой сертификатов.

Новые сертификаты появляются в общей папке постоянно. Требовать от оператора
нажимать «Переиндексировать» — значит гарантировать, что рано или поздно он
этого не сделает и получит «сертификат не найден» на актуальный товар.

Наблюдатель устраняет проблему: изменения в папке подхватываются автоматически
с задержкой в пару секунд (события файловой системы приходят пачками, пока
файл копируется, поэтому обработка обязательно откладывается).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from app.core.concurrency import Debouncer
from app.core.constants import PDF_EXTENSIONS
from app.services.indexing_service import IndexingService

_LOGGER = logging.getLogger(__name__)


class CertificateWatcher:
    """Следит за папкой сертификатов и индексирует изменения.

    При отсутствии пакета ``watchdog`` наблюдение просто не запускается —
    приложение остаётся полностью работоспособным.
    """

    def __init__(
        self,
        indexing_service: IndexingService,
        *,
        debounce_seconds: float = 2.0,
        on_change: Callable[[int, int], None] | None = None,
    ) -> None:
        """Создаёт наблюдателя.

        Args:
            indexing_service: Сервис индексации.
            debounce_seconds: Пауза после последнего события перед обработкой.
            on_change: Обратный вызов ``(добавлено, удалено)`` после обработки.
        """
        self._indexing = indexing_service
        self._debounce_seconds = debounce_seconds
        self._on_change = on_change
        self._observer: object | None = None
        self._directory: Path | None = None
        self._pending_changes: set[Path] = set()
        self._pending_deletions: set[Path] = set()
        self._lock = threading.Lock()
        self._debouncer = Debouncer(debounce_seconds, self._flush)

    # --------------------------------------------------------------- свойства
    @property
    def is_running(self) -> bool:
        """Признак активного наблюдения."""
        return self._observer is not None

    @property
    def directory(self) -> Path | None:
        """Папка, за которой ведётся наблюдение."""
        return self._directory

    @staticmethod
    def available() -> bool:
        """Проверяет наличие пакета ``watchdog``.

        Returns:
            ``True``, если наблюдение поддерживается.
        """
        try:
            import importlib.util

            return importlib.util.find_spec("watchdog") is not None
        except (ImportError, ValueError):  # pragma: no cover
            return False

    # ------------------------------------------------------------ управление
    def start(self, directory: Path, *, recursive: bool = True) -> bool:
        """Запускает наблюдение за папкой.

        Args:
            directory: Папка сертификатов.
            recursive: Следить ли за вложенными папками.

        Returns:
            ``True``, если наблюдение запущено.
        """
        if not directory.exists() or not directory.is_dir():
            _LOGGER.debug("Наблюдение не запущено: папка %s недоступна", directory)
            return False

        if self.is_running and self._directory == directory:
            return True

        self.stop()

        try:
            from watchdog.events import FileSystemEvent, FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:
            _LOGGER.info("Пакет watchdog не установлен — автообновление папки выключено")
            return False

        watcher = self

        class _Handler(FileSystemEventHandler):
            """Преобразует события файловой системы в задания индексации."""

            def on_created(self, event: FileSystemEvent) -> None:
                watcher._enqueue_change(event)

            def on_modified(self, event: FileSystemEvent) -> None:
                watcher._enqueue_change(event)

            def on_moved(self, event: FileSystemEvent) -> None:
                watcher._enqueue_deletion(getattr(event, "src_path", ""))
                watcher._enqueue_path(getattr(event, "dest_path", ""))

            def on_deleted(self, event: FileSystemEvent) -> None:
                watcher._enqueue_deletion(getattr(event, "src_path", ""))

        try:
            observer = Observer()
            observer.schedule(_Handler(), str(directory), recursive=recursive)
            observer.daemon = True
            observer.start()
        except Exception as error:
            _LOGGER.warning("Не удалось запустить наблюдение за %s: %s", directory, error)
            return False

        self._observer = observer
        self._directory = directory
        _LOGGER.info("Запущено наблюдение за папкой сертификатов: %s", directory)
        return True

    def stop(self) -> None:
        """Останавливает наблюдение и отменяет отложенную обработку."""
        self._debouncer.cancel()
        observer = self._observer
        self._observer = None
        self._directory = None
        if observer is None:
            return
        try:
            observer.stop()  # type: ignore[attr-defined]
            observer.join(timeout=3)  # type: ignore[attr-defined]
        except Exception:
            _LOGGER.debug("Наблюдатель остановлен с ошибкой", exc_info=True)
        _LOGGER.info("Наблюдение за папкой сертификатов остановлено")

    # -------------------------------------------------------------- события
    def _enqueue_change(self, event: object) -> None:
        """Ставит файл в очередь на индексацию."""
        if getattr(event, "is_directory", False):
            return
        self._enqueue_path(getattr(event, "src_path", ""))

    def _enqueue_path(self, raw_path: str) -> None:
        """Добавляет путь в очередь изменений, если это PDF."""
        if not raw_path:
            return
        path = Path(raw_path)
        if path.suffix.lower() not in PDF_EXTENSIONS:
            return
        with self._lock:
            self._pending_changes.add(path)
            self._pending_deletions.discard(path)
        self._debouncer.trigger()

    def _enqueue_deletion(self, raw_path: str) -> None:
        """Добавляет путь в очередь удалений."""
        if not raw_path:
            return
        path = Path(raw_path)
        if path.suffix.lower() not in PDF_EXTENSIONS:
            return
        with self._lock:
            self._pending_deletions.add(path)
            self._pending_changes.discard(path)
        self._debouncer.trigger()

    def _flush(self) -> None:
        """Обрабатывает накопленные изменения."""
        with self._lock:
            changes = sorted(self._pending_changes)
            deletions = sorted(self._pending_deletions)
            self._pending_changes.clear()
            self._pending_deletions.clear()

        indexed = 0
        removed = 0

        for path in changes:
            if not path.exists():
                continue
            try:
                if self._indexing.index_single_file(path):
                    indexed += 1
            except Exception:
                _LOGGER.exception("Ошибка индексации файла %s", path)

        for path in deletions:
            try:
                if self._indexing.remove_file(path):
                    removed += 1
            except Exception:
                _LOGGER.exception("Ошибка удаления записи о файле %s", path)

        if (indexed or removed) and self._on_change is not None:
            try:
                self._on_change(indexed, removed)
            except Exception:
                _LOGGER.exception("Ошибка обработчика изменений папки")

        if indexed or removed:
            _LOGGER.info("Автообновление справочника: добавлено %s, удалено %s", indexed, removed)
