"""Многоэтапный подбор сертификата для строки заказа.

Конвейер (порядок этапов задан требованиями и не подлежит изменению без
пересмотра ожиданий пользователя):

1. **Псевдонимы.** Ранее подтверждённое человеком соответствие. Мгновенно,
   детерминированно, имеет приоритет над любой эвристикой.
2. **Точное совпадение** нормализованных наименований.
3. **Нечёткий поиск** (RapidFuzz) — основной источник кандидатов.
4. **Семантический поиск** (Sentence Transformers) — подключается, когда
   лексика неуверена, и находит совпадения без общих букв.
5. **Сравнение объёма.**
6. **Сравнение срока** и выбор ближайшего по сроку из равных кандидатов.

Итоговая оценка — взвешенная сумма трёх составляющих (50/30/20 по умолчанию).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Sequence

from app.ai.embeddings import EmbeddingBackend
from app.ai.fuzzy import LexicalIndex
from app.ai.scorer import ScoringContext, is_hard_mismatch, score_candidate
from app.ai.vector_index import VectorIndex
from app.config.settings import SettingsService
from app.core.events import ProgressReporter
from app.core.text import normalize
from app.models.certificate import Certificate
from app.models.matching import (
    MatchCandidate,
    MatchResult,
    MatchSource,
    MatchStatus,
    ScoreBreakdown,
)
from app.models.order import OrderRow
from app.repositories.alias_repository import AliasRepository
from app.repositories.certificate_repository import CertificateRepository

_LOGGER = logging.getLogger(__name__)


class MatchingService:
    """Подбирает сертификаты для позиций заказа.

    Сервис держит в памяти подготовленные индексы справочника. Метод
    :meth:`prepare` вызывается один раз перед обработкой заказа, после чего
    :meth:`match_row` отрабатывает за доли миллисекунды.
    """

    def __init__(
        self,
        certificate_repository: CertificateRepository,
        alias_repository: AliasRepository,
        settings_service: SettingsService,
        embedding_backend: EmbeddingBackend,
        vector_index: VectorIndex,
    ) -> None:
        """Создаёт сервис подбора.

        Args:
            certificate_repository: Доступ к справочнику сертификатов.
            alias_repository: Доступ к таблице псевдонимов.
            settings_service: Источник параметров алгоритма.
            embedding_backend: Семантический бэкенд.
            vector_index: Векторный индекс наименований.
        """
        self._certificates = certificate_repository
        self._aliases = alias_repository
        self._settings = settings_service
        self._backend = embedding_backend
        self._vectors = vector_index
        self._lexical: LexicalIndex | None = None
        self._by_id: dict[int, Certificate] = {}
        self._by_normalized: dict[str, list[Certificate]] = {}
        self._lock = threading.RLock()
        self._prepared = False

    # ---------------------------------------------------------- подготовка
    @property
    def is_prepared(self) -> bool:
        """Признак готовности индексов к подбору."""
        return self._prepared

    @property
    def indexed_count(self) -> int:
        """Количество сертификатов в подготовленном индексе."""
        return len(self._by_id)

    def prepare(self, *, reporter: ProgressReporter | None = None, force: bool = False) -> int:
        """Загружает справочник и строит индексы поиска.

        Args:
            reporter: Приёмник прогресса (построение векторов небыстрое).
            force: Перестроить индексы, даже если они уже готовы.

        Returns:
            Количество сертификатов, доступных для подбора.
        """
        with self._lock:
            if self._prepared and not force:
                return len(self._by_id)

            settings = self._settings.current.matching
            certificates = self._certificates.list_active(
                include_expired=not settings.require_valid_expiry
            )

            self._by_id = {
                certificate.id: certificate
                for certificate in certificates
                if certificate.id is not None
            }
            self._by_normalized = {}
            for certificate in certificates:
                key = certificate.normalized_name or normalize(certificate.product_name)
                if key:
                    self._by_normalized.setdefault(key, []).append(certificate)

            self._lexical = LexicalIndex(certificates)

            self._backend.set_enabled(settings.use_semantic)
            if settings.use_semantic and self._backend.enabled:
                try:
                    self._vectors.build(certificates, reporter=reporter)
                except Exception as error:
                    _LOGGER.warning("Семантический индекс не построен: %s", error)
                    self._vectors.clear()
            else:
                self._vectors.clear()

            self._prepared = True
            _LOGGER.info(
                "Индексы подбора готовы: %s сертификатов, семантика %s",
                len(self._by_id),
                "включена" if self._vectors.is_ready else "выключена",
            )
            return len(self._by_id)

    def invalidate(self) -> None:
        """Помечает индексы устаревшими (после изменения справочника)."""
        with self._lock:
            self._prepared = False

    # --------------------------------------------------------------- подбор
    def match_row(self, row: OrderRow) -> MatchResult:
        """Подбирает сертификат для одной строки заказа.

        Args:
            row: Строка заказа.

        Returns:
            Результат подбора со списком кандидатов и статусом.
        """
        started = time.perf_counter()
        settings = self._settings.current.matching

        if row.is_empty:
            return MatchResult(
                row=row, status=MatchStatus.SKIPPED, note="Пустая строка", duration_ms=0.0
            )

        if not self._prepared:
            self.prepare()

        context = ScoringContext.create(settings)

        alias_result = self._match_by_alias(row, context)
        if alias_result is not None:
            alias_result.duration_ms = (time.perf_counter() - started) * 1000
            return alias_result

        candidates = self._collect_candidates(row, context, limit=settings.max_candidates)
        result = self._decide(row, candidates)
        result.duration_ms = (time.perf_counter() - started) * 1000
        return result

    def match_rows(
        self, rows: Sequence[OrderRow], *, reporter: ProgressReporter | None = None
    ) -> list[MatchResult]:
        """Подбирает сертификаты для всех строк заказа.

        Подбор выполняется последовательно: индексы уже в памяти, и накладные
        расходы на синхронизацию потоков превысили бы выигрыш.

        Args:
            rows: Строки заказа.
            reporter: Приёмник прогресса.

        Returns:
            Результаты подбора в порядке строк.
        """
        if reporter is not None:
            reporter.start(len(rows), "Подбор сертификатов", "matching")

        results: list[MatchResult] = []
        for index, row in enumerate(rows, start=1):
            results.append(self.match_row(row))
            if reporter is not None:
                reporter.advance(1, f"Обработано {index} из {len(rows)}", "matching")

        if reporter is not None:
            reporter.finish("Подбор завершён", "matching")
        return results

    def find_candidates(
        self, text: str, *, limit: int = 20, include_other_volumes: bool = True
    ) -> list[MatchCandidate]:
        """Ищет кандидатов для произвольного текста.

        Используется окном неоднозначного выбора и строкой поиска: там важно
        показать не только точные попадания, но и соседние фасовки товара.

        Args:
            text: Наименование товара.
            limit: Максимальное количество кандидатов.
            include_other_volumes: Добавлять ли товары с тем же названием,
                но другим объёмом.

        Returns:
            Кандидаты, отсортированные по убыванию оценки.
        """
        if not self._prepared:
            self.prepare()

        settings = self._settings.current.matching
        context = ScoringContext.create(settings)
        row = OrderRow(row_number=0, product_name=text)

        candidates = self._collect_candidates(
            row, context, limit=limit, skip_hard_filter=include_other_volumes
        )

        if include_other_volumes and self._lexical is not None:
            known = {candidate.certificate.id for candidate in candidates}
            for hit in self._lexical.search_by_signature(text, limit=limit):
                if hit.certificate.id in known:
                    continue
                score = score_candidate(
                    row, hit.certificate, lexical=hit.score, semantic=None, context=context
                )
                candidates.append(
                    MatchCandidate(
                        certificate=hit.certificate, score=score, source=MatchSource.LEXICAL
                    )
                )
                known.add(hit.certificate.id)

        candidates.sort(key=_candidate_sort_key, reverse=True)
        for rank, candidate in enumerate(candidates):
            candidate.rank = rank
        return candidates[:limit]

    # ------------------------------------------------------------- этапы
    def _match_by_alias(self, row: OrderRow, context: ScoringContext) -> MatchResult | None:
        """Этап 1: поиск в таблице псевдонимов."""
        if not context.settings.prefer_alias:
            return None

        aliases = self._aliases.find_for_text(row.search_text)
        for alias in aliases:
            if alias.certificate_id is None:
                continue
            certificate = self._by_id.get(alias.certificate_id)
            if certificate is None:
                certificate = self._certificates.get_by_id(alias.certificate_id)
                if certificate is None or not certificate.is_active:
                    continue

            if alias.id is not None:
                self._aliases.register_hit(alias.id)

            breakdown = score_candidate(
                row, certificate, lexical=1.0, semantic=None, context=context
            )
            # Псевдоним — подтверждённое человеком решение: итоговая оценка
            # выставляется в единицу, но детализация сохраняется для отчёта.
            confirmed = ScoreBreakdown(
                name=1.0,
                volume=breakdown.volume,
                expiry=breakdown.expiry,
                total=1.0,
                lexical=1.0,
                semantic=None,
                weights=breakdown.weights,
            )
            candidate = MatchCandidate(
                certificate=certificate, score=confirmed, source=MatchSource.ALIAS
            )
            return MatchResult(
                row=row,
                status=MatchStatus.MATCHED,
                candidates=[candidate],
                selected_index=0,
                alias_applied=True,
                note=f"Применён псевдоним «{alias.source_text}»",
            )
        return None

    def _collect_candidates(
        self,
        row: OrderRow,
        context: ScoringContext,
        *,
        limit: int,
        skip_hard_filter: bool = False,
    ) -> list[MatchCandidate]:
        """Этапы 2–6: сбор, фильтрация и оценка кандидатов."""
        settings = context.settings
        query = row.search_text
        lexical_scores: dict[int, tuple[Certificate, float, MatchSource]] = {}

        # Этап 2 — точное совпадение нормализованного наименования.
        for certificate in self._by_normalized.get(row.normalized_name, ()):
            if certificate.id is not None:
                lexical_scores[certificate.id] = (certificate, 1.0, MatchSource.EXACT)

        # Этап 3 — нечёткий поиск.
        if self._lexical is not None:
            for hit in self._lexical.search(query, limit=settings.fuzzy_prefilter_limit):
                certificate_id = hit.certificate.id
                if certificate_id is None:
                    continue
                existing = lexical_scores.get(certificate_id)
                if existing is None or hit.score > existing[1]:
                    lexical_scores[certificate_id] = (
                        hit.certificate,
                        hit.score,
                        MatchSource.LEXICAL,
                    )

        best_lexical = max((score for _, score, _ in lexical_scores.values()), default=0.0)

        # Этап 4 — семантика, только если лексика неуверена.
        semantic_scores: dict[int, float] = {}
        if (
            settings.use_semantic
            and self._vectors.is_ready
            and best_lexical < settings.semantic_trigger_threshold
        ):
            for semantic_hit in self._vectors.search(query, top_k=settings.fuzzy_prefilter_limit):
                semantic_scores[semantic_hit.certificate_id] = semantic_hit.score
                if semantic_hit.certificate_id not in lexical_scores:
                    semantic_certificate = self._by_id.get(semantic_hit.certificate_id)
                    if semantic_certificate is not None:
                        lexical_scores[semantic_hit.certificate_id] = (
                            semantic_certificate,
                            0.0,
                            MatchSource.SEMANTIC,
                        )
            if lexical_scores and not semantic_scores:
                semantic_scores = self._vectors.score_pairs(query, list(lexical_scores))

        # Этапы 5–6 — оценка объёма и срока, отсев безусловных несоответствий.
        candidates: list[MatchCandidate] = []
        for certificate_id, (certificate, lexical, source) in lexical_scores.items():
            if not skip_hard_filter and is_hard_mismatch(row, certificate, context):
                continue
            semantic = semantic_scores.get(certificate_id)
            breakdown = score_candidate(
                row, certificate, lexical=lexical, semantic=semantic, context=context
            )
            if breakdown.total <= 0.0:
                continue
            if not skip_hard_filter and breakdown.name < settings.min_name_score:
                # Порог наименования: объём и срок не должны «вытягивать»
                # кандидата, у которого попросту другое название товара.
                continue
            effective_source = (
                MatchSource.SEMANTIC
                if semantic is not None and semantic > lexical and source is not MatchSource.EXACT
                else source
            )
            candidates.append(
                MatchCandidate(certificate=certificate, score=breakdown, source=effective_source)
            )

        candidates.sort(key=_candidate_sort_key, reverse=True)
        for rank, candidate in enumerate(candidates):
            candidate.rank = rank
        return candidates[: max(limit, settings.max_candidates)]

    def _decide(self, row: OrderRow, candidates: list[MatchCandidate]) -> MatchResult:
        """Принимает итоговое решение по набору кандидатов."""
        matching = self._settings.current.matching

        if not candidates:
            return MatchResult(
                row=row,
                status=MatchStatus.NOT_FOUND,
                note="Подходящих сертификатов не найдено",
            )

        best = candidates[0]
        if best.total < matching.review_threshold:
            return MatchResult(
                row=row,
                status=MatchStatus.NOT_FOUND,
                candidates=candidates,
                note=f"Лучшее совпадение слишком низкое ({best.percent} %)",
            )

        rivals = [
            candidate
            for candidate in candidates[1:]
            if best.total - candidate.total < matching.ambiguity_margin
        ]

        if rivals and matching.auto_resolve_duplicates and _same_product(best, rivals):
            # Кандидаты различаются только сроком — выбираем ближайший
            # по сроку окончания (FEFO) без обращения к пользователю.
            group = [best, *rivals]
            chosen = min(group, key=lambda item: _expiry_sort_key(item))
            index = candidates.index(chosen)
            return MatchResult(
                row=row,
                status=MatchStatus.MATCHED,
                candidates=candidates,
                selected_index=index,
                note="Выбран сертификат с ближайшим сроком окончания",
            )

        if best.total < matching.auto_accept_threshold or rivals:
            return MatchResult(
                row=row,
                status=MatchStatus.AMBIGUOUS,
                candidates=candidates,
                selected_index=0,
                note=(
                    f"Найдено {len(rivals) + 1} близких варианта — требуется проверка"
                    if rivals
                    else f"Совпадение {best.percent} % ниже порога автоматического принятия"
                ),
            )

        return MatchResult(
            row=row,
            status=MatchStatus.MATCHED,
            candidates=candidates,
            selected_index=0,
        )


def _candidate_sort_key(candidate: MatchCandidate) -> tuple[float, float, float]:
    """Формирует ключ сортировки кандидатов.

    Основной критерий — итоговая оценка. При равенстве предпочтение отдаётся
    кандидату с большей оценкой наименования, затем — с ближайшим сроком.

    Args:
        candidate: Кандидат.

    Returns:
        Кортеж для сортировки по убыванию.
    """
    expiry = candidate.certificate.expiry_date
    proximity = -expiry.toordinal() if expiry is not None else -(10**9)
    return (candidate.score.total, candidate.score.name, proximity)


def _expiry_sort_key(candidate: MatchCandidate) -> tuple[int, int]:
    """Формирует ключ выбора «ближайшего по сроку» кандидата."""
    expiry = candidate.certificate.expiry_date
    if expiry is None:
        return (1, 0)
    return (0, expiry.toordinal())


def _same_product(best: MatchCandidate, rivals: list[MatchCandidate]) -> bool:
    """Проверяет, что кандидаты описывают один и тот же товар.

    Товары считаются одинаковыми, если совпадают нормализованные наименования
    и объёмы: тогда различие сводится к сроку действия, и выбор можно сделать
    автоматически.

    Args:
        best: Лучший кандидат.
        rivals: Близкие по оценке кандидаты.

    Returns:
        ``True``, если все кандидаты — один товар.
    """
    reference_name = best.certificate.normalized_name
    reference_volume = best.certificate.volume
    reference_key = reference_volume.total_base_value if reference_volume else None
    reference_unit = reference_volume.base_unit if reference_volume else ""

    for rival in rivals:
        if rival.certificate.normalized_name != reference_name:
            return False
        volume = rival.certificate.volume
        key = volume.total_base_value if volume else None
        unit = volume.base_unit if volume else ""
        if key != reference_key or unit != reference_unit:
            return False
    return True
