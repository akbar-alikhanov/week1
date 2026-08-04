"""Нормализация и сравнение текста товарных наименований.

Качество подбора сертификатов на 90 % определяется качеством нормализации.
Наименования приходят из трёх источников (Excel заказа, текст PDF, ручной ввод)
и содержат: смесь кириллицы и латиницы, символы ®/™, разные написания единиц
измерения («мл», «ml», «мл.»), омоглифы (латинская «c» внутри русского слова),
двойные пробелы, неразрывные пробелы и произвольную пунктуацию.

Модуль предоставляет чистые функции без побочных эффектов, что делает их
тривиально тестируемыми и потокобезопасными.
"""

from __future__ import annotations

import functools
import re
import unicodedata
from typing import Final

# --------------------------------------------------------------------------- #
# Таблицы преобразований
# --------------------------------------------------------------------------- #

#: Латинские символы, визуально неотличимые от кириллических.
#: Используются для «лечения» смешанных слов вида «Cироп» (латинская C).
_LATIN_TO_CYRILLIC: Final[dict[str, str]] = {
    "a": "а",
    "b": "в",
    "c": "с",
    "e": "е",
    "h": "н",
    "k": "к",
    "m": "м",
    "o": "о",
    "p": "р",
    "t": "т",
    "x": "х",
    "y": "у",
}

#: Обратная таблица — кириллица, визуально неотличимая от латиницы.
_CYRILLIC_TO_LATIN_HOMOGLYPHS: Final[dict[str, str]] = {
    "а": "a",
    "в": "b",
    "с": "c",
    "е": "e",
    "н": "h",
    "к": "k",
    "м": "m",
    "о": "o",
    "р": "p",
    "т": "t",
    "х": "x",
    "у": "y",
}

#: Полная таблица практической транслитерации (ГОСТ 7.79-2000, система Б,
#: упрощённая под товарные наименования).
_TRANSLIT_TABLE: Final[dict[str, str]] = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
    # узбекская кириллица
    "ў": "o",
    "қ": "q",
    "ғ": "g",
    "ҳ": "h",
}

#: Приведение единиц измерения к каноническому латинскому виду.
#: Порядок важен: длинные формы должны обрабатываться раньше коротких.
_UNIT_ALIASES: Final[tuple[tuple[str, str], ...]] = (
    ("миллилитров", "ml"),
    ("миллилитра", "ml"),
    ("миллилитр", "ml"),
    ("millilitres", "ml"),
    ("milliliters", "ml"),
    ("литров", "l"),
    ("литра", "l"),
    ("литр", "l"),
    ("litres", "l"),
    ("liters", "l"),
    ("миллиграммов", "mg"),
    ("миллиграмм", "mg"),
    ("milligrams", "mg"),
    ("килограммов", "kg"),
    ("килограмм", "kg"),
    ("kilograms", "kg"),
    ("граммов", "g"),
    ("грамма", "g"),
    ("грамм", "g"),
    ("grams", "g"),
    ("таблеток", "tab"),
    ("таблетки", "tab"),
    ("таблетка", "tab"),
    ("tablets", "tab"),
    ("капсул", "caps"),
    ("капсулы", "caps"),
    ("капсула", "caps"),
    ("capsules", "caps"),
    ("саше", "sachet"),
    ("sachets", "sachet"),
    ("ампул", "amp"),
    ("ампулы", "amp"),
    ("ампула", "amp"),
    ("ampoules", "amp"),
    ("штук", "pcs"),
    ("шт", "pcs"),
    ("pieces", "pcs"),
    ("мл", "ml"),
    ("мг", "mg"),
    ("кг", "kg"),
    ("гр", "g"),
    ("г", "g"),
    ("л", "l"),
    ("мкг", "mcg"),
    ("таб", "tab"),
    ("капс", "caps"),
    ("амп", "amp"),
    # Тождественные соответствия для латинских единиц: нужны, чтобы «100ml»
    # превращалось в «100 ml» и совпадало с «100 мл» из русского прайс-листа.
    ("mcg", "mcg"),
    ("mg", "mg"),
    ("kg", "kg"),
    ("ml", "ml"),
    ("g", "g"),
    ("l", "l"),
    ("tab", "tab"),
    ("caps", "caps"),
    ("amp", "amp"),
    ("pcs", "pcs"),
    ("sachet", "sachet"),
)

