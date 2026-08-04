"""Тесты лексического (нечёткого) поиска."""

from __future__ import annotations

from app.ai.fuzzy import LexicalIndex, similarity
from tests.conftest import make_certificate


class TestSimilarity:
    """Проверки точечного сравнения двух наименований."""

    def test_identical_strings(self) -> None:
        """Идентичные строки дают максимальное совпадение."""
        assert similarity("Лечебные травы 100 мл", "Лечебные травы 100 мл") == 1.0

    def test_case_insensitive(self) -> None:
        """Сравнение нечувствительно к регистру."""
        assert similarity("ЛЕЧЕБНЫЕ ТРАВЫ", "лечебные травы") == 1.0

    def test_does_not_confuse_different_products_with_shared_volume(self) -> None:
        """Разные товары с одинаковым объёмом не считаются похожими.

        Это регрессионный тест на дефект, при котором «Масло облепиховое 100 мл»
        и «Гель антисептический 100 мл» получали завышенную оценку из-за общего
        численного фрагмента «100 ml».
        """
        score = similarity("Масло облепиховое 100 мл", "Гель антисептический для рук 100 мл")
        assert score < 0.5

    def test_same_product_different_volume_scores_high(self) -> None:
        """Один и тот же товар в разной фасовке даёт высокую лексическую оценку.

        Разграничение по объёму — обязанность отдельной составляющей
        (:mod:`app.core.units`), а не лексического сравнения текста.
        """
        score = similarity("Лечебные травы, сироп 100 мл", "Лечебные травы, сироп 150 мл")
        assert score > 0.85

    def test_empty_strings(self) -> None:
        """Пустые строки дают нулевое совпадение."""
        assert similarity("", "Товар") == 0.0
        assert similarity("Товар", "") == 0.0

    def test_cross_script_similarity_is_low_without_translit_hint(self) -> None:
        """Без общих смысловых токенов латиница и кириллица не считаются похожими."""
        score = similarity("Cough syrup", "Крем для рук")
        assert score < 0.4


class TestLexicalIndex:
    """Проверки индекса нечёткого поиска."""

    def test_search_finds_exact_match_first(self) -> None:
        """Точное совпадение оказывается на первом месте."""
        certificates = [
            make_certificate("Лечебные травы, сироп 100 мл", "/c/1.pdf"),
            make_certificate("Сироп шиповника 100 мл", "/c/2.pdf"),
        ]
        index = LexicalIndex(certificates)
        hits = index.search("Лечебные травы, сироп 100 мл")
        assert hits[0].certificate.pdf_path == "/c/1.pdf"
        assert hits[0].score > 0.95

    def test_search_ranks_volume_variant_below_exact(self) -> None:
        """Тот же товар другого объёма оценивается ниже точного совпадения."""
        certificates = [
            make_certificate("Лечебные травы, сироп 100 мл", "/c/100.pdf"),
            make_certificate("Лечебные травы, сироп 150 мл", "/c/150.pdf"),
        ]
        index = LexicalIndex(certificates)
        hits = index.search("Лечебные травы, сироп 100 мл")
        by_path = {hit.certificate.pdf_path: hit.score for hit in hits}
        assert by_path["/c/100.pdf"] > by_path["/c/150.pdf"]

    def test_search_does_not_confuse_unrelated_products(self) -> None:
        """Не связанные товары с общим числом объёма не выходят в лидеры."""
        certificates = [
            make_certificate("Масло облепиховое 100 мл", "/c/oil.pdf"),
            make_certificate("Гель антисептический для рук 100 мл", "/c/gel.pdf"),
        ]
        index = LexicalIndex(certificates)
        hits = index.search("Масло облепиховое 100мл")
        assert hits[0].certificate.pdf_path == "/c/oil.pdf"

    def test_empty_index_returns_empty(self) -> None:
        """Пустой индекс не порождает ошибок."""
        assert LexicalIndex([]).search("Что угодно") == []

    def test_translit_matches_latin_query(self) -> None:
        """Латинский запрос находит кириллическое наименование через транслитерацию."""
        certificates = [make_certificate("Витамин С 100 мг", "/c/vitamin.pdf")]
        index = LexicalIndex(certificates)
        hits = index.search("Vitamin C 100mg")
        assert hits
        assert hits[0].certificate.pdf_path == "/c/vitamin.pdf"

    def test_search_by_signature_finds_other_volumes(self) -> None:
        """Поиск по сигнатуре находит все фасовки товара."""
        certificates = [
            make_certificate("Лечебные травы, сироп 100 мл", "/c/100.pdf"),
            make_certificate("Лечебные травы, сироп 150 мл", "/c/150.pdf"),
            make_certificate("Сироп шиповника 100 мл", "/c/other.pdf"),
        ]
        index = LexicalIndex(certificates)
        hits = index.search_by_signature("Лечебные травы, сироп")
        paths = {hit.certificate.pdf_path for hit in hits}
        assert "/c/100.pdf" in paths
        assert "/c/150.pdf" in paths
