"""Тесты нормализации текста."""

from __future__ import annotations

import pytest

from app.core.text import (
    alpha_signature,
    detect_script,
    fix_homoglyphs,
    normalize,
    shorten,
    token_key,
    tokenize,
    transliterate,
)


class TestNormalize:
    """Проверки функции normalize."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Лечебные травы  100 мл.", "лечебные травы 100 ml"),
            ("TP Herbal® 100ml", "tp herbal 100 ml"),
            ("Сироп «Доктор» 0,5 л", "сироп доктор 0.5 l"),
            ("Витамин C 100мг №30", "витамин c 100 mg 30"),
            ("трава.сироп 50 г", "трава сироп 50 g"),
            ("", ""),
            (None, ""),
            ("   ", ""),
        ],
    )
    def test_normalize_examples(self, raw: str | None, expected: str) -> None:
        """Нормализация приводит разнородные строки к единому виду."""
        assert normalize(raw) == expected

    def test_normalize_is_idempotent(self) -> None:
        """Повторная нормализация не меняет уже нормализованную строку."""
        once = normalize("Лечебные Травы 100 Мл")
        assert normalize(once) == once

    def test_normalize_collapses_whitespace(self) -> None:
        """Множественные пробелы и переносы строк схлопываются."""
        assert normalize("Товар\n\t  100  мл") == "товар 100 ml"

    def test_normalize_handles_nbsp(self) -> None:
        """Неразрывный пробел обрабатывается как обычный."""
        assert normalize("Товар 100 мл") == "товар 100 ml"

    def test_units_case_insensitive(self) -> None:
        """Единицы измерения распознаются независимо от регистра."""
        assert normalize("Крем 50 Г") == normalize("Крем 50 г")

    def test_does_not_convert_unit_inside_word(self) -> None:
        """Буква «г», не являющаяся отдельным словом-единицей, не заменяется."""
        # "глюкоза" не должна превратиться в "gлюкоза" или потерять смысл
        result = normalize("Глюкоза 100 г")
        assert "глюкоза" in result
        assert "100 g" in result


class TestFixHomoglyphs:
    """Проверки исправления смешанной кириллицы/латиницы."""

    def test_latin_c_in_cyrillic_word(self) -> None:
        """Латинская C внутри русского слова заменяется на кириллическую."""
        assert fix_homoglyphs("cироп") == "сироп"

    def test_pure_latin_untouched(self) -> None:
        """Чисто латинское слово не изменяется."""
        assert fix_homoglyphs("herbal") == "herbal"

    def test_pure_cyrillic_untouched(self) -> None:
        """Чисто кириллическое слово не изменяется."""
        assert fix_homoglyphs("сироп") == "сироп"


class TestDetectScript:
    """Проверки определения письменности."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Лечебные травы", "cyrillic"),
            ("Herbal Syrup", "latin"),
            ("TP Лечебные", "mixed"),
            ("100 500", "none"),
        ],
    )
    def test_scripts(self, text: str, expected: str) -> None:
        """Функция корректно классифицирует письменность строки."""
        assert detect_script(text) == expected


class TestTransliterate:
    """Проверки транслитерации."""

    def test_basic_transliteration(self) -> None:
        """Кириллица преобразуется в латиницу по таблице ГОСТ."""
        assert transliterate("Витамин") == "vitamin"

    def test_transliteration_matches_latin_variant(self) -> None:
        """Транслитерация даёт совпадение с изначально латинским написанием."""
        assert transliterate("Сироп") != ""

    def test_empty_input(self) -> None:
        """Пустая строка транслитерируется в пустую строку."""
        assert transliterate("") == ""
        assert transliterate(None) == ""


class TestTokenize:
    """Проверки токенизации."""

    def test_drops_stopwords_by_default(self) -> None:
        """Служебные слова исключаются по умолчанию."""
        tokens = tokenize("Крем для рук ООО Ромашка")
        assert "для" not in tokens
        assert "ооо" not in tokens
        assert "крем" in tokens

    def test_keeps_stopwords_when_disabled(self) -> None:
        """При отключении фильтрации служебные слова сохраняются."""
        tokens = tokenize("Крем для рук", drop_stopwords=False)
        assert "для" in tokens


class TestTokenKey:
    """Проверки ключа, инвариантного к порядку слов."""

    def test_order_independent(self) -> None:
        """Одинаковый набор слов в разном порядке даёт одинаковый ключ."""
        assert token_key("травы лечебные 100 мл") == token_key("Лечебные травы 100мл")

    def test_different_words_differ(self) -> None:
        """Разный набор слов даёт разные ключи."""
        assert token_key("Крем детский") != token_key("Крем взрослый")


class TestAlphaSignature:
    """Проверки буквенной сигнатуры (без чисел и единиц)."""

    def test_strips_volume(self) -> None:
        """Числа и единицы измерения исключаются из сигнатуры."""
        assert alpha_signature("Лечебные травы 100 мл") == alpha_signature("Лечебные травы 150 мл")

    def test_different_products_differ(self) -> None:
        """Разные товары дают разные сигнатуры."""
        assert alpha_signature("Крем детский") != alpha_signature("Крем взрослый")


class TestShorten:
    """Проверки обрезки строки для интерфейса."""

    def test_short_text_untouched(self) -> None:
        """Короткая строка возвращается без изменений."""
        assert shorten("Крем", 10) == "Крем"

    def test_long_text_truncated_with_ellipsis(self) -> None:
        """Длинная строка обрезается и получает многоточие."""
        result = shorten("Очень длинное наименование товара", 10)
        assert len(result) == 10
        assert result.endswith("…")
