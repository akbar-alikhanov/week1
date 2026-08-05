"""Тесты разбора и сравнения дат."""

from __future__ import annotations

import datetime as dt
import itertools

import pytest

from app.core.dates import (
    days_between,
    expiry_similarity,
    find_dates,
    format_date,
    parse_date,
    parse_duration,
    resolve_month,
)


class TestParseDate:
    """Проверки разбора дат из разных форматов."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("31.12.2029", dt.date(2029, 12, 31)),
            ("2029-12-31", dt.date(2029, 12, 31)),
            ("«31» декабря 2029 г.", dt.date(2029, 12, 31)),
            ("31 дек. 2029", dt.date(2029, 12, 31)),
            ("5 May 2029", dt.date(2029, 5, 5)),
            ("1 сентября 2027", dt.date(2027, 9, 1)),
            ("15 март 2026", dt.date(2026, 3, 15)),
        ],
    )
    def test_recognized_formats(self, raw: str, expected: dt.date) -> None:
        """Все поддерживаемые форматы разбираются в одинаковую дату."""
        assert parse_date(raw) == expected

    def test_none_input(self) -> None:
        """None не приводит к ошибке."""
        assert parse_date(None) is None

    def test_empty_string(self) -> None:
        """Пустая строка не распознаётся как дата."""
        assert parse_date("") is None

    def test_garbage_string(self) -> None:
        """Строка без даты возвращает None."""
        assert parse_date("не дата") is None

    def test_date_object_passthrough(self) -> None:
        """Объект date возвращается без изменений."""
        value = dt.date(2025, 1, 1)
        assert parse_date(value) is value

    def test_datetime_converted_to_date(self) -> None:
        """datetime приводится к date (время отбрасывается)."""
        value = dt.datetime(2025, 1, 1, 15, 30)
        assert parse_date(value) == dt.date(2025, 1, 1)

    def test_excel_serial_date(self) -> None:
        """Числовой Excel-serial корректно конвертируется."""
        # 45658 соответствует 2025-01-01 в системе Excel (1900-based).
        result = parse_date(45658)
        assert result is not None
        assert result.year == 2025

    def test_implausible_number_rejected(self) -> None:
        """Число вне разумного диапазона serial-дат не разбирается."""
        assert parse_date(999999) is None

    def test_out_of_range_year_rejected(self) -> None:
        """Год за пределами разумного диапазона отбрасывается."""
        assert parse_date("31.12.1500") is None


class TestResolveMonth:
    """Проверки распознавания названия месяца."""

    @pytest.mark.parametrize(
        ("word", "expected"),
        [
            ("декабря", 12),
            ("дек", 12),
            ("dec", 12),
            ("December", 12),
            ("май", 5),
            ("мая", 5),
            ("не_месяц", 0),
        ],
    )
    def test_month_resolution(self, word: str, expected: int) -> None:
        """Месяц определяется по полному имени и общепринятым сокращениям."""
        assert resolve_month(word) == expected


class TestFindDates:
    """Проверки поиска нескольких дат в тексте."""

    def test_multiple_dates_in_order(self) -> None:
        """Даты находятся в порядке появления в тексте."""
        matches = find_dates("Действителен с 01.02.2024 по 31.01.2029, выдан 12.2023")
        values = [match.value for match in matches]
        assert values == [dt.date(2024, 2, 1), dt.date(2029, 1, 31), dt.date(2023, 12, 1)]

    def test_no_overlap(self) -> None:
        """Пересекающиеся совпадения не дублируются."""
        matches = find_dates("31.12.2029")
        assert len(matches) == 1

    def test_empty_text(self) -> None:
        """Пустой текст не порождает совпадений."""
        assert find_dates("") == []
        assert find_dates(None) == []


class TestParseDuration:
    """Проверки разбора срока годности, заданного длительностью."""

    def test_years(self) -> None:
        """«3 года» разбирается как 3 года."""
        duration = parse_duration("Срок годности 3 года")
        assert duration is not None
        assert duration.years == 3

    def test_months(self) -> None:
        """«18 месяцев» разбирается как relativedelta с суммарным периодом 18 мес.

        ``dateutil.relativedelta`` нормализует значения свыше 12 месяцев в
        годы и месяцы (``months=18`` становится ``years=1, months=6``) — это
        штатное поведение библиотеки, а не результат работы ``parse_duration``.
        """
        duration = parse_duration("Срок годности 18 месяцев")
        assert duration is not None
        assert duration.years * 12 + duration.months == 18

    def test_short_month_period(self) -> None:
        """Период до 12 месяцев не нормализуется в годы."""
        duration = parse_duration("Срок годности 6 месяцев")
        assert duration is not None
        assert duration.years == 0
        assert duration.months == 6

    def test_no_duration(self) -> None:
        """Текст без длительности возвращает None."""
        assert parse_duration("Без указания срока") is None


class TestDaysBetween:
    """Проверки вычисления разницы в днях."""

    def test_basic_difference(self) -> None:
        """Разница вычисляется как (left - right).days."""
        assert days_between(dt.date(2025, 1, 10), dt.date(2025, 1, 1)) == 9

    def test_none_returns_none(self) -> None:
        """Отсутствие одной из дат даёт None."""
        assert days_between(None, dt.date(2025, 1, 1)) is None
        assert days_between(dt.date(2025, 1, 1), None) is None


class TestExpirySimilarity:
    """Проверки оценки соответствия срока сертификата."""

    def test_missing_certificate_expiry(self) -> None:
        """Отсутствие срока сертификата даёт нейтральную оценку."""
        assert expiry_similarity(None, None) == pytest.approx(0.6)

    def test_expired_certificate_scores_zero(self) -> None:
        """Просроченный сертификат получает нулевую оценку."""
        score = expiry_similarity(dt.date(2020, 1, 1), None, reference=dt.date(2025, 1, 1))
        assert score == pytest.approx(0.0)

    def test_exact_match_with_requested(self) -> None:
        """Точное совпадение с требуемым сроком даёт максимум."""
        score = expiry_similarity(
            dt.date(2029, 1, 1), dt.date(2029, 1, 1), reference=dt.date(2025, 1, 1)
        )
        assert score == pytest.approx(1.0)

    def test_far_from_requested_scores_low_but_not_zero(self) -> None:
        """Большое расхождение с требуемым сроком сильно снижает оценку, но не до нуля.

        Не обнуляем намеренно: если ни один сертификат не попал в окно
        допуска, подбор должен уметь выбрать «ближайший подходящий» вариант
        среди кандидатов, а не увидеть у всех одинаковый ноль.
        """
        score = expiry_similarity(
            dt.date(2029, 1, 1),
            dt.date(2026, 1, 1),
            reference=dt.date(2025, 1, 1),
            tolerance_days=180,
        )
        assert 0.0 < score < 0.3

    def test_within_tolerance_window_scores_high(self) -> None:
        """Срок в пределах окна допуска получает высокую, но не максимальную оценку."""
        score = expiry_similarity(
            dt.date(2026, 6, 20),  # +19 дней от требуемого
            dt.date(2026, 6, 1),
            reference=dt.date(2025, 1, 1),
            tolerance_days=45,
        )
        assert 0.85 < score < 1.0

    def test_exact_tolerance_boundary(self) -> None:
        """На границе окна (ровно tolerance_days) оценка равна 0.85 в обе стороны."""
        before = expiry_similarity(
            dt.date(2026, 4, 17),  # -45 дней
            dt.date(2026, 6, 1),
            reference=dt.date(2025, 1, 1),
            tolerance_days=45,
        )
        after = expiry_similarity(
            dt.date(2026, 7, 16),  # +45 дней
            dt.date(2026, 6, 1),
            reference=dt.date(2025, 1, 1),
            tolerance_days=45,
        )
        assert before == pytest.approx(0.85)
        assert after == pytest.approx(0.85)

    def test_score_never_reaches_zero_for_a_valid_certificate(self) -> None:
        """Даже огромное расхождение не обнуляет оценку действующего сертификата."""
        score = expiry_similarity(
            dt.date(2099, 1, 1),
            dt.date(2026, 6, 1),
            reference=dt.date(2025, 1, 1),
            tolerance_days=45,
        )
        assert score > 0.0

    def test_closer_out_of_window_certificate_still_ranks_higher(self) -> None:
        """За пределами окна допуска более близкий срок всё равно оценивается выше.

        Прямая проверка требования «если в пределах ±45 дней ничего не
        нашлось — предложить сертификаты с наиболее близким сроком»: чтобы
        подбор мог ранжировать кандидатов по близости, их оценки не должны
        совпадать (что происходило бы при жёстком обнулении за окном).
        """
        requested = dt.date(2026, 6, 1)
        closer = expiry_similarity(
            dt.date(2026, 9, 1),
            requested,
            reference=dt.date(2025, 1, 1),
            tolerance_days=45,
        )
        farther = expiry_similarity(
            dt.date(2027, 6, 1),
            requested,
            reference=dt.date(2025, 1, 1),
            tolerance_days=45,
        )
        assert closer > farther > 0.0

    def test_score_is_monotonic_in_distance(self) -> None:
        """Оценка убывает монотонно с ростом расхождения — окно и «хвост» без разрывов."""
        requested = dt.date(2026, 6, 1)
        scores = [
            expiry_similarity(
                requested + dt.timedelta(days=diff),
                requested,
                reference=dt.date(2025, 1, 1),
                tolerance_days=45,
            )
            for diff in range(0, 400)
        ]
        assert all(earlier >= later for earlier, later in itertools.pairwise(scores))

    def test_fefo_prefers_nearer_expiry(self) -> None:
        """Без требуемого срока действует принцип FEFO: ближе срок — выше оценка."""
        near = expiry_similarity(dt.date(2026, 1, 1), None, reference=dt.date(2025, 8, 4))
        far = expiry_similarity(dt.date(2035, 1, 1), None, reference=dt.date(2025, 8, 4))
        assert near > far
        assert far >= 0.79  # валидный сертификат всё равно получает высокую оценку

    def test_valid_certificate_always_above_expired(self) -> None:
        """Валидный сертификат всегда оценивается выше просроченного."""
        valid = expiry_similarity(dt.date(2026, 1, 1), None, reference=dt.date(2025, 8, 4))
        expired = expiry_similarity(dt.date(2024, 1, 1), None, reference=dt.date(2025, 8, 4))
        assert valid > expired


class TestFormatDate:
    """Проверки форматирования даты для интерфейса."""

    def test_formats_with_default_pattern(self) -> None:
        """Дата форматируется как ДД.ММ.ГГГГ по умолчанию."""
        assert format_date(dt.date(2029, 3, 22)) == "22.03.2029"

    def test_none_returns_placeholder(self) -> None:
        """Отсутствующая дата отображается прочерком."""
        assert format_date(None) == "—"
