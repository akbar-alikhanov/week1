"""Тесты репозитория псевдонимов."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.exceptions import DuplicateAliasError
from app.models.alias import Alias
from app.models.certificate import Certificate
from app.repositories.alias_repository import AliasRepository
from app.repositories.certificate_repository import CertificateRepository
from tests.conftest import make_certificate


def _certificate(repository: CertificateRepository, name: str, path: str) -> Certificate:
    """Создаёт и сохраняет сертификат для использования как цель псевдонима.

    Таблица ``aliases`` ссылается на ``certificates`` внешним ключом, поэтому
    псевдоним не может существовать без реального сертификата — так же, как и
    в продакшене, где псевдоним без цели бессмысленен.
    """
    certificate = make_certificate(name, path)
    repository.add(certificate)
    return certificate


class TestSave:
    """Проверки сохранения псевдонимов."""

    def test_save_assigns_id(
        self, alias_repository: AliasRepository, certificate_repository: CertificateRepository
    ) -> None:
        """Новый псевдоним получает идентификатор при сохранении."""
        certificate = _certificate(certificate_repository, "Товар", "/c/1.pdf")
        alias = Alias(
            source_text="TP Herbal 100ml", certificate_id=certificate.id, target_name="Товар"
        )
        saved = alias_repository.save(alias)
        assert saved.id is not None

    def test_save_is_idempotent_for_same_pair(
        self, alias_repository: AliasRepository, certificate_repository: CertificateRepository
    ) -> None:
        """Повторное сохранение того же соответствия обновляет запись, не дублируя."""
        certificate = _certificate(certificate_repository, "A", "/c/1.pdf")
        alias_repository.save(
            Alias(source_text="TP Herbal", certificate_id=certificate.id, target_name="A")
        )
        alias_repository.save(
            Alias(source_text="TP Herbal", certificate_id=certificate.id, target_name="A")
        )
        assert alias_repository.count() == 1

    def test_save_different_target_creates_new_record(
        self, alias_repository: AliasRepository, certificate_repository: CertificateRepository
    ) -> None:
        """Тот же источник с другой целью создаёт отдельную запись."""
        first = _certificate(certificate_repository, "Товар A", "/c/1.pdf")
        second = _certificate(certificate_repository, "Товар B", "/c/2.pdf")
        alias_repository.save(Alias(source_text="Товар", certificate_id=first.id))
        alias_repository.save(Alias(source_text="Товар", certificate_id=second.id))
        assert alias_repository.count() == 2


class TestFindForText:
    """Проверки поиска псевдонима по тексту заказа."""

    def test_exact_normalized_match(
        self, alias_repository: AliasRepository, certificate_repository: CertificateRepository
    ) -> None:
        """Точное совпадение нормализованного текста находит псевдоним."""
        certificate = _certificate(certificate_repository, "Товар", "/c/1.pdf")
        alias_repository.save(
            Alias(source_text="TP Herbal 100ml", certificate_id=certificate.id, target_name="Товар")
        )
        found = alias_repository.find_for_text("tp  herbal 100 ml")
        assert len(found) == 1

    def test_token_order_independent_match(
        self, alias_repository: AliasRepository, certificate_repository: CertificateRepository
    ) -> None:
        """Соответствие находится даже при перестановке слов."""
        certificate = _certificate(certificate_repository, "Товар", "/c/1.pdf")
        alias_repository.save(
            Alias(
                source_text="Лечебные травы 100 мл",
                certificate_id=certificate.id,
                target_name="Товар",
            )
        )
        found = alias_repository.find_for_text("100мл травы лечебные")
        assert len(found) == 1

    def test_no_match_for_unrelated_text(
        self, alias_repository: AliasRepository, certificate_repository: CertificateRepository
    ) -> None:
        """Несвязанный текст не находит псевдонимов."""
        certificate = _certificate(certificate_repository, "Товар А", "/c/1.pdf")
        alias_repository.save(Alias(source_text="Товар А", certificate_id=certificate.id))
        assert alias_repository.find_for_text("Совершенно другой товар") == []

    def test_priority_by_weight(
        self, alias_repository: AliasRepository, certificate_repository: CertificateRepository
    ) -> None:
        """При нескольких совпадениях приоритет отдаётся псевдониму с большим весом."""
        first = _certificate(certificate_repository, "Товар A", "/c/1.pdf")
        second = _certificate(certificate_repository, "Товар B", "/c/2.pdf")
        alias_repository.save(Alias(source_text="Товар", certificate_id=first.id, weight=1.0))
        alias_repository.save(Alias(source_text="Товар", certificate_id=second.id, weight=5.0))
        found = alias_repository.find_for_text("Товар")
        assert found[0].certificate_id == second.id


class TestRegisterHit:
    """Проверки учёта применений псевдонима."""

    def test_hit_count_increments(
        self, alias_repository: AliasRepository, certificate_repository: CertificateRepository
    ) -> None:
        """Счётчик применений увеличивается при регистрации."""
        certificate = _certificate(certificate_repository, "Товар", "/c/1.pdf")
        alias = alias_repository.save(Alias(source_text="Товар", certificate_id=certificate.id))
        alias_repository.register_hit(alias.id)  # type: ignore[arg-type]
        alias_repository.register_hit(alias.id)  # type: ignore[arg-type]
        updated = alias_repository.find_for_text("Товар")[0]
        assert updated.hit_count == 2


class TestImportExport:
    """Проверки импорта и экспорта псевдонимов."""

    def test_export_and_import_json(
        self,
        alias_repository: AliasRepository,
        certificate_repository: CertificateRepository,
        tmp_path: Path,
    ) -> None:
        """Экспортированные псевдонимы корректно восстанавливаются при импорте."""
        certificate = make_certificate("Лечебные травы 100 мл", "/c/1.pdf")
        certificate.pdf_name = "183255.pdf"
        certificate_repository.add(certificate)
        alias_repository.save(
            Alias(
                source_text="TP Herbal 100ml",
                certificate_id=certificate.id,
                target_name=certificate.product_name,
                target_pdf_name=certificate.pdf_name,
            )
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

    def test_import_skips_unknown_certificate(
        self, alias_repository: AliasRepository, tmp_path: Path
    ) -> None:
        """Импорт пропускает записи, ссылающиеся на несуществующий PDF."""
        import json

        payload = [
            {
                "source_text": "TP Herbal 100ml",
                "target_name": "Товар",
                "target_pdf_name": "missing.pdf",
            }
        ]
        path = tmp_path / "aliases.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        added, merged, skipped = alias_repository.import_from_file(path)
        assert added == 0
        assert merged == 0
        assert skipped == 1

    def test_import_merges_existing_pair(
        self,
        alias_repository: AliasRepository,
        certificate_repository: CertificateRepository,
        tmp_path: Path,
    ) -> None:
        """Повторный импорт того же соответствия учитывается как объединение."""
        import json

        certificate = make_certificate("Товар", "/c/1.pdf")
        certificate.pdf_name = "1.pdf"
        certificate_repository.add(certificate)
        alias_repository.save(
            Alias(source_text="TP Herbal", certificate_id=certificate.id, target_pdf_name="1.pdf")
        )

        payload = [{"source_text": "TP Herbal", "target_pdf_name": "1.pdf"}]
        path = tmp_path / "aliases.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        added, merged, skipped = alias_repository.import_from_file(path)
        assert added == 0
        assert merged == 1
        assert skipped == 0
        assert alias_repository.count() == 1

    def test_xlsx_round_trip(
        self,
        alias_repository: AliasRepository,
        certificate_repository: CertificateRepository,
        tmp_path: Path,
    ) -> None:
        """Экспорт и импорт в формате Excel сохраняют данные без потерь."""
        certificate = make_certificate("Лечебные травы 100 мл", "/c/1.pdf")
        certificate.pdf_name = "183255.pdf"
        certificate_repository.add(certificate)
        alias_repository.save(
            Alias(
                source_text="TP Herbal 100ml",
                certificate_id=certificate.id,
                target_name=certificate.product_name,
                target_pdf_name=certificate.pdf_name,
                brand="Balton",
            )
        )

        export_path = tmp_path / "aliases.xlsx"
        assert alias_repository.export_to_file(export_path) == 1

        alias_repository.clear()
        added, merged, skipped = alias_repository.import_from_file(export_path)
        assert (added, merged, skipped) == (1, 0, 0)
        restored = alias_repository.find_for_text("TP Herbal 100ml")
        assert restored[0].brand == "Balton"


class TestConfidence:
    """Проверки вычисляемого уровня доверия и его влияния на поиск."""

    def test_manual_alias_has_full_confidence(
        self, alias_repository: AliasRepository, certificate_repository: CertificateRepository
    ) -> None:
        """Псевдоним, созданный пользователем, всегда имеет доверие 100%."""
        certificate = _certificate(certificate_repository, "Товар", "/c/1.pdf")
        alias = alias_repository.save(Alias(source_text="Товар", certificate_id=certificate.id))
        assert alias.confidence == 100.0

    def test_automatic_alias_gains_confidence_after_confirmations(
        self, alias_repository: AliasRepository, certificate_repository: CertificateRepository
    ) -> None:
        """Неручной псевдоним поднимается с 80% до 95% после нескольких применений."""
        certificate = _certificate(certificate_repository, "Товар", "/c/1.pdf")
        alias = alias_repository.save(
            Alias(source_text="Товар", certificate_id=certificate.id, is_manual=False)
        )
        assert alias.confidence == 80.0
        for _ in range(3):
            alias_repository.register_hit(alias.id)  # type: ignore[arg-type]
        refreshed = alias_repository.get_by_id(alias.id)  # type: ignore[arg-type]
        assert refreshed is not None
        assert refreshed.confidence == 95.0

    def test_search_orders_manual_before_automatic(
        self, alias_repository: AliasRepository, certificate_repository: CertificateRepository
    ) -> None:
        """При равном тексте более доверенная запись находится первой."""
        first = _certificate(certificate_repository, "Товар A", "/c/1.pdf")
        second = _certificate(certificate_repository, "Товар B", "/c/2.pdf")
        alias_repository.save(Alias(source_text="Товар", certificate_id=first.id, is_manual=False))
        alias_repository.save(
            Alias(source_text="Товар Х", certificate_id=second.id, is_manual=True)
        )
        results = alias_repository.search("Товар", sort="confidence_desc")
        assert results[0].certificate_id == second.id


class TestCreateAndUpdate:
    """Проверки явного создания/редактирования записей словаря."""

    def test_create_sets_manual_source(
        self, alias_repository: AliasRepository, certificate_repository: CertificateRepository
    ) -> None:
        """Явное создание записи всегда помечается как ручное (100% доверия)."""
        certificate = _certificate(certificate_repository, "Товар", "/c/1.pdf")
        created = alias_repository.create(
            Alias(source_text="Ручная запись", certificate_id=certificate.id, is_manual=True)
        )
        assert created.id is not None
        assert created.confidence == 100.0

    def test_create_rejects_exact_duplicate(
        self, alias_repository: AliasRepository, certificate_repository: CertificateRepository
    ) -> None:
        """Точный дубликат (тот же источник и сертификат) отклоняется."""
        certificate = _certificate(certificate_repository, "Товар", "/c/1.pdf")
        alias_repository.create(Alias(source_text="Товар", certificate_id=certificate.id))
        with pytest.raises(DuplicateAliasError):
            alias_repository.create(Alias(source_text="Товар", certificate_id=certificate.id))

    def test_update_changes_fields_in_place(
        self, alias_repository: AliasRepository, certificate_repository: CertificateRepository
    ) -> None:
        """Редактирование меняет запись, сохраняя её идентификатор."""
        certificate = _certificate(certificate_repository, "Товар", "/c/1.pdf")
        created = alias_repository.create(Alias(source_text="Товар", certificate_id=certificate.id))
        updated = alias_repository.update(created.id, brand="Balton", note="проверено")  # type: ignore[arg-type]
        assert updated.id == created.id
        assert updated.brand == "Balton"
        assert updated.note == "проверено"

    def test_update_missing_record_raises(self, alias_repository: AliasRepository) -> None:
        """Редактирование несуществующей записи порождает понятную ошибку."""
        with pytest.raises(DuplicateAliasError):
            alias_repository.update(999, brand="X")


class TestFindSimilar:
    """Проверки поиска потенциальных дубликатов."""

    def test_finds_close_variant(
        self, alias_repository: AliasRepository, certificate_repository: CertificateRepository
    ) -> None:
        """Похожая, но не идентичная запись обнаруживается как вероятный дубликат."""
        certificate = _certificate(certificate_repository, "Товар", "/c/1.pdf")
        alias_repository.create(Alias(source_text="TP Herbal 100ml", certificate_id=certificate.id))
        similar = alias_repository.find_similar("TP Herbal 100 ml")
        assert similar
        assert similar[0].source_text == "TP Herbal 100ml"

    def test_excludes_given_id(
        self, alias_repository: AliasRepository, certificate_repository: CertificateRepository
    ) -> None:
        """Запись не считается похожей сама на себя при редактировании."""
        certificate = _certificate(certificate_repository, "Товар", "/c/1.pdf")
        created = alias_repository.create(
            Alias(source_text="TP Herbal 100ml", certificate_id=certificate.id)
        )
        similar = alias_repository.find_similar("TP Herbal 100ml", exclude_id=created.id)
        assert similar == []


class TestBulkOperations:
    """Проверки массового удаления и изменения."""

    def test_bulk_delete_removes_all(
        self, alias_repository: AliasRepository, certificate_repository: CertificateRepository
    ) -> None:
        """Массовое удаление убирает все переданные записи."""
        first = _certificate(certificate_repository, "Товар A", "/c/1.pdf")
        second = _certificate(certificate_repository, "Товар B", "/c/2.pdf")
        one = alias_repository.create(Alias(source_text="Товар A", certificate_id=first.id))
        two = alias_repository.create(Alias(source_text="Товар B", certificate_id=second.id))
        removed = alias_repository.bulk_delete([one.id, two.id])  # type: ignore[list-item]
        assert removed == 2
        assert alias_repository.count() == 0

    def test_bulk_update_sets_brand(
        self, alias_repository: AliasRepository, certificate_repository: CertificateRepository
    ) -> None:
        """Массовое изменение бренда применяется ко всем записям."""
        first = _certificate(certificate_repository, "Товар A", "/c/1.pdf")
        second = _certificate(certificate_repository, "Товар B", "/c/2.pdf")
        one = alias_repository.create(Alias(source_text="Товар A", certificate_id=first.id))
        two = alias_repository.create(Alias(source_text="Товар B", certificate_id=second.id))
        changed = alias_repository.bulk_update([one.id, two.id], brand="Balton")  # type: ignore[list-item]
        assert changed == 2
        assert alias_repository.get_by_id(one.id).brand == "Balton"  # type: ignore[arg-type,union-attr]


class TestUndo:
    """Проверки журнала изменений и отмены последнего действия."""

    def test_undo_reverts_deletion(
        self, alias_repository: AliasRepository, certificate_repository: CertificateRepository
    ) -> None:
        """Отмена удаления восстанавливает запись."""
        certificate = _certificate(certificate_repository, "Товар", "/c/1.pdf")
        created = alias_repository.create(Alias(source_text="Товар", certificate_id=certificate.id))
        alias_repository.delete(created.id)  # type: ignore[arg-type]
        assert alias_repository.count() == 0

        entry = alias_repository.last_audit_entry()
        assert entry is not None
        assert entry.action.value == "deleted"
        assert alias_repository.undo(entry.id)  # type: ignore[arg-type]
        assert alias_repository.count() == 1
        assert alias_repository.find_for_text("Товар")[0].source_text == "Товар"

    def test_undo_reverts_creation(
        self, alias_repository: AliasRepository, certificate_repository: CertificateRepository
    ) -> None:
        """Отмена создания убирает только что добавленную запись."""
        certificate = _certificate(certificate_repository, "Товар", "/c/1.pdf")
        created = alias_repository.create(Alias(source_text="Товар", certificate_id=certificate.id))
        entry = alias_repository.last_audit_entry()
        assert entry is not None
        assert entry.action.value == "created"
        assert alias_repository.undo(entry.id)  # type: ignore[arg-type]
        assert alias_repository.get_by_id(created.id) is None  # type: ignore[arg-type]

    def test_undo_reverts_update(
        self, alias_repository: AliasRepository, certificate_repository: CertificateRepository
    ) -> None:
        """Отмена изменения возвращает прежние значения полей."""
        certificate = _certificate(certificate_repository, "Товар", "/c/1.pdf")
        created = alias_repository.create(
            Alias(source_text="Товар", certificate_id=certificate.id, brand="")
        )
        alias_repository.update(created.id, brand="Balton")  # type: ignore[arg-type]

        entry = alias_repository.last_audit_entry()
        assert entry is not None
        assert entry.action.value == "updated"
        assert alias_repository.undo(entry.id)  # type: ignore[arg-type]
        restored = alias_repository.get_by_id(created.id)  # type: ignore[arg-type]
        assert restored is not None
        assert restored.brand == ""

    def test_undo_is_available_again_after_previous_undo(
        self, alias_repository: AliasRepository, certificate_repository: CertificateRepository
    ) -> None:
        """Отмена нескольких действий подряд отматывает историю по одному шагу.

        Регрессия: запись журнала о самой отмене (``restored``) не должна
        сама становиться «последним действием» — иначе после первой же
        отмены кнопка «Отменить» переставала бы находить что-либо, пока не
        случится новое действие, хотя в истории есть более ранние правки.
        """
        certificate = _certificate(certificate_repository, "Товар", "/c/1.pdf")
        first = alias_repository.create(Alias(source_text="Товар 1", certificate_id=certificate.id))
        second = alias_repository.create(
            Alias(source_text="Товар 2", certificate_id=certificate.id)
        )
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
        self, alias_repository: AliasRepository, certificate_repository: CertificateRepository
    ) -> None:
        """Повторная отмена уже отменённого действия ничего не делает."""
        certificate = _certificate(certificate_repository, "Товар", "/c/1.pdf")
        alias_repository.create(Alias(source_text="Товар", certificate_id=certificate.id))
        entry = alias_repository.last_audit_entry()
        assert entry is not None
        assert alias_repository.undo(entry.id)  # type: ignore[arg-type]
        assert alias_repository.undo(entry.id) is False  # type: ignore[arg-type]


class TestSearchFilters:
    """Проверки поиска по словарю с фильтрами."""

    def test_filters_by_brand(
        self, alias_repository: AliasRepository, certificate_repository: CertificateRepository
    ) -> None:
        """Фильтр по бренду ограничивает результаты точным совпадением."""
        first = _certificate(certificate_repository, "Товар A", "/c/1.pdf")
        second = _certificate(certificate_repository, "Товар B", "/c/2.pdf")
        alias_repository.create(
            Alias(source_text="Товар A", certificate_id=first.id, brand="Balton")
        )
        alias_repository.create(
            Alias(source_text="Товар B", certificate_id=second.id, brand="Other")
        )
        results = alias_repository.search("", brand="Balton")
        assert len(results) == 1
        assert results[0].brand == "Balton"

    def test_free_text_matches_multiple_fields(
        self, alias_repository: AliasRepository, certificate_repository: CertificateRepository
    ) -> None:
        """Поиск находит совпадение и по бренду, и по названию."""
        certificate = _certificate(certificate_repository, "Товар", "/c/1.pdf")
        alias_repository.create(
            Alias(source_text="Товар", certificate_id=certificate.id, brand="Balton Trading")
        )
        assert len(alias_repository.search("balton")) == 1
        assert len(alias_repository.search("нет такого")) == 0