#: Слова, не несущие различающей информации в товарных наименованиях.
_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "для",
        "и",
        "с",
        "в",
        "на",
        "от",
        "по",
        "или",
        "the",
        "of",
        "and",
        "for",
        "ооо",
        "оао",
        "зао",
        "ао",
        "ип",
        "чп",
        "лтд",
        "ltd",
        "llc",
        "inc",
        "gmbh",
        "co",
        "corp",
        "company",
        "мчж",
        "qmj",
        "тм",
        "tm",
    }
)

#: Символы, которые полностью удаляются перед разбором.
_NOISE_CHARACTERS: Final[str] = "®™©℠°"

_RE_WHITESPACE: Final[re.Pattern[str]] = re.compile(r"\s+")
_RE_NON_ALNUM: Final[re.Pattern[str]] = re.compile(r"[^0-9a-zA-Zа-яёўқғҳ\s.,]", re.UNICODE)
_RE_UNIT_BOUNDARY: Final[re.Pattern[str]] = re.compile(
    r"(?<=\d)\s*(" + "|".join(re.escape(src) for src, _ in _UNIT_ALIASES) + r")(?![а-яёa-z])",
    re.IGNORECASE | re.UNICODE,
)
_RE_DECIMAL_COMMA: Final[re.Pattern[str]] = re.compile(r"(?<=\d),(?=\d)")
#: Точка, не являющаяся десятичным разделителем («мл.», «трава.сироп»).
_RE_DOT_NOT_DECIMAL: Final[re.Pattern[str]] = re.compile(r"(?<!\d)\.|\.(?!\d)")
_RE_CYRILLIC: Final[re.Pattern[str]] = re.compile(r"[а-яёўқғҳ]", re.IGNORECASE)
_RE_LATIN: Final[re.Pattern[str]] = re.compile(r"[a-z]", re.IGNORECASE)

_UNIT_LOOKUP: Final[dict[str, str]] = dict(_UNIT_ALIASES)


# --------------------------------------------------------------------------- #
# Базовые операции
# --------------------------------------------------------------------------- #
def collapse_whitespace(text: str) -> str:
    """Схлопывает любые последовательности пробельных символов в один пробел.

    Args:
        text: Исходная строка.

    Returns:
        Строка без ведущих/замыкающих пробелов и с одиночными разделителями.
    """
    return _RE_WHITESPACE.sub(" ", text).strip()


def strip_accents(text: str) -> str:
    """Удаляет диакритические знаки, сохраняя базовые буквы.

    Кириллическая «ё» сохраняется отдельной обработкой в :func:`normalize`,
    так как её разложение по NFD ломает русские слова.

    Args:
        text: Исходная строка.

    Returns:
        Строка без комбинирующих диакритических символов.
    """
    decomposed = unicodedata.normalize("NFD", text)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return unicodedata.normalize("NFC", without_marks)


def detect_script(text: str) -> str:
    """Определяет преобладающую письменность строки.

    Args:
        text: Исходная строка.

    Returns:
        ``"cyrillic"``, ``"latin"``, ``"mixed"`` или ``"none"``.
    """
    has_cyrillic = bool(_RE_CYRILLIC.search(text))
    has_latin = bool(_RE_LATIN.search(text))
    if has_cyrillic and has_latin:
        return "mixed"
    if has_cyrillic:
        return "cyrillic"
    if has_latin:
        return "latin"
    return "none"


def fix_homoglyphs(text: str) -> str:
    """Исправляет пословно смешение кириллицы и латиницы.

    В сертификатах регулярно встречаются слова, где часть букв набрана в другой
    раскладке («Cироп», «Витaмин»). Для каждого слова определяется доминирующая
    письменность, и «чужие» омоглифы приводятся к ней.

    Args:
        text: Исходная строка.

    Returns:
        Строка, в которой каждое слово использует одну письменность.
    """
    words = text.split(" ")
    repaired: list[str] = []
    for word in words:
        cyrillic_count = len(_RE_CYRILLIC.findall(word))
        latin_count = len(_RE_LATIN.findall(word))
        if cyrillic_count and latin_count:
            if cyrillic_count >= latin_count:
                word = "".join(_LATIN_TO_CYRILLIC.get(ch, ch) for ch in word)
            else:
                word = "".join(_CYRILLIC_TO_LATIN_HOMOGLYPHS.get(ch, ch) for ch in word)
        repaired.append(word)
    return " ".join(repaired)


