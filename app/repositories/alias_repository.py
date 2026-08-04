"""Репозиторий псевдонимов — хранилище «памяти» приложения."""

from __future__ import annotations

import csv
import json
import logging
import sqlite3
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from app.ai.fuzzy import similarity
from app.core.exceptions import DuplicateAliasError, ExportError
from app.core.text import normalize, token_key
from app.models.alias import CONFIDENCE_SQL, Alias
from app.models.alias_audit import AliasAuditAction, AliasAuditEntry
from app.repositories.base import BaseRepository

_LOGGER = logging.getLogger(__name__)

#: Соответствие «ключ сортировки из интерфейса → выражение ``ORDER BY``».
_SORT_EXPRESSIONS: dict[str, str] = {
    "updated_desc": "updated_at DESC",
    "created_desc": "created_at DESC",
    "hits_desc": "hit_count DESC, updated_at DESC",
    "confidence_desc": f"{CONFIDENCE_SQL} DESC, hit_count DESC",
    "name_asc": "lower(source_text) ASC",
    "name_desc": "lower(source_text) DESC",
}

#: Поля, экспортируемые/импортируемые в файлы обмена (JSON/CSV/Excel).
_EXCHANGE_FIELDS: tuple[str, ...] = (
    "source_text",
    "target_name",
    "target_pdf_name",
    "brand",
    "volume_value",
    "volume_unit",
    "weight",
    "hit_count",
    "is_manual",
    "note",
    "created_at",
)


def current_user() -> str:
    """Определяет имя текущего пользователя ОС для полей «автор».

    Returns:
        Имя пользователя либо пустая строка, если его не удалось определить.
    """
    try:
        import getpass

        return getpass.getuser()
    except Exception:  # pragma: no cover — платформенно-зависимо
        return ""


