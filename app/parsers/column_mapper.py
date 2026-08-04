"""Автоматическое распознавание структуры файла заказа.

Каждый поставщик и каждый менеджер оформляют заказ по-своему: шапка может
начинаться с первой строки или с двенадцатой, названия колонок различаются
(«Наименование», «Товар», «Продукция», «Mahsulot nomi»), часть колонок
отсутствует. Требовать от пользователя настраивать соответствие вручную —
значит вернуть ему те самые минуты, ради экономии которых написана программа.

Модуль решает две задачи: находит строку заголовка и сопоставляет колонки
их ролям.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Final

from app.core.text import normalize

_LOGGER = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Роли колонок
# --------------------------------------------------------------------------- #
ROLE_PRODUCT: Final[str] = "product"
ROLE_QUANTITY: Final[str] = "quantity"
ROLE_UNIT: Final[str] = "unit"
ROLE_VOLUME: Final[str] = "volume"
ROLE_BRAND: Final[str] = "brand"
ROLE_CODE: Final[str] = "code"
ROLE_PRICE: Final[str] = "price"
ROLE_NUMBER: Final[str] = "number"
ROLE_CERTIFICATE: Final[str] = "certificate"
ROLE_EXPIRY: Final[str] = "expiry"

#: Ключевые слова заголовков для каждой роли.
#: Сопоставление идёт по вхождению подстроки в нормализованный заголовок.
_ROLE_KEYWORDS: Final[dict[str, tuple[str, ...]]] = {
    ROLE_PRODUCT: (
        "наименование товара",
        "наименование продукции",
        "наименование",
        "товар",
        "продукция",
        "название",
        "препарат",
        "номенклатура",
        "mahsulot nomi",
        "mahsulot",
        "tovar",
        "product name",
        "product",
        "item",
        "description",
    ),
    ROLE_CERTIFICATE: (
        "сертификат соответствия",
        "сертификат",
        "серт",
        "номер сертификата",
        "sertifikat",
        "certificate",
    ),
    ROLE_EXPIRY: (
        "срок сертификата",
        "срок действия",
        "срок годности",
        "годен до",
        "действителен до",
        "срок",
        "amal qilish",
        "expiry",
        "valid",
    ),
    ROLE_QUANTITY: (
        "кол во",
        "количество",
        "колво",
        "кол",
        "qty",
        "quantity",
        "miqdor",
        "soni",
    ),
    ROLE_UNIT: ("ед изм", "единица", "ед", "birlik", "unit", "uom"),
    ROLE_VOLUME: ("объем", "фасовка", "емкость", "вес", "hajm", "volume", "size", "pack"),
    ROLE_BRAND: ("бренд", "торговая марка", "марка", "brend", "brand", "trademark"),
    ROLE_CODE: ("артикул", "код товара", "код", "sku", "article", "kod"),
    ROLE_PRICE: ("цена", "стоимость", "сумма", "narx", "price", "amount", "cost"),
    ROLE_NUMBER: ("№", "n п п", "п п", "номер", "no", "tartib"),
}

#: Роли, которые обязаны быть найдены для успешного разбора.
REQUIRED_ROLES: Final[frozenset[str]] = frozenset({ROLE_PRODUCT})

#: Максимальное количество строк, просматриваемых в поисках заголовка.
MAX_HEADER_SCAN_ROWS: Final[int] = 30

_RE_NUMERIC_ONLY: Final[re.Pattern[str]] = re.compile(r"^[\d\s.,%-]+$")


@dataclass(slots=True)
class ColumnMapping:
    """Результат распознавания структуры листа.

    Attributes:
        header_row: Номер строки заголовка (1-based).
        columns: Соответствие «роль → индекс колонки» (0-based).
        headers: Заголовки колонок в исходном порядке.
        confidence: Уверенность распознавания ``[0..1]``.
    """

    header_row: int = 0
    columns: dict[str, int] = field(default_factory=dict)
    headers: list[str] = field(default_factory=list)
    confidence: float = 0.0

    @property
    def is_valid(self) -> bool:
        """Признак того, что найдены все обязательные колонки."""
        return all(role in self.columns for role in REQUIRED_ROLES)

    def index_of(self, role: str) -> int | None:
        """Возвращает индекс колонки для роли.

        Args:
            role: Идентификатор роли.

        Returns:
            Индекс колонки (0-based) либо ``None``.
        """
        return self.columns.get(role)

    def describe(self) -> str:
        """Возвращает описание распознанной структуры для журнала."""
        if not self.columns:
            return "структура не распознана"
        mapping = ", ".join(
            f"{role}→{_column_letter(index)}" for role, index in sorted(self.columns.items())
        )
        return f"строка заголовка {self.header_row}; {mapping}"


def _column_letter(index: int) -> str:
    """Преобразует индекс колонки (0-based) в буквенное обозначение Excel."""
    letters = ""
    number = index + 1
    while number > 0:
        number, remainder = divmod(number - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _cell_text(value: Any) -> str:
    """Приводит значение ячейки к строке заголовка."""
    if value is None:
        return ""
    text = str(value).strip()
    return normalize(text) if text else ""


def _match_role(header: str) -> tuple[str, int] | None:
    """Определяет роль колонки по её заголовку.

    Args:
        header: Нормализованный заголовок.

    Returns:
        Пара ``(роль, длина совпавшего ключевого слова)`` либо ``None``.
        Длина используется как приоритет: «срок сертификата» точнее, чем «срок».
    """
    if not header:
        return None
    best: tuple[str, int] | None = None
    for role, keywords in _ROLE_KEYWORDS.items():
        for keyword in keywords:
            normalized_keyword = normalize(keyword)
            if not normalized_keyword:
                continue
            if normalized_keyword in header and (best is None or len(normalized_keyword) > best[1]):
                best = (role, len(normalized_keyword))
    return best


def score_header_row(values: list[Any]) -> tuple[float, dict[str, int]]:
    """Оценивает, насколько строка похожа на заголовок таблицы.

    Args:
        values: Значения ячеек строки.

    Returns:
        Пара ``(оценка, соответствие ролей колонкам)``.
    """
    columns: dict[str, int] = {}
    priorities: dict[str, int] = {}
    filled = 0
    textual = 0

    for index, raw in enumerate(values):
        header = _cell_text(raw)
        if not header:
            continue
        filled += 1
        if not _RE_NUMERIC_ONLY.match(header):
            textual += 1
        matched = _match_role(header)
        if matched is None:
            continue
        role, priority = matched
        if role not in columns or priority > priorities.get(role, 0):
            columns[role] = index
            priorities[role] = priority

    if not filled:
        return (0.0, {})

    role_score = min(1.0, len(columns) / 4.0)
    text_ratio = textual / filled
    required_bonus = 0.5 if ROLE_PRODUCT in columns else 0.0
    score = role_score * 0.5 + text_ratio * 0.2 + required_bonus
    return (round(score, 4), columns)


def detect_mapping(rows: list[list[Any]]) -> ColumnMapping:
    """Определяет строку заголовка и роли колонок.

    Args:
        rows: Первые строки листа (значения ячеек).

    Returns:
        Распознанная структура; ``ColumnMapping.is_valid`` сообщает об успехе.
    """
    best = ColumnMapping()
    for row_index, values in enumerate(rows[:MAX_HEADER_SCAN_ROWS]):
        score, columns = score_header_row(values)
        if score > best.confidence and ROLE_PRODUCT in columns:
            best = ColumnMapping(
                header_row=row_index + 1,
                columns=columns,
                headers=[str(value).strip() if value is not None else "" for value in values],
                confidence=score,
            )

    if not best.is_valid:
        fallback = _fallback_mapping(rows)
        if fallback is not None:
            _LOGGER.info("Заголовок не распознан — применена эвристика по содержимому")
            return fallback

    _LOGGER.debug("Структура заказа: %s", best.describe())
    return best


def _fallback_mapping(rows: list[list[Any]]) -> ColumnMapping | None:
    """Определяет колонку с наименованием по содержимому, без заголовка.

    Логика: колонка товара — та, где больше всего длинных текстовых значений.

    Args:
        rows: Строки листа.

    Returns:
        Структура с единственной ролью ``product`` либо ``None``.
    """
    if not rows:
        return None

    width = max((len(row) for row in rows), default=0)
    if width == 0:
        return None

    scores = [0] * width
    for row in rows[:60]:
        for index, value in enumerate(row):
            if index >= width or value is None:
                continue
            text = str(value).strip()
            if len(text) >= 8 and sum(character.isalpha() for character in text) >= 5:
                scores[index] += 1

    best_index = max(range(width), key=lambda index: scores[index])
    if scores[best_index] < 3:
        return None

    return ColumnMapping(
        header_row=0,
        columns={ROLE_PRODUCT: best_index},
        headers=[""] * width,
        confidence=0.3,
    )
