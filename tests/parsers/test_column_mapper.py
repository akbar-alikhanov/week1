"""Тесты распознавания структуры файла заказа."""

from __future__ import annotations

from typing import Any

from app.parsers.column_mapper import (
    ROLE_CERTIFICATE,
    ROLE_EXPIRY,
    ROLE_PRODUCT,
    ROLE_QUANTITY,
    detect_mapping,
)


class TestDetectMapping:
    """Проверки распознавания заголовка и колонок."""

    def test_standard_header(self) -> None:
        """Стандартный заголовок распознаётся с ролями всех колонок."""
        rows: list[list[Any]] = [
            ["№", "Код", "Наименование товара", "Кол-во", "Сертификат", "Срок сертификата"],
            [1, "BT-1", "Товар А", 10, None, None],
            [2, "BT-2", "Товар Б", 20, None, None],
        ]
        mapping = detect_mapping(rows)
        assert mapping.is_valid
        assert mapping.header_row == 1
        assert mapping.columns[ROLE_PRODUCT] == 2
        assert mapping.columns[ROLE_QUANTITY] == 3
        assert mapping.columns[ROLE_CERTIFICATE] == 4
        assert mapping.columns[ROLE_EXPIRY] == 5

    def test_header_not_on_first_row(self) -> None:
        """Заголовок, смещённый вниз (шапка компании), находится корректно."""
        rows: list[list[Any]] = [
            ['ООО "BALTON TRADING ASIA"', None, None],
            ["Заказ № 123 от 01.01.2025", None, None],
            [None, None, None],
            ["№", "Наименование товара", "Кол-во"],
            [1, "Товар А", 5],
        ]
        mapping = detect_mapping(rows)
        assert mapping.is_valid
        assert mapping.header_row == 4

    def test_alternative_wording(self) -> None:
        """Альтернативные формулировки заголовков распознаются."""
        rows = [["Товар", "Объем", "Бренд"], ["Позиция 1", "100 мл", "Марка"]]
        mapping = detect_mapping(rows)
        assert mapping.is_valid
        assert mapping.columns[ROLE_PRODUCT] == 0

    def test_no_header_falls_back_to_heuristic(self) -> None:
        """При отсутствии заголовка применяется эвристика по содержимому."""
        rows = [
            [1, "Лечебные травы, сироп 100 мл", 10],
            [2, "Масло облепиховое 100 мл", 20],
            [3, "Витамин C, таблетки жевательные", 30],
        ]
        mapping = detect_mapping(rows)
        assert mapping.is_valid
        assert mapping.columns[ROLE_PRODUCT] == 1

    def test_empty_rows(self) -> None:
        """Пустой список строк не даёт валидного результата."""
        mapping = detect_mapping([])
        assert not mapping.is_valid

    def test_uzbek_headers(self) -> None:
        """Заголовки на узбекском языке распознаются."""
        rows: list[list[Any]] = [["Mahsulot nomi", "Miqdor"], ["Тестовый товар", 5]]
        mapping = detect_mapping(rows)
        assert mapping.is_valid
        assert mapping.columns[ROLE_PRODUCT] == 0
