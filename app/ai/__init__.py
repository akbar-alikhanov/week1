"""Алгоритмическое ядро подбора: нечёткий и семантический поиск, оценка."""

from app.ai.embeddings import EmbeddingBackend, EmbeddingBackendStatus
from app.ai.fuzzy import LexicalHit, LexicalIndex, similarity
from app.ai.scorer import ScoringContext, is_hard_mismatch, score_candidate
from app.ai.vector_index import SemanticHit, VectorIndex

__all__ = [
    "EmbeddingBackend",
    "EmbeddingBackendStatus",
    "LexicalHit",
    "LexicalIndex",
    "ScoringContext",
    "SemanticHit",
    "VectorIndex",
    "is_hard_mismatch",
    "score_candidate",
    "similarity",
]
