"""Векторный индекс наименований для семантического поиска.

Реализация намеренно простая: матрица нормированных векторов в NumPy и поиск
скалярным произведением. Для справочника в десятки тысяч сертификатов это
даёт время отклика в единицы миллисекунд, не требуя внешней векторной базы
(FAISS, Qdrant), которую пришлось бы упаковывать в EXE и обслуживать.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from app.ai.embeddings import (
    VECTOR_DTYPE,
    EmbeddingBackend,
    bytes_to_vector,
    text_hash,
    vector_to_bytes,
)
from app.core.events import ProgressReporter
from app.core.text import normalize
from app.models.certificate import Certificate
from app.repositories.cache_repository import CacheRepository

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SemanticHit:
    """Кандидат, найденный семантическим поиском.

    Attributes:
        certificate_id: Идентификатор сертификата.
        score: Косинусная близость, приведённая к диапазону ``[0..1]``.
    """

    certificate_id: int
    score: float


class VectorIndex:
    """Хранилище и поиск векторных представлений наименований.

    Индекс строится инкрементально: пересчитываются только те наименования,
    для которых нет сохранённого вектора или изменился исходный текст.
    """

    def __init__(self, backend: EmbeddingBackend, cache: CacheRepository | None = None) -> None:
        """Создаёт индекс.

        Args:
            backend: Бэкенд вычисления векторов.
            cache: Репозиторий для персистентного хранения векторов.
        """
        self._backend = backend
        self._cache = cache
        self._matrix: np.ndarray = np.zeros((0, 0), dtype=VECTOR_DTYPE)
        self._ids: list[int] = []
        self._hashes: dict[int, str] = {}

    # ------------------------------------------------------------- свойства
    @property
    def size(self) -> int:
        """Количество векторов в индексе."""
        return len(self._ids)

    @property
    def is_ready(self) -> bool:
        """Признак того, что индекс пригоден для поиска."""
        return self.size > 0 and self._matrix.size > 0

    @property
    def dimension(self) -> int:
        """Размерность векторов в индексе."""
        return int(self._matrix.shape[1]) if self._matrix.ndim == 2 and self._matrix.size else 0

    # ------------------------------------------------------------- построение
    @staticmethod
    def source_text(certificate: Certificate) -> str:
        """Формирует текст, кодируемый для сертификата.

        К наименованию добавляется бренд: он часто является единственным
        различающим признаком между похожими позициями.

        Args:
            certificate: Сертификат.

        Returns:
            Текст для кодирования.
        """
        parts = [certificate.product_name]
        if certificate.brand:
            parts.append(certificate.brand)
        return normalize(" ".join(part for part in parts if part))

    def build(
        self,
        certificates: Sequence[Certificate],
        *,
        reporter: ProgressReporter | None = None,
        force: bool = False,
    ) -> int:
        """Строит или обновляет индекс.

        Args:
            certificates: Сертификаты, подлежащие индексации.
            reporter: Приёмник прогресса (кодирование может занять минуты).
            force: Пересчитать все векторы, игнорируя сохранённые.

        Returns:
            Количество заново вычисленных векторов.
        """
        if not self._backend.enabled:
            self.clear()
            return 0

        # Строится через явный цикл, а не словарное включение: только так
        # mypy сохраняет сужение `certificate.id is not None` до `int` внутри
        # тела цикла — в includes-выражении оно теряется.
        texts: dict[int, str] = {}
        for certificate in certificates:
            if certificate.id is not None:
                texts[certificate.id] = self.source_text(certificate)
        if not texts:
            self.clear()
            return 0

        stored: dict[int, tuple[bytes, str]] = {}
        if self._cache is not None and not force:
            stored = self._cache.load_embeddings(self._backend.model_name)

        hashes = {key: text_hash(value) for key, value in texts.items()}

        pending = [
            certificate_id
            for certificate_id in texts
            if force
            or certificate_id not in stored
            or stored[certificate_id][1] != hashes[certificate_id]
        ]

        computed = 0
        new_vectors: dict[int, bytes] = {}
        if pending:
            if not self._backend.ensure_loaded():
                _LOGGER.info("Семантический индекс не построен: модель недоступна")
                self.clear()
                return 0

            if reporter is not None:
                reporter.start(len(pending), "Вычисление семантического индекса", "embedding")

            chunk_size = 256
            for offset in range(0, len(pending), chunk_size):
                chunk = pending[offset : offset + chunk_size]
                vectors = self._backend.encode([texts[key] for key in chunk])
                if vectors.size == 0:
                    break
                for position, certificate_id in enumerate(chunk):
                    new_vectors[certificate_id] = vector_to_bytes(vectors[position])
                computed += len(chunk)
                if reporter is not None:
                    reporter.advance(
                        len(chunk), f"Обработано {computed} из {len(pending)}", "embedding"
                    )

            if new_vectors and self._cache is not None:
                self._cache.save_embeddings(
                    self._backend.model_name,
                    self._backend.dimension,
                    new_vectors,
                    {key: hashes[key] for key in new_vectors},
                )
            if reporter is not None:
                reporter.finish("Семантический индекс построен", "embedding")

        dimension = self._backend.dimension
        ids: list[int] = []
        rows: list[np.ndarray] = []
        for certificate_id in texts:
            payload = new_vectors.get(certificate_id)
            if payload is None:
                cached = stored.get(certificate_id)
                payload = cached[0] if cached else None
            if payload is None:
                continue
            vector = bytes_to_vector(payload, dimension)
            if vector.size == 0:
                continue
            ids.append(int(certificate_id))
            rows.append(vector)

        if rows:
            self._matrix = np.vstack(rows).astype(VECTOR_DTYPE, copy=False)
            self._ids = ids
            self._hashes = {key: hashes[key] for key in ids if key in hashes}
        else:
            self.clear()

        _LOGGER.info(
            "Семантический индекс: %s векторов (вычислено заново: %s)", self.size, computed
        )
        return computed

    def clear(self) -> None:
        """Полностью очищает индекс."""
        self._matrix = np.zeros((0, 0), dtype=VECTOR_DTYPE)
        self._ids = []
        self._hashes = {}

    # ---------------------------------------------------------------- поиск
    def search(self, query: str, *, top_k: int = 20, min_score: float = 0.30) -> list[SemanticHit]:
        """Находит семантически близкие наименования.

        Args:
            query: Наименование товара из заказа.
            top_k: Максимальное количество результатов.
            min_score: Минимальная близость.

        Returns:
            Кандидаты, отсортированные по убыванию близости.
        """
        if not self.is_ready or not query.strip():
            return []

        vector = self._backend.encode_one(normalize(query))
        if vector.size == 0 or vector.shape[0] != self._matrix.shape[1]:
            return []
        return self.search_by_vector(vector, top_k=top_k, min_score=min_score)

    def search_by_vector(
        self, vector: np.ndarray, *, top_k: int = 20, min_score: float = 0.30
    ) -> list[SemanticHit]:
        """Находит ближайшие векторы к заданному.

        Args:
            vector: Вектор запроса (нормированный).
            top_k: Максимальное количество результатов.
            min_score: Минимальная близость.

        Returns:
            Кандидаты, отсортированные по убыванию близости.
        """
        if not self.is_ready or vector.size == 0:
            return []

        similarities = self._matrix @ vector.astype(VECTOR_DTYPE, copy=False)
        # Косинусная близость лежит в [-1, 1]; отрицательные значения для
        # текстовых эмбеддингов означают полное несходство.
        count = min(top_k, similarities.shape[0])
        if count <= 0:
            return []

        top_indices = np.argpartition(-similarities, count - 1)[:count]
        top_indices = top_indices[np.argsort(-similarities[top_indices])]

        hits: list[SemanticHit] = []
        for index in top_indices:
            score = float(similarities[index])
            if score < min_score:
                continue
            hits.append(SemanticHit(certificate_id=self._ids[int(index)], score=round(score, 6)))
        return hits

    def score_pairs(self, query: str, certificate_ids: Sequence[int]) -> dict[int, float]:
        """Вычисляет близость запроса к конкретным сертификатам.

        Метод дешевле полного поиска: используется для уточнения оценок
        кандидатов, уже отобранных лексическим этапом.

        Args:
            query: Наименование товара из заказа.
            certificate_ids: Идентификаторы сертификатов-кандидатов.

        Returns:
            Отображение «идентификатор → близость».
        """
        if not self.is_ready or not certificate_ids:
            return {}

        vector = self._backend.encode_one(normalize(query))
        if vector.size == 0 or vector.shape[0] != self._matrix.shape[1]:
            return {}

        position_by_id = {certificate_id: index for index, certificate_id in enumerate(self._ids)}
        rows = [
            (certificate_id, position_by_id[certificate_id])
            for certificate_id in certificate_ids
            if certificate_id in position_by_id
        ]
        if not rows:
            return {}

        indices = np.array([position for _, position in rows], dtype=np.int64)
        similarities = self._matrix[indices] @ vector.astype(VECTOR_DTYPE, copy=False)
        return {
            certificate_id: round(float(similarities[position]), 6)
            for position, (certificate_id, _) in enumerate(rows)
        }
