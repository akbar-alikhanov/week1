"""Самообучение и управление словарём соответствий товаров.

Это то, что превращает программу из «умного поиска» в инструмент, который со
временем перестаёт ошибаться. Каждое ручное исправление сохраняется навсегда
и на следующем заказе применяется мгновенно, до обращения к любым алгоритмам.

Сервис также обслуживает раздел «Словарь товаров» — полноценный редактор
соответствий: создание, редактирование, удаление (одиночное и массовое),
проверку дубликатов перед сохранением, отмену последнего действия и
резервное копирование словаря независимо от общей базы данных.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.core.events import AppEvent, EventBus
from app.core.exceptions import DuplicateAliasError
from app.core.paths import AppPaths
from app.core.text import normalize
from app.models.alias import Alias
from app.models.alias_audit import AliasAuditEntry
from app.models.certificate_product import CertificateProduct
from app.models.matching import MatchResult
from app.repositories.alias_repository import AliasRepository
from app.repositories.certificate_product_repository import CertificateProductRepository

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class DuplicateWarning:
    """Итог проверки на дубликаты перед сохранением записи словаря.

    Attributes:
        candidates: Похожие записи, уже существующие в словаре.
    """

    candidates: list[Alias]

    @property
    def has_matches(self) -> bool:
        """Признак того, что похожие записи найдены."""
        return bool(self.candidates)


class AliasService:
    """Управляет таблицей псевдонимов и словарём соответствий."""

    def __init__(
        self,
        alias_repository: AliasRepository,
        certificate_repository: CertificateProductRepository,
        event_bus: EventBus,
        paths: AppPaths | None = None,
    ) -> None:
        """Создаёт сервис псевдонимов.

        Args:
            alias_repository: Хранилище псевдонимов.
            certificate_repository: База сертификатов (для подсказок и
                проверки текущих соответствий).
            event_bus: Шина событий приложения.
            paths: Пути приложения (для резервных копий словаря).
        """
        self._aliases = alias_repository
        self._certificates = certificate_repository
        self._events = event_bus
        self._paths = paths

    # --------------------------------------------------------- самообучение
    def learn(
        self,
        source_text: str,
        certificate: CertificateProduct,
        *,
        note: str = "",
        weight: float = 1.0,
    ) -> Alias:
        """Запоминает соответствие «наименование → товар».

        Используется окном неоднозначного выбора: решение пользователя
        должно быть учтено раньше любых алгоритмов при следующей обработке.

        Args:
            source_text: Наименование из заказа, как его видел пользователь.
            certificate: Позиция базы сертификатов, выбранная пользователем.
            note: Комментарий.
            weight: Приоритет псевдонима при конфликтах.

        Returns:
            Сохранённый псевдоним.
        """
        alias = Alias(
            source_text=source_text.strip(),
            target_name=certificate.product_name,
            volume_ml=certificate.volume_ml,
            weight=weight,
            note=note,
            is_manual=True,
        )
        saved = self._aliases.save(alias)
        self._events.publish(AppEvent.ALIAS_CREATED, alias=saved)
        _LOGGER.info("Обучение: %s", saved.describe())
        return saved

    def learn_from_result(self, result: MatchResult, *, note: str = "") -> Alias | None:
        """Создаёт псевдоним по результату ручного выбора.

        Args:
            result: Результат подбора с выбранным пользователем кандидатом.
            note: Комментарий.

        Returns:
            Созданный псевдоним либо ``None``, если выбор отсутствует.
        """
        certificate = result.certificate
        if certificate is None:
            return None
        return self.learn(result.row.search_text, certificate, note=note)

    # -------------------------------------------------- словарь: CRUD
    def find_potential_duplicates(
        self, source_text: str, target_name: str = "", *, exclude_id: int | None = None
    ) -> DuplicateWarning:
        """Проверяет, есть ли в словаре записи, похожие на предлагаемую.

        Вызывается перед сохранением новой или изменённой записи, чтобы
        предупредить пользователя, а не молча создать почти дубликат.

        Args:
            source_text: Предлагаемое системное наименование.
            target_name: Предлагаемое русское наименование.
            exclude_id: Идентификатор записи, которую нужно исключить из
                сравнения (при редактировании — сама запись).

        Returns:
            Результат проверки.
        """
        candidates = self._aliases.find_similar(source_text, target_name, exclude_id=exclude_id)
        return DuplicateWarning(candidates=candidates)

    def add(
        self,
        source_text: str,
        target_name: str,
        *,
        brand: str = "",
        volume_ml: float | None = None,
        note: str = "",
    ) -> Alias:
        """Добавляет новую запись словаря вручную (окно «Добавить соответствие»).

        В отличие от :meth:`learn`, отклоняет точный дубликат вместо тихого
        слияния — на этом уровне вызывающая сторона уже должна была
        предупредить пользователя через :meth:`find_potential_duplicates`.

        Args:
            source_text: Системное наименование (как в заказе).
            target_name: Русское наименование товара (как в базе сертификатов).
            brand: Бренд (произвольная заметка).
            volume_ml: Объём товара.
            note: Комментарий.

        Returns:
            Созданная запись.

        Raises:
            DuplicateAliasError: Если точно такая же запись уже существует.
        """
        alias = Alias(
            source_text=source_text.strip(),
            target_name=target_name.strip(),
            brand=brand,
            volume_ml=volume_ml,
            note=note,
            is_manual=True,
        )
        created = self._aliases.create(alias)
        self._events.publish(AppEvent.ALIAS_CREATED, alias=created)
        return created

    def update(self, alias_id: int, **changes: object) -> Alias:
        """Изменяет существующую запись словаря.

        Args:
            alias_id: Идентификатор записи.
            **changes: Новые значения полей.

        Returns:
            Обновлённая запись.

        Raises:
            DuplicateAliasError: Если запись не найдена или конфликтует
                с другой существующей записью.
        """
        updated = self._aliases.update(alias_id, **changes)
        self._events.publish(AppEvent.DATABASE_CHANGED, reason="alias_updated")
        return updated

    def forget(self, alias_id: int) -> bool:
        """Удаляет псевдоним.

        Args:
            alias_id: Идентификатор псевдонима.

        Returns:
            ``True``, если запись была удалена.
        """
        removed = self._aliases.delete(alias_id)
        if removed:
            _LOGGER.info("Псевдоним %s удалён", alias_id)
            self._events.publish(AppEvent.DATABASE_CHANGED, reason="alias_deleted")
        return removed

    def forget_source(self, source_text: str) -> int:
        """Удаляет все псевдонимы для наименования.

        Args:
            source_text: Наименование из заказа.

        Returns:
            Количество удалённых записей.
        """
        removed = self._aliases.remove_for_source(source_text)
        if removed:
            self._events.publish(AppEvent.DATABASE_CHANGED, reason="alias_deleted")
        return removed

    def bulk_delete(self, ids: list[int]) -> int:
        """Удаляет несколько записей одновременно.

        Args:
            ids: Идентификаторы записей.

        Returns:
            Количество удалённых записей.
        """
        removed = self._aliases.bulk_delete(ids)
        if removed:
            self._events.publish(AppEvent.DATABASE_CHANGED, reason="alias_bulk_deleted")
        return removed

    def bulk_update(
        self, ids: list[int], *, brand: str | None = None, note: str | None = None
    ) -> int:
        """Массово изменяет бренд и/или комментарий у набора записей.

        Args:
            ids: Идентификаторы записей.
            brand: Новое значение бренда.
            note: Новое значение комментария.

        Returns:
            Количество изменённых записей.
        """
        changed = self._aliases.bulk_update(ids, brand=brand, note=note)
        if changed:
            self._events.publish(AppEvent.DATABASE_CHANGED, reason="alias_bulk_updated")
        return changed

    # -------------------------------------------------------- undo и журнал
    def undo_last(self) -> AliasAuditEntry | None:
        """Отменяет последнее действие в словаре (создание/изменение/удаление).

        Returns:
            Отменённая запись журнала либо ``None``, если отменять нечего.
        """
        entry = self._aliases.last_audit_entry()
        if entry is None or entry.id is None:
            return None
        if not self._aliases.undo(entry.id):
            return None
        self._events.publish(AppEvent.DATABASE_CHANGED, reason="alias_undo")
        return entry

    def pending_undo(self) -> AliasAuditEntry | None:
        """Возвращает действие, которое будет отменено по Ctrl+Z, без отмены.

        Используется интерфейсом, чтобы показать поясняющую подсказку на
        кнопке «Отменить» до того, как пользователь на неё нажмёт.

        Returns:
            Последняя ещё не отменённая запись журнала либо ``None``.
        """
        return self._aliases.last_audit_entry()

    def audit_log(self, *, alias_id: int | None = None, limit: int = 200) -> list[AliasAuditEntry]:
        """Возвращает журнал изменений словаря.

        Args:
            alias_id: Ограничить журнал одной записью (``None`` — весь журнал).
            limit: Максимум записей.

        Returns:
            Записи журнала, новые сначала.
        """
        return self._aliases.list_audit(alias_id=alias_id, limit=limit)

    # ------------------------------------------------------------- чтение
    def list_aliases(self, *, search: str = "", limit: int = 0) -> list[Alias]:
        """Возвращает псевдонимы для отображения (устаревший метод).

        Args:
            search: Фильтр по подстроке.
            limit: Ограничение количества.

        Returns:
            Список псевдонимов.
        """
        return self._aliases.search(search, limit=limit or 100_000)

    def search(
        self,
        query: str = "",
        *,
        brand: str = "",
        volume_ml: float | None = None,
        sort: str = "updated_desc",
        limit: int = 500,
        offset: int = 0,
    ) -> list[Alias]:
        """Ищет записи словаря с фильтрами и сортировкой.

        Args:
            query: Текст поиска.
            brand: Точное значение бренда.
            volume_ml: Значение объёма для фильтра.
            sort: Ключ сортировки.
            limit: Максимум записей.
            offset: Смещение для постраничной загрузки.

        Returns:
            Найденные записи.
        """
        return self._aliases.search(
            query, brand=brand, volume_ml=volume_ml, sort=sort, limit=limit, offset=offset
        )

    def count_search(
        self, query: str = "", *, brand: str = "", volume_ml: float | None = None
    ) -> int:
        """Возвращает общее количество записей, подходящих под фильтр.

        Args:
            query: Текст поиска.
            brand: Точное значение бренда.
            volume_ml: Значение объёма.

        Returns:
            Количество подходящих записей.
        """
        return self._aliases.count_search(query, brand=brand, volume_ml=volume_ml)

    def list_brands(self) -> list[str]:
        """Возвращает список брендов для выпадающего фильтра.

        Returns:
            Бренды в алфавитном порядке.
        """
        return self._aliases.list_brands()

    def list_volumes(self) -> list[float]:
        """Возвращает список объёмов для выпадающего фильтра.

        Returns:
            Значения объёма.
        """
        return self._aliases.list_volumes()

    def find_related_certificates(
        self, alias: Alias, *, limit: int = 8
    ) -> list[CertificateProduct]:
        """Возвращает позиции базы, на которые сейчас разрешается запись.

        Показывает не абстрактно похожие товары, а именно то, что найдёт
        строгий поиск алгоритма подбора прямо сейчас: ``normalized_name`` +
        ``volume_ml`` записи словаря. Это самый честный предпросмотр того,
        что произойдёт при следующей обработке заказа.

        Args:
            alias: Псевдоним.
            limit: Максимум результатов.

        Returns:
            Подходящие позиции базы сертификатов, максимум ``limit``.
        """
        normalized = normalize(alias.target_name)
        if not normalized:
            return []
        found = self._certificates.find_strict(normalized, alias.volume_ml)
        return found[:limit]

    def count(self) -> int:
        """Возвращает количество сохранённых псевдонимов.

        Returns:
            Количество записей.
        """
        return self._aliases.count()

    # -------------------------------------------------------- импорт/экспорт
    def export(self, destination: Path) -> int:
        """Экспортирует псевдонимы в файл.

        Args:
            destination: Путь файла (``.json``, ``.csv`` или ``.xlsx``).

        Returns:
            Количество экспортированных записей.
        """
        return self._aliases.export_to_file(destination)

    def import_from(self, source: Path) -> tuple[int, int, int]:
        """Импортирует псевдонимы из файла.

        Args:
            source: Путь файла.

        Returns:
            Тройка ``(добавлено, объединено, пропущено)``.
        """
        result = self._aliases.import_from_file(source)
        self._events.publish(AppEvent.DATABASE_CHANGED, reason="aliases_imported")
        return result

    # --------------------------------------------------------------- бэкапы
    @property
    def backups_dir(self) -> Path | None:
        """Каталог резервных копий словаря соответствий.

        Returns:
            Путь к каталогу либо ``None``, если пути приложения не заданы
            (например, в модульных тестах сервиса без файловой системы).
        """
        if self._paths is None:
            return None
        directory = self._paths.backup_dir / "aliases"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def backup(self) -> Path:
        """Создаёт именованную по времени резервную копию словаря.

        Returns:
            Путь созданного файла.

        Raises:
            RuntimeError: Если пути приложения не настроены.
        """
        directory = self.backups_dir
        if directory is None:
            raise RuntimeError("Резервное копирование недоступно: пути приложения не заданы")
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        destination = directory / f"aliases_{stamp}.json"
        self._aliases.export_to_file(destination)
        _LOGGER.info("Создана резервная копия словаря: %s", destination)
        return destination

    def restore(self, source: Path, *, replace: bool = False) -> tuple[int, int, int]:
        """Восстанавливает словарь из резервной копии или экспортированного файла.

        Args:
            source: Путь файла резервной копии.
            replace: Если ``True`` — полностью очистить текущий словарь перед
                восстановлением (необратимо; подтверждение — на совести
                вызывающей стороны). Если ``False`` (по умолчанию) — записи
                сливаются с текущими, как при обычном импорте.

        Returns:
            Тройка ``(добавлено, объединено, пропущено)``.
        """
        if replace:
            cleared = self._aliases.clear()
            _LOGGER.warning("Словарь очищен перед восстановлением: %s записей", cleared)
        return self.import_from(source)


__all__ = ["AliasService", "DuplicateAliasError", "DuplicateWarning"]
