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
from app.models.certificate_product import CertificateProduct
from app.repositories.alias_repository import AliasRepository
from app.repositories.cache_repository import CacheRepository
from app.repositories.certificate_product_repository import CertificateProductRepository
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
def certificate_repository(database: Database) -> CertificateProductRepository:
    """Репозиторий базы сертификатов поверх временной базы."""
    return CertificateProductRepository(database)


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
    *,
    volume_ml: float | None = None,
    expiry_date: dt.date | None = None,
    certificate_number: str = "",
    source_row: int = 0,
) -> CertificateProduct:
    """Создаёт строку базы сертификатов для использования в тестах.

    Args:
        product_name: Наименование товара.
        volume_ml: Объём в базовых единицах (``None`` — извлечь из названия).
        expiry_date: Срок годности.
        certificate_number: Номер сертификата.
        source_row: Порядковый номер строки в исходном Excel-файле.

    Returns:
        Заполненный объект :class:`CertificateProduct`.
    """
    return CertificateProduct(
        product_name=product_name,
        volume_ml=volume_ml,
        expiry_date=expiry_date,
        certificate_number=certificate_number,
        source_row=source_row,
    )
