"""Тесты миграций схемы базы данных."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.database.schema import _SCHEMA_V1, TARGET_VERSION, apply_migrations, current_version


def _seed_v1_database(path: Path) -> sqlite3.Connection:
    """Создаёт базу данных версии 1 с тестовыми данными, минуя миграции.

    Воспроизводит состояние реальной установки до перехода на Excel как
    источник данных: сертификаты из PDF (``certificates``) и псевдоним,
    ссылающийся на один из них через ``certificate_id`` — именно эта связь
    рвётся при миграции до версии 4, поскольку у Excel-базы нет общих
    идентификаторов со старым PDF-справочником.

    Args:
        path: Путь к файлу базы данных.

    Returns:
        Открытое соединение с уже заполненной схемой версии 1.
    """
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(_SCHEMA_V1)
    connection.execute(
        "INSERT INTO certificates (id, product_name, pdf_path, indexed_at, updated_at) "
        "VALUES (1, 'Лечебные травы 100 мл', '/c/1.pdf', '2025-01-01T00:00:00', "
        "'2025-01-01T00:00:00')"
    )
    connection.execute(
        "INSERT INTO certificates (id, product_name, pdf_path, indexed_at, updated_at) "
        "VALUES (2, 'Витамин C', '/c/2.pdf', '2025-01-01T00:00:00', '2025-01-01T00:00:00')"
    )
    connection.execute(
        "INSERT INTO aliases "
        "(source_text, normalized_source, certificate_id, created_at, updated_at) "
        "VALUES ('Herbal Doctor Syrup', 'herbal doctor syrup', 1, "
        "'2025-01-01T00:00:00', '2025-01-01T00:00:00')"
    )
    connection.execute("PRAGMA user_version = 1")
    connection.commit()
    return connection


class TestMigrationToTargetVersion:
    """Проверки полной цепочки миграций от версии 1 до текущей."""

    def test_upgrades_to_target_version(self, tmp_path: Path) -> None:
        """apply_migrations доводит старую базу до целевой версии схемы."""
        connection = _seed_v1_database(tmp_path / "legacy.db")
        assert current_version(connection) == 1

        result_version = apply_migrations(connection)

        assert result_version == TARGET_VERSION
        assert current_version(connection) == TARGET_VERSION
        connection.close()

    def test_old_certificates_table_is_removed(self, tmp_path: Path) -> None:
        """Таблица PDF-справочника и её полнотекстовый индекс удаляются."""
        connection = _seed_v1_database(tmp_path / "legacy.db")
        apply_migrations(connection)

        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            )
        }
        assert "certificates" not in tables
        assert "certificates_fts" not in tables
        connection.close()

    def test_certificate_products_table_created_empty(self, tmp_path: Path) -> None:
        """Новая таблица Excel-базы создаётся с ожидаемыми колонками, но пустой.

        Строки старого PDF-справочника не переносятся: у Excel-базы нет
        отображения на прежние идентификаторы, а данные впредь поступают
        только из импорта Excel-файла пользователя.
        """
        connection = _seed_v1_database(tmp_path / "legacy.db")
        apply_migrations(connection)

        columns = {row[1] for row in connection.execute("PRAGMA table_info(certificate_products)")}
        assert columns == {
            "id",
            "product_name",
            "normalized_name",
            "volume_ml",
            "expiry_date",
            "certificate_number",
            "source_row",
        }
        count = connection.execute("SELECT count(*) FROM certificate_products").fetchone()[0]
        assert count == 0
        connection.close()

    def test_alias_survives_rebuild_without_certificate_id(self, tmp_path: Path) -> None:
        """Псевдоним переживает пересборку таблицы, но теряет certificate_id."""
        connection = _seed_v1_database(tmp_path / "legacy.db")
        apply_migrations(connection)

        columns = {row[1] for row in connection.execute("PRAGMA table_info(aliases)")}
        assert "certificate_id" not in columns
        assert "target_pdf_name" not in columns
        assert "volume_ml" in columns

        alias = connection.execute(
            "SELECT source_text FROM aliases WHERE source_text = 'Herbal Doctor Syrup'"
        ).fetchone()
        assert alias is not None
        connection.close()

    def test_aliases_unique_constraint_is_source_text_only(self, tmp_path: Path) -> None:
        """После апгрейда уникален только normalized_source, без пары с сертификатом."""
        connection = _seed_v1_database(tmp_path / "legacy.db")
        apply_migrations(connection)

        try:
            connection.execute(
                "INSERT INTO aliases (source_text, normalized_source, created_at, updated_at) "
                "VALUES ('Herbal Doctor Syrup', 'herbal doctor syrup', "
                "'2025-01-01T00:00:00', '2025-01-01T00:00:00')"
            )
            connection.commit()
            raised = False
        except sqlite3.IntegrityError:
            raised = True
        assert raised
        connection.close()

    def test_embeddings_cache_cleared_on_upgrade(self, tmp_path: Path) -> None:
        """Кэш векторов очищается — старые идентификаторы сертификатов не имеют смысла."""
        connection = _seed_v1_database(tmp_path / "legacy.db")
        apply_migrations(connection)

        count = connection.execute("SELECT count(*) FROM embeddings").fetchone()[0]
        assert count == 0
        connection.close()

    def test_second_call_is_a_no_op(self, tmp_path: Path) -> None:
        """Повторный вызов apply_migrations на уже актуальной базе ничего не меняет."""
        connection = _seed_v1_database(tmp_path / "legacy.db")
        apply_migrations(connection)
        count_before = connection.execute("SELECT count(*) FROM certificate_products").fetchone()[0]

        result_version = apply_migrations(connection)

        assert result_version == TARGET_VERSION
        count_after = connection.execute("SELECT count(*) FROM certificate_products").fetchone()[0]
        assert count_after == count_before
        connection.close()

    def test_fresh_database_reaches_target_version_directly(self, tmp_path: Path) -> None:
        """Новая (пустая) база инициализируется сразу в целевой версии."""
        connection = sqlite3.connect(tmp_path / "fresh.db")
        assert current_version(connection) == 0

        result_version = apply_migrations(connection)

        assert result_version == TARGET_VERSION
        columns = {row[1] for row in connection.execute("PRAGMA table_info(certificate_products)")}
        assert "normalized_name" in columns
        assert "volume_ml" in columns
        connection.close()

    def test_aliases_gain_certificate_product_id_hint(self, tmp_path: Path) -> None:
        """После миграции у словаря появляется необязательная подсказка-ссылка.

        Существующие записи (перенесённые ещё из версии 1) получают
        ``NULL`` — подсказки без выбора пользователя в новом диалоге быть
        не может, это не то же самое, что прежний обязательный
        ``certificate_id``.
        """
        connection = _seed_v1_database(tmp_path / "legacy.db")
        apply_migrations(connection)

        columns = {row[1] for row in connection.execute("PRAGMA table_info(aliases)")}
        assert "certificate_product_id" in columns

        value = connection.execute(
            "SELECT certificate_product_id FROM aliases WHERE source_text = 'Herbal Doctor Syrup'"
        ).fetchone()[0]
        assert value is None
        connection.close()

    def test_certificate_product_id_hint_is_cleared_on_reimport(self, tmp_path: Path) -> None:
        """Подсказка ссылается на текущую базу и обнуляется при её замене.

        Полный переимпорт Excel (``DELETE`` + ``INSERT`` в
        ``certificate_products``) — обычный сценарий, а не редкий случай, и
        подсказка не должна пережить его как битая ссылка на чужую строку.
        """
        connection = sqlite3.connect(tmp_path / "fresh.db")
        connection.execute("PRAGMA foreign_keys = ON")
        apply_migrations(connection)

        connection.execute(
            "INSERT INTO certificate_products (id, product_name) VALUES (1, 'Товар')"
        )
        connection.execute(
            "INSERT INTO aliases "
            "(source_text, normalized_source, target_name, certificate_product_id, "
            "created_at, updated_at) "
            "VALUES ('Псевдоним', 'псевдоним', 'Товар', 1, "
            "'2025-01-01T00:00:00', '2025-01-01T00:00:00')"
        )
        connection.commit()

        connection.execute("DELETE FROM certificate_products")
        connection.commit()

        value = connection.execute(
            "SELECT certificate_product_id FROM aliases WHERE source_text = 'Псевдоним'"
        ).fetchone()[0]
        assert value is None
        connection.close()
