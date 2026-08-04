"""Тесты доменных моделей результата подбора."""

from __future__ import annotations

import datetime as dt

from app.models.matching import (
    MatchCandidate,
    MatchResult,
    MatchSource,
    MatchStatus,
    ScoreBreakdown,
)
from app.models.order import OrderRow
from tests.conftest import make_certificate


def _candidate(name: str, path: str, total: float = 0.9) -> MatchCandidate:
    """Создаёт кандидата для тестов моделей."""
    certificate = make_certificate(name, path, expiry_date=dt.date(2029, 1, 1))
    score = ScoreBreakdown(name=total, volume=1.0, expiry=1.0, total=total)
    return MatchCandidate(certificate=certificate, score=score, source=MatchSource.LEXICAL)


class TestMatchResult:
    """Проверки поведения результата подбора."""

    def test_selected_defaults_to_none(self) -> None:
        """Без явного выбора selected возвращает None."""
        result = MatchResult(
            row=OrderRow(row_number=1, product_name="Товар"), status=MatchStatus.NOT_FOUND
        )
        assert result.selected is None
        assert result.certificate is None

    def test_select_sets_selected_candidate(self) -> None:
        """Выбор кандидата делает его доступным через selected/certificate."""
        candidate = _candidate("Товар", "/c/1.pdf")
        result = MatchResult(
            row=OrderRow(row_number=1, product_name="Товар"),
            status=MatchStatus.AMBIGUOUS,
            candidates=[candidate],
        )
        result.select(0)
        assert result.selected is candidate
        assert result.certificate is candidate.certificate

    def test_select_manual_changes_status(self) -> None:
        """Ручной выбор переводит статус в MANUAL."""
        candidate = _candidate("Товар", "/c/1.pdf")
        result = MatchResult(
            row=OrderRow(row_number=1, product_name="Товар"),
            status=MatchStatus.AMBIGUOUS,
            candidates=[candidate],
        )
        result.select(0, manual=True)
        assert result.status is MatchStatus.MANUAL

    def test_select_out_of_range_raises(self) -> None:
        """Выбор несуществующего индекса порождает IndexError."""
        import pytest

        result = MatchResult(
            row=OrderRow(row_number=1, product_name="Товар"), status=MatchStatus.NOT_FOUND
        )
        with pytest.raises(IndexError):
            result.select(0)

    def test_best_returns_first_candidate_regardless_of_selection(self) -> None:
        """best всегда указывает на первого кандидата в списке."""
        first = _candidate("A", "/c/1.pdf", total=0.9)
        second = _candidate("B", "/c/2.pdf", total=0.7)
        result = MatchResult(
            row=OrderRow(row_number=1, product_name="Товар"),
            status=MatchStatus.AMBIGUOUS,
            candidates=[first, second],
        )
        assert result.best is first

    def test_score_falls_back_to_best_without_selection(self) -> None:
        """До явного выбора score берётся у лучшего кандидата."""
        candidate = _candidate("Товар", "/c/1.pdf", total=0.77)
        result = MatchResult(
            row=OrderRow(row_number=1, product_name="Товар"),
            status=MatchStatus.AMBIGUOUS,
            candidates=[candidate],
        )
        assert result.score == 0.77

    def test_to_report_dict_contains_expected_keys(self) -> None:
        """Словарь отчёта содержит все ключевые поля для Excel/CSV."""
        candidate = _candidate("Товар", "/c/1.pdf")
        result = MatchResult(
            row=OrderRow(row_number=5, product_name="Товар"),
            status=MatchStatus.MATCHED,
            candidates=[candidate],
            selected_index=0,
        )
        report = result.to_report_dict()
        assert report["Строка"] == 5
        assert report["Статус"] == "Найден"
        assert report["Сертификат"] == candidate.certificate.display_number


class TestScoreBreakdown:
    """Проверки детализации оценки."""

    def test_percent_rounds_correctly(self) -> None:
        """Процент округляется до целого."""
        breakdown = ScoreBreakdown(name=1.0, volume=1.0, expiry=0.5, total=0.876)
        assert breakdown.percent == 88

    def test_explain_includes_all_components(self) -> None:
        """Пояснение содержит все три составляющие оценки."""
        breakdown = ScoreBreakdown(name=0.9, volume=0.8, expiry=0.7, total=0.83)
        text = breakdown.explain()
        assert "Наименование" in text
        assert "Объём" in text
        assert "Срок" in text


class TestMatchStatus:
    """Проверки перечисления статусов."""

    def test_is_resolved_true_for_matched_and_manual(self) -> None:
        """MATCHED и MANUAL считаются разрешёнными статусами."""
        assert MatchStatus.MATCHED.is_resolved
        assert MatchStatus.MANUAL.is_resolved

    def test_is_resolved_false_for_others(self) -> None:
        """AMBIGUOUS и NOT_FOUND не считаются разрешёнными."""
        assert not MatchStatus.AMBIGUOUS.is_resolved
        assert not MatchStatus.NOT_FOUND.is_resolved
