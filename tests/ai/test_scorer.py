"""Тесты взвешенной оценки кандидатов."""

from __future__ import annotations

import datetime as dt

from app.ai.scorer import ScoringContext, is_hard_mismatch, score_candidate
from app.config.settings import MatchingSettings
from app.models.order import OrderRow
from tests.conftest import make_certificate


def _context(**overrides: object) -> ScoringContext:
    """Создаёт контекст оценки с настройками по умолчанию и переопределениями."""
    settings = MatchingSettings()
    for key, value in overrides.items():
        setattr(settings, key, value)
    return ScoringContext.create(settings, today=dt.date(2025, 8, 4))


class TestScoreCandidate:
    """Проверки формулы взвешенной оценки."""

    def test_perfect_match(self) -> None:
        """Полное совпадение по всем трём составляющим даёт оценку, близкую к 1."""
        row = OrderRow(row_number=1, product_name="Лечебные травы 100 мл")
        certificate = make_certificate("Лечебные травы 100 мл", expiry_date=dt.date(2030, 1, 1))
        breakdown = score_candidate(
            row, certificate, lexical=1.0, semantic=None, context=_context()
        )
        assert breakdown.total > 0.9

    def test_weights_sum_influence(self) -> None:
        """Вес наименования 50% доминирует при прочих равных."""
        row = OrderRow(row_number=1, product_name="Товар 100 мл")
        good_name = make_certificate("Товар 100 мл")
        bad_name = make_certificate("Другой товар 100 мл")
        context = _context()
        first = score_candidate(row, good_name, lexical=1.0, semantic=None, context=context)
        second = score_candidate(row, bad_name, lexical=0.3, semantic=None, context=context)
        assert first.total > second.total

    def test_semantic_boosts_zero_lexical_match(self) -> None:
        """Семантическое совпадение поднимает оценку при нулевой лексике."""
        row = OrderRow(row_number=1, product_name="TP Herbal 100ml")
        certificate = make_certificate("Лечебные травы 100 мл")
        context = _context()
        without_semantic = score_candidate(
            row, certificate, lexical=0.0, semantic=None, context=context
        )
        with_semantic = score_candidate(
            row, certificate, lexical=0.0, semantic=0.9, context=context
        )
        assert with_semantic.total > without_semantic.total

    def test_custom_weights_normalized(self) -> None:
        """Ненормированные веса из настроек нормируются перед применением."""
        row = OrderRow(row_number=1, product_name="Товар")
        certificate = make_certificate("Товар")
        context = _context(weight_name=5.0, weight_volume=3.0, weight_expiry=2.0)
        breakdown = score_candidate(row, certificate, lexical=1.0, semantic=None, context=context)
        assert breakdown.weights == (0.5, 0.3, 0.2)


class TestIsHardMismatch:
    """Проверки безусловной отбраковки кандидатов."""

    def test_expired_certificate_rejected_when_required(self) -> None:
        """Просроченный сертификат отбраковывается при строгой настройке."""
        row = OrderRow(row_number=1, product_name="Товар")
        certificate = make_certificate("Товар", expiry_date=dt.date(2020, 1, 1))
        assert is_hard_mismatch(row, certificate, _context(require_valid_expiry=True))

    def test_expired_certificate_allowed_when_not_required(self) -> None:
        """Просроченный сертификат допускается, если строгая проверка выключена."""
        row = OrderRow(row_number=1, product_name="Товар")
        certificate = make_certificate("Товар", expiry_date=dt.date(2020, 1, 1))
        assert not is_hard_mismatch(row, certificate, _context(require_valid_expiry=False))

    def test_different_volume_dimension_rejected(self) -> None:
        """Несопоставимые размерности объёма (мл против шт) отбраковываются."""
        row = OrderRow(row_number=1, product_name="Товар 100 мл")
        certificate = make_certificate("Товар 30 шт")
        assert is_hard_mismatch(row, certificate, _context())

    def test_strict_volume_rejects_different_volume(self) -> None:
        """В строгом режиме объёма 100 мл не подтверждается сертификатом на 150 мл."""
        row = OrderRow(row_number=1, product_name="Товар 100 мл")
        certificate = make_certificate("Товар 150 мл")
        assert is_hard_mismatch(row, certificate, _context(strict_volume_match=True))

    def test_non_strict_volume_allows_close_difference(self) -> None:
        """Без строгого режима разница в объёме не приводит к безусловному отказу."""
        row = OrderRow(row_number=1, product_name="Товар 100 мл")
        certificate = make_certificate("Товар 150 мл")
        assert not is_hard_mismatch(row, certificate, _context(strict_volume_match=False))

    def test_multi_volume_certificate_covers_requested(self) -> None:
        """Сертификат, упоминающий несколько фасовок, покрывает нужный объём.

        Каждое число сопровождается собственной единицей измерения — только в
        этом случае :func:`extract_volumes` находит все перечисленные объёмы;
        общий суффикс единицы на список чисел («100, 150, 200 мл») не
        поддерживается и является намеренным ограничением разбора.
        """
        row = OrderRow(row_number=1, product_name="Товар 100 мл")
        certificate = make_certificate("Товар 100 мл, 150 мл, 200 мл")
        assert not is_hard_mismatch(row, certificate, _context(strict_volume_match=True))

    def test_missing_volume_does_not_reject(self) -> None:
        """Отсутствие объёма с любой из сторон не приводит к отбраковке."""
        row = OrderRow(row_number=1, product_name="Товар")
        certificate = make_certificate("Товар")
        assert not is_hard_mismatch(row, certificate, _context())


