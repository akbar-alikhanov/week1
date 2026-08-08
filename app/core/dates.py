"""Разбор и сравнение дат из русскоязычных документов.

Сроки в сертификатах записаны как минимум пятью способами: ``31.12.2029``,
``2029-12-31``, ``«31» декабря 2029 г.``, ``31 дек. 2029``, ``12.2029``.
Модуль приводит всё это к :class:`datetime.date` и предоставляет функции
оценки близости сроков, используемые при ранжировании кандидатов.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final

from dateutil.relativedelta import relativedelta

# --------------------------------------------------------------------------- #
# Словари месяцев
# --------------------------------------------------------------------------- #
_MONTHS: Final[dict[str, int]] = {
    "январ": 1,
    "феврал": 2,
    "март": 3,
    "апрел": 4,
    "мая": 5,
    "май": 5,
    "июн": 6,
    "июл": 7,
    "август": 8,
    "сентябр": 9,
    "октябр": 10,
    "ноябр": 11,
    "декабр": 12,
    "yanvar": 1,
    "fevral": 2,
    "mart": 3,
    "aprel": 4,
    "iyun": 6,
    "iyul": 7,
    "avgust": 8,
    "sentyabr": 9,
    "oktyabr": 10,
    "noyabr": 11,
    "dekabr": 12,
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "may": 5,
}

_RE_NUMERIC: Final[re.Pattern[str]] = re.compile(
    r"\b(?P<day>[0-3]?\d)[./\-](?P<month>[01]?\d)[./\-](?P<year>\d{4}|\d{2})\b"
)
_RE_ISO: Final[re.Pattern[str]] = re.compile(
    r"\b(?P<year>\d{4})[.\-/](?P<month>[01]?\d)[.\-/](?P<day>[0-3]?\d)\b"
)
#: Текстовая дата: «31» декабря 2029 г., 31 дек. 2029, 5 May 2029.
#: Месяц захватывается как произвольное слово и разбирается по префиксу —
#: это покрывает и полные названия, и общепринятые сокращения.
_RE_TEXTUAL: Final[re.Pattern[str]] = re.compile(
    r"[«\"']?\b(?P<day>[0-3]?\d)\b[»\"']?\s*(?P<month>[а-яёa-z]{3,12})\.?\s*(?P<year>\d{4})",
    re.IGNORECASE | re.UNICODE,
)
_RE_MONTH_YEAR: Final[re.Pattern[str]] = re.compile(r"\b(?P<month>[01]?\d)[./\-](?P<year>\d{4})\b")
_RE_DURATION: Final[re.Pattern[str]] = re.compile(
    r"\b(?P<amount>\d{1,2})\s*(?P<unit>лет|год[а]?|мес(?:яц[аев]*)?|year[s]?|month[s]?)\b",
    re.IGNORECASE,
)

#: Разумные границы дат в документах — отсекают номера и артикулы.
_MIN_YEAR: Final[int] = 1995
_MAX_YEAR: Final[int] = 2099


@dataclass(frozen=True, slots=True)
class DateMatch:
    """Дата, найденная в тексте, вместе с её позицией.

    Attributes:
        value: Разобранная дата.
        raw: Исходный фрагмент текста.
        start: Индекс начала фрагмента в тексте.
        end: Индекс конца фрагмента в тексте.
    """

    value: date
    raw: str
    start: int
    end: int


def resolve_month(token: str) -> int:
    """Определяет номер месяца по слову или его сокращению.

    Args:
        token: Слово из текста («декабря», «дек», «December», «dec»).

    Returns:
        Номер месяца ``1..12`` либо ``0``, если слово месяцем не является.
    """
    word = token.strip(" .«»\"'").lower().replace("ё", "е")
    if not word:
        return 0
    if word in _MONTHS:
        return _MONTHS[word]
    for key, number in _MONTHS.items():
        if word.startswith(key):
            return number
    for key, number in _MONTHS.items():
        if key.startswith(word):
            return number
    return 0


def _safe_date(year: int, month: int, day: int) -> date | None:
    """Создаёт дату, возвращая ``None`` при некорректных компонентах."""
    if year < 100:
        year += 2000 if year < 80 else 1900
    if not (_MIN_YEAR <= year <= _MAX_YEAR) or not (1 <= month <= 12) or not (1 <= day <= 31):
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def find_dates(text: str | None) -> list[DateMatch]:
    """Находит в тексте все распознаваемые даты.

    Args:
        text: Произвольный текст.

    Returns:
        Список найденных дат, отсортированный по позиции в тексте.
        Пересекающиеся совпадения устраняются (побеждает более длинное).
    """
    if not text:
        return []

    matches: list[DateMatch] = []

    def _collect(pattern: re.Pattern[str], *, with_day: bool = True) -> None:
        for match in pattern.finditer(text):
            groups = match.groupdict()
            month_raw = groups["month"]
            month = int(month_raw) if month_raw.isdigit() else resolve_month(month_raw)
            if month == 0:
                continue
            day = int(groups["day"]) if with_day else 1
            parsed = _safe_date(int(groups["year"]), month, day)
            if parsed is not None:
                matches.append(DateMatch(parsed, match.group(0), match.start(), match.end()))

    _collect(_RE_ISO)
    _collect(_RE_TEXTUAL)
    _collect(_RE_NUMERIC)
    _collect(_RE_MONTH_YEAR, with_day=False)

    matches.sort(key=lambda item: (item.start, -(item.end - item.start)))
    deduplicated: list[DateMatch] = []
    last_end = -1
    for match in matches:
        if match.start >= last_end:
            deduplicated.append(match)
            last_end = match.end
    return deduplicated


def parse_date(value: object) -> date | None:
    """Приводит произвольное значение к :class:`datetime.date`.

    Поддерживаются: ``date``/``datetime``, значения ячеек Excel (в том числе
    числовые serial-даты) и строки в любом из распознаваемых форматов.

    Args:
        value: Значение из Excel, БД или текста PDF.

    Returns:
        Дата либо ``None``, если распознать не удалось.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        # Excel-serial: отсчёт от 1899-12-30 (с учётом «бага 1900 года»).
        if 1 <= float(value) <= 80_000:
            return date(1899, 12, 30) + relativedelta(days=int(value))
        return None

    text = str(value).strip()
    if not text:
        return None
    found = find_dates(text)
    return found[0].value if found else None


