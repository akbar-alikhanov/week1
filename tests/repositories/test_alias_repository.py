"""Тесты репозитория псевдонимов."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.exceptions import DuplicateAliasError
from app.models.alias import Alias
from app.repositories.alias_repository import AliasRepository


class TestSave:
    """Проверки сохранения псевдонимов."""

    def test_save_assigns_id(self, alias_repository: AliasRepository) -> None:
        """Новый псевдоним получает идентификатор при сохранении."""
        alias = Alias(source_text="TP Herbal 100ml", target_name="Товар")
        saved = alias_repository.save(alias)
        assert saved.id is not None

    def test_save_is_idempotent_for_same_source(self, alias_repository: AliasRepository) -> None:
        """Повторное сохранение того же источника обновляет запись, не дублируя."""
        alias_repository.save(Alias(source_text="TP Herbal", target_name="A"))
        alias_repository.save(Alias(source_text="TP Herbal", target_name="A (уточнено)"))
        assert alias_repository.count() == 1

    def test_save_different_source_creates_new_record(
        self, alias_repository: AliasRepository
    ) -> None:
        """Разные исходные наименования создают отдельные записи."""
        alias_repository.save(Alias(source_text="Товар A", target_name="Товар A"))
        alias_repository.save(Alias(source_text="Товар B", target_name="Товар B"))
        assert alias_repository.count() == 2


class TestFindForText:
    """Проверки поиска псевдонима по тексту заказа."""

    def test_exact_normalized_match(self, alias_repository: AliasRepository) -> None:
        """Точное совпадение нормализованного текста находит псевдоним."""
        alias_repository.save(Alias(source_text="TP Herbal 100ml", target_name="Товар"))
        found = alias_repository.find_for_text("tp  herbal 100 ml")
        assert len(found) == 1

    def test_token_order_independent_match(self, alias_repository: AliasRepository) -> None:
        """Соответствие находится даже при перестановке слов."""
        alias_repository.save(Alias(source_text="Лечебные травы 100 мл", target_name="Товар"))
        found = alias_repository.find_for_text("100мл травы лечебные")
        assert len(found) == 1

    def test_no_match_for_unrelated_text(self, alias_repository: AliasRepository) -> None:
        """Несвязанный текст не находит псевдонимов."""
        alias_repository.save(Alias(source_text="Товар А", target_name="Товар А"))
        assert alias_repository.find_for_text("Совершенно другой товар") == []

    def test_priority_by_weight(self, alias_repository: AliasRepository) -> None:
        """При нескольких совпадениях по токенам приоритет — у большего веса.

        Обе записи набраны в разном порядке слов, поэтому ни одна не даёт
        точного совпадения с запросом — сравнение идёт по набору токенов
        (``token_source``), где вес и решает, какая запись главнее.
        """
        alias_repository.save(
            Alias(source_text="лечебная сильная трава", target_name="A", weight=1.0)
        )
        alias_repository.save(
            Alias(source_text="трава лечебная сильная", target_name="B", weight=5.0)
        )
        found = alias_repository.find_for_text("сильная трава лечебная")
        assert found[0].target_name == "B"


class TestRegisterHit:
    """Проверки учёта применений псевдонима."""

    def test_hit_count_increments(self, alias_repository: AliasRepository) -> None:
        """Счётчик применений увеличивается при регистрации."""
        alias = alias_repository.save(Alias(source_text="Товар", target_name="Товар"))
        alias_repository.register_hit(alias.id)  # type: ignore[arg-type]
        alias_repository.register_hit(alias.id)  # type: ignore[arg-type]
        updated = alias_repository.find_for_text("Товар")[0]
        assert updated.hit_count == 2


class TestImportExport:
    """Проверки импорта и экспорта псевдонимов."""

    def test_export_and_import_json(
        self, alias_repository: AliasRepository, tmp_path: Path
    ) -> None:
        """Экспортированные псевдонимы корректно восстанавливаются при импорте."""
        alias_repository.save(
            Alias(source_text="TP Herbal 100ml", target_name="Лечебные травы 100 мл")
        )

        export_path = tmp_path / "aliases.json"
        exported = alias_repository.export_to_file(export_path)
        assert exported == 1

        alias_repository.clear()
        assert alias_repository.count() == 0

        added, merged, skipped = alias_repository.import_from_file(export_path)
        assert added == 1
        assert merged == 0
        assert skipped == 0
        assert alias_repository.count() == 1

    def test_import_skips_records_without_target_name(
        self, alias_repository: AliasRepository, tmp_path: Path
    ) -> None:
        """Импорт пропускает записи без обязательного русского названия."""
        import json

        payload = [{"source_text": "TP Herbal 100ml", "target_name": ""}]
        path = tmp_path / "aliases.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        added, merged, skipped = alias_repository.import_from_file(path)
        assert added == 0
        assert merged == 0
        assert skipped == 1

    def test_import_merges_existing_source(
        self, alias_repository: AliasRepository, tmp_path: Path
    ) -> None:
        """Повторный импорт того же источника учитывается как объединение."""
        import json

        alias_repository.save(Alias(source_text="TP Herbal", target_name="Товар"))

        payload = [{"source_text": "TP Herbal", "target_name": "Товар (уточнено)"}]
        path = tmp_path / "aliases.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        added, merged, skipped = alias_repository.import_from_file(path)
        assert added == 0
        assert merged == 1
        assert skipped == 0
        assert alias_repository.count() == 1

    def test_xlsx_round_trip(self, alias_repository: AliasRepository, tmp_path: Path) -> None:
        """Экспорт и импорт в формате Excel сохраняют данные без потерь."""
        alias_repository.save(
            Alias(
                source_text="TP Herbal 100ml",
                target_name="Лечебные травы 100 мл",
                brand="Balton",
                volume_ml=100.0,
            )
        )

        export_path = tmp_path / "aliases.xlsx"
        assert alias_repository.export_to_file(export_path) == 1

        alias_repository.clear()
        added, merged, skipped = alias_repository.import_from_file(export_path)
        assert (added, merged, skipped) == (1, 0, 0)
        restored = alias_repository.find_for_text("TP Herbal 100ml")
        assert restored[0].brand == "Balton"
        assert restored[0].volume_ml == 100.0


class TestConfidence:
    """Проверки вычисляемого уровня доверия и его влияния на поиск."""

    def test_manual_alias_has_full_confidence(self, alias_repository: AliasRepository) -> None:
        """Псевдоним, созданный пользователем, всегда имеет доверие 100%."""
        alias = alias_repository.save(Alias(source_text="Товар", target_name="Товар"))
        assert alias.confidence == 100.0

    def test_automatic_alias_gains_confidence_after_confirmations(
        self, alias_repository: AliasRepository
    ) -> None:
        """Неручной псевдоним поднимается с 80% до 95% после нескольких применений."""
        alias = alias_repository.save(
            Alias(source_text="Товар", target_name="Товар", is_manual=False)
        )
        assert alias.confidence == 80.0
        for _ in range(3):
            alias_repository.register_hit(alias.id)  # type: ignore[arg-type]
        refreshed = alias_repository.get_by_id(alias.id)  # type: ignore[arg-type]
        assert refreshed is not None
        assert refreshed.confidence == 95.0

    def test_search_orders_manual_before_automatic(self, alias_repository: AliasRepository) -> None:
        """При равном тексте более доверенная запись находится первой."""
        alias_repository.save(Alias(source_text="Товар", target_name="A", is_manual=False))
        alias_repository.save(Alias(source_text="Товар Х", target_name="B", is_manual=True))
        results = alias_repository.search("Товар", sort="confidence_desc")
        assert results[0].target_name == "B"


class TestCreateAndUpdate:
    """Проверки явного создания/редактирования записей словаря."""

    def test_create_sets_manual_source(self, alias_repository: AliasRepository) -> None:
        """Явное создание записи всегда помечается как ручное (100% доверия)."""
        created = alias_repository.create(
            Alias(source_text="Ручная запись", target_name="Товар", is_manual=True)
        )
        assert created.id is not None
        assert created.confidence == 100.0

    def test_create_rejects_exact_duplicate(self, alias_repository: AliasRepository) -> None:
        """Точный дубликат (тот же нормализованный источник) отклоняется."""
        alias_repository.create(Alias(source_text="Товар", target_name="Товар"))
        with pytest.raises(DuplicateAliasError):
            alias_repository.create(Alias(source_text="Товар", target_name="Другое"))

    def test_update_changes_fields_in_place(self, alias_repository: AliasRepository) -> None:
        """Редактирование меняет запись, сохраняя её идентификатор."""
        created = alias_repository.create(Alias(source_text="Товар", target_name="Товар"))
        updated = alias_repository.update(created.id, brand="Balton", note="проверено")  # type: ignore[arg-type]
        assert updated.id == created.id
        assert updated.brand == "Balton"
        assert updated.note == "проверено"

    def test_update_missing_record_raises(self, alias_repository: AliasRepository) -> None:
        """Редактирование несуществующей записи порождает понятную ошибку."""
        with pytest.raises(DuplicateAliasError):
            alias_repository.update(999, brand="X")

    def test_update_source_text_recomputes_key_from_cleaned_text(
        self, alias_repository: AliasRepository
    ) -> None:
        """Смена системного названия пересчитывает ключ поиска по очищенному тексту.

        Регрессия: при смене ``source_text`` на полное системное название
        («61004628 TP Herbal 100ml [48]») ключ поиска должен совпадать с
        тем, что дал бы ``create()`` с тем же текстом — иначе запись,
        отредактированная через диалог, переставала бы находиться при
        подборе заказа.
        """
        created = alias_repository.create(Alias(source_text="Товар", target_name="Товар"))

        updated = alias_repository.update(
            created.id,  # type: ignore[arg-type]
            source_text="61004628 TP Herbal 100ml [48]",
        )

        assert updated.normalized_source == "tp herbal 100 ml"


class TestFindSimilar:
    """Проверки поиска потенциальных дубликатов."""

    def test_finds_close_variant(self, alias_repository: AliasRepository) -> None:
        """Похожая, но не идентичная запись обнаруживается как вероятный дубликат."""
        alias_repository.create(Alias(source_text="TP Herbal 100ml", target_name="Товар"))
        similar = alias_repository.find_similar("TP Herbal 100 ml")
        assert similar
        assert similar[0].source_text == "TP Herbal 100ml"

    def test_excludes_given_id(self, alias_repository: AliasRepository) -> None:
        """Запись не считается похожей сама на себя при редактировании."""
        created = alias_repository.create(Alias(source_text="TP Herbal 100ml", target_name="Товар"))
        similar = alias_repository.find_similar("TP Herbal 100ml", exclude_id=created.id)
        assert similar == []


class TestBulkOperations:
    """Проверки массового удаления и изменения."""

    def test_bulk_delete_removes_all(self, alias_repository: AliasRepository) -> None:
        """Массовое удаление убирает все переданные записи."""
        one = alias_repository.create(Alias(source_text="Товар A", target_name="A"))
        two = alias_repository.create(Alias(source_text="Товар B", target_name="B"))
        removed = alias_repository.bulk_delete([one.id, two.id])  # type: ignore[list-item]
        assert removed == 2
        assert alias_repository.count() == 0

    def test_bulk_update_sets_brand(self, alias_repository: AliasRepository) -> None:
        """Массовое изменение бренда применяется ко всем записям."""
        one = alias_repository.create(Alias(source_text="Товар A", target_name="A"))
        two = alias_repository.create(Alias(source_text="Товар B", target_name="B"))
        changed = alias_repository.bulk_update([one.id, two.id], brand="Balton")  # type: ignore[list-item]
        assert changed == 2
        assert alias_repository.get_by_id(one.id).brand == "Balton"  # type: ignore[arg-type,union-attr]


class TestUndo:
    """Проверки журнала изменений и отмены последнего действия."""

    def test_undo_reverts_deletion(self, alias_repository: AliasRepository) -> None:
        """Отмена удаления восстанавливает запись."""
        created = alias_repository.create(Alias(source_text="Товар", target_name="Товар"))
        alias_repository.delete(created.id)  # type: ignore[arg-type]
        assert alias_repository.count() == 0

        entry = alias_repository.last_audit_entry()
        assert entry is not None
        assert entry.action.value == "deleted"
        assert alias_repository.undo(entry.id)  # type: ignore[arg-type]
        assert alias_repository.count() == 1
        assert alias_repository.find_for_text("Товар")[0].source_text == "Товар"

    def test_undo_reverts_creation(self, alias_repository: AliasRepository) -> None:
        """Отмена создания убирает только что добавленную запись."""
        created = alias_repository.create(Alias(source_text="Товар", target_name="Товар"))
        entry = alias_repository.last_audit_entry()
        assert entry is not None
        assert entry.action.value == "created"
        assert alias_repository.undo(entry.id)  # type: ignore[arg-type]
        assert alias_repository.get_by_id(created.id) is None  # type: ignore[arg-type]

    def test_undo_reverts_update(self, alias_repository: AliasRepository) -> None:
        """Отмена изменения возвращает прежние значения полей."""
        created = alias_repository.create(Alias(source_text="Товар", target_name="Товар", brand=""))
        alias_repository.update(created.id, brand="Balton")  # type: ignore[arg-type]

        entry = alias_repository.last_audit_entry()
        assert entry is not None
        assert entry.action.value == "updated"
        assert alias_repository.undo(entry.id)  # type: ignore[arg-type]
        restored = alias_repository.get_by_id(created.id)  # type: ignore[arg-type]
        assert restored is not None
        assert restored.brand == ""

    def test_undo_is_available_again_after_previous_undo(
        self, alias_repository: AliasRepository
    ) -> None:
        """Отмена нескольких действий подряд отматывает историю по одному шагу.

        Регрессия: запись журнала о самой отмене (``restored``) не должна
        сама становиться «последним действием» — иначе после первой же
        отмены кнопка «Отменить» переставала бы находить что-либо, пока не
        случится новое действие, хотя в истории есть более ранние правки.
        """
        first = alias_repository.create(Alias(source_text="Товар 1", target_name="Товар"))
        second = alias_repository.create(Alias(source_text="Товар 2", target_name="Товар"))
        assert alias_repository.count() == 2

        first_undo = alias_repository.last_audit_entry()
        assert first_undo is not None
        assert first_undo.alias_id == second.id
        assert alias_repository.undo(first_undo.id)  # type: ignore[arg-type]
        assert alias_repository.count() == 1

        second_undo = alias_repository.last_audit_entry()
        assert second_undo is not None
        assert second_undo.alias_id == first.id
        assert alias_repository.undo(second_undo.id)  # type: ignore[arg-type]
        assert alias_repository.count() == 0

    def test_already_undone_entry_cannot_be_undone_twice(
        self, alias_repository: AliasRepository
    ) -> None:
        """Повторная отмена уже отменённого действия ничего не делает."""
        alias_repository.create(Alias(source_text="Товар", target_name="Товар"))
        entry = alias_repository.last_audit_entry()
        assert entry is not None
        assert alias_repository.undo(entry.id)  # type: ignore[arg-type]
        assert alias_repository.undo(entry.id) is False  # type: ignore[arg-type]


class TestSearchFilters:
    """Проверки поиска по словарю с фильтрами."""

    def test_filters_by_brand(self, alias_repository: AliasRepository) -> None:
        """Фильтр по бренду ограничивает результаты точным совпадением."""
        alias_repository.create(Alias(source_text="Товар A", target_name="A", brand="Balton"))
        alias_repository.create(Alias(source_text="Товар B", target_name="B", brand="Other"))
        results = alias_repository.search("", brand="Balton")
        assert len(results) == 1
        assert results[0].brand == "Balton"

    def test_free_text_matches_multiple_fields(self, alias_repository: AliasRepository) -> None:
        """Поиск находит совпадение и по бренду, и по названию."""
        alias_repository.create(
            Alias(source_text="Товар", target_name="Товар", brand="Balton Trading")
        )
        assert len(alias_repository.search("balton")) == 1
        assert len(alias_repository.search("нет такого")) == 0
