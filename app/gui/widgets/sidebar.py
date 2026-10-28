"""Боковая панель навигации."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import customtkinter as ctk

from app.core.constants import APP_COMPANY, APP_NAME, APP_VERSION
from app.gui.animations import DURATION_NORMAL, Animator
from app.gui.icons import icons
from app.gui.theme import FontRole, Radius, Sizes, Spacing, Theme
from app.gui.widgets.controls import Tooltip


@dataclass(frozen=True, slots=True)
class NavItem:
    """Пункт навигации.

    Attributes:
        key: Идентификатор раздела.
        title: Название.
        icon: Имя иконки.
        shortcut: Подпись горячей клавиши.
    """

    key: str
    title: str
    icon: str
    shortcut: str = ""


class NavButton(ctk.CTkButton):
    """Кнопка раздела с индикатором активности."""

    def __init__(
        self,
        master: Any,
        theme: Theme,
        *,
        item: NavItem,
        command: Callable[[], None],
        **kwargs: Any,
    ) -> None:
        """Создаёт кнопку раздела.

        Args:
            master: Родительский виджет.
            theme: Активная тема оформления.
            item: Описание пункта навигации.
            command: Обработчик нажатия.
            **kwargs: Дополнительные параметры ``CTkButton``.
        """
        self._theme = theme
        self._item = item
        self._active = False

        super().__init__(
            master,
            text=f"  {item.title}",
            image=icons.colored(item.icon, theme, "text_muted", 19),
            compound="left",
            anchor="w",
            height=42,
            corner_radius=Radius.MD,
            font=theme.font(FontRole.BODY),
            fg_color="transparent",
            hover_color=theme.color("surface_hover"),
            text_color=theme.color("text_muted"),
            command=command,
            **kwargs,
        )
        self._tooltip = Tooltip(self, theme, text=self._tooltip_text())

    def _tooltip_text(self) -> str:
        """Формирует текст подсказки с горячей клавишей."""
        return (
            f"{self._item.title} ({self._item.shortcut})"
            if self._item.shortcut
            else self._item.title
        )

    def set_active(self, value: bool, *, force: bool = False) -> None:
        """Отмечает раздел активным.

        Args:
            value: Новое состояние.
            force: Перерисовать даже при неизменившемся состоянии (нужно
                после смены темы, когда меняются цвета, а не состояние).
        """
        if value == self._active and not force:
            return
        self._active = value
        role = "accent" if value else "text_muted"
        try:
            self.configure(
                fg_color=self._theme.color("accent_soft") if value else "transparent",
                text_color=self._theme.color("accent" if value else "text_muted"),
                font=self._theme.font(FontRole.BODY_STRONG if value else FontRole.BODY),
                image=icons.colored(self._item.icon, self._theme, role, 19),
            )
        except Exception:
            pass

    def set_collapsed(self, collapsed: bool) -> None:
        """Переключает компактный режим (только иконка).

        Args:
            collapsed: Свернуть ли подпись.
        """
        try:
            self.configure(
                text="" if collapsed else f"  {self._item.title}",
                anchor="center" if collapsed else "w",
            )
            self._tooltip.update_text(self._tooltip_text())
        except Exception:
            pass


class Sidebar(ctk.CTkFrame):
    """Панель навигации с логотипом, разделами и нижним блоком состояния."""

    def __init__(
        self,
        master: Any,
        theme: Theme,
        animator: Animator,
        *,
        items: Sequence[NavItem],
        on_navigate: Callable[[str], None],
        on_toggle_theme: Callable[[], None],
        on_toggle_collapse: Callable[[bool], None] | None = None,
        expanded: bool = True,
        **kwargs: Any,
    ) -> None:
        """Создаёт боковую панель.

        Args:
            master: Родительский виджет.
            theme: Активная тема оформления.
            animator: Менеджер анимаций.
            items: Пункты навигации.
            on_navigate: Обработчик перехода в раздел.
            on_toggle_theme: Обработчик смены темы.
            on_toggle_collapse: Обработчик сворачивания панели.
            expanded: Раскрыта ли панель изначально.
            **kwargs: Дополнительные параметры ``CTkFrame``.
        """
        self._theme = theme
        self._animator = animator
        self._on_navigate = on_navigate
        self._on_toggle_collapse = on_toggle_collapse
        self._expanded = expanded
        self._buttons: dict[str, NavButton] = {}
        self._active = ""

        super().__init__(
            master,
            fg_color=theme.color("surface_alt"),
            corner_radius=0,
            width=Sizes.SIDEBAR_WIDTH if expanded else Sizes.SIDEBAR_COLLAPSED,
            **kwargs,
        )
        self.pack_propagate(False)

        # --- Логотип --------------------------------------------------------
        brand = ctk.CTkFrame(self, fg_color="transparent", width=0, height=0)
        brand.pack(fill="x", padx=Spacing.MD, pady=(Spacing.LG, Spacing.XL))

        self._logo = ctk.CTkFrame(
            brand, fg_color=theme.color("accent"), corner_radius=Radius.MD, width=36, height=36
        )
        self._logo.pack(side="left")
        self._logo.pack_propagate(False)
        self._logo_icon = ctk.CTkLabel(
            self._logo,
            text="",
            image=icons.get("shield_check", 20, light_color="#FFFFFF", dark_color="#FFFFFF"),
        )
        self._logo_icon.pack(expand=True)

        self._brand_texts = ctk.CTkFrame(brand, fg_color="transparent", width=0, height=0)
        self._brand_texts.pack(side="left", padx=(Spacing.SM, 0), fill="x", expand=True)

        ctk.CTkLabel(
            self._brand_texts,
            text="CertMatcher",
            font=theme.font(FontRole.SUBHEADING),
            text_color=theme.color("text"),
            anchor="w",
        ).pack(fill="x", anchor="w")
        ctk.CTkLabel(
            self._brand_texts,
            text=APP_COMPANY,
            font=theme.font(FontRole.CAPTION),
            text_color=theme.color("text_muted"),
            anchor="w",
        ).pack(fill="x", anchor="w")

        # --- Разделы --------------------------------------------------------
        navigation = ctk.CTkFrame(self, fg_color="transparent", width=0, height=0)
        navigation.pack(fill="both", expand=True, padx=Spacing.SM)

        for item in items:
            button = NavButton(navigation, theme, item=item, command=self._make_navigate(item.key))
            button.pack(fill="x", pady=2)
            self._buttons[item.key] = button

        # --- Нижний блок ----------------------------------------------------
        footer = ctk.CTkFrame(self, fg_color="transparent", width=0, height=0)
        footer.pack(fill="x", padx=Spacing.SM, pady=Spacing.MD)

        self._status_label = ctk.CTkLabel(
            footer,
            text="",
            font=theme.font(FontRole.CAPTION),
            text_color=theme.color("text_muted"),
            anchor="w",
            justify="left",
            wraplength=Sizes.SIDEBAR_WIDTH - 32,
        )
        self._status_label.pack(fill="x", padx=Spacing.SM, pady=(0, Spacing.SM))

        controls = ctk.CTkFrame(footer, fg_color="transparent", width=0, height=0)
        controls.pack(fill="x")

        self._theme_button = ctk.CTkButton(
            controls,
            text="",
            image=icons.colored("moon" if not theme.is_dark else "sun", theme, "text_muted", 18),
            width=36,
            height=36,
            corner_radius=Radius.MD,
            fg_color="transparent",
            hover_color=theme.color("surface_hover"),
            command=on_toggle_theme,
        )
        self._theme_button.pack(side="left")
        Tooltip(self._theme_button, theme, text="Светлая / тёмная тема (Ctrl+T)")

        self._collapse_button = ctk.CTkButton(
            controls,
            text="",
            image=icons.colored("chevron_right", theme, "text_muted", 18),
            width=36,
            height=36,
            corner_radius=Radius.MD,
            fg_color="transparent",
            hover_color=theme.color("surface_hover"),
            command=self.toggle_collapse,
        )
        self._collapse_button.pack(side="right")
        Tooltip(self._collapse_button, theme, text="Свернуть панель (Ctrl+B)")

        self._version_label = ctk.CTkLabel(
            footer,
            text=f"{APP_NAME.split()[-1]} {APP_VERSION}",
            font=theme.font(FontRole.CAPTION),
            text_color=theme.color("text_muted"),
        )
        self._version_label.pack(pady=(Spacing.SM, 0))

        if not expanded:
            self._apply_collapsed(True)

    # ---------------------------------------------------------------- API
    @property
    def expanded(self) -> bool:
        """Раскрыта ли панель."""
        return self._expanded

    @property
    def active(self) -> str:
        """Идентификатор активного раздела."""
        return self._active

    def set_active(self, key: str) -> None:
        """Отмечает раздел активным.

        Args:
            key: Идентификатор раздела.
        """
        self._active = key
        for item_key, button in self._buttons.items():
            button.set_active(item_key == key)

    def set_status(self, text: str) -> None:
        """Обновляет строку состояния внизу панели.

        Args:
            text: Текст состояния.
        """
        try:
            self._status_label.configure(text=text)
        except Exception:
            pass

    def update_theme_icon(self) -> None:
        """Обновляет иконку переключателя темы."""
        try:
            self._theme_button.configure(
                image=icons.colored(
                    "sun" if self._theme.is_dark else "moon", self._theme, "text_muted", 18
                )
            )
        except Exception:
            pass

    def toggle_collapse(self) -> None:
        """Переключает свёрнутое состояние панели."""
        self._expanded = not self._expanded
        target = Sizes.SIDEBAR_WIDTH if self._expanded else Sizes.SIDEBAR_COLLAPSED
        current = self.winfo_width() or target

        def _apply(value: float) -> None:
            try:
                self.configure(width=int(value))
            except Exception:
                pass

        self._animator.animate(
            self,
            f"sidebar-{id(self)}",
            start=float(current),
            end=float(target),
            duration=DURATION_NORMAL,
            on_frame=_apply,
            on_complete=lambda: self._apply_collapsed(not self._expanded),
        )

        if self._on_toggle_collapse is not None:
            self._on_toggle_collapse(self._expanded)

    def _apply_collapsed(self, collapsed: bool) -> None:
        """Переключает содержимое панели в компактный режим."""
        for button in self._buttons.values():
            button.set_collapsed(collapsed)
        try:
            if collapsed:
                self._brand_texts.pack_forget()
                self._status_label.pack_forget()
                self._version_label.pack_forget()
            else:
                self._brand_texts.pack(side="left", padx=(Spacing.SM, 0), fill="x", expand=True)
                self._status_label.pack(fill="x", padx=Spacing.SM, pady=(0, Spacing.SM))
                self._version_label.pack(pady=(Spacing.SM, 0))
        except Exception:
            pass

    def _make_navigate(self, key: str) -> Callable[[], None]:
        """Создаёт обработчик перехода в конкретный раздел.

        Именованная фабрика вместо ``lambda key=key: ...`` внутри цикла —
        нагляднее и не полагается на приём «умолчание фиксирует значение».

        Args:
            key: Идентификатор раздела.

        Returns:
            Обработчик без аргументов для кнопки раздела.
        """
        return lambda: self._navigate(key)

    def _navigate(self, key: str) -> None:
        """Переходит в раздел."""
        self.set_active(key)
        self._on_navigate(key)

    def refresh_theme(self) -> None:
        """Обновляет цвета после смены темы."""
        try:
            self.configure(fg_color=self._theme.color("surface_alt"))
            self._logo.configure(fg_color=self._theme.color("accent"))
            self.update_theme_icon()
            for key, button in self._buttons.items():
                button.set_active(key == self._active, force=True)
        except Exception:
            pass