def parse_duration(text: str | None) -> relativedelta | None:
    """Разбирает срок годности, заданный длительностью («3 года», «18 мес.»).

    Args:
        text: Фрагмент текста сертификата.

    Returns:
        Относительный интервал либо ``None``.
    """
    if not text:
        return None
    match = _RE_DURATION.search(text)
    if match is None:
        return None
    amount = int(match.group("amount"))
    unit = match.group("unit").lower()
    if unit.startswith(("год", "лет", "year")):
        return relativedelta(years=amount)
    return relativedelta(months=amount)


def days_between(left: date | None, right: date | None) -> int | None:
    """Возвращает разницу в днях между двумя датами.

    Args:
        left: Уменьшаемое.
        right: Вычитаемое.

    Returns:
        ``(left - right).days`` либо ``None``, если одна из дат отсутствует.
    """
    if left is None or right is None:
        return None
    return (left - right).days


#: Оценка срока годности на границе допуска (``difference == tolerance_days``)
#: — сертификат ещё в пределах разрешённого окна, но уже не идеальный.
_EXPIRY_BOUNDARY_SCORE: Final[float] = 0.85


def expiry_similarity(
    certificate_expiry: date | None,
    requested_expiry: date | None,
    *,
    reference: date | None = None,
    tolerance_days: int = 45,
    missing_score: float = 0.6,
    expired_score: float = 0.0,
) -> float:
    """Оценивает пригодность срока действия сертификата.

    Логика соответствует практике работы аптечного склада:

    * сертификат, истёкший на дату обработки, непригоден → ``expired_score``;
    * если в заказе указан требуемый срок, сертификат считается подходящим
      ТОЛЬКО если ``abs(certificate_expiry - requested_expiry) <= tolerance_days``
      (год учитывается — сравниваются полные даты, а не день/месяц отдельно).
      В пределах этого окна оценка плавно снижается от ``1.0`` (точное
      совпадение) до ``_EXPIRY_BOUNDARY_SCORE`` на самой границе. За пределами
      окна сертификат считается полностью неподходящим и получает ``0.0`` —
      не пониженную, а именно нулевую оценку, чтобы такой кандидат не мог
      быть выбран ни при каких весах. Безусловное исключение таких
      кандидатов из списка вообще выполняется отдельно, на уровне
      :func:`~app.ai.scorer.is_hard_mismatch` — эта функция обеспечивает
      согласованную (нулевую) оценку на тот случай, если её всё же вызовут
      для кандидата за пределами допуска напрямую;
    * если требуемый срок не указан, предпочитается сертификат с ближайшим
      сроком окончания (принцип FEFO — first expired, first out), при этом
      слишком «короткие» сертификаты не штрафуются, поскольку они валидны.
      Это ограничение (окно допуска) на FEFO-ветку не распространяется — она
      применяется только когда в заказе вообще нет требуемого срока, поэтому
      сравнивать её не с чем.

    Args:
        certificate_expiry: Срок из сертификата.
        requested_expiry: Срок, указанный в строке заказа (если есть).
        reference: Дата, относительно которой проверяется валидность
            (по умолчанию — сегодня).
        tolerance_days: Ширина окна допуска в днях (в каждую сторону).
        missing_score: Оценка при отсутствии данных о сроке.
        expired_score: Оценка для просроченного сертификата.

    Returns:
        Оценка в диапазоне ``[0.0, 1.0]``.
    """
    if certificate_expiry is None:
        return missing_score

    today = reference or date.today()
    if certificate_expiry < today:
        return expired_score

    if requested_expiry is None:
        # FEFO: чем ближе срок окончания, тем выше приоритет расходования,
        # но валидный сертификат всегда получает высокую базовую оценку.
        remaining = (certificate_expiry - today).days
        horizon = max(tolerance_days * 10, 365)
        proximity = 1.0 - min(remaining, horizon) / horizon
        return round(0.80 + 0.20 * proximity, 6)

    difference = abs((certificate_expiry - requested_expiry).days)
    if difference == 0:
        return 1.0

    window = max(1, tolerance_days)
    if difference > window:
        return 0.0

    return round(1.0 - (1.0 - _EXPIRY_BOUNDARY_SCORE) * (difference / window), 6)


def format_date(value: date | None, *, fmt: str = "%d.%m.%Y") -> str:
    """Форматирует дату для интерфейса и Excel.

    Args:
        value: Дата либо ``None``.
        fmt: Строка формата :func:`datetime.date.strftime`.

    Returns:
        Отформатированная дата или ``"—"``.
    """
    return value.strftime(fmt) if value is not None else "—"
