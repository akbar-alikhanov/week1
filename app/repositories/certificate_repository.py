"""Репозиторий справочника сертификатов."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from datetime import date, datetime
from typing import Any, NamedTuple

from app.core.text import normalize
from app.database.schema import has_fts
from app.models.certificate import Certificate
from app.repositories.base import BaseRepository

_LOGGER = logging.getLogger(__name__)

#: Колонки, выбираемые при чтении сертификатов. ``raw_text`` исключён из
#: списковых выборок: он может весить килобайты и не нужен для ранжирования.
_LIGHT_COLUMNS = (
    "id, product_name, normalized_name, translit_name, name_signature, token_signature, "
    "brand, manufacturer, applicant, country, certificate_number, certificate_date, "
    "valid_from, expiry_date, issued_by, volume_value, volume_unit, volume_raw, pack_count, "
    "pdf_name, pdf_path, page_count, file_hash, file_size, file_mtime, indexed_at, "
    "updated_at, '' AS raw_text, extraction_confidence, is_active"
)


class FileFingerprint(NamedTuple):
    """Отпечаток проиндексированного файла для инкрементального сканирования.

    Attributes:
        certificate_id: Идентификатор записи сертификата.
        file_hash: SHA-256 содержимого файла.
        file_size: Размер файла в байтах.
        file_mtime: Время изменения файла.
    """

    certificate_id: int
    file_hash: str
    file_size: int
    file_mtime: float


class CertificateRepository(BaseRepository[Certificate]):
    """Хранение и поиск сертификатов соответствия.

    Репозиторий обслуживает три сценария с разными требованиями:

    * инкрементальную индексацию (быстрая проверка «файл изменился?»);
    * загрузку всего справочника в память для подбора (десятки тысяч записей);
    * интерактивный поиск по строке из интерфейса.
    """

    @property
    def table(self) -> str:
        """Имя таблицы сертификатов."""
        return "certificates"

    def _to_model(self, row: sqlite3.Row) -> Certificate:
        """Преобразует строку результата в :class:`Certificate`."""
        return Certificate.from_row(row)

    # ------------------------------------------------------------- запись
    def add(self, certificate: Certificate) -> int:
        """Добавляет сертификат в справочник.

        Args:
            certificate: Сохраняемый сертификат.

        Returns:
            Идентификатор созданной записи.
        """
        with self._db.transaction(exclusive=True) as connection:
            certificate.id = self._insert(connection, certificate.to_row())
        return certificate.id or 0

    def update(self, certificate: Certificate) -> bool:
        """Обновляет существующую запись сертификата.

        Args:
            certificate: Сертификат с заполненным ``id``.

        Returns:
            ``True``, если запись была изменена.
        """
        if certificate.id is None:
            return False
        certificate.updated_at = datetime.now()
        with self._db.transaction(exclusive=True) as connection:
            changed = self._update(
                connection,
                certificate.to_row(),
                where="id = :row_id",
                parameters={"row_id": certificate.id},
            )
        return changed > 0

    def upsert_many(self, certificates: Sequence[Certificate]) -> tuple[int, int]:
        """Массово добавляет или обновляет сертификаты за одну транзакцию.

        Ключом служит ``pdf_path``: он уникален и стабилен между запусками.

        Args:
            certificates: Сохраняемые сертификаты.

        Returns:
            Пара ``(добавлено, обновлено)``.
        """
        if not certificates:
            return (0, 0)

        added = 0
        updated = 0
        with self._db.transaction(exclusive=True) as connection:
            placeholders = ", ".join("?" for _ in certificates)
            existing = {
                str(row["pdf_path"]): int(row["id"])
                for row in connection.execute(
                    f"SELECT id, pdf_path FROM certificates WHERE pdf_path IN ({placeholders})",
                    [certificate.pdf_path for certificate in certificates],
                )
            }
            for certificate in certificates:
                row_id = existing.get(certificate.pdf_path)
                if row_id is None:
                    certificate.id = self._insert(connection, certificate.to_row())
                    added += 1
                else:
                    certificate.id = row_id
                    certificate.updated_at = datetime.now()
                    self._update(
                        connection,
                        certificate.to_row(),
                        where="id = :row_id",
                        parameters={"row_id": row_id},
                    )
                    updated += 1
        _LOGGER.debug("Сохранено сертификатов: добавлено %s, обновлено %s", added, updated)
        return (added, updated)

    def deactivate_missing(self, existing_paths: Iterable[str]) -> int:
        """Помечает неактивными записи, файлы которых исчезли с диска.

        Записи не удаляются: на них могут ссылаться псевдонимы и история.

        Args:
            existing_paths: Пути файлов, найденных при сканировании.

        Returns:
            Количество деактивированных записей.
        """
        paths = set(existing_paths)
        with self._db.transaction(exclusive=True) as connection:
            stored = {
                str(row["pdf_path"]): int(row["id"])
                for row in connection.execute(
                    "SELECT id, pdf_path FROM certificates WHERE is_active = 1"
                )
            }
            missing = [row_id for path, row_id in stored.items() if path not in paths]
            for row_id in missing:
                connection.execute(
                    "UPDATE certificates SET is_active = 0, updated_at = ? WHERE id = ?",
                    (datetime.now().isoformat(timespec="seconds"), row_id),
                )
        if missing:
            _LOGGER.info("Помечено отсутствующими сертификатов: %s", len(missing))
        return len(missing)

    def delete_by_path(self, pdf_path: str) -> bool:
        """Удаляет сертификат по пути к файлу.

        Args:
            pdf_path: Полный путь к PDF-файлу.

        Returns:
            ``True``, если запись была удалена.
        """
        cursor = self._db.execute("DELETE FROM certificates WHERE pdf_path = ?", (pdf_path,))
        return cursor.rowcount > 0

    # ------------------------------------------------------------- чтение
    def get_by_id(self, certificate_id: int) -> Certificate | None:
        """Возвращает сертификат по идентификатору.

        Args:
            certificate_id: Идентификатор записи.

        Returns:
            Сертификат либо ``None``.
        """
        row = self._db.query_one("SELECT * FROM certificates WHERE id = ?", (certificate_id,))
        return self._to_model(row) if row else None

    def get_by_path(self, pdf_path: str) -> Certificate | None:
        """Возвращает сертификат по пути к PDF-файлу.

        Args:
            pdf_path: Полный путь к файлу.

        Returns:
            Сертификат либо ``None``.
        """
        row = self._db.query_one("SELECT * FROM certificates WHERE pdf_path = ?", (pdf_path,))
        return self._to_model(row) if row else None

    def get_many(self, identifiers: Sequence[int]) -> list[Certificate]:
        """Возвращает сертификаты по списку идентификаторов.

        Args:
            identifiers: Идентификаторы записей.

        Returns:
            Список найденных сертификатов.
        """
        if not identifiers:
            return []
        placeholders = ", ".join("?" * len(identifiers))
        rows = self._db.query_all(
            f"SELECT * FROM certificates WHERE id IN ({placeholders})", list(identifiers)
        )
        return self._rows_to_models(rows)

    def list_active(self, *, include_expired: bool = True) -> list[Certificate]:
        """Загружает все активные сертификаты для подбора.

        Args:
            include_expired: Включать ли сертификаты с истёкшим сроком.

        Returns:
            Список сертификатов без тяжёлого поля ``raw_text``.
        """
        sql = f"SELECT {_LIGHT_COLUMNS} FROM certificates WHERE is_active = 1"
        parameters: list[Any] = []
        if not include_expired:
            sql += " AND (expiry_date IS NULL OR expiry_date >= ?)"
            parameters.append(date.today().isoformat())
        return self._rows_to_models(self._db.query_all(sql, parameters))

    def iter_active(self, batch_size: int = 500) -> Iterator[Certificate]:
        """Итерирует активные сертификаты порциями.

        Используется при построении векторного индекса, чтобы не удерживать
        в памяти весь справочник одновременно.

        Args:
            batch_size: Размер порции.

        Yields:
            Сертификаты по одному.
        """
        offset = 0
        while True:
            rows = self._db.query_all(
                f"SELECT {_LIGHT_COLUMNS} FROM certificates WHERE is_active = 1 "
                "ORDER BY id LIMIT ? OFFSET ?",
                (batch_size, offset),
            )
            if not rows:
                return
            yield from self._rows_to_models(rows)
            offset += batch_size

    def find_by_normalized_name(self, name: str) -> list[Certificate]:
        """Находит сертификаты с точно совпадающим нормализованным наименованием.

        Args:
            name: Наименование (нормализуется автоматически).

        Returns:
            Список сертификатов.
        """
        rows = self._db.query_all(
            f"SELECT {_LIGHT_COLUMNS} FROM certificates "
            "WHERE is_active = 1 AND normalized_name = ?",
            (normalize(name),),
        )
        return self._rows_to_models(rows)

    def fingerprints(self) -> dict[str, FileFingerprint]:
        """Возвращает отпечатки всех проиндексированных файлов.

        Один запрос вместо тысяч точечных проверок — основа быстрой
        инкрементальной индексации.

        Returns:
            Отображение «путь к файлу → отпечаток».
        """
        rows = self._db.query_all(
            "SELECT id, pdf_path, file_hash, file_size, file_mtime FROM certificates"
        )
        return {
            str(row["pdf_path"]): FileFingerprint(
                certificate_id=int(row["id"]),
                file_hash=str(row["file_hash"] or ""),
                file_size=int(row["file_size"] or 0),
                file_mtime=float(row["file_mtime"] or 0.0),
            )
            for row in rows
        }

    # -------------------------------------------------------------- поиск
    def search(
        self, query: str, *, limit: int = 200, include_inactive: bool = False
    ) -> list[Certificate]:
        """Ищет сертификаты по произвольной строке.

        Сначала используется полнотекстовый индекс FTS5; если он недоступен
        или ничего не нашёл, выполняется поиск по подстроке.

        Args:
            query: Поисковый запрос.
            limit: Максимальное количество результатов.
            include_inactive: Включать ли записи с отсутствующими файлами.

        Returns:
            Список найденных сертификатов.
        """
        text = query.strip()
        if not text:
            sql = f"SELECT {_LIGHT_COLUMNS} FROM certificates"
            if not include_inactive:
                sql += " WHERE is_active = 1"
            sql += " ORDER BY product_name LIMIT ?"
            return self._rows_to_models(self._db.query_all(sql, (limit,)))

        results = self._search_fts(text, limit=limit, include_inactive=include_inactive)
        if results:
            return results
        return self._search_like(text, limit=limit, include_inactive=include_inactive)

    def _search_fts(self, query: str, *, limit: int, include_inactive: bool) -> list[Certificate]:
        """Выполняет полнотекстовый поиск через FTS5."""
        if not has_fts(self._db.connection):
            return []
        tokens = [token for token in normalize(query).split(" ") if token]
        if not tokens:
            return []
        expression = " AND ".join(f'"{token}"*' for token in tokens)
        sql = (
            "SELECT c.* FROM certificates_fts f "
            "JOIN certificates c ON c.id = f.rowid "
            "WHERE certificates_fts MATCH ?"
        )
        if not include_inactive:
            sql += " AND c.is_active = 1"
        sql += " ORDER BY rank LIMIT ?"
        try:
            rows = self._db.query_all(sql, (expression, limit))
        except Exception as error:
            _LOGGER.debug("Полнотекстовый поиск не выполнен: %s", error)
            return []
        return self._rows_to_models(rows)

    def _search_like(self, query: str, *, limit: int, include_inactive: bool) -> list[Certificate]:
        """Выполняет поиск по подстроке (резервный вариант)."""
        pattern = f"%{normalize(query)}%"
        raw_pattern = f"%{query.strip().lower()}%"
        sql = (
            f"SELECT {_LIGHT_COLUMNS} FROM certificates "
            "WHERE (normalized_name LIKE ? OR translit_name LIKE ? "
            "       OR lower(certificate_number) LIKE ? OR lower(pdf_name) LIKE ? "
            "       OR lower(brand) LIKE ?)"
        )
        if not include_inactive:
            sql += " AND is_active = 1"
        sql += " ORDER BY product_name LIMIT ?"
        rows = self._db.query_all(
            sql, (pattern, pattern, raw_pattern, raw_pattern, raw_pattern, limit)
        )
        return self._rows_to_models(rows)

    # ------------------------------------------------------------ сводка
    def statistics(self) -> dict[str, Any]:
        """Собирает статистику справочника для панели мониторинга.

        Returns:
            Словарь с показателями: всего, активных, просроченных,
            истекающих в ближайшие 90 дней, без распознанного срока.
        """
        today = date.today().isoformat()
        return {
            "total": self.count(),
            "active": self.count("is_active = 1"),
            "expired": self.count(
                "is_active = 1 AND expiry_date IS NOT NULL AND expiry_date < ?", (today,)
            ),
            "expiring_soon": int(
                self._db.query_scalar(
                    "SELECT count(*) FROM certificates WHERE is_active = 1 "
                    "AND expiry_date IS NOT NULL AND expiry_date >= ? "
                    "AND julianday(expiry_date) - julianday(?) <= 90",
                    (today, today),
                )
                or 0
            ),
            "without_expiry": self.count(
                "is_active = 1 AND (expiry_date IS NULL OR expiry_date = '')"
            ),
            "without_volume": self.count("is_active = 1 AND volume_value IS NULL"),
            "last_indexed": self._db.query_scalar("SELECT max(indexed_at) FROM certificates"),
        }
