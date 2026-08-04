"""Строка поиска с иконкой, отложенным вводом и кнопкой очистки."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from app.gui.icons import icons
from app.gui.theme import FontRole, Radius, Sizes, Spacing, Theme


class SearchEntry(ctk.CTkFrame):
    """Поле поиска, вызывающее обработчик после паузы в наборе.

    Задержка обязательна: без неё каждый символ порождал бы запрос к базе,
    и при быстром наборе интерфейс начинал бы «захлёбываться».
    """

    def __init__(
        self,
        master: Any,
        theme: Theme,
        *,
        placeholder: str = "Поиск…",
        on_search: Callable[[str], None],
        delay_ms: int = 250,
        width: int = 320,
        **kwargs: Any,
    ) -> None:
        """Создаёт строку поиска.

        Args:
            master: Родительский виджет.
            theme: Активная тема оформления.
            placeholder: Текст-подсказка.
            on_search: Обработчик поиска; получает введённый текст.
            delay_ms: Пауза после последнего нажатия клавиши.
            width: Ширина поля.
            **kwargs: Дополнительные параметры ``CTkFrame``.
        """
        self._theme = theme
        self._on_search = on_search
        self._delay_ms = delay_ms
        self._after_id: str | None = None

        super().__init__(
            master,
            fg_color=theme.color("surface_alt"),
            corner_radius=Radius.MD,
            border_width=1,
            border_color=theme.color("border"),
            height=Sizes.INPUT_HEIGHT,
            width=width,
            **kwargs,
        )
        self.pack_propagate(False)

        ctk.CTkLabel(
            self, text="", image=icons.colored("search", theme, "text_muted", 16), width=18
        ).pack(side="left", padx=(Spacing.MD, Spacing.XS))

        self.variable = ctk.StringVar()
        self.entry = ctk.CTkEntry(
            self,
            textvariable=self.variable,
            placeholder_text=placeholder,
            border_width=0,
            fg_color="transparent",
            font=theme.font(FontRole.BODY),
            text_color=theme.color("text"),
            placeholder_text_color=theme.color("text_muted"),
        )
        self.entry.pack(side="left", fill="both", expand=True, padx=(0, Spacing.XS))

        self._clear_button = ctk.CTkButton(
            self,
            text="",
            image=icons.colored("close", theme, "text_muted", 14),
            width=24,
            height=24,
            corner_radius=Radius.SM,
            fg_color="transparent",
            hover_color=theme.color("surface_hover"),
            command=self.clear,
        )

        self.variable.trace_add("write", lambda *_: self._schedule())
        self.entry.bind("<Return>", lambda _: self._fire(immediate=True))
        self.entry.bind("<Escape>", lambda _: self.clear())

    @property
    def value(self) -> str:
        """Текущий текст запроса."""
        return str(self.variable.get()).strip()

    def focus_input(self) -> None:
        """Передаёт фокус ввода полю поиска."""
        try:
            self.entry.focus_set()
            self.entry.select_range(0, "end")
        except Exception:
            pass

    def set_value(self, value: str, *, notify: bool = False) -> None:
        """Устанавливает текст запроса.

        Args:
            value: Новый текст.
            notify: Вызывать ли обработчик поиска.
        """
        self.variable.set(value)
        if notify:
            self._fire(immediate=True)

    def clear(self) -> None:
        """Очищает поле и выполняет пустой поиск."""
        self.variable.set("")
        self._fire(immediate=True)

    def _schedule(self) -> None:
        """Планирует поиск после паузы в наборе."""
        self._update_clear_button()
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
        try:
            self._after_id = self.after(self._delay_ms, self._fire)
        except Exception:
            pass

    def _fire(self, *, immediate: bool = False) -> None:
        """Вызывает обработчик поиска."""
        if immediate and self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        try:
            self._on_search(self.value)
        except Exception:
            pass

    def _update_clear_button(self) -> None:
        """Показывает или скрывает кнопку очистки."""
        try:
            if self.variable.get():
                self._clear_button.pack(side="right", padx=(0, Spacing.SM))
            else:
                self._clear_button.pack_forget()
        except Exception:
            pass
