"""Модели результата подбора сертификата."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any

from app.core.constants import (
    STATUS_AMBIGUOUS,
    STATUS_MANUAL,
    STATUS_MATCHED,
    STATUS_NOT_FOUND,
    STATUS_SKIPPED,
)
from app.models.certificate_product import CertificateProduct
from app.models.order import OrderRow


class MatchSource(StrEnum):
    """Источник, обеспечивший совпадение.

    Порядок членов соответствует порядку этапов конвейера подбора.
    """

    ALIAS = "alias"
    EXACT = "exact"
    LEXICAL = "lexical"
    SEMANTIC = "semantic"
    MANUAL = "manual"

    @property
    def label(self) -> str:
        """Человекочитаемое название источника."""
        return {
            MatchSource.ALIAS: "Псевдоним",
            MatchSource.EXACT: "Точное совпадение",
            MatchSource.LEXICAL: "Нечёткий поиск",
            MatchSource.SEMANTIC: "Семантический поиск",
            MatchSource.MANUAL: "Ручной выбор",
        }[self]


class MatchStatus(StrEnum):
    """Итоговый статус строки заказа."""

    MATCHED = STATUS_MATCHED
    AMBIGUOUS = STATUS_AMBIGUOUS
    NOT_FOUND = STATUS_NOT_FOUND
    MANUAL = STATUS_MANUAL
    SKIPPED = STATUS_SKIPPED

    @property
    def label(self) -> str:
        """Человекочитаемое название статуса."""
        return {
            MatchStatus.MATCHED: "Найден",
            MatchStatus.AMBIGUOUS: "Требует проверки",
            MatchStatus.NOT_FOUND: "Не найден",
            MatchStatus.MANUAL: "Выбран вручную",
            MatchStatus.SKIPPED: "Пропущен",
        }[self]

    @property
    def is_resolved(self) -> bool:
        """Признак того, что для строки определён итоговый сертификат."""
        return self in (MatchStatus.MATCHED, MatchStatus.MANUAL)


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    """Детализация итоговой оценки кандидата.

    Хранение составляющих оценки — обязательное требование прозрачности:
    пользователь должен понимать, почему программа выбрала именно этот
    сертификат, а служба поддержки — воспроизвести решение.

    Attributes:
        name: Оценка совпадения наименования ``[0..1]``.
        volume: Оценка совпадения объёма ``[0..1]``.
        expiry: Оценка соответствия срока ``[0..1]``.
        total: Взвешенная итоговая оценка ``[0..1]``.
        lexical: Оценка лексического (нечёткого) сравнения.
        semantic: Оценка семантического сравнения (``None``, если не считалась).
        weights: Применённые веса ``(наименование, объём, срок)``.
    """

    name: float
    volume: float
    expiry: float
    total: float
    lexical: float = 0.0
    semantic: float | None = None
    weights: tuple[float, float, float] = (0.5, 0.3, 0.2)

    @property
    def percent(self) -> int:
        """Итоговая оценка в процентах."""
        return round(self.total * 100)

    def explain(self) -> str:
        """Возвращает текстовое пояснение оценки для интерфейса.

        Returns:
            Строка вида ``Наименование 97% · Объём 100% · Срок 92%``.
        """
        parts = [
            f"Наименование {self.name * 100:.0f}%",
            f"Объём {self.volume * 100:.0f}%",
            f"Срок {self.expiry * 100:.0f}%",
        ]
        if self.semantic is not None:
            parts.append(f"ИИ {self.semantic * 100:.0f}%")
        return " · ".join(parts)


@dataclass(slots=True)
class MatchCandidate:
    """Кандидат на роль сертификата для строки заказа.

    Attributes:
        certificate: Товарная позиция базы сертификатов — кандидат.
        score: Детализация оценки.
        source: Этап, на котором кандидат был найден.
        rank: Позиция в отсортированном списке (0 — лучший).
    """

    certificate: CertificateProduct
    score: ScoreBreakdown
    source: MatchSource
    rank: int = 0

    @property
    def total(self) -> float:
        """Итоговая оценка кандидата."""
        return self.score.total

    @property
    def percent(self) -> int:
        """Итоговая оценка кандидата в процентах."""
        return self.score.percent


@dataclass(frozen=True, slots=True)
class BatchAllocation:
    """Одна партия, использованная при выполнении заказа несколькими сроками годности.

    Строится этапом подбора срока годности
    (:class:`~app.services.expiry_resolution_service.ExpiryResolutionService`)
    только тогда, когда ни одна партия товара не покрывает требуемое
    количество самостоятельно — тогда несколько партий с уже подтверждённым
    сертификатом объединяются, и для каждой запоминается, сколько именно из
    неё взято (см. :attr:`MatchResult.batch_allocations`).

    Attributes:
        candidate: Кандидат, которым пробный подбор подтвердил сертификат
            для срока этой партии, — тот же объект, что построил бы обычный
            подбор сертификата, включая его настоящую оценку и источник.
        quantity: Сколько единиц товара взято из этой партии (не обязательно
            весь остаток).
        expiry_date: Срок годности партии.
    """

    candidate: MatchCandidate
    quantity: float
    expiry_date: date | None

    @property
    def certificate(self) -> CertificateProduct:
        """Сертификат, подтверждённый для этой партии."""
        return self.candidate.certificate


@dataclass(slots=True)
class MatchResult:
    """Результат подбора сертификата для одной строки заказа.

    Attributes:
        row: Исходная строка заказа.
        status: Итоговый статус.
        candidates: Кандидаты, отсортированные по убыванию оценки.
        selected_index: Индекс выбранного кандидата в ``candidates``.
        duration_ms: Время подбора в миллисекундах.
        note: Пояснение (причина неоднозначности или отсутствия результата).
        alias_applied: Признак того, что решение принято по таблице псевдонимов.
        alias_stale: Признак того, что запись словаря есть, но официальный
            товар из неё сейчас отсутствует в базе сертификатов — результат
            получен запасным путём (ИИ-поиск), и словарь стоит обновить.
        expiry_not_in_database: Признак того, что этап подбора срока
            годности (:class:`~app.services.expiry_resolution_service.ExpiryResolutionService`,
            выполняется ДО подбора сертификата) не нашёл товар в базе
            сроков годности вообще — подбор сертификата для строки поэтому
            не выполнялся. Требует отдельного визуального выделения в
            итоговом Excel (жёлтая заливка и зачёркнутый текст).
        expiry_auto_resolved: Признак того, что требуемый срок годности
            (:attr:`~app.models.order.OrderRow.requested_expiry`) в заказе
            изначально отсутствовал и был подобран новым этапом
            (:class:`~app.services.expiry_resolution_service.ExpiryResolutionService`).
            Только при этом признаке колонка «требуемый срок» исходного
            заказа заполняется в итоговом Excel — если срок уже был указан
            в заказе, колонка остаётся нетронутой независимо от этого поля.
        expiry_no_certificate_available: Признак того, что товар присутствует
            в базе сроков годности, но ни для одной его партии не подтверждён
            сертификат (Этап 2 подбора срока годности). Как и
            ``expiry_not_in_database``, требует жёлтой заливки и зачёркнутого
            текста — строка ни разу не дошла до подбора сертификата.
        batch_allocations: Партии, использованные для выполнения заказа,
            если одной партии не хватило и потребовалось объединение
            нескольких сроков годности (Этап 2). Пустой список — обычный
            случай одной партии/одного сертификата; ``certificate``,
            ``certificate_number`` и ``expiry_date`` при этом по-прежнему
            отражают первую (самую новую) использованную партию, а полную
            раскладку по всем партиям читает
            :class:`~app.services.excel_writer_service.ExcelWriterService`
            из этого поля.
    """

    row: OrderRow
    status: MatchStatus
    candidates: list[MatchCandidate] = field(default_factory=list)
    selected_index: int | None = None
    duration_ms: float = 0.0
    note: str = ""
    alias_applied: bool = False
    alias_stale: bool = False
    expiry_not_in_database: bool = False
    expiry_auto_resolved: bool = False
    expiry_no_certificate_available: bool = False
    batch_allocations: list[BatchAllocation] = field(default_factory=list)

    @property
    def selected(self) -> MatchCandidate | None:
        """Выбранный кандидат либо ``None``."""
        if self.selected_index is None:
            return None
        if 0 <= self.selected_index < len(self.candidates):
            return self.candidates[self.selected_index]
        return None

    @property
    def certificate(self) -> CertificateProduct | None:
        """Товарная позиция базы сертификатов, выбранная для строки заказа."""
        candidate = self.selected
        return candidate.certificate if candidate else None

    @property
    def best(self) -> MatchCandidate | None:
        """Лучший кандидат независимо от статуса."""
        return self.candidates[0] if self.candidates else None

    @property
    def certificate_number(self) -> str:
        """Номер выбранного сертификата или пустая строка."""
        certificate = self.certificate
        return certificate.display_number if certificate else ""

    @property
    def expiry_date(self) -> date | None:
        """Срок действия выбранного сертификата."""
        certificate = self.certificate
        return certificate.expiry_date if certificate else None

    @property
    def score(self) -> float:
        """Оценка выбранного кандидата (или лучшего, если выбор не сделан)."""
        candidate = self.selected or self.best
        return candidate.total if candidate else 0.0

    def select(self, index: int, *, manual: bool = False) -> None:
        """Фиксирует выбор кандидата.

        Args:
            index: Индекс кандидата в списке.
            manual: Признак ручного выбора пользователем.

        Raises:
            IndexError: Если индекс выходит за границы списка.
        """
        if not 0 <= index < len(self.candidates):
            raise IndexError(f"Кандидат с индексом {index} отсутствует")
        self.selected_index = index
        if manual:
            self.status = MatchStatus.MANUAL

    def to_report_dict(self) -> dict[str, Any]:
        """Формирует плоский словарь для отчёта и журнала обработки.

        Returns:
            Словарь со всеми значимыми полями результата.
        """
        certificate = self.certificate
        candidate = self.selected or self.best
        return {
            "Строка": self.row.row_number,
            "Товар": self.row.product_name,
            "Объём заказа": str(self.row.volume) if self.row.volume else "",
            "Статус": self.status.label,
            "Сертификат": certificate.display_number if certificate else "",
            "Срок сертификата": certificate.expiry_date if certificate else None,
            "Товар в сертификате": certificate.product_name if certificate else "",
            "Совпадение, %": candidate.percent if candidate else 0,
            "Метод": candidate.source.label if candidate else "",
            "Детализация": candidate.score.explain() if candidate else "",
            "Кандидатов": len(self.candidates),
            "Примечание": self.note,
            "Время, мс": round(self.duration_ms, 1),
        }
