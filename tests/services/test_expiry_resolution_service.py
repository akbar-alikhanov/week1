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

Два практических правила для дат в этом файле (оба — следствие того, что
здесь используется настоящий, неизменённый ``MatchingService``, а не мок):

* Срок действия ЛЮБОГО сертификата в тестовых данных обязан быть в будущем
  относительно реальной даты выполнения тестов — иначе он безусловно
  отбраковывается как просроченный (``require_valid_expiry``) независимо от
  кандидатной даты партии, которую он должен был бы подтвердить.
* Если в одном тесте участвует НЕСКОЛЬКО сертификатов одного и того же
  товара, их даты должны отличаться друг от друга минимум на год: иначе оба
  сертификата попадают в допуск (``expiry_tolerance_days``) друг для друга,
  и решает не «какой сертификат ближе к нужной дате», а сработавший
  автовыбор ближайшего среди «конкурирующих» вариантов (FEFO,
  ``auto_resolve_duplicates`` — часть неизменного алгоритма подбора) — это
  корректное поведение существующего подбора, но не то, что нужно для
  однозначной проверки конкретной партии в тесте.
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
from app.models.matching import MatchSource
from app.models.order import OrderRow
from app.repositories.alias_repository import AliasRepository
from app.repositories.certificate_product_repository import CertificateProductRepository
from app.repositories.expiry_stock_repository import ExpiryStockRepository
from app.services.expiry_resolution_service import (
    ExpiryExclusion,
    ExpiryResolutionService,
    ExpirySuggestion,
    ManualExpiryReview,
)
from app.services.matching_service import MatchingService
from tests.conftest import make_certificate, make_expiry_entry

#: Товар с объёмом в названии — совпадение объёма 1.0 гарантированно (не
#: нейтральное значение по умолчанию), поэтому итоговая оценка предсказуема.
_PRODUCT = "Крем детский 100 мл"


def _make_settings_service(tmp_path: Path) -> SettingsService:
    """Собирает сервис настроек поверх временного файла (значения по умолчанию)."""
    settings_service = SettingsService(tmp_path / "settings.json")
    settings_service.load()
    return settings_service


def _make_matching_service(
    database: Database, settings_service: SettingsService
) -> MatchingService:
    """Собирает минимальный, полностью настоящий сервис подбора сертификата.

    Используется только для пробных вызовов ``match_row`` внутри
    :class:`ExpiryResolutionService` — сам сервис подбора этим не изменяется
    и не подменяется.
    """
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
    settings_service = _make_settings_service(tmp_path)
    return ExpiryResolutionService(
        expiry_stock_repository,
        _make_matching_service(database, settings_service),
        settings_service,
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
    """Успешный подбор одной партией: срок найден, сертификат подтверждён (Этап 1)."""

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
        excluded, combined, _ = expiry_resolution_service.resolve_rows([row])

        assert excluded == {}
        assert combined == {}
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
        excluded, combined, _ = expiry_resolution_service.resolve_rows([row])

        assert excluded == {}
        assert combined == {}
        assert row.requested_expiry == dt.date(2028, 1, 1)


class TestFallsBackOnInsufficientQuantity:
    """Ветка «количества не хватает на этом сроке — перейти к следующему» (Этап 1)."""

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
        excluded, combined, _ = expiry_resolution_service.resolve_rows([row])

        assert excluded == {}
        assert combined == {}
        assert row.requested_expiry == dt.date(2027, 1, 1)


class TestFallsBackWhenCertificateNotFoundForDate:
    """Ветка «сертификат не найден на этот срок — перейти к следующему» (Этап 1)."""

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
        excluded, combined, _ = expiry_resolution_service.resolve_rows([row])

        assert excluded == {}
        assert combined == {}
        assert row.requested_expiry == dt.date(2027, 6, 1)

    def test_no_certificate_anywhere_excludes_row_with_no_certificate_flag(
        self,
        expiry_resolution_service: ExpiryResolutionService,
        expiry_stock_repository: ExpiryStockRepository,
    ) -> None:
        """Обе партии годны по количеству, но сертификатов в базе нет вообще.

        Раз ни для одной партии сертификат не подтверждён — не только
        одиночная попытка (Этап 1), но и попытка комбинации (Этап 2) не
        имеют смысла: суммировать нечего, доступный остаток любой партии
        равен нулю. Это специальный случай п. 13 требования — со своим
        флагом и текстом причины, отдельным от обычного «не найдено».
        """
        expiry_stock_repository.replace_all(
            [
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2028, 1, 1), quantity=100),
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2027, 1, 1), quantity=100),
            ]
        )

        row = _row(1, quantity=50)
        excluded, combined, _ = expiry_resolution_service.resolve_rows([row])

        assert combined == {}
        assert excluded == {
            1: ExpiryExclusion(
                note="Для доступных сроков не найден подходящий сертификат.",
                no_certificate_available=True,
            )
        }
        assert row.requested_expiry is None


