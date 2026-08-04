"""Тесты репозитория сертификатов."""

from __future__ import annotations

import datetime as dt

from app.repositories.certificate_repository import CertificateRepository
from tests.conftest import make_certificate


class TestUpsert:
    """Проверки добавления и обновления сертификатов."""

    def test_add_assigns_id(self, certificate_repository: CertificateRepository) -> None:
        """После сохранения сертификат получает идентификатор."""
        certificate = make_certificate("Товар", "/c/1.pdf")
        certificate_id = certificate_repository.add(certificate)
        assert certificate_id > 0
        assert certificate.id == certificate_id

    def test_upsert_many_inserts_new(self, certificate_repository: CertificateRepository) -> None:
        """Первый вызов upsert_many добавляет все записи как новые."""
        certificates = [make_certificate(f"Товар {i}", f"/c/{i}.pdf") for i in range(3)]
        added, updated = certificate_repository.upsert_many(certificates)
        assert added == 3
        assert updated == 0

    def test_upsert_many_updates_existing_by_path(
        self, certificate_repository: CertificateRepository
    ) -> None:
        """Повторный upsert по тому же пути обновляет запись, не дублируя её."""
        first = make_certificate("Товар", "/c/1.pdf")
        certificate_repository.upsert_many([first])

        changed = make_certificate("Товар (обновлён)", "/c/1.pdf")
        added, updated = certificate_repository.upsert_many([changed])

        assert added == 0
        assert updated == 1
        assert certificate_repository.count() == 1

    def test_update_existing_record(self, certificate_repository: CertificateRepository) -> None:
        """Прямое обновление сертификата изменяет его поля."""
        certificate = make_certificate("Старое имя", "/c/1.pdf")
        certificate_repository.add(certificate)

        certificate.product_name = "Новое имя"
        assert certificate_repository.update(certificate)

        fetched = certificate_repository.get_by_id(certificate.id)  # type: ignore[arg-type]
        assert fetched is not None
        assert fetched.product_name == "Новое имя"


class TestQueries:
    """Проверки чтения справочника."""

    def test_get_by_path(self, certificate_repository: CertificateRepository) -> None:
        """Сертификат находится по точному пути к файлу."""
        certificate_repository.add(make_certificate("Товар", "/c/1.pdf"))
        found = certificate_repository.get_by_path("/c/1.pdf")
        assert found is not None
        assert found.product_name == "Товар"

    def test_get_by_path_missing(self, certificate_repository: CertificateRepository) -> None:
        """Несуществующий путь даёт None."""
        assert certificate_repository.get_by_path("/c/missing.pdf") is None

    def test_list_active_excludes_inactive(
        self, certificate_repository: CertificateRepository
    ) -> None:
        """Список активных сертификатов не включает деактивированные записи."""
        certificate_repository.add(make_certificate("Активный", "/c/1.pdf"))
        certificate_repository.deactivate_missing([])  # деактивирует всё, включая /c/1.pdf
        assert certificate_repository.list_active() == []

    def test_list_active_excludes_expired_when_requested(
        self, certificate_repository: CertificateRepository
    ) -> None:
        """Просроченные сертификаты исключаются по флагу include_expired."""
        certificate_repository.add(
            make_certificate("Просрочен", "/c/1.pdf", expiry_date=dt.date(2000, 1, 1))
        )
        certificate_repository.add(
            make_certificate("Действителен", "/c/2.pdf", expiry_date=dt.date(2099, 1, 1))
        )
        results = certificate_repository.list_active(include_expired=False)
        assert len(results) == 1
        assert results[0].product_name == "Действителен"

    def test_search_finds_by_normalized_name(
        self, certificate_repository: CertificateRepository
    ) -> None:
        """Поиск находит запись по частичному нормализованному имени."""
        certificate_repository.add(make_certificate("Лечебные травы 100 мл", "/c/1.pdf"))
        results = certificate_repository.search("травы")
        assert len(results) == 1

    def test_search_finds_by_certificate_number(
        self, certificate_repository: CertificateRepository
    ) -> None:
        """Поиск находит запись по номеру сертификата."""
        certificate_repository.add(
            make_certificate("Товар", "/c/1.pdf", certificate_number="UZ.AMT.01.183255")
        )
        results = certificate_repository.search("183255")
        assert len(results) == 1

    def test_search_empty_query_returns_all_active(
        self, certificate_repository: CertificateRepository
    ) -> None:
        """Пустой запрос возвращает все активные записи."""
        certificate_repository.add(make_certificate("Товар 1", "/c/1.pdf"))
        certificate_repository.add(make_certificate("Товар 2", "/c/2.pdf"))
        assert len(certificate_repository.search("")) == 2


class TestFingerprints:
    """Проверки инкрементальной индексации по отпечаткам файлов."""

    def test_fingerprints_reflect_stored_hash(
        self, certificate_repository: CertificateRepository
    ) -> None:
        """Отпечатки содержат сохранённый хэш файла."""
        certificate = make_certificate("Товар", "/c/1.pdf")
        certificate.file_hash = "abc123"
        certificate.file_size = 1024
        certificate_repository.add(certificate)

        fingerprints = certificate_repository.fingerprints()
        assert fingerprints["/c/1.pdf"].file_hash == "abc123"
        assert fingerprints["/c/1.pdf"].file_size == 1024

    def test_deactivate_missing(self, certificate_repository: CertificateRepository) -> None:
        """Файлы, отсутствующие среди найденных, помечаются неактивными."""
        certificate_repository.add(make_certificate("Есть", "/c/present.pdf"))
        certificate_repository.add(make_certificate("Нет", "/c/absent.pdf"))

        removed = certificate_repository.deactivate_missing(["/c/present.pdf"])
        assert removed == 1
        assert certificate_repository.count("is_active = 1") == 1


class TestStatistics:
    """Проверки сводной статистики справочника."""

    def test_statistics_counts_expired(self, certificate_repository: CertificateRepository) -> None:
        """Статистика корректно подсчитывает просроченные записи."""
        certificate_repository.add(
            make_certificate("Просрочен", "/c/1.pdf", expiry_date=dt.date(2000, 1, 1))
        )
        stats = certificate_repository.statistics()
        assert stats["expired"] == 1
        assert stats["total"] == 1
