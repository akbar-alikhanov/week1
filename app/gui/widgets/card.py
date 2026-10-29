"""Карточки — основной строительный блок макета."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from app.gui.animations import Animator
from app.gui.icons import icons
from app.gui.theme import FontRole, Radius, Sizes, Spacing, Theme
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
    """Карточка с заголовком, подзаголовком, областью действий и опциональным сворачиванием."""

    def __init__(
        self,
        master: Any,
        theme: Theme,
        *,
        title: str,
        subtitle: str = "",
        icon: str = "",
        icon_role: str = "accent",
        animator: Animator | None = None,
        collapsible: bool = False,
        collapsed: bool = False,
        compact_text: str = "",
        on_toggle: Callable[[bool], None] | None = None,
        **kwargs: Any,
    ) -> None:
        """Создаёт карточку-раздел.

        Args:
            master: Родительский виджет.
            theme: Активная тема оформления.
            title: Заголовок раздела.
            subtitle: Пояснение под заголовком (видно в развёрнутом состоянии).
            icon: Имя иконки слева от заголовка; при наличии рисуется в
                цветной плитке — так же, как иконка :class:`StatCard`.
            icon_role: Роль цвета плитки и иконки из палитры.
            animator: Менеджер анимаций.
            collapsible: Показывать ли шеврон для сворачивания содержимого.
            collapsed: Начальное состояние (имеет смысл только при
                ``collapsible=True``).
            compact_text: Текст подзаголовка в свёрнутом состоянии (вместо
                ``subtitle``) — например, сводка выбранных файлов.
            on_toggle: Обработчик смены состояния (получает новое значение
                ``collapsed``).
            **kwargs: Дополнительные параметры :class:`Card`.
        """
        super().__init__(master, theme, animator=animator, **kwargs)
        self._subtitle = subtitle
        self._compact_text = compact_text
        self._collapsed = collapsed and collapsible
        self._on_toggle = on_toggle

        header = ctk.CTkFrame(self.body, fg_color="transparent", width=0, height=0)
        header.pack(fill="x")

        title_row = ctk.CTkFrame(header, fg_color="transparent", width=0, height=0)
        title_row.pack(side="left", fill="x", expand=True)

        if icon:
            tile = ctk.CTkFrame(
                title_row,
                fg_color=theme.color(f"{icon_role}_soft"),
                corner_radius=Radius.MD,
                width=Sizes.TILE_SM,
                height=Sizes.TILE_SM,
            )
            tile.pack(side="left", padx=(0, Spacing.SM))
            tile.pack_propagate(False)
            ctk.CTkLabel(tile, text="", image=icons.colored(icon, theme, icon_role, 16)).pack(
                expand=True
            )

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
        if subtitle or compact_text:
            self.subtitle_label = ctk.CTkLabel(
                labels,
                text=self._compact_text if self._collapsed else subtitle,
                font=theme.font(FontRole.SMALL),
                text_color=theme.color("text_muted"),
                anchor="w",
                justify="left",
            )
            self.subtitle_label.pack(fill="x", anchor="w", pady=(2, 0))

        self.actions = ctk.CTkFrame(header, fg_color="transparent", width=0, height=0)
        self.actions.pack(side="right")

        self._toggle_button: ctk.CTkButton | None = None
        if collapsible:
            self._toggle_button = ctk.CTkButton(
                self.actions,
                text="",
                image=icons.colored(
                    "chevron_right" if self._collapsed else "chevron_down", theme, "text_muted", 16
                ),
                width=30,
                height=30,
                corner_radius=Radius.SM,
                fg_color="transparent",
                hover_color=theme.color("surface_hover"),
                command=self.toggle_collapsed,
            )
            self._toggle_button.pack(side="right")

        self.content = ctk.CTkFrame(self.body, fg_color="transparent", width=0, height=0)
        if not self._collapsed:
            self.content.pack(fill="both", expand=True, pady=(Spacing.MD, 0))

    def set_subtitle(self, text: str) -> None:
        """Обновляет текст подзаголовка (в развёрнутом состоянии).

        Args:
            text: Новый текст.
        """
        self._subtitle = text
        if self.subtitle_label is not None and not self._collapsed:
            self.subtitle_label.configure(text=text)

    def set_compact_text(self, text: str) -> None:
        """Обновляет текст подзаголовка, показываемый в свёрнутом состоянии.

        Args:
            text: Новый текст (например, сводка выбранных файлов).
        """
        self._compact_text = text
        if self.subtitle_label is not None and self._collapsed:
            self.subtitle_label.configure(text=text)

    def toggle_collapsed(self) -> None:
        """Переключает развёрнутое/свёрнутое состояние."""
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, value: bool) -> None:
        """Устанавливает развёрнутое/свёрнутое состояние.

        Args:
            value: ``True`` — свернуть содержимое.
        """
        if value == self._collapsed:
            return
        self._collapsed = value
        if value:
            self.content.pack_forget()
        else:
            self.content.pack(fill="both", expand=True, pady=(Spacing.MD, 0))
        try:
            if self.subtitle_label is not None:
                self.subtitle_label.configure(text=self._compact_text if value else self._subtitle)
            if self._toggle_button is not None:
                name = "chevron_right" if value else "chevron_down"
                self._toggle_button.configure(
                    image=icons.colored(name, self._theme, "text_muted", 16)
                )
        except Exception:
            pass
        if self._on_toggle is not None:
            self._on_toggle(value)


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

        self._icon_tile = ctk.CTkFrame(
            top,
            fg_color=theme.color(f"{accent_role}_soft"),
            corner_radius=Radius.MD,
            width=Sizes.TILE_SM,
            height=Sizes.TILE_SM,
        )
        self._icon_tile.pack(side="right")
        self._icon_tile.pack_propagate(False)
        self._icon_label = ctk.CTkLabel(
            self._icon_tile, text="", image=icons.colored(icon, theme, accent_role, 16)
        )
        self._icon_label.pack(expand=True)

        self.value_label = ctk.CTkLabel(
            self.body,
            text=value,
            font=theme.font(FontRole.METRIC, mono=True),
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
            self._icon_tile.configure(fg_color=self._theme.color(f"{role}_soft"))
            self._icon_label.configure(image=icons.colored(self._icon_name, self._theme, role, 16))
        except Exception:
            pass


class RunHeaderCard(Card):
    """Карточка-«герой» конкретной обработки: файл, время, место под действия.

    Один и тот же компонент используется и для текущего запуска на экране
    подбора, и для просматриваемого запуска в истории — единый визуальный
    язык для «это про один конкретный файл», а не разные самодельные блоки.
    """

    def __init__(
        self,
        master: Any,
        theme: Theme,
        *,
        icon: str = "excel",
        icon_role: str = "accent",
        eyebrow: str = "",
        title: str = "",
        meta: str = "",
        animator: Animator | None = None,
        **kwargs: Any,
    ) -> None:
        """Создаёт карточку.

        Args:
            master: Родительский виджет.
            theme: Активная тема оформления.
            icon: Имя иконки в плитке слева.
            icon_role: Роль цвета плитки и иконки.
            eyebrow: Короткая надпись над заголовком (капслоком, моно).
            title: Заголовок — как правило, имя файла.
            meta: Строка с подробностями под заголовком.
            animator: Менеджер анимаций.
            **kwargs: Дополнительные параметры :class:`Card`.
        """
        super().__init__(master, theme, animator=animator, **kwargs)
        self._icon_name = icon
        self._icon_role = icon_role

        header = ctk.CTkFrame(self.body, fg_color="transparent", width=0, height=0)
        header.pack(fill="x")

        left = ctk.CTkFrame(header, fg_color="transparent", width=0, height=0)
        left.pack(side="left", fill="x", expand=True)

        self._icon_tile = ctk.CTkFrame(
            left,
            fg_color=theme.color(f"{icon_role}_soft"),
            corner_radius=Radius.MD,
            width=Sizes.TILE_LG,
            height=Sizes.TILE_LG,
        )
        self._icon_tile.pack(side="left", padx=(0, Spacing.MD))
        self._icon_tile.pack_propagate(False)
        self._icon_label = ctk.CTkLabel(
            self._icon_tile, text="", image=icons.colored(icon, theme, icon_role, 20)
        )
        self._icon_label.pack(expand=True)

        labels = ctk.CTkFrame(left, fg_color="transparent", width=0, height=0)
        labels.pack(side="left", fill="x", expand=True)

        self.eyebrow_label = ctk.CTkLabel(
            labels,
            text=eyebrow.upper(),
            font=theme.font(FontRole.CAPTION, mono=True),
            text_color=theme.color("text_muted"),
            anchor="w",
        )
        self.eyebrow_label.pack(fill="x", anchor="w")

        self.title_label = ctk.CTkLabel(
            labels,
            text=title,
            font=theme.font(FontRole.TITLE),
            text_color=theme.color("text"),
            anchor="w",
            justify="left",
            wraplength=560,
        )
        self.title_label.pack(fill="x", anchor="w", pady=(3, 0))

        self.meta_label = ctk.CTkLabel(
            labels,
            text=meta,
            font=theme.font(FontRole.SMALL),
            text_color=theme.color("text_muted"),
            anchor="w",
        )
        self.meta_label.pack(fill="x", anchor="w", pady=(4, 0))

        self.actions = ctk.CTkFrame(header, fg_color="transparent", width=0, height=0)
        self.actions.pack(side="right")

    def update(
        self,
        *,
        icon: str | None = None,
        icon_role: str | None = None,
        eyebrow: str | None = None,
        title: str | None = None,
        meta: str | None = None,
    ) -> None:
        """Обновляет содержимое карточки без пересборки виджетов.

        Args:
            icon: Новое имя иконки; ``None`` — оставить прежнюю.
            icon_role: Новая роль цвета; ``None`` — оставить прежнюю.
            eyebrow: Новая надпись над заголовком; ``None`` — не менять.
            title: Новый заголовок; ``None`` — не менять.
            meta: Новая строка подробностей; ``None`` — не менять.
        """
        try:
            if icon is not None:
                self._icon_name = icon
            if icon_role is not None:
                self._icon_role = icon_role
            if icon is not None or icon_role is not None:
                self._icon_tile.configure(fg_color=self._theme.color(f"{self._icon_role}_soft"))
                self._icon_label.configure(
                    image=icons.colored(self._icon_name, self._theme, self._icon_role, 20)
                )
            if eyebrow is not None:
                self.eyebrow_label.configure(text=eyebrow.upper())
            if title is not None:
                self.title_label.configure(text=title)
            if meta is not None:
                self.meta_label.configure(text=meta)
        except Exception:
            pass

    def refresh_theme(self) -> None:
        """Перечитывает цвета после смены темы."""
        super().refresh_theme()
        try:
            self.eyebrow_label.configure(text_color=self._theme.color("text_muted"))
            self.title_label.configure(text_color=self._theme.color("text"))
            self.meta_label.configure(text_color=self._theme.color("text_muted"))
            self._icon_tile.configure(fg_color=self._theme.color(f"{self._icon_role}_soft"))
            self._icon_label.configure(
                image=icons.colored(self._icon_name, self._theme, self._icon_role, 20)
            )
        except Exception:
            pass
