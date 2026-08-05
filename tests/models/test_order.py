"""Тесты доменной модели строки заказа."""

from __future__ import annotations

from app.models.order import OrderRow


class TestSearchTextCleaning:
    """Проверки очистки наименования от кода товара и отметки количества."""

    def test_strips_leading_product_code(self) -> None:
        """Числовой код товара в начале наименования убирается."""
        row = OrderRow(row_number=1, product_name="61004628 TP Dr Rabbit Kids Bubblegum 50ml")
        assert row.search_text == "TP Dr Rabbit Kids Bubblegum 50ml"

    def test_strips_trailing_pack_count_brackets(self) -> None:
        """Отметка количества в коробке в квадратных скобках убирается."""
        row = OrderRow(row_number=1, product_name="Dr Rabbit Kids Bubblegum 50ml [48]")
        assert row.search_text == "Dr Rabbit Kids Bubblegum 50ml"

    def test_strips_both_code_and_brackets_together(self) -> None:
        """Полный системный формат «код + наименование + объём + [кол-во]» очищается целиком."""
        row = OrderRow(row_number=1, product_name="61004628 TP Dr Rabbit Kids Bubblegum 50ml [48]")
        assert row.search_text == "TP Dr Rabbit Kids Bubblegum 50ml"

    def test_product_name_itself_is_unchanged(self) -> None:
        """Исходное наименование сохраняется как есть — для отчёта и отображения."""
        row = OrderRow(row_number=1, product_name="61004628 TP Dr Rabbit Kids Bubblegum 50ml [48]")
        assert row.product_name == "61004628 TP Dr Rabbit Kids Bubblegum 50ml [48]"

    def test_short_leading_number_is_not_treated_as_code(self) -> None:
        """Короткое число (меньше 4 цифр) не принимается за код товара."""
        row = OrderRow(row_number=1, product_name="911 Мазь охлаждающая 50 г")
        assert row.search_text == "911 Мазь охлаждающая 50 г"

    def test_digit_prefixed_real_name_is_preserved(self) -> None:
        """Наименование, начинающееся с цифры без кода (напр. «5-НОК»), не искажается."""
        row = OrderRow(row_number=1, product_name="5-НОК капли 10мл")
        assert row.search_text == "5-НОК капли 10мл"

    def test_multiple_bracket_groups_are_all_stripped(self) -> None:
        """Несколько скобочных групп подряд в конце убираются целиком."""
        row = OrderRow(row_number=1, product_name="Товар 50ml [48][доп]")
        assert row.search_text == "Товар 50ml"

    def test_plain_name_without_code_or_brackets_is_unaffected(self) -> None:
        """Наименование без кода и скобок не меняется."""
        row = OrderRow(row_number=1, product_name="Зубная паста Colgate 75мл")
        assert row.search_text == "Зубная паста Colgate 75мл"

    def test_cleaning_enables_correct_volume_extraction(self) -> None:
        """После очистки объём по-прежнему извлекается корректно."""
        row = OrderRow(row_number=1, product_name="61004628 TP Dr Rabbit Kids Bubblegum 50ml [48]")
        volume = row.volume
        assert volume is not None
        assert volume.base_value == 50.0
        assert volume.base_unit == "ml"

    def test_declared_volume_appended_to_cleaned_core_name(self) -> None:
        """Объём из отдельной колонки приклеивается к уже очищенному наименованию."""
        row = OrderRow(
            row_number=1,
            product_name="61004628 TP Dr Rabbit Kids Bubblegum [48]",
            declared_volume="50ml",
        )
        assert row.search_text == "TP Dr Rabbit Kids Bubblegum 50ml"

    def test_derived_fields_use_cleaned_text(self) -> None:
        """normalized_name и другие производные поля вычисляются из очищенного текста."""
        row = OrderRow(row_number=1, product_name="61004628 TP Dr Rabbit Kids Bubblegum 50ml [48]")
        assert "61004628" not in row.normalized_name


class TestIsEmpty:
    """Проверки признака пустой строки заказа."""

    def test_blank_product_name_is_empty(self) -> None:
        """Строка без наименования считается пустой (технической)."""
        row = OrderRow(row_number=1, product_name="   ")
        assert row.is_empty

    def test_non_blank_product_name_is_not_empty(self) -> None:
        """Строка с наименованием не считается пустой."""
        row = OrderRow(row_number=1, product_name="Товар")
        assert not row.is_empty
