"""Таблица данных с сортировкой, контекстным меню и цветными статусами.

CustomTkinter не содержит таблицы, поэтому используется ``ttk.Treeview``,
стилизованный под общее оформление. Выбор обоснован: Treeview — единственный
виджет Tk, который отрисовывает десятки тысяч строк без потери отзывчивости,
и он поддерживает виртуальную прокрутку из коробки.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, Literal

import customtkinter as ctk

from app.gui.theme import FontRole, Radius, Spacing, Theme

_LOGGER = logging.getLogger(__name__)

#: Значения выравнивания, которые допускает ``ttk.Treeview``.
TkAnchor = Literal["nw", "n", "ne", "w", "center", "e", "sw", "s", "se"]


@dataclass(frozen=True, slots=True)
class Column:
    """Описание колонки таблицы.

    Attributes:
        key: Идентификатор колонки.
        title: Заголовок.
        width: Ширина в пикселях.
        anchor: Выравнивание содержимого (``w``, ``center``, ``e``).
        stretch: Растягивать ли колонку при изменении размера окна.
        sortable: Разрешена ли сортировка по колонке.
        numeric: Сортировать ли значения как числа.
    """

    key: str
    title: str
    width: int = 140
    anchor: TkAnchor = "w"
    stretch: bool = False
    sortable: bool = True
    numeric: bool = False


class DataTable(ctk.CTkFrame):
    """Таблица со строками, окрашенными по статусу."""

    #: Соответствие «тег строки → роль цвета фона в палитре».
    STATUS_TAGS: ClassVar[dict[str, str]] = {
        "matched": "success_soft",
        "manual": "success_soft",
        "ambiguous": "warning_soft",
        "not_found": "danger_soft",
        "expired": "danger_soft",
        "warning": "warning_soft",
        "muted": "surface_alt",
    }

    def __init__(
        self,
        master: Any,
        theme: Theme,
        *,
        columns: Sequence[Column],
        on_select: Callable[[str], None] | None = None,
        on_activate: Callable[[str], None] | None = None,
        context_actions: Sequence[tuple[str, Callable[[str], None]]] = (),
        height: int = 14,
        **kwargs: Any,
    ) -> None:
        """Создаёт таблицу.

        Args:
            master: Родительский виджет.
            theme: Активная тема оформления.
            columns: Описания колонок.
            on_select: Обработчик выбора строки (получает её идентификатор).
            on_activate: Обработчик двойного щелчка.
            context_actions: Пункты контекстного меню.
            height: Высота в строках.
            **kwargs: Дополнительные параметры ``CTkFrame``.
        """
        from tkinter import ttk

        self._theme = theme
        self._columns = list(columns)
        self._on_select = on_select
        self._on_activate = on_activate
        self._sort_column = ""
        self._sort_reverse = False
        self._row_values: dict[str, dict[str, Any]] = {}

        super().__init__(
            master,
            fg_color=theme.color("surface"),
            corner_radius=Radius.MD,
            border_width=1,
            border_color=theme.color("border"),
            **kwargs,
        )

        theme.style_treeview(self)

        container = ctk.CTkFrame(self, fg_color="transparent", width=0, height=0)
        container.pack(fill="both", expand=True, padx=1, pady=1)

        self.tree = ttk.Treeview(
            container,
            columns=[column.key for column in self._columns],
            show="headings",
            height=height,
            style="CertMatcher.Treeview",
            selectmode="browse",
        )

        for column in self._columns:
            if column.sortable:
                self.tree.heading(
                    column.key,
                    text=column.title,
                    anchor=column.anchor,
                    command=lambda key=column.key: self.sort_by(key),
                )
            else:
                self.tree.heading(column.key, text=column.title, anchor=column.anchor)
            self.tree.column(
                column.key, width=column.width, anchor=column.anchor, stretch=column.stretch
            )

        scrollbar = ttk.Scrollbar(
            container,
            orient="vertical",
            command=self.tree.yview,
            style="CertMatcher.Vertical.TScrollbar",
        )
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._apply_tag_colors()

        self.tree.bind("<<TreeviewSelect>>", self._handle_select)
        self.tree.bind("<Double-1>", self._handle_activate)
        self.tree.bind("<Return>", self._handle_activate)

        self._menu: Any = None
        if context_actions:
            self._build_context_menu(context_actions)

    # ------------------------------------------------------------- свойства
    @property
    def selected_id(self) -> str:
        """Идентификатор выбранной строки (пустая строка, если выбора нет)."""
        selection = self.tree.selection()
        return str(selection[0]) if selection else ""

    @property
    def row_count(self) -> int:
        """Количество строк в таблице."""
        return len(self.tree.get_children(""))

    def values_for(self, row_id: str) -> dict[str, Any]:
        """Возвращает исходные значения строки.

        Args:
            row_id: Идентификатор строки.

        Returns:
            Словарь значений; пустой, если строка не найдена.
        """
        return self._row_values.get(row_id, {})

    # ---------------------------------------------------------------- данные
    def set_rows(self, rows: Sequence[tuple[str, dict[str, Any], str]]) -> None:
        """Полностью заменяет содержимое таблицы.

        Args:
            rows: Кортежи ``(идентификатор, значения, тег статуса)``.
        """
        selected = self.selected_id
        self.tree.delete(*self.tree.get_children(""))
        self._row_values.clear()

        for row_id, values, tag in rows:
            display = [_format(values.get(column.key)) for column in self._columns]
            try:
                self.tree.insert("", "end", iid=row_id, values=display, tags=(tag,) if tag else ())
            except Exception:
                continue
            self._row_values[row_id] = values

        if selected and selected in self._row_values:
            self.tree.selection_set(selected)
            self.tree.see(selected)

        if self._sort_column:
            self._sort(self._sort_column, self._sort_reverse)

    def clear(self) -> None:
        """Удаляет все строки."""
        self.tree.delete(*self.tree.get_children(""))
        self._row_values.clear()

    def select_first(self) -> None:
        """Выбирает первую строку таблицы."""
        children = self.tree.get_children("")
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])

    # ------------------------------------------------------------ сортировка
    def sort_by(self, key: str) -> None:
        """Сортирует таблицу по колонке, переключая направление.

        Args:
            key: Идентификатор колонки.
        """
        reverse = self._sort_reverse if key != self._sort_column else not self._sort_reverse
        self._sort(key, reverse)

    def _sort(self, key: str, reverse: bool) -> None:
        """Выполняет сортировку строк."""
        column = next((item for item in self._columns if item.key == key), None)
        if column is None:
            return

        def _sort_key(row_id: str) -> Any:
            value = self._row_values.get(row_id, {}).get(key)
            if column.numeric:
                try:
                    return float(str(value).replace("%", "").replace(",", ".").strip() or 0)
                except (TypeError, ValueError):
                    return 0.0
            return str(value or "").lower()

        rows = sorted(self.tree.get_children(""), key=_sort_key, reverse=reverse)
        for index, row_id in enumerate(rows):
            self.tree.move(row_id, "", index)

        self._sort_column = key
        self._sort_reverse = reverse
        for item in self._columns:
            marker = ""
            if item.key == key:
                marker = "  ↓" if reverse else "  ↑"
            self.tree.heading(item.key, text=item.title + marker)

    # ------------------------------------------------------------- события
    def _handle_select(self, _: Any = None) -> None:
        """Передаёт выбор строки обработчику."""
        if self._on_select is not None and self.selected_id:
            self._on_select(self.selected_id)

    def _handle_activate(self, _: Any = None) -> str:
        """Передаёт двойной щелчок обработчику."""
        if self._on_activate is not None and self.selected_id:
            self._on_activate(self.selected_id)
        return "break"

    def _build_context_menu(self, actions: Sequence[tuple[str, Callable[[str], None]]]) -> None:
        """Создаёт контекстное меню таблицы."""
        import tkinter as tk

        menu = tk.Menu(self, tearoff=0)
        menu.configure(
            background=self._theme.resolved("surface"),
            foreground=self._theme.resolved("text"),
            activebackground=self._theme.resolved("accent_soft"),
            activeforeground=self._theme.resolved("text"),
            borderwidth=0,
            relief="flat",
        )
        for label, handler in actions:
            if label == "-":
                menu.add_separator()
                continue
            menu.add_command(label=label, command=self._make_action(handler))
        self._menu = menu

        def _popup(event: Any) -> None:
            row_id = self.tree.identify_row(event.y)
            if row_id:
                self.tree.selection_set(row_id)
                try:
                    menu.tk_popup(event.x_root, event.y_root)
                finally:
                    menu.grab_release()

        self.tree.bind("<Button-3>", _popup)
        self.tree.bind("<Button-2>", _popup)

    def _make_action(self, handler: Callable[[str], None]) -> Callable[[], None]:
        """Оборачивает обработчик пункта меню в вызов без аргументов.

        Именованная фабрика вместо ``lambda action=handler: ...`` — это не
        только обходит трудности вывода типов у лямбды с аргументом по
        умолчанию, но и устраняет типичную ловушку позднего связывания
        замыкания в цикле.

        Args:
            handler: Обработчик, принимающий идентификатор выбранной строки.

        Returns:
            Обработчик без аргументов, пригодный для ``command=``.
        """
        return lambda: self._invoke(handler)

    def _invoke(self, action: Callable[[str], None]) -> None:
        """Выполняет действие контекстного меню для выбранной строки."""
        row_id = self.selected_id
        if not row_id:
            return
        try:
            action(row_id)
        except Exception:
            _LOGGER.exception("Ошибка действия контекстного меню")

    # -------------------------------------------------------------- оформление
    def _apply_tag_colors(self) -> None:
        """Задаёт цвета фона строк по тегам статусов."""
        for tag, role in self.STATUS_TAGS.items():
            try:
                self.tree.tag_configure(
                    tag,
                    background=self._theme.resolved(role),
                    foreground=self._theme.resolved("text"),
                )
            except Exception:
                continue

    def refresh_theme(self) -> None:
        """Обновляет стиль таблицы после смены темы."""
        self._theme.style_treeview(self)
        self._apply_tag_colors()
        try:
            self.configure(
                fg_color=self._theme.color("surface"), border_color=self._theme.color("border")
            )
            if self._menu is not None:
                self._menu.configure(
                    background=self._theme.resolved("surface"),
                    foreground=self._theme.resolved("text"),
                    activebackground=self._theme.resolved("accent_soft"),
                    activeforeground=self._theme.resolved("text"),
                )
        except Exception:
            pass


def _format(value: Any) -> str:
    """Приводит значение ячейки к отображаемой строке."""
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


class EmptyState(ctk.CTkFrame):
    """Заглушка для пустых списков с подсказкой о следующем действии."""

    def __init__(
        self,
        master: Any,
        theme: Theme,
        *,
        icon: str = "info",
        title: str = "Пока пусто",
        message: str = "",
        action_text: str = "",
        on_action: Callable[[], None] | None = None,
        **kwargs: Any,
    ) -> None:
        """Создаёт заглушку.

        Args:
            master: Родительский виджет.
            theme: Активная тема оформления.
            icon: Имя иконки.
            title: Заголовок.
            message: Пояснение.
            action_text: Надпись кнопки действия.
            on_action: Обработчик кнопки.
            **kwargs: Дополнительные параметры ``CTkFrame``.
        """
        super().__init__(master, fg_color="transparent", **kwargs)
        from app.gui.icons import icons as icon_factory

        ctk.CTkLabel(self, text="", image=icon_factory.colored(icon, theme, "text_muted", 44)).pack(
            pady=(Spacing.XXL, Spacing.MD)
        )
        ctk.CTkLabel(
            self,
            text=title,
            font=theme.font(FontRole.SUBHEADING),
            text_color=theme.color("text"),
        ).pack()
        if message:
            ctk.CTkLabel(
                self,
                text=message,
                font=theme.font(FontRole.SMALL),
                text_color=theme.color("text_muted"),
                wraplength=420,
                justify="center",
            ).pack(pady=(Spacing.XS, 0))
        if action_text and on_action is not None:
            from app.gui.widgets.controls import secondary_button

            secondary_button(self, theme, text=action_text, command=on_action).pack(
                pady=(Spacing.LG, 0)
            )