class TestProductNotInDatabase:
    """Ветка «товар отсутствует в базе сроков» — особое форматирование результата (п. 12)."""

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
        excluded, combined, _ = expiry_resolution_service.resolve_rows([row])

        assert combined == {}
        assert excluded == {
            1: ExpiryExclusion(note="Товар отсутствует в базе сроков.", not_in_database=True)
        }
        assert row.requested_expiry is None


class TestCombinationOfMultipleBatches:
    """Этап 2: одной партии не хватает — используется сразу несколько (п. 6-10, 14)."""

    def test_two_batches_combined_when_neither_alone_is_enough(
        self,
        expiry_resolution_service: ExpiryResolutionService,
        expiry_stock_repository: ExpiryStockRepository,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Ни одна партия не покрывает заказ в одиночку — используются обе.

        Пример из требования (п. 7): требуется 1500, партии 1068 и 880
        покрывают заказ в сумме, третья (700) не нужна и не используется.
        """
        certificate_repository.replace_all(
            [
                make_certificate(
                    _PRODUCT, expiry_date=dt.date(2029, 5, 25), certificate_number="UZ.1"
                ),
                make_certificate(
                    _PRODUCT, expiry_date=dt.date(2027, 1, 1), certificate_number="UZ.2"
                ),
                make_certificate(
                    _PRODUCT, expiry_date=dt.date(2025, 6, 1), certificate_number="UZ.3"
                ),
            ]
        )
        expiry_stock_repository.replace_all(
            [
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2029, 5, 25), quantity=1068),
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2027, 1, 1), quantity=880),
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2025, 6, 1), quantity=700),
            ]
        )

        row = _row(1, quantity=1500)
        excluded, combined, _ = expiry_resolution_service.resolve_rows([row])

        assert excluded == {}
        assert row.requested_expiry is None  # у комбинации нет одного срока
        allocations = combined[1]
        assert [(a.quantity, a.expiry_date) for a in allocations] == [
            (1068, dt.date(2029, 5, 25)),
            (432, dt.date(2027, 1, 1)),
        ]
        assert sum(a.quantity for a in allocations) == 1500
        assert {a.certificate.display_number for a in allocations} == {"UZ.1", "UZ.2"}

    def test_batch_without_certificate_is_excluded_from_combination(
        self,
        expiry_resolution_service: ExpiryResolutionService,
        expiry_stock_repository: ExpiryStockRepository,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Партия без подтверждённого сертификата не входит в сумму (п. 3, 8) — критический случай.

        Единственный сертификат в базе действителен только под самую новую
        партию (50 шт.). Средняя партия физически огромна (1000 шт.), но её
        срок (2024, вне допуска) не наберёт сертификата — по правилу
        требования её физический остаток в расчёт НЕ идёт вообще, поэтому
        заказа не хватает, хотя формальная сумма всех остатков (50+1000+40)
        многократно превышает требуемое количество.
        """
        certificate_repository.replace_all(
            [
                make_certificate(
                    _PRODUCT, expiry_date=dt.date(2029, 5, 25), certificate_number="UZ.1"
                )
            ]
        )
        expiry_stock_repository.replace_all(
            [
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2029, 5, 25), quantity=50),
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2024, 1, 1), quantity=1000),
            ]
        )

        row = _row(1, quantity=100)
        excluded, combined, _ = expiry_resolution_service.resolve_rows([row])

        assert combined == {}
        assert excluded == {
            1: ExpiryExclusion(note="Недостаточно остатка по партиям с подходящими сертификатами.")
        }
        assert excluded[1].not_in_database is False
        assert excluded[1].no_certificate_available is False

    def test_combination_excludes_batch_whose_only_certificate_is_beyond_tolerance(
        self,
        expiry_resolution_service: ExpiryResolutionService,
        expiry_stock_repository: ExpiryStockRepository,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Партия «имеет сертификат» только если он проходит тот же строгий
        допуск по сроку, что и обычный подбор (регрессия к отчёту
        пользователя: раньше при подборе для партии брался просто ближайший
        сертификат без проверки допуска).

        Обе партии физически достаточны для заказа (600 + 600 >= 1000), но
        сертификат второй партии отстоит от ЕЁ даты на 46 дней — на день
        больше допуска по умолчанию (45). Такая партия должна считаться не
        имеющей сертификата вообще, и тогда одной первой партии (600) не
        хватает на заказ в 1000 штук.
        """
        first_date = dt.date(2029, 1, 1)
        second_date = dt.date(2027, 1, 1)
        certificate_repository.replace_all(
            [
                make_certificate(_PRODUCT, expiry_date=first_date, certificate_number="UZ.1"),
                make_certificate(
                    _PRODUCT,
                    expiry_date=second_date + dt.timedelta(days=46),
                    certificate_number="UZ.2",
                ),
            ]
        )
        expiry_stock_repository.replace_all(
            [
                make_expiry_entry(_PRODUCT, expiry_date=first_date, quantity=600),
                make_expiry_entry(_PRODUCT, expiry_date=second_date, quantity=600),
            ]
        )

        row = _row(1, quantity=1000)
        excluded, combined, _ = expiry_resolution_service.resolve_rows([row])

        assert combined == {}
        assert excluded == {
            1: ExpiryExclusion(note="Недостаточно остатка по партиям с подходящими сертификатами.")
        }

    def test_prefers_fewest_and_freshest_batches(
        self,
        expiry_resolution_service: ExpiryResolutionService,
        expiry_stock_repository: ExpiryStockRepository,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Из нескольких возможных комбинаций выбираются самые свежие партии (п. 9-10).

        Пример из требования: требуется 1000, партии 600/500/900 (все с
        сертификатом). Ожидаемый выбор — две самые новые партии (600 + 400
        из следующей), а не третья, более старая.
        """
        certificate_repository.replace_all(
            [
                make_certificate(
                    _PRODUCT, expiry_date=dt.date(2029, 5, 25), certificate_number="UZ.1"
                ),
                make_certificate(
                    _PRODUCT, expiry_date=dt.date(2027, 4, 1), certificate_number="UZ.2"
                ),
                make_certificate(
                    _PRODUCT, expiry_date=dt.date(2025, 1, 1), certificate_number="UZ.3"
                ),
            ]
        )
        expiry_stock_repository.replace_all(
            [
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2029, 5, 25), quantity=600),
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2027, 4, 1), quantity=500),
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2025, 1, 1), quantity=900),
            ]
        )

        row = _row(1, quantity=1000)
        excluded, combined, _ = expiry_resolution_service.resolve_rows([row])

        assert excluded == {}
        allocations = combined[1]
        assert [(a.quantity, a.expiry_date) for a in allocations] == [
            (600, dt.date(2029, 5, 25)),
            (400, dt.date(2027, 4, 1)),
        ]

    def test_does_not_use_more_than_required(
        self,
        expiry_resolution_service: ExpiryResolutionService,
        expiry_stock_repository: ExpiryStockRepository,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Из последней использованной партии берётся не весь остаток, а только нужное.

        Обе партии по отдельности недостаточны (10 и 25 при требуемых 30) —
        комбинация обязательна; из второй партии, несмотря на остаток 25,
        берётся только 20 (сколько не хватило после первой), а не весь
        остаток.
        """
        certificate_repository.replace_all(
            [
                make_certificate(
                    _PRODUCT, expiry_date=dt.date(2029, 1, 1), certificate_number="UZ.1"
                ),
                make_certificate(
                    _PRODUCT, expiry_date=dt.date(2027, 1, 1), certificate_number="UZ.2"
                ),
            ]
        )
        expiry_stock_repository.replace_all(
            [
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2029, 1, 1), quantity=10),
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2027, 1, 1), quantity=25),
            ]
        )

        row = _row(1, quantity=30)
        excluded, combined, _ = expiry_resolution_service.resolve_rows([row])

        assert excluded == {}
        allocations = combined[1]
        assert [(a.quantity, a.expiry_date) for a in allocations] == [
            (10, dt.date(2029, 1, 1)),
            (20, dt.date(2027, 1, 1)),
        ]


class TestInsufficientEvenAfterCombination:
    """Ветка «суммарного остатка партий с сертификатом всё равно недостаточно» (п. 11)."""

    def test_critical_example_from_requirements(
        self,
        expiry_resolution_service: ExpiryResolutionService,
        expiry_stock_repository: ExpiryStockRepository,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Критический пример требования (п. 4) — дословное воспроизведение.

        Требуется 1500. Партии: 1068 (сертификат есть), 880 и 700
        (сертификата нет ни у одной). Доступный остаток — только 1068, а не
        1068+880+700 — поэтому заказ выполнить нельзя, несмотря на то, что
        физическая сумма остатков (2648) с большим запасом покрыла бы 1500.
        """
        certificate_repository.replace_all(
            [
                make_certificate(
                    _PRODUCT, expiry_date=dt.date(2029, 5, 25), certificate_number="UZ.1"
                )
            ]
        )
        expiry_stock_repository.replace_all(
            [
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2029, 5, 25), quantity=1068),
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2024, 1, 1), quantity=880),
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2023, 12, 15), quantity=700),
            ]
        )

        row = _row(1, quantity=1500)
        excluded, combined, _ = expiry_resolution_service.resolve_rows([row])

        assert combined == {}
        assert excluded == {
            1: ExpiryExclusion(note="Недостаточно остатка по партиям с подходящими сертификатами.")
        }
        assert excluded[1].not_in_database is False
        assert excluded[1].no_certificate_available is False
        assert row.requested_expiry is None


