"""Раздел журнала операций."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import customtkinter as ctk

from app.core.logging_setup import LogRecordView
from app.gui.theme import FontRole, Radius, Spacing
from app.gui.views.base_view import BaseView
from app.gui.widgets.controls import SegmentedFilter, ghost_button, secondary_button
from app.gui.widgets.search_entry import SearchEntry

_LOGGER = logging.getLogger(__name__)

#: Соответствие «фильтр → минимальный уровень».
_LEVELS: dict[str, int] = {
    "all": logging.NOTSET,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}

#: Максимум строк, выводимых в текстовое поле.
_MAX_LINES = 2000


class LogsView(BaseView):
    """Журнал операций с фильтрацией по уровню и поиском."""

    title = "Журнал операций"
    subtitle = "Индексация, подбор, ошибки и ручные исправления — всё, что делала программа"

    def __init__(self, master: Any, app: Any, **kwargs: Any) -> None:
        """Создаёт раздел.

        Args:
            master: Родительский виджет.
            app: Главное окно приложения.
            **kwargs: Дополнительные параметры ``CTkFrame``.
        """
        super().__init__(master, app, **kwargs)
        self._level = logging.NOTSET
        self._query = ""
        self._unsubscribe: Any = None
        self._follow = True

    def build(self) -> None:
        """Создаёт содержимое раздела."""
        secondary_button(
            self.actions,
            self.theme,
            text="Открыть файл журнала",
            icon="external",
            command=self._open_log_file,
        ).pack(side="right")

        toolbar = ctk.CTkFrame(self.content, fg_color="transparent", width=0, height=0)
        toolbar.pack(fill="x", pady=(0, Spacing.MD))

        self.search = SearchEntry(
            toolbar,
            self.theme,
            placeholder="Поиск по журналу…",
            on_search=self._on_search,
            width=360,
        )
        self.search.pack(side="left")

        SegmentedFilter(
            toolbar,
            self.theme,
            options=[
                ("all", "Всё"),
                ("info", "События"),
                ("warning", "Предупреждения"),
                ("error", "Ошибки"),
            ],
            on_change=self._on_level,
        ).pack(side="left", padx=(Spacing.MD, 0))

        self._follow_switch = ctk.CTkSwitch(
            toolbar,
            text="Следить",
            command=self._toggle_follow,
            font=self.theme.font(FontRole.SMALL),
            text_color=self.theme.color("text_muted"),
            progress_color=self.theme.color("accent"),
            button_color=self.theme.color("surface"),
            width=44,
        )
        self._follow_switch.select()
        self._follow_switch.pack(side="right")

        ghost_button(toolbar, self.theme, text="Очистить", icon="trash", command=self._clear).pack(
            side="right", padx=(0, Spacing.SM)
        )

        self._textbox = ctk.CTkTextbox(
            self.content,
            font=self.theme.font(FontRole.CAPTION, mono=True),
            fg_color=self.theme.color("surface"),
            text_color=self.theme.color("text"),
            border_width=1,
            border_color=self.theme.color("border"),
            corner_radius=Radius.MD,
            wrap="none",
        )
        self._textbox.pack(fill="both", expand=True)
        self._configure_tags()
        self._textbox.configure(state="disabled")

        self._status_label = ctk.CTkLabel(
            self.content,
            text="",
            font=self.theme.font(FontRole.CAPTION),
            text_color=self.theme.color("text_muted"),
            anchor="w",
        )
        self._status_label.pack(fill="x", pady=(Spacing.XS, 0))

        self._subscribe()
        self.refresh()

    # ------------------------------------------------------------- поведение
    def on_show(self) -> None:
        """Перечитывает журнал при открытии раздела."""
        self.refresh()

    def focus_search(self) -> None:
        """Передаёт фокус строке поиска."""
        self.ensure_built()
        self.search.focus_input()

    def refresh(self) -> None:
        """Полностью перерисовывает журнал."""
        handler = self.app.container.log_handler
        if handler is None:
            return

        records = handler.snapshot(min_level=self._level)
        if self._query:
            needle = self._query.lower()
            records = [record for record in records if needle in record.message.lower()]

        records = records[-_MAX_LINES:]

        self._textbox.configure(state="normal")
        self._textbox.delete("1.0", "end")
        for record in records:
            self._append_record(record)
        self._textbox.configure(state="disabled")
        if self._follow:
            self._textbox.see("end")

        self._status_label.configure(
            text=(
                f"Показано записей: {len(records)} · "
                f"файл журнала: {self.app.container.paths.log_file}"
            )
        )

    def _append_record(self, record: LogRecordView) -> None:
        """Добавляет запись в текстовое поле."""
        tag = _tag_for(record.level_number)
        try:
            self._textbox.insert("end", record.format() + "\n", tag)
        except Exception:
            pass

    def _configure_tags(self) -> None:
        """Настраивает цвета уровней журнала."""
        try:
            self._textbox.tag_config("error", foreground=self.theme.resolved("danger"))
            self._textbox.tag_config("warning", foreground=self.theme.resolved("warning"))
            self._textbox.tag_config("info", foreground=self.theme.resolved("text"))
            self._textbox.tag_config("debug", foreground=self.theme.resolved("text_muted"))
        except Exception:
            pass

    def _subscribe(self) -> None:
        """Подписывается на новые записи журнала."""
        handler = self.app.container.log_handler
        if handler is None:
            return

        def _listener(record: LogRecordView) -> None:
            # Обработчик вызывается из произвольного потока — перенос
            # в поток интерфейса обязателен.
            try:
                self.app.after(0, lambda: self._on_record(record))
            except Exception:
                pass

        self._unsubscribe = handler.subscribe(_listener)

    def _on_record(self, record: LogRecordView) -> None:
        """Добавляет новую запись, если она проходит фильтры."""
        if not self.winfo_exists() or not self._follow:
            return
        if record.level_number < self._level:
            return
        if self._query and self._query.lower() not in record.message.lower():
            return
        try:
            self._textbox.configure(state="normal")
            self._append_record(record)
            self._textbox.configure(state="disabled")
            self._textbox.see("end")
        except Exception:
            pass

    def _on_level(self, value: str) -> None:
        """Меняет минимальный уровень отображаемых записей."""
        self._level = _LEVELS.get(value, logging.NOTSET)
        self.refresh()

    def _on_search(self, query: str) -> None:
        """Меняет строку фильтрации."""
        self._query = query
        self.refresh()

    def _toggle_follow(self) -> None:
        """Включает или выключает автопрокрутку."""
        self._follow = bool(self._follow_switch.get())
        if self._follow:
            self.refresh()

    def _clear(self) -> None:
        """Очищает экранный буфер журнала."""
        handler = self.app.container.log_handler
        if handler is not None:
            handler.clear()
        self.refresh()
        self.app.toasts.info("Экранный журнал очищен. Файл журнала сохранён.")

    def _open_log_file(self) -> None:
        """Открывает файл журнала во внешней программе."""
        path: Path = self.app.container.paths.log_file
        if path.exists():
            self.app.open_path(path)
        else:
            self.app.toasts.warning("Файл журнала ещё не создан")

    def on_hide(self) -> None:
        """Ничего не делает: подписка сохраняется для накопления записей."""

    def destroy(self) -> None:
        """Отписывается от журнала при уничтожении раздела."""
        if self._unsubscribe is not None:
            try:
                self._unsubscribe()
            except Exception:
                pass
            self._unsubscribe = None
        super().destroy()

    def refresh_theme(self) -> None:
        """Обновляет цвета после смены темы."""
        super().refresh_theme()
        try:
            self._textbox.configure(
                fg_color=self.theme.color("surface"),
                text_color=self.theme.color("text"),
                border_color=self.theme.color("border"),
            )
            self._configure_tags()
        except Exception:
            pass


def _tag_for(level: int) -> str:
    """Возвращает тег оформления для уровня журнала."""
    if level >= logging.ERROR:
        return "error"
    if level >= logging.WARNING:
        return "warning"
    if level >= logging.INFO:
        return "info"
    return "debug"
