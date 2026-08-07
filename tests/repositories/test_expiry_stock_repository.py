"""Тесты репозитория базы сроков годности и остатков."""

from __future__ import annotations

import datetime as dt

from app.core.text import normalize
from app.repositories.expiry_stock_repository import ExpiryStockRepository
from tests.conftest import make_expiry_entry


class TestReplaceAll:
    """Проверки полной замены содержимого базы (импорт Excel)."""

    def test_assigns_ids_and_returns_count(
        self, expiry_stock_repository: ExpiryStockRepository
    ) -> None:
        """Каждой сохранённой записи присваивается идентификатор."""
        entries = [
            make_expiry_entry("Товар A", quantity=10),
            make_expiry_entry("Товар B", quantity=20),
        ]
        imported = expiry_stock_repository.replace_all(entries)

        assert imported == 2
        assert all(entry.id is not None for entry in entries)
        assert expiry_stock_repository.count() == 2

    def test_second_call_replaces_first_entirely(
        self, expiry_stock_repository: ExpiryStockRepository
    ) -> None:
        """Повторный импорт полностью стирает прежнее содержимое, а не дополняет его."""
        expiry_stock_repository.replace_all([make_expiry_entry("Старый товар", quantity=1)])
        expiry_stock_repository.replace_all([make_expiry_entry("Новый товар", quantity=2)])

        assert expiry_stock_repository.count() == 1
        remaining = expiry_stock_repository.list_all()
        assert remaining[0].product_name == "Новый товар"

    def test_empty_list_clears_database(
        self, expiry_stock_repository: ExpiryStockRepository
    ) -> None:
        """Импорт пустого списка (пустой файл) оставляет базу пустой."""
        expiry_stock_repository.replace_all([make_expiry_entry("Товар", quantity=1)])
        expiry_stock_repository.replace_all([])
        assert expiry_stock_repository.count() == 0

    def test_same_product_can_have_multiple_batches(
        self, expiry_stock_repository: ExpiryStockRepository
    ) -> None:
        """Один товар может встречаться много раз — по одной записи на партию."""
        expiry_stock_repository.replace_all(
            [
                make_expiry_entry("Товар", expiry_date=dt.date(2026, 1, 1), quantity=5),
                make_expiry_entry("Товар", expiry_date=dt.date(2027, 1, 1), quantity=7),
            ]
        )
        assert expiry_stock_repository.count() == 2


class TestFindByProductName:
    """Проверки точного поиска партий по нормализованному названию."""

    def test_finds_all_batches_of_product(
        self, expiry_stock_repository: ExpiryStockRepository
    ) -> None:
        """Находятся все партии товара, а не только первая."""
        expiry_stock_repository.replace_all(
            [
                make_expiry_entry("Крем детский 100 мл", expiry_date=dt.date(2026, 1, 1)),
                make_expiry_entry("Крем детский 100 мл", expiry_date=dt.date(2027, 1, 1)),
                make_expiry_entry("Другой товар", expiry_date=dt.date(2026, 1, 1)),
            ]
        )
        found = expiry_stock_repository.find_by_product_name(normalize("Крем детский 100 мл"))
        assert len(found) == 2

    def test_no_match_returns_empty_list(
        self, expiry_stock_repository: ExpiryStockRepository
    ) -> None:
        """Товар, отсутствующий в базе, возвращает пустой список, а не ошибку."""
        expiry_stock_repository.replace_all([make_expiry_entry("Товар", quantity=1)])
        assert expiry_stock_repository.find_by_product_name("совсем другой товар") == []

    def test_empty_query_returns_empty_list(
        self, expiry_stock_repository: ExpiryStockRepository
    ) -> None:
        """Пустая строка запроса не возвращает всю базу по ошибке."""
        expiry_stock_repository.replace_all([make_expiry_entry("Товар", quantity=1)])
        assert expiry_stock_repository.find_by_product_name("") == []

    def test_match_requires_exact_normalized_equality(
        self, expiry_stock_repository: ExpiryStockRepository
    ) -> None:
        """В отличие от подбора сертификата, здесь нет нечёткого сравнения."""
        expiry_stock_repository.replace_all([make_expiry_entry("Крем детский 100 мл")])
        assert expiry_stock_repository.find_by_product_name(normalize("Крем детский")) == []


class TestListAll:
    """Проверки полной выгрузки базы."""

    def test_returns_every_batch(self, expiry_stock_repository: ExpiryStockRepository) -> None:
        """list_all() возвращает все партии независимо от товара."""
        expiry_stock_repository.replace_all(
            [make_expiry_entry("Товар A"), make_expiry_entry("Товар B")]
        )
        assert len(expiry_stock_repository.list_all()) == 2

    def test_empty_database_returns_empty_list(
        self, expiry_stock_repository: ExpiryStockRepository
    ) -> None:
        """Пустая (ещё не импортированная) база возвращает пустой список."""
        assert expiry_stock_repository.list_all() == []


class TestStatistics:
    """Проверки сводки для панели мониторинга."""

    def test_counts_total_and_unique_products(
        self, expiry_stock_repository: ExpiryStockRepository
    ) -> None:
        """total считает все партии, unique_products — уникальные товары."""
        expiry_stock_repository.replace_all(
            [
                make_expiry_entry("Товар A", expiry_date=dt.date(2026, 1, 1)),
                make_expiry_entry("Товар A", expiry_date=dt.date(2027, 1, 1)),
                make_expiry_entry("Товар B", expiry_date=dt.date(2026, 1, 1)),
            ]
        )
        stats = expiry_stock_repository.statistics()
        assert stats["total"] == 3
        assert stats["unique_products"] == 2

    def test_empty_database_reports_zeros(
        self, expiry_stock_repository: ExpiryStockRepository
    ) -> None:
        """На пустой базе статистика — нули, а не ошибка деления."""
        stats = expiry_stock_repository.statistics()
        assert stats == {"total": 0, "unique_products": 0}
