"""Доменные модели приложения.

Все модели — dataclass без зависимостей от инфраструктуры: их можно создавать
в тестах, передавать между слоями и сериализовать без побочных эффектов.
"""

from app.models.alias import Alias
from app.models.certificate import Certificate
from app.models.history import IndexingResult, ProcessingItem, ProcessingRun
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
    "Certificate",
    "IndexingResult",
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
