"""Тесты нового этапа подбора срока годности (ДО поиска сертификата).

Обёртка вокруг настоящего, неизменённого ``MatchingService``: пробный вызов
``match_row`` для конкретной кандидатной даты либо находит сертификат
(``MatchStatus.MATCHED``), либо нет — никакого мока подбора здесь нет,
поведение проверяется на реальном алгоритме с реальной (хоть и минимальной)
базой сертификатов. Это осознанный выбор: тестировать нужно именно то, как
новый этап УЖИВАЕТСЯ со старым алгоритмом, а не то, как вёл бы себя мок.

Даты сертификатов и кандидатов подобраны так, чтобы попадание/непопадание в
допуск срока (``expiry_tolerance_days``) было однозначным, без балансирования
на границе порогов: совпадающая дата всегда даёт совпадение по сроку 1.0,
а сильно удалённая (годы, не дни) — оценку около нижней границы, независимо
от мелких изменений весов или порогов по умолчанию.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from app.ai.embeddings import EmbeddingBackend
from app.ai.vector_index import VectorIndex
from app.config.settings import SettingsService
from app.core.events import ProgressReporter, ProgressUpdate
from app.database.connection import Database
from app.models.order import OrderRow
from app.repositories.alias_repository import AliasRepository
from app.repositories.certificate_product_repository import CertificateProductRepository
from app.repositories.expiry_stock_repository import ExpiryStockRepository
from app.services.expiry_resolution_service import ExpiryExclusion, ExpiryResolutionService
from app.services.matching_service import MatchingService
from tests.conftest import make_certificate, make_expiry_entry

#: Товар с объёмом в названии — совпадение объёма 1.0 гарантированно (не
#: нейтральное значение по умолчанию), поэтому итоговая оценка предсказуема.
_PRODUCT = "Крем детский 100 мл"


def _make_matching_service(database: Database, tmp_path: Path) -> MatchingService:
    """Собирает минимальный, полностью настоящий сервис подбора сертификата.

    Используется только для пробных вызовов ``match_row`` внутри
    :class:`ExpiryResolutionService` — сам сервис подбора этим не изменяется
    и не подменяется.
    """
    settings_service = SettingsService(tmp_path / "settings.json")
    settings_service.load()
    backend = EmbeddingBackend(enabled=False)
    return MatchingService(
        CertificateProductRepository(database),
        AliasRepository(database),
        settings_service,
        backend,
        VectorIndex(backend, None),
    )


@pytest.fixture
def expiry_resolution_service(
    database: Database, expiry_stock_repository: ExpiryStockRepository, tmp_path: Path
) -> ExpiryResolutionService:
    """Собранный сервис подбора срока годности поверх временной базы."""
    return ExpiryResolutionService(
        expiry_stock_repository, _make_matching_service(database, tmp_path)
    )


def _row(
    row_number: int,
    *,
    product_name: str = _PRODUCT,
    quantity: float = 50,
    requested_expiry: dt.date | None = None,
) -> OrderRow:
    """Создаёт строку заказа для тестов подбора срока годности."""
    return OrderRow(
        row_number=row_number,
        product_name=product_name,
        quantity=quantity,
        requested_expiry=requested_expiry,
    )


class TestPicksNewestSufficientDate:
    """Успешный подбор: срок найден, сертификат подтверждён, товар передаётся дальше."""

    def test_single_batch_with_matching_certificate(
        self,
        expiry_resolution_service: ExpiryResolutionService,
        expiry_stock_repository: ExpiryStockRepository,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Единственная партия с достаточным количеством и подтверждённым сроком принимается."""
        certificate_repository.replace_all(
            [make_certificate(_PRODUCT, expiry_date=dt.date(2027, 6, 1))]
        )
        expiry_stock_repository.replace_all(
            [make_expiry_entry(_PRODUCT, expiry_date=dt.date(2027, 6, 1), quantity=100)]
        )

        row = _row(1, quantity=50)
        excluded = expiry_resolution_service.resolve_rows([row])

        assert excluded == {}
        assert row.requested_expiry == dt.date(2027, 6, 1)

    def test_prefers_newest_date_without_trying_older(
        self,
        expiry_resolution_service: ExpiryResolutionService,
        expiry_stock_repository: ExpiryStockRepository,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Из двух годных по количеству партий выбирается более новая партия.

        Сертификат существует только под срок новой партии; срок старой
        партии сознательно выбран очень далёким (годы, а не дни) от
        единственного сертификата в базе — если бы алгоритм ошибочно
        предпочёл более старую партию, пробный подбор для нового срока
        никогда бы не потребовался, а старая партия не прошла бы пробный
        подбор (сертификат на такую дату не наберёт нужной оценки), и
        строка оказалась бы исключена. Раз строка успешно проходит —
        значит выбрана именно новая партия.
        """
        certificate_repository.replace_all(
            [make_certificate(_PRODUCT, expiry_date=dt.date(2028, 1, 1))]
        )
        expiry_stock_repository.replace_all(
            [
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2028, 1, 1), quantity=100),
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2020, 1, 1), quantity=100),
            ]
        )

        row = _row(1, quantity=50)
        excluded = expiry_resolution_service.resolve_rows([row])

        assert excluded == {}
        assert row.requested_expiry == dt.date(2028, 1, 1)


class TestFallsBackOnInsufficientQuantity:
    """Ветка «количества не хватает на этом сроке — перейти к следующему»."""

    def test_skips_newest_batch_when_quantity_insufficient(
        self,
        expiry_resolution_service: ExpiryResolutionService,
        expiry_stock_repository: ExpiryStockRepository,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Партия с недостаточным количеством пропускается в пользу более старой."""
        certificate_repository.replace_all(
            [make_certificate(_PRODUCT, expiry_date=dt.date(2027, 1, 1))]
        )
        expiry_stock_repository.replace_all(
            [
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2028, 1, 1), quantity=5),
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2027, 1, 1), quantity=100),
            ]
        )

        row = _row(1, quantity=50)
        excluded = expiry_resolution_service.resolve_rows([row])

        assert excluded == {}
        assert row.requested_expiry == dt.date(2027, 1, 1)


