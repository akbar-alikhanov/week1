"""Репозиторий Excel-базы сертификатов (SQLite — индекс над Excel)."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Sequence
from datetime import date
from typing import Any

from app.core.text import normalize
from app.models.certificate_product import CertificateProduct
from app.repositories.base import BaseRepository

_LOGGER = logging.getLogger(__name__)


class CertificateProductRepository(BaseRepository[CertificateProduct]):
    """Хранит и ищет товарные позиции Excel-базы сертификатов.

    База полностью переимпортируется при каждом обновлении Excel-файла
    (см. :class:`~app.services.certificate_import_service.CertificateImportService`)
    — инкрементальных обновлений и отслеживания изменившихся строк нет,
    потому что полный переимпорт нескольких тысяч строк занимает миллисекунды
    и не требует более сложной логики.
    """

    @property
    def table(self) -> str:
        """Имя таблицы Excel-базы сертификатов."""
        return "certificate_products"

    def _to_model(self, row: sqlite3.Row) -> CertificateProduct:
        """Преобразует строку результата в :class:`CertificateProduct`."""
        return CertificateProduct.from_row(row)

    # ------------------------------------------------------------- запись
    def replace_all(self, products: Sequence[CertificateProduct]) -> int:
        """Полностью заменяет содержимое базы новыми данными из Excel.

        Внешние ключи ``products.last_certificate_id`` (``ON DELETE SET
        NULL``) и ``embeddings.certificate_id`` (``ON DELETE CASCADE``)
        автоматически освобождаются при удалении старых строк — устаревший
        кэш эмбеддингов не может пережить переимпорт и не должен.

        Args:
            products: Строки, прочитанные из Excel-файла базы сертификатов.

        Returns:
            Количество сохранённых строк.
        """
        with self._db.transaction(exclusive=True) as connection:
            connection.execute("DELETE FROM certificate_products")
            for product in products:
                product.id = self._insert(connection, product.to_row())
        _LOGGER.info("База сертификатов переимпортирована: %s строк", len(products))
        return len(products)

    # ------------------------------------------------------------- чтение
    def get_by_id(self, product_id: int) -> CertificateProduct | None:
        """Возвращает позицию по идентификатору.

        Args:
            product_id: Идентификатор записи.

        Returns:
            Позиция либо ``None``.
        """
        row = self._db.query_one("SELECT * FROM certificate_products WHERE id = ?", (product_id,))
        return self._to_model(row) if row else None

    def list_all(self) -> list[CertificateProduct]:
        """Загружает всю базу для построения индексов подбора.

        Returns:
            Все строки Excel-базы сертификатов.
        """
        rows = self._db.query_all("SELECT * FROM certificate_products ORDER BY id")
        return self._rows_to_models(rows)

    def find_strict(
        self, normalized_name: str, volume_ml: float | None
    ) -> list[CertificateProduct]:
        """Строгий поиск по словарю: точное наименование и точный объём.

        Единственный способ подбора, разрешённый после срабатывания
        псевдонима — ``WHERE normalized_name = ? AND volume_ml IS ?``,
        без нечёткого сравнения и без допуска. ``IS`` (а не ``=``) нужен,
        чтобы значение ``NULL`` (объём не определён) тоже участвовало в
        сравнении как обычное значение, а не терялось в SQL-семантике
        трёхзначной логики.

        Args:
            normalized_name: Нормализованное русское наименование из словаря.
            volume_ml: Объём из словаря (``None`` — товар без объёма).

        Returns:
            Все подходящие строки базы сертификатов.
        """
        if not normalized_name:
            return []
        rows = self._db.query_all(
            "SELECT * FROM certificate_products WHERE normalized_name = ? AND volume_ml IS ?",
            (normalized_name, volume_ml),
        )
        return self._rows_to_models(rows)

    def search(self, query: str, *, limit: int = 200) -> list[CertificateProduct]:
        """Ищет позиции по подстроке наименования или номеру сертификата.

        Используется интерфейсом (справочник, подбор сертификата для
        словаря соответствий) — не участвует в алгоритме подбора заказа.

        Args:
            query: Поисковый запрос.
            limit: Максимальное количество результатов.

        Returns:
            Найденные позиции, отсортированные по наименованию.
        """
        text = query.strip()
        if not text:
            rows = self._db.query_all(
                "SELECT * FROM certificate_products ORDER BY product_name LIMIT ?", (limit,)
            )
            return self._rows_to_models(rows)

        pattern = f"%{normalize(text)}%"
        raw_pattern = f"%{text.lower()}%"
        rows = self._db.query_all(
            "SELECT * FROM certificate_products "
            "WHERE normalized_name LIKE ? OR lower(certificate_number) LIKE ? "
            "ORDER BY product_name LIMIT ?",
            (pattern, raw_pattern, limit),
        )
        return self._rows_to_models(rows)

    def find_by_certificate_number(self, certificate_number: str) -> list[CertificateProduct]:
        """Возвращает все позиции с заданным номером сертификата.

        Args:
            certificate_number: Номер сертификата.

        Returns:
            Список позиций (один номер сертификата может покрывать несколько
            товарных строк базы).
        """
        rows = self._db.query_all(
            "SELECT * FROM certificate_products WHERE certificate_number = ? ORDER BY id",
            (certificate_number,),
        )
        return self._rows_to_models(rows)

    # ------------------------------------------------------------ сводка
    def statistics(self) -> dict[str, Any]:
        """Собирает статистику базы сертификатов для панели мониторинга.

        Returns:
            Словарь с показателями: всего, просроченных, истекающих в
            ближайшие 90 дней, без распознанного срока.
        """
        today = date.today().isoformat()
        return {
            "total": self.count(),
            "expired": self.count("expiry_date IS NOT NULL AND expiry_date < ?", (today,)),
            "expiring_soon": int(
                self._db.query_scalar(
                    "SELECT count(*) FROM certificate_products WHERE expiry_date IS NOT NULL "
                    "AND expiry_date >= ? AND julianday(expiry_date) - julianday(?) <= 90",
                    (today, today),
                )
                or 0
            ),
            "without_expiry": self.count("expiry_date IS NULL OR expiry_date = ''"),
            "without_volume": self.count("volume_ml IS NULL"),
        }
