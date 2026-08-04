"""Тесты репозитория псевдонимов."""

from __future__ import annotations

from pathlib import Path

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

        imported, skipped = alias_repository.import_from_file(export_path)
        assert imported == 1
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

        imported, skipped = alias_repository.import_from_file(path)
        assert imported == 0
        assert skipped == 1
