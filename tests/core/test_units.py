"""Тесты разбора и сравнения объёмов."""

from __future__ import annotations

import pytest

from app.core.units import (
    DIMENSION_COUNT,
    DIMENSION_MASS,
    DIMENSION_VOLUME,
    extract_primary_volume,
    extract_volumes,
    volume_similarity,
)


class TestExtractVolumes:
    """Проверки извлечения объёма из текста."""

    def test_simple_ml(self) -> None:
        """Простой объём в миллилитрах распознаётся корректно."""
        volumes = extract_volumes("Лечебные травы 100 мл")
        assert len(volumes) == 1
        assert volumes[0].base_value == pytest.approx(100.0)
        assert volumes[0].base_unit == "ml"

    def test_liters_converted_to_ml(self) -> None:
        """Литры приводятся к миллилитрам."""
        volumes = extract_volumes("Настойка 0,5 л")
        assert volumes[0].base_value == pytest.approx(500.0)
        assert volumes[0].base_unit == "ml"

    def test_pack_notation(self) -> None:
        """Упаковка вида «2 x 100 мл» распознаётся с количеством."""
        volumes = extract_volumes("Сироп 2 х 100 мл")
        assert volumes[0].pack_count == 2
        assert volumes[0].base_value == pytest.approx(100.0)
        assert volumes[0].total_base_value == pytest.approx(200.0)

    def test_grams(self) -> None:
        """Масса в граммах распознаётся с размерностью mass."""
        volumes = extract_volumes("Крем 50 г")
        assert volumes[0].dimension == DIMENSION_MASS
        assert volumes[0].base_value == pytest.approx(50.0)

    def test_tablets_count(self) -> None:
        """Количество таблеток распознаётся с размерностью count.

        Извлечение объёма опирается на явную единицу измерения рядом с числом
        («30 таб»), а не на произвольный числовой признак вроде «№30» —
        последний слишком легко спутать с артикулом или номером партии.
        """
        volumes = extract_volumes("Таблетки 30 таб")
        assert volumes
        assert volumes[0].dimension == DIMENSION_COUNT

    def test_hash_number_alone_is_not_a_volume(self) -> None:
        """Номер после «№» без единицы измерения не считается объёмом."""
        assert extract_volumes("Таблетки №30") == []

    def test_no_volume(self) -> None:
        """Текст без числовых величин не даёт объёмов."""
        assert extract_volumes("Крем детский увлажняющий") == []

    def test_empty_input(self) -> None:
        """Пустая строка не вызывает ошибок."""
        assert extract_volumes("") == []
        assert extract_volumes(None) == []

    def test_implausible_value_rejected(self) -> None:
        """Аномально большие значения (похожие на номера) отбрасываются."""
        volumes = extract_volumes("Партия 999999 кг")
        assert volumes == []


class TestExtractPrimaryVolume:
    """Проверки выбора основного объёма."""

    def test_prefers_volume_over_count(self) -> None:
        """При наличии объёма и количества выбирается объём (мл)."""
        volume = extract_primary_volume("Сироп 100 мл, 30 таб")
        assert volume is not None
        assert volume.dimension == DIMENSION_VOLUME

    def test_returns_none_when_absent(self) -> None:
        """Возвращает None, если объём не найден."""
        assert extract_primary_volume("Крем детский") is None


class TestVolumeSimilarity:
    """Проверки оценки совпадения объёмов."""

    def test_identical_volumes(self) -> None:
        """Идентичные объёмы дают максимальную оценку."""
        left = extract_primary_volume("Товар 100 мл")
        right = extract_primary_volume("Товар 100 мл")
        assert volume_similarity(left, right) == pytest.approx(1.0)

    def test_within_tolerance(self) -> None:
        """Незначительная разница в пределах допуска даёт максимум."""
        left = extract_primary_volume("Товар 100 мл")
        right = extract_primary_volume("Товар 0,1 л")
        assert volume_similarity(left, right) == pytest.approx(1.0)

    def test_different_volumes_score_low(self) -> None:
        """Существенно разные объёмы дают низкую оценку."""
        left = extract_primary_volume("Товар 100 мл")
        right = extract_primary_volume("Товар 150 мл")
        score = volume_similarity(left, right)
        assert 0.0 < score < 1.0

    def test_far_apart_volumes_score_zero(self) -> None:
        """Втрое различающиеся объёмы дают нулевую оценку."""
        left = extract_primary_volume("Товар 100 мл")
        right = extract_primary_volume("Товар 500 мл")
        assert volume_similarity(left, right) == pytest.approx(0.0)

    def test_different_dimensions_score_zero(self) -> None:
        """Объём и количество несопоставимы — оценка ноль."""
        left = extract_primary_volume("Товар 100 мл")
        right = extract_primary_volume("Товар 30 таб")
        assert volume_similarity(left, right) == pytest.approx(0.0)

    def test_missing_data_returns_neutral_score(self) -> None:
        """Отсутствие объёма с одной из сторон даёт нейтральную оценку."""
        left = extract_primary_volume("Товар 100 мл")
        assert volume_similarity(left, None) == pytest.approx(0.55)
        assert volume_similarity(None, None) == pytest.approx(0.55)

    def test_pack_notation_compares_total(self) -> None:
        """Упаковка «2 x 100 мл» сравнивается по суммарному объёму."""
        pack = extract_primary_volume("Товар 2 х 100 мл")
        single = extract_primary_volume("Товар 200 мл")
        assert volume_similarity(pack, single) == pytest.approx(1.0)


class TestVolumeFormatting:
    """Проверки форматирования объёма для интерфейса."""

    def test_format_simple(self) -> None:
        """Простой объём форматируется как «значение единица»."""
        volume = extract_primary_volume("Товар 100 мл")
        assert volume is not None
        assert volume.format() == "100 мл"

    def test_format_liters_shown_in_ml(self) -> None:
        """Литры отображаются в миллилитрах после нормализации."""
        volume = extract_primary_volume("Товар 0,5 л")
        assert volume is not None
        assert volume.format() == "500 мл"

    def test_format_pack(self) -> None:
        """Упаковка форматируется с указанием количества."""
        volume = extract_primary_volume("Товар 2 х 100 мл")
        assert volume is not None
        assert volume.format() == "2 x 100 мл"
