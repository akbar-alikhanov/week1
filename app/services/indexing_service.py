"""Сканирование папки сертификатов и наполнение справочника.

Требование продукта: при первом запуске прочитать все PDF, при последующих —
только новые и изменённые. Реализация опирается на трёхступенчатую проверку
«файл изменился?», выстроенную по возрастанию стоимости:

1. размер и время изменения (данные каталога, дисковых чтений нет);
2. SHA-256 содержимого (чтение файла, но без разбора PDF);
3. полный разбор PDF (самая дорогая операция).

Благодаря этому повторное сканирование папки из 10 000 файлов занимает
секунды, а не минуты.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable, Sequence
from pathlib import Path

from app.config.settings import SettingsService
from app.core.concurrency import ManagedThreadPool, default_worker_count
from app.core.constants import DB_BATCH_SIZE, PDF_EXTENSIONS
from app.core.events import AppEvent, EventBus, ProgressReporter
from app.core.exceptions import OperationCancelledError, PdfParsingError
from app.models.certificate import Certificate
from app.models.history import IndexingResult
from app.parsers.pdf_parser import PdfParser, compute_file_hash
from app.repositories.alias_repository import AliasRepository
from app.repositories.certificate_repository import CertificateRepository, FileFingerprint
from app.repositories.settings_repository import (
    KEY_LAST_CERTIFICATES_DIR,
    KEY_LAST_INDEXED_AT,
    SettingsRepository,
)

_LOGGER = logging.getLogger(__name__)


class IndexingService:
    """Индексирует папку с PDF-сертификатами."""

    def __init__(
        self,
        certificate_repository: CertificateRepository,
        alias_repository: AliasRepository,
        settings_repository: SettingsRepository,
        settings_service: SettingsService,
        event_bus: EventBus,
    ) -> None:
        """Создаёт сервис индексации.

        Args:
            certificate_repository: Справочник сертификатов.
            alias_repository: Таблица псевдонимов (для восстановления связей).
            settings_repository: Служебное состояние приложения.
            settings_service: Пользовательская конфигурация.
            event_bus: Шина событий приложения.
        """
        self._certificates = certificate_repository
        self._aliases = alias_repository
        self._state = settings_repository
        self._settings = settings_service
        self._events = event_bus

    # ------------------------------------------------------------ сканирование
    def discover_files(self, directory: Path, *, recursive: bool = True) -> list[Path]:
        """Находит PDF-файлы в папке сертификатов.

        Args:
            directory: Корневая папка.
            recursive: Обходить ли вложенные папки.

        Returns:
            Отсортированный список путей к PDF-файлам.
        """
        if not directory.exists() or not directory.is_dir():
            return []

        pattern = "**/*" if recursive else "*"
        files: list[Path] = []
        for path in directory.glob(pattern):
            try:
                if path.is_file() and path.suffix.lower() in PDF_EXTENSIONS:
                    files.append(path)
            except OSError:  # pragma: no cover — недоступный сетевой путь
                continue
        files.sort()
        return files

    def scan(
        self,
        directory: Path,
        *,
        reporter: ProgressReporter | None = None,
        force: bool = False,
    ) -> IndexingResult:
        """Сканирует папку и обновляет справочник сертификатов.

        Args:
            directory: Папка с PDF-сертификатами.
            reporter: Приёмник прогресса и токен отмены.
            force: Переиндексировать все файлы, игнорируя отпечатки.

        Returns:
            Итоги индексации.
        """
        started = time.perf_counter()
        result = IndexingResult()
        settings = self._settings.current.indexing

        self._events.publish(AppEvent.INDEX_STARTED, directory=str(directory))

        # Папка недоступна (не смонтирован сетевой диск, опечатка в пути) — в
        # этом случае справочник намеренно не трогаем: временная недоступность
        # не должна деактивировать весь накопленный список сертификатов.
        if not directory.exists() or not directory.is_dir():
            result.duration_ms = (time.perf_counter() - started) * 1000
            _LOGGER.warning("Папка сертификатов недоступна: %s", directory)
            self._events.publish(AppEvent.INDEX_FINISHED, result=result)
            return result

        files = self.discover_files(directory, recursive=settings.recursive)
        result.scanned = len(files)
        if reporter is not None:
            reporter.start(max(1, len(files)), f"Найдено файлов: {len(files)}", "scanning")

        if not files:
            # Папка существует, но пуста — в отличие от недоступности, это
            # осознанное состояние: если файлы были удалены пользователем,
            # соответствующие записи справочника должны деактивироваться.
            result.removed = self._certificates.deactivate_missing(())
            self._state.set(KEY_LAST_CERTIFICATES_DIR, str(directory))
            self._state.set_now(KEY_LAST_INDEXED_AT)
            result.duration_ms = (time.perf_counter() - started) * 1000
            _LOGGER.warning("В папке %s не найдено PDF-файлов", directory)
            self._events.publish(AppEvent.INDEX_FINISHED, result=result)
            return result

        fingerprints = self._certificates.fingerprints()
        plan = self._build_plan(files, fingerprints, force=force)
        result.skipped = len(files) - len(plan)

        if reporter is not None:
            reporter.set_progress(
                result.skipped,
                len(files),
                f"К обработке: {len(plan)}, без изменений: {result.skipped}",
            )

        if plan:
            try:
                added, updated, failed, errors = self._process_files(
                    plan,
                    settings.max_pages,
                    reporter=reporter,
                    offset=result.skipped,
                    total=len(files),
                )
                result.added = added
                result.updated = updated
                result.failed = failed
                result.errors = errors
            except OperationCancelledError:
                result.cancelled = True
                _LOGGER.info("Индексация отменена пользователем")

        if not result.cancelled:
            result.removed = self._certificates.deactivate_missing(str(path) for path in files)
            self._aliases.repair_links()
            self._state.set(KEY_LAST_CERTIFICATES_DIR, str(directory))
            self._state.set_now(KEY_LAST_INDEXED_AT)

        result.duration_ms = (time.perf_counter() - started) * 1000
        if reporter is not None:
            reporter.finish(result.summary(), "scanning")

        _LOGGER.info("%s за %.1f с", result.summary(), result.duration_ms / 1000)
        self._events.publish(AppEvent.INDEX_FINISHED, result=result)
        return result

    def index_single_file(self, path: Path) -> Certificate | None:
        """Индексирует один файл (используется наблюдателем за папкой).

        Args:
            path: Путь к PDF-файлу.

        Returns:
            Сохранённый сертификат либо ``None`` при ошибке разбора.
        """
        if not path.exists() or path.suffix.lower() not in PDF_EXTENSIONS:
            return None
        parser = PdfParser(max_pages=self._settings.current.indexing.max_pages)
        try:
            certificate = parser.parse(path)
        except PdfParsingError as error:
            _LOGGER.warning("Файл %s не проиндексирован: %s", path.name, error.message)
            return None

        self._certificates.upsert_many([certificate])
        self._events.publish(AppEvent.INDEX_FILE_ADDED, certificate=certificate)
        _LOGGER.info("Проиндексирован новый файл: %s", path.name)
        return certificate

    def remove_file(self, path: Path) -> bool:
        """Удаляет запись о файле, исчезнувшем из папки.

        Args:
            path: Путь к удалённому файлу.

        Returns:
            ``True``, если запись была удалена.
        """
        removed = self._certificates.delete_by_path(str(path))
        if removed:
            _LOGGER.info("Удалена запись о файле %s", path.name)
        return removed

    # ------------------------------------------------------------- внутреннее
    def _build_plan(
        self,
        files: Sequence[Path],
        fingerprints: dict[str, FileFingerprint],
        *,
        force: bool,
    ) -> list[Path]:
        """Отбирает файлы, требующие разбора.

        Args:
            files: Все найденные файлы.
            fingerprints: Отпечатки ранее проиндексированных файлов.
            force: Игнорировать отпечатки и обработать всё.

        Returns:
            Список файлов к обработке.
        """
        if force:
            return list(files)

        settings = self._settings.current.indexing
        plan: list[Path] = []
        for path in files:
            known = fingerprints.get(str(path))
            if known is None:
                plan.append(path)
                continue
            try:
                stat = path.stat()
            except OSError:  # pragma: no cover — файл исчез между обходом и проверкой
                continue

            if stat.st_size == known.file_size and abs(stat.st_mtime - known.file_mtime) < 1.0:
                continue

            if not settings.reindex_on_hash_change:
                plan.append(path)
                continue

            try:
                if compute_file_hash(path) == known.file_hash and known.file_hash:
                    continue
            except PdfParsingError:
                plan.append(path)
                continue
            plan.append(path)
        return plan

    def _process_files(
        self,
        files: Sequence[Path],
        max_pages: int,
        *,
        reporter: ProgressReporter | None,
        offset: int,
        total: int,
    ) -> tuple[int, int, int, list[tuple[str, str]]]:
        """Разбирает файлы в пуле потоков и сохраняет результат пакетами."""
        settings = self._settings.current.indexing
        workers = settings.max_workers or default_worker_count()
        parser = PdfParser(max_pages=max_pages)

        added = 0
        updated = 0
        failed = 0
        errors: list[tuple[str, str]] = []
        batch: list[Certificate] = []
        processed = 0

        def _flush() -> None:
            nonlocal added, updated, batch
            if not batch:
                return
            batch_added, batch_updated = self._certificates.upsert_many(batch)
            added += batch_added
            updated += batch_updated
            batch = []

        with ManagedThreadPool(workers, name="index") as pool:
            for path, certificate, error in pool.map_unordered(
                parser.parse, files, chunk_size=workers * 8
            ):
                if reporter is not None:
                    reporter.token.raise_if_cancelled()

                processed += 1
                if error is not None:
                    failed += 1
                    message = getattr(error, "message", str(error))
                    errors.append((path.name, message))
                    _LOGGER.warning("Ошибка разбора %s: %s", path.name, message)
                elif certificate is not None:
                    batch.append(certificate)
                    if len(batch) >= DB_BATCH_SIZE:
                        _flush()

                if reporter is not None and processed % 5 == 0:
                    reporter.set_progress(
                        offset + processed, total, f"Обработано {processed} из {len(files)}"
                    )
                    self._events.publish(
                        AppEvent.INDEX_PROGRESS, current=offset + processed, total=total
                    )

        _flush()
        return (added, updated, failed, errors)

    # ------------------------------------------------------------- состояние
    def last_indexed_at(self) -> str:
        """Возвращает время последней индексации в виде строки.

        Returns:
            Отметка времени либо пустая строка.
        """
        value = self._state.get_datetime(KEY_LAST_INDEXED_AT)
        return value.strftime("%d.%m.%Y %H:%M") if value else ""

    def last_directory(self) -> str:
        """Возвращает последнюю проиндексированную папку.

        Returns:
            Путь либо пустая строка.
        """
        stored = self._state.get(KEY_LAST_CERTIFICATES_DIR)
        if stored:
            return stored
        return self._settings.current.indexing.certificates_dir

    def needs_initial_scan(self) -> bool:
        """Проверяет, требуется ли первичное сканирование.

        Returns:
            ``True``, если справочник пуст.
        """
        return self._certificates.count("is_active = 1") == 0

    def collect_errors(self, result: IndexingResult, limit: int = 20) -> Iterable[str]:
        """Формирует человекочитаемый список ошибок индексации.

        Args:
            result: Итоги индексации.
            limit: Максимальное количество строк.

        Yields:
            Строки вида ``файл: причина``.
        """
        for name, message in result.errors[:limit]:
            yield f"{name}: {message}"
        if len(result.errors) > limit:
            yield f"… и ещё {len(result.errors) - limit} файлов"
