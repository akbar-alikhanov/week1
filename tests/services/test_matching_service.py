"""Тесты сервиса подбора сертификатов — ядра приложения."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from pathlib import Path

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
from app.repositories.certificate_product_repository import CertificateProductRepository
from app.services.matching_service import MatchingService
from tests.conftest import make_certificate

_TODAY = dt.date.today()
_FUTURE = _TODAY + dt.timedelta(days=365 * 3)
_NEAR_FUTURE = _TODAY + dt.timedelta(days=365 * 2)
_PAST = _TODAY - dt.timedelta(days=30)


@pytest.fixture
def matching_service(tmp_path: Path, database: Database) -> Iterator[MatchingService]:
    """Полностью собранный сервис подбора поверх временной базы данных."""
    certificates = CertificateProductRepository(database)
    aliases = AliasRepository(database)
    settings_service = SettingsService(tmp_path / "settings.json")
    settings_service.load()
    backend = EmbeddingBackend(enabled=False)
    vector_index = VectorIndex(backend, CacheRepository(database))

    service = MatchingService(certificates, aliases, settings_service, backend, vector_index)
    yield service


class TestAliasStage:
    """Проверки первого этапа конвейера — словаря соответствий.

    Архитектурное требование (не подлежит смягчению без явного пересмотра):
    словарь — абсолютный источник истины, а не ещё один источник кандидатов
    для взвешенной оценки. Если наименование заказа найдено в словаре, весь
    остальной подбор (RapidFuzz, Sentence Transformers, любая оценка «по
    процентам», пороги принятия решений) для этой строки не выполняется —
    в базе сертификатов ищут только строгим SQL-равенством наименования и
    объёма, зафиксированных в самой записи словаря, а выбор между найденными
    строками — только по ближайшему сроку годности. Каждый тест ниже
    проверяет одну грань именно этого требования.
    """

    def test_alias_matches_exact_name_and_volume(
        self,
        matching_service: MatchingService,
        certificate_repository: CertificateProductRepository,
        alias_repository: AliasRepository,
    ) -> None:
        """Базовый случай: точное совпадение наименования и объёма из словаря."""
        certificate = make_certificate(
            "Лечебные травы 100 мл",
            volume_ml=100.0,
            expiry_date=_FUTURE,
            certificate_number="aliased",
        )
        certificate_repository.replace_all([certificate])
        alias_repository.save(
            Alias(
                source_text="TP Herbal 100ml",
                target_name=certificate.product_name,
                volume_ml=100.0,
            )
        )

        result = matching_service.match_row(OrderRow(row_number=1, product_name="TP Herbal 100ml"))

        assert result.status is MatchStatus.MATCHED
        assert result.alias_applied
        assert result.certificate is not None
        assert result.certificate.certificate_number == "aliased"
        assert result.candidates[0].source is MatchSource.ALIAS

    def test_alias_ignores_lexically_similar_certificate_with_different_name(
        self,
        matching_service: MatchingService,
        certificate_repository: CertificateProductRepository,
        alias_repository: AliasRepository,
    ) -> None:
        """Псевдоним не подменяется лексически похожим, но не тем же товаром.

        RapidFuzz нашёл бы «TP Herbal 100ml» как почти точное совпадение —
        но раз строка распознана словарём, в дело идёт только запись
        словаря (другое, «настоящее» наименование), а лексически похожий
        сертификат вообще не рассматривается.
        """
        lookalike = make_certificate(
            "TP Herbal 100ml", volume_ml=100.0, expiry_date=_FUTURE, certificate_number="lookalike"
        )
        real_target = make_certificate(
            "Лечебные травы 100 мл", volume_ml=100.0, expiry_date=_FUTURE, certificate_number="real"
        )
        certificate_repository.replace_all([lookalike, real_target])
        alias_repository.save(
            Alias(
                source_text="TP Herbal 100ml",
                target_name=real_target.product_name,
                volume_ml=100.0,
            )
        )

        result = matching_service.match_row(OrderRow(row_number=1, product_name="TP Herbal 100ml"))

        assert result.certificate is not None
        assert result.certificate.certificate_number == "real"

    def test_alias_hit_is_registered(
        self,
        matching_service: MatchingService,
        certificate_repository: CertificateProductRepository,
        alias_repository: AliasRepository,
    ) -> None:
        """Применение псевдонима увеличивает счётчик его использований."""
        certificate = make_certificate(
            "Товар", volume_ml=1.0, expiry_date=_FUTURE, certificate_number="1"
        )
        certificate_repository.replace_all([certificate])
        alias = alias_repository.save(
            Alias(source_text="Псевдоним", target_name=certificate.product_name, volume_ml=1.0)
        )

        matching_service.match_row(OrderRow(row_number=1, product_name="Псевдоним"))

        refreshed = alias_repository.find_for_text("Псевдоним")[0]
        assert refreshed.hit_count == alias.hit_count + 1

    def test_alias_hit_is_registered_even_when_not_found(
        self,
        matching_service: MatchingService,
        alias_repository: AliasRepository,
    ) -> None:
        """Счётчик применений растёт и тогда, когда строгий поиск ничего не даёт.

        Псевдоним всё равно был решающим фактором для этой строки — он
        определённо исключил обращение к остальному конвейеру.
        """
        alias = alias_repository.save(
            Alias(source_text="TP Herbal 100ml", target_name="Товар, которого нет в базе")
        )

        matching_service.match_row(OrderRow(row_number=1, product_name="TP Herbal 100ml"))

        refreshed = alias_repository.find_for_text("TP Herbal 100ml")[0]
        assert refreshed.hit_count == alias.hit_count + 1

    def test_alias_picks_certificate_closest_to_requested_expiry(
        self,
        matching_service: MatchingService,
        certificate_repository: CertificateProductRepository,
        alias_repository: AliasRepository,
    ) -> None:
        """Среди строго совпавших по словарю строк базы выбирается ближайшая по сроку.

        Один и тот же товар подтверждён двумя строками базы (переизданный
        сертификат/другая партия) — псевдоним указывает на первую по
        наименованию, но в заказе запрошен срок, который точно совпадает со
        ВТОРОЙ. Должна вернуться именно она.
        """
        original = make_certificate(
            "Лечебные травы 100 мл",
            volume_ml=100.0,
            expiry_date=_FUTURE,
            certificate_number="original",
        )
        renewed = make_certificate(
            "Лечебные травы 100 мл",
            volume_ml=100.0,
            expiry_date=_NEAR_FUTURE,
            certificate_number="renewed",
        )
        certificate_repository.replace_all([original, renewed])
        alias_repository.save(
            Alias(source_text="TP Herbal 100ml", target_name=original.product_name, volume_ml=100.0)
        )

        result = matching_service.match_row(
            OrderRow(row_number=1, product_name="TP Herbal 100ml", requested_expiry=_NEAR_FUTURE)
        )

        assert result.status is MatchStatus.MATCHED
        assert result.certificate is not None
        assert result.certificate.certificate_number == "renewed"

    def test_alias_never_returns_ambiguous_even_with_close_candidates(
        self,
        matching_service: MatchingService,
        certificate_repository: CertificateProductRepository,
        alias_repository: AliasRepository,
    ) -> None:
        """Выбор среди строго совпавших строк базы детерминирован — не «требует проверки».

        Для обычных (не словарных) кандидатов близкие по оценке варианты
        дают статус AMBIGUOUS. Здесь наименование и объём уже подтверждены
        точным совпадением, поэтому несколько строк той же строгой группы
        не приводят к неоднозначности — решает только ближайший срок.
        """
        near = make_certificate(
            "Лечебные травы 100 мл",
            volume_ml=100.0,
            expiry_date=_NEAR_FUTURE,
            certificate_number="near",
        )
        far = make_certificate(
            "Лечебные травы 100 мл", volume_ml=100.0, expiry_date=_FUTURE, certificate_number="far"
        )
        certificate_repository.replace_all([near, far])
        alias_repository.save(
            Alias(source_text="TP Herbal 100ml", target_name=near.product_name, volume_ml=100.0)
        )

        result = matching_service.match_row(
            OrderRow(row_number=1, product_name="TP Herbal 100ml", requested_expiry=_NEAR_FUTURE)
        )

        assert result.status is MatchStatus.MATCHED
        assert result.certificate is not None
        assert result.certificate.certificate_number == "near"

    def test_alias_fefo_without_requested_expiry(
        self,
        matching_service: MatchingService,
        certificate_repository: CertificateProductRepository,
        alias_repository: AliasRepository,
    ) -> None:
        """Без требуемого срока выбирается самая ранняя из строго совпавших строк (FEFO)."""
        soon = make_certificate(
            "Лечебные травы 100 мл",
            volume_ml=100.0,
            expiry_date=_NEAR_FUTURE,
            certificate_number="soon",
        )
        later = make_certificate(
            "Лечебные травы 100 мл",
            volume_ml=100.0,
            expiry_date=_FUTURE,
            certificate_number="later",
        )
        certificate_repository.replace_all([soon, later])
        alias_repository.save(
            Alias(source_text="TP Herbal 100ml", target_name=later.product_name, volume_ml=100.0)
        )

        result = matching_service.match_row(OrderRow(row_number=1, product_name="TP Herbal 100ml"))

        assert result.certificate is not None
        assert result.certificate.certificate_number == "soon"

    def test_alias_survives_excel_reimport_with_new_ids(
        self,
        matching_service: MatchingService,
        certificate_repository: CertificateProductRepository,
        alias_repository: AliasRepository,
    ) -> None:
        """Псевдоним переживает переимпорт Excel-базы, даже если id строк изменились.

        Полный переимпорт (:meth:`CertificateProductRepository.replace_all`)
        всегда выдаёт всем строкам новые идентификаторы — подбор по словарю не
        должен от этого сломаться, так как он ищет по наименованию и объёму,
        а не по сохранённому id какой-либо конкретной строки.
        """
        original = make_certificate(
            "Лечебные травы 100 мл",
            volume_ml=100.0,
            expiry_date=_FUTURE,
            certificate_number="original",
        )
        certificate_repository.replace_all([original])
        alias_repository.save(
            Alias(source_text="TP Herbal 100ml", target_name=original.product_name, volume_ml=100.0)
        )

        matching_service.invalidate()
        replacement = make_certificate(
            "Лечебные травы 100 мл",
            volume_ml=100.0,
            expiry_date=_FUTURE,
            certificate_number="replacement",
        )
        certificate_repository.replace_all([replacement])

        result = matching_service.match_row(OrderRow(row_number=1, product_name="TP Herbal 100ml"))

        assert result.alias_applied
        assert result.certificate is not None
        assert result.certificate.certificate_number == "replacement"

    def test_alias_skips_expired_certificate_in_favor_of_valid_one(
        self,
        matching_service: MatchingService,
        certificate_repository: CertificateProductRepository,
        alias_repository: AliasRepository,
    ) -> None:
        """Просроченная строка базы, найденная по данным псевдонима, отбраковывается."""
        expired = make_certificate(
            "Лечебные травы 100 мл",
            volume_ml=100.0,
            expiry_date=_PAST,
            certificate_number="expired",
        )
        valid = make_certificate(
            "Лечебные травы 100 мл",
            volume_ml=100.0,
            expiry_date=_FUTURE,
            certificate_number="valid",
        )
        certificate_repository.replace_all([expired, valid])
        alias_repository.save(
            Alias(source_text="TP Herbal 100ml", target_name=expired.product_name, volume_ml=100.0)
        )

        result = matching_service.match_row(OrderRow(row_number=1, product_name="TP Herbal 100ml"))

        assert result.alias_applied
        assert result.certificate is not None
        assert result.certificate.certificate_number == "valid"

    def test_alias_requires_exact_volume_not_within_tolerance(
        self,
        matching_service: MatchingService,
        certificate_repository: CertificateProductRepository,
        alias_repository: AliasRepository,
    ) -> None:
        """Объём сравнивается строгим равенством, а не в пределах допуска на округление.

        99.9 мл — практически то же самое, что 100 мл, и обычный подбор счёл
        бы это совпадением в пределах обычного допуска. Здесь — нет: словарь
        требует точного равенства, «почти совпадающий» объём не подходит.
        """
        almost = make_certificate(
            "Товар Х", volume_ml=99.9, expiry_date=_FUTURE, certificate_number="almost"
        )
        exact = make_certificate(
            "Товар Х", volume_ml=100.0, expiry_date=_FUTURE, certificate_number="exact"
        )
        certificate_repository.replace_all([almost, exact])
        alias_repository.save(
            Alias(source_text="TP Kh 100ml", target_name="Товар Х", volume_ml=100.0)
        )

        result = matching_service.match_row(OrderRow(row_number=1, product_name="TP Kh 100ml"))

        assert result.certificate is not None
        assert result.certificate.certificate_number == "exact"

    def test_alias_matches_by_dictionary_volume_even_when_order_text_implies_other_volume(
        self,
        matching_service: MatchingService,
        certificate_repository: CertificateProductRepository,
        alias_repository: AliasRepository,
    ) -> None:
        """Подбор идёт по объёму, зафиксированному в словаре, а не по тексту заказа.

        В строке заказа явно написано «150ml», но псевдоним закрепляет за
        этим текстом товар объёмом 100 мл — должна найтись именно
        100-миллилитровая строка базы, объём из текста заказа не участвует.
        """
        wrong_volume = make_certificate(
            "Товар Х", volume_ml=150.0, expiry_date=_FUTURE, certificate_number="150ml"
        )
        right_volume = make_certificate(
            "Товар Х", volume_ml=100.0, expiry_date=_FUTURE, certificate_number="100ml"
        )
        certificate_repository.replace_all([wrong_volume, right_volume])
        alias_repository.save(
            Alias(source_text="TP Kh 150ml", target_name="Товар Х", volume_ml=100.0)
        )

        result = matching_service.match_row(OrderRow(row_number=1, product_name="TP Kh 150ml"))

        assert result.alias_applied
        assert result.certificate is not None
        assert result.certificate.certificate_number == "100ml"

    def test_alias_without_dictionary_volume_matches_only_volumeless_certificates(
        self,
        matching_service: MatchingService,
        certificate_repository: CertificateProductRepository,
        alias_repository: AliasRepository,
    ) -> None:
        """Если словарь не фиксирует объём, сравнение всё равно строгое — «пусто == пусто»."""
        with_volume = make_certificate(
            "Товар Y", volume_ml=50.0, expiry_date=_FUTURE, certificate_number="with-volume"
        )
        without_volume = make_certificate(
            "Товар Y", expiry_date=_FUTURE, certificate_number="no-volume"
        )
        certificate_repository.replace_all([with_volume, without_volume])
        alias_repository.save(Alias(source_text="TP Y", target_name="Товар Y"))

        result = matching_service.match_row(OrderRow(row_number=1, product_name="TP Y"))

        assert result.certificate is not None
        assert result.certificate.certificate_number == "no-volume"

    def test_alias_with_dictionary_volume_and_no_matching_certificate_is_not_found(
        self,
        matching_service: MatchingService,
        certificate_repository: CertificateProductRepository,
        alias_repository: AliasRepository,
    ) -> None:
        """Если строки базы на объём, зафиксированный в словаре, нет — статус «не найден»."""
        certificate_repository.replace_all(
            [
                make_certificate(
                    "Товар Х", volume_ml=150.0, expiry_date=_FUTURE, certificate_number="150ml"
                )
            ]
        )
        alias_repository.save(
            Alias(source_text="TP Kh 100ml", target_name="Товар Х", volume_ml=100.0)
        )

        result = matching_service.match_row(OrderRow(row_number=1, product_name="TP Kh 100ml"))

        assert result.alias_applied
        assert result.status is MatchStatus.NOT_FOUND
        assert result.certificate is None
        assert result.note == "Не найден сертификат для товара из словаря: «Товар Х, 100 мл»"

    def test_alias_strict_miss_does_not_fall_back_to_fuzzy_search(
        self,
        matching_service: MatchingService,
        certificate_repository: CertificateProductRepository,
        alias_repository: AliasRepository,
    ) -> None:
        """Провал строгого подбора по словарю не подменяется похожим товаром.

        Есть лексически похожая строка базы другого объёма, которую обычный
        нечёткий поиск нашёл бы — но раз товар распознан по словарю, подбор
        должен остановиться на «не найдено», а не тихо подставить её.
        """
        lookalike = make_certificate(
            "Товар Х", volume_ml=250.0, expiry_date=_FUTURE, certificate_number="lookalike"
        )
        certificate_repository.replace_all([lookalike])
        alias_repository.save(
            Alias(source_text="TP Kh 100ml", target_name="Товар Х", volume_ml=100.0)
        )

        result = matching_service.match_row(OrderRow(row_number=1, product_name="TP Kh 100ml"))

        assert result.status is MatchStatus.NOT_FOUND
        assert result.certificate is None

    def test_alias_no_certificates_at_all_is_not_found(
        self,
        matching_service: MatchingService,
        alias_repository: AliasRepository,
    ) -> None:
        """Пустая база сертификатов не роняет подбор по словарю — просто «не найдено»."""
        alias_repository.save(
            Alias(source_text="TP Kh 100ml", target_name="Товар Х", volume_ml=100.0)
        )

        result = matching_service.match_row(OrderRow(row_number=1, product_name="TP Kh 100ml"))

        assert result.status is MatchStatus.NOT_FOUND


class TestLexicalStage:
    """Проверки лексического подбора и автоматического принятия решений."""

    def test_exact_name_and_volume_match_is_auto_accepted(
        self,
        matching_service: MatchingService,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Точное совпадение наименования и объёма принимается автоматически."""
        certificate_repository.replace_all(
            [make_certificate("Лечебные травы, сироп 100 мл", volume_ml=100.0, expiry_date=_FUTURE)]
        )
        result = matching_service.match_row(
            OrderRow(row_number=1, product_name="Лечебные травы, сироп 100 мл")
        )
        assert result.status is MatchStatus.MATCHED
        assert result.certificate is not None
        assert result.score > 0.9

    def test_unrelated_product_not_found(
        self,
        matching_service: MatchingService,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Совершенно непохожий товар не подбирается."""
        certificate_repository.replace_all(
            [make_certificate("Лечебные травы, сироп 100 мл", volume_ml=100.0, expiry_date=_FUTURE)]
        )
        result = matching_service.match_row(
            OrderRow(row_number=1, product_name="Шампунь дегтярный 250 мл")
        )
        assert result.status is MatchStatus.NOT_FOUND

    def test_regression_shared_volume_does_not_cause_false_match(
        self,
        matching_service: MatchingService,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Товары с общим объёмом, но разным названием, не путаются друг с другом.

        Исходный дефект: «Крем-гель для душа морской 400 мл» ошибочно
        сопоставлялся с «Сироп шиповника 250 мл» на основании частичного
        текстового совпадения, усиленного объёмным сходством.
        """
        certificate_repository.replace_all(
            [make_certificate("Сироп шиповника 250 мл", volume_ml=250.0, expiry_date=_FUTURE)]
        )
        result = matching_service.match_row(
            OrderRow(row_number=1, product_name="Крем-гель для душа морской 400 мл")
        )
        assert result.status is MatchStatus.NOT_FOUND

    def test_strict_volume_prevents_wrong_size_auto_accept(
        self,
        matching_service: MatchingService,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Строка базы другой фасовки того же товара не принимается автоматически."""
        certificate_repository.replace_all(
            [make_certificate("Лечебные травы, сироп 150 мл", volume_ml=150.0, expiry_date=_FUTURE)]
        )
        result = matching_service.match_row(
            OrderRow(row_number=1, product_name="Лечебные травы, сироп 100 мл")
        )
        assert result.status is not MatchStatus.MATCHED

    def test_expired_certificate_excluded_by_default(
        self,
        matching_service: MatchingService,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Просроченная строка базы не подбирается при настройках по умолчанию."""
        certificate_repository.replace_all(
            [make_certificate("Товар", volume_ml=100.0, expiry_date=_PAST)]
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
        self,
        matching_service: MatchingService,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Несколько строк базы на разные товары с близкой оценкой требуют проверки."""
        certificate_repository.replace_all(
            [
                make_certificate("Крем детский увлажняющий", volume_ml=45.0, expiry_date=_FUTURE),
                make_certificate("Крем детский защитный", volume_ml=45.0, expiry_date=_NEAR_FUTURE),
            ]
        )
        result = matching_service.match_row(
            OrderRow(row_number=1, product_name="Крем детский 45 г")
        )
        assert result.status is MatchStatus.AMBIGUOUS
        assert len(result.candidates) >= 2

    def test_same_product_different_expiry_auto_resolved_by_fefo(
        self,
        matching_service: MatchingService,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Один и тот же товар с разными сроками разрешается автоматически (FEFO)."""
        near = make_certificate(
            "Лечебные травы 100 мл",
            volume_ml=100.0,
            expiry_date=_NEAR_FUTURE,
            certificate_number="near",
        )
        far = make_certificate(
            "Лечебные травы 100 мл", volume_ml=100.0, expiry_date=_FUTURE, certificate_number="far"
        )
        certificate_repository.replace_all([near, far])

        result = matching_service.match_row(
            OrderRow(row_number=1, product_name="Лечебные травы 100 мл")
        )

        assert result.status is MatchStatus.MATCHED
        assert result.certificate is not None
        assert result.certificate.certificate_number == "near"


class TestFindCandidates:
    """Проверки поиска кандидатов для окна неоднозначного выбора."""

    def test_includes_other_volumes_of_same_product(
        self,
        matching_service: MatchingService,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Результат включает соседние фасовки того же товара."""
        certificate_repository.replace_all(
            [
                make_certificate(
                    "Лечебные травы, сироп 100 мл",
                    volume_ml=100.0,
                    expiry_date=_FUTURE,
                    certificate_number="100",
                ),
                make_certificate(
                    "Лечебные травы, сироп 150 мл",
                    volume_ml=150.0,
                    expiry_date=_FUTURE,
                    certificate_number="150",
                ),
            ]
        )
        candidates = matching_service.find_candidates(
            "Лечебные травы, сироп", include_other_volumes=True
        )
        numbers = {candidate.certificate.certificate_number for candidate in candidates}
        assert "100" in numbers
        assert "150" in numbers


class TestInvalidate:
    """Проверки инвалидации индексов подбора."""

    def test_invalidate_forces_rebuild_on_next_prepare(
        self,
        matching_service: MatchingService,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """После invalidate новый сертификат попадает в индекс при следующем prepare."""
        matching_service.prepare()
        assert matching_service.indexed_count == 0

        certificate_repository.replace_all([make_certificate("Новый товар", expiry_date=_FUTURE)])
        matching_service.invalidate()
        matching_service.prepare()

        assert matching_service.indexed_count == 1
