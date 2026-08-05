"""Определение схемы базы данных и миграции.

Схема версионируется через ``PRAGMA user_version``. Каждая миграция — чистая
функция, принимающая соединение; движок применяет их последовательно в одной
транзакции. Такой подход даёт предсказуемое обновление базы при выходе новых
версий приложения без потери накопленных псевдонимов и истории.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from typing import Final

from app.core.exceptions import MigrationError

_LOGGER = logging.getLogger(__name__)

#: Полный DDL начальной схемы (версия 1).
_SCHEMA_V1: Final[str] = """
-- Справочник сертификатов, извлечённых из PDF -------------------------------
CREATE TABLE IF NOT EXISTS certificates (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name           TEXT    NOT NULL,
    normalized_name        TEXT    NOT NULL DEFAULT '',
    translit_name          TEXT    NOT NULL DEFAULT '',
    name_signature         TEXT    NOT NULL DEFAULT '',
    token_signature        TEXT    NOT NULL DEFAULT '',
    brand                  TEXT    NOT NULL DEFAULT '',
    manufacturer           TEXT    NOT NULL DEFAULT '',
    applicant              TEXT    NOT NULL DEFAULT '',
    country                TEXT    NOT NULL DEFAULT '',
    certificate_number     TEXT    NOT NULL DEFAULT '',
    certificate_date       TEXT,
    valid_from             TEXT,
    expiry_date            TEXT,
    issued_by              TEXT    NOT NULL DEFAULT '',
    volume_value           REAL,
    volume_unit            TEXT    NOT NULL DEFAULT '',
    volume_raw             TEXT    NOT NULL DEFAULT '',
    pack_count             INTEGER NOT NULL DEFAULT 1,
    pdf_name               TEXT    NOT NULL DEFAULT '',
    pdf_path               TEXT    NOT NULL UNIQUE,
    page_count             INTEGER NOT NULL DEFAULT 0,
    file_hash              TEXT    NOT NULL DEFAULT '',
    file_size              INTEGER NOT NULL DEFAULT 0,
    file_mtime             REAL    NOT NULL DEFAULT 0,
    indexed_at             TEXT    NOT NULL,
    updated_at             TEXT    NOT NULL,
    raw_text               TEXT    NOT NULL DEFAULT '',
    extraction_confidence  REAL    NOT NULL DEFAULT 0,
    is_active              INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_certificates_normalized ON certificates (normalized_name);
CREATE INDEX IF NOT EXISTS idx_certificates_signature  ON certificates (name_signature);
CREATE INDEX IF NOT EXISTS idx_certificates_hash       ON certificates (file_hash);
CREATE INDEX IF NOT EXISTS idx_certificates_expiry     ON certificates (expiry_date);
CREATE INDEX IF NOT EXISTS idx_certificates_active     ON certificates (is_active);
CREATE INDEX IF NOT EXISTS idx_certificates_number     ON certificates (certificate_number);

-- Справочник товаров, встречавшихся в заказах --------------------------------
CREATE TABLE IF NOT EXISTS products (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT    NOT NULL,
    normalized_name     TEXT    NOT NULL UNIQUE,
    translit_name       TEXT    NOT NULL DEFAULT '',
    name_signature      TEXT    NOT NULL DEFAULT '',
    brand               TEXT    NOT NULL DEFAULT '',
    volume_value        REAL,
    volume_unit         TEXT    NOT NULL DEFAULT '',
    last_certificate_id INTEGER REFERENCES certificates (id) ON DELETE SET NULL,
    seen_count          INTEGER NOT NULL DEFAULT 0,
    matched_count       INTEGER NOT NULL DEFAULT 0,
    first_seen_at       TEXT    NOT NULL,
    last_seen_at        TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_products_signature ON products (name_signature);

-- Псевдонимы: механизм самообучения ------------------------------------------
CREATE TABLE IF NOT EXISTS aliases (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    source_text       TEXT    NOT NULL,
    normalized_source TEXT    NOT NULL,
    token_source      TEXT    NOT NULL DEFAULT '',
    certificate_id    INTEGER REFERENCES certificates (id) ON DELETE CASCADE,
    target_name       TEXT    NOT NULL DEFAULT '',
    target_pdf_name   TEXT    NOT NULL DEFAULT '',
    weight            REAL    NOT NULL DEFAULT 1.0,
    hit_count         INTEGER NOT NULL DEFAULT 0,
    is_manual         INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL,
    note              TEXT    NOT NULL DEFAULT '',
    UNIQUE (normalized_source, certificate_id)
);

CREATE INDEX IF NOT EXISTS idx_aliases_normalized ON aliases (normalized_source);
CREATE INDEX IF NOT EXISTS idx_aliases_token      ON aliases (token_source);
CREATE INDEX IF NOT EXISTS idx_aliases_target     ON aliases (certificate_id);

-- История обработки заказов ---------------------------------------------------
CREATE TABLE IF NOT EXISTS history (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id           TEXT    NOT NULL UNIQUE,
    order_file       TEXT    NOT NULL,
    output_file      TEXT    NOT NULL DEFAULT '',
    certificates_dir TEXT    NOT NULL DEFAULT '',
    report_file      TEXT    NOT NULL DEFAULT '',
    started_at       TEXT    NOT NULL,
    finished_at      TEXT,
    total_rows       INTEGER NOT NULL DEFAULT 0,
    matched          INTEGER NOT NULL DEFAULT 0,
    ambiguous        INTEGER NOT NULL DEFAULT 0,
    not_found        INTEGER NOT NULL DEFAULT 0,
    manual           INTEGER NOT NULL DEFAULT 0,
    copied_files     INTEGER NOT NULL DEFAULT 0,
    duration_ms      REAL    NOT NULL DEFAULT 0,
    status           TEXT    NOT NULL DEFAULT 'success',
    message          TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_history_started ON history (started_at DESC);

CREATE TABLE IF NOT EXISTS history_items (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id             TEXT    NOT NULL,
    row_number         INTEGER NOT NULL,
    product_name       TEXT    NOT NULL,
    status             TEXT    NOT NULL,
    certificate_id     INTEGER,
    certificate_number TEXT    NOT NULL DEFAULT '',
    certificate_expiry TEXT    NOT NULL DEFAULT '',
    pdf_name           TEXT    NOT NULL DEFAULT '',
    score              REAL    NOT NULL DEFAULT 0,
    method             TEXT    NOT NULL DEFAULT '',
    candidates_count   INTEGER NOT NULL DEFAULT 0,
    duration_ms        REAL    NOT NULL DEFAULT 0,
    note               TEXT    NOT NULL DEFAULT '',
    FOREIGN KEY (run_id) REFERENCES history (run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_history_items_run    ON history_items (run_id);
CREATE INDEX IF NOT EXISTS idx_history_items_status ON history_items (status);

-- Настройки, хранимые в базе (в дополнение к JSON-файлу) ----------------------
CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Универсальный кэш (эмбеддинги, результаты дорогих вычислений) ---------------
CREATE TABLE IF NOT EXISTS cache (
    namespace  TEXT    NOT NULL,
    key        TEXT    NOT NULL,
    value      BLOB,
    text_value TEXT,
    created_at TEXT    NOT NULL,
    expires_at TEXT,
    PRIMARY KEY (namespace, key)
);

CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache (expires_at);

-- Векторные представления наименований для семантического поиска -------------
CREATE TABLE IF NOT EXISTS embeddings (
    certificate_id INTEGER NOT NULL REFERENCES certificates (id) ON DELETE CASCADE,
    model          TEXT    NOT NULL,
    dimension      INTEGER NOT NULL,
    vector         BLOB    NOT NULL,
    source_hash    TEXT    NOT NULL DEFAULT '',
    created_at     TEXT    NOT NULL,
    PRIMARY KEY (certificate_id, model)
);
"""

#: Полнотекстовый индекс. Выделен отдельно: FTS5 доступен не во всех сборках
#: SQLite, и его отсутствие не должно мешать работе приложения.
_SCHEMA_FTS: Final[str] = """
CREATE VIRTUAL TABLE IF NOT EXISTS certificates_fts USING fts5 (
    product_name,
    normalized_name,
    certificate_number,
    brand,
    raw_text,
    content='certificates',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS certificates_fts_insert AFTER INSERT ON certificates BEGIN
    INSERT INTO certificates_fts (
        rowid, product_name, normalized_name, certificate_number, brand, raw_text
    )
    VALUES (
        new.id, new.product_name, new.normalized_name, new.certificate_number,
        new.brand, new.raw_text
    );
END;

CREATE TRIGGER IF NOT EXISTS certificates_fts_delete AFTER DELETE ON certificates BEGIN
    INSERT INTO certificates_fts (
        certificates_fts, rowid, product_name, normalized_name, certificate_number,
        brand, raw_text
    )
    VALUES (
        'delete', old.id, old.product_name, old.normalized_name,
        old.certificate_number, old.brand, old.raw_text
    );
END;

CREATE TRIGGER IF NOT EXISTS certificates_fts_update AFTER UPDATE ON certificates BEGIN
    INSERT INTO certificates_fts (
        certificates_fts, rowid, product_name, normalized_name, certificate_number,
        brand, raw_text
    )
    VALUES (
        'delete', old.id, old.product_name, old.normalized_name,
        old.certificate_number, old.brand, old.raw_text
    );
    INSERT INTO certificates_fts (
        rowid, product_name, normalized_name, certificate_number, brand, raw_text
    )
    VALUES (
        new.id, new.product_name, new.normalized_name, new.certificate_number,
        new.brand, new.raw_text
    );
END;
"""


#: Модуль управления словарём соответствий (версия 2): бренд и объём как
#: самостоятельные редактируемые поля алиаса (а не только производные от
#: связанного сертификата), раздельные отметки «изменён»/«применён» и
#: журнал аудита — основа отмены последнего действия и истории изменений.
_SCHEMA_V2: Final[str] = """
ALTER TABLE aliases ADD COLUMN brand         TEXT NOT NULL DEFAULT '';
ALTER TABLE aliases ADD COLUMN volume_value  REAL;
ALTER TABLE aliases ADD COLUMN volume_unit   TEXT NOT NULL DEFAULT '';
ALTER TABLE aliases ADD COLUMN last_used_at  TEXT;
ALTER TABLE aliases ADD COLUMN created_by    TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_aliases_brand ON aliases (brand);

-- Журнал изменений словаря: основа undo и раздела «Журнал изменений».
-- alias_id намеренно без FK — запись о удалении должна пережить сам алиас.
CREATE TABLE IF NOT EXISTS alias_audit (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    alias_id    INTEGER NOT NULL,
    action      TEXT    NOT NULL,
    source_text TEXT    NOT NULL DEFAULT '',
    before_json TEXT,
    after_json  TEXT,
    actor       TEXT    NOT NULL DEFAULT '',
    at          TEXT    NOT NULL,
    undone      INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_alias_audit_alias ON alias_audit (alias_id);
CREATE INDEX IF NOT EXISTS idx_alias_audit_at    ON alias_audit (at DESC);
"""


def _migration_001_initial(connection: sqlite3.Connection) -> None:
    """Создаёт начальную схему базы данных.

    Args:
        connection: Открытое соединение SQLite.
    """
    connection.executescript(_SCHEMA_V1)
    _try_create_fts(connection)


def _migration_002_alias_manager(connection: sqlite3.Connection) -> None:
    """Расширяет таблицу псевдонимов для модуля управления словарём.

    Args:
        connection: Открытое соединение SQLite.
    """
    connection.executescript(_SCHEMA_V2)


#: Модуль многопозиционных сертификатов (версия 3). Один PDF органа по
#: сертификации на практике удостоверяет не один товар, а таблицу из
#: десятков позиций («ПРИЛОЖЕНИЕ К СЕРТИФИКАТУ»), каждая — со своим
#: наименованием и сроком годности. Прежняя схема допускала только одну
#: запись на файл (``pdf_path`` был уникален сам по себе); теперь уникальна
#: пара «файл + порядковый номер позиции в приложении». SQLite не умеет
#: менять ограничение UNIQUE через ALTER TABLE, поэтому таблица
#: пересоздаётся с переносом данных (существующие записи получают
#: ``row_index = 0`` — они и были единственной позицией на файл).
_SCHEMA_V3: Final[str] = """
CREATE TABLE certificates_v3 (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name           TEXT    NOT NULL,
    normalized_name        TEXT    NOT NULL DEFAULT '',
    translit_name          TEXT    NOT NULL DEFAULT '',
    name_signature         TEXT    NOT NULL DEFAULT '',
    token_signature        TEXT    NOT NULL DEFAULT '',
    brand                  TEXT    NOT NULL DEFAULT '',
    manufacturer           TEXT    NOT NULL DEFAULT '',
    applicant              TEXT    NOT NULL DEFAULT '',
    country                TEXT    NOT NULL DEFAULT '',
    certificate_number     TEXT    NOT NULL DEFAULT '',
    certificate_date       TEXT,
    valid_from             TEXT,
    expiry_date            TEXT,
    issued_by              TEXT    NOT NULL DEFAULT '',
    volume_value           REAL,
    volume_unit            TEXT    NOT NULL DEFAULT '',
    volume_raw             TEXT    NOT NULL DEFAULT '',
    pack_count             INTEGER NOT NULL DEFAULT 1,
    row_index              INTEGER NOT NULL DEFAULT 0,
    pdf_name               TEXT    NOT NULL DEFAULT '',
    pdf_path               TEXT    NOT NULL,
    page_count             INTEGER NOT NULL DEFAULT 0,
    file_hash              TEXT    NOT NULL DEFAULT '',
    file_size              INTEGER NOT NULL DEFAULT 0,
    file_mtime             REAL    NOT NULL DEFAULT 0,
    indexed_at             TEXT    NOT NULL,
    updated_at             TEXT    NOT NULL,
    raw_text               TEXT    NOT NULL DEFAULT '',
    extraction_confidence  REAL    NOT NULL DEFAULT 0,
    is_active              INTEGER NOT NULL DEFAULT 1,
    UNIQUE (pdf_path, row_index)
);

INSERT INTO certificates_v3 (
    id, product_name, normalized_name, translit_name, name_signature, token_signature,
    brand, manufacturer, applicant, country, certificate_number, certificate_date,
    valid_from, expiry_date, issued_by, volume_value, volume_unit, volume_raw, pack_count,
    row_index, pdf_name, pdf_path, page_count, file_hash, file_size, file_mtime,
    indexed_at, updated_at, raw_text, extraction_confidence, is_active
)
SELECT
    id, product_name, normalized_name, translit_name, name_signature, token_signature,
    brand, manufacturer, applicant, country, certificate_number, certificate_date,
    valid_from, expiry_date, issued_by, volume_value, volume_unit, volume_raw, pack_count,
    0, pdf_name, pdf_path, page_count, file_hash, file_size, file_mtime,
    indexed_at, updated_at, raw_text, extraction_confidence, is_active
FROM certificates;

DROP TABLE certificates;
ALTER TABLE certificates_v3 RENAME TO certificates;

CREATE INDEX IF NOT EXISTS idx_certificates_normalized ON certificates (normalized_name);
CREATE INDEX IF NOT EXISTS idx_certificates_signature  ON certificates (name_signature);
CREATE INDEX IF NOT EXISTS idx_certificates_hash       ON certificates (file_hash);
CREATE INDEX IF NOT EXISTS idx_certificates_expiry     ON certificates (expiry_date);
CREATE INDEX IF NOT EXISTS idx_certificates_active     ON certificates (is_active);
CREATE INDEX IF NOT EXISTS idx_certificates_number     ON certificates (certificate_number);
CREATE INDEX IF NOT EXISTS idx_certificates_path       ON certificates (pdf_path);
"""


def _migration_003_multi_row_certificates(connection: sqlite3.Connection) -> None:
    """Пересоздаёт таблицу сертификатов с поддержкой нескольких позиций на файл.

    Триггеры полнотекстового индекса привязаны к таблице ``certificates`` и
    уничтожаются вместе с ней при ``DROP TABLE`` — их нужно создать заново,
    а сам индекс перестроить, чтобы он не расходился со старыми ``rowid``.

    Args:
        connection: Открытое соединение SQLite.
    """
    connection.executescript(_SCHEMA_V3)
    _try_create_fts(connection)
    rebuild_fts(connection)


def _try_create_fts(connection: sqlite3.Connection) -> None:
    """Создаёт полнотекстовый индекс, если сборка SQLite поддерживает FTS5.

    Args:
        connection: Открытое соединение SQLite.
    """
    try:
        connection.executescript(_SCHEMA_FTS)
        _LOGGER.debug("Полнотекстовый индекс FTS5 создан")
    except sqlite3.OperationalError as error:
        _LOGGER.warning(
            "FTS5 недоступен (%s) — поиск по тексту сертификатов будет выполняться перебором", error
        )


#: Реестр миграций: версия → функция применения.
MIGRATIONS: Final[dict[int, Callable[[sqlite3.Connection], None]]] = {
    1: _migration_001_initial,
    2: _migration_002_alias_manager,
    3: _migration_003_multi_row_certificates,
}

#: Целевая версия схемы.
TARGET_VERSION: Final[int] = max(MIGRATIONS)


def current_version(connection: sqlite3.Connection) -> int:
    """Возвращает текущую версию схемы базы.

    Args:
        connection: Открытое соединение SQLite.

    Returns:
        Значение ``PRAGMA user_version``.
    """
    row = connection.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row else 0


def apply_migrations(connection: sqlite3.Connection) -> int:
    """Приводит схему базы к целевой версии.

    Args:
        connection: Открытое соединение SQLite.

    Returns:
        Версия схемы после применения миграций.

    Raises:
        MigrationError: Если миграцию применить не удалось.
    """
    version = current_version(connection)
    if version >= TARGET_VERSION:
        return version

    for target in range(version + 1, TARGET_VERSION + 1):
        migration = MIGRATIONS.get(target)
        if migration is None:  # pragma: no cover — защита от разрыва в реестре
            raise MigrationError(f"Миграция до версии {target} не найдена")
        _LOGGER.info("Применение миграции базы данных до версии %s", target)
        try:
            with connection:
                migration(connection)
                connection.execute(f"PRAGMA user_version = {target}")
        except sqlite3.Error as error:
            raise MigrationError(
                f"Не удалось применить миграцию до версии {target}", details=str(error)
            ) from error

    return TARGET_VERSION


def has_fts(connection: sqlite3.Connection) -> bool:
    """Проверяет наличие полнотекстового индекса.

    Args:
        connection: Открытое соединение SQLite.

    Returns:
        ``True``, если таблица ``certificates_fts`` существует.
    """
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'certificates_fts'"
    ).fetchone()
    return row is not None


def rebuild_fts(connection: sqlite3.Connection) -> None:
    """Перестраивает полнотекстовый индекс из содержимого таблицы сертификатов.

    Args:
        connection: Открытое соединение SQLite.
    """
    if not has_fts(connection):
        _try_create_fts(connection)
        if not has_fts(connection):
            return
    try:
        with connection:
            connection.execute("INSERT INTO certificates_fts (certificates_fts) VALUES ('rebuild')")
        _LOGGER.info("Полнотекстовый индекс перестроен")
    except sqlite3.Error as error:  # pragma: no cover — зависит от сборки SQLite
        _LOGGER.warning("Не удалось перестроить полнотекстовый индекс: %s", error)
