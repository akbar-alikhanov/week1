"""Тесты доменной модели строки базы сроков годности."""

from __future__ import annotations

import datetime as dt

from app.core.text import normalize
from app.models.expiry_stock import ExpiryStockEntry


class TestNormalizedName:
    """Проверки автоматического построения ключа поиска."""

    def test_derived_from_product_name_when_not_given(self) -> None:
        """normalized_name достраивается из product_name, если не задан явно."""
        entry = ExpiryStockEntry(product_name="TP Herbal  100ml.")
        assert entry.normalized_name == normalize("TP Herbal  100ml.")
        assert entry.normalized_name != ""

    def test_explicit_value_is_not_overwritten(self) -> None:
        """Явно переданный normalized_name не пересчитывается."""
        entry = ExpiryStockEntry(product_name="Товар", normalized_name="уже нормализовано")
        assert entry.normalized_name == "уже нормализовано"


class TestSummary:
    """Проверки однострочного описания партии."""

    def test_includes_expiry_when_present(self) -> None:
        """При известном сроке годности он попадает в описание."""
        entry = ExpiryStockEntry(
            product_name="Крем детский", expiry_date=dt.date(2026, 12, 31), quantity=10
        )
        summary = entry.summary()
        assert "Крем детский" in summary
        assert "31.12.2026" in summary
        assert "остаток 10" in summary

    def test_omits_expiry_when_absent(self) -> None:
        """Без срока годности описание обходится без даты."""
        entry = ExpiryStockEntry(product_name="Крем детский", quantity=5)
        summary = entry.summary()
        assert "Крем детский" in summary
        assert "до " not in summary


class TestRowRoundTrip:
    """Проверки (де)сериализации в/из строки SQLite."""

    def test_to_row_serializes_expiry_as_iso_string(self) -> None:
        """to_row() кодирует дату в ISO-строку для хранения в SQLite."""
        entry = ExpiryStockEntry(product_name="Товар", expiry_date=dt.date(2027, 3, 5))
        row = entry.to_row()
        assert row["expiry_date"] == "2027-03-05"

    def test_to_row_keeps_none_expiry_as_none(self) -> None:
        """Отсутствующий срок годности сохраняется как NULL, а не пустая строка."""
        entry = ExpiryStockEntry(product_name="Товар")
        row = entry.to_row()
        assert row["expiry_date"] is None

    def test_from_row_round_trip_preserves_fields(self) -> None:
        """Запись, прошедшая to_row() → from_row(), эквивалентна исходной."""
        original = ExpiryStockEntry(
            product_name="Крем детский 100 мл",
            expiry_date=dt.date(2026, 6, 15),
            quantity=42.5,
            source_row=7,
        )
        restored = ExpiryStockEntry.from_row(original.to_row())

        assert restored.product_name == original.product_name
        assert restored.normalized_name == original.normalized_name
        assert restored.expiry_date == original.expiry_date
        assert restored.quantity == original.quantity
        assert restored.source_row == original.source_row

    def test_from_row_defaults_missing_fields(self) -> None:
        """Отсутствующие поля в строке восстанавливаются значениями по умолчанию."""
        restored = ExpiryStockEntry.from_row({"product_name": "Товар"})
        assert restored.quantity == 0.0
        assert restored.source_row == 0
        assert restored.expiry_date is None
