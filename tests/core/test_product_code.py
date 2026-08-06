"""Тесты разбора системного наименования товара."""

from __future__ import annotations

from app.core.product_code import parse_product_name


class TestParseProductName:
    """Проверки разбора кода, типа, названия, объёма и упаковки."""

    def test_full_pattern_from_requirements(self) -> None:
        """Пример из требований разбирается на все пять составных частей."""
        parsed = parse_product_name("61004628 TP Dr Rabbit Kids Bubblegum 50ml [48]")

        assert parsed.code == "61004628"
        assert parsed.product_type == "TP"
        assert parsed.name == "Dr Rabbit Kids Bubblegum"
        assert parsed.volume is not None
        assert parsed.volume.base_value == 50.0
        assert parsed.volume.base_unit == "ml"
        assert parsed.box_quantity == 48

    def test_missing_box_quantity_is_none(self) -> None:
        """Без квадратных скобок количество в коробке не определяется."""
        parsed = parse_product_name("61004628 TP Dr Rabbit Kids Bubblegum 50ml")
        assert parsed.box_quantity is None
        assert parsed.name == "Dr Rabbit Kids Bubblegum"

    def test_missing_type_leaves_field_empty(self) -> None:
        """Без короткого кода типа (не ЗАГЛАВНЫЕ буквы) поле остаётся пустым."""
        parsed = parse_product_name("12345 Товар без типа 100 мл")
        assert parsed.code == "12345"
        assert parsed.product_type == ""
        assert parsed.name == "Товар без типа"

    def test_missing_code_leaves_field_empty(self) -> None:
        """Без ведущего числового кода поле кода остаётся пустым, тип распознаётся."""
        parsed = parse_product_name("TP Herbal 100ml")
        assert parsed.code == ""
        assert parsed.product_type == "TP"
        assert parsed.name == "Herbal"

    def test_free_form_text_without_code_or_type(self) -> None:
        """Свободный ввод без кода и типа не ломает разбор, название сохраняется целиком."""
        parsed = parse_product_name("Просто название без кода")
        assert parsed.code == ""
        assert parsed.product_type == ""
        assert parsed.name == "Просто название без кода"
        assert parsed.volume is None

    def test_raw_preserves_original_text(self) -> None:
        """Поле raw хранит исходную строку без изменений."""
        text = "  61004628 TP Dr Rabbit Kids Bubblegum 50ml [48]  "
        parsed = parse_product_name(text)
        assert parsed.raw == text

    def test_box_quantity_extracts_first_number_inside_brackets(self) -> None:
        """Из отметки количества в коробке берётся первое встретившееся число."""
        parsed = parse_product_name("Товар 100 мл [кор. 24]")
        assert parsed.box_quantity == 24

    def test_empty_string_returns_all_empty_fields(self) -> None:
        """Пустая строка не вызывает ошибок и не даёт ни одного поля."""
        parsed = parse_product_name("")
        assert parsed.code == ""
        assert parsed.product_type == ""
        assert parsed.name == ""
        assert parsed.volume is None
        assert parsed.box_quantity is None
