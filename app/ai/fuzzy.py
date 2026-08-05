"""Лексический (нечёткий) поиск кандидатов на основе RapidFuzz.

Это второй этап конвейера подбора и основной «рабочий конь» системы: он
находит 90–95 % совпадений, потребляя доли миллисекунды на позицию.

Ключевое решение — двухскриптовое сравнение. Каждое наименование хранится
в двух формах (нормализованной и транслитерированной), запрос сравнивается
с обеими, берётся лучшая оценка. Это позволяет сопоставить «Витамин С» и
«Vitamin C» без нейросетевой модели.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from rapidfuzz import fuzz, process, utils

from app.core.text import alpha_signature, normalize, transliterate
from app.models.certificate_product import CertificateProduct

_LOGGER = logging.getLogger(__name__)

#: Нижняя граница оценки, ниже которой кандидат даже не рассматривается.
DEFAULT_SCORE_CUTOFF: Final[float] = 45.0

#: Вклад «сигнатуры» (наименование без чисел и единиц) в оценку наименования.
#:
#: Сигнатура — основной сигнал. Сравнивать наименования целиком нельзя:
#: «Масло облепиховое 100 мл» и «Гель антисептический 100 мл» получают у любого
#: подстрочного алгоритма высокую оценку из-за общего фрагмента «100 ml», хотя
#: это разные товары. Объём оценивается отдельной составляющей с весом 30 %,
#: поэтому его влияние на оценку наименования — прямое двойное начисление.
_SIGNATURE_WEIGHT: Final[float] = 0.75

#: Вклад полного нормализованного наименования (числа значимы, например «3%»).
_FULL_WEIGHT: Final[float] = 1.0 - _SIGNATURE_WEIGHT


@dataclass(frozen=True, slots=True)
class LexicalHit:
    """Кандидат, найденный лексическим поиском.

    Attributes:
        certificate: Найденный сертификат.
        score: Оценка совпадения ``[0..1]``.
        matched_form: Форма, давшая лучшую оценку (``normalized``/``translit``).
    """

    certificate: CertificateProduct
    score: float
    matched_form: str


class LexicalIndex:
    """Индекс наименований сертификатов для нечёткого поиска.

    Индекс строится один раз после загрузки справочника и переиспользуется
    для всех строк заказа: подготовка списков — самая дорогая часть, а сам
    поиск в RapidFuzz выполняется в C-коде без удержания GIL.
    """

    def __init__(self, certificates: Sequence[CertificateProduct]) -> None:
        """Строит индекс по списку сертификатов.

        Args:
            certificates: Сертификаты, участвующие в подборе.
        """
        self._certificates: list[CertificateProduct] = list(certificates)
        self._normalized: list[str] = []
        self._translit: list[str] = []
        self._signatures: list[str] = []
        self._rebuild()

    def _rebuild(self) -> None:
        """Пересобирает внутренние массивы строк для поиска."""
        self._normalized = [
            certificate.normalized_name or normalize(certificate.product_name)
            for certificate in self._certificates
        ]
        self._translit = [
            certificate.translit_name or transliterate(certificate.product_name)
            for certificate in self._certificates
        ]
        self._signatures = [
            certificate.name_signature or alpha_signature(certificate.product_name)
            for certificate in self._certificates
        ]
        _LOGGER.debug("Лексический индекс построен: %s наименований", len(self._certificates))

    # ------------------------------------------------------------- свойства
    @property
    def size(self) -> int:
        """Количество проиндексированных сертификатов."""
        return len(self._certificates)

    @property
    def certificates(self) -> list[CertificateProduct]:
        """Проиндексированные сертификаты в порядке добавления."""
        return self._certificates

    def certificate_at(self, index: int) -> CertificateProduct:
        """Возвращает сертификат по внутреннему индексу.

        Args:
            index: Позиция в индексе.

        Returns:
            Сертификат.
        """
        return self._certificates[index]

    # ---------------------------------------------------------------- поиск
    def search(
        self,
        query: str,
        *,
        limit: int = 40,
        score_cutoff: float = DEFAULT_SCORE_CUTOFF,
    ) -> list[LexicalHit]:
        """Находит наиболее похожие наименования.

        Поиск двухфазный. Быстрая фаза отбирает кандидатов по сигнатуре
        наименования средствами RapidFuzz (C-код, без удержания GIL); точная
        фаза пересчитывает для них составную оценку, устойчивую к совпадению
        чисел и единиц измерения.

        Args:
            query: Наименование товара из заказа.
            limit: Максимальное количество кандидатов.
            score_cutoff: Минимальная оценка в шкале ``0..100``.

        Returns:
            Кандидаты, отсортированные по убыванию оценки.
        """
        if not self._certificates:
            return []

        normalized_query = normalize(query)
        if not normalized_query:
            return []

        translit_query = transliterate(query)
        signature_query = alpha_signature(query) or normalized_query
        translit_signature = transliterate(signature_query)

        # --- Фаза 1: быстрый отбор ------------------------------------------
        prefilter_limit = max(limit * 3, 60)
        prefiltered: dict[int, str] = {}
        for form_name, haystack, needle in (
            ("signature", self._signatures, signature_query),
            ("translit", self._translit, translit_signature),
            ("normalized", self._normalized, normalized_query),
        ):
            if not needle:
                continue
            for _, _, index in process.extract(
                needle,
                haystack,
                scorer=fuzz.token_sort_ratio,
                processor=utils.default_process,
                limit=prefilter_limit,
                score_cutoff=max(30.0, score_cutoff - 20.0),
            ):
                prefiltered.setdefault(index, form_name)

        if not prefiltered:
            return []

        # --- Фаза 2: точная составная оценка --------------------------------
        hits: list[LexicalHit] = []
        for index, form_name in prefiltered.items():
            score = _composite_score(
                signature_query,
                translit_signature,
                normalized_query,
                translit_query,
                self._signatures[index],
                self._normalized[index],
                self._translit[index],
            )
            if score * 100.0 < score_cutoff:
                continue
            hits.append(
                LexicalHit(
                    certificate=self._certificates[index],
                    score=score,
                    matched_form=form_name,
                )
            )

        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:limit]

    def search_by_signature(self, query: str, *, limit: int = 40) -> list[LexicalHit]:
        """Ищет товары «того же наименования, но другого объёма».

        Сравниваются сигнатуры без чисел и единиц измерения. Метод нужен для
        окна неоднозначности: пользователю полезно видеть весь ряд фасовок.

        Args:
            query: Наименование товара.
            limit: Максимальное количество кандидатов.

        Returns:
            Кандидаты, отсортированные по убыванию оценки.
        """
        signature = alpha_signature(query)
        if not signature or not self._certificates:
            return []
        matches = process.extract(
            signature,
            self._signatures,
            scorer=fuzz.token_set_ratio,
            processor=utils.default_process,
            limit=limit,
            score_cutoff=70.0,
        )
        return [
            LexicalHit(
                certificate=self._certificates[index],
                score=round(float(score) / 100.0, 6),
                matched_form="signature",
            )
            for _, score, index in matches
        ]


def _pair_score(left: str, right: str) -> float:
    """Сравнивает две строки, комбинируя порядко-независимые метрики.

    Используются только ``token_sort_ratio`` и ``token_set_ratio``.
    ``partial_ratio`` (и построенный на нём ``WRatio``) сознательно исключён:
    он оценивает вхождение подстроки и потому присваивает высокую оценку
    парам вида «Масло облепиховое 100 мл» / «Гель для рук 100 мл».

    Args:
        left: Первая строка (нормализованная).
        right: Вторая строка (нормализованная).

    Returns:
        Оценка в диапазоне ``[0.0, 1.0]``.
    """
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    sorted_ratio = fuzz.token_sort_ratio(left, right)
    set_ratio = fuzz.token_set_ratio(left, right)
    # token_set_ratio склонен завышать оценку при частичном пересечении
    # множеств токенов, поэтому берётся с понижающим коэффициентом.
    return max(sorted_ratio, set_ratio * 0.85) / 100.0


def _composite_score(
    signature_query: str,
    translit_signature_query: str,
    normalized_query: str,
    translit_query: str,
    candidate_signature: str,
    candidate_normalized: str,
    candidate_translit: str,
) -> float:
    """Вычисляет составную оценку совпадения наименований.

    Args:
        signature_query: Сигнатура запроса (без чисел и единиц).
        translit_signature_query: Латинизированная сигнатура запроса.
        normalized_query: Нормализованный запрос целиком.
        translit_query: Латинизированный запрос целиком.
        candidate_signature: Сигнатура кандидата.
        candidate_normalized: Нормализованное наименование кандидата.
        candidate_translit: Латинизированное наименование кандидата.

    Returns:
        Оценка в диапазоне ``[0.0, 1.0]``.
    """
    signature_score = max(
        _pair_score(signature_query, candidate_signature),
        _pair_score(translit_signature_query, transliterate(candidate_signature)),
    )
    full_score = max(
        _pair_score(normalized_query, candidate_normalized),
        _pair_score(translit_query, candidate_translit),
    )
    return round(signature_score * _SIGNATURE_WEIGHT + full_score * _FULL_WEIGHT, 6)


def similarity(left: str, right: str) -> float:
    """Оценивает схожесть двух наименований без построения индекса.

    Используется для точечных сравнений: проверка псевдонима, отображение
    процента совпадения в интерфейсе.

    Args:
        left: Первое наименование.
        right: Второе наименование.

    Returns:
        Оценка в диапазоне ``[0.0, 1.0]``.
    """
    left_normalized = normalize(left)
    right_normalized = normalize(right)
    if not left_normalized or not right_normalized:
        return 0.0
    if left_normalized == right_normalized:
        return 1.0

    left_signature = alpha_signature(left) or left_normalized
    right_signature = alpha_signature(right) or right_normalized
    return _composite_score(
        left_signature,
        transliterate(left_signature),
        left_normalized,
        transliterate(left),
        right_signature,
        right_normalized,
        transliterate(right),
    )
