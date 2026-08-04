"""Самообучение: запоминание ручных решений пользователя.

Это то, что превращает программу из «умного поиска» в инструмент, который со
временем перестаёт ошибаться. Каждое ручное исправление сохраняется навсегда
и на следующем заказе применяется мгновенно, до обращения к любым алгоритмам.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.events import AppEvent, EventBus
from app.models.alias import Alias
from app.models.certificate import Certificate
from app.models.matching import MatchResult
from app.repositories.alias_repository import AliasRepository
from app.repositories.certificate_repository import CertificateRepository

_LOGGER = logging.getLogger(__name__)


class AliasService:
    """Управляет таблицей псевдонимов."""

    def __init__(
        self,
        alias_repository: AliasRepository,
        certificate_repository: CertificateRepository,
        event_bus: EventBus,
    ) -> None:
        """Создаёт сервис псевдонимов.

        Args:
            alias_repository: Хранилище псевдонимов.
            certificate_repository: Справочник сертификатов.
            event_bus: Шина событий приложения.
        """
        self._aliases = alias_repository
        self._certificates = certificate_repository
        self._events = event_bus

    def learn(
        self, source_text: str, certificate: Certificate, *, note: str = "", weight: float = 1.0
    ) -> Alias:
        """Запоминает соответствие «наименование → сертификат».

        Args:
            source_text: Наименование из заказа, как его видел пользователь.
            certificate: Сертификат, выбранный пользователем.
            note: Комментарий.
            weight: Приоритет псевдонима при конфликтах.

        Returns:
            Сохранённый псевдоним.

        Raises:
            ValueError: Если сертификат не сохранён в базе.
        """
        if certificate.id is None:
            raise ValueError("Невозможно создать псевдоним для несохранённого сертификата")

        alias = Alias(
            source_text=source_text.strip(),
            certificate_id=certificate.id,
            target_name=certificate.product_name,
            target_pdf_name=certificate.pdf_name,
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

    def forget(self, alias_id: int) -> bool:
        """Удаляет псевдоним.

        Args:
            alias_id: Идентификатор псевдонима.

        Returns:
            ``True``, если запись была удалена.
        """
        removed = self._aliases.delete_by_id(alias_id)
        if removed:
            _LOGGER.info("Псевдоним %s удалён", alias_id)
        return removed

    def forget_source(self, source_text: str) -> int:
        """Удаляет все псевдонимы для наименования.

        Args:
            source_text: Наименование из заказа.

        Returns:
            Количество удалённых записей.
        """
        return self._aliases.remove_for_source(source_text)

    def list_aliases(self, *, search: str = "", limit: int = 0) -> list[Alias]:
        """Возвращает псевдонимы для отображения.

        Args:
            search: Фильтр по подстроке.
            limit: Ограничение количества.

        Returns:
            Список псевдонимов.
        """
        return self._aliases.list_all(search=search, limit=limit)

    def resolve_certificate(self, alias: Alias) -> Certificate | None:
        """Возвращает сертификат, на который ссылается псевдоним.

        Args:
            alias: Псевдоним.

        Returns:
            Сертификат либо ``None``, если связь потеряна.
        """
        if alias.certificate_id is None:
            return None
        return self._certificates.get_by_id(alias.certificate_id)

    def export(self, destination: Path) -> int:
        """Экспортирует псевдонимы в файл.

        Args:
            destination: Путь файла (``.json`` или ``.csv``).

        Returns:
            Количество экспортированных записей.
        """
        return self._aliases.export_to_file(destination)

    def import_from(self, source: Path) -> tuple[int, int]:
        """Импортирует псевдонимы из файла.

        Args:
            source: Путь файла.

        Returns:
            Пара ``(импортировано, пропущено)``.
        """
        result = self._aliases.import_from_file(source)
        self._events.publish(AppEvent.DATABASE_CHANGED, reason="aliases_imported")
        return result

    def repair(self) -> int:
        """Восстанавливает связи псевдонимов после переиндексации.

        Returns:
            Количество восстановленных связей.
        """
        return self._aliases.repair_links()

    def count(self) -> int:
        """Возвращает количество сохранённых псевдонимов.

        Returns:
            Количество записей.
        """
        return self._aliases.count()