class TestExpiryToleranceHardCutoff:
    """Проверки безусловного исключения по допуску срока годности.

    Если в заказе указан требуемый срок, сертификат за пределами
    ``expiry_tolerance_days`` — не кандидат с пониженной оценкой, а
    отбракованный кандидат, независимо от совпадения наименования и объёма.
    """

    def test_zero_difference_is_not_a_hard_mismatch(self) -> None:
        """Точное совпадение срока — кандидат допускается."""
        row = OrderRow(row_number=1, product_name="Товар", requested_expiry=dt.date(2026, 6, 1))
        certificate = make_certificate("Товар", expiry_date=dt.date(2026, 6, 1))
        assert not is_hard_mismatch(row, certificate, _context())

    def test_thirty_days_difference_is_not_a_hard_mismatch(self) -> None:
        """Расхождение в 30 дней укладывается в допуск по умолчанию (45 дней)."""
        row = OrderRow(row_number=1, product_name="Товар", requested_expiry=dt.date(2026, 6, 1))
        certificate = make_certificate("Товар", expiry_date=dt.date(2026, 7, 1))
        assert not is_hard_mismatch(row, certificate, _context())

    def test_exact_tolerance_boundary_is_not_a_hard_mismatch(self) -> None:
        """Расхождение, равное ровно tolerance_days, — граница включительно."""
        row = OrderRow(row_number=1, product_name="Товар", requested_expiry=dt.date(2026, 6, 1))
        certificate = make_certificate("Товар", expiry_date=dt.date(2026, 7, 16))  # +45 дней
        assert not is_hard_mismatch(row, certificate, _context(expiry_tolerance_days=45))

    def test_one_day_beyond_tolerance_is_a_hard_mismatch(self) -> None:
        """Расхождение в tolerance_days + 1 день уже безусловно отбраковывается."""
        row = OrderRow(row_number=1, product_name="Товар", requested_expiry=dt.date(2026, 6, 1))
        certificate = make_certificate("Товар", expiry_date=dt.date(2026, 7, 17))  # +46 дней
        assert is_hard_mismatch(row, certificate, _context(expiry_tolerance_days=45))

    def test_one_year_difference_is_a_hard_mismatch(self) -> None:
        """Расхождение в год безусловно отбраковывается, даже день и месяц совпадают."""
        row = OrderRow(row_number=1, product_name="Товар", requested_expiry=dt.date(2026, 6, 1))
        certificate = make_certificate("Товар", expiry_date=dt.date(2027, 6, 1))
        assert is_hard_mismatch(row, certificate, _context())

    def test_same_day_and_month_different_year_is_a_hard_mismatch(self) -> None:
        """Год обязательно учитывается: совпадение дня и месяца не спасает кандидата.

        Оба срока — «действующие» на опорную дату контекста (не просрочены),
        поэтому отбраковка объясняется именно допуском по сроку, а не
        отдельной проверкой ``require_valid_expiry``.
        """
        row = OrderRow(row_number=1, product_name="Товар", requested_expiry=dt.date(2028, 6, 1))
        certificate = make_certificate("Товар", expiry_date=dt.date(2027, 6, 1))
        assert is_hard_mismatch(row, certificate, _context())
