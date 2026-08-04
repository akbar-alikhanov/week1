"""Композиционный корень приложения (Dependency Injection).

Единственное место, где создаются конкретные реализации и связываются между
собой. Все остальные классы получают зависимости через конструктор и не знают,
кто их создал, — это делает каждый слой заменяемым и тестируемым в изоляции.

Контейнер реализует ленивую инициализацию: тяжёлые объекты (соединение с
базой, семантическая модель) создаются в момент первого обращения, поэтому
окно приложения появляется на экране мгновенно.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.ai.embeddings import EmbeddingBackend
from app.ai.vector_index import VectorIndex
from app.config.settings import AppSettings, SettingsService
from app.core.concurrency import Lazy, ManagedThreadPool
from app.core.events import EventBus
from app.core.logging_setup import MemoryLogHandler, configure_logging, get_memory_handler
from app.core.paths import AppPaths
from app.database.connection import Database
from app.parsers.excel_order_parser import ExcelOrderParser
from app.parsers.pdf_parser import PdfParser
from app.repositories.alias_repository import AliasRepository
from app.repositories.cache_repository import CacheRepository
from app.repositories.certificate_repository import CertificateRepository
from app.repositories.history_repository import HistoryRepository
from app.repositories.product_repository import ProductRepository
from app.repositories.settings_repository import SettingsRepository
from app.services.alias_service import AliasService
from app.services.backup_service import BackupService
from app.services.indexing_service import IndexingService
from app.services.matching_service import MatchingService
from app.services.order_processing_service import OrderProcessingService
from app.services.report_service import ReportService
from app.services.watcher_service import CertificateWatcher

_LOGGER = logging.getLogger(__name__)


class ApplicationContainer:
    """Контейнер зависимостей приложения.

    Использование::

        container = ApplicationContainer.create()
        container.startup()
        ...
        container.shutdown()
    """

    def __init__(self, paths: AppPaths) -> None:
        """Создаёт контейнер для заданного размещения данных.

        Args:
            paths: Пути приложения.
        """
        self._paths = paths
        self._events = EventBus()
        self._log_handler: MemoryLogHandler | None = get_memory_handler()

        self._settings_service = Lazy(self._create_settings_service)
        self._database = Lazy(self._create_database)
        self._certificate_repository: Lazy[CertificateRepository] = Lazy(
            lambda: CertificateRepository(self.database)
        )
        self._alias_repository: Lazy[AliasRepository] = Lazy(lambda: AliasRepository(self.database))
        self._product_repository: Lazy[ProductRepository] = Lazy(
            lambda: ProductRepository(self.database)
        )
        self._history_repository: Lazy[HistoryRepository] = Lazy(
            lambda: HistoryRepository(self.database)
        )
        self._cache_repository: Lazy[CacheRepository] = Lazy(lambda: CacheRepository(self.database))
        self._settings_repository: Lazy[SettingsRepository] = Lazy(
            lambda: SettingsRepository(self.database)
        )

        self._embedding_backend = Lazy(self._create_embedding_backend)
        self._vector_index: Lazy[VectorIndex] = Lazy(
            lambda: VectorIndex(self.embedding_backend, self.cache_repository)
        )

        self._matching_service = Lazy(self._create_matching_service)
        self._indexing_service = Lazy(self._create_indexing_service)
        self._alias_service = Lazy(self._create_alias_service)
        self._order_service = Lazy(self._create_order_service)
        self._backup_service = Lazy(self._create_backup_service)
        self._watcher = Lazy(self._create_watcher)
        self._report_service: Lazy[ReportService] = Lazy(ReportService)
        self._excel_parser: Lazy[ExcelOrderParser] = Lazy(ExcelOrderParser)
        self._pdf_parser: Lazy[PdfParser] = Lazy(PdfParser)
        self._background_pool = Lazy(lambda: ManagedThreadPool(name="app"))

    # --------------------------------------------------------------- фабрика
    @classmethod
    def create(
        cls, *, data_dir: Path | str | None = None, configure_logs: bool = True
    ) -> ApplicationContainer:
        """Создаёт контейнер и настраивает журналирование.

        Args:
            data_dir: Явный каталог данных (аргумент ``--data-dir``).
            configure_logs: Настраивать ли журналирование.

        Returns:
            Готовый к использованию контейнер.
        """
        paths = AppPaths.resolve(data_dir)
        container = cls(paths)
        if configure_logs:
            container._log_handler = configure_logging(
                log_file=paths.log_file,
                error_log_file=paths.error_log_file,
                level=container.settings.maintenance.log_level,
            )
        return container

    # ------------------------------------------------------------- свойства
    @property
    def paths(self) -> AppPaths:
        """Пути приложения."""
        return self._paths

    @property
    def events(self) -> EventBus:
        """Шина доменных событий."""
        return self._events

    @property
    def log_handler(self) -> MemoryLogHandler | None:
        """Обработчик оперативного журнала для окна «Журнал»."""
        return self._log_handler

    @property
    def settings_service(self) -> SettingsService:
        """Сервис конфигурации."""
        return self._settings_service.get()

    @property
    def settings(self) -> AppSettings:
        """Текущая конфигурация приложения."""
        return self.settings_service.current

    @property
    def database(self) -> Database:
        """Менеджер базы данных."""
        return self._database.get()

    @property
    def certificate_repository(self) -> CertificateRepository:
        """Репозиторий сертификатов."""
        return self._certificate_repository.get()

    @property
    def alias_repository(self) -> AliasRepository:
        """Репозиторий псевдонимов."""
        return self._alias_repository.get()

    @property
    def product_repository(self) -> ProductRepository:
        """Репозиторий товаров."""
        return self._product_repository.get()

    @property
    def history_repository(self) -> HistoryRepository:
        """Репозиторий истории обработки."""
        return self._history_repository.get()

    @property
    def cache_repository(self) -> CacheRepository:
        """Репозиторий кэша и векторов."""
        return self._cache_repository.get()

    @property
    def settings_repository(self) -> SettingsRepository:
        """Репозиторий служебного состояния."""
        return self._settings_repository.get()

    @property
    def embedding_backend(self) -> EmbeddingBackend:
        """Семантический бэкенд."""
        return self._embedding_backend.get()

    @property
    def vector_index(self) -> VectorIndex:
        """Векторный индекс наименований."""
        return self._vector_index.get()

    @property
    def matching_service(self) -> MatchingService:
        """Сервис подбора сертификатов."""
        return self._matching_service.get()

    @property
    def indexing_service(self) -> IndexingService:
        """Сервис индексации папки сертификатов."""
        return self._indexing_service.get()

    @property
    def alias_service(self) -> AliasService:
        """Сервис псевдонимов."""
        return self._alias_service.get()

    @property
    def order_service(self) -> OrderProcessingService:
        """Оркестратор обработки заказа."""
        return self._order_service.get()

    @property
    def report_service(self) -> ReportService:
        """Сервис отчётов."""
        return self._report_service.get()

    @property
    def backup_service(self) -> BackupService:
        """Сервис резервного копирования."""
        return self._backup_service.get()

    @property
    def watcher(self) -> CertificateWatcher:
        """Наблюдатель за папкой сертификатов."""
        return self._watcher.get()

    @property
    def excel_parser(self) -> ExcelOrderParser:
        """Парсер файлов заказа."""
        return self._excel_parser.get()

    @property
    def pdf_parser(self) -> PdfParser:
        """Парсер PDF-сертификатов."""
        return self._pdf_parser.get()

    @property
    def background_pool(self) -> ManagedThreadPool:
        """Пул фоновых задач интерфейса."""
        return self._background_pool.get()

    # ------------------------------------------------------- жизненный цикл
    def startup(self) -> None:
        """Инициализирует базу данных и выполняет обслуживание при запуске."""
        self.database.initialize()

        maintenance = self.settings.maintenance
        if maintenance.vacuum_on_start:
            self.database.vacuum()
        if maintenance.auto_backup:
            self.backup_service.create_if_due()

        try:
            self.cache_repository.purge_expired()
        except Exception:
            _LOGGER.debug("Очистка кэша не выполнена", exc_info=True)

        _LOGGER.info("Приложение инициализировано (%s)", self._paths.base)

    def start_watcher(self) -> bool:
        """Запускает наблюдение за папкой сертификатов, если это разрешено.

        Returns:
            ``True``, если наблюдение запущено.
        """
        indexing = self.settings.indexing
        if not indexing.watch_enabled:
            return False
        directory = self.indexing_service.last_directory()
        if not directory:
            return False
        return self.watcher.start(Path(directory), recursive=indexing.recursive)

    def shutdown(self) -> None:
        """Корректно завершает работу всех подсистем."""
        _LOGGER.info("Завершение работы приложения…")
        if self._watcher.initialized:
            self.watcher.stop()
        if self._background_pool.initialized:
            self.background_pool.shutdown(wait=False)
        if self._embedding_backend.initialized:
            self.embedding_backend.unload()
        if self._database.initialized:
            self.database.checkpoint()
            self.database.close()
        self._events.clear()

    def __enter__(self) -> ApplicationContainer:
        """Инициализирует контейнер при входе в блок ``with``."""
        self.startup()
        return self

    def __exit__(self, *_: object) -> None:
        """Завершает работу контейнера при выходе из блока ``with``."""
        self.shutdown()

    # -------------------------------------------------------------- фабрики
    def _create_settings_service(self) -> SettingsService:
        """Создаёт сервис конфигурации."""
        service = SettingsService(self._paths.settings_file)
        service.load()
        return service

    def _create_database(self) -> Database:
        """Создаёт менеджер базы данных."""
        return Database(self._paths.database_file)

    def _create_embedding_backend(self) -> EmbeddingBackend:
        """Создаёт семантический бэкенд."""
        matching = self.settings.matching
        return EmbeddingBackend(
            matching.embedding_model,
            cache_dir=self._paths.models_dir,
            enabled=matching.use_semantic,
        )

    def _create_matching_service(self) -> MatchingService:
        """Создаёт сервис подбора."""
        return MatchingService(
            self.certificate_repository,
            self.alias_repository,
            self.settings_service,
            self.embedding_backend,
            self.vector_index,
        )

    def _create_indexing_service(self) -> IndexingService:
        """Создаёт сервис индексации."""
        return IndexingService(
            self.certificate_repository,
            self.alias_repository,
            self.settings_repository,
            self.settings_service,
            self._events,
        )

    def _create_alias_service(self) -> AliasService:
        """Создаёт сервис псевдонимов."""
        return AliasService(
            self.alias_repository, self.certificate_repository, self._events, self._paths
        )

    def _create_order_service(self) -> OrderProcessingService:
        """Создаёт оркестратор обработки заказа."""
        return OrderProcessingService(
            self.matching_service,
            self.excel_parser,
            self.history_repository,
            self.product_repository,
            self.report_service,
            self.settings_service,
            self._events,
            alias_service=self.alias_service,
        )

    def _create_backup_service(self) -> BackupService:
        """Создаёт сервис резервного копирования."""
        return BackupService(
            self.database,
            self._paths.backup_dir,
            self.settings_repository,
            retention=self.settings.maintenance.backup_retention,
        )

    def _create_watcher(self) -> CertificateWatcher:
        """Создаёт наблюдателя за папкой сертификатов."""
        return CertificateWatcher(
            self.indexing_service,
            debounce_seconds=self.settings.indexing.watch_debounce_seconds,
            on_change=self._on_watcher_change,
        )

    def _on_watcher_change(self, indexed: int, removed: int) -> None:
        """Реагирует на изменения в папке сертификатов."""
        if self._matching_service.initialized:
            self.matching_service.invalidate()
        self._events.publish("index.auto_updated", indexed=indexed, removed=removed)

    # ------------------------------------------------------------ диагностика
    def diagnostics(self) -> dict[str, Any]:
        """Собирает сведения о состоянии приложения.

        Используется окном «О программе» и командой ``--selfcheck``.

        Returns:
            Словарь «раздел → значение».
        """
        import platform
        import sys

        from app.core.constants import APP_NAME, APP_VERSION

        info: dict[str, Any] = {
            "Приложение": f"{APP_NAME} {APP_VERSION}",
            "Python": sys.version.split()[0],
            "Система": f"{platform.system()} {platform.release()}",
        }
        info.update(self._paths.describe())
        try:
            info["Сертификатов в базе"] = self.certificate_repository.count("is_active = 1")
            info["Псевдонимов"] = self.alias_repository.count()
            info["Обработок в истории"] = self.history_repository.count()
        except Exception as error:
            info["База данных"] = f"недоступна: {error}"

        status = self.embedding_backend.status()
        info["Семантический поиск"] = status.message
        info["Наблюдение за папкой"] = (
            "доступно" if CertificateWatcher.available() else "недоступно (нет watchdog)"
        )
        return info
