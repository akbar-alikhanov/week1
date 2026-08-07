"""Доменные модели приложения.

Все модели — dataclass без зависимостей от инфраструктуры: их можно создавать
в тестах, передавать между слоями и сериализовать без побочных эффектов.
"""

from app.models.alias import Alias
from app.models.certificate_product import CertificateProduct
from app.models.expiry_stock import ExpiryStockEntry
from app.models.history import ImportResult, ProcessingItem, ProcessingRun
from app.models.matching import (
    MatchCandidate,
    MatchResult,
    MatchSource,
    MatchStatus,
    ScoreBreakdown,
)
from app.models.order import OrderDocument, OrderRow
from app.models.product import Product

__all__ = [
    "Alias",
    "CertificateProduct",
    "ExpiryStockEntry",
    "ImportResult",
    "MatchCandidate",
    "MatchResult",
    "MatchSource",
    "MatchStatus",
    "OrderDocument",
    "OrderRow",
    "ProcessingItem",
    "ProcessingRun",
    "Product",
    "ScoreBreakdown",
]
