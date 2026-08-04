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
