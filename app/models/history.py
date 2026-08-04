"""Модели журнала обработки заказов и результатов индексации."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models.matching import MatchStatus


@dataclass(slots=True)
class ProcessingItem:
    """Строка журнала: результат подбора для одной позиции заказа.

    Attributes:
        run_id: Идентификатор запуска обработки.
        row_number: Номер строки в исходном файле.
        product_name: Наименование товара из заказа.
        status: Итоговый статус подбора.
        certificate_id: Идентификатор выбранного сертификата.
        certificate_number: Номер выбранного сертификата.
        certificate_expiry: Срок действия выбранного сертификата (ISO-строка).
        pdf_name: Имя PDF-файла.
        score: Итоговая оценка совпадения.
        method: Метод, давший результат.
        candidates_count: Количество рассмотренных кандидатов.
        duration_ms: Длительность подбора.
        note: Пояснение.
        id: Первичный ключ.
    """

    run_id: str
    row_number: int
    product_name: str
    status: str
    certificate_id: int | None = None
    certificate_number: str = ""
    certificate_expiry: str = ""
    pdf_name: str = ""
    score: float = 0.0
    method: str = ""
    candidates_count: int = 0
    duration_ms: float = 0.0
    note: str = ""
    id: int | None = None

    def to_row(self) -> dict[str, Any]:
        """Преобразует запись в словарь для SQLite."""
        return {
            "id": self.id,
            "run_id": self.run_id,
            "row_number": self.row_number,
            "product_name": self.product_name,
            "status": self.status,
            "certificate_id": self.certificate_id,
            "certificate_number": self.certificate_number,
            "certificate_expiry": self.certificate_expiry,
            "pdf_name": self.pdf_name,
            "score": self.score,
            "method": self.method,
            "candidates_count": self.candidates_count,
            "duration_ms": self.duration_ms,
            "note": self.note,
        }

    @classmethod
    def from_row(cls, row: Any) -> ProcessingItem:
        """Восстанавливает запись из строки SQLite."""
        data = dict(row)
        return cls(
            id=data.get("id"),
            run_id=data.get("run_id") or "",
            row_number=int(data.get("row_number") or 0),
            product_name=data.get("product_name") or "",
            status=data.get("status") or MatchStatus.NOT_FOUND.value,
            certificate_id=data.get("certificate_id"),
            certificate_number=data.get("certificate_number") or "",
            certificate_expiry=data.get("certificate_expiry") or "",
            pdf_name=data.get("pdf_name") or "",
            score=float(data.get("score") or 0.0),
            method=data.get("method") or "",
            candidates_count=int(data.get("candidates_count") or 0),
            duration_ms=float(data.get("duration_ms") or 0.0),
            note=data.get("note") or "",
        )


@dataclass(slots=True)
class ProcessingRun:
    """Запуск обработки заказа целиком.

    Attributes:
        run_id: Уникальный идентификатор запуска.
        order_file: Путь к исходному файлу заказа.
        output_file: Путь к сформированному файлу результата.
        certificates_dir: Каталог, куда скопированы PDF.
        report_file: Путь к файлу отчёта.
        started_at: Момент начала.
        finished_at: Момент завершения.
        total_rows: Всего обработано строк.
        matched: Найдено автоматически.
        ambiguous: Потребовало проверки.
        not_found: Не найдено.
        manual: Выбрано вручную.
        copied_files: Скопировано PDF-файлов.
        duration_ms: Общая длительность.
        status: ``success``, ``partial``, ``failed`` или ``cancelled``.
        message: Итоговое сообщение/ошибка.
        id: Первичный ключ.
    """

    order_file: str
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    output_file: str = ""
    certificates_dir: str = ""
    report_file: str = ""
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None
    total_rows: int = 0
    matched: int = 0
    ambiguous: int = 0
    not_found: int = 0
    manual: int = 0
    copied_files: int = 0
    duration_ms: float = 0.0
    status: str = "success"
    message: str = ""
    id: int | None = None

    @property
    def order_name(self) -> str:
        """Имя файла заказа без пути."""
        return Path(self.order_file).name if self.order_file else ""

    @property
    def resolved(self) -> int:
        """Количество строк с определённым сертификатом."""
        return self.matched + self.manual

    @property
    def success_rate(self) -> float:
        """Доля успешно подобранных строк в диапазоне ``[0..1]``."""
        if self.total_rows <= 0:
            return 0.0
        return self.resolved / self.total_rows

    @property
    def duration_seconds(self) -> float:
        """Длительность обработки в секундах."""
        return self.duration_ms / 1000.0

    def to_row(self) -> dict[str, Any]:
        """Преобразует запуск в словарь для SQLite."""
        return {
            "id": self.id,
            "run_id": self.run_id,
            "order_file": self.order_file,
            "output_file": self.output_file,
            "certificates_dir": self.certificates_dir,
            "report_file": self.report_file,
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "finished_at": (
                self.finished_at.isoformat(timespec="seconds") if self.finished_at else None
            ),
            "total_rows": self.total_rows,
            "matched": self.matched,
            "ambiguous": self.ambiguous,
            "not_found": self.not_found,
            "manual": self.manual,
            "copied_files": self.copied_files,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "message": self.message,
        }

    @classmethod
    def from_row(cls, row: Any) -> ProcessingRun:
        """Восстанавливает запуск из строки SQLite."""
        data = dict(row)
        finished = data.get("finished_at")
        return cls(
            id=data.get("id"),
            run_id=data.get("run_id") or "",
            order_file=data.get("order_file") or "",
            output_file=data.get("output_file") or "",
            certificates_dir=data.get("certificates_dir") or "",
            report_file=data.get("report_file") or "",
            started_at=_parse(data.get("started_at")),
            finished_at=_parse(finished) if finished else None,
            total_rows=int(data.get("total_rows") or 0),
            matched=int(data.get("matched") or 0),
            ambiguous=int(data.get("ambiguous") or 0),
            not_found=int(data.get("not_found") or 0),
            manual=int(data.get("manual") or 0),
            copied_files=int(data.get("copied_files") or 0),
            duration_ms=float(data.get("duration_ms") or 0.0),
            status=data.get("status") or "success",
            message=data.get("message") or "",
        )


@dataclass(slots=True)
class IndexingResult:
    """Итог сканирования папки сертификатов.

    Attributes:
        scanned: Всего просмотрено файлов.
        added: Проиндексировано новых.
        updated: Переиндексировано изменённых.
        skipped: Пропущено без изменений.
        removed: Помечено отсутствующими.
        failed: Не удалось прочитать.
        duration_ms: Длительность операции.
        errors: Пары «файл → сообщение об ошибке».
        cancelled: Признак отмены пользователем.
    """

    scanned: int = 0
    added: int = 0
    updated: int = 0
    skipped: int = 0
    removed: int = 0
    failed: int = 0
    duration_ms: float = 0.0
    errors: list[tuple[str, str]] = field(default_factory=list)
    cancelled: bool = False

    @property
    def changed(self) -> int:
        """Количество фактически изменённых записей."""
        return self.added + self.updated + self.removed

    def summary(self) -> str:
        """Возвращает однострочную сводку для уведомления и журнала."""
        if self.cancelled:
            return f"Индексация прервана: обработано {self.scanned} файлов"
        parts = [f"просмотрено {self.scanned}"]
        if self.added:
            parts.append(f"добавлено {self.added}")
        if self.updated:
            parts.append(f"обновлено {self.updated}")
        if self.removed:
            parts.append(f"удалено {self.removed}")
        if self.failed:
            parts.append(f"ошибок {self.failed}")
        if not self.changed and not self.failed:
            parts.append("изменений нет")
        return "Индексация: " + ", ".join(parts)


def _parse(value: Any) -> datetime:
    """Разбирает отметку времени, подставляя текущий момент при ошибке."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return datetime.now()
    return datetime.now()