class AliasRepository(BaseRepository[Alias]):
    """Хранение, поиск и аудит запомненных соответствий.

    Псевдонимы читаются на каждой строке заказа, поэтому подбор построен на
    индексированных точных сравнениях — без ``LIKE`` и без нечёткого поиска.
    Управление словарём (раздел интерфейса) использует более широкий набор
    операций: многополевой поиск, массовые действия, поиск дубликатов и
    журнал изменений с отменой последнего действия.
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
        """Создаёт или обновляет псевдоним (используется самообучением).

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
                before = existing.to_row()
                alias.id = existing.id
                alias.created_at = existing.created_at
                alias.created_by = existing.created_by or alias.created_by or current_user()
                alias.hit_count = max(alias.hit_count, existing.hit_count)
                alias.last_used_at = alias.last_used_at or existing.last_used_at
                self._update(
                    connection,
                    alias.to_row(),
                    where="id = :row_id",
                    parameters={"row_id": existing.id},
                )
                self._write_audit(
                    connection,
                    alias.id,
                    AliasAuditAction.UPDATED,
                    alias.source_text,
                    before=before,
                    after=alias.to_row(),
                    actor=alias.created_by,
                )
            else:
                alias.created_by = alias.created_by or current_user()
                alias.id = self._insert(connection, alias.to_row())
                self._write_audit(
                    connection,
                    alias.id,
                    AliasAuditAction.CREATED,
                    alias.source_text,
                    before=None,
                    after=alias.to_row(),
                    actor=alias.created_by,
                )
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

    def create(self, alias: Alias) -> Alias:
        """Создаёт новую запись словаря (раздел «Словарь товаров»).

        В отличие от :meth:`save`, не выполняет слияние с существующей
        записью — вызывающая сторона (сервис) обязана заранее проверить
        дубликаты через :meth:`find_similar` и получить подтверждение
        пользователя. Точный дубликат по ключу (нормализованное наименование
        + сертификат) отклоняется безусловно.

        Args:
            alias: Новый псевдоним (``id`` игнорируется).

        Returns:
            Созданный псевдоним с заполненным ``id``.

        Raises:
            DuplicateAliasError: Если точно такая же запись уже существует.
        """
        if self.find_exact_target(alias.normalized_source, alias.certificate_id) is not None:
            raise DuplicateAliasError(
                "Такое соответствие уже есть в словаре",
                details=f"{alias.source_text} → certificate_id={alias.certificate_id}",
            )
        alias.id = None
        alias.created_at = datetime.now()
        alias.updated_at = alias.created_at
        alias.created_by = alias.created_by or current_user()
        with self._db.transaction(exclusive=True) as connection:
            alias.id = self._insert(connection, alias.to_row())
            self._write_audit(
                connection,
                alias.id,
                AliasAuditAction.CREATED,
                alias.source_text,
                before=None,
                after=alias.to_row(),
                actor=alias.created_by,
            )
        _LOGGER.info("Добавлено соответствие: %s", alias.describe())
        return alias

    def update(self, alias_id: int, **changes: Any) -> Alias:
        """Изменяет существующую запись словаря по её идентификатору.

        В отличие от :meth:`save`, обновляет запись «на месте» независимо от
        того, изменились ли ключевые поля (наименование, сертификат) —
        именно этого ожидает пользователь, редактируя строку в таблице.

        Args:
            alias_id: Идентификатор изменяемой записи.
            **changes: Новые значения полей (``source_text``, ``target_name``,
                ``target_pdf_name``, ``certificate_id``, ``brand``,
                ``volume_value``, ``volume_unit``, ``note``).

        Returns:
            Обновлённая запись.

        Raises:
            DuplicateAliasError: Если запись не найдена или изменение
                привело бы к конфликту с другой существующей записью.
        """
        current = self.get_by_id(alias_id)
        if current is None:
            raise DuplicateAliasError(f"Запись #{alias_id} не найдена")

        before = current.to_row()
        for key, value in changes.items():
            setattr(current, key, value)
        if "source_text" in changes:
            current.normalized_source = normalize(current.source_text)
            current.token_source = token_key(current.source_text)
        current.updated_at = datetime.now()

        conflict = self.find_exact_target(current.normalized_source, current.certificate_id)
        if conflict is not None and conflict.id != alias_id:
            raise DuplicateAliasError(
                "Уже есть другая запись с таким же наименованием и сертификатом"
            )

        with self._db.transaction(exclusive=True) as connection:
            self._update(
                connection,
                current.to_row(),
                where="id = :row_id",
                parameters={"row_id": alias_id},
            )
            self._write_audit(
                connection,
                alias_id,
                AliasAuditAction.UPDATED,
                current.source_text,
                before=before,
                after=current.to_row(),
                actor=current_user(),
            )
        _LOGGER.info("Изменено соответствие #%s", alias_id)
        return current

    def get_by_id(self, alias_id: int) -> Alias | None:
        """Возвращает запись по идентификатору.

        Args:
            alias_id: Идентификатор записи.

        Returns:
            Псевдоним либо ``None``.
        """
        row = self._db.query_one("SELECT * FROM aliases WHERE id = ?", (alias_id,))
        return self._to_model(row) if row else None

    def delete(self, alias_id: int, *, actor: str = "") -> bool:
        """Удаляет запись словаря с сохранением её в журнале изменений.

        Args:
            alias_id: Идентификатор записи.
            actor: Пользователь, выполнивший удаление.

        Returns:
            ``True``, если запись была удалена.
        """
        current = self.get_by_id(alias_id)
        if current is None:
            return False
        with self._db.transaction(exclusive=True) as connection:
            cursor = connection.execute("DELETE FROM aliases WHERE id = ?", (alias_id,))
            if cursor.rowcount <= 0:
                return False
            self._write_audit(
                connection,
                alias_id,
                AliasAuditAction.DELETED,
                current.source_text,
                before=current.to_row(),
                after=None,
                actor=actor or current_user(),
            )
        return True

    def bulk_delete(self, ids: Sequence[int], *, actor: str = "") -> int:
        """Удаляет несколько записей одновременно.

        Args:
            ids: Идентификаторы удаляемых записей.
            actor: Пользователь, выполнивший удаление.

        Returns:
            Количество фактически удалённых записей.
        """
        if not ids:
            return 0
        deleted = 0
        who = actor or current_user()
        with self._db.transaction(exclusive=True) as connection:
            for alias_id in ids:
                row = connection.execute(
                    "SELECT * FROM aliases WHERE id = ?", (alias_id,)
                ).fetchone()
                if row is None:
                    continue
                current = self._to_model(row)
                cursor = connection.execute("DELETE FROM aliases WHERE id = ?", (alias_id,))
                if cursor.rowcount <= 0:
                    continue
                deleted += 1
                self._write_audit(
                    connection,
                    alias_id,
                    AliasAuditAction.DELETED,
                    current.source_text,
                    before=current.to_row(),
                    after=None,
                    actor=who,
                )
        _LOGGER.info("Массовое удаление соответствий: %s", deleted)
        return deleted

    def bulk_update(
        self,
        ids: Sequence[int],
        *,
        brand: str | None = None,
        note: str | None = None,
        actor: str = "",
    ) -> int:
        """Массово изменяет одно или несколько полей у набора записей.

        Args:
            ids: Идентификаторы изменяемых записей.
            brand: Новое значение бренда (``None`` — не менять).
            note: Новое значение комментария (``None`` — не менять).
            actor: Пользователь, выполнивший изменение.

        Returns:
            Количество изменённых записей.
        """
        if not ids or (brand is None and note is None):
            return 0
        changed = 0
        who = actor or current_user()
        with self._db.transaction(exclusive=True) as connection:
            for alias_id in ids:
                row = connection.execute(
                    "SELECT * FROM aliases WHERE id = ?", (alias_id,)
                ).fetchone()
                if row is None:
                    continue
                current = self._to_model(row)
                before = current.to_row()
                if brand is not None:
                    current.brand = brand
                if note is not None:
                    current.note = note
                current.updated_at = datetime.now()
                self._update(
                    connection,
                    current.to_row(),
                    where="id = :row_id",
                    parameters={"row_id": alias_id},
                )
                self._write_audit(
                    connection,
                    alias_id,
                    AliasAuditAction.UPDATED,
                    current.source_text,
                    before=before,
                    after=current.to_row(),
                    actor=who,
                )
                changed += 1
        _LOGGER.info("Массовое изменение соответствий: %s", changed)
        return changed

    def register_hit(self, alias_id: int) -> None:
        """Отмечает применение псевдонима при подборе сертификата.

        Обновляет счётчик применений и отдельную отметку «последнее
        использование» — не путать с ``updated_at``, которая меняется только
        при редактировании записи человеком.

        Args:
            alias_id: Идентификатор псевдонима.
        """
        self._db.execute(
            "UPDATE aliases SET hit_count = hit_count + 1, last_used_at = ? WHERE id = ?",
            (datetime.now().isoformat(timespec="seconds"), alias_id),
        )

    def remove_for_source(self, source_text: str) -> int:
        """Удаляет все псевдонимы для заданного исходного наименования.

        Args:
            source_text: Исходное наименование.

        Returns:
            Количество удалённых записей.
        """
        normalized = normalize(source_text)
        rows = self._db.query_all(
            "SELECT id FROM aliases WHERE normalized_source = ?", (normalized,)
        )
        ids = [int(row["id"]) for row in rows]
        return self.bulk_delete(ids)

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
        слов). Результат отсортирован по уровню доверия (записи, подтверждённые
        пользователем, — впереди), затем по приоритету и частоте применения.

        Args:
            text: Наименование товара из заказа.

        Returns:
            Список подходящих псевдонимов (обычно ноль или один).
        """
        normalized = normalize(text)
        if not normalized:
            return []

        order = f"{CONFIDENCE_SQL} DESC, weight DESC, hit_count DESC, updated_at DESC"
        rows = self._db.query_all(
            f"SELECT * FROM aliases WHERE normalized_source = ? ORDER BY {order}",
            (normalized,),
        )
        if rows:
            return self._rows_to_models(rows)

        tokens = token_key(text)
        if not tokens:
            return []
        rows = self._db.query_all(
            f"SELECT * FROM aliases WHERE token_source = ? ORDER BY {order}",
            (tokens,),
        )
        return self._rows_to_models(rows)

    def search(
        self,
        query: str = "",
        *,
        brand: str = "",
        volume_value: float | None = None,
        volume_unit: str = "",
        sort: str = "updated_desc",
        limit: int = 500,
        offset: int = 0,
    ) -> list[Alias]:
        """Ищет записи словаря для раздела «Словарь товаров».

        Поиск ведётся одновременно по системному наименованию, наименованию в
        сертификате, бренду, файлу и комментарию — без учёта регистра.

        Args:
            query: Текст поиска (пусто — без фильтра по тексту).
            brand: Точное значение бренда (пусто — без фильтра).
            volume_value: Значение объёма для фильтра (``None`` — без фильтра).
            volume_unit: Единица объёма, дополняет ``volume_value``.
            sort: Ключ сортировки (см. :data:`_SORT_EXPRESSIONS`).
            limit: Максимум записей.
            offset: Смещение для постраничной загрузки.

        Returns:
            Найденные записи.
        """
        clauses, parameters = _build_filter(query, brand, volume_value, volume_unit)
        order = _SORT_EXPRESSIONS.get(sort, _SORT_EXPRESSIONS["updated_desc"])
        sql = f"SELECT * FROM aliases{clauses} ORDER BY {order} LIMIT ? OFFSET ?"
        rows = self._db.query_all(sql, (*parameters, limit, offset))
        return self._rows_to_models(rows)

    def count_search(
        self,
        query: str = "",
        *,
        brand: str = "",
        volume_value: float | None = None,
        volume_unit: str = "",
    ) -> int:
        """Возвращает общее количество записей, подходящих под фильтр поиска.

        Args:
            query: Текст поиска.
            brand: Точное значение бренда.
            volume_value: Значение объёма для фильтра.
            volume_unit: Единица объёма.

        Returns:
            Количество подходящих записей.
        """
        clauses, parameters = _build_filter(query, brand, volume_value, volume_unit)
        return int(self._db.query_scalar(f"SELECT count(*) FROM aliases{clauses}", parameters) or 0)

    def list_all(self, *, limit: int = 0, search: str = "") -> list[Alias]:
        """Возвращает псевдонимы для отображения в интерфейсе (устаревший метод).

        Оставлен для обратной совместимости; новый код должен использовать
        :meth:`search`, поддерживающий фильтры по бренду и объёму.

        Args:
            limit: Максимум записей (0 — без ограничения).
            search: Фильтр по подстроке источника или цели.

        Returns:
            Список псевдонимов, отсортированный по дате изменения.
        """
        return self.search(search, limit=limit or 100_000)

    def list_brands(self) -> list[str]:
        """Возвращает список различных непустых брендов для фильтра.

        Returns:
            Бренды в алфавитном порядке.
        """
        rows = self._db.query_all(
            "SELECT DISTINCT brand FROM aliases WHERE brand != '' ORDER BY lower(brand)"
        )
        return [str(row["brand"]) for row in rows]

    def list_volumes(self) -> list[tuple[float, str]]:
        """Возвращает список различных объёмов для фильтра.

        Returns:
            Пары ``(значение, единица)`` в порядке возрастания.
        """
        rows = self._db.query_all(
            "SELECT DISTINCT volume_value, volume_unit FROM aliases "
            "WHERE volume_value IS NOT NULL AND volume_unit != '' "
            "ORDER BY volume_unit, volume_value"
        )
        return [(float(row["volume_value"]), str(row["volume_unit"])) for row in rows]

    def find_similar(
        self,
        source_text: str,
        target_name: str = "",
        *,
        exclude_id: int | None = None,
        threshold: float = 0.82,
        limit: int = 5,
    ) -> list[Alias]:
        """Ищет записи, похожие на предлагаемую — основа проверки дубликатов.

        Сравнение нечёткое (см. :func:`app.ai.fuzzy.similarity`): находит не
        только точные совпадения (их отклоняет уникальный индекс базы), но и
        близкие варианты вида «TP Herbal 100ml» / «TP Herbal 100 ml».

        Args:
            source_text: Предлагаемое системное наименование.
            target_name: Предлагаемое русское наименование (усиливает поиск).
            exclude_id: Идентификатор записи, которую не нужно учитывать
                (используется при редактировании — запись не сравнивается
                сама с собой).
            threshold: Минимальная оценка схожести ``[0..1]``.
            limit: Максимум возвращаемых записей.

        Returns:
            Похожие записи, отсортированные по убыванию схожести.
        """
        if not source_text.strip():
            return []
        rows = self._db.query_all("SELECT * FROM aliases")
        scored: list[tuple[float, Alias]] = []
        for row in rows:
            candidate = self._to_model(row)
            if exclude_id is not None and candidate.id == exclude_id:
                continue
            score = similarity(source_text, candidate.source_text)
            if target_name:
                score = max(score, similarity(target_name, candidate.target_name))
            if score >= threshold:
                scored.append((score, candidate))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [candidate for _, candidate in scored[:limit]]

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

    # --------------------------------------------------------- журнал и undo
    def _write_audit(
        self,
        connection: sqlite3.Connection,
        alias_id: int,
        action: AliasAuditAction,
        source_text: str,
        *,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        actor: str,
    ) -> None:
        """Записывает запись в журнал изменений внутри активной транзакции."""
        entry = AliasAuditEntry(
            alias_id=alias_id,
            action=action,
            source_text=source_text,
            before=before,
            after=after,
            actor=actor,
        )
        self._insert(connection, entry.to_row(), table="alias_audit")

    def list_audit(self, *, alias_id: int | None = None, limit: int = 200) -> list[AliasAuditEntry]:
        """Возвращает записи журнала изменений.

        Args:
            alias_id: Ограничить журнал одной записью словаря (``None`` — все).
            limit: Максимум записей.

        Returns:
            Записи журнала, новые сначала.
        """
        if alias_id is not None:
            rows = self._db.query_all(
                "SELECT * FROM alias_audit WHERE alias_id = ? ORDER BY at DESC, id DESC LIMIT ?",
                (alias_id, limit),
            )
        else:
            rows = self._db.query_all(
                "SELECT * FROM alias_audit ORDER BY at DESC, id DESC LIMIT ?", (limit,)
            )
        return [AliasAuditEntry.from_row(row) for row in rows]

    def last_audit_entry(self) -> AliasAuditEntry | None:
        """Возвращает последнее действие журнала, которое можно отменить.

        Записи со действием ``restored`` — это следы самой операции отмены,
        а не отменяемые действия сами по себе; они намеренно исключены,
        иначе после первой же отмены кнопка «Отменить» переставала бы
        находить что-либо снова, пока не произойдёт новое действие, хотя в
        истории могут быть более ранние правки, которые пользователь
        разумно ожидает отменить одну за другой.

        Returns:
            Запись журнала либо ``None``, если отменять нечего.
        """
        row = self._db.query_one(
            "SELECT * FROM alias_audit WHERE undone = 0 AND action != ? "
            "ORDER BY at DESC, id DESC LIMIT 1",
            (AliasAuditAction.RESTORED.value,),
        )
        return AliasAuditEntry.from_row(row) if row else None

    def undo(self, entry_id: int, *, actor: str = "") -> bool:
        """Отменяет одно действие журнала изменений.

        Args:
            entry_id: Идентификатор записи журнала.
            actor: Пользователь, выполнивший отмену.

        Returns:
            ``True``, если действие было отменено.
        """
        row = self._db.query_one(
            "SELECT * FROM alias_audit WHERE id = ? AND undone = 0", (entry_id,)
        )
        if row is None:
            return False
        entry = AliasAuditEntry.from_row(row)
        restored_alias_id = entry.alias_id

        with self._db.transaction(exclusive=True) as connection:
            if entry.action is AliasAuditAction.CREATED:
                connection.execute("DELETE FROM aliases WHERE id = ?", (entry.alias_id,))
            elif entry.action is AliasAuditAction.DELETED and entry.before:
                payload = {key: value for key, value in entry.before.items() if key != "id"}
                restored_alias_id = self._insert(connection, payload)
            elif entry.action is AliasAuditAction.UPDATED and entry.before:
                payload = {key: value for key, value in entry.before.items() if key != "id"}
                self._update(
                    connection,
                    payload,
                    where="id = :row_id",
                    parameters={"row_id": entry.alias_id},
                )
            else:  # pragma: no cover — защита от неполных/неизвестных записей
                return False

            connection.execute("UPDATE alias_audit SET undone = 1 WHERE id = ?", (entry.id,))
            self._write_audit(
                connection,
                restored_alias_id,
                AliasAuditAction.RESTORED,
                entry.source_text,
                before=None,
                after=entry.before,
                actor=actor or current_user(),
            )
        _LOGGER.info("Отменено действие журнала #%s (%s)", entry_id, entry.action.value)
        return True

    # ---------------------------------------------------------- импорт/экспорт
    def export_to_file(self, destination: Path) -> int:
        """Экспортирует словарь в JSON, CSV или Excel.

        Формат определяется расширением файла. Экспорт нужен как для переноса
        накопленной «памяти» между рабочими местами, так и для резервных копий.

        Args:
            destination: Путь файла назначения.

        Returns:
            Количество экспортированных записей.

        Raises:
            ExportError: При ошибке записи файла.
        """
        aliases = self.search("", limit=1_000_000)
        payload = [_to_exchange_record(alias) for alias in aliases]
        suffix = destination.suffix.lower()
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if suffix == ".csv":
                _write_csv(destination, payload)
            elif suffix in (".xlsx", ".xlsm"):
                _write_xlsx(destination, payload)
            else:
                destination.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
                )
        except OSError as error:
            raise ExportError("Не удалось экспортировать словарь", details=str(error)) from error

        _LOGGER.info("Экспортировано соответствий: %s → %s", len(payload), destination)
        return len(payload)

    def import_from_file(self, source: Path) -> tuple[int, int, int]:
        """Импортирует словарь из JSON, CSV или Excel.

        Связь с сертификатом восстанавливается по имени PDF-файла, поэтому
        файл переносим между машинами с разными базами. Записи, совпадающие
        по ключу «наименование + сертификат» с уже существующими, сливаются
        (обновляются), а не дублируются — счётчик применений при этом берётся
        максимальный из двух источников.

        Args:
            source: Путь файла-источника.

        Returns:
            Тройка ``(добавлено, объединено с существующими, пропущено)``.

        Raises:
            ExportError: Если файл нечитаем или имеет неверный формат.
        """
        suffix = source.suffix.lower()
        try:
            if suffix == ".csv":
                with source.open("r", encoding="utf-8-sig", newline="") as handle:
                    records: list[dict[str, Any]] = list(csv.DictReader(handle, delimiter=";"))
            elif suffix in (".xlsx", ".xlsm"):
                records = _read_xlsx(source)
            else:
                records = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, csv.Error) as error:
            raise ExportError("Не удалось прочитать файл словаря", details=str(error)) from error

        if not isinstance(records, list):
            raise ExportError("Файл словаря имеет неверный формат")

        added = 0
        merged = 0
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
                "SELECT id, product_name, brand, volume_value, volume_unit "
                "FROM certificates WHERE pdf_name = ? ORDER BY is_active DESC LIMIT 1",
                (pdf_name,),
            )
            if certificate_row is None:
                skipped += 1
                continue

            certificate_id = int(certificate_row["id"])
            was_existing = (
                self.find_exact_target(normalize(source_text), certificate_id) is not None
            )
            self.save(
                Alias(
                    source_text=source_text,
                    certificate_id=certificate_id,
                    target_name=str(record.get("target_name") or certificate_row["product_name"]),
                    target_pdf_name=pdf_name,
                    brand=str(record.get("brand") or certificate_row["brand"] or ""),
                    volume_value=_to_float(record.get("volume_value"))
                    or certificate_row["volume_value"],
                    volume_unit=str(
                        record.get("volume_unit") or certificate_row["volume_unit"] or ""
                    ),
                    weight=float(record.get("weight") or 1.0),
                    note=str(record.get("note") or ""),
                )
            )
            if was_existing:
                merged += 1
            else:
                added += 1

        _LOGGER.info(
            "Импорт словаря: добавлено %s, объединено %s, пропущено %s", added, merged, skipped
        )
        return (added, merged, skipped)


# --------------------------------------------------------------------------- #
# Вспомогательные функции модуля
# --------------------------------------------------------------------------- #
def _build_filter(
    query: str, brand: str, volume_value: float | None, volume_unit: str
) -> tuple[str, list[Any]]:
    """Строит условие ``WHERE`` и параметры для поиска по словарю."""
    conditions: list[str] = []
    parameters: list[Any] = []

    text = query.strip().lower()
    if text:
        pattern = f"%{text}%"
        conditions.append(
            "(lower(source_text) LIKE ? OR lower(target_name) LIKE ? OR lower(brand) LIKE ? "
            "OR lower(target_pdf_name) LIKE ? OR lower(note) LIKE ?)"
        )
        parameters.extend([pattern, pattern, pattern, pattern, pattern])

    if brand:
        conditions.append("brand = ?")
        parameters.append(brand)

    if volume_value is not None:
        conditions.append("volume_value = ? AND volume_unit = ?")
        parameters.extend([volume_value, volume_unit])

    clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    return clause, parameters


def _to_exchange_record(alias: Alias) -> dict[str, Any]:
    """Формирует запись обмена (экспорт) из псевдонима."""
    return {
        "source_text": alias.source_text,
        "target_name": alias.target_name,
        "target_pdf_name": alias.target_pdf_name,
        "brand": alias.brand,
        "volume_value": alias.volume_value,
        "volume_unit": alias.volume_unit,
        "weight": alias.weight,
        "hit_count": alias.hit_count,
        "is_manual": int(alias.is_manual),
        "note": alias.note,
        "created_at": alias.created_at.isoformat(timespec="seconds"),
    }


def _to_float(value: Any) -> float | None:
    """Приводит значение к ``float``, возвращая ``None`` при неудаче."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _write_csv(destination: Path, payload: list[dict[str, Any]]) -> None:
    """Записывает записи обмена в CSV."""
    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_EXCHANGE_FIELDS), delimiter=";")
        writer.writeheader()
        writer.writerows(payload)


def _write_xlsx(destination: Path, payload: list[dict[str, Any]]) -> None:
    """Записывает записи обмена в Excel."""
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Словарь соответствий"
    sheet.append(list(_EXCHANGE_FIELDS))
    for record in payload:
        sheet.append([record.get(field) for field in _EXCHANGE_FIELDS])
    for column_cells in sheet.columns:
        length = max((len(str(cell.value)) for cell in column_cells if cell.value), default=10)
        sheet.column_dimensions[column_cells[0].column_letter].width = min(60, max(12, length + 2))
    workbook.save(destination)


def _read_xlsx(source: Path) -> list[dict[str, Any]]:
    """Читает записи обмена из Excel."""
    from openpyxl import load_workbook

    workbook = load_workbook(source, read_only=True, data_only=True)
    try:
        sheet = workbook.active
        rows = sheet.iter_rows(values_only=True)
        headers = [str(value or "").strip() for value in next(rows, ())]
        records: list[dict[str, Any]] = []
        for row in rows:
            if not any(value is not None and str(value).strip() for value in row):
                continue
            records.append(dict(zip(headers, row, strict=False)))
        return records
    finally:
        workbook.close()
