"""Доменная модель строки Excel-базы сроков годности и остатков."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.core.dates import format_date, parse_date
from app.core.text import normalize


@dataclass(slots=True)
class ExpiryStockEntry:
    """Одна партия товара из Excel-базы сроков годности.

    Эта база — отдельный источник данных от базы сертификатов: она отвечает
    на вопрос «какие партии этого товара сейчас есть на складе и когда у
    них заканчивается срок годности», а не «какой сертификат подтверждает
    товар». Ключ поиска — ``normalized_name`` от ПОЛНОГО системного
    названия товара (``product_name``), без очистки от кода товара и
    отметки количества в коробке: в отличие от подбора сертификата или
    словаря соответствий, здесь строка заказа должна совпасть с записью
    базы дословно (после нормализации регистра/пробелов) — это выгрузка
    остатков по конкретному складскому артикулу, а не свободный текст.

    Один товар может встречаться в базе много раз — по одной записи на
    партию/срок годности (см.
    :class:`~app.services.expiry_resolution_service.ExpiryResolutionService`,
    которая выбирает из них подходящую партию до начала подбора сертификата).

    Attributes:
        product_name: Полное системное название товара, как в заказе.
        expiry_date: Срок годности партии.
        quantity: Остаток партии на складе.
        id: Первичный ключ в SQLite (``None`` до сохранения).
        normalized_name: Каноническое наименование — ключ поиска.
        source_row: Порядковый номер строки в исходном Excel-файле.
    """

    product_name: str
    expiry_date: date | None = None
    quantity: float = 0.0
    id: int | None = None
    normalized_name: str = ""
    source_row: int = 0

    def __post_init__(self) -> None:
        """Достраивает производные поля, если они не заданы явно."""
        if not self.normalized_name:
            self.normalized_name = normalize(self.product_name)

    def summary(self) -> str:
        """Возвращает однострочное описание партии для интерфейса."""
        parts = [self.product_name, f"остаток {self.quantity:g}"]
        if self.expiry_date:
            parts.append(f"до {format_date(self.expiry_date)}")
        return " · ".join(part for part in parts if part)

    # ----------------------------------------------------- (де)сериализация
    def to_row(self) -> dict[str, Any]:
        """Преобразует запись в словарь для вставки в SQLite.

        Returns:
            Словарь, ключи которого совпадают с колонками таблицы
            ``expiry_stock``.
        """
        return {
            "id": self.id,
            "product_name": self.product_name,
            "normalized_name": self.normalized_name,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "quantity": self.quantity,
            "source_row": self.source_row,
        }

    @classmethod
    def from_row(cls, row: Any) -> ExpiryStockEntry:
        """Восстанавливает объект из строки SQLite.

        Args:
            row: :class:`sqlite3.Row` или совместимое отображение.

        Returns:
            Экземпляр :class:`ExpiryStockEntry`.
        """
        data = dict(row)
        return cls(
            id=data.get("id"),
            product_name=data.get("product_name") or "",
            normalized_name=data.get("normalized_name") or "",
            expiry_date=parse_date(data.get("expiry_date")),
            quantity=float(data.get("quantity") or 0.0),
            source_row=int(data.get("source_row") or 0),
        )
