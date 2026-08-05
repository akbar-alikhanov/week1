"""Общие фикстуры pytest.

Фикстуры уровня сессии (шрифты, тяжёлые модели) здесь намеренно отсутствуют:
модульные тесты обязаны оставаться быстрыми и независимыми от порядка запуска.
Каждый тест, которому нужна база данных, получает собственный временный файл.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.database.connection import Database
from app.models.certificate import Certificate
from app.repositories.alias_repository import AliasRepository
from app.repositories.cache_repository import CacheRepository
from app.repositories.certificate_repository import CertificateRepository
from app.repositories.history_repository import HistoryRepository
from app.repositories.product_repository import ProductRepository
from app.repositories.settings_repository import SettingsRepository


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    """Создаёт временную инициализированную базу данных."""
    db = Database(tmp_path / "test.db")
    db.initialize()
    yield db
    db.close()


@pytest.fixture
def certificate_repository(database: Database) -> CertificateRepository:
    """Репозиторий сертификатов поверх временной базы."""
    return CertificateRepository(database)


@pytest.fixture
def alias_repository(database: Database) -> AliasRepository:
    """Репозиторий псевдонимов поверх временной базы."""
    return AliasRepository(database)


@pytest.fixture
def product_repository(database: Database) -> ProductRepository:
    """Репозиторий товаров поверх временной базы."""
    return ProductRepository(database)


@pytest.fixture
def history_repository(database: Database) -> HistoryRepository:
    """Репозиторий истории поверх временной базы."""
    return HistoryRepository(database)


@pytest.fixture
def cache_repository(database: Database) -> CacheRepository:
    """Репозиторий кэша поверх временной базы."""
    return CacheRepository(database)


@pytest.fixture
def settings_repository(database: Database) -> SettingsRepository:
    """Репозиторий служебных настроек поверх временной базы."""
    return SettingsRepository(database)


def make_certificate(
    product_name: str,
    pdf_path: str,
    *,
    volume_value: float | None = None,
    volume_unit: str = "",
    expiry_date: dt.date | None = None,
    certificate_number: str = "",
    brand: str = "",
    row_index: int = 0,
) -> Certificate:
    """Создаёт сертификат для использования в тестах.

    Args:
        product_name: Наименование товара.
        pdf_path: Путь к PDF-файлу (может быть фиктивным).
        volume_value: Объём в базовых единицах.
        volume_unit: Базовая единица объёма.
        expiry_date: Срок действия.
        certificate_number: Номер сертификата.
        brand: Торговая марка.
        row_index: Порядковый номер позиции внутри приложения к сертификату
            (несколько записей с одним ``pdf_path`` и разными ``row_index``
            имитируют файл с таблицей приложения).

    Returns:
        Заполненный объект :class:`Certificate`.
    """
    return Certificate(
        product_name=product_name,
        pdf_path=pdf_path,
        volume_value=volume_value,
        volume_unit=volume_unit,
        expiry_date=expiry_date,
        certificate_number=certificate_number,
        brand=brand,
        row_index=row_index,
    )
