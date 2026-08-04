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
from app.repositories.certificate_repository import CertificateRepository
from app.services.alias_service import AliasService
from tests.conftest import make_certificate


@pytest.fixture
def alias_service(database: Database) -> AliasService:
    """Собранный сервис псевдонимов поверх временной базы данных."""
    return AliasService(AliasRepository(database), CertificateRepository(database), EventBus())


class TestLearn:
    """Проверки создания псевдонима из ручного выбора."""

    def test_learn_creates_alias(
        self, alias_service: AliasService, certificate_repository: CertificateRepository
    ) -> None:
        """Обучение создаёт псевдоним, ссылающийся на выбранный сертификат."""
        certificate = make_certificate("Лечебные травы 100 мл", "/c/1.pdf")
        certificate_repository.add(certificate)

        alias = alias_service.learn("TP Herbal 100ml", certificate)

        assert alias.id is not None
        assert alias.certificate_id == certificate.id
        assert alias.target_name == certificate.product_name

    def test_learn_without_saved_certificate_raises(self, alias_service: AliasService) -> None:
        """Обучение на несохранённом сертификате (без id) порождает ошибку."""
        certificate = make_certificate("Товар", "/c/1.pdf")
        with pytest.raises(ValueError, match="несохранённого"):
            alias_service.learn("Псевдоним", certificate)

    def test_learn_publishes_event(
        self, database: Database, certificate_repository: CertificateRepository
    ) -> None:
        """Создание псевдонима публикует доменное событие."""
        events = EventBus()
        received: list[object] = []
        events.subscribe("alias.created", lambda **kwargs: received.append(kwargs.get("alias")))

        service = AliasService(AliasRepository(database), certificate_repository, events)
        certificate = make_certificate("Товар", "/c/1.pdf")
        certificate_repository.add(certificate)

        service.learn("Псевдоним", certificate)

        assert len(received) == 1


class TestLearnFromResult:
    """Проверки обучения по результату подбора."""

    def test_learn_from_result_with_selection(
        self, alias_service: AliasService, certificate_repository: CertificateRepository
    ) -> None:
        """Обучение по результату с выбранным кандидатом создаёт псевдоним."""
        certificate = make_certificate("Товар", "/c/1.pdf")
        certificate_repository.add(certificate)
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

    def test_forget_removes_alias(
        self, alias_service: AliasService, certificate_repository: CertificateRepository
    ) -> None:
        """Удаление по идентификатору убирает псевдоним из хранилища."""
        certificate = make_certificate("Товар", "/c/1.pdf")
        certificate_repository.add(certificate)
        alias = alias_service.learn("Псевдоним", certificate)

        assert alias_service.forget(alias.id)  # type: ignore[arg-type]
        assert alias_service.count() == 0

    def test_forget_unknown_id_returns_false(self, alias_service: AliasService) -> None:
        """Удаление несуществующего идентификатора не вызывает ошибку."""
        assert alias_service.forget(999) is False


class TestDictionaryCrud:
    """Проверки явного управления словарём (раздел «Словарь товаров»)."""

    def test_add_creates_manual_entry(
        self, alias_service: AliasService, certificate_repository: CertificateRepository
    ) -> None:
        """Ручное добавление создаёт запись с полным доверием."""
        certificate = make_certificate("Товар", "/c/1.pdf")
        certificate_repository.add(certificate)

        alias = alias_service.add("Системное имя", certificate, brand="Balton")

        assert alias.is_manual is True
        assert alias.confidence == 100.0
        assert alias.brand == "Balton"

    def test_find_potential_duplicates_detects_close_variant(
        self, alias_service: AliasService, certificate_repository: CertificateRepository
    ) -> None:
        """Проверка дубликатов находит близкий, но не идентичный вариант."""
        certificate = make_certificate("Товар", "/c/1.pdf")
        certificate_repository.add(certificate)
        alias_service.add("TP Herbal 100ml", certificate)

        warning = alias_service.find_potential_duplicates("TP Herbal 100 ml")

        assert warning.has_matches

    def test_update_resyncs_pdf_name_on_certificate_change(
        self, alias_service: AliasService, certificate_repository: CertificateRepository
    ) -> None:
        """Изменение привязанного сертификата подтягивает актуальное имя PDF."""
        first = make_certificate("Товар A", "/c/1.pdf")
        first.pdf_name = "1.pdf"
        second = make_certificate("Товар B", "/c/2.pdf")
        second.pdf_name = "2.pdf"
        certificate_repository.add(first)
        certificate_repository.add(second)

        alias = alias_service.add("Системное имя", first)
        updated = alias_service.update(alias.id, certificate_id=second.id)  # type: ignore[arg-type]

        assert updated.certificate_id == second.id
        assert updated.target_pdf_name == "2.pdf"

    def test_bulk_delete_removes_multiple(
        self, alias_service: AliasService, certificate_repository: CertificateRepository
    ) -> None:
        """Массовое удаление через сервис убирает все указанные записи."""
        first = make_certificate("Товар A", "/c/1.pdf")
        second = make_certificate("Товар B", "/c/2.pdf")
        certificate_repository.add(first)
        certificate_repository.add(second)
        one = alias_service.add("Товар A", first)
        two = alias_service.add("Товар B", second)

        removed = alias_service.bulk_delete([one.id, two.id])  # type: ignore[list-item]

        assert removed == 2
        assert alias_service.count() == 0

    def test_undo_last_reverts_most_recent_action(
        self, alias_service: AliasService, certificate_repository: CertificateRepository
    ) -> None:
        """Отмена последнего действия восстанавливает словарь до предыдущего состояния."""
        certificate = make_certificate("Товар", "/c/1.pdf")
        certificate_repository.add(certificate)
        alias = alias_service.add("Товар", certificate)
        assert alias.id is not None
        alias_service.forget(alias.id)
        assert alias_service.count() == 0

        entry = alias_service.undo_last()

        assert entry is not None
        assert alias_service.count() == 1

    def test_undo_last_with_nothing_to_undo_returns_none(self, alias_service: AliasService) -> None:
        """Отмена без предшествующих действий не вызывает ошибку."""
        assert alias_service.undo_last() is None
