"""Тесты сервиса самообучения (псевдонимов)."""

from __future__ import annotations

import pytest

from app.core.events import EventBus
from app.database.connection import Database
from app.models.matching import (
    MatchCandidate,
    MatchResult,
    MatchSource,
    MatchStatus,
    ScoreBreakdown,
)
from app.models.order import OrderRow
from app.repositories.alias_repository import AliasRepository
from app.repositories.certificate_product_repository import CertificateProductRepository
from app.services.alias_service import AliasService
from tests.conftest import make_certificate


@pytest.fixture
def alias_service(database: Database) -> AliasService:
    """Собранный сервис псевдонимов поверх временной базы данных."""
    return AliasService(
        AliasRepository(database), CertificateProductRepository(database), EventBus()
    )


class TestLearn:
    """Проверки создания псевдонима из ручного выбора."""

    def test_learn_creates_alias(self, alias_service: AliasService) -> None:
        """Обучение создаёт псевдоним с наименованием и объёмом выбранного товара."""
        certificate = make_certificate("Лечебные травы 100 мл")

        alias = alias_service.learn("TP Herbal 100ml", certificate)

        assert alias.id is not None
        assert alias.target_name == certificate.product_name
        assert alias.volume_ml == certificate.volume_ml

    def test_learn_publishes_event(self, database: Database) -> None:
        """Создание псевдонима публикует доменное событие."""
        events = EventBus()
        received: list[object] = []
        events.subscribe("alias.created", lambda **kwargs: received.append(kwargs.get("alias")))

        service = AliasService(
            AliasRepository(database), CertificateProductRepository(database), events
        )
        certificate = make_certificate("Товар")

        service.learn("Псевдоним", certificate)

        assert len(received) == 1


class TestLearnFromResult:
    """Проверки обучения по результату подбора."""

    def test_learn_from_result_with_selection(self, alias_service: AliasService) -> None:
        """Обучение по результату с выбранным кандидатом создаёт псевдоним."""
        certificate = make_certificate("Товар")
        score = ScoreBreakdown(name=0.9, volume=1.0, expiry=1.0, total=0.9)
        candidate = MatchCandidate(certificate=certificate, score=score, source=MatchSource.LEXICAL)
        result = MatchResult(
            row=OrderRow(row_number=1, product_name="Наименование из заказа"),
            status=MatchStatus.MANUAL,
            candidates=[candidate],
            selected_index=0,
        )

        alias = alias_service.learn_from_result(result)

        assert alias is not None
        assert alias.source_text == "Наименование из заказа"

    def test_learn_from_result_without_certificate_returns_none(
        self, alias_service: AliasService
    ) -> None:
        """Результат без выбранного сертификата не создаёт псевдоним."""
        result = MatchResult(
            row=OrderRow(row_number=1, product_name="Товар"), status=MatchStatus.NOT_FOUND
        )
        assert alias_service.learn_from_result(result) is None


class TestForget:
    """Проверки удаления псевдонимов."""

    def test_forget_removes_alias(self, alias_service: AliasService) -> None:
        """Удаление по идентификатору убирает псевдоним из хранилища."""
        certificate = make_certificate("Товар")
        alias = alias_service.learn("Псевдоним", certificate)

        assert alias_service.forget(alias.id)  # type: ignore[arg-type]
        assert alias_service.count() == 0

    def test_forget_unknown_id_returns_false(self, alias_service: AliasService) -> None:
        """Удаление несуществующего идентификатора не вызывает ошибку."""
        assert alias_service.forget(999) is False


class TestDictionaryCrud:
    """Проверки явного управления словарём (раздел «Словарь товаров»)."""

    def test_add_creates_manual_entry(self, alias_service: AliasService) -> None:
        """Ручное добавление создаёт запись с полным доверием."""
        alias = alias_service.add("Системное имя", "Товар", brand="Balton")

        assert alias.is_manual is True
        assert alias.confidence == 100.0
        assert alias.brand == "Balton"

    def test_find_potential_duplicates_detects_close_variant(
        self, alias_service: AliasService
    ) -> None:
        """Проверка дубликатов находит близкий, но не идентичный вариант."""
        alias_service.add("TP Herbal 100ml", "Товар")

        warning = alias_service.find_potential_duplicates("TP Herbal 100 ml")

        assert warning.has_matches

    def test_update_changes_volume(self, alias_service: AliasService) -> None:
        """Изменение записи обновляет объём независимо от текущей базы."""
        alias = alias_service.add("Системное имя", "Товар A", volume_ml=100.0)
        updated = alias_service.update(alias.id, volume_ml=150.0)  # type: ignore[arg-type]

        assert updated.volume_ml == 150.0

    def test_bulk_delete_removes_multiple(self, alias_service: AliasService) -> None:
        """Массовое удаление через сервис убирает все указанные записи."""
        one = alias_service.add("Товар A", "A")
        two = alias_service.add("Товар B", "B")

        removed = alias_service.bulk_delete([one.id, two.id])  # type: ignore[list-item]

        assert removed == 2
        assert alias_service.count() == 0

    def test_undo_last_reverts_most_recent_action(self, alias_service: AliasService) -> None:
        """Отмена последнего действия восстанавливает словарь до предыдущего состояния."""
        alias = alias_service.add("Товар", "Товар")
        assert alias.id is not None
        alias_service.forget(alias.id)
        assert alias_service.count() == 0

        entry = alias_service.undo_last()

        assert entry is not None
        assert alias_service.count() == 1

    def test_undo_last_with_nothing_to_undo_returns_none(self, alias_service: AliasService) -> None:
        """Отмена без предшествующих действий не вызывает ошибку."""
        assert alias_service.undo_last() is None


class TestFindRelatedCertificates:
    """Проверки предпросмотра текущего разрешения записи словаря."""

    def test_finds_strict_match_in_database(
        self, alias_service: AliasService, certificate_repository: CertificateProductRepository
    ) -> None:
        """Показывается именно то, что найдёт строгий поиск алгоритма подбора."""
        certificate_repository.replace_all(
            [make_certificate("Лечебные травы 100 мл", volume_ml=100.0)]
        )
        alias = alias_service.add("TP Herbal", "Лечебные травы 100 мл", volume_ml=100.0)

        related = alias_service.find_related_certificates(alias)

        assert len(related) == 1
        assert related[0].product_name == "Лечебные травы 100 мл"

    def test_empty_when_nothing_matches(
        self, alias_service: AliasService, certificate_repository: CertificateProductRepository
    ) -> None:
        """Пустой результат, если строгий поиск ничего не находит."""
        alias = alias_service.add("TP Herbal", "Товар, которого нет в базе")

        assert alias_service.find_related_certificates(alias) == []
