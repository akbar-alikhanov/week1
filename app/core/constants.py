"""Неизменяемые константы приложения.

Модуль намеренно не имеет зависимостей — его можно импортировать из любого слоя
(включая GUI и скрипты сборки) без риска циклических импортов.
"""

from __future__ import annotations

from typing import Final

# --------------------------------------------------------------------------- #
# Идентификация приложения
# --------------------------------------------------------------------------- #
APP_NAME: Final[str] = "BALTON CertMatcher"
APP_SLUG: Final[str] = "BaltonCertMatcher"
APP_VERSION: Final[str] = "1.0.0"
APP_COMPANY: Final[str] = "BALTON TRADING ASIA"
APP_DESCRIPTION: Final[str] = "Автоматический подбор сертификатов соответствия для аптечных заказов"

# --------------------------------------------------------------------------- #
# Файловая система
# --------------------------------------------------------------------------- #
DATABASE_FILENAME: Final[str] = "certmatcher.db"
SETTINGS_FILENAME: Final[str] = "settings.json"
WINDOW_STATE_FILENAME: Final[str] = "window_state.json"
LOG_FILENAME: Final[str] = "certmatcher.log"
ERROR_LOG_FILENAME: Final[str] = "errors.log"
PORTABLE_MARKER: Final[str] = "portable.flag"

#: Имя папки, в которую копируются подобранные PDF-сертификаты.
CERTIFICATES_OUTPUT_DIRNAME: Final[str] = "Certificates"

#: Расширения, которые сканер считает сертификатами.
PDF_EXTENSIONS: Final[frozenset[str]] = frozenset({".pdf"})

#: Расширения файлов заказов.
EXCEL_EXTENSIONS: Final[frozenset[str]] = frozenset({".xlsx", ".xlsm", ".xls"})

# --------------------------------------------------------------------------- #
# Схема базы данных
# --------------------------------------------------------------------------- #
SCHEMA_VERSION: Final[int] = 1

# --------------------------------------------------------------------------- #
# Подбор
# --------------------------------------------------------------------------- #
#: Идентификатор модели семантического поиска по умолчанию.
#: Многоязычная модель — критично для смеси русского/узбекского/английского.
DEFAULT_EMBEDDING_MODEL: Final[str] = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

#: Статусы результата подбора (используются в БД, Excel и отчётах).
STATUS_MATCHED: Final[str] = "matched"
STATUS_AMBIGUOUS: Final[str] = "ambiguous"
STATUS_NOT_FOUND: Final[str] = "not_found"
STATUS_MANUAL: Final[str] = "manual"
STATUS_SKIPPED: Final[str] = "skipped"

#: Человекочитаемые названия статусов для интерфейса и отчётов.
STATUS_LABELS: Final[dict[str, str]] = {
    STATUS_MATCHED: "Найден",
    STATUS_AMBIGUOUS: "Требует проверки",
    STATUS_NOT_FOUND: "Не найден",
    STATUS_MANUAL: "Выбран вручную",
    STATUS_SKIPPED: "Пропущен",
}

# --------------------------------------------------------------------------- #
# Производительность
# --------------------------------------------------------------------------- #
#: Размер пакета вставки в SQLite при индексации.
DB_BATCH_SIZE: Final[int] = 200

#: Сколько символов текста PDF сохраняется в БД для последующего поиска.
RAW_TEXT_EXCERPT_LIMIT: Final[int] = 4000

#: Максимум страниц PDF, читаемых при извлечении полей (сертификаты короткие).
PDF_MAX_PAGES_TO_PARSE: Final[int] = 4
