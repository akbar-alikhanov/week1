"""Репозитории — единственное место в приложении, где присутствует SQL."""

from app.repositories.alias_repository import AliasRepository
from app.repositories.base import BaseRepository
from app.repositories.cache_repository import CacheRepository
from app.repositories.certificate_product_repository import CertificateProductRepository
from app.repositories.expiry_stock_repository import ExpiryStockRepository
from app.repositories.history_repository import HistoryRepository
from app.repositories.product_repository import ProductRepository
from app.repositories.settings_repository import SettingsRepository

__all__ = [
    "AliasRepository",
    "BaseRepository",
    "CacheRepository",
    "CertificateProductRepository",
    "ExpiryStockRepository",
    "HistoryRepository",
    "ProductRepository",
    "SettingsRepository",
]
