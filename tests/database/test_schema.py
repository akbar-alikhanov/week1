"""Тесты миграций схемы базы данных."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.database.schema import (
    _SCHEMA_V1,
    TARGET_VERSION,
    apply_migrations,
    current_version,
    has_fts,
)


def _seed_v1_database(path: Path) -> sqlite3.Connection:
    """Создаёт базу данных версии 1 с тестовыми данными, минуя миграции.

    Воспроизводит состояние реальной установки до обновления: несколько
    сертификатов (один — с несколькими помечающими его псевдонимами) в
    исходной схеме, где ``pdf_path`` был единственным ключом файла.

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

    def test_certificate_data_and_ids_survive_upgrade(self, tmp_path: Path) -> None:
        """Существующие записи сертификатов сохраняют id и данные после апгрейда."""
        connection = _seed_v1_database(tmp_path / "legacy.db")
        apply_migrations(connection)

        rows = {
            row["id"]: dict(row)
            for row in connection.execute("SELECT * FROM certificates ORDER BY id")
        }
        assert set(rows) == {1, 2}
        assert rows[1]["product_name"] == "Лечебные травы 100 мл"
        assert rows[1]["pdf_path"] == "/c/1.pdf"
        connection.close()

    def test_existing_rows_get_row_index_zero(self, tmp_path: Path) -> None:
        """Записи, существовавшие до появления построчных позиций, получают row_index = 0."""
        connection = _seed_v1_database(tmp_path / "legacy.db")
        apply_migrations(connection)

        values = [
            row["row_index"] for row in connection.execute("SELECT row_index FROM certificates")
        ]
        assert values == [0, 0]
        connection.close()

    def test_alias_foreign_key_survives_table_rebuild(self, tmp_path: Path) -> None:
        """Псевдоним продолжает ссылаться на тот же сертификат после пересборки таблицы."""
        connection = _seed_v1_database(tmp_path / "legacy.db")
        apply_migrations(connection)

        alias = connection.execute(
            "SELECT certificate_id FROM aliases WHERE source_text = 'Herbal Doctor Syrup'"
        ).fetchone()
        assert alias["certificate_id"] == 1
        connection.close()

    def test_composite_unique_constraint_active_after_upgrade(self, tmp_path: Path) -> None:
        """После апгрейда уникальна пара (pdf_path, row_index), а не сам путь."""
        connection = _seed_v1_database(tmp_path / "legacy.db")
        apply_migrations(connection)

        # Тот же файл, другая позиция — должно приниматься.
        connection.execute(
            "INSERT INTO certificates "
            "(product_name, pdf_path, row_index, indexed_at, updated_at) "
            "VALUES ('Вторая позиция', '/c/1.pdf', 1, '2025-01-01T00:00:00', "
            "'2025-01-01T00:00:00')"
        )
        connection.commit()

        # Тот же файл и та же позиция — обязано отклоняться.
        try:
            connection.execute(
                "INSERT INTO certificates "
                "(product_name, pdf_path, row_index, indexed_at, updated_at) "
                "VALUES ('Дубликат', '/c/1.pdf', 0, '2025-01-01T00:00:00', '2025-01-01T00:00:00')"
            )
            connection.commit()
            raised = False
        except sqlite3.IntegrityError:
            raised = True
        assert raised
        connection.close()

    def test_fts_index_present_and_searchable_after_upgrade(self, tmp_path: Path) -> None:
        """Полнотекстовый индекс воссоздан и находит перенесённые записи."""
        connection = _seed_v1_database(tmp_path / "legacy.db")
        apply_migrations(connection)

        assert has_fts(connection)
        matches = connection.execute(
            "SELECT rowid FROM certificates_fts WHERE certificates_fts MATCH ?", ("травы",)
        ).fetchall()
        assert len(matches) == 1
        connection.close()

    def test_second_call_is_a_no_op(self, tmp_path: Path) -> None:
        """Повторный вызов apply_migrations на уже актуальной базе ничего не меняет."""
        connection = _seed_v1_database(tmp_path / "legacy.db")
        apply_migrations(connection)
        count_before = connection.execute("SELECT count(*) FROM certificates").fetchone()[0]

        result_version = apply_migrations(connection)

        assert result_version == TARGET_VERSION
        count_after = connection.execute("SELECT count(*) FROM certificates").fetchone()[0]
        assert count_after == count_before
        connection.close()

    def test_fresh_database_reaches_target_version_directly(self, tmp_path: Path) -> None:
        """Новая (пустая) база инициализируется сразу в целевой версии."""
        connection = sqlite3.connect(tmp_path / "fresh.db")
        assert current_version(connection) == 0

        result_version = apply_migrations(connection)

        assert result_version == TARGET_VERSION
        columns = {row[1] for row in connection.execute("PRAGMA table_info(certificates)")}
        assert "row_index" in columns
        connection.close()
