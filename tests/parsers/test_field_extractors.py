"""Тесты извлечения полей сертификата из текста."""

from __future__ import annotations

import datetime as dt

from app.parsers.field_extractors import (
    extract_all,
    extract_certificate_number,
    extract_dates,
    extract_labeled_value,
    extract_product_name,
    split_lines,
)

_SAMPLE_TEXT = """ОРГАН ПО СЕРТИФИКАЦИИ ПРОДУКЦИИ "UZTEST"
СЕРТИФИКАТ СООТВЕТСТВИЯ
№ UZ.AMT.01.183255

Продукция: Лечебные травы, сироп 100 мл
Торговая марка: «Herbal Doctor»
Изготовитель: ООО "ФИТО-ФАРМ", Республика Узбекистан
Заявитель: ООО "BALTON TRADING ASIA"
Страна происхождения: Узбекистан
Код ТН ВЭД: 2106 90 980 9
Соответствует требованиям O'z DSt 1219:2018
Срок действия: с 22.03.2024 по 22.03.2029
Дата регистрации: 22.03.2024
Руководитель органа по сертификации   Иванов И.И.
"""


class TestExtractCertificateNumber:
    """Проверки извлечения номера сертификата."""

    def test_number_after_hash_sign(self) -> None:
        """Номер после знака № извлекается корректно."""
        assert extract_certificate_number(_SAMPLE_TEXT) == "UZ.AMT.01.183255"

    def test_fallback_to_filename(self) -> None:
        """При отсутствии номера в тексте используется имя файла."""
        number = extract_certificate_number("Текст без номера", filename="183600.pdf")
        assert number == "183600"

    def test_no_number_anywhere(self) -> None:
        """При полном отсутствии данных возвращается пустая строка."""
        assert extract_certificate_number("Ничего полезного здесь нет") == ""


class TestExtractDates:
    """Проверки извлечения дат сертификата."""

    def test_validity_range(self) -> None:
        """Диапазон «с ... по ...» разбирается на начало и конец."""
        issued, valid_from, expiry = extract_dates(_SAMPLE_TEXT)
        assert valid_from == dt.date(2024, 3, 22)
        assert expiry == dt.date(2029, 3, 22)
        assert issued == dt.date(2024, 3, 22)

    def test_single_expiry_date(self) -> None:
        """Текст с единственной формулировкой срока разбирается корректно."""
        _, _, expiry = extract_dates("Действителен до 18.04.2029")
        assert expiry == dt.date(2029, 4, 18)

    def test_no_dates(self) -> None:
        """Текст без дат не порождает исключений."""
        assert extract_dates("Без дат") == (None, None, None)

    def test_duration_based_expiry(self) -> None:
        """Срок действия, заданный длительностью, вычисляется от даты выдачи."""
        text = "Дата регистрации: 01.01.2024. Срок годности 3 года."
        issued, _, expiry = extract_dates(text)
        assert issued == dt.date(2024, 1, 1)
        assert expiry == dt.date(2027, 1, 1)


class TestExtractLabeledValue:
    """Проверки извлечения значения по метке поля."""

    def test_value_on_same_line(self) -> None:
        """Значение в той же строке, что и метка, извлекается полностью."""
        lines = split_lines(_SAMPLE_TEXT)
        value = extract_labeled_value(lines, ("изготовитель",))
        assert "ФИТО-ФАРМ" in value

    def test_missing_label_returns_empty(self) -> None:
        """Отсутствующая метка даёт пустую строку."""
        lines = split_lines("Просто текст без меток")
        assert extract_labeled_value(lines, ("несуществующая метка",)) == ""

    def test_longer_label_wins_over_shorter(self) -> None:
        """Более длинная метка («страна происхождения») не путается с короткой («страна»)."""
        lines = split_lines(_SAMPLE_TEXT)
        value = extract_labeled_value(lines, ("страна происхождения", "страна"))
        assert value == "Узбекистан"


class TestExtractProductName:
    """Проверки извлечения наименования продукции."""

    def test_labeled_product(self) -> None:
        """Наименование извлекается по метке «Продукция»."""
        lines = split_lines(_SAMPLE_TEXT)
        name = extract_product_name(lines, filename="183255.pdf")
        assert "Лечебные травы" in name

    def test_falls_back_to_filename(self) -> None:
        """При отсутствии текста используется имя файла."""
        name = extract_product_name([], filename="183600.pdf")
        assert name == "183600"

    def test_heuristic_without_label(self) -> None:
        """Без метки применяется эвристика по самой длинной строке."""
        lines = split_lines("Шапка документа\nЛечебные травы, сироп от кашля 100 мл\n№12345")
        name = extract_product_name(lines)
        assert "Лечебные травы" in name


class TestExtractAll:
    """Интеграционные проверки полного извлечения полей."""

    def test_full_extraction(self) -> None:
        """Полный текст даёт высокую уверенность извлечения."""
        fields = extract_all(_SAMPLE_TEXT, filename="183255.pdf")
        assert "Лечебные травы" in fields.product_name
        assert fields.certificate_number == "UZ.AMT.01.183255"
        assert fields.expiry_date == dt.date(2029, 3, 22)
        assert fields.brand == "Herbal Doctor"
        assert fields.country == "Узбекистан"
        assert fields.confidence >= 0.8

    def test_empty_text_gives_warnings(self) -> None:
        """Пустой текст (скан без OCR) порождает предупреждения и низкую уверенность."""
        fields = extract_all("", filename="unnamed.pdf")
        assert fields.product_name == "unnamed"
        assert fields.warnings
        assert fields.confidence == 0.0

    def test_minimal_text_still_extracts_basics(self) -> None:
        """Минималистичный документ без меток всё равно даёт базовые поля."""
        text = (
            "MUVOFIQLIK SERTIFIKATI\nNo 183600\nЛечебные травы 100 мл\nДействителен до 18.04.2029"
        )
        fields = extract_all(text, filename="183600.pdf")
        assert fields.expiry_date == dt.date(2029, 4, 18)
        assert fields.certificate_number == "183600"
