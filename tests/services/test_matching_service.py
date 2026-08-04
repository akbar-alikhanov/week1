"""Тесты сервиса подбора сертификатов — ядра приложения."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

import pytest

from app.ai.embeddings import EmbeddingBackend
from app.ai.vector_index import VectorIndex
from app.config.settings import SettingsService
from app.database.connection import Database
from app.models.alias import Alias
from app.models.matching import MatchSource, MatchStatus
from app.models.order import OrderRow
from app.repositories.alias_repository import AliasRepository
from app.repositories.cache_repository import CacheRepository
from app.repositories.certificate_repository import CertificateRepository
from app.services.matching_service import MatchingService
from tests.conftest import make_certificate

_TODAY = dt.date.today()
_FUTURE = _TODAY + dt.timedelta(days=365 * 3)
_NEAR_FUTURE = _TODAY + dt.timedelta(days=365 * 2)
_PAST = _TODAY - dt.timedelta(days=30)


@pytest.fixture
def matching_service(tmp_path, database: Database) -> Iterator[MatchingService]:
    """Полностью собранный сервис подбора поверх временной базы данных."""
    certificates = CertificateRepository(database)
    aliases = AliasRepository(database)
    settings_service = SettingsService(tmp_path / "settings.json")
    settings_service.load()
    backend = EmbeddingBackend(enabled=False)
    vector_index = VectorIndex(backend, CacheRepository(database))

    service = MatchingService(certificates, aliases, settings_service, backend, vector_index)
    yield service


class TestAliasStage:
    """Проверки первого этапа конвейера — таблицы псевдонимов."""

    def test_alias_takes_priority_over_everything(
        self,
        matching_service: MatchingService,
        certificate_repository: CertificateRepository,
        alias_repository: AliasRepository,
    ) -> None:
        """Псевдоним применяется даже при наличии лексически более похожего кандидата."""
        exact_match = make_certificate(
            "TP Herbal 100ml",
            "/c/exact.pdf",
            volume_value=100.0,
            volume_unit="ml",
            expiry_date=_FUTURE,
        )
        aliased_target = make_certificate(
            "Лечебные травы 100 мл",
            "/c/aliased.pdf",
            volume_value=100.0,
            volume_unit="ml",
            expiry_date=_FUTURE,
        )
        certificate_repository.upsert_many([exact_match, aliased_target])
        alias_repository.save(
            Alias(
                source_text="TP Herbal 100ml",
                certificate_id=aliased_target.id,
                target_name=aliased_target.product_name,
                target_pdf_name=aliased_target.pdf_name,
            )
        )

        result = matching_service.match_row(OrderRow(row_number=1, product_name="TP Herbal 100ml"))

        assert result.status is MatchStatus.MATCHED
        assert result.alias_applied
        assert result.certificate is not None
        assert result.certificate.pdf_path == "/c/aliased.pdf"
        assert result.candidates[0].source is MatchSource.ALIAS

    def test_alias_hit_is_registered(
        self,
        matching_service: MatchingService,
        certificate_repository: CertificateRepository,
        alias_repository: AliasRepository,
    ) -> None:
        """Применение псевдонима увеличивает счётчик его использований."""
        certificate = make_certificate("Товар", "/c/1.pdf", expiry_date=_FUTURE)
        certificate_repository.add(certificate)
        alias = alias_repository.save(Alias(source_text="Псевдоним", certificate_id=certificate.id))

        matching_service.match_row(OrderRow(row_number=1, product_name="Псевдоним"))

        refreshed = alias_repository.find_for_text("Псевдоним")[0]
        assert refreshed.hit_count == alias.hit_count + 1


class TestLexicalStage:
    """Проверки лексического подбора и автоматического принятия решений."""

    def test_exact_name_and_volume_match_is_auto_accepted(
        self, matching_service: MatchingService, certificate_repository: CertificateRepository
    ) -> None:
        """Точное совпадение наименования и объёма принимается автоматически."""
        certificate_repository.add(
            make_certificate(
                "Лечебные травы, сироп 100 мл",
                "/c/1.pdf",
                volume_value=100.0,
                volume_unit="ml",
                expiry_date=_FUTURE,
            )
        )
        result = matching_service.match_row(
            OrderRow(row_number=1, product_name="Лечебные травы, сироп 100 мл")
        )
        assert result.status is MatchStatus.MATCHED
        assert result.certificate is not None
        assert result.score > 0.9

    def test_unrelated_product_not_found(
        self, matching_service: MatchingService, certificate_repository: CertificateRepository
    ) -> None:
        """Совершенно непохожий товар не подбирается."""
        certificate_repository.add(
            make_certificate(
                "Лечебные травы, сироп 100 мл",
                "/c/1.pdf",
                volume_value=100.0,
                volume_unit="ml",
                expiry_date=_FUTURE,
            )
        )
        result = matching_service.match_row(
            OrderRow(row_number=1, product_name="Шампунь дегтярный 250 мл")
        )
        assert result.status is MatchStatus.NOT_FOUND

    def test_regression_shared_volume_does_not_cause_false_match(
        self, matching_service: MatchingService, certificate_repository: CertificateRepository
    ) -> None:
        """Товары с общим объёмом, но разным названием, не путаются друг с другом.

        Исходный дефект: «Крем-гель для душа морской 400 мл» ошибочно
        сопоставлялся с «Сироп шиповника 250 мл» на основании частичного
        текстового совпадения, усиленного объёмным сходством.
        """
        certificate_repository.add(
            make_certificate(
                "Сироп шиповника 250 мл",
                "/c/rosehip.pdf",
                volume_value=250.0,
                volume_unit="ml",
                expiry_date=_FUTURE,
            )
        )
        result = matching_service.match_row(
            OrderRow(row_number=1, product_name="Крем-гель для душа морской 400 мл")
        )
        assert result.status is MatchStatus.NOT_FOUND

    def test_strict_volume_prevents_wrong_size_auto_accept(
        self, matching_service: MatchingService, certificate_repository: CertificateRepository
    ) -> None:
        """Сертификат другой фасовки того же товара не принимается автоматически."""
        certificate_repository.add(
            make_certificate(
                "Лечебные травы, сироп 150 мл",
                "/c/150.pdf",
                volume_value=150.0,
                volume_unit="ml",
                expiry_date=_FUTURE,
            )
        )
        result = matching_service.match_row(
            OrderRow(row_number=1, product_name="Лечебные травы, сироп 100 мл")
        )
        assert result.status is not MatchStatus.MATCHED

    def test_expired_certificate_excluded_by_default(
        self, matching_service: MatchingService, certificate_repository: CertificateRepository
    ) -> None:
        """Просроченный сертификат не подбирается при настройках по умолчанию."""
        certificate_repository.add(
            make_certificate(
                "Товар", "/c/1.pdf", volume_value=100.0, volume_unit="ml", expiry_date=_PAST
            )
        )
        result = matching_service.match_row(OrderRow(row_number=1, product_name="Товар 100 мл"))
        assert result.status is MatchStatus.NOT_FOUND

    def test_empty_row_is_skipped(self, matching_service: MatchingService) -> None:
        """Пустая строка заказа помечается как пропущенная, без обращения к базе."""
        result = matching_service.match_row(OrderRow(row_number=1, product_name=""))
        assert result.status is MatchStatus.SKIPPED


class TestAmbiguity:
    """Проверки распознавания неоднозначных ситуаций."""

    def test_multiple_close_candidates_marked_ambiguous(
        self, matching_service: MatchingService, certificate_repository: CertificateRepository
    ) -> None:
        """Несколько сертификатов на разные товары с близкой оценкой требуют проверки."""
        certificate_repository.add(
            make_certificate(
                "Крем детский увлажняющий",
                "/c/1.pdf",
                volume_value=45.0,
                volume_unit="g",
                expiry_date=_FUTURE,
            )
        )
        certificate_repository.add(
            make_certificate(
                "Крем детский защитный",
                "/c/2.pdf",
                volume_value=45.0,
                volume_unit="g",
                expiry_date=_NEAR_FUTURE,
            )
        )
        result = matching_service.match_row(
            OrderRow(row_number=1, product_name="Крем детский 45 г")
        )
        assert result.status is MatchStatus.AMBIGUOUS
        assert len(result.candidates) >= 2

    def test_same_product_different_expiry_auto_resolved_by_fefo(
        self, matching_service: MatchingService, certificate_repository: CertificateRepository
    ) -> None:
        """Один и тот же товар с разными сроками разрешается автоматически (FEFO)."""
        near = make_certificate(
            "Лечебные травы 100 мл",
            "/c/near.pdf",
            volume_value=100.0,
            volume_unit="ml",
            expiry_date=_NEAR_FUTURE,
        )
        far = make_certificate(
            "Лечебные травы 100 мл",
            "/c/far.pdf",
            volume_value=100.0,
            volume_unit="ml",
            expiry_date=_FUTURE,
        )
        certificate_repository.upsert_many([near, far])

        result = matching_service.match_row(
            OrderRow(row_number=1, product_name="Лечебные травы 100 мл")
        )

        assert result.status is MatchStatus.MATCHED
        assert result.certificate is not None
        assert result.certificate.pdf_path == "/c/near.pdf"


class TestFindCandidates:
    """Проверки поиска кандидатов для окна неоднозначного выбора."""

    def test_includes_other_volumes_of_same_product(
        self, matching_service: MatchingService, certificate_repository: CertificateRepository
    ) -> None:
        """Результат включает соседние фасовки того же товара."""
        certificate_repository.add(
            make_certificate(
                "Лечебные травы, сироп 100 мл",
                "/c/100.pdf",
                volume_value=100.0,
                volume_unit="ml",
                expiry_date=_FUTURE,
            )
        )
        certificate_repository.add(
            make_certificate(
                "Лечебные травы, сироп 150 мл",
                "/c/150.pdf",
                volume_value=150.0,
                volume_unit="ml",
                expiry_date=_FUTURE,
            )
        )
        candidates = matching_service.find_candidates(
            "Лечебные травы, сироп", include_other_volumes=True
        )
        paths = {candidate.certificate.pdf_path for candidate in candidates}
        assert "/c/100.pdf" in paths
        assert "/c/150.pdf" in paths


class TestInvalidate:
    """Проверки инвалидации индексов подбора."""

    def test_invalidate_forces_rebuild_on_next_prepare(
        self, matching_service: MatchingService, certificate_repository: CertificateRepository
    ) -> None:
        """После invalidate новый сертификат попадает в индекс при следующем prepare."""
        matching_service.prepare()
        assert matching_service.indexed_count == 0

        certificate_repository.add(make_certificate("Новый товар", "/c/1.pdf", expiry_date=_FUTURE))
        matching_service.invalidate()
        matching_service.prepare()

        assert matching_service.indexed_count == 1
