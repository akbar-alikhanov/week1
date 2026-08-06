"""Тесты распознавания структуры файла заказа."""

from __future__ import annotations

from typing import Any

from app.parsers.column_mapper import (
    ROLE_CERTIFICATE,
    ROLE_CERTIFICATE_EXPIRY,
    ROLE_EXPIRY,
    ROLE_PRODUCT,
    ROLE_QUANTITY,
    detect_mapping,
)


class TestDetectMapping:
    """Проверки распознавания заголовка и колонок."""

    def test_standard_header(self) -> None:
        """Стандартный заголовок распознаётся с ролями всех колонок.

        «Требуемый срок годности» (входной, из заказа) и «Срок сертификата»
        (выходной, пишет программа) — заведомо разные колонки в этом
        примере, поэтому обе роли должны получить РАЗНЫЕ индексы: смешение
        этих ролей и было причиной затирания срока годности заказа.
        """
        rows: list[list[Any]] = [
            [
                "№",
                "Код",
                "Наименование товара",
                "Кол-во",
                "Требуемый срок годности",
                "Сертификат",
                "Срок сертификата",
            ],
            [1, "BT-1", "Товар А", 10, None, None, None],
            [2, "BT-2", "Товар Б", 20, None, None, None],
        ]
        mapping = detect_mapping(rows)
        assert mapping.is_valid
        assert mapping.header_row == 1
        assert mapping.columns[ROLE_PRODUCT] == 2
        assert mapping.columns[ROLE_QUANTITY] == 3
        assert mapping.columns[ROLE_EXPIRY] == 4
        assert mapping.columns[ROLE_CERTIFICATE] == 5
        assert mapping.columns[ROLE_CERTIFICATE_EXPIRY] == 6

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


class TestRequestedVsCertificateExpiry:
    """Регрессия: требуемый срок заказа и срок сертификата — разные роли.

    До исправления обе колонки распознавались одной и той же ролью
    (``ROLE_EXPIRY``), из-за чего запись найденного срока сертификата
    затирала требуемый срок годности заказа — критическая ошибка.
    """

    def test_requested_expiry_alone_maps_to_expiry_role(self) -> None:
        """«Требуемый срок годности» без соседней колонки сертификата — ROLE_EXPIRY."""
        rows: list[list[Any]] = [
            ["№", "Наименование товара", "Требуемый срок годности"],
            [1, "Товар", None],
        ]
        mapping = detect_mapping(rows)
        assert mapping.columns.get(ROLE_EXPIRY) == 2
        assert ROLE_CERTIFICATE_EXPIRY not in mapping.columns

    def test_legacy_certificate_expiry_wording_maps_to_certificate_role(self) -> None:
        """«Срок сертификата» (прежняя формулировка) больше не путается со сроком заказа."""
        rows: list[list[Any]] = [
            ["№", "Наименование товара", "Срок сертификата"],
            [1, "Товар", None],
        ]
        mapping = detect_mapping(rows)
        assert mapping.columns.get(ROLE_CERTIFICATE_EXPIRY) == 2
        assert ROLE_EXPIRY not in mapping.columns

    def test_generated_header_maps_back_to_certificate_expiry_role(self) -> None:
        """Заголовок «С.Г. сертификата», который создаёт сама программа, распознаётся
        как та же роль при повторном разборе — иначе колонка дублировалась бы.
        """
        rows: list[list[Any]] = [
            ["№", "Наименование товара", "Сертификат", "С.Г. сертификата"],
            [1, "Товар", None, None],
        ]
        mapping = detect_mapping(rows)
        assert mapping.columns.get(ROLE_CERTIFICATE) == 2
        assert mapping.columns.get(ROLE_CERTIFICATE_EXPIRY) == 3

    def test_both_columns_present_resolve_to_distinct_indices(self) -> None:
        """Требуемый срок заказа и срок сертификата, стоящие рядом, не смешиваются."""
        rows: list[list[Any]] = [
            [
                "№",
                "Наименование товара",
                "Кол-во",
                "Требуемый срок годности заказа",
                "Сертификат",
                "С.Г. сертификата",
            ],
            [1, "Товар", 5, None, None, None],
        ]
        mapping = detect_mapping(rows)
        assert mapping.columns[ROLE_EXPIRY] == 3
        assert mapping.columns[ROLE_CERTIFICATE] == 4
        assert mapping.columns[ROLE_CERTIFICATE_EXPIRY] == 5