def canonicalize_units(text: str) -> str:
    """Приводит единицы измерения к каноническому латинскому написанию.

    Преобразование применяется только к единицам, следующим за числом, чтобы
    не разрушать слова («г» в слове «глюкоза» не должна стать «g»).

    Args:
        text: Строка в нижнем регистре.

    Returns:
        Строка с единицами вида ``100 ml``, ``0.5 l``, ``30 tab``.
    """

    def _replace(match: re.Match[str]) -> str:
        return " " + _UNIT_LOOKUP[match.group(1).lower()]

    return _RE_UNIT_BOUNDARY.sub(_replace, text)


@functools.lru_cache(maxsize=8192)
def normalize(text: str | None) -> str:
    """Приводит наименование к каноническому виду для сравнения.

    Конвейер: NFC → нижний регистр → удаление шума → починка омоглифов →
    десятичная запятая → канонизация единиц → удаление пунктуации →
    схлопывание пробелов.

    Args:
        text: Исходное наименование (может быть ``None``).

    Returns:
        Нормализованная строка; пустая строка, если на входе пусто.

    Examples:
        >>> normalize("Лечебные травы  100 мл.")
        'лечебные травы 100 ml'
        >>> normalize("TP Herbal® 100ml")
        'tp herbal 100 ml'
    """
    if not text:
        return ""

    result = unicodedata.normalize("NFC", str(text)).lower()
    result = result.replace("\u0451", "\u0435").replace("\u00a0", " ").replace("\u200b", "")
    for char in _NOISE_CHARACTERS:
        result = result.replace(char, " ")
    result = collapse_whitespace(result)
    result = fix_homoglyphs(result)
    result = _RE_DECIMAL_COMMA.sub(".", result)
    result = canonicalize_units(result)
    result = _RE_NON_ALNUM.sub(" ", result)
    result = _RE_DOT_NOT_DECIMAL.sub(" ", result)
    result = result.replace(",", " ")
    return collapse_whitespace(result)


@functools.lru_cache(maxsize=8192)
def transliterate(text: str | None) -> str:
    """Транслитерирует кириллицу в латиницу для кросс-скриптового сравнения.

    Позволяет сопоставлять «Витамин» и «Vitamin», «Сироп» и «Sirop» без
    привлечения нейросетевой модели.

    Args:
        text: Исходная строка (нормализованная или нет).

    Returns:
        Латинизированная нормализованная строка.
    """
    if not text:
        return ""
    normalized = normalize(text)
    return collapse_whitespace("".join(_TRANSLIT_TABLE.get(ch, ch) for ch in normalized))


def tokenize(text: str | None, *, drop_stopwords: bool = True) -> list[str]:
    """Разбивает наименование на значимые токены.

    Args:
        text: Исходное наименование.
        drop_stopwords: Исключать ли служебные слова и организационные формы.

    Returns:
        Список токенов в порядке появления.
    """
    tokens = normalize(text).split(" ")
    if not drop_stopwords:
        return [token for token in tokens if token]
    return [token for token in tokens if token and token not in _STOPWORDS]


@functools.lru_cache(maxsize=8192)
def token_key(text: str | None) -> str:
    """Строит ключ, инвариантный к порядку слов.

    Используется как вторичный ключ поиска в таблице псевдонимов: «травы
    лечебные 100 мл» и «лечебные травы 100 мл» дают одинаковый ключ.

    Args:
        text: Исходное наименование.

    Returns:
        Токены, отсортированные по алфавиту и склеенные пробелом.
    """
    return " ".join(sorted(set(tokenize(text))))


def alpha_signature(text: str | None) -> str:
    """Возвращает только буквенную часть наименования (без чисел и единиц).

    Нужна для сравнения «того же товара в другом объёме»: сигнатуры
    «Лечебные травы 100 мл» и «Лечебные травы 150 мл» совпадают.

    Args:
        text: Исходное наименование.

    Returns:
        Буквенные токены, склеенные пробелом.
    """
    tokens = [token for token in tokenize(text) if not any(ch.isdigit() for ch in token)]
    canonical_units = set(_UNIT_LOOKUP.values())
    return " ".join(token for token in tokens if token not in canonical_units)


def shorten(text: str, limit: int = 60) -> str:
    """Обрезает строку до указанной длины, добавляя многоточие.

    Args:
        text: Исходная строка.
        limit: Максимальная длина результата, включая многоточие.

    Returns:
        Строка длиной не более ``limit``.
    """
    text = collapse_whitespace(text)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"
