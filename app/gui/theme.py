"""Дизайн-система приложения: цвета, типографика, отступы, скругления.

Все визуальные константы собраны в одном месте. Ни один виджет не содержит
«магических» цветов — это даёт согласованный вид всего приложения и позволяет
поменять фирменный стиль правкой одного файла.

Каждый цвет задан парой ``(светлая тема, тёмная тема)`` — формат, который
CustomTkinter понимает нативно и переключает автоматически.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Final, cast

_LOGGER = logging.getLogger(__name__)

#: Тип цвета CustomTkinter: одиночное значение или пара «светлая/тёмная».
ColorPair = tuple[str, str]


# --------------------------------------------------------------------------- #
# Палитра
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Palette:
    """Цветовая палитра интерфейса.

    Attributes:
        background: Фон окна.
        surface: Фон панелей и карточек.
        surface_alt: Фон второстепенных областей (боковая панель, шапки).
        surface_hover: Фон элемента под курсором.
        border: Цвет разделителей и рамок.
        text: Основной цвет текста.
        text_muted: Второстепенный текст.
        text_inverted: Текст на акцентной заливке.
        accent: Основной акцентный цвет.
        accent_hover: Акцент под курсором.
        accent_soft: Полупрозрачная акцентная подложка.
        success: Цвет успешного состояния.
        warning: Цвет предупреждения.
        danger: Цвет ошибки.
        info: Цвет информационного состояния.
        success_soft: Подложка успешного состояния.
        warning_soft: Подложка предупреждения.
        danger_soft: Подложка ошибки.
        info_soft: Подложка информационного состояния.
        shadow: Цвет имитации тени.
    """

    background: ColorPair
    surface: ColorPair
    surface_alt: ColorPair
    surface_hover: ColorPair
    border: ColorPair
    text: ColorPair
    text_muted: ColorPair
    text_inverted: ColorPair
    accent: ColorPair
    accent_hover: ColorPair
    accent_soft: ColorPair
    success: ColorPair
    warning: ColorPair
    danger: ColorPair
    info: ColorPair
    success_soft: ColorPair
    warning_soft: ColorPair
    danger_soft: ColorPair
    info_soft: ColorPair
    shadow: ColorPair


#: Фирменная палитра BALTON: сдержанный изумрудный акцент на нейтральном фоне.
#: Выбор обусловлен фармацевтической отраслью (зелёный — отраслевой код)
#: и требованием читаемости при многочасовой работе. Светлая сторона — точные
#: цвета дизайн-макета редизайна; тёмная сторона подобрана в той же палитре
#: оттенков (макет тёмную тему не определяет).
EMERALD: Final[Palette] = Palette(
    background=("#F5F7F9", "#16191D"),
    surface=("#FFFFFF", "#1E2227"),
    surface_alt=("#ECEFF3", "#22272D"),
    surface_hover=("#E1E6EB", "#2A3037"),
    border=("#E3E7EC", "#2E343B"),
    text=("#151A21", "#EEF1F5"),
    text_muted=("#5B6472", "#98A3AF"),
    text_inverted=("#FFFFFF", "#0E1114"),
    accent=("#146B5C", "#2DD4BF"),
    accent_hover=("#0F5248", "#5EEAD4"),
    accent_soft=("#E7F0EE", "#15302C"),
    success=("#15803D", "#4ADE80"),
    warning=("#B45309", "#FBBF24"),
    danger=("#B91C1C", "#F87171"),
    info=("#1D4ED8", "#60A5FA"),
    success_soft=("#DCFCE7", "#14291C"),
    warning_soft=("#FEF3C7", "#2E2410"),
    danger_soft=("#FEE2E2", "#2B1616"),
    info_soft=("#DBEAFE", "#172234"),
    shadow=("#D5DBE3", "#101315"),
)

#: Альтернативная палитра — корпоративный синий.
SAPPHIRE: Final[Palette] = Palette(
    background=("#F3F5F9", "#15181E"),
    surface=("#FFFFFF", "#1D2129"),
    surface_alt=("#EAEEF5", "#212631"),
    surface_hover=("#DFE5EF", "#29303B"),
    border=("#D9E0EA", "#2C333F"),
    text=("#101520", "#EDF0F6"),
    text_muted=("#66707F", "#96A0AF"),
    text_inverted=("#FFFFFF", "#0D1014"),
    accent=("#2563C7", "#4E8FE8"),
    accent_hover=("#1D51A6", "#659FF0"),
    accent_soft=("#E1EBFA", "#17263D"),
    success=("#1E9E63", "#31C17E"),
    warning=("#C08416", "#E0A93A"),
    danger=("#C6413C", "#E4635E"),
    info=("#2C6FB5", "#4A94DA"),
    success_soft=("#E2F5EA", "#142B20"),
    warning_soft=("#FBF0DA", "#2F2718"),
    danger_soft=("#FBE5E4", "#2E1B1A"),
    info_soft=("#E1EBFA", "#17263D"),
    shadow=("#D3DAE5", "#0F1216"),
)

#: Доступные палитры по идентификатору из настроек.
PALETTES: Final[dict[str, Palette]] = {"emerald": EMERALD, "sapphire": SAPPHIRE}


# --------------------------------------------------------------------------- #
# Метрики
# --------------------------------------------------------------------------- #
class Spacing:
    """Шкала отступов (кратна 4 px — базовой сетке макета)."""

    XS: Final[int] = 4
    SM: Final[int] = 8
    MD: Final[int] = 12
    LG: Final[int] = 16
    XL: Final[int] = 24
    XXL: Final[int] = 32


class Radius:
    """Радиусы скругления."""

    SM: Final[int] = 6
    MD: Final[int] = 10
    LG: Final[int] = 14
    XL: Final[int] = 20
    PILL: Final[int] = 999


class Sizes:
    """Характерные размеры элементов интерфейса."""

    SIDEBAR_WIDTH: Final[int] = 232
    SIDEBAR_COLLAPSED: Final[int] = 68
    HEADER_HEIGHT: Final[int] = 60
    BUTTON_HEIGHT: Final[int] = 38
    BUTTON_HEIGHT_LG: Final[int] = 48
    INPUT_HEIGHT: Final[int] = 38
    ICON: Final[int] = 20
    ICON_LG: Final[int] = 24
    ICON_XL: Final[int] = 40
    MIN_WINDOW: Final[tuple[int, int]] = (1120, 700)
    DEFAULT_WINDOW: Final[tuple[int, int]] = (1360, 860)


# --------------------------------------------------------------------------- #
# Типографика
# --------------------------------------------------------------------------- #
#: Приоритет системных шрифтов. Segoe UI Variable — системный шрифт Windows 11,
#: Segoe UI — Windows 10; остальные нужны для запуска в среде разработки.
FONT_STACK: Final[tuple[str, ...]] = (
    "Segoe UI Variable Text",
    "Segoe UI",
    "Inter",
    "SF Pro Text",
    "Ubuntu",
    "DejaVu Sans",
)

MONO_FONT_STACK: Final[tuple[str, ...]] = (
    "Cascadia Mono",
    "Consolas",
    "JetBrains Mono",
    "SF Mono",
    "DejaVu Sans Mono",
)


class FontRole:
    """Роли типографики: размер и насыщенность."""

    DISPLAY: Final[tuple[int, str]] = (30, "bold")
    TITLE: Final[tuple[int, str]] = (21, "bold")
    HEADING: Final[tuple[int, str]] = (16, "bold")
    SUBHEADING: Final[tuple[int, str]] = (14, "bold")
    BODY: Final[tuple[int, str]] = (13, "normal")
    BODY_STRONG: Final[tuple[int, str]] = (13, "bold")
    SMALL: Final[tuple[int, str]] = (12, "normal")
    CAPTION: Final[tuple[int, str]] = (11, "normal")
    METRIC: Final[tuple[int, str]] = (27, "bold")


class Theme:
    """Активная тема оформления.

    Экземпляр создаётся один раз главным окном и передаётся всем виджетам.
    Смена темы выполняется методом :meth:`apply`, после чего подписчики
    перерисовывают элементы, которые CustomTkinter не обновляет сам
    (в первую очередь — таблицы на базе ``ttk``).
    """

    def __init__(self, palette_name: str = "emerald", mode: str = "system") -> None:
        """Создаёт тему.

        Args:
            palette_name: Идентификатор палитры.
            mode: ``light``, ``dark`` или ``system``.
        """
        self._palette = PALETTES.get(palette_name, EMERALD)
        self._palette_name = palette_name if palette_name in PALETTES else "emerald"
        self._mode = mode
        self._font_family = FONT_STACK[-1]
        self._mono_family = MONO_FONT_STACK[-1]
        self._fonts: dict[tuple[int, str], Any] = {}
        self._listeners: list[Any] = []

    # ------------------------------------------------------------- свойства
    @property
    def palette(self) -> Palette:
        """Активная цветовая палитра."""
        return self._palette

    @property
    def palette_name(self) -> str:
        """Идентификатор активной палитры."""
        return self._palette_name

    @property
    def mode(self) -> str:
        """Режим оформления (``light``/``dark``/``system``)."""
        return self._mode

    @property
    def is_dark(self) -> bool:
        """Признак тёмного оформления с учётом системной настройки."""
        try:
            import customtkinter as ctk

            return bool(ctk.get_appearance_mode().lower() == "dark")
        except Exception:
            return self._mode == "dark"

    def color(self, name: str) -> ColorPair:
        """Возвращает цвет палитры по имени поля.

        Args:
            name: Имя атрибута :class:`Palette`.

        Returns:
            Пара «светлый/тёмный».
        """
        return cast(ColorPair, getattr(self._palette, name))

    def resolved(self, name: str) -> str:
        """Возвращает конкретный цвет для текущего режима.

        Нужен там, где CustomTkinter не участвует в отрисовке (``ttk``,
        ``tkinter.Canvas``) и пару значений передать нельзя.

        Args:
            name: Имя атрибута :class:`Palette`.

        Returns:
            Строка вида ``#RRGGBB``.
        """
        pair = self.color(name)
        return pair[1] if self.is_dark else pair[0]

    # ------------------------------------------------------------- шрифты
    def detect_fonts(self, root: Any) -> None:
        """Подбирает лучший доступный системный шрифт.

        Args:
            root: Корневое окно Tk (нужно для доступа к списку шрифтов).
        """
        try:
            from tkinter import font as tkfont

            available = {name.lower() for name in tkfont.families(root)}
        except Exception:
            return

        for family in FONT_STACK:
            if family.lower() in available:
                self._font_family = family
                break
        for family in MONO_FONT_STACK:
            if family.lower() in available:
                self._mono_family = family
                break
        self._fonts.clear()
        _LOGGER.debug("Выбраны шрифты: %s / %s", self._font_family, self._mono_family)

    def font(self, role: tuple[int, str] = FontRole.BODY, *, mono: bool = False) -> Any:
        """Возвращает объект шрифта для заданной роли.

        Шрифты кэшируются: создание ``CTkFont`` — недешёвая операция, а
        интерфейс запрашивает их сотни раз.

        Args:
            role: Пара «размер, насыщенность» из :class:`FontRole`.
            mono: Использовать ли моноширинный шрифт.

        Returns:
            Экземпляр ``customtkinter.CTkFont``.
        """
        import customtkinter as ctk

        key = (role[0], f"{role[1]}{'-mono' if mono else ''}")
        cached = self._fonts.get(key)
        if cached is None:
            cached = ctk.CTkFont(
                family=self._mono_family if mono else self._font_family,
                size=role[0],
                weight=role[1],
            )
            self._fonts[key] = cached
        return cached

    # -------------------------------------------------------------- режимы
    def apply(self, *, mode: str | None = None, palette_name: str | None = None) -> None:
        """Применяет режим оформления и палитру.

        Args:
            mode: Новый режим; ``None`` — оставить текущий.
            palette_name: Новая палитра; ``None`` — оставить текущую.
        """
        import customtkinter as ctk

        if palette_name is not None and palette_name in PALETTES:
            self._palette_name = palette_name
            self._palette = PALETTES[palette_name]
        if mode is not None:
            self._mode = mode

        ctk.set_appearance_mode(self._mode)
        self._notify()

    def toggle_mode(self) -> str:
        """Переключает светлое и тёмное оформление.

        Returns:
            Новый режим оформления.
        """
        new_mode = "light" if self.is_dark else "dark"
        self.apply(mode=new_mode)
        return new_mode

    def subscribe(self, listener: Any) -> None:
        """Подписывает обработчик на смену темы.

        Args:
            listener: Вызывается без аргументов после применения темы.
        """
        self._listeners.append(listener)

    def _notify(self) -> None:
        """Оповещает подписчиков о смене темы."""
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:
                _LOGGER.debug("Ошибка обработчика смены темы", exc_info=True)

    # ---------------------------------------------------------------- ttk
    def style_treeview(self, widget: Any) -> None:
        """Настраивает оформление таблиц ``ttk.Treeview`` под текущую тему.

        CustomTkinter не предоставляет таблицы, а ``ttk.Treeview`` не
        поддерживает пары цветов, поэтому стиль приходится задавать вручную
        и обновлять при каждой смене темы.

        Args:
            widget: Любой виджет (нужен только для доступа к ``ttk.Style``).
        """
        try:
            from tkinter import ttk
        except ImportError:  # pragma: no cover
            return

        style = ttk.Style(widget)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        surface = self.resolved("surface")
        surface_alt = self.resolved("surface_alt")
        text = self.resolved("text")
        muted = self.resolved("text_muted")
        border = self.resolved("border")
        accent_soft = self.resolved("accent_soft")
        accent = self.resolved("accent")

        style.configure(
            "CertMatcher.Treeview",
            background=surface,
            fieldbackground=surface,
            foreground=text,
            bordercolor=border,
            borderwidth=0,
            relief="flat",
            rowheight=30,
        )
        style.configure(
            "CertMatcher.Treeview.Heading",
            background=surface_alt,
            foreground=muted,
            relief="flat",
            borderwidth=0,
            padding=(10, 8),
        )
        style.map(
            "CertMatcher.Treeview.Heading",
            background=[("active", self.resolved("surface_hover"))],
            foreground=[("active", text)],
        )
        style.map(
            "CertMatcher.Treeview",
            background=[("selected", accent_soft)],
            foreground=[("selected", text)],
        )
        style.configure(
            "CertMatcher.Vertical.TScrollbar",
            background=surface_alt,
            troughcolor=surface,
            bordercolor=surface,
            arrowcolor=muted,
            relief="flat",
            borderwidth=0,
        )
        style.map(
            "CertMatcher.Vertical.TScrollbar",
            background=[("active", accent)],
        )
