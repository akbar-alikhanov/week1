"""Подбор наиболее подходящего срока годности ДО поиска сертификата.

Новый, полностью самостоятельный этап конвейера обработки заказа: он
выполняется ПЕРЕД существующим алгоритмом подбора сертификата
(:class:`~app.services.matching_service.MatchingService`) и не изменяет, не
переписывает и не заменяет его — только определяет для каждой строки заказа
наиболее подходящий срок годности (если он ещё не указан в самом заказе) и
передаёт готовую строку дальше, в уже существующий, нетронутый подбор.

Источник данных — отдельная от базы сертификатов Excel-таблица «сроков
годности и остатков»: она отвечает на вопрос «какие партии этого товара
сейчас есть на складе и когда у них истекает срок», а не «какой сертификат
подтверждает товар». Одна и та же строка заказа может встречаться в этой
базе много раз — по одной записи на партию/срок.

Этап 2 (объединение нескольких партий): если ни одна партия не покрывает
требуемое количество самостоятельно, разрешается использовать сразу
несколько партий — но только тех, для которых пробным подбором уже
подтверждён сертификат. Физический остаток партии без сертификата в расчёт
доступного количества не входит вообще (доступный остаток такой партии
считается нулевым), поэтому недостающее количество никогда не «добирается»
партиями, которые сертификатом не подтверждены.

Этап 3 (ручной режим): если после проверки ВСЕХ партий не подтверждён
сертификат ни для одной из них (Этап 1 не находит вообще ничего в пределах
``expiry_tolerance_days``), товар не считается автоматически неподходящим —
для каждой проверенной партии подбираются ближайшие по сроку сертификаты
(:meth:`~app.services.matching_service.MatchingService.find_expiry_alternatives`,
без учёта допуска) и предлагаются пользователю на ручное подтверждение
(:class:`ManualExpiryReview`). Подтверждённые пользователем партии передаются в
:meth:`ExpiryResolutionService.apply_manual_selections`, которая направляет
их в ТУ ЖЕ, неизменённую логику объединения (:meth:`_resolve_combination`) —
подтверждённая вручную партия участвует в распределении количества наравне
с партией, подтверждённой автоматически. Если предложить нечего вообще ни
для одной партии, поведение не отличается от того, что было до появления
этого этапа: обычное исключение «нет сертификата».
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from app.config.settings import SettingsService
from app.core.dates import format_date
from app.core.events import ProgressReporter
from app.core.text import normalize
from app.models.certificate_product import CertificateProduct
from app.models.expiry_stock import ExpiryStockEntry
from app.models.matching import BatchAllocation, MatchCandidate, MatchStatus
from app.models.order import OrderRow
from app.repositories.expiry_stock_repository import ExpiryStockRepository
from app.services.matching_service import MatchingService

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ExpiryExclusion:
    """Причина, по которой строка заказа не передаётся в обычный подбор сертификата.

    Attributes:
        note: Пояснение для пользователя (итоговый Excel, отчёт, история).
        not_in_database: Признак того, что товар отсутствует в базе сроков
            годности вообще. Вместе с ``no_certificate_available`` —
            единственные случаи с отдельным визуальным выделением (жёлтая
            заливка и зачёркнутый текст, требования п. 12 и п. 13 Этапа 2).
            Остальные случаи (недостаточно суммарного остатка среди партий
            с сертификатом) получают обычное выделение «не найдено», как и
            любая другая ненайденная строка, без специального форматирования.
        no_certificate_available: Признак того, что товар в базе сроков
            есть, но ни для одной его партии не подтверждён сертификат —
            попытка подбора (ни одной, ни нескольких партий) поэтому не
            имела смысла. Как и ``not_in_database``, требует жёлтой заливки
            и зачёркнутого текста.
    """

    note: str
    not_in_database: bool = False
    no_certificate_available: bool = False


@dataclass(frozen=True, slots=True)
class _BatchCheck:
    """Результат проверки одной партии: остаток, сертификат, доступное количество.

    ``available`` — центральное понятие Этапа 2 (см. докстринг модуля):
    физический остаток партии засчитывается только тогда, когда для неё
    подтверждён сертификат, иначе он равен нулю независимо от того, сколько
    товара физически есть на складе.
    """

    entry: ExpiryStockEntry
    candidate: MatchCandidate | None
    available: float

    @property
    def has_certificate(self) -> bool:
        """Признак того, что для партии подтверждён сертификат."""
        return self.candidate is not None


@dataclass(frozen=True, slots=True)
class ExpirySuggestion:
    """Один вариант сертификата, предложенный вместо результата строгого поиска.

    Строится Этапом 3 (см. докстринг модуля) ТОЛЬКО после того, как Этап 1
    не подтвердил сертификат ни для одной партии товара. Автоматически
    нигде не используется — только для показа пользователю и последующего
    ручного подтверждения (:meth:`ExpiryResolutionService.apply_manual_selections`).

    Attributes:
        candidate: Кандидат-сертификат (наименование и объём уже
            подтверждены — не хватает только срока в пределах допуска).
        difference_days: Расхождение в днях между сроком сертификата и
            сроком партии, для которой предложен этот вариант.
    """

    candidate: MatchCandidate
    difference_days: int

    @property
    def certificate(self) -> CertificateProduct:
        """Сертификат-кандидат."""
        return self.candidate.certificate


@dataclass(frozen=True, slots=True)
class BatchSuggestions:
    """Партия, для которой Этап 1 не подтвердил сертификат — с вариантами.

    Attributes:
        entry: Партия из базы сроков годности и остатков.
        suggestions: Ближайшие по сроку варианты, отсортированные по
            возрастанию расхождения в днях. Пустой список — для товара и
            объёма этой партии в базе сертификатов вообще ничего не
            нашлось, предложить пользователю нечего.
    """

    entry: ExpiryStockEntry
    suggestions: list[ExpirySuggestion]


@dataclass(frozen=True, slots=True)
class ManualExpiryReview:
    """Строка заказа, ожидающая ручного подтверждения сертификата для партий.

    Строится вместо :class:`ExpiryExclusion` (``no_certificate_available``)
    ТОЛЬКО когда хотя бы у одной проверенной партии есть хотя бы один
    вариант для предложения — иначе (предложить нечего вообще) поведение не
    отличается от прежнего: возвращается обычное исключение.

    Attributes:
        row: Строка заказа.
        required_quantity: Требуемое количество.
        batches: Партии, проверенные на Этапе 1, в том же порядке (от новой
            к старой) — по одной записи на партию независимо от того, есть
            ли у неё варианты.
    """

    row: OrderRow
    required_quantity: float
    batches: list[BatchSuggestions]


class ExpiryResolutionService:
    """Подбирает срок годности для строк заказа перед поиском сертификата.

    Если база сроков годности не настроена (ни разу не импортирована —
    пустая таблица), сервис не делает вообще ничего: ни одна строка не
    исключается и не изменяется. Это осознанное решение: новая функция
    должна быть полностью незаметна для тех, кто её не настроил, и не
    менять поведение приложения по умолчанию.
    """

    def __init__(
        self,
        expiry_repository: ExpiryStockRepository,
        matching_service: MatchingService,
        settings_service: SettingsService,
    ) -> None:
        """Создаёт сервис подбора срока годности.

        Args:
            expiry_repository: База сроков годности и остатков (индекс над Excel).
            matching_service: Существующий, неизменяемый сервис подбора
                сертификата — используется только для пробных вызовов
                ``match_row`` при проверке «найдётся ли сертификат на этот
                срок», без единой правки в самом сервисе, и (Этап 3) для
                поиска ближайших вариантов в обход допуска.
            settings_service: Источник параметров — сейчас используется
                только ``expiry_stock.max_manual_suggestions`` (сколько
                вариантов предлагать на партию в ручном режиме).
        """
        self._stock = expiry_repository
        self._matching = matching_service
        self._settings = settings_service

    def resolve_rows(
        self, rows: Sequence[OrderRow], *, reporter: ProgressReporter | None = None
    ) -> tuple[
        dict[int, ExpiryExclusion],
        dict[int, list[BatchAllocation]],
        dict[int, ManualExpiryReview],
    ]:
        """Подбирает срок годности (или комбинацию партий) для каждой строки заказа.

        Строкам, для которых подходящий срок найден одной партией (или у
        которых он уже был указан в заказе), метод ничего дополнительно не
        сообщает — ``row.requested_expiry`` уже мутирован на месте, и дальше
        строка идёт в обычный, неизменённый подбор сертификата.

        Args:
            rows: Строки заказа.
            reporter: Приёмник прогресса (пробные подборы на больших
                заказах небыстры).

        Returns:
            Тройка словарей, все ключом — номер строки заказа:

            * «строка → причина исключения» для строк, которые не должны
              передаваться в обычный подбор сертификата вообще (товара нет
              в базе, ни для одной партии нет сертификата и предложить
              нечего, либо суммарного подтверждённого остатка недостаточно);
            * «строка → распределение по партиям» для строк, выполненных
              несколькими сроками годности сразу (Этап 2) — такие строки
              тоже не должны передаваться в обычный подбор: сертификаты для
              них уже найдены здесь, по каждой партии отдельно;
            * «строка → обзор партий с предложениями» (Этап 3) для строк,
              ожидающих ручного подтверждения — см. :class:`ManualExpiryReview`.

            Все словари пустые, если база сроков годности не настроена или
            все строки успешно прошли этап одной партией (или уже имели
            указанный срок).
        """
        if self._stock.count() == 0:
            return {}, {}, {}

        if reporter is not None:
            reporter.start(len(rows), "Подбор срока годности…", "expiry")

        excluded: dict[int, ExpiryExclusion] = {}
        combined: dict[int, list[BatchAllocation]] = {}
        pending_review: dict[int, ManualExpiryReview] = {}
        for index, row in enumerate(rows, start=1):
            outcome = self._resolve_row(row)
            if isinstance(outcome, ExpiryExclusion):
                excluded[row.row_number] = outcome
            elif isinstance(outcome, ManualExpiryReview):
                pending_review[row.row_number] = outcome
            elif isinstance(outcome, list):
                combined[row.row_number] = outcome
            if reporter is not None:
                reporter.advance(1, f"Обработано {index} из {len(rows)}", "expiry")

        if reporter is not None:
            reporter.finish("Подбор срока годности завершён", "expiry")
        return excluded, combined, pending_review

    def apply_manual_selections(
        self, review: ManualExpiryReview, choices: dict[int, ExpirySuggestion]
    ) -> ExpiryExclusion | list[BatchAllocation]:
        """Строит распределение по партиям, подтверждённым пользователем вручную.

        Партии без подтверждения (нет записи в ``choices``) считаются не
        имеющими сертификата — то же правило «нет сертификата → доступно
        ноль», что и при автоматическом объединении партий (см. докстринг
        модуля). Дальнейшая проверка суммарного остатка и распределение —
        существующая, неизменённая логика :meth:`_resolve_combination`: она
        не отличает вручную подтверждённую партию от партии, подтверждённой
        автоматически, — обе просто ``_BatchCheck`` с сертификатом.

        Ни выбор пользователя, ни его отсутствие никогда не создаёт и не
        изменяет запись в словаре соответствий — это отдельное, разовое
        подтверждение конкретного сертификата для конкретной партии.

        Args:
            review: Обзор партий с предложенными вариантами (получен из
                третьего словаря :meth:`resolve_rows`).
            choices: Выбор пользователя — индекс партии в ``review.batches``
                → подтверждённый вариант. Партии, для которых пользователь
                не подтвердил вариант, в словаре отсутствуют.

        Returns:
            Распределение по партиям либо причина, по которой выполнить
            заказ не удалось — как и в автоматическом Этапе 2.
        """
        checks = [
            _BatchCheck(
                entry=batch.entry,
                candidate=choices[index].candidate if index in choices else None,
                available=batch.entry.quantity if index in choices else 0.0,
            )
            for index, batch in enumerate(review.batches)
        ]
        outcome = self._resolve_combination(
            review.row, review.required_quantity, checks, allow_manual_review=False
        )
        assert isinstance(outcome, (ExpiryExclusion, list))  # allow_manual_review=False гарантирует
        return outcome

    # ------------------------------------------------------------- строка
    def _resolve_row(
        self, row: OrderRow
    ) -> ExpiryExclusion | list[BatchAllocation] | ManualExpiryReview | None:
        """Определяет срок годности (или комбинацию партий) для одной строки заказа.

        Реализует алгоритм требования пошагово:

        1. Найти все партии товара в базе сроков (точное совпадение полного
           системного названия).
        2. Отсортировать от самого нового срока к самому старому.
        3. Для КАЖДОЙ партии по очереди — пробным вызовом существующего
           ``MatchingService.match_row`` проверить, подтверждается ли для
           неё сертификат; доступное количество партии равно её остатку,
           если сертификат подтверждён, и нулю, если нет (см. докстринг
           модуля). Партия, чьего ОДНОГО доступного количества хватает на
           весь заказ, используется сразу — Этап 1, поведение не отличается
           от того, что было до появления Этапа 2.
        4. Если ни одна партия по отдельности не покрыла заказ — Этап 2:
           просуммировать доступное количество партий с сертификатом; если
           достаточно — распределить требуемое количество между ними
           (жадно, от самой новой партии к самой старой, максимум возможного
           из каждой), иначе — сообщить о нехватке.
        5. Если сертификат не подтверждён НИ ДЛЯ ОДНОЙ партии вообще — Этап 3:
           предложить пользователю ближайшие варианты на ручное
           подтверждение вместо немедленного отказа (см. докстринг модуля).

        Args:
            row: Строка заказа (мутируется при успехе одной партией).

        Returns:
            ``None`` — строку можно передавать в обычный подбор как обычно
            (либо срок уже был в заказе, либо Этап 1 подобрал его одной
            партией); список :class:`BatchAllocation` — строка выполнена
            комбинацией нескольких партий (Этап 2), сертификаты для неё уже
            найдены; :class:`ManualExpiryReview` — строка ожидает ручного
            подтверждения (Этап 3); :class:`ExpiryExclusion` — строку
            выполнить не удалось (и предложить нечего).
        """
        if row.requested_expiry is not None:
            # Заказ уже указывает требуемый срок — это осознанный выбор
            # человека, новый этап его не переопределяет и не проверяет.
            return None

        entries = self._stock.find_by_product_name(normalize(row.product_name))
        if not entries:
            exclusion = ExpiryExclusion(
                note="Товар отсутствует в базе сроков.", not_in_database=True
            )
            _LOGGER.debug("Товар «%s» отсутствует в базе сроков годности", row.product_name)
            return exclusion

        newest_first = sorted(
            entries, key=lambda entry: entry.expiry_date or date.min, reverse=True
        )
        required_quantity = row.quantity or 0.0

        # Шаг 1: проверка сертификата для каждой партии по очереди — если
        # какая-то одна партия покрывает заказ целиком, останавливаемся
        # сразу (Этап 1, эффективность и результат как раньше). Если нет —
        # к моменту исчерпания партий уже накоплены проверенные данные по
        # всем им, ровно то, что нужно Этапу 2 для комбинации.
        checks: list[_BatchCheck] = []
        for entry in newest_first:
            row.requested_expiry = entry.expiry_date
            trial = self._matching.match_row(row)
            candidate = trial.selected if trial.status is MatchStatus.MATCHED else None
            available = entry.quantity if candidate is not None else 0.0
            checks.append(_BatchCheck(entry=entry, candidate=candidate, available=available))

            if candidate is not None and available >= required_quantity:
                _LOGGER.debug(
                    "Срок годности подобран для «%s»: %s (одна партия)",
                    row.product_name,
                    entry.expiry_date,
                )
                self._log_diagnostics(row, required_quantity, checks, outcome="одна партия")
                return None
            row.requested_expiry = None

        return self._resolve_combination(row, required_quantity, checks)

    def _resolve_combination(
        self,
        row: OrderRow,
        required_quantity: float,
        checks: list[_BatchCheck],
        *,
        allow_manual_review: bool = True,
    ) -> ExpiryExclusion | list[BatchAllocation] | ManualExpiryReview:
        """Этап 2: пытается покрыть заказ комбинацией нескольких партий.

        Args:
            row: Строка заказа.
            required_quantity: Требуемое количество.
            checks: Результаты проверки всех партий товара (см. :meth:`_resolve_row`).
            allow_manual_review: Разрешить ли предложить Этап 3 (ручные
                варианты), если сертификат не подтверждён ни для одной
                партии. ``False`` — используется только
                :meth:`apply_manual_selections`, чтобы после уже
                применённого ручного выбора не строить новое предложение
                вместо окончательного результата.

        Returns:
            Распределение по партиям; обзор для ручного подтверждения
            (Этап 3, только если ``allow_manual_review``); либо причина, по
            которой выполнить заказ не удалось.
        """
        certified = [check for check in checks if check.has_certificate]

        if not certified:
            if allow_manual_review:
                review = self._build_manual_review(row, required_quantity, checks)
                if review is not None:
                    self._log_diagnostics(
                        row, required_quantity, checks, outcome="ожидает ручного подтверждения"
                    )
                    return review
            exclusion = ExpiryExclusion(
                note="Для доступных сроков не найден подходящий сертификат.",
                no_certificate_available=True,
            )
            self._log_diagnostics(row, required_quantity, checks, outcome=exclusion.note)
            return exclusion

        total_available = sum(check.available for check in certified)
        if total_available < required_quantity:
            exclusion = ExpiryExclusion(
                note="Недостаточно остатка по партиям с подходящими сертификатами."
            )
            self._log_diagnostics(row, required_quantity, checks, outcome=exclusion.note)
            return exclusion

        allocations = self._allocate(certified, required_quantity)
        _LOGGER.debug(
            "Заказ «%s» выполнен комбинацией из %s партий",
            row.product_name,
            len(allocations),
        )
        self._log_diagnostics(
            row, required_quantity, checks, outcome="комбинация партий", allocations=allocations
        )
        return allocations

    def _build_manual_review(
        self, row: OrderRow, required_quantity: float, checks: list[_BatchCheck]
    ) -> ManualExpiryReview | None:
        """Этап 3: подбирает ближайшие варианты для партий без сертификата.

        Вызывается только когда сертификат не подтверждён НИ ДЛЯ ОДНОЙ
        партии (см. :meth:`_resolve_combination`). Для каждой партии ищет
        ближайшие по сроку сертификаты в обход допуска
        (:meth:`~app.services.matching_service.MatchingService.find_expiry_alternatives`)
        — тем же наименованием, объёмом и словарём, что и обычный подбор.

        Args:
            row: Строка заказа.
            required_quantity: Требуемое количество.
            checks: Результаты проверки всех партий товара (сертификат не
                подтверждён ни для одной).

        Returns:
            Обзор с предложениями либо ``None``, если предложить нечего ни
            для одной партии — тогда вызывающая сторона возвращает обычное
            исключение, как и до появления этого этапа.
        """
        limit = self._settings.current.expiry_stock.max_manual_suggestions
        batches: list[BatchSuggestions] = []
        has_suggestions = False
        for check in checks:
            batch_expiry = check.entry.expiry_date
            if batch_expiry is None:
                batches.append(BatchSuggestions(entry=check.entry, suggestions=[]))
                continue

            alternatives = self._matching.find_expiry_alternatives(row, batch_expiry, limit=limit)
            suggestions: list[ExpirySuggestion] = []
            for candidate in alternatives:
                certificate_expiry = candidate.certificate.expiry_date
                if certificate_expiry is None:
                    continue
                suggestions.append(
                    ExpirySuggestion(
                        candidate=candidate,
                        difference_days=abs((certificate_expiry - batch_expiry).days),
                    )
                )
            if suggestions:
                has_suggestions = True
            batches.append(BatchSuggestions(entry=check.entry, suggestions=suggestions))

        if not has_suggestions:
            return None
        return ManualExpiryReview(row=row, required_quantity=required_quantity, batches=batches)

    def _allocate(
        self, certified: list[_BatchCheck], required_quantity: float
    ) -> list[BatchAllocation]:
        """Жадно распределяет требуемое количество по партиям от новой к старой.

        Условие вызова — суммарного доступного остатка партий с
        сертификатом достаточно (проверено в :meth:`_resolve_combination`).
        Из каждой партии (начиная с самой новой) берётся максимум
        возможного — ровно столько, сколько ещё недостаёт до требуемого
        количества, — что одновременно минимизирует число использованных
        партий, предпочитает более свежие сроки и не расходует лишний
        остаток сверх необходимого (правила приоритета требования).

        Args:
            certified: Партии с подтверждённым сертификатом, отсортированные
                от новой к старой.
            required_quantity: Требуемое количество.

        Returns:
            Партии с распределённым по ним количеством, в порядке
            использования (от новой к старой).
        """
        allocations: list[BatchAllocation] = []
        remaining = required_quantity
        for check in certified:
            if remaining <= 0:
                break
            if check.candidate is None or check.available <= 0:
                continue
            take = min(remaining, check.available)
            allocations.append(
                BatchAllocation(
                    candidate=check.candidate, quantity=take, expiry_date=check.entry.expiry_date
                )
            )
            remaining -= take
        return allocations

    # ------------------------------------------------------------ журнал
    def _log_diagnostics(
        self,
        row: OrderRow,
        required_quantity: float,
        checks: list[_BatchCheck],
        *,
        outcome: str,
        allocations: list[BatchAllocation] | None = None,
    ) -> None:
        """Записывает в журнал полную раскладку подбора партий по товару.

        Формат соответствует требованию — по каждой партии остаток, статус
        сертификата, доступное количество; далее суммарный доступный
        остаток, выбранное распределение (если есть) и итог. Уровень
        DEBUG — сообщение многострочное и на больших заказах многочисленное.
        """
        if not _LOGGER.isEnabledFor(logging.DEBUG):
            return

        lines = [f"Товар: {row.product_name}", f"Требуется: {_format_quantity(required_quantity)}"]
        for position, check in enumerate(checks, start=1):
            certificate_status = "найден" if check.has_certificate else "не найден"
            lines.append(
                f"Партия {position}: {format_date(check.entry.expiry_date)} · "
                f"остаток {_format_quantity(check.entry.quantity)} · "
                f"сертификат {certificate_status} · "
                f"доступно {_format_quantity(check.available)}"
            )
        total_available = sum(check.available for check in checks)
        lines.append(f"Суммарный доступный остаток: {_format_quantity(total_available)}")
        if allocations:
            distribution = ", ".join(
                f"{_format_quantity(allocation.quantity)} → {format_date(allocation.expiry_date)}"
                for allocation in allocations
            )
            lines.append(f"Распределение: {distribution}")
        lines.append(f"Результат: {outcome}")
        _LOGGER.debug("\n".join(lines))


def _format_quantity(value: float) -> str:
    """Форматирует количество для журнала и Excel без лишних нулей после запятой."""
    return f"{value:g}"
