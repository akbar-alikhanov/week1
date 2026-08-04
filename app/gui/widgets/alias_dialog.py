"""Диалоги словаря соответствий: добавление/редактирование и журнал изменений."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from app.core.units import extract_primary_volume
from app.gui.theme import FontRole, Radius, Spacing, Theme
from app.gui.widgets.controls import ghost_button, primary_button, secondary_button
from app.gui.widgets.data_table import Column, DataTable
from app.gui.widgets.dialogs import ModalDialog
from app.models.alias import Alias
from app.models.alias_audit import AliasAuditEntry
from app.models.certificate import Certificate

_LOGGER = logging.getLogger(__name__)


class AliasEditDialog(ModalDialog):
    """Окно добавления или редактирования записи словаря соответствий.

    Диалог не обращается к сервисам напрямую — он лишь собирает и проверяет
    ввод, а поиск сертификата делегирует переданной функции. Сохранение
    (включая проверку дубликатов) выполняет вызывающая сторона после того,
    как диалог закрылся с результатом: так раздел, показывающий диалог,
    остаётся единственным местом, где принимаются решения о сохранении.
    """

    def __init__(
        self,
        master: Any,
        theme: Theme,
        *,
        search_certificates: Callable[[str], list[Certificate]],
        alias: Alias | None = None,
    ) -> None:
        """Создаёт диалог добавления/редактирования.

        Args:
            master: Родительское окно.
            theme: Активная тема оформления.
            search_certificates: Функция поиска сертификатов по тексту.
            alias: Редактируемая запись; ``None`` — создание новой.
        """
        editing = alias is not None
        super().__init__(
            master,
            theme,
            title="Изменить соответствие" if editing else "Добавить соответствие",
            width=760,
            height=640,
            resizable=True,
        )
        self._search_certificates = search_certificates
        self._alias = alias
        self._selected_certificate: Certificate | None = None
        self._selected_summary: dict[str, str] = {
            "name": alias.target_name if alias else "",
            "pdf": alias.target_pdf_name if alias else "",
        }
        self._certificate_id = alias.certificate_id if alias else None

        self._build_form()
        self._build_certificate_picker()
        self._build_footer()

        if alias is not None:
            self._render_selected_summary()

    # ------------------------------------------------------------- разметка
    def _build_form(self) -> None:
        """Строит форму системного/русского названия и атрибутов товара."""
        theme = self._theme
        columns = ctk.CTkFrame(self.container, fg_color="transparent", width=0, height=0)
        columns.pack(fill="x")
        columns.grid_columnconfigure(0, weight=1, uniform="cols")
        columns.grid_columnconfigure(1, weight=1, uniform="cols")

        left = ctk.CTkFrame(columns, fg_color="transparent", width=0, height=0)
        left.grid(row=0, column=0, sticky="new", padx=(0, Spacing.MD))

        right = ctk.CTkFrame(columns, fg_color="transparent", width=0, height=0)
        right.grid(row=0, column=1, sticky="new", padx=(Spacing.MD, 0))

        self.source_var = ctk.StringVar(value=self._alias.source_text if self._alias else "")
        _field(left, theme, "Системное название (как в заказе)", self.source_var, focus=True)

        self.target_var = ctk.StringVar(value=self._alias.target_name if self._alias else "")
        _field(right, theme, "Русское название (в сертификате)", self.target_var)

        self.volume_var = ctk.StringVar(
            value=self._alias.volume_label if self._alias else "",
        )
        _field(right, theme, "Объём (например, «100 мл»)", self.volume_var)

        self.brand_var = ctk.StringVar(value=self._alias.brand if self._alias else "")
        _field(right, theme, "Бренд", self.brand_var)

        self.note_var = ctk.StringVar(value=self._alias.note if self._alias else "")
        _field(right, theme, "Комментарий", self.note_var)

    def _build_certificate_picker(self) -> None:
        """Строит область поиска и выбора связанного сертификата."""
        theme = self._theme
        ctk.CTkLabel(
            self.container,
            text="СЕРТИФИКАТ",
            font=theme.font(FontRole.CAPTION),
            text_color=theme.color("text_muted"),
            anchor="w",
        ).pack(fill="x", anchor="w", pady=(Spacing.LG, Spacing.XS))

        self._summary_label = ctk.CTkLabel(
            self.container,
            text="Сертификат не выбран",
            font=theme.font(FontRole.BODY_STRONG),
            text_color=theme.color("text_muted"),
            anchor="w",
        )
        self._summary_label.pack(fill="x", anchor="w")

        search_row = ctk.CTkFrame(self.container, fg_color="transparent", width=0, height=0)
        search_row.pack(fill="x", pady=(Spacing.SM, 0))

        self._search_var = ctk.StringVar(value=self.target_var.get())
        entry = ctk.CTkEntry(
            search_row,
            textvariable=self._search_var,
            height=34,
            font=theme.font(FontRole.BODY),
            fg_color=theme.color("surface_alt"),
            border_color=theme.color("border"),
            placeholder_text="Наименование товара или номер сертификата…",
        )
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda _: self._run_search())

        secondary_button(
            search_row, theme, text="Найти", icon="search", command=self._run_search, height=34
        ).pack(side="left", padx=(Spacing.SM, 0))

        self._results = ctk.CTkScrollableFrame(
            self.container, fg_color=theme.color("surface_alt"), corner_radius=Radius.MD, height=190
        )
        self._results.pack(fill="both", expand=True, pady=(Spacing.SM, 0))
        self._render_empty_results("Введите запрос и нажмите «Найти»")

    def _build_footer(self) -> None:
        """Строит кнопки сохранения и отмены."""
        theme = self._theme
        self._error_label = ctk.CTkLabel(
            self.container,
            text="",
            font=theme.font(FontRole.CAPTION),
            text_color=theme.color("danger"),
            anchor="w",
        )
        self._error_label.pack(fill="x", anchor="w", pady=(Spacing.SM, 0))

        buttons = ctk.CTkFrame(self.container, fg_color="transparent", width=0, height=0)
        buttons.pack(fill="x", side="bottom", pady=(Spacing.MD, 0))

        primary_button(buttons, theme, text="Сохранить", command=self._submit).pack(side="right")
        secondary_button(buttons, theme, text="Отмена", command=self.close).pack(
            side="right", padx=(0, Spacing.SM)
        )

    # ------------------------------------------------------------- поиск
    def _run_search(self) -> None:
        """Ищет сертификаты по введённому запросу."""
        query = self._search_var.get().strip()
        if not query:
            return
        try:
            results = self._search_certificates(query)
        except Exception:
            _LOGGER.exception("Ошибка поиска сертификата для словаря")
            results = []
        self._render_results(results)

    def _render_empty_results(self, message: str) -> None:
        """Показывает пояснение вместо списка результатов."""
        for child in self._results.winfo_children():
            child.destroy()
        ctk.CTkLabel(
            self._results,
            text=message,
            font=self._theme.font(FontRole.SMALL),
            text_color=self._theme.color("text_muted"),
        ).pack(pady=Spacing.LG)

    def _render_results(self, results: list[Certificate]) -> None:
        """Отображает найденные сертификаты списком с кнопкой выбора."""
        for child in self._results.winfo_children():
            child.destroy()

        if not results:
            self._render_empty_results("Ничего не найдено")
            return

        theme = self._theme
        for certificate in results:
            row = ctk.CTkFrame(
                self._results, fg_color=theme.color("surface"), corner_radius=Radius.SM
            )
            row.pack(fill="x", padx=Spacing.XS, pady=Spacing.XS)

            texts = ctk.CTkFrame(row, fg_color="transparent", width=0, height=0)
            texts.pack(side="left", fill="both", expand=True, padx=Spacing.SM, pady=Spacing.XS)

            ctk.CTkLabel(
                texts,
                text=certificate.product_name,
                font=theme.font(FontRole.SMALL),
                text_color=theme.color("text"),
                anchor="w",
                justify="left",
                wraplength=420,
            ).pack(fill="x", anchor="w")

            details = " · ".join(
                part
                for part in (
                    str(certificate.volume) if certificate.volume else "",
                    certificate.brand,
                    certificate.pdf_name,
                )
                if part
            )
            ctk.CTkLabel(
                texts,
                text=details,
                font=theme.font(FontRole.CAPTION),
                text_color=theme.color("text_muted"),
                anchor="w",
            ).pack(fill="x", anchor="w")

            ghost_button(
                row,
                theme,
                text="Выбрать",
                command=self._make_select(certificate),
            ).pack(side="right", padx=Spacing.SM)

    def _make_select(self, certificate: Certificate) -> Callable[[], None]:
        """Создаёт обработчик выбора для конкретного сертификата в списке.

        Именованная фабрика вместо ``lambda item=certificate: ...`` — так же,
        как и в остальном интерфейсе, это устраняет и трудности вывода типов
        у лямбды с аргументом по умолчанию, и ловушку позднего связывания
        замыкания в цикле.

        Args:
            certificate: Сертификат, который нужно привязать к обработчику.

        Returns:
            Обработчик без аргументов, пригодный для ``command=``.
        """
        return lambda: self._select_certificate(certificate)

    def _select_certificate(self, certificate: Certificate) -> None:
        """Привязывает диалог к выбранному сертификату, подставляя его поля."""
        self._selected_certificate = certificate
        self._certificate_id = certificate.id
        if not self.target_var.get().strip():
            self.target_var.set(certificate.product_name)
        if not self.brand_var.get().strip() and certificate.brand:
            self.brand_var.set(certificate.brand)
        if not self.volume_var.get().strip() and certificate.volume:
            self.volume_var.set(certificate.volume.format())
        self._selected_summary = {"name": certificate.product_name, "pdf": certificate.pdf_name}
        self._render_selected_summary()

    def _render_selected_summary(self) -> None:
        """Обновляет строку с описанием выбранного сертификата."""
        name = self._selected_summary.get("name")
        pdf = self._selected_summary.get("pdf")
        if not name:
            self._summary_label.configure(
                text="Сертификат не выбран", text_color=self._theme.color("text_muted")
            )
            return
        text = f"{name}" + (f" · {pdf}" if pdf else "")
        self._summary_label.configure(text=text, text_color=self._theme.color("text"))

    # -------------------------------------------------------------- отправка
    def _submit(self) -> None:
        """Проверяет форму и закрывает диалог с собранными данными."""
        source_text = self.source_var.get().strip()
        target_name = self.target_var.get().strip()

        if not source_text:
            self._show_error("Укажите системное название")
            return
        if self._certificate_id is None:
            self._show_error("Выберите сертификат из списка справа")
            return

        volume = extract_primary_volume(self.volume_var.get())

        self.close(
            {
                "source_text": source_text,
                "target_name": target_name,
                "certificate_id": self._certificate_id,
                "certificate": self._selected_certificate,
                "brand": self.brand_var.get().strip(),
                "volume_value": volume.base_value if volume else None,
                "volume_unit": volume.base_unit if volume else "",
                "note": self.note_var.get().strip(),
            }
        )

    def _show_error(self, message: str) -> None:
        """Показывает сообщение об ошибке проверки формы."""
        try:
            self._error_label.configure(text=message)
        except Exception:
            pass


class AliasAuditDialog(ModalDialog):
    """Окно журнала изменений словаря соответствий (только для чтения)."""

    def __init__(
        self,
        master: Any,
        theme: Theme,
        *,
        entries: list[AliasAuditEntry],
        title: str = "Журнал изменений",
    ) -> None:
        """Создаёт окно журнала.

        Args:
            master: Родительское окно.
            theme: Активная тема оформления.
            entries: Записи журнала, которые нужно показать.
            title: Заголовок окна.
        """
        super().__init__(master, theme, title=title, width=760, height=560, resizable=True)

        table = DataTable(
            self.container,
            theme,
            columns=(
                Column("action", "Действие", width=150),
                Column("source", "Наименование", width=280, stretch=True),
                Column("actor", "Кто", width=120),
                Column("at", "Когда", width=150),
            ),
            height=18,
        )
        table.pack(fill="both", expand=True)

        rows = [
            (
                str(index),
                {
                    "action": entry.action.label,
                    "source": entry.source_text or "—",
                    "actor": entry.actor or "—",
                    "at": entry.at.strftime("%d.%m.%Y %H:%M"),
                },
                "" if not entry.undone else "muted",
            )
            for index, entry in enumerate(entries)
        ]
        table.set_rows(rows)

        if not entries:
            ctk.CTkLabel(
                self.container,
                text="Журнал пока пуст",
                font=theme.font(FontRole.BODY),
                text_color=theme.color("text_muted"),
            ).pack(pady=Spacing.XXL)

        primary_button(self.container, theme, text="Закрыть", command=self.close).pack(
            side="bottom", anchor="e", pady=(Spacing.LG, 0)
        )


def _field(
    master: Any, theme: Theme, label: str, variable: ctk.StringVar, *, focus: bool = False
) -> ctk.CTkEntry:
    """Создаёт подписанное поле ввода и возвращает сам виджет ввода.

    Args:
        master: Родительский виджет.
        theme: Активная тема оформления.
        label: Подпись поля.
        variable: Связанная переменная.
        focus: Передать ли полю фокус сразу после отрисовки.

    Returns:
        Созданный ``CTkEntry``.
    """
    ctk.CTkLabel(
        master,
        text=label,
        font=theme.font(FontRole.CAPTION),
        text_color=theme.color("text_muted"),
        anchor="w",
    ).pack(fill="x", anchor="w", pady=(Spacing.SM, 2))
    entry = ctk.CTkEntry(
        master,
        textvariable=variable,
        height=34,
        font=theme.font(FontRole.BODY),
        fg_color=theme.color("surface_alt"),
        border_color=theme.color("border"),
    )
    entry.pack(fill="x")
    if focus:
        entry.after(120, entry.focus_set)
    return entry


__all__ = ["AliasAuditDialog", "AliasEditDialog"]
