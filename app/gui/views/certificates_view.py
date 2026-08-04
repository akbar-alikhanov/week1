"""Раздел справочника сертификатов с поиском и просмотром PDF."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import customtkinter as ctk

from app.core.dates import format_date
from app.gui.theme import FontRole, Spacing
from app.gui.views.base_view import BaseView
from app.gui.widgets.base import format_bytes
from app.gui.widgets.card import SectionCard
from app.gui.widgets.controls import SegmentedFilter, secondary_button
from app.gui.widgets.data_table import Column, DataTable
from app.gui.widgets.pdf_viewer import PdfViewer
from app.gui.widgets.search_entry import SearchEntry
from app.models.certificate import Certificate

_LOGGER = logging.getLogger(__name__)

#: Максимум записей, отображаемых одновременно.
_PAGE_SIZE = 500


class CertificatesView(BaseView):
    """Просмотр и поиск по справочнику сертификатов."""

    title = "Сертификаты"
    subtitle = "Поиск по справочнику, просмотр документов и сведений об извлечённых полях"

    def __init__(self, master: Any, app: Any, **kwargs: Any) -> None:
        """Создаёт раздел.

        Args:
            master: Родительский виджет.
            app: Главное окно приложения.
            **kwargs: Дополнительные параметры ``CTkFrame``.
        """
        super().__init__(master, app, **kwargs)
        self._certificates: list[Certificate] = []
        self._filter = "all"
        self._query = ""

    # ---------------------------------------------------------------- разметка
    def build(self) -> None:
        """Создаёт содержимое раздела."""
        secondary_button(
            self.actions,
            self.theme,
            text="Переиндексировать",
            icon="refresh",
            command=lambda: self.app.navigate("dashboard", action="reindex"),
        ).pack(side="right")

        toolbar = ctk.CTkFrame(self.content, fg_color="transparent", width=0, height=0)
        toolbar.pack(fill="x", pady=(0, Spacing.MD))

        self.search = SearchEntry(
            toolbar,
            self.theme,
            placeholder="Наименование, номер сертификата, бренд или файл…",
            on_search=self._on_search,
            width=440,
        )
        self.search.pack(side="left")

        SegmentedFilter(
            toolbar,
            self.theme,
            options=[
                ("all", "Все"),
                ("valid", "Действующие"),
                ("expiring", "Истекают"),
                ("expired", "Просроченные"),
                ("incomplete", "Без данных"),
            ],
            on_change=self._on_filter,
        ).pack(side="left", padx=(Spacing.MD, 0))

        self._count_label = ctk.CTkLabel(
            toolbar,
            text="",
            font=self.theme.font(FontRole.SMALL),
            text_color=self.theme.color("text_muted"),
        )
        self._count_label.pack(side="right")

        split = ctk.CTkFrame(self.content, fg_color="transparent", width=0, height=0)
        split.pack(fill="both", expand=True)
        split.grid_columnconfigure(0, weight=3, uniform="split")
        split.grid_columnconfigure(1, weight=2, uniform="split")
        split.grid_rowconfigure(0, weight=1)

        self._table = DataTable(
            split,
            self.theme,
            columns=(
                Column("product", "Наименование", width=280, stretch=True),
                Column("volume", "Объём", width=90, anchor="center"),
                Column("number", "Номер", width=160),
                Column("expiry", "Действует до", width=110, anchor="center"),
                Column("brand", "Бренд", width=120),
                Column("file", "Файл", width=140),
            ),
            on_select=self._on_select,
            on_activate=self._open_external,
            context_actions=(
                ("Открыть PDF во внешней программе", self._open_external),
                ("Показать папку с файлом", self._reveal),
                ("-", lambda _: None),
                ("Скопировать номер сертификата", self._copy_number),
            ),
            height=18,
        )
        self._table.grid(row=0, column=0, sticky="nsew", padx=(0, Spacing.MD))

        side = ctk.CTkFrame(split, fg_color="transparent", width=0, height=0)
        side.grid(row=0, column=1, sticky="nsew")
        side.grid_rowconfigure(1, weight=1)
        side.grid_columnconfigure(0, weight=1)

        self._details_card = SectionCard(
            side,
            self.theme,
            title="Сведения",
            subtitle="Выберите сертификат в списке",
            icon="info",
            animator=self.app.animator,
        )
        self._details_card.grid(row=0, column=0, sticky="new", pady=(0, Spacing.MD))

        self._details_body = ctk.CTkFrame(
            self._details_card.content, fg_color="transparent", width=0, height=0
        )
        self._details_body.pack(fill="both", expand=True)

        self._viewer = PdfViewer(
            side,
            self.theme,
            render=self._render_pdf_page,
            page_count=self.app.container.pdf_parser.page_count,
            submit=self.app.submit_background,
            on_open_external=self.app.open_path,
        )
        self._viewer.grid(row=1, column=0, sticky="nsew")

        self.refresh()

    # ------------------------------------------------------------- поведение
    def on_show(self) -> None:
        """Обновляет список при открытии раздела."""
        if not self._certificates:
            self.refresh()

    def focus_search(self) -> None:
        """Передаёт фокус строке поиска."""
        self.ensure_built()
        self.search.focus_input()

    def refresh(self) -> None:
        """Перечитывает справочник с учётом поиска и фильтра."""
        repository = self.app.container.certificate_repository
        try:
            if self._query:
                found = repository.search(self._query, limit=_PAGE_SIZE, include_inactive=True)
            else:
                found = repository.search("", limit=_PAGE_SIZE, include_inactive=False)
        except Exception:
            _LOGGER.exception("Не удалось загрузить справочник сертификатов")
            return

        self._certificates = [item for item in found if self._matches_filter(item)]
        self._render()

    def _matches_filter(self, certificate: Certificate) -> bool:
        """Проверяет соответствие сертификата активному фильтру."""
        if self._filter == "all":
            return True
        if self._filter == "valid":
            return not certificate.is_expired and certificate.expiry_date is not None
        if self._filter == "expired":
            return certificate.is_expired
        if self._filter == "expiring":
            days = certificate.days_until_expiry
            return days is not None and 0 <= days <= 90
        if self._filter == "incomplete":
            return certificate.expiry_date is None or certificate.volume_value is None
        return True

    def _render(self) -> None:
        """Отображает найденные сертификаты в таблице."""
        rows: list[tuple[str, dict[str, Any], str]] = []
        for index, certificate in enumerate(self._certificates):
            tag = ""
            if certificate.is_expired:
                tag = "expired"
            elif (certificate.days_until_expiry or 999) <= 90:
                tag = "warning"
            elif not certificate.is_active:
                tag = "muted"

            rows.append(
                (
                    str(index),
                    {
                        "product": certificate.product_name,
                        "volume": str(certificate.volume) if certificate.volume else "—",
                        "number": certificate.display_number,
                        "expiry": format_date(certificate.expiry_date),
                        "brand": certificate.brand or "—",
                        "file": certificate.pdf_name,
                    },
                    tag,
                )
            )

        self._table.set_rows(rows)
        total = self.app.container.certificate_repository.count("is_active = 1")
        self._count_label.configure(text=f"показано {len(rows)} из {total}")

    def _on_search(self, query: str) -> None:
        """Обрабатывает изменение поискового запроса."""
        self._query = query
        self.refresh()

    def _on_filter(self, value: str) -> None:
        """Обрабатывает смену фильтра."""
        self._filter = value
        self.refresh()

    def _on_select(self, row_id: str) -> None:
        """Показывает сведения и документ выбранного сертификата."""
        certificate = self._certificate_at(row_id)
        if certificate is None:
            return
        self._show_details(certificate)
        self._viewer.open(certificate.path if certificate.path.exists() else None)

    def _show_details(self, certificate: Certificate) -> None:
        """Заполняет карточку сведений."""
        for child in self._details_body.winfo_children():
            child.destroy()

        self._details_card.set_subtitle(certificate.pdf_name)

        size = ""
        try:
            if certificate.path.exists():
                size = format_bytes(certificate.path.stat().st_size)
        except OSError:
            size = ""

        fields: list[tuple[str, str]] = [
            ("Товар", certificate.product_name),
            ("Номер", certificate.display_number),
            ("Объём", str(certificate.volume) if certificate.volume else "не определён"),
            ("Выдан", format_date(certificate.certificate_date)),
            ("Действует до", format_date(certificate.expiry_date)),
            ("Бренд", certificate.brand or "—"),
            ("Изготовитель", certificate.manufacturer or "—"),
            ("Страна", certificate.country or "—"),
            ("Орган", certificate.issued_by or "—"),
            ("Полнота разбора", f"{certificate.extraction_confidence * 100:.0f} %"),
            ("Проиндексирован", certificate.indexed_at.strftime("%d.%m.%Y %H:%M")),
            ("Файл", f"{certificate.pdf_path}{f' · {size}' if size else ''}"),
        ]

        if certificate.is_expired:
            fields.insert(0, ("ВНИМАНИЕ", "Срок действия сертификата истёк"))

        for label, value in fields:
            row = ctk.CTkFrame(self._details_body, fg_color="transparent", width=0, height=0)
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(
                row,
                text=label,
                font=self.theme.font(FontRole.CAPTION),
                text_color=self.theme.color("danger" if label == "ВНИМАНИЕ" else "text_muted"),
                width=130,
                anchor="w",
            ).pack(side="left")
            ctk.CTkLabel(
                row,
                text=value,
                font=self.theme.font(FontRole.CAPTION),
                text_color=self.theme.color("danger" if label == "ВНИМАНИЕ" else "text"),
                anchor="w",
                justify="left",
                wraplength=260,
            ).pack(side="left", fill="x", expand=True)

    # -------------------------------------------------------------- действия
    def _certificate_at(self, row_id: str) -> Certificate | None:
        """Возвращает сертификат по идентификатору строки."""
        try:
            return self._certificates[int(row_id)]
        except (ValueError, IndexError):
            return None

    def _open_external(self, row_id: str) -> None:
        """Открывает PDF во внешней программе."""
        certificate = self._certificate_at(row_id)
        if certificate is not None:
            self.app.open_path(certificate.path)

    def _reveal(self, row_id: str) -> None:
        """Открывает папку, содержащую файл сертификата."""
        certificate = self._certificate_at(row_id)
        if certificate is not None:
            self.app.open_path(certificate.path.parent)

    def _copy_number(self, row_id: str) -> None:
        """Копирует номер сертификата в буфер обмена."""
        certificate = self._certificate_at(row_id)
        if certificate is None:
            return
        try:
            self.app.clipboard_clear()
            self.app.clipboard_append(certificate.display_number)
            self.app.toasts.info("Номер сертификата скопирован")
        except Exception:
            pass

    def _render_pdf_page(self, path: Path, page: int, zoom: float) -> tuple[bytes, int, int]:
        """Адаптирует сигнатуру ``PdfParser.render_page`` под контракт просмотрщика.

        ``PdfViewer`` вызывает рендерер тремя позиционными аргументами, а
        ``PdfParser.render_page`` объявляет ``zoom`` как keyword-only —
        вызов напрямую без адаптера падал бы ``TypeError`` на каждой странице.

        Args:
            path: Путь к PDF-файлу.
            page: Индекс страницы (с нуля).
            zoom: Коэффициент масштабирования.

        Returns:
            Кортеж ``(данные PNG, ширина, высота)``.
        """
        return self.app.container.pdf_parser.render_page(path, page, zoom=zoom)

    def open_certificate(self, path: Path) -> None:
        """Открывает документ во встроенном просмотрщике.

        Args:
            path: Путь к PDF-файлу.
        """
        self.ensure_built()
        self._viewer.open(path)

    def refresh_theme(self) -> None:
        """Обновляет цвета после смены темы."""
        super().refresh_theme()
        try:
            self._table.refresh_theme()
        except Exception:
            pass
