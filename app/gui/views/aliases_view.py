"""Раздел управления псевдонимами — «памятью» приложения."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import customtkinter as ctk

from app.gui.theme import FontRole, Spacing
from app.gui.views.base_view import BaseView
from app.gui.widgets.controls import ghost_button, secondary_button
from app.gui.widgets.data_table import Column, DataTable, EmptyState
from app.gui.widgets.dialogs import ask_confirmation
from app.gui.widgets.search_entry import SearchEntry
from app.models.alias import Alias

_LOGGER = logging.getLogger(__name__)


class AliasesView(BaseView):
    """Просмотр, поиск, импорт и экспорт запомненных соответствий."""

    title = "Соответствия"
    subtitle = "Программа запоминает каждое ваше решение и применяет его раньше любых алгоритмов"

    def __init__(self, master: Any, app: Any, **kwargs: Any) -> None:
        """Создаёт раздел.

        Args:
            master: Родительский виджет.
            app: Главное окно приложения.
            **kwargs: Дополнительные параметры ``CTkFrame``.
        """
        super().__init__(master, app, **kwargs)
        self._aliases: list[Alias] = []
        self._query = ""

    def build(self) -> None:
        """Создаёт содержимое раздела."""
        secondary_button(
            self.actions, self.theme, text="Импорт", icon="upload", command=self.import_aliases
        ).pack(side="right", padx=(Spacing.SM, 0))
        secondary_button(
            self.actions, self.theme, text="Экспорт", icon="download", command=self.export_aliases
        ).pack(side="right")

        toolbar = ctk.CTkFrame(self.content, fg_color="transparent", width=0, height=0)
        toolbar.pack(fill="x", pady=(0, Spacing.MD))

        self.search = SearchEntry(
            toolbar,
            self.theme,
            placeholder="Наименование из заказа или товар в сертификате…",
            on_search=self._on_search,
            width=440,
        )
        self.search.pack(side="left")

        ghost_button(
            toolbar,
            self.theme,
            text="Восстановить связи",
            icon="refresh",
            command=self.repair_links,
        ).pack(side="left", padx=(Spacing.MD, 0))

        self._count_label = ctk.CTkLabel(
            toolbar,
            text="",
            font=self.theme.font(FontRole.SMALL),
            text_color=self.theme.color("text_muted"),
        )
        self._count_label.pack(side="right")

        self._table = DataTable(
            self.content,
            self.theme,
            columns=(
                Column("source", "Наименование из заказа", width=300, stretch=True),
                Column("target", "Товар в сертификате", width=300, stretch=True),
                Column("file", "Файл", width=150),
                Column("hits", "Применений", width=110, anchor="center", numeric=True),
                Column("updated", "Изменён", width=140),
            ),
            on_activate=self._preview,
            context_actions=(
                ("Открыть сертификат", self._preview),
                ("Удалить соответствие", self._delete),
            ),
            height=20,
        )
        self._table.pack(fill="both", expand=True)

        self._empty = EmptyState(
            self.content,
            self.theme,
            icon="alias",
            title="Соответствий пока нет",
            message=(
                "Соответствия появляются автоматически, когда вы выбираете сертификат "
                "в окне проверки. Их также можно импортировать с другого рабочего места."
            ),
            action_text="Импортировать из файла",
            on_action=self.import_aliases,
        )

        self.refresh()

    # ------------------------------------------------------------- поведение
    def on_show(self) -> None:
        """Обновляет список при открытии раздела."""
        self.refresh()

    def focus_search(self) -> None:
        """Передаёт фокус строке поиска."""
        self.ensure_built()
        self.search.focus_input()

    def refresh(self) -> None:
        """Перечитывает список соответствий."""
        try:
            self._aliases = self.app.container.alias_service.list_aliases(search=self._query)
        except Exception:
            _LOGGER.exception("Не удалось загрузить псевдонимы")
            return

        rows: list[tuple[str, dict[str, Any], str]] = []
        for index, alias in enumerate(self._aliases):
            rows.append(
                (
                    str(index),
                    {
                        "source": alias.source_text,
                        "target": alias.target_name or "—",
                        "file": alias.target_pdf_name or "—",
                        "hits": alias.hit_count,
                        "updated": alias.updated_at.strftime("%d.%m.%Y %H:%M"),
                    },
                    "matched" if alias.hit_count else "",
                )
            )

        self._table.set_rows(rows)
        self._count_label.configure(text=f"всего: {len(self._aliases)}")

        if rows:
            self._empty.pack_forget()
            self._table.pack(fill="both", expand=True)
        else:
            self._table.pack_forget()
            self._empty.pack(fill="both", expand=True)

    def _on_search(self, query: str) -> None:
        """Обрабатывает изменение поискового запроса."""
        self._query = query
        self.refresh()

    # -------------------------------------------------------------- действия
    def _alias_at(self, row_id: str) -> Alias | None:
        """Возвращает псевдоним по идентификатору строки."""
        try:
            return self._aliases[int(row_id)]
        except (ValueError, IndexError):
            return None

    def _preview(self, row_id: str) -> None:
        """Открывает сертификат, на который ссылается псевдоним."""
        alias = self._alias_at(row_id)
        if alias is None:
            return
        certificate = self.app.container.alias_service.resolve_certificate(alias)
        if certificate is None:
            self.app.toasts.warning("Сертификат не найден в справочнике. Выполните переиндексацию.")
            return
        self.app.preview_pdf(certificate.path)

    def _delete(self, row_id: str) -> None:
        """Удаляет соответствие после подтверждения."""
        alias = self._alias_at(row_id)
        if alias is None or alias.id is None:
            return

        if not ask_confirmation(
            self.app,
            self.theme,
            title="Удалить соответствие",
            message="Удалить запомненное соответствие?",
            detail=alias.describe(),
            confirm_text="Удалить",
            danger=True,
        ):
            return

        if self.app.container.alias_service.forget(alias.id):
            self.app.toasts.success("Соответствие удалено")
            self.refresh()

    def repair_links(self) -> None:
        """Восстанавливает связи псевдонимов с сертификатами."""
        repaired = self.app.container.alias_service.repair()
        if repaired:
            self.app.toasts.success(f"Восстановлено связей: {repaired}")
            self.refresh()
        else:
            self.app.toasts.info("Все связи в порядке")

    def export_aliases(self) -> None:
        """Экспортирует соответствия в файл."""
        from tkinter import filedialog

        target = filedialog.asksaveasfilename(
            title="Экспорт соответствий",
            defaultextension=".json",
            initialfile="aliases.json",
            filetypes=[("JSON", "*.json"), ("CSV", "*.csv")],
        )
        if not target:
            return
        try:
            count = self.app.container.alias_service.export(Path(target))
        except Exception as error:
            self.app.show_error("Экспорт не выполнен", str(error))
            return
        self.app.toasts.success(f"Экспортировано соответствий: {count}")

    def import_aliases(self) -> None:
        """Импортирует соответствия из файла."""
        from tkinter import filedialog

        source = filedialog.askopenfilename(
            title="Импорт соответствий",
            filetypes=[("JSON или CSV", "*.json *.csv"), ("Все файлы", "*.*")],
        )
        if not source:
            return
        try:
            imported, skipped = self.app.container.alias_service.import_from(Path(source))
        except Exception as error:
            self.app.show_error("Импорт не выполнен", str(error))
            return

        self.refresh()
        message = f"Импортировано: {imported}"
        if skipped:
            message += f", пропущено: {skipped} (сертификаты не найдены в справочнике)"
        self.app.toasts.success(message)

    def refresh_theme(self) -> None:
        """Обновляет цвета после смены темы."""
        super().refresh_theme()
        try:
            self._table.refresh_theme()
        except Exception:
            pass