class TestManualReviewStage:
    """Этап 3: если сертификат не подтверждён ни для одной партии — предложить варианты."""

    def test_returns_pending_review_with_suggestion_beyond_tolerance(
        self,
        expiry_resolution_service: ExpiryResolutionService,
        expiry_stock_repository: ExpiryStockRepository,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Сертификат вне допуска не подтверждается автоматически, но предлагается вручную."""
        batch_date = dt.date(2029, 6, 1)
        certificate_repository.replace_all(
            [
                make_certificate(
                    _PRODUCT,
                    expiry_date=batch_date + dt.timedelta(days=100),
                    certificate_number="UZ.1",
                )
            ]
        )
        expiry_stock_repository.replace_all(
            [make_expiry_entry(_PRODUCT, expiry_date=batch_date, quantity=100)]
        )

        row = _row(1, quantity=50)
        excluded, combined, pending_review = expiry_resolution_service.resolve_rows([row])

        assert excluded == {}
        assert combined == {}
        assert set(pending_review) == {1}
        review = pending_review[1]
        assert review.row is row
        assert review.required_quantity == 50
        assert len(review.batches) == 1
        batch = review.batches[0]
        assert batch.entry.expiry_date == batch_date
        assert [s.certificate.certificate_number for s in batch.suggestions] == ["UZ.1"]
        assert batch.suggestions[0].difference_days == 100

    def test_all_batches_receive_suggestions(
        self,
        expiry_resolution_service: ExpiryResolutionService,
        expiry_stock_repository: ExpiryStockRepository,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Варианты подбираются для ВСЕХ проверенных партий, а не только для первой.

        Пример из требования: три партии, ни для одной строгий поиск ничего
        не находит — второй этап обязан проверить их все, а не
        остановиться после первой неудачи.
        """
        certificate_repository.replace_all(
            [make_certificate(_PRODUCT, expiry_date=dt.date(2030, 1, 1), certificate_number="UZ.1")]
        )
        expiry_stock_repository.replace_all(
            [
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2029, 1, 1), quantity=1600),
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2028, 1, 10), quantity=7000),
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2027, 6, 15), quantity=10000),
            ]
        )

        row = _row(1, quantity=1000)
        excluded, combined, pending_review = expiry_resolution_service.resolve_rows([row])

        assert excluded == {}
        assert combined == {}
        review = pending_review[1]
        assert len(review.batches) == 3
        assert all(batch.suggestions for batch in review.batches)
        assert {batch.entry.expiry_date for batch in review.batches} == {
            dt.date(2029, 1, 1),
            dt.date(2028, 1, 10),
            dt.date(2027, 6, 15),
        }

    def test_suggestions_capped_at_default_limit_and_sorted(
        self,
        expiry_resolution_service: ExpiryResolutionService,
        expiry_stock_repository: ExpiryStockRepository,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """По умолчанию предлагается не больше 3 вариантов, ближайших по сроку."""
        batch_date = dt.date(2029, 6, 1)
        certificate_repository.replace_all(
            [
                make_certificate(
                    _PRODUCT,
                    expiry_date=batch_date + dt.timedelta(days=offset),
                    certificate_number=str(offset),
                )
                for offset in (300, 100, 200, 400, 150)
            ]
        )
        expiry_stock_repository.replace_all(
            [make_expiry_entry(_PRODUCT, expiry_date=batch_date, quantity=100)]
        )

        row = _row(1, quantity=50)
        _, _, pending_review = expiry_resolution_service.resolve_rows([row])

        suggestions = pending_review[1].batches[0].suggestions
        assert len(suggestions) == 3
        assert [s.difference_days for s in suggestions] == [100, 150, 200]

    def test_no_pending_review_when_nothing_to_suggest(
        self,
        expiry_resolution_service: ExpiryResolutionService,
        expiry_stock_repository: ExpiryStockRepository,
    ) -> None:
        """Если предложить нечего вообще ни для одной партии — обычное исключение, как раньше."""
        expiry_stock_repository.replace_all(
            [
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2029, 1, 1), quantity=100),
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2028, 1, 1), quantity=100),
            ]
        )

        row = _row(1, quantity=50)
        excluded, combined, pending_review = expiry_resolution_service.resolve_rows([row])

        assert pending_review == {}
        assert combined == {}
        assert excluded == {
            1: ExpiryExclusion(
                note="Для доступных сроков не найден подходящий сертификат.",
                no_certificate_available=True,
            )
        }


