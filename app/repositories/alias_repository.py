"""Репозиторий псевдонимов — хранилище «памяти» приложения."""

from __future__ import annotations

import csv
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.exceptions import ExportError
from app.core.text import normalize, token_key
from app.models.alias import Alias
from app.repositories.base import BaseRepository

_LOGGER = logging.getLogger(__name__)


class AliasRepository(BaseRepository[Alias]):
    """Хранение и поиск запомненных соответствий.

    Псевдонимы читаются на каждой строке заказа, поэтому доступ построен на
    индексированных точных сравнениях — без ``LIKE`` и без нечёткого поиска.
    """

    @property
    def table(self) -> str:
        """Имя таблицы псевдонимов."""
        return "aliases"

    def _to_model(self, row: sqlite3.Row) -> Alias:
        """Преобразует строку результата в :class:`Alias`."""
        return Alias.from_row(row)

    # ------------------------------------------------------------- запись
    def save(self, alias: Alias) -> Alias:
        """Создаёт или обновляет псевдоним.

        Уникальность обеспечивается парой «нормализованный источник + цель»:
        повторное обучение на том же соответствии обновляет запись, а не
        порождает дубликаты.

        Args:
            alias: Сохраняемый псевдоним.

        Returns:
            Сохранённый псевдоним с заполненным ``id``.
        """
        alias.updated_at = datetime.now()
        existing = self.find_exact_target(alias.normalized_source, alias.certificate_id)
        with self._db.transaction(exclusive=True) as connection:
            if existing is not None and existing.id is not None:
                alias.id = existing.id
                alias.created_at = existing.created_at
                alias.hit_count = max(alias.hit_count, existing.hit_count)
                self._update(
                    connection,
                    alias.to_row(),
                    where="id = :row_id",
                    parameters={"row_id": existing.id},
                )
            else:
                alias.id = self._insert(connection, alias.to_row())
        _LOGGER.info("Сохранён псевдоним: %s", alias.describe())
        return alias

    def save_many(self, aliases: list[Alias]) -> int:
        """Массово сохраняет псевдонимы (используется при импорте).

        Args:
            aliases: Список псевдонимов.

        Returns:
            Количество успешно сохранённых записей.
        """
        saved = 0
        for alias in aliases:
            if not alias.is_valid:
                continue
            self.save(alias)
            saved += 1
        return saved

    def register_hit(self, alias_id: int) -> None:
        """Увеличивает счётчик применений псевдонима.

        Args:
            alias_id: Идентификатор псевдонима.
        """
        self._db.execute(
            "UPDATE aliases SET hit_count = hit_count + 1, updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(timespec="seconds"), alias_id),
        )

    def remove_for_source(self, source_text: str) -> int:
        """Удаляет все псевдонимы для заданного исходного наименования.

        Args:
            source_text: Исходное наименование.

        Returns:
            Количество удалённых записей.
        """
        cursor = self._db.execute(
            "DELETE FROM aliases WHERE normalized_source = ?", (normalize(source_text),)
        )
        return cursor.rowcount

    # ------------------------------------------------------------- чтение
    def find_exact_target(self, normalized_source: str, certificate_id: int | None) -> Alias | None:
        """Находит псевдоним по паре «источник + сертификат».

        Args:
            normalized_source: Нормализованное исходное наименование.
            certificate_id: Идентификатор сертификата-цели.

        Returns:
            Псевдоним либо ``None``.
        """
        row = self._db.query_one(
            "SELECT * FROM aliases WHERE normalized_source = ? AND certificate_id IS ?",
            (normalized_source, certificate_id),
        )
        return self._to_model(row) if row else None

    def find_for_text(self, text: str) -> list[Alias]:
        """Находит псевдонимы для наименования из заказа.

        Поиск двухступенчатый: сначала точное совпадение нормализованной
        строки, затем — совпадение по набору токенов (устойчиво к перестановке
        слов). Результат отсортирован по приоритету и частоте применения.

        Args:
            text: Наименование товара из заказа.

        Returns:
            Список подходящих псевдонимов (обычно ноль или один).
        """
        normalized = normalize(text)
        if not normalized:
            return []

        rows = self._db.query_all(
            "SELECT * FROM aliases WHERE normalized_source = ? "
            "ORDER BY weight DESC, hit_count DESC, updated_at DESC",
            (normalized,),
        )
        if rows:
            return self._rows_to_models(rows)

        tokens = token_key(text)
        if not tokens:
            return []
        rows = self._db.query_all(
            "SELECT * FROM aliases WHERE token_source = ? "
            "ORDER BY weight DESC, hit_count DESC, updated_at DESC",
            (tokens,),
        )
        return self._rows_to_models(rows)

    def list_all(self, *, limit: int = 0, search: str = "") -> list[Alias]:
        """Возвращает псевдонимы для отображения в интерфейсе.

        Args:
            limit: Максимум записей (0 — без ограничения).
            search: Фильтр по подстроке источника или цели.

        Returns:
            Список псевдонимов, отсортированный по дате изменения.
        """
        sql = "SELECT * FROM aliases"
        parameters: list[Any] = []
        if search.strip():
            pattern = f"%{search.strip().lower()}%"
            sql += (
                " WHERE lower(source_text) LIKE ? OR lower(target_name) LIKE ?"
                " OR lower(target_pdf_name) LIKE ?"
            )
            parameters.extend([pattern, pattern, pattern])
        sql += " ORDER BY updated_at DESC"
        if limit > 0:
            sql += " LIMIT ?"
            parameters.append(limit)
        return self._rows_to_models(self._db.query_all(sql, parameters))

    def count_for_certificate(self, certificate_id: int) -> int:
        """Возвращает количество псевдонимов, ссылающихся на сертификат.

        Args:
            certificate_id: Идентификатор сертификата.

        Returns:
            Количество псевдонимов.
        """
        return self.count("certificate_id = ?", (certificate_id,))

    def repair_links(self) -> int:
        """Восстанавливает связи псевдонимов после переиндексации.

        При смене идентификаторов сертификатов (например, после полной
        переиндексации) псевдонимы переподвязываются по имени PDF-файла.

        Returns:
            Количество восстановленных связей.
        """
        rows = self._db.query_all(
            "SELECT a.id AS alias_id, a.target_pdf_name AS pdf_name "
            "FROM aliases a LEFT JOIN certificates c ON c.id = a.certificate_id "
            "WHERE a.certificate_id IS NULL OR c.id IS NULL"
        )
        repaired = 0
        with self._db.transaction(exclusive=True) as connection:
            for row in rows:
                pdf_name = str(row["pdf_name"] or "")
                if not pdf_name:
                    continue
                target = connection.execute(
                    "SELECT id FROM certificates WHERE pdf_name = ? AND is_active = 1 LIMIT 1",
                    (pdf_name,),
                ).fetchone()
                if target is None:
                    continue
                connection.execute(
                    "UPDATE aliases SET certificate_id = ?, updated_at = ? WHERE id = ?",
                    (
                        int(target["id"]),
                        datetime.now().isoformat(timespec="seconds"),
                        int(row["alias_id"]),
                    ),
                )
                repaired += 1
        if repaired:
            _LOGGER.info("Восстановлено связей псевдонимов: %s", repaired)
        return repaired

    # ---------------------------------------------------------- импорт/экспорт
    def export_to_file(self, destination: Path) -> int:
        """Экспортирует псевдонимы в JSON или CSV.

        Формат определяется расширением файла. Экспорт нужен для переноса
        накопленной «памяти» между рабочими местами.

        Args:
            destination: Путь файла назначения.

        Returns:
            Количество экспортированных записей.

        Raises:
            ExportError: При ошибке записи файла.
        """
        aliases = self.list_all()
        payload = [
            {
                "source_text": alias.source_text,
                "target_name": alias.target_name,
                "target_pdf_name": alias.target_pdf_name,
                "weight": alias.weight,
                "hit_count": alias.hit_count,
                "note": alias.note,
                "created_at": alias.created_at.isoformat(timespec="seconds"),
            }
            for alias in aliases
        ]
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.suffix.lower() == ".csv":
                with destination.open("w", encoding="utf-8-sig", newline="") as handle:
                    writer = csv.DictWriter(
                        handle,
                        fieldnames=(
                            list(payload[0])
                            if payload
                            else [
                                "source_text",
                                "target_name",
                                "target_pdf_name",
                                "weight",
                                "hit_count",
                                "note",
                                "created_at",
                            ]
                        ),
                        delimiter=";",
                    )
                    writer.writeheader()
                    writer.writerows(payload)
            else:
                destination.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
                )
        except OSError as error:
            raise ExportError("Не удалось экспортировать псевдонимы", details=str(error)) from error

        _LOGGER.info("Экспортировано псевдонимов: %s → %s", len(payload), destination)
        return len(payload)

    def import_from_file(self, source: Path) -> tuple[int, int]:
        """Импортирует псевдонимы из JSON или CSV.

        Связь с сертификатом восстанавливается по имени PDF-файла, поэтому
        файл переносим между машинами с разными базами.

        Args:
            source: Путь файла-источника.

        Returns:
            Пара ``(импортировано, пропущено)``.

        Raises:
            ExportError: Если файл нечитаем или имеет неверный формат.
        """
        try:
            if source.suffix.lower() == ".csv":
                with source.open("r", encoding="utf-8-sig", newline="") as handle:
                    records = list(csv.DictReader(handle, delimiter=";"))
            else:
                records = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, csv.Error) as error:
            raise ExportError(
                "Не удалось прочитать файл псевдонимов", details=str(error)
            ) from error

        if not isinstance(records, list):
            raise ExportError("Файл псевдонимов имеет неверный формат")

        imported = 0
        skipped = 0
        for record in records:
            if not isinstance(record, dict):
                skipped += 1
                continue
            source_text = str(record.get("source_text") or "").strip()
            pdf_name = str(record.get("target_pdf_name") or "").strip()
            if not source_text or not pdf_name:
                skipped += 1
                continue
            certificate_row = self._db.query_one(
                "SELECT id, product_name FROM certificates WHERE pdf_name = ? "
                "ORDER BY is_active DESC LIMIT 1",
                (pdf_name,),
            )
            if certificate_row is None:
                skipped += 1
                continue
            self.save(
                Alias(
                    source_text=source_text,
                    certificate_id=int(certificate_row["id"]),
                    target_name=str(record.get("target_name") or certificate_row["product_name"]),
                    target_pdf_name=pdf_name,
                    weight=float(record.get("weight") or 1.0),
                    note=str(record.get("note") or ""),
                )
            )
            imported += 1

        _LOGGER.info("Импорт псевдонимов: добавлено %s, пропущено %s", imported, skipped)
        return (imported, skipped)
