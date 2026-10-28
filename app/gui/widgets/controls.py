"""Кнопки, значки состояния и прочие управляющие элементы."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

import customtkinter as ctk

from app.gui.icons import icons
from app.gui.theme import FontRole, Radius, Sizes, Spacing, Theme


def primary_button(
    master: Any,
    theme: Theme,
    *,
    text: str,
    command: Callable[[], None],
    icon: str = "",
    height: int = Sizes.BUTTON_HEIGHT,
    width: int = 0,
    **kwargs: Any,
) -> ctk.CTkButton:
    """Создаёт основную кнопку действия.

    Args:
        master: Родительский виджет.
        theme: Активная тема оформления.
        text: Надпись.
        command: Обработчик нажатия.
        icon: Имя иконки слева от надписи.
        height: Высота кнопки.
        width: Ширина (0 — по содержимому).
        **kwargs: Дополнительные параметры ``CTkButton``.

    Returns:
        Настроенная кнопка.
    """
    image = (
        icons.get(icon, 18, light_color="#FFFFFF", dark_color=theme.color("text_inverted")[1])
        if icon
        else None
    )
    button = ctk.CTkButton(
        master,
        text=text,
        command=command,
        image=image,
        compound="left",
        height=height,
        corner_radius=Radius.MD,
        font=theme.font(FontRole.BODY_STRONG),
        fg_color=theme.color("accent"),
        hover_color=theme.color("accent_hover"),
        text_color=theme.color("text_inverted"),
        **kwargs,
    )
    if width:
        button.configure(width=width)
    return button


def secondary_button(
    master: Any,
    theme: Theme,
    *,
    text: str,
    command: Callable[[], None],
    icon: str = "",
    height: int = Sizes.BUTTON_HEIGHT,
    **kwargs: Any,
) -> ctk.CTkButton:
    """Создаёт второстепенную кнопку с контурным оформлением.

    Args:
        master: Родительский виджет.
        theme: Активная тема оформления.
        text: Надпись.
        command: Обработчик нажатия.
        icon: Имя иконки.
        height: Высота кнопки.
        **kwargs: Дополнительные параметры ``CTkButton``.

    Returns:
        Настроенная кнопка.
    """
    return ctk.CTkButton(
        master,
        text=text,
        command=command,
        image=icons.colored(icon, theme, "text", 18) if icon else None,
        compound="left",
        height=height,
        corner_radius=Radius.MD,
        font=theme.font(FontRole.BODY),
        fg_color="transparent",
        hover_color=theme.color("surface_hover"),
        text_color=theme.color("text"),
        border_width=1,
        border_color=theme.color("border"),
        **kwargs,
    )


def ghost_button(
    master: Any,
    theme: Theme,
    *,
    text: str,
    command: Callable[[], None],
    icon: str = "",
    danger: bool = False,
    height: int = Sizes.BUTTON_HEIGHT,
    **kwargs: Any,
) -> ctk.CTkButton:
    """Создаёт кнопку без рамки и заливки.

    Args:
        master: Родительский виджет.
        theme: Активная тема оформления.
        text: Надпись.
        command: Обработчик нажатия.
        icon: Имя иконки.
        danger: Использовать ли цвет опасного действия.
        height: Высота кнопки.
        **kwargs: Дополнительные параметры ``CTkButton``.

    Returns:
        Настроенная кнопка.
    """
    role = "danger" if danger else "text_muted"
    return ctk.CTkButton(
        master,
        text=text,
        command=command,
        image=icons.colored(icon, theme, role, 18) if icon else None,
        compound="left",
        height=height,
        corner_radius=Radius.MD,
        font=theme.font(FontRole.BODY),
        fg_color="transparent",
        hover_color=theme.color("danger_soft" if danger else "surface_hover"),
        text_color=theme.color(role),
        **kwargs,
    )


def icon_button(
    master: Any,
    theme: Theme,
    *,
    icon: str,
    command: Callable[[], None],
    tooltip: str = "",
    size: int = 36,
    role: str = "text_muted",
    **kwargs: Any,
) -> ctk.CTkButton:
    """Создаёт квадратную кнопку с одной иконкой.

    Args:
        master: Родительский виджет.
        theme: Активная тема оформления.
        icon: Имя иконки.
        command: Обработчик нажатия.
        tooltip: Текст всплывающей подсказки.
        size: Сторона кнопки в пикселях.
        role: Роль цвета иконки.
        **kwargs: Дополнительные параметры ``CTkButton``.

    Returns:
        Настроенная кнопка.
    """
    button = ctk.CTkButton(
        master,
        text="",
        command=command,
        image=icons.colored(icon, theme, role, 18),
        width=size,
        height=size,
        corner_radius=Radius.MD,
        fg_color="transparent",
        hover_color=theme.color("surface_hover"),
        **kwargs,
    )
    if tooltip:
        Tooltip(button, theme, text=tooltip)
    return button


class Badge(ctk.CTkFrame):
    """Небольшой цветной значок состояния."""

    #: Соответствие «роль → (цвет текста, цвет подложки)».
    ROLES: ClassVar[dict[str, tuple[str, str]]] = {
        "success": ("success", "success_soft"),
        "warning": ("warning", "warning_soft"),
        "danger": ("danger", "danger_soft"),
        "accent": ("accent", "accent_soft"),
        "muted": ("text_muted", "surface_alt"),
    }

    def __init__(
        self, master: Any, theme: Theme, *, text: str, role: str = "muted", **kwargs: Any
    ) -> None:
        """Создаёт значок состояния.

        Args:
            master: Родительский виджет.
            theme: Активная тема оформления.
            text: Надпись.
            role: Роль состояния (``success``, ``warning``, ``danger``…).
            **kwargs: Дополнительные параметры ``CTkFrame``.
        """
        self._theme = theme
        text_role, background_role = self.ROLES.get(role, self.ROLES["muted"])
        super().__init__(
            master, fg_color=theme.color(background_role), corner_radius=Radius.PILL, **kwargs
        )
        self._label = ctk.CTkLabel(
            self,
            text=text,
            font=theme.font(FontRole.CAPTION),
            text_color=theme.color(text_role),
        )
        self._label.pack(padx=Spacing.SM, pady=2)

    def update_state(self, text: str, role: str) -> None:
        """Обновляет надпись и цвет значка.

        Args:
            text: Новая надпись.
            role: Новая роль состояния.
        """
        text_role, background_role = self.ROLES.get(role, self.ROLES["muted"])
        try:
            self.configure(fg_color=self._theme.color(background_role))
            self._label.configure(text=text, text_color=self._theme.color(text_role))
        except Exception:
            pass


class Tooltip:
    """Всплывающая подсказка для любого виджета.

    Реализована отдельным окном без рамки: стандартная подсказка Tk выглядит
    чужеродно рядом с оформлением CustomTkinter.
    """

    def __init__(self, widget: Any, theme: Theme, *, text: str, delay: int = 550) -> None:
        """Привязывает подсказку к виджету.

        Args:
            widget: Виджет-владелец.
            theme: Активная тема оформления.
            text: Текст подсказки.
            delay: Задержка появления в миллисекундах.
        """
        self._widget = widget
        self._theme = theme
        self._text = text
        self._delay = delay
        self._window: Any = None
        self._after_id: str | None = None

        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def update_text(self, text: str) -> None:
        """Меняет текст подсказки.

        Args:
            text: Новый текст.
        """
        self._text = text

    def _schedule(self, _: Any = None) -> None:
        """Планирует показ подсказки."""
        self._cancel()
        try:
            self._after_id = self._widget.after(self._delay, self._show)
        except Exception:
            pass

    def _cancel(self) -> None:
        """Отменяет запланированный показ."""
        if self._after_id is not None:
            try:
                self._widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self) -> None:
        """Отображает окно подсказки."""
        if self._window is not None or not self._text:
            return
        try:
            import tkinter as tk

            x = self._widget.winfo_rootx() + self._widget.winfo_width() // 2
            y = self._widget.winfo_rooty() + self._widget.winfo_height() + 8

            window = tk.Toplevel(self._widget)
            window.wm_overrideredirect(True)
            window.attributes("-topmost", True)
            frame = ctk.CTkFrame(
                window,
                fg_color=self._theme.color("surface_alt"),
                corner_radius=Radius.SM,
                border_width=1,
                border_color=self._theme.color("border"),
            )
            frame.pack()
            ctk.CTkLabel(
                frame,
                text=self._text,
                font=self._theme.font(FontRole.CAPTION),
                text_color=self._theme.color("text"),
                justify="left",
            ).pack(padx=Spacing.SM, pady=Spacing.XS)
            window.update_idletasks()
            window.wm_geometry(f"+{x - window.winfo_width() // 2}+{y}")
            self._window = window
        except Exception:
            self._window = None

    def _hide(self, _: Any = None) -> None:
        """Скрывает подсказку."""
        self._cancel()
        if self._window is not None:
            try:
                self._window.destroy()
            except Exception:
                pass
            self._window = None


class SegmentedFilter(ctk.CTkFrame):
    """Переключатель фильтров в виде группы кнопок-чипов со счётчиками."""

    def __init__(
        self,
        master: Any,
        theme: Theme,
        *,
        options: list[tuple[str, str]],
        on_change: Callable[[str], None],
        initial: str = "",
        **kwargs: Any,
    ) -> None:
        """Создаёт переключатель.

        Args:
            master: Родительский виджет.
            theme: Активная тема оформления.
            options: Пары ``(значение, надпись)``.
            on_change: Обработчик выбора значения.
            initial: Изначально выбранное значение.
            **kwargs: Дополнительные параметры ``CTkFrame``.
        """
        super().__init__(master, fg_color="transparent", **kwargs)
        self._theme = theme
        self._on_change = on_change
        self._buttons: dict[str, ctk.CTkButton] = {}
        self._labels: dict[str, str] = dict(options)
        self._counts: dict[str, int] = {}
        self._value = initial or (options[0][0] if options else "")

        for value, _label in options:
            button = ctk.CTkButton(
                self,
                text=self._labels[value],
                width=0,
                height=34,
                corner_radius=Radius.PILL,
                font=theme.font(FontRole.SMALL),
                fg_color="transparent",
                hover_color=theme.color("surface_hover"),
                text_color=theme.color("text_muted"),
                border_width=1,
                border_color=theme.color("border"),
                command=lambda item=value: self.select(item),
            )
            button.pack(side="left", padx=(0, Spacing.XS))
            self._buttons[value] = button

        self._refresh()

    @property
    def value(self) -> str:
        """Выбранное значение."""
        return self._value

    def select(self, value: str, *, notify: bool = True) -> None:
        """Выбирает значение фильтра.

        Args:
            value: Новое значение.
            notify: Вызывать ли обработчик изменения.
        """
        if value not in self._buttons:
            return
        self._value = value
        self._refresh()
        if notify:
            self._on_change(value)

    def set_counts(self, counts: dict[str, int]) -> None:
        """Обновляет количество позиций, отображаемое рядом с каждой меткой.

        Args:
            counts: Количество по значению фильтра; отсутствующие значения
                показываются без счётчика.
        """
        self._counts = counts
        self._refresh()

    def _refresh(self) -> None:
        """Обновляет надписи и оформление кнопок."""
        for value, button in self._buttons.items():
            active = value == self._value
            count = self._counts.get(value)
            text = f"{self._labels[value]} · {count}" if count is not None else self._labels[value]
            try:
                button.configure(
                    text=text,
                    fg_color=self._theme.color("accent_soft") if active else "transparent",
                    text_color=self._theme.color("accent" if active else "text_muted"),
                    border_color=self._theme.color("accent" if active else "border"),
                )
            except Exception:
                continue