class TestApplyManualSelections:
    """Проверки применения ручного выбора пользователя (после показа предложений)."""

    def test_confirmed_batches_are_combined_like_automatic_ones(
        self,
        expiry_resolution_service: ExpiryResolutionService,
        expiry_stock_repository: ExpiryStockRepository,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Подтверждённые вручную партии участвуют в распределении количества.

        Переиспользуется та же логика объединения, что и для партий,
        подтверждённых автоматически (Этап 2) — источник подтверждённого
        кандидата при этом ``MatchSource.MANUAL``, а не строгий/нечёткий
        поиск.
        """
        first_date = dt.date(2029, 6, 1)
        second_date = dt.date(2028, 1, 1)
        certificate_repository.replace_all(
            [
                make_certificate(
                    _PRODUCT,
                    expiry_date=first_date + dt.timedelta(days=90),
                    certificate_number="UZ.1",
                ),
                make_certificate(
                    _PRODUCT,
                    expiry_date=second_date + dt.timedelta(days=90),
                    certificate_number="UZ.2",
                ),
            ]
        )
        expiry_stock_repository.replace_all(
            [
                make_expiry_entry(_PRODUCT, expiry_date=first_date, quantity=40),
                make_expiry_entry(_PRODUCT, expiry_date=second_date, quantity=60),
            ]
        )

        row = _row(1, quantity=100)
        _, _, pending_review = expiry_resolution_service.resolve_rows([row])
        review = pending_review[1]
        assert len(review.batches) == 2

        choices: dict[int, ExpirySuggestion] = {
            index: batch.suggestions[0]
            for index, batch in enumerate(review.batches)
            if batch.suggestions
        }
        outcome = expiry_resolution_service.apply_manual_selections(review, choices)

        assert isinstance(outcome, list)
        assert sum(allocation.quantity for allocation in outcome) == 100
        assert {allocation.candidate.source for allocation in outcome} == {MatchSource.MANUAL}
        assert {allocation.certificate.certificate_number for allocation in outcome} == {
            "UZ.1",
            "UZ.2",
        }

    def test_partial_confirmation_is_insufficient(
        self,
        expiry_resolution_service: ExpiryResolutionService,
        expiry_stock_repository: ExpiryStockRepository,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Подтверждённых партий не хватает — обычное исключение «недостаточно остатка»."""
        first_date = dt.date(2029, 6, 1)
        second_date = dt.date(2028, 1, 1)
        certificate_repository.replace_all(
            [
                make_certificate(
                    _PRODUCT,
                    expiry_date=first_date + dt.timedelta(days=90),
                    certificate_number="UZ.1",
                )
            ]
        )
        expiry_stock_repository.replace_all(
            [
                make_expiry_entry(_PRODUCT, expiry_date=first_date, quantity=40),
                make_expiry_entry(_PRODUCT, expiry_date=second_date, quantity=60),
            ]
        )

        row = _row(1, quantity=100)
        _, _, pending_review = expiry_resolution_service.resolve_rows([row])
        review = pending_review[1]

        # Подтверждена только первая партия (40 шт.) — второй нечего предложить.
        choices = {0: review.batches[0].suggestions[0]}
        outcome = expiry_resolution_service.apply_manual_selections(review, choices)

        assert outcome == ExpiryExclusion(
            note="Недостаточно остатка по партиям с подходящими сертификатами."
        )

    def test_no_confirmation_falls_back_to_no_certificate_exclusion(
        self,
        expiry_resolution_service: ExpiryResolutionService,
        expiry_stock_repository: ExpiryStockRepository,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Пустой выбор пользователя — то же исключение, что и без Этапа 3 вообще.

        Проверяет заодно, что применение пустого выбора никогда не строит
        новое предложение вместо окончательного результата (тип результата
        — не :class:`ManualExpiryReview`).
        """
        batch_date = dt.date(2029, 6, 1)
        certificate_repository.replace_all(
            [
                make_certificate(
                    _PRODUCT,
                    expiry_date=batch_date + dt.timedelta(days=100),
                    certificate_number="UZ.1",
                )
            ]
        )
        expiry_stock_repository.replace_all(
            [make_expiry_entry(_PRODUCT, expiry_date=batch_date, quantity=100)]
        )

        row = _row(1, quantity=50)
        _, _, pending_review = expiry_resolution_service.resolve_rows([row])
        review = pending_review[1]

        outcome = expiry_resolution_service.apply_manual_selections(review, {})

        assert not isinstance(outcome, ManualExpiryReview)
        assert outcome == ExpiryExclusion(
            note="Для доступных сроков не найден подходящий сертификат.",
            no_certificate_available=True,
        )


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
        базе сроков» — этого не должно происходить: заказ уже содержит
        осознанный выбор человека.
        """
        expiry_stock_repository.replace_all(
            [make_expiry_entry("Другой товар", expiry_date=dt.date(2027, 1, 1), quantity=100)]
        )

        row = _row(1, product_name=_PRODUCT, requested_expiry=dt.date(2030, 1, 1))
        excluded, combined, _ = expiry_resolution_service.resolve_rows([row])

        assert excluded == {}
        assert combined == {}
        assert row.requested_expiry == dt.date(2030, 1, 1)


class TestInertWhenDatabaseEmpty:
    """Пустая (ни разу не импортированная) база сроков годности ничего не меняет."""

    def test_returns_empty_results_without_touching_rows(
        self, expiry_resolution_service: ExpiryResolutionService
    ) -> None:
        """Ни одна строка не исключается и не изменяется, если база вообще не настроена."""
        untouched = _row(1, product_name=_PRODUCT, requested_expiry=None)
        already_set = _row(2, product_name="Ещё товар", requested_expiry=dt.date(2029, 1, 1))

        excluded, combined, _ = expiry_resolution_service.resolve_rows([untouched, already_set])

        assert excluded == {}
        assert combined == {}
        assert untouched.requested_expiry is None
        assert already_set.requested_expiry == dt.date(2029, 1, 1)


class TestMultipleRows:
    """Проверки, что результат корректно ключуется по номеру строки заказа."""

    def test_results_are_keyed_by_row_number(
        self,
        expiry_resolution_service: ExpiryResolutionService,
        expiry_stock_repository: ExpiryStockRepository,
        certificate_repository: CertificateProductRepository,
    ) -> None:
        """Смесь успешной, исключённой и комбинированной строк — каждая в своём словаре."""
        certificate_repository.replace_all(
            [
                make_certificate(
                    _PRODUCT, expiry_date=dt.date(2027, 1, 1), certificate_number="UZ.1"
                ),
                make_certificate(
                    "Комбинируемый товар",
                    expiry_date=dt.date(2029, 1, 1),
                    certificate_number="UZ.2",
                ),
                make_certificate(
                    "Комбинируемый товар",
                    expiry_date=dt.date(2027, 1, 1),
                    certificate_number="UZ.3",
                ),
            ]
        )
        expiry_stock_repository.replace_all(
            [
                make_expiry_entry(_PRODUCT, expiry_date=dt.date(2027, 1, 1), quantity=100),
                make_expiry_entry(
                    "Комбинируемый товар", expiry_date=dt.date(2029, 1, 1), quantity=10
                ),
                make_expiry_entry(
                    "Комбинируемый товар", expiry_date=dt.date(2027, 1, 1), quantity=10
                ),
            ]
        )

        resolved_row = _row(1, product_name=_PRODUCT, quantity=10)
        excluded_row = _row(3, product_name="Совсем другой товар", quantity=10)
        combined_row = _row(5, product_name="Комбинируемый товар", quantity=15)

        excluded, combined, _ = expiry_resolution_service.resolve_rows(
            [resolved_row, excluded_row, combined_row]
        )

        assert set(excluded) == {3}
        assert excluded[3].not_in_database is True
        assert set(combined) == {5}
        assert resolved_row.requested_expiry == dt.date(2027, 1, 1)
        assert excluded_row.requested_expiry is None
        assert combined_row.requested_expiry is None


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
