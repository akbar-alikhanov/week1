"""Раздел истории обработки заказов."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import customtkinter as ctk

from app.core.constants import STATUS_LABELS
from app.gui.theme import FontRole, Spacing
from app.gui.views.base_view import BaseView
from app.gui.widgets.base import format_duration
from app.gui.widgets.card import SectionCard
from app.gui.widgets.controls import ghost_button, secondary_button
from app.gui.widgets.data_table import Column, DataTable, EmptyState
from app.gui.widgets.dialogs import ask_confirmation
from app.models.history import ProcessingRun

_LOGGER = logging.getLogger(__name__)


class HistoryView(BaseView):
    """История обработок с детализацией по позициям."""

    title = "История"
    subtitle = "Все обработанные заказы, их результаты и созданные файлы"

    def __init__(self, master: Any, app: Any, **kwargs: Any) -> None:
        """Создаёт раздел.

        Args:
            master: Родительский виджет.
            app: Главное окно приложения.
            **kwargs: Дополнительные параметры ``CTkFrame``.
        """
        super().__init__(master, app, **kwargs)
        self._runs: list[ProcessingRun] = []
        self._selected: ProcessingRun | None = None

    def build(self) -> None:
        """Создаёт содержимое раздела."""
        secondary_button(
            self.actions, self.theme, text="Обновить", icon="refresh", command=self.refresh
        ).pack(side="right")

        split = ctk.CTkFrame(self.content, fg_color="transparent", width=0, height=0)
        split.pack(fill="both", expand=True)
        split.grid_columnconfigure(0, weight=1, uniform="hist")
        split.grid_columnconfigure(1, weight=1, uniform="hist")
        split.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(split, fg_color="transparent", width=0, height=0)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, Spacing.MD))

        self._runs_table = DataTable(
            left,
            self.theme,
            columns=(
                Column("date", "Дата", width=130),
                Column("order", "Заказ", width=220, stretch=True),
                Column("rows", "Позиций", width=80, anchor="center", numeric=True),
                Column("rate", "Успешность", width=100, anchor="center", numeric=True),
                Column("duration", "Время", width=90, anchor="center"),
            ),
            on_select=self._on_select_run,
            on_activate=self._open_output,
            context_actions=(
                ("Открыть файл результата", self._open_output),
                ("Открыть папку сертификатов", self._open_certificates),
                ("Открыть отчёт", self._open_report),
                ("-", lambda _: None),
                ("Удалить запись", self._delete_run),
            ),
            height=16,
        )
        self._runs_table.pack(fill="both", expand=True)

        right = ctk.CTkFrame(split, fg_color="transparent", width=0, height=0)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self._summary_card = SectionCard(
            right,
            self.theme,
            title="Детали обработки",
            subtitle="Выберите запись в списке",
            icon="chart",
            animator=self.app.animator,
        )
        self._summary_card.grid(row=0, column=0, sticky="new", pady=(0, Spacing.MD))
        self._summary_body = ctk.CTkFrame(
            self._summary_card.content, fg_color="transparent", width=0, height=0
        )
        self._summary_body.pack(fill="x")

        self._items_table = DataTable(
            right,
            self.theme,
            columns=(
                Column("row", "Строка", width=70, anchor="center", numeric=True),
                Column("product", "Товар", width=220, stretch=True),
                Column("status", "Статус", width=130),
                Column("certificate", "Сертификат", width=150),
                Column("score", "Совпадение", width=100, anchor="center", numeric=True),
            ),
            height=12,
        )
        self._items_table.grid(row=1, column=0, sticky="nsew")

        self._empty = EmptyState(
            self.content,
            self.theme,
            icon="history",
            title="История пуста",
            message=(
                "Обработайте первый заказ — и здесь появится запись "
                "с результатами и ссылками на файлы."
            ),
        )

        self.refresh()

    # ------------------------------------------------------------- поведение
    def on_show(self) -> None:
        """Обновляет историю при открытии раздела."""
        self.refresh()

    def refresh(self) -> None:
        """Перечитывает список обработок."""
        try:
            self._runs = self.app.container.history_repository.recent(limit=200)
        except Exception:
            _LOGGER.exception("Не удалось загрузить историю")
            return

        rows: list[tuple[str, dict[str, Any], str]] = []
        for index, run in enumerate(self._runs):
            rate = run.success_rate * 100
            tag = "matched" if rate >= 90 else "ambiguous" if rate >= 60 else "not_found"
            if run.status == "failed":
                tag = "not_found"
            rows.append(
                (
                    str(index),
                    {
                        "date": run.started_at.strftime("%d.%m.%Y %H:%M"),
                        "order": run.order_name,
                        "rows": run.total_rows,
                        "rate": f"{rate:.0f} %",
                        "duration": format_duration(run.duration_seconds),
                    },
                    tag,
                )
            )

        self._runs_table.set_rows(rows)

        if rows:
            self._empty.pack_forget()
            self._runs_table.select_first()
        else:
            self._empty.pack(fill="both", expand=True)

    def _on_select_run(self, row_id: str) -> None:
        """Показывает детали выбранной обработки."""
        run = self._run_at(row_id)
        if run is None:
            return
        self._selected = run
        self._summary_card.set_subtitle(f"{run.order_name} · {run.started_at:%d.%m.%Y %H:%M}")

        for child in self._summary_body.winfo_children():
            child.destroy()

        metrics = [
            ("Всего позиций", str(run.total_rows), "text"),
            ("Найдено автоматически", str(run.matched), "success"),
            ("Выбрано вручную", str(run.manual), "info"),
            ("Требует проверки", str(run.ambiguous), "warning"),
            ("Не найдено", str(run.not_found), "danger"),
            ("Скопировано файлов", str(run.copied_files), "text"),
            ("Длительность", format_duration(run.duration_seconds), "text"),
        ]
        grid = ctk.CTkFrame(self._summary_body, fg_color="transparent", width=0, height=0)
        grid.pack(fill="x")
        for label, value, role in metrics:
            row = ctk.CTkFrame(grid, fg_color="transparent", width=0, height=0)
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(
                row,
                text=label,
                font=self.theme.font(FontRole.CAPTION),
                text_color=self.theme.color("text_muted"),
                width=180,
                anchor="w",
            ).pack(side="left")
            ctk.CTkLabel(
                row,
                text=value,
                font=self.theme.font(FontRole.BODY_STRONG),
                text_color=self.theme.color(role),
                anchor="w",
            ).pack(side="left")

        buttons = ctk.CTkFrame(self._summary_body, fg_color="transparent", width=0, height=0)
        buttons.pack(fill="x", pady=(Spacing.MD, 0))
        if run.output_file and Path(run.output_file).exists():
            ghost_button(
                buttons,
                self.theme,
                text="Excel",
                icon="excel",
                command=lambda: self.app.open_path(Path(run.output_file)),
                height=30,
            ).pack(side="left")
        if run.certificates_dir and Path(run.certificates_dir).exists():
            ghost_button(
                buttons,
                self.theme,
                text="Сертификаты",
                icon="folder",
                command=lambda: self.app.open_path(Path(run.certificates_dir)),
                height=30,
            ).pack(side="left", padx=(Spacing.SM, 0))
        if run.report_file and Path(run.report_file).exists():
            ghost_button(
                buttons,
                self.theme,
                text="Отчёт",
                icon="chart",
                command=lambda: self.app.open_path(Path(run.report_file)),
                height=30,
            ).pack(side="left", padx=(Spacing.SM, 0))

        self._load_items(run)

    def _load_items(self, run: ProcessingRun) -> None:
        """Загружает позиции выбранной обработки."""
        try:
            items = self.app.container.history_repository.items_for_run(run.run_id)
        except Exception:
            _LOGGER.exception("Не удалось загрузить позиции обработки")
            return

        rows: list[tuple[str, dict[str, Any], str]] = []
        for item in items:
            tag = {
                "matched": "matched",
                "manual": "matched",
                "ambiguous": "ambiguous",
                "not_found": "not_found",
            }.get(item.status, "")
            rows.append(
                (
                    str(item.id or item.row_number),
                    {
                        "row": item.row_number,
                        "product": item.product_name,
                        "status": STATUS_LABELS.get(item.status, item.status),
                        "certificate": item.certificate_number or "—",
                        "score": f"{int(item.score * 100)} %" if item.score else "—",
                    },
                    tag,
                )
            )
        self._items_table.set_rows(rows)

    # -------------------------------------------------------------- действия
    def _run_at(self, row_id: str) -> ProcessingRun | None:
        """Возвращает обработку по идентификатору строки."""
        try:
            return self._runs[int(row_id)]
        except (ValueError, IndexError):
            return None

    def _open_output(self, row_id: str) -> None:
        """Открывает файл результата."""
        run = self._run_at(row_id)
        if run and run.output_file:
            self.app.open_path(Path(run.output_file))

    def _open_certificates(self, row_id: str) -> None:
        """Открывает папку с сертификатами."""
        run = self._run_at(row_id)
        if run and run.certificates_dir:
            self.app.open_path(Path(run.certificates_dir))

    def _open_report(self, row_id: str) -> None:
        """Открывает отчёт."""
        run = self._run_at(row_id)
        if run and run.report_file:
            self.app.open_path(Path(run.report_file))

    def _delete_run(self, row_id: str) -> None:
        """Удаляет запись истории."""
        run = self._run_at(row_id)
        if run is None:
            return
        if not ask_confirmation(
            self.app,
            self.theme,
            title="Удалить запись",
            message="Удалить запись из истории?",
            detail=(
                f"{run.order_name} · {run.started_at:%d.%m.%Y %H:%M}. "
                "Созданные файлы останутся на диске."
            ),
            confirm_text="Удалить",
            danger=True,
        ):
            return
        self.app.container.history_repository.delete_run(run.run_id)
        self.refresh()
        self.app.toasts.success("Запись удалена")

    def refresh_theme(self) -> None:
        """Обновляет цвета после смены темы."""
        super().refresh_theme()
        for table in (self._runs_table, self._items_table):
            try:
                table.refresh_theme()
            except Exception:
                continue
