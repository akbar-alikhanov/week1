"""Многоэтапный подбор сертификата для строки заказа.

Единственный источник данных о сертификатах — Excel-база, проиндексированная
в SQLite (:class:`~app.repositories.certificate_product_repository.CertificateProductRepository`).
PDF в подборе не участвуют вообще: они находятся по номеру сертификата и
копируются в результат позже, отдельным шагом
(:class:`~app.services.certificate_copy_service.CertificateCopyService`).

Конвейер (порядок этапов задан требованиями и не подлежит изменению без
пересмотра ожиданий пользователя):

1. **Псевдонимы.** Словарь соответствий — абсолютный источник истины, а не
   ещё один канал оценки. Если системное наименование заказа найдено в
   словаре, все остальные этапы (2–4) для этой строки не выполняются:
   ни нечёткий, ни семантический поиск, никакая оценка по процентам —
   наименование и объём берутся из самой записи словаря, и по ним
   выполняется строгий поиск в SQLite (``normalized_name`` + ``volume_ml``);
   из найденных строк базы выбирается только ближайшая по сроку годности.
   Единственное исключение: если официальный товар из словаря сейчас
   отсутствует в базе (Excel изменился, товар переименован/удалён), строка
   не считается ненайденной сразу — разрешается одна повторная попытка через
   обычный конвейер (этапы 2–4), а результат помечается ``alias_stale`` как
   сигнал «словарь стоит обновить».
2. **Точное совпадение** нормализованных наименований.
3. **Нечёткий поиск** (RapidFuzz) — основной источник кандидатов.
4. **Семантический поиск** (Sentence Transformers) — подключается, когда
   лексика неуверена, и находит совпадения без общих букв.
5. **Сравнение объёма.**
6. **Сравнение срока** и выбор ближайшего по сроку из равных кандидатов.

Итоговая оценка (для этапов 2–6) — взвешенная сумма трёх составляющих
(50/30/20 по умолчанию); этап псевдонимов в этой оценке не участвует.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Sequence
from datetime import date

from app.ai.embeddings import EmbeddingBackend
from app.ai.fuzzy import LexicalIndex
from app.ai.scorer import ScoringContext, is_hard_mismatch, score_candidate
from app.ai.vector_index import VectorIndex
from app.config.settings import SettingsService
from app.core.events import ProgressReporter
from app.core.text import normalize
from app.models.alias import Alias
from app.models.certificate_product import CertificateProduct
from app.models.matching import (
    MatchCandidate,
    MatchResult,
    MatchSource,
    MatchStatus,
    ScoreBreakdown,
)
from app.models.order import OrderRow
from app.repositories.alias_repository import AliasRepository
from app.repositories.certificate_product_repository import CertificateProductRepository

_LOGGER = logging.getLogger(__name__)


class MatchingService:
    """Подбирает сертификаты для позиций заказа.

    Сервис держит в памяти подготовленные индексы справочника. Метод
    :meth:`prepare` вызывается один раз перед обработкой заказа, после чего
    :meth:`match_row` отрабатывает за доли миллисекунды.
    """

    def __init__(
        self,
        certificate_repository: CertificateProductRepository,
        alias_repository: AliasRepository,
        settings_service: SettingsService,
        embedding_backend: EmbeddingBackend,
        vector_index: VectorIndex,
    ) -> None:
        """Создаёт сервис подбора.

        Args:
            certificate_repository: Доступ к базе сертификатов (индекс над Excel).
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
        self._by_id: dict[int, CertificateProduct] = {}
        self._by_normalized: dict[str, list[CertificateProduct]] = {}
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
        """Загружает базу сертификатов и строит индексы поиска.

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
            certificates = self._certificates.list_all()

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
        """Помечает индексы устаревшими (после переимпорта базы)."""
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

    def find_expiry_alternatives(
        self, row: OrderRow, batch_expiry: date, *, limit: int
    ) -> list[MatchCandidate]:
        """Ищет ближайшие по сроку сертификаты в обход допуска ``expiry_tolerance_days``.

        Второй (ручной) этап подбора срока годности
        (:class:`~app.services.expiry_resolution_service.ExpiryResolutionService`)
        вызывает этот метод ТОЛЬКО после того, как обычный строгий подбор не
        подтвердил сертификат ни для одной партии товара. Название и объём
        разрешаются точно так же, как в обычном подборе — тем же словарём,
        если для товара есть запись (строгим SQL-поиском по официальному
        наименованию и объёму), иначе тем же нечётким/семантическим поиском
        и тем же порогом ``min_name_score``. Меняется только срок: жёсткое
        исключение по допуску (:func:`~app.ai.scorer.is_hard_mismatch`) не
        применяется, а результат сортируется по абсолютной разнице в днях от
        ``batch_expiry``, а не по взвешенной оценке.

        Метод ничего не решает и не выбирает сам — результат предназначен
        только для показа пользователю и ручного подтверждения; ни один из
        возвращённых кандидатов не должен использоваться автоматически.

        Args:
            row: Строка заказа (используется её наименование/словарь; срок,
                уже записанный в самой строке, не участвует — сравнение
                идёт с ``batch_expiry``).
            batch_expiry: Срок годности партии, для которой ищутся варианты.
            limit: Максимальное количество вариантов в результате.

        Returns:
            Кандидаты в порядке возрастания расхождения в днях от
            ``batch_expiry`` с источником :attr:`~app.models.matching.MatchSource.MANUAL`
            (независимо от того, чем изначально был разрешён товар) — ни
            один из них не мог бы появиться в результате обычного
            автоматического подбора. Кандидаты без известного срока
            сертификата не включаются — сравнивать не с чем.
        """
        if not self._prepared:
            self.prepare()

        settings = self._settings.current.matching
        context = ScoringContext.create(settings)

        original_expiry = row.requested_expiry
        row.requested_expiry = batch_expiry
        try:
            candidates = self._alias_expiry_alternatives(row, context)
            if candidates is None:
                candidates = self._collect_candidates(
                    row,
                    context,
                    limit=max(limit * 5, settings.max_candidates),
                    ignore_expiry_tolerance=True,
                )
        finally:
            row.requested_expiry = original_expiry

        # Источник переопределяется безусловно, независимо от того, как был
        # разрешён товар (словарь/точное совпадение/нечёткий/семантический
        # поиск): в отличие от обычного конвейера, ни один из этих
        # кандидатов не мог бы появиться в автоматическом решении — они
        # существуют только благодаря снятому допуску по сроку, поэтому
        # источник честно отражает это как «ручной выбор», а не как то,
        # что могло бы сойти за обычный автоматический результат.
        for candidate in candidates:
            candidate.source = MatchSource.MANUAL

        dated = [
            candidate for candidate in candidates if candidate.certificate.expiry_date is not None
        ]
        dated.sort(
            key=lambda candidate: abs((candidate.certificate.expiry_date - batch_expiry).days)  # type: ignore[operator]
        )
        return dated[:limit]

    def _alias_expiry_alternatives(
        self, row: OrderRow, context: ScoringContext
    ) -> list[MatchCandidate] | None:
        """Кандидаты по официальному названию из словаря, без допуска по сроку.

        Вспомогательный метод :meth:`find_expiry_alternatives`. Возвращает
        ``None``, если для товара нет записи в словаре — тогда вызывающая
        сторона переходит к обычному конвейеру (нечёткий/семантический
        поиск). Пустой список — запись в словаре есть, но строгий поиск по
        (наименование, объём) не нашёл в базе ни одной строки.

        Args:
            row: Строка заказа (``row.requested_expiry`` уже установлен
                вызывающей стороной на дату партии).
            context: Общий контекст оценки.

        Returns:
            Кандидаты либо ``None``, если словарь для товара пуст.
        """
        if not context.settings.prefer_alias:
            return None
        aliases = self._aliases.find_for_text(row.search_text)
        if not aliases:
            return None

        alias = aliases[0]
        normalized_target = alias.normalized_target
        if not normalized_target:
            return []

        certificates = self._certificates.find_strict(normalized_target, alias.volume_ml)
        if context.settings.require_valid_expiry:
            certificates = [
                certificate
                for certificate in certificates
                if certificate.expiry_date is None
                or certificate.expiry_date >= context.reference_date
            ]
        return [
            MatchCandidate(
                certificate=certificate,
                score=score_candidate(
                    row, certificate, lexical=1.0, semantic=None, context=context
                ),
                source=MatchSource.MANUAL,
            )
            for certificate in certificates
        ]

    # ------------------------------------------------------------- этапы
    def _match_by_alias(self, row: OrderRow, context: ScoringContext) -> MatchResult | None:
        """Этап 1: словарь соответствий — абсолютный источник истины.

        Если системное наименование заказа найдено в словаре, весь остальной
        подбор для этой строки не выполняется: ни RapidFuzz, ни Sentence
        Transformers, ни какая-либо оценка «по процентам» не участвуют.
        Наименование и объём берутся из самой записи словаря, и по ним
        выполняется строгий SQL-поиск в базе сертификатов
        (:meth:`~app.repositories.certificate_product_repository.CertificateProductRepository.find_strict`)
        — точное равенство, без допуска и без нечёткого/семантического
        поиска. Среди найденных таким образом строк сравнивается только срок
        годности: выбирается тот, что ближе всего к требуемой дате заказа.

        Если в заказе указан требуемый срок годности, из найденных по
        словарю строк дополнительно исключаются те, чей срок отличается от
        требуемого больше чем на ``expiry_tolerance_days`` (в любую сторону,
        год учитывается — сравниваются полные даты) — так же безусловно,
        как это делает :func:`~app.ai.scorer.is_hard_mismatch` для обычного
        конвейера (см. :meth:`_collect_candidates`). Строка базы за
        пределами допуска не может быть выбрана «как ближайшая из
        неподходящих» ни здесь, ни там.

        Если запись словаря для товара есть, а строгий поиск (или последующая
        фильтрация по валидности и допуску срока) не оставил ни одной строки
        базы — сам официальный товар из словаря сейчас либо отсутствует в
        базе (Excel изменился), либо ни одна его партия не подходит по сроку,
        а не то, что подбор ошибся в объёме. В этом единственном случае
        разрешена одна повторная попытка через обычный конвейер
        (:meth:`_fallback_after_stale_alias`) — так позиция заказа не
        остаётся без результата только из-за того, что словарь отстал от
        текущей базы; сам обычный конвейер применит тот же допуск по сроку
        независимо, так что подходящий по названию, но неподходящий по сроку
        сертификат не проскочит и через него.

        Args:
            row: Строка заказа.
            context: Общий контекст оценки.

        Returns:
            Результат подбора либо ``None``, если для строки нет записи в
            словаре — тогда управление переходит к обычному конвейеру
            (:meth:`_collect_candidates`).
        """
        if not context.settings.prefer_alias:
            return None

        aliases = self._aliases.find_for_text(row.search_text)
        if not aliases:
            return None

        alias = aliases[0]
        if alias.id is not None:
            self._aliases.register_hit(alias.id)

        normalized_target = alias.normalized_target
        if not normalized_target:
            return MatchResult(
                row=row,
                status=MatchStatus.NOT_FOUND,
                alias_applied=True,
                note=f"В словаре нет русского названия для «{alias.source_text}»",
            )

        settings = context.settings
        certificates = self._certificates.find_strict(normalized_target, alias.volume_ml)
        if settings.require_valid_expiry:
            certificates = [
                certificate
                for certificate in certificates
                if certificate.expiry_date is None
                or certificate.expiry_date >= context.reference_date
            ]
        if row.requested_expiry is not None:
            # Тот же жёсткий допуск, что и в is_hard_mismatch() обычного
            # конвейера: строка базы за пределами expiry_tolerance_days —
            # не кандидат вообще, а не «менее подходящий вариант».
            certificates = [
                certificate
                for certificate in certificates
                if certificate.expiry_date is None
                or abs((certificate.expiry_date - row.requested_expiry).days)
                <= settings.expiry_tolerance_days
            ]

        if not certificates:
            return self._fallback_after_stale_alias(row, alias, context)

        certificate = _closest_by_expiry(certificates, row.requested_expiry)
        breakdown = score_candidate(row, certificate, lexical=1.0, semantic=None, context=context)
        name_weight, volume_weight, expiry_weight = breakdown.weights
        # Наименование и объём уже подтверждены точным совпадением со
        # словарём — единственная честная составляющая оценки здесь
        # (для отчёта, не для выбора) — срок годности.
        confirmed = ScoreBreakdown(
            name=1.0,
            volume=1.0,
            expiry=breakdown.expiry,
            total=name_weight + volume_weight + breakdown.expiry * expiry_weight,
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

    def _fallback_after_stale_alias(
        self, row: OrderRow, alias: Alias, context: ScoringContext
    ) -> MatchResult:
        """Запасной шаг: официальный товар из словаря пропал из базы.

        Единственный случай, когда после срабатывания словаря разрешён
        обычный конвейер подбора (RapidFuzz/Sentence Transformers) — словарь
        при этом не игнорируется, а помечается устаревшим (``alias_stale``),
        чтобы интерфейс предложил пользователю обновить запись на актуальный
        товар, а не просто молча подменил решение человека своим.

        Args:
            row: Строка заказа.
            alias: Псевдоним, чей официальный товар не найден в базе.
            context: Общий контекст оценки.

        Returns:
            Результат обычного конвейера подбора с ``alias_stale=True``.
        """
        candidates = self._collect_candidates(row, context, limit=context.settings.max_candidates)
        result = self._decide(row, candidates)
        result.alias_stale = True

        detail = alias.target_name
        if alias.volume_label:
            detail += f", {alias.volume_label}"
        if result.status.is_resolved:
            result.note = (
                f"Товар из словаря «{detail}» не найден в базе — сработал резервный поиск. "
                "Обновить словарь?"
            )
        else:
            result.note = (
                f"Товар из словаря «{detail}» не найден в базе; резервный поиск тоже не помог"
            )
        return result

    def _collect_candidates(
        self,
        row: OrderRow,
        context: ScoringContext,
        *,
        limit: int,
        skip_hard_filter: bool = False,
        ignore_expiry_tolerance: bool = False,
    ) -> list[MatchCandidate]:
        """Этапы 2–6: сбор, фильтрация и оценка кандидатов."""
        settings = context.settings
        query = row.search_text
        lexical_scores: dict[int, tuple[CertificateProduct, float, MatchSource]] = {}

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
            if not skip_hard_filter and is_hard_mismatch(
                row, certificate, context, ignore_expiry_tolerance=ignore_expiry_tolerance
            ):
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


def _closest_by_expiry(
    certificates: list[CertificateProduct], requested: date | None
) -> CertificateProduct:
    """Выбирает строку базы с ближайшим сроком годности среди совпавших по словарю.

    С требуемым сроком заказа — минимизирует абсолютную разницу в днях. Без
    него действует FEFO (first expired, first out): выбирается сертификат,
    истекающий раньше остальных, — расходуется первым, как и везде в
    конвейере подбора. Строки без распознанного срока считаются наименее
    подходящими и рассматриваются в последнюю очередь.

    Args:
        certificates: Строки базы, уже прошедшие строгий отбор по словарю
            (непустой список).
        requested: Требуемый срок из строки заказа (может отсутствовать).

    Returns:
        Единственная выбранная строка базы сертификатов.
    """
    if requested is not None:
        return min(
            certificates,
            key=lambda c: (
                (1, 0) if c.expiry_date is None else (0, abs((c.expiry_date - requested).days))
            ),
        )
    return min(
        certificates,
        key=lambda c: (1, 0) if c.expiry_date is None else (0, c.expiry_date.toordinal()),
    )


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
