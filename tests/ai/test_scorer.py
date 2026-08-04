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
        certificate = make_certificate(
            "Лечебные травы 100 мл",
            "/c/1.pdf",
            volume_value=100.0,
            volume_unit="ml",
            expiry_date=dt.date(2030, 1, 1),
        )
        breakdown = score_candidate(
            row, certificate, lexical=1.0, semantic=None, context=_context()
        )
        assert breakdown.total > 0.9

    def test_weights_sum_influence(self) -> None:
        """Вес наименования 50% доминирует при прочих равных."""
        row = OrderRow(row_number=1, product_name="Товар 100 мл")
        good_name = make_certificate(
            "Товар 100 мл", "/c/1.pdf", volume_value=100.0, volume_unit="ml"
        )
        bad_name = make_certificate(
            "Другой товар 100 мл", "/c/2.pdf", volume_value=100.0, volume_unit="ml"
        )
        context = _context()
        first = score_candidate(row, good_name, lexical=1.0, semantic=None, context=context)
        second = score_candidate(row, bad_name, lexical=0.3, semantic=None, context=context)
        assert first.total > second.total

    def test_semantic_boosts_zero_lexical_match(self) -> None:
        """Семантическое совпадение поднимает оценку при нулевой лексике."""
        row = OrderRow(row_number=1, product_name="TP Herbal 100ml")
        certificate = make_certificate(
            "Лечебные травы 100 мл", "/c/1.pdf", volume_value=100.0, volume_unit="ml"
        )
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
        certificate = make_certificate("Товар", "/c/1.pdf")
        context = _context(weight_name=5.0, weight_volume=3.0, weight_expiry=2.0)
        breakdown = score_candidate(row, certificate, lexical=1.0, semantic=None, context=context)
        assert breakdown.weights == (0.5, 0.3, 0.2)


class TestIsHardMismatch:
    """Проверки безусловной отбраковки кандидатов."""

    def test_expired_certificate_rejected_when_required(self) -> None:
        """Просроченный сертификат отбраковывается при строгой настройке."""
        row = OrderRow(row_number=1, product_name="Товар")
        certificate = make_certificate("Товар", "/c/1.pdf", expiry_date=dt.date(2020, 1, 1))
        assert is_hard_mismatch(row, certificate, _context(require_valid_expiry=True))

    def test_expired_certificate_allowed_when_not_required(self) -> None:
        """Просроченный сертификат допускается, если строгая проверка выключена."""
        row = OrderRow(row_number=1, product_name="Товар")
        certificate = make_certificate("Товар", "/c/1.pdf", expiry_date=dt.date(2020, 1, 1))
        assert not is_hard_mismatch(row, certificate, _context(require_valid_expiry=False))

    def test_different_volume_dimension_rejected(self) -> None:
        """Несопоставимые размерности объёма (мл против шт) отбраковываются."""
        row = OrderRow(row_number=1, product_name="Товар 100 мл")
        certificate = make_certificate(
            "Товар 30 шт", "/c/1.pdf", volume_value=30.0, volume_unit="pcs"
        )
        assert is_hard_mismatch(row, certificate, _context())

    def test_strict_volume_rejects_different_volume(self) -> None:
        """В строгом режиме объёма 100 мл не подтверждается сертификатом на 150 мл."""
        row = OrderRow(row_number=1, product_name="Товар 100 мл")
        certificate = make_certificate(
            "Товар 150 мл", "/c/1.pdf", volume_value=150.0, volume_unit="ml"
        )
        assert is_hard_mismatch(row, certificate, _context(strict_volume_match=True))

    def test_non_strict_volume_allows_close_difference(self) -> None:
        """Без строгого режима разница в объёме не приводит к безусловному отказу."""
        row = OrderRow(row_number=1, product_name="Товар 100 мл")
        certificate = make_certificate(
            "Товар 150 мл", "/c/1.pdf", volume_value=150.0, volume_unit="ml"
        )
        assert not is_hard_mismatch(row, certificate, _context(strict_volume_match=False))

    def test_multi_volume_certificate_covers_requested(self) -> None:
        """Сертификат, упоминающий несколько фасовок, покрывает нужный объём.

        Каждое число сопровождается собственной единицей измерения — только в
        этом случае :func:`extract_volumes` находит все перечисленные объёмы;
        общий суффикс единицы на список чисел («100, 150, 200 мл») не
        поддерживается и является намеренным ограничением разбора.
        """
        row = OrderRow(row_number=1, product_name="Товар 100 мл")
        certificate = make_certificate(
            "Товар 100 мл, 150 мл, 200 мл", "/c/1.pdf", volume_value=150.0, volume_unit="ml"
        )
        assert not is_hard_mismatch(row, certificate, _context(strict_volume_match=True))

    def test_missing_volume_does_not_reject(self) -> None:
        """Отсутствие объёма с любой из сторон не приводит к отбраковке."""
        row = OrderRow(row_number=1, product_name="Товар")
        certificate = make_certificate("Товар", "/c/1.pdf")
        assert not is_hard_mismatch(row, certificate, _context())
