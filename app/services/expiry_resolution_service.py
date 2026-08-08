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
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from app.core.dates import format_date
from app.core.events import ProgressReporter
from app.core.text import normalize
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


class ExpiryResolutionService:
    """Подбирает срок годности для строк заказа перед поиском сертификата.

    Если база сроков годности не настроена (ни разу не импортирована —
    пустая таблица), сервис не делает вообще ничего: ни одна строка не
    исключается и не изменяется. Это осознанное решение: новая функция
    должна быть полностью незаметна для тех, кто её не настроил, и не
    менять поведение приложения по умолчанию.
    """

    def __init__(
        self, expiry_repository: ExpiryStockRepository, matching_service: MatchingService
    ) -> None:
        """Создаёт сервис подбора срока годности.

        Args:
            expiry_repository: База сроков годности и остатков (индекс над Excel).
            matching_service: Существующий, неизменяемый сервис подбора
                сертификата — используется только для пробных вызовов
                ``match_row`` при проверке «найдётся ли сертификат на этот
                срок», без единой правки в самом сервисе.
        """
        self._stock = expiry_repository
        self._matching = matching_service

    def resolve_rows(
        self, rows: Sequence[OrderRow], *, reporter: ProgressReporter | None = None
    ) -> tuple[dict[int, ExpiryExclusion], dict[int, list[BatchAllocation]]]:
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
            Пара словарей, оба ключом — номер строки заказа:

            * «строка → причина исключения» для строк, которые не должны
              передаваться в обычный подбор сертификата вообще (товара нет
              в базе, ни для одной партии нет сертификата, либо суммарного
              подтверждённого остатка недостаточно);
            * «строка → распределение по партиям» для строк, выполненных
              несколькими сроками годности сразу (Этап 2) — такие строки
              тоже не должны передаваться в обычный подбор: сертификаты для
              них уже найдены здесь, по каждой партии отдельно.

            Оба словаря пустые, если база сроков годности не настроена или
            все строки успешно прошли этап одной партией (или уже имели
            указанный срок).
        """
        if self._stock.count() == 0:
            return {}, {}

        if reporter is not None:
            reporter.start(len(rows), "Подбор срока годности…", "expiry")

        excluded: dict[int, ExpiryExclusion] = {}
        combined: dict[int, list[BatchAllocation]] = {}
        for index, row in enumerate(rows, start=1):
            outcome = self._resolve_row(row)
            if isinstance(outcome, ExpiryExclusion):
                excluded[row.row_number] = outcome
            elif isinstance(outcome, list):
                combined[row.row_number] = outcome
            if reporter is not None:
                reporter.advance(1, f"Обработано {index} из {len(rows)}", "expiry")

        if reporter is not None:
            reporter.finish("Подбор срока годности завершён", "expiry")
        return excluded, combined

    # ------------------------------------------------------------- строка
    def _resolve_row(self, row: OrderRow) -> ExpiryExclusion | list[BatchAllocation] | None:
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

        Args:
            row: Строка заказа (мутируется при успехе одной партией).

        Returns:
            ``None`` — строку можно передавать в обычный подбор как обычно
            (либо срок уже был в заказе, либо Этап 1 подобрал его одной
            партией); список :class:`BatchAllocation` — строка выполнена
            комбинацией нескольких партий (Этап 2), сертификаты для неё уже
            найдены; :class:`ExpiryExclusion` — строку выполнить не удалось.
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
        self, row: OrderRow, required_quantity: float, checks: list[_BatchCheck]
    ) -> ExpiryExclusion | list[BatchAllocation]:
        """Этап 2: пытается покрыть заказ комбинацией нескольких партий.

        Args:
            row: Строка заказа.
            required_quantity: Требуемое количество.
            checks: Результаты проверки всех партий товара (см. :meth:`_resolve_row`).

        Returns:
            Распределение по партиям либо причина, по которой выполнить
            заказ не удалось.
        """
        certified = [check for check in checks if check.has_certificate]

        if not certified:
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