class TestFallsBackWhenCertificateNotFoundForDate:
    """Ветка «сертификат не найден на этот срок — перейти к следующему»."""

    def test_older_date_used_when_newest_fails_trial(
        self,
        expiry_resolution_service: ExpiryResolutionService,
        expiry_stock_repository: ExpiryStockRepository,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Обе партии годны по количеству, но пробный подбор проходит только старая.

        Единственный сертификат в базе действителен на 2027-06-01. Срок
        новой партии (2032-06-01) намеренно удалён на годы — пробный подбор
        для него не наберёт проходной балл (не ``MATCHED``), и алгоритм
        обязан вернуться к старой партии, чей срок совпадает с сертификатом
        день в день.
        """
        certificate_repository.replace_all(
            [make_certificate(_PRODUCT, expiry_date=dt.date(2027, 6, 1))]
        )
        expiry_stock_repository.replace_all(
            [
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2032, 6, 1), quantity=100),
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2027, 6, 1), quantity=100),
            ]
        )

        row = _row(1, quantity=50)
        excluded = expiry_resolution_service.resolve_rows([row])

        assert excluded == {}
        assert row.requested_expiry == dt.date(2027, 6, 1)

    def test_no_certificate_for_any_sufficient_date_excludes_row(
        self,
        expiry_resolution_service: ExpiryResolutionService,
        expiry_stock_repository: ExpiryStockRepository,
    ) -> None:
        """Если ни для одного годного по количеству срока сертификат не находится — исключение.

        В базе сертификатов вообще нет строк для этого товара — символизирует
        случай, когда явно правильный по остаткам подбор всё равно не может
        завершиться, потому что сертификата попросту не существует ни на одну
        из дат. Это не тот же случай, что «товара нет в базе сроков» —
        сертификата не хватает на этапе поиска, а не на этапе учёта остатков.
        """
        expiry_stock_repository.replace_all(
            [
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2028, 1, 1), quantity=100),
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2027, 1, 1), quantity=100),
            ]
        )

        row = _row(1, quantity=50)
        excluded = expiry_resolution_service.resolve_rows([row])

        assert excluded == {
            1: ExpiryExclusion(
                note="Ни для одного срока с достаточным количеством не найден сертификат."
            )
        }
        assert excluded[1].not_in_database is False
        assert row.requested_expiry is None


class TestProductNotInDatabase:
    """Ветка «товар отсутствует в базе сроков» — особое форматирование результата."""

    def test_excludes_with_not_in_database_flag(
        self,
        expiry_resolution_service: ExpiryResolutionService,
        expiry_stock_repository: ExpiryStockRepository,
    ) -> None:
        """Товар, которого нет в базе сроков вообще, помечается отдельным флагом."""
        expiry_stock_repository.replace_all(
            [make_expiry_entry("Другой товар", expiry_date=dt.date(2027, 1, 1), quantity=100)]
        )

        row = _row(1, product_name=_PRODUCT, quantity=50)
        excluded = expiry_resolution_service.resolve_rows([row])

        assert excluded == {
            1: ExpiryExclusion(note="Товар отсутствует в базе сроков.", not_in_database=True)
        }
        assert row.requested_expiry is None


class TestInsufficientQuantityEverywhere:
    """Ветка «по сумме хватило бы, но по отдельности — нет» (пока не реализовано)."""

    def test_partial_batches_are_excluded_without_summing(
        self,
        expiry_resolution_service: ExpiryResolutionService,
        expiry_stock_repository: ExpiryStockRepository,
    ) -> None:
        """Ни одна партия не хватает по отдельности — строка помечается на ручную обработку.

        По ТЗ это осознанно нереализованная логика частичного резервирования
        по нескольким срокам сразу («ничего пока не делать») — товар просто
        помечается как требующий ручной обработки, суммирование остатков не
        выполняется.
        """
        expiry_stock_repository.replace_all(
            [
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2028, 1, 1), quantity=20),
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2027, 1, 1), quantity=25),
            ]
        )

        row = _row(1, quantity=40)
        excluded = expiry_resolution_service.resolve_rows([row])

        assert excluded == {
            1: ExpiryExclusion(
                note="Недостаточное количество ни на одном сроке базы — требуется ручная обработка."
            )
        }
        assert excluded[1].not_in_database is False
        assert row.requested_expiry is None


class TestExistingRequestedExpiryIsNeverTouched:
    """Строки с уже указанным сроком не проходят через новый этап вообще."""

    def test_short_circuits_even_if_product_missing_from_stock(
        self,
        expiry_resolution_service: ExpiryResolutionService,
        expiry_stock_repository: ExpiryStockRepository,
    ) -> None:
        """Уже указанный в заказе срок не проверяется и не может быть исключён.

        База сроков годности не пуста (иначе сработал бы быстрый путь
        «функция не настроена» — см. :class:`TestInertWhenDatabaseEmpty`), но
        не содержит этого товара вообще. Если бы короткое замыкание не
        сработало, строка была бы ошибочно помечена «товар отсутствует в
        базе сроков» — этого происходить не должно: заказ уже содержит
        осознанный выбор человека.
        """
        expiry_stock_repository.replace_all(
            [make_expiry_entry("Другой товар", expiry_date=dt.date(2027, 1, 1), quantity=100)]
        )

        row = _row(1, product_name=_PRODUCT, requested_expiry=dt.date(2030, 1, 1))
        excluded = expiry_resolution_service.resolve_rows([row])

        assert excluded == {}
        assert row.requested_expiry == dt.date(2030, 1, 1)


class TestInertWhenDatabaseEmpty:
    """Пустая (ни разу не импортированная) база сроков годности ничего не меняет."""

    def test_returns_empty_dict_without_touching_rows(
        self, expiry_resolution_service: ExpiryResolutionService
    ) -> None:
        """Ни одна строка не исключается и не изменяется, если база вообще не настроена."""
        untouched = _row(1, product_name=_PRODUCT, requested_expiry=None)
        already_set = _row(2, product_name="Ещё товар", requested_expiry=dt.date(2029, 1, 1))

        excluded = expiry_resolution_service.resolve_rows([untouched, already_set])

        assert excluded == {}
        assert untouched.requested_expiry is None
        assert already_set.requested_expiry == dt.date(2029, 1, 1)


class TestMultipleRows:
    """Проверки, что результат корректно ключуется по номеру строки заказа."""

    def test_excluded_dict_is_keyed_by_row_number(
        self,
        expiry_resolution_service: ExpiryResolutionService,
        expiry_stock_repository: ExpiryStockRepository,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Смесь успешной и исключённой строки даёт словарь только по исключённой."""
        certificate_repository.replace_all(
            [make_certificate(_PRODUCT, expiry_date=dt.date(2027, 1, 1))]
        )
        expiry_stock_repository.replace_all(
            [make_expiry_entry(_PRODUCT, expiry_date=dt.date(2027, 1, 1), quantity=100)]
        )

        resolved_row = _row(1, product_name=_PRODUCT, quantity=10)
        excluded_row = _row(3, product_name="Совсем другой товар", quantity=10)

        excluded = expiry_resolution_service.resolve_rows([resolved_row, excluded_row])

        assert set(excluded) == {3}
        assert excluded[3].not_in_database is True
        assert resolved_row.requested_expiry == dt.date(2027, 1, 1)
        assert excluded_row.requested_expiry is None


class TestProgressReporting:
    """Проверки публикации прогресса на больших заказах."""

    def test_reports_start_and_finish_with_expiry_stage(
        self,
        expiry_resolution_service: ExpiryResolutionService,
        expiry_stock_repository: ExpiryStockRepository,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Репортёр получает start() с общим числом строк и finish() по завершении."""
        certificate_repository.replace_all(
            [make_certificate(_PRODUCT, expiry_date=dt.date(2027, 1, 1))]
        )
        expiry_stock_repository.replace_all(
            [make_expiry_entry(_PRODUCT, expiry_date=dt.date(2027, 1, 1), quantity=100)]
        )

        updates: list[ProgressUpdate] = []
        reporter = ProgressReporter(updates.append, min_interval=0.0)

        rows = [
            _row(1, product_name=_PRODUCT, quantity=10),
            _row(2, product_name=_PRODUCT, quantity=10),
        ]
        expiry_resolution_service.resolve_rows(rows, reporter=reporter)

        assert updates[0].total == 2
        assert updates[0].stage == "expiry"
        assert updates[-1].stage == "expiry"
        assert updates[-1].current == 2
