"""Семантический бэкенд на Sentence Transformers.

Третий этап конвейера подбора. Он подключается только там, где лексический
поиск неуверен, и решает единственную задачу, недоступную RapidFuzz:
сопоставление наименований, не имеющих общих букв, — «TP Herbal» и
«Лечебные травы», «Cough syrup» и «Сироп от кашля».

Инженерные требования, определившие устройство модуля:

* **Необязательность.** ``sentence-transformers`` тянет за собой PyTorch
  (~2 ГБ). Приложение обязано полноценно работать и без него, поэтому
  импорт ленивый, а отсутствие пакета переводит бэкенд в режим «выключен».
* **Ленивая загрузка.** Модель весит сотни мегабайт и грузится секунды —
  делать это на старте недопустимо.
* **Кэширование векторов.** Векторы наименований сохраняются в базе и
  переиспользуются между запусками: пересчитываются только новые записи.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.core.constants import DEFAULT_EMBEDDING_MODEL
from app.core.exceptions import EmbeddingBackendError

_LOGGER = logging.getLogger(__name__)

#: Тип данных хранимых векторов. float32 вдвое компактнее float64
#: при неразличимой на практике потере точности косинусной близости.
VECTOR_DTYPE = np.float32


@dataclass(frozen=True, slots=True)
class EmbeddingBackendStatus:
    """Состояние семантического бэкенда для интерфейса и диагностики.

    Attributes:
        available: Установлена ли библиотека.
        loaded: Загружена ли модель в память.
        model_name: Идентификатор модели.
        dimension: Размерность векторов (0, если модель не загружена).
        message: Пояснение для пользователя.
        failed: Провалилась ли последняя попытка загрузки модели.
    """

    available: bool
    loaded: bool
    model_name: str
    dimension: int = 0
    message: str = ""
    failed: bool = False


def text_hash(text: str) -> str:
    """Вычисляет короткий хэш исходного текста.

    Позволяет понять, нужно ли пересчитывать сохранённый вектор.

    Args:
        text: Исходный текст.

    Returns:
        Первые 16 символов SHA-1 в шестнадцатеричном виде.
    """
    return hashlib.sha1(text.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


class EmbeddingBackend:
    """Обёртка над моделью Sentence Transformers.

    Класс потокобезопасен: загрузка модели защищена блокировкой, а сам
    вызов ``encode`` в библиотеке безопасен для параллельного использования.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        *,
        cache_dir: Path | None = None,
        enabled: bool = True,
        batch_size: int = 64,
    ) -> None:
        """Создаёт бэкенд без загрузки модели.

        Args:
            model_name: Идентификатор модели Sentence Transformers.
            cache_dir: Каталог для локального хранения модели.
            enabled: Разрешено ли использование семантического поиска.
            batch_size: Размер пакета при кодировании.
        """
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._enabled = enabled
        self._batch_size = max(1, batch_size)
        self._model: Any | None = None
        self._dimension = 0
        self._lock = threading.RLock()
        self._load_failed = False
        self._failure_reason = ""

    # ------------------------------------------------------------- свойства
    @property
    def model_name(self) -> str:
        """Идентификатор используемой модели."""
        return self._model_name

    @property
    def dimension(self) -> int:
        """Размерность векторов (0, пока модель не загружена)."""
        return self._dimension

    @property
    def is_loaded(self) -> bool:
        """Признак того, что модель загружена в память."""
        return self._model is not None

    @property
    def enabled(self) -> bool:
        """Разрешено ли использование бэкенда."""
        return self._enabled and not self._load_failed

    def set_enabled(self, value: bool) -> None:
        """Включает или выключает семантический этап.

        Args:
            value: Новое состояние.
        """
        self._enabled = value
        if value:
            self._load_failed = False

    @staticmethod
    def library_available() -> bool:
        """Проверяет наличие пакета ``sentence-transformers``.

        Returns:
            ``True``, если библиотеку можно импортировать.
        """
        try:
            import importlib.util

            return importlib.util.find_spec("sentence_transformers") is not None
        except (ImportError, ValueError):  # pragma: no cover
            return False

    def status(self) -> EmbeddingBackendStatus:
        """Возвращает состояние бэкенда для интерфейса.

        Returns:
            Снимок состояния с пояснением для пользователя.
        """
        available = self.library_available()
        if not available:
            return EmbeddingBackendStatus(
                available=False,
                loaded=False,
                model_name=self._model_name,
                message=(
                    "Семантический поиск недоступен: не установлен пакет "
                    "sentence-transformers. Подбор работает на нечётком поиске "
                    "и псевдонимах."
                ),
            )
        if not self._enabled:
            return EmbeddingBackendStatus(
                available=True,
                loaded=False,
                model_name=self._model_name,
                message="Семантический поиск выключен в настройках",
            )
        if self._load_failed:
            return EmbeddingBackendStatus(
                available=True,
                loaded=False,
                model_name=self._model_name,
                message=f"Модель не загрузилась: {self._failure_reason}",
                failed=True,
            )
        return EmbeddingBackendStatus(
            available=True,
            loaded=self.is_loaded,
            model_name=self._model_name,
            dimension=self._dimension,
            message=(
                "Модель загружена"
                if self.is_loaded
                else "Модель будет загружена при первом обращении"
            ),
        )

    # ------------------------------------------------------------- загрузка
    def ensure_loaded(self) -> bool:
        """Загружает модель, если это ещё не сделано.

        Returns:
            ``True``, если модель готова к работе.
        """
        if not self._enabled or self._load_failed:
            return False
        if self._model is not None:
            return True

        with self._lock:
            if self._model is not None:
                return True
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as error:
                self._load_failed = True
                self._failure_reason = "пакет sentence-transformers не установлен"
                _LOGGER.info("Семантический поиск недоступен: %s", error)
                return False

            _LOGGER.info("Загрузка семантической модели %s …", self._model_name)
            try:
                kwargs: dict[str, Any] = {}
                if self._cache_dir is not None:
                    kwargs["cache_folder"] = str(self._cache_dir)
                model = SentenceTransformer(self._model_name, **kwargs)
                self._dimension = int(model.get_sentence_embedding_dimension() or 0)
                self._model = model
            except Exception as error:
                self._load_failed = True
                self._failure_reason = str(error)[:200]
                _LOGGER.warning("Не удалось загрузить модель %s: %s", self._model_name, error)
                return False

            _LOGGER.info("Семантическая модель загружена (размерность %s)", self._dimension)
            return True

    def unload(self) -> None:
        """Выгружает модель из памяти, освобождая сотни мегабайт."""
        with self._lock:
            self._model = None
            self._dimension = 0

    # ------------------------------------------------------------ кодирование
    def encode(self, texts: Sequence[str], *, normalize_vectors: bool = True) -> np.ndarray:
        """Преобразует тексты в векторы.

        Args:
            texts: Наименования для кодирования.
            normalize_vectors: Нормировать ли векторы к единичной длине.
                При нормировке косинусная близость сводится к скалярному
                произведению, что кратно ускоряет поиск.

        Returns:
            Массив формы ``(len(texts), dimension)`` типа ``float32``.
            Пустой массив, если бэкенд недоступен.

        Raises:
            EmbeddingBackendError: Если кодирование завершилось ошибкой.
        """
        if not texts:
            return np.zeros((0, self._dimension or 1), dtype=VECTOR_DTYPE)
        if not self.ensure_loaded() or self._model is None:
            return np.zeros((0, 1), dtype=VECTOR_DTYPE)

        try:
            vectors = self._model.encode(
                list(texts),
                batch_size=self._batch_size,
                convert_to_numpy=True,
                normalize_embeddings=normalize_vectors,
                show_progress_bar=False,
            )
        except Exception as error:
            raise EmbeddingBackendError(
                "Не удалось вычислить семантические векторы", details=str(error)
            ) from error

        return np.asarray(vectors, dtype=VECTOR_DTYPE)

    def encode_one(self, text: str) -> np.ndarray:
        """Кодирует одно наименование.

        Args:
            text: Наименование товара.

        Returns:
            Вектор формы ``(dimension,)``; пустой массив, если бэкенд выключен.
        """
        vectors = self.encode([text])
        if vectors.size == 0:
            return np.zeros((0,), dtype=VECTOR_DTYPE)
        return np.asarray(vectors[0], dtype=VECTOR_DTYPE)


def vector_to_bytes(vector: np.ndarray) -> bytes:
    """Сериализует вектор для хранения в базе.

    Args:
        vector: Вектор ``float32``.

    Returns:
        Двоичное представление.
    """
    return np.asarray(vector, dtype=VECTOR_DTYPE).tobytes()


def bytes_to_vector(payload: bytes, dimension: int) -> np.ndarray:
    """Восстанавливает вектор из двоичного представления.

    Args:
        payload: Двоичные данные.
        dimension: Ожидаемая размерность.

    Returns:
        Вектор ``float32``; пустой массив при несовпадении размерности.
    """
    vector = np.frombuffer(payload, dtype=VECTOR_DTYPE)
    if dimension and vector.size != dimension:
        return np.zeros((0,), dtype=VECTOR_DTYPE)
    return vector
