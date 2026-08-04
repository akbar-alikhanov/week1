"""Карточки — основной строительный блок макета."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from app.gui.animations import Animator
from app.gui.icons import icons
from app.gui.theme import FontRole, Radius, Spacing, Theme
from app.gui.widgets.base import bind_recursive, set_cursor


class Card(ctk.CTkFrame):
    """Прямоугольная панель с фоном, рамкой и скруглением.

    Карточка может быть интерактивной: тогда она подсвечивается при наведении
    и реагирует на щелчок. Подсветка выполняется плавным переходом цвета —
    это единственная анимация, которую пользователь замечает постоянно,
    поэтому она сделана короткой (140 мс) и незаметной.
    """

    def __init__(
        self,
        master: Any,
        theme: Theme,
        *,
        animator: Animator | None = None,
        on_click: Callable[[], None] | None = None,
        padding: int = Spacing.LG,
        radius: int = Radius.LG,
        elevated: bool = False,
        **kwargs: Any,
    ) -> None:
        """Создаёт карточку.

        Args:
            master: Родительский виджет.
            theme: Активная тема оформления.
            animator: Менеджер анимаций.
            on_click: Обработчик щелчка; ``None`` — карточка неинтерактивна.
            padding: Внутренний отступ содержимого.
            radius: Радиус скругления.
            elevated: Использовать ли усиленную рамку (имитация тени).
            **kwargs: Дополнительные параметры ``CTkFrame``.
        """
        self._theme = theme
        self._animator = animator
        self._on_click = on_click
        self._padding = padding
        self._hovered = False

        super().__init__(
            master,
            fg_color=theme.color("surface"),
            corner_radius=radius,
            border_width=1,
            border_color=theme.color("shadow" if elevated else "border"),
            **kwargs,
        )

        self.body = ctk.CTkFrame(self, fg_color="transparent", width=0, height=0)
        self.body.pack(fill="both", expand=True, padx=padding, pady=padding)

        if on_click is not None:
            self.after(50, self._enable_interaction)

    @property
    def theme(self) -> Theme:
        """Активная тема оформления."""
        return self._theme

    def _enable_interaction(self) -> None:
        """Включает реакцию на наведение и щелчок."""
        set_cursor(self, "hand2")
        bind_recursive(self, "<Enter>", lambda _: self._set_hover(True))
        bind_recursive(self, "<Leave>", lambda _: self._set_hover(False))
        bind_recursive(self, "<Button-1>", lambda _: self._activate())

    def _set_hover(self, value: bool) -> None:
        """Меняет состояние подсветки."""
        if value == self._hovered:
            return
        self._hovered = value
        start = self._theme.resolved("surface" if value else "surface_hover")
        end = self._theme.resolved("surface_hover" if value else "surface")

        if self._animator is None:
            self.configure(fg_color=end)
            return

        self._animator.fade_color(
            self,
            f"card-{id(self)}",
            start_color=start,
            end_color=end,
            apply=lambda color: self._safe_color(color),
        )

    def _safe_color(self, color: str) -> None:
        """Применяет цвет фона, игнорируя уничтоженный виджет."""
        try:
            self.configure(fg_color=color)
        except Exception:
            pass

    def _activate(self) -> None:
        """Вызывает обработчик щелчка."""
        if self._on_click is not None:
            self._on_click()

    def refresh_theme(self) -> None:
        """Перечитывает цвета после смены темы."""
        self.configure(
            fg_color=self._theme.color("surface"), border_color=self._theme.color("border")
        )
        self._hovered = False


class SectionCard(Card):
    """Карточка с заголовком, подзаголовком и областью действий."""

    def __init__(
        self,
        master: Any,
        theme: Theme,
        *,
        title: str,
        subtitle: str = "",
        icon: str = "",
        animator: Animator | None = None,
        **kwargs: Any,
    ) -> None:
        """Создаёт карточку-раздел.

        Args:
            master: Родительский виджет.
            theme: Активная тема оформления.
            title: Заголовок раздела.
            subtitle: Пояснение под заголовком.
            icon: Имя иконки слева от заголовка.
            animator: Менеджер анимаций.
            **kwargs: Дополнительные параметры :class:`Card`.
        """
        super().__init__(master, theme, animator=animator, **kwargs)

        header = ctk.CTkFrame(self.body, fg_color="transparent", width=0, height=0)
        header.pack(fill="x")

        title_row = ctk.CTkFrame(header, fg_color="transparent", width=0, height=0)
        title_row.pack(side="left", fill="x", expand=True)

        if icon:
            ctk.CTkLabel(
                title_row,
                text="",
                image=icons.colored(icon, theme, "text_muted", 18),
                width=22,
            ).pack(side="left", padx=(0, Spacing.SM))

        labels = ctk.CTkFrame(title_row, fg_color="transparent", width=0, height=0)
        labels.pack(side="left", fill="x", expand=True)

        self.title_label = ctk.CTkLabel(
            labels,
            text=title,
            font=theme.font(FontRole.HEADING),
            text_color=theme.color("text"),
            anchor="w",
        )
        self.title_label.pack(fill="x", anchor="w")

        self.subtitle_label: ctk.CTkLabel | None = None
        if subtitle:
            self.subtitle_label = ctk.CTkLabel(
                labels,
                text=subtitle,
                font=theme.font(FontRole.SMALL),
                text_color=theme.color("text_muted"),
                anchor="w",
                justify="left",
            )
            self.subtitle_label.pack(fill="x", anchor="w", pady=(2, 0))

        self.actions = ctk.CTkFrame(header, fg_color="transparent", width=0, height=0)
        self.actions.pack(side="right")

        self.content = ctk.CTkFrame(self.body, fg_color="transparent", width=0, height=0)
        self.content.pack(fill="both", expand=True, pady=(Spacing.MD, 0))

    def set_subtitle(self, text: str) -> None:
        """Обновляет текст подзаголовка.

        Args:
            text: Новый текст.
        """
        if self.subtitle_label is not None:
            self.subtitle_label.configure(text=text)


class StatCard(Card):
    """Карточка ключевого показателя для панели мониторинга."""

    def __init__(
        self,
        master: Any,
        theme: Theme,
        *,
        title: str,
        value: str = "—",
        hint: str = "",
        icon: str = "chart",
        accent_role: str = "accent",
        animator: Animator | None = None,
        on_click: Callable[[], None] | None = None,
        **kwargs: Any,
    ) -> None:
        """Создаёт карточку показателя.

        Args:
            master: Родительский виджет.
            theme: Активная тема оформления.
            title: Название показателя.
            value: Значение показателя.
            hint: Пояснение под значением.
            icon: Имя иконки.
            accent_role: Роль цвета из палитры для иконки и значения.
            animator: Менеджер анимаций.
            on_click: Обработчик щелчка.
            **kwargs: Дополнительные параметры :class:`Card`.
        """
        super().__init__(
            master, theme, animator=animator, on_click=on_click, padding=Spacing.LG, **kwargs
        )
        self._accent_role = accent_role
        self._icon_name = icon

        top = ctk.CTkFrame(self.body, fg_color="transparent", width=0, height=0)
        top.pack(fill="x")

        ctk.CTkLabel(
            top,
            text=title.upper(),
            font=theme.font(FontRole.CAPTION),
            text_color=theme.color("text_muted"),
            anchor="w",
        ).pack(side="left")

        self._icon_label = ctk.CTkLabel(
            top, text="", image=icons.colored(icon, theme, accent_role, 18), width=20
        )
        self._icon_label.pack(side="right")

        self.value_label = ctk.CTkLabel(
            self.body,
            text=value,
            font=theme.font(FontRole.METRIC),
            text_color=theme.color(accent_role),
            anchor="w",
        )
        self.value_label.pack(fill="x", anchor="w", pady=(Spacing.SM, 0))

        self.hint_label = ctk.CTkLabel(
            self.body,
            text=hint,
            font=theme.font(FontRole.CAPTION),
            text_color=theme.color("text_muted"),
            anchor="w",
        )
        self.hint_label.pack(fill="x", anchor="w")

    def update_value(self, value: str, hint: str = "") -> None:
        """Обновляет значение показателя.

        Args:
            value: Новое значение.
            hint: Новое пояснение (пустая строка оставляет прежнее).
        """
        try:
            self.value_label.configure(text=value)
            if hint:
                self.hint_label.configure(text=hint)
        except Exception:
            pass

    def set_accent(self, role: str) -> None:
        """Меняет цветовую роль показателя.

        Args:
            role: Имя цвета в палитре.
        """
        self._accent_role = role
        try:
            self.value_label.configure(text_color=self._theme.color(role))
            self._icon_label.configure(image=icons.colored(self._icon_name, self._theme, role, 18))
        except Exception:
            pass
