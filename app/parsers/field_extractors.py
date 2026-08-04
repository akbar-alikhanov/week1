"""Извлечение структурированных полей из текста сертификата.

Сертификаты соответствия не имеют единого машинночитаемого формата: это
сканы и печатные формы разных органов сертификации. Устойчивое извлечение
строится на трёх принципах:

1. **Опора на метки, а не на координаты.** Ищем подписи полей («Продукция»,
   «Изготовитель», «Срок действия») и берём текст после них.
2. **Явные границы значения.** Значение заканчивается там, где начинается
   следующая известная метка — это защищает от «слипания» полей.
3. **Каскад стратегий.** Если метка не найдена, применяется эвристика
   (самая длинная содержательная строка, имя файла, все даты документа).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Final

from app.core.dates import find_dates, parse_duration
from app.core.text import collapse_whitespace

# --------------------------------------------------------------------------- #
# Метки полей
# --------------------------------------------------------------------------- #
#: Метки наименования продукции (в порядке убывания надёжности).
PRODUCT_LABELS: Final[tuple[str, ...]] = (
    "наименование продукции",
    "наименование товара",
    "наименование и обозначение продукции",
    "продукция",
    "товар",
    "mahsulot nomi",
    "mahsulot",
    "product name",
    "product",
)

#: Метки номера сертификата.
NUMBER_LABELS: Final[tuple[str, ...]] = (
    "сертификат соответствия",
    "регистрационный номер",
    "рег. номер",
    "рег номер",
    "номер сертификата",
    "сертификат №",
    "muvofiqlik sertifikati",
    "certificate no",
    "certificate number",
)

#: Метки изготовителя.
MANUFACTURER_LABELS: Final[tuple[str, ...]] = (
    "изготовитель",
    "производитель",
    "ishlab chiqaruvchi",
    "manufacturer",
)

#: Метки заявителя.
APPLICANT_LABELS: Final[tuple[str, ...]] = (
    "заявитель",
    "получатель",
    "ariza beruvchi",
    "applicant",
)

#: Метки органа по сертификации.
ISSUER_LABELS: Final[tuple[str, ...]] = (
    "орган по сертификации",
    "выдан",
    "sertifikatlashtirish organi",
    "issued by",
)

#: Метки торговой марки.
BRAND_LABELS: Final[tuple[str, ...]] = (
    "торговая марка",
    "товарный знак",
    "тм",
    "бренд",
    "savdo belgisi",
    "trademark",
    "brand",
)

#: Метки страны.
COUNTRY_LABELS: Final[tuple[str, ...]] = ("страна", "страна происхождения", "mamlakat", "country")

#: Все известные метки — служат границами значения.
_ALL_LABELS: Final[tuple[str, ...]] = (
    PRODUCT_LABELS
    + NUMBER_LABELS
    + MANUFACTURER_LABELS
    + APPLICANT_LABELS
    + ISSUER_LABELS
    + BRAND_LABELS
    + COUNTRY_LABELS
    + (
        "соответствует требованиям",
        "код тн вэд",
        "тн вэд",
        "срок действия",
        "срок годности",
        "дата регистрации",
        "серийный выпуск",
        "основание выдачи",
        "схема сертификации",
        "дополнительная информация",
        "руководитель",
        "эксперт",
        "подпись",
        "м п",
    )
)

# --------------------------------------------------------------------------- #
# Регулярные выражения
# --------------------------------------------------------------------------- #
#: Номер сертификата: «№ UZ.AMT.01.123.45678», «№ 183255», «RU C-CN.АБ12.В.34567».
_RE_CERT_NUMBER: Final[re.Pattern[str]] = re.compile(
    r"№\s*([A-ZА-Я0-9][A-ZА-Я0-9./\-]{3,40})", re.IGNORECASE | re.UNICODE
)
_RE_CERT_NUMBER_CODED: Final[re.Pattern[str]] = re.compile(
    r"\b([A-Z]{2}[./][A-Z0-9]{2,6}(?:[./][A-Z0-9]{1,8}){1,5})\b", re.IGNORECASE
)
_RE_FILENAME_NUMBER: Final[re.Pattern[str]] = re.compile(r"([A-Za-z0-9][A-Za-z0-9\-]{3,30})")

#: Диапазон действия: «с 01.02.2024 по 31.01.2029».
_RE_VALIDITY_RANGE: Final[re.Pattern[str]] = re.compile(
    r"\bс\b(?P<from>.{0,40}?)\bпо\b(?P<to>.{0,40})", re.IGNORECASE | re.DOTALL
)

#: Контекст срока окончания.
_EXPIRY_CONTEXTS: Final[tuple[str, ...]] = (
    "действителен до",
    "действителен по",
    "действительно до",
    "срок действия до",
    "срок действия по",
    "срок годности до",
    "срок годности",
    "срок действия",
    "amal qilish muddati",
    "valid until",
)

#: Контекст даты выдачи.
_ISSUE_CONTEXTS: Final[tuple[str, ...]] = (
    "дата регистрации",
    "дата выдачи",
    "зарегистрирован",
    "выдан",
    "berilgan sana",
    "date of issue",
)

#: Торговая марка в кавычках.
_RE_QUOTED: Final[re.Pattern[str]] = re.compile(r"[«\"'”“]([^«»\"'”“]{2,60})[»\"'”“]")

#: Мусорные строки, которые не могут быть наименованием продукции.
_RE_JUNK_LINE: Final[re.Pattern[str]] = re.compile(
    r"^[\s\d.,;:_\-–—/\\|№*()\[\]]*$|^(стр|страница|page)\b", re.IGNORECASE
)


@dataclass(slots=True)
class ExtractedFields:
    """Результат извлечения полей из текста сертификата.

    Attributes:
        product_name: Наименование продукции.
        certificate_number: Номер сертификата.
        certificate_date: Дата выдачи.
        valid_from: Начало срока действия.
        expiry_date: Окончание срока действия.
        brand: Торговая марка.
        manufacturer: Изготовитель.
        applicant: Заявитель.
        issued_by: Орган по сертификации.
        country: Страна происхождения.
        confidence: Доля успешно извлечённых ключевых полей ``[0..1]``.
        warnings: Замечания, попадающие в журнал индексации.
    """

    product_name: str = ""
    certificate_number: str = ""
    certificate_date: date | None = None
    valid_from: date | None = None
    expiry_date: date | None = None
    brand: str = ""
    manufacturer: str = ""
    applicant: str = ""
    issued_by: str = ""
    country: str = ""
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)


def clean_value(value: str, *, max_length: int = 300) -> str:
    """Очищает извлечённое значение от служебных символов.

    Args:
        value: Сырое значение.
        max_length: Максимальная длина результата.

    Returns:
        Очищенная строка.
    """
    text = collapse_whitespace(value)
    text = text.strip(" :;-–—*.,\t«»\"'")
    text = re.sub(r"\s{2,}", " ", text)
    return text[:max_length].strip()


def split_lines(text: str) -> list[str]:
    """Разбивает текст PDF на осмысленные строки.

    Args:
        text: Текст, извлечённый из PDF.

    Returns:
        Список непустых строк без лишних пробелов.
    """
    lines: list[str] = []
    for raw in text.replace("\r", "\n").split("\n"):
        line = collapse_whitespace(raw)
        if line:
            lines.append(line)
    return lines


def _is_label_line(line: str, *, exclude: tuple[str, ...] = ()) -> bool:
    """Проверяет, начинается ли строка с известной метки поля."""
    lowered = line.lower()
    return any(lowered.startswith(label) for label in _ALL_LABELS if label not in exclude)


def _is_confident_label_match(line: str, position: int, end: int) -> bool:
    """Отличает настоящую метку поля от случайного слова внутри предложения.

    Слова вроде «товар» или «страна» — обычная лексика, которая закономерно
    встречается в преамбуле сертификата («...нижеуказанный товар соответствует
    требованиям...») до настоящей метки «Продукция:». Без этой проверки такое
    предложение обрывалось бы посередине, а «наименованием товара» становился
    случайный хвост фразы. Совпадение считается меткой, только если оно стоит
    в начале строки (после короткого маркера вроде «1.» или «-») либо сразу
    сопровождается разделителем «:», «-», «–» или «—».

    Args:
        line: Строка целиком.
        position: Индекс начала найденного вхождения метки.
        end: Индекс конца найденного вхождения метки.

    Returns:
        ``True``, если вхождение похоже на настоящую метку поля.
    """
    prefix = line[:position]
    if len(prefix) <= 3 and not any(character.isalpha() for character in prefix):
        return True
    tail = line[end : end + 2].lstrip()
    return bool(tail) and tail[0] in ":-–—"


def extract_labeled_value(
    lines: list[str],
    labels: tuple[str, ...],
    *,
    max_continuation_lines: int = 3,
    max_length: int = 300,
) -> str:
    """Извлекает значение поля по его метке.

    Значение берётся из остатка строки после метки; если остаток пуст —
    из следующих строк, пока не встретится другая метка.

    Args:
        lines: Строки документа.
        labels: Возможные метки поля.
        max_continuation_lines: Сколько строк допускается склеивать.
        max_length: Максимальная длина значения.

    Returns:
        Очищенное значение либо пустая строка.
    """
    # Длинные метки проверяются первыми: иначе «страна» перехватит значение
    # у более точной метки «страна происхождения».
    ordered_labels = sorted(labels, key=len, reverse=True)
    for index, line in enumerate(lines):
        lowered = line.lower()
        for label in ordered_labels:
            position = lowered.find(label)
            if position < 0:
                continue
            label_end = position + len(label)
            if not _is_confident_label_match(line, position, label_end):
                continue
            remainder = clean_value(line[label_end:], max_length=max_length)
            if len(remainder) >= 3:
                return remainder

            collected: list[str] = []
            for offset in range(1, max_continuation_lines + 1):
                if index + offset >= len(lines):
                    break
                candidate = lines[index + offset]
                if _is_label_line(candidate, exclude=labels) or _RE_JUNK_LINE.match(candidate):
                    break
                collected.append(candidate)
                if len(" ".join(collected)) > 40:
                    break
            if collected:
                return clean_value(" ".join(collected), max_length=max_length)
    return ""


def extract_certificate_number(text: str, *, filename: str = "") -> str:
    """Извлекает номер сертификата.

    Порядок стратегий: явная метка со знаком «№» → кодированный номер вида
    ``UZ.AMT.01.123`` → имя файла (на практике оно совпадает с номером).

    Args:
        text: Текст документа.
        filename: Имя PDF-файла без пути.

    Returns:
        Номер сертификата либо пустая строка.
    """
    head = text[:2500]
    match = _RE_CERT_NUMBER.search(head)
    if match:
        candidate = clean_value(match.group(1), max_length=48)
        if len(candidate) >= 4 and any(ch.isdigit() for ch in candidate):
            return candidate

    coded = _RE_CERT_NUMBER_CODED.search(head)
    if coded:
        return clean_value(coded.group(1), max_length=48)

    if filename:
        stem = filename.rsplit(".", 1)[0]
        name_match = _RE_FILENAME_NUMBER.search(stem)
        if name_match and any(ch.isdigit() for ch in name_match.group(1)):
            return clean_value(name_match.group(1), max_length=48)
    return ""


def _dates_near(text: str, contexts: tuple[str, ...], *, window: int = 120) -> list[date]:
    """Возвращает даты, встречающиеся рядом с указанными формулировками."""
    lowered = text.lower()
    found: list[date] = []
    for context in contexts:
        start = 0
        while True:
            position = lowered.find(context, start)
            if position < 0:
                break
            fragment = text[position : position + len(context) + window]
            found.extend(match.value for match in find_dates(fragment))
            start = position + len(context)
    return found


def extract_dates(text: str) -> tuple[date | None, date | None, date | None]:
    """Извлекает дату выдачи, начало и окончание срока действия.

    Args:
        text: Текст документа.

    Returns:
        Кортеж ``(дата выдачи, начало действия, окончание действия)``.
    """
    all_dates = [match.value for match in find_dates(text)]
    if not all_dates:
        return (None, None, None)

    expiry_candidates = _dates_near(text, _EXPIRY_CONTEXTS)
    issue_candidates = _dates_near(text, _ISSUE_CONTEXTS)

    valid_from: date | None = None
    expiry: date | None = None

    range_match = _RE_VALIDITY_RANGE.search(text)
    if range_match:
        from_dates = find_dates(range_match.group("from"))
        to_dates = find_dates(range_match.group("to"))
        if from_dates and to_dates:
            valid_from = from_dates[-1].value
            expiry = to_dates[0].value

    if expiry is None and expiry_candidates:
        # Из дат рядом с формулировкой срока берём самую позднюю: именно она
        # означает окончание действия, а не дату начала.
        expiry = max(expiry_candidates)

    issued = min(issue_candidates) if issue_candidates else None

    if expiry is None:
        latest = max(all_dates)
        if latest > date.today():
            expiry = latest

    if issued is None:
        # Дату выдачи берём только из дат, предшествующих окончанию срока.
        # Если такой нет, поле остаётся пустым: считать дату окончания датой
        # выдачи хуже, чем честно признать её неизвестной.
        earlier = [value for value in all_dates if expiry is None or value < expiry]
        issued = min(earlier) if earlier else None

    if valid_from is None:
        valid_from = issued

    if expiry is None:
        duration = parse_duration(text)
        if duration is not None and issued is not None:
            expiry = issued + duration

    return (issued, valid_from, expiry)


def extract_product_name(lines: list[str], *, filename: str = "") -> str:
    """Извлекает наименование продукции.

    Args:
        lines: Строки документа.
        filename: Имя PDF-файла — используется как запасной вариант.

    Returns:
        Наименование продукции либо имя файла без расширения.
    """
    value = extract_labeled_value(lines, PRODUCT_LABELS, max_continuation_lines=4)
    if len(value) >= 3:
        return _trim_product_name(value)

    # Эвристика: самая длинная содержательная строка в первой трети документа,
    # не являющаяся меткой и не состоящая из служебных символов.
    horizon = lines[: max(12, len(lines) // 3)]
    candidates = [
        line
        for line in horizon
        if not _is_label_line(line)
        and not _RE_JUNK_LINE.match(line)
        and 8 <= len(line) <= 160
        and sum(ch.isalpha() for ch in line) >= 5
    ]
    if candidates:
        return _trim_product_name(max(candidates, key=len))

    return filename.rsplit(".", 1)[0] if filename else ""


def _trim_product_name(value: str) -> str:
    """Отсекает от наименования «хвост» соседнего поля."""
    lowered = value.lower()
    cut = len(value)
    for label in _ALL_LABELS:
        position = lowered.find(label)
        if 0 < position < cut:
            cut = position
    return clean_value(value[:cut], max_length=250)


def extract_brand(text: str, lines: list[str]) -> str:
    """Извлекает торговую марку.

    Args:
        text: Полный текст документа.
        lines: Строки документа.

    Returns:
        Торговая марка либо пустая строка.
    """
    value = extract_labeled_value(lines, BRAND_LABELS, max_continuation_lines=1, max_length=80)
    if value:
        return value
    quoted = _RE_QUOTED.search(text[:1500])
    if quoted:
        candidate = clean_value(quoted.group(1), max_length=60)
        if 2 <= len(candidate) <= 60 and any(ch.isalpha() for ch in candidate):
            return candidate
    return ""


def extract_all(text: str, *, filename: str = "") -> ExtractedFields:
    """Извлекает все поддерживаемые поля из текста сертификата.

    Args:
        text: Текст, извлечённый из PDF.
        filename: Имя PDF-файла без пути.

    Returns:
        Заполненный объект :class:`ExtractedFields` с оценкой достоверности.
    """
    fields_result = ExtractedFields()
    if not text or not text.strip():
        fields_result.product_name = filename.rsplit(".", 1)[0] if filename else ""
        fields_result.certificate_number = extract_certificate_number("", filename=filename)
        fields_result.warnings.append("Текст не извлечён — вероятно, скан без текстового слоя")
        return fields_result

    lines = split_lines(text)
    fields_result.product_name = extract_product_name(lines, filename=filename)
    fields_result.certificate_number = extract_certificate_number(text, filename=filename)
    fields_result.certificate_date, fields_result.valid_from, fields_result.expiry_date = (
        extract_dates(text)
    )
    fields_result.brand = extract_brand(text, lines)
    fields_result.manufacturer = extract_labeled_value(lines, MANUFACTURER_LABELS, max_length=160)
    fields_result.applicant = extract_labeled_value(lines, APPLICANT_LABELS, max_length=160)
    fields_result.issued_by = extract_labeled_value(lines, ISSUER_LABELS, max_length=160)
    fields_result.country = extract_labeled_value(
        lines, COUNTRY_LABELS, max_continuation_lines=1, max_length=60
    )

    achieved = sum(
        (
            2 if len(fields_result.product_name) >= 4 else 0,
            2 if fields_result.expiry_date is not None else 0,
            1 if fields_result.certificate_number else 0,
            1 if fields_result.certificate_date is not None else 0,
        )
    )
    fields_result.confidence = round(achieved / 6.0, 3)

    if not fields_result.product_name:
        fields_result.warnings.append("Не удалось определить наименование продукции")
    if fields_result.expiry_date is None:
        fields_result.warnings.append("Не удалось определить срок действия")
    return fields_result
