"""Раздел базы сертификатов с поиском и просмотром PDF."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import customtkinter as ctk

from app.core.dates import format_date
from app.gui.theme import FontRole, Spacing
from app.gui.views.base_view import BaseView
from app.gui.widgets.card import SectionCard, StatCard
from app.gui.widgets.controls import Badge, SegmentedFilter, secondary_button
from app.gui.widgets.data_table import Column, DataTable, EmptyState
from app.gui.widgets.pdf_viewer import PdfViewer
from app.gui.widgets.search_entry import SearchEntry
from app.models.certificate_product import CertificateProduct
from app.services.certificate_file_locator import find_pdf

_LOGGER = logging.getLogger(__name__)

#: Максимум записей, отображаемых одновременно.
_PAGE_SIZE = 500


class CertificatesView(BaseView):
    """Просмотр и поиск по базе сертификатов (Excel, проиндексированной в SQLite)."""

    title = "Сертификаты"
    subtitle = "Поиск по базе сертификатов и просмотр PDF-файлов, найденных по номеру"

    def __init__(self, master: Any, app: Any, **kwargs: Any) -> None:
        """Создаёт раздел.

        Args:
            master: Родительский виджет.
            app: Главное окно приложения.
            **kwargs: Дополнительные параметры ``CTkFrame``.
        """
        super().__init__(master, app, **kwargs)
        self._certificates: list[CertificateProduct] = []
        self._filter = "all"
        self._query = ""
        self._stat_cards: dict[str, StatCard] = {}
        self._empty_visible = False

    # ---------------------------------------------------------------- разметка
    def build(self) -> None:
        """Создаёт содержимое раздела."""
        secondary_button(
            self.actions,
            self.theme,
            text="Импортировать заново",
            icon="refresh",
            command=lambda: self.app.navigate("dashboard", action="reimport"),
        ).pack(side="right")

        self._build_stats()

        toolbar = ctk.CTkFrame(self.content, fg_color="transparent", width=0, height=0)
        toolbar.pack(fill="x", pady=(0, Spacing.MD))

        self.search = SearchEntry(
            toolbar,
            self.theme,
            placeholder="Наименование или номер сертификата…",
            on_search=self._on_search,
            width=440,
        )
        self.search.pack(side="left")

        self._filter_control = SegmentedFilter(
            toolbar,
            self.theme,
            options=[
                ("all", "Все"),
                ("valid", "Действующие"),
                ("expiring", "Истекают"),
                ("expired", "Просроченные"),
                ("incomplete", "Без срока"),
            ],
            on_change=self._on_filter,
        )
        self._filter_control.pack(side="left", padx=(Spacing.MD, 0))

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
                Column("product", "Наименование", width=320, stretch=True),
                Column("volume", "Объём", width=90, anchor="center"),
                Column("number", "Номер сертификата", width=180),
                Column("expiry", "Срок годности", width=110, anchor="center"),
                Column("row", "Строка Excel", width=90, anchor="center", numeric=True),
            ),
            on_select=self._on_select,
            context_actions=(
                ("Показать PDF во внешней программе", self._open_external),
                ("-", lambda _: None),
                ("Скопировать номер сертификата", self._copy_number),
            ),
            height=18,
        )
        self._table.grid(row=0, column=0, sticky="nsew", padx=(0, Spacing.MD))

        self._empty_state = EmptyState(
            split,
            self.theme,
            icon="certificate",
            title="База сертификатов пока пуста",
            message="Импортируйте Excel-файл с сертификатами на экране «Подбор».",
            action_text="Перейти к импорту",
            on_action=lambda: self.app.navigate("dashboard", action="reimport"),
        )

        side = ctk.CTkFrame(split, fg_color="transparent", width=0, height=0)
        side.grid(row=0, column=1, sticky="nsew")
        side.grid_rowconfigure(1, weight=1)
        side.grid_columnconfigure(0, weight=1)

        self._details_card = SectionCard(
            side,
            self.theme,
            title="Сведения",
            subtitle="Выберите позицию в списке",
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

    def _build_stats(self) -> None:
        """Создаёт полосу ключевых показателей по базе сертификатов.

        Числа всегда по всей базе (как в :meth:`DashboardView._build_stats`),
        независимо от активного поиска и фильтра — щелчок по карточке лишь
        переключает фильтр таблицы через тот же :class:`SegmentedFilter`.
        """
        ctk.CTkLabel(
            self.content,
            text="Обзор базы".upper(),
            font=self.theme.font(FontRole.CAPTION, mono=True),
            text_color=self.theme.color("text_muted"),
            anchor="w",
        ).pack(fill="x", anchor="w", pady=(0, Spacing.SM))

        row = ctk.CTkFrame(self.content, fg_color="transparent", width=0, height=0)
        row.pack(fill="x", pady=(0, Spacing.LG))
        for index in range(4):
            row.grid_columnconfigure(index, weight=1, uniform="stats")

        definitions = [
            ("all", "Всего в базе", "database", "accent", ""),
            ("valid", "Действующих", "check", "success", "без просроченных"),
            ("expiring", "Истекают ≤90 дн.", "history", "warning", "пора продлевать"),
            ("expired", "Просрочено", "alert", "danger", "требуют замены"),
        ]
        for column, (key, title, icon, role, hint) in enumerate(definitions):
            card = StatCard(
                row,
                self.theme,
                title=title,
                icon=icon,
                accent_role=role,
                hint=hint,
                animator=self.app.animator,
                on_click=self._make_filter_click(key),
            )
            card.grid(
                row=0, column=column, sticky="nsew", padx=(0 if column == 0 else Spacing.MD, 0)
            )
            self._stat_cards[key] = card

    def _make_filter_click(self, value: str) -> Callable[[], None]:
        """Создаёт обработчик щелчка по карточке — выбирает фильтр таблицы.

        Именованная фабрика вместо ``lambda value=value: ...`` внутри цикла —
        тот же приём, что и в ``DashboardView``/``Sidebar``.

        Args:
            value: Значение фильтра, соответствующее карточке.

        Returns:
            Обработчик без аргументов для ``StatCard.on_click``.
        """
        return lambda: self._filter_control.select(value)

    def _update_stats(self) -> None:
        """Обновляет карточки показателей и счётчики фильтра по всей базе."""
        try:
            stats = self.app.container.certificate_repository.statistics()
        except Exception:
            _LOGGER.debug("Не удалось обновить показатели базы сертификатов", exc_info=True)
            return

        total = stats.get("total", 0)
        expired = stats.get("expired", 0)
        expiring = stats.get("expiring_soon", 0)
        without_expiry = stats.get("without_expiry", 0)
        valid = max(0, total - expired - without_expiry)

        self._stat_cards["all"].update_value(str(total))
        self._stat_cards["valid"].update_value(str(valid))
        self._stat_cards["expiring"].update_value(str(expiring))
        self._stat_cards["expired"].update_value(str(expired))

        self._filter_control.set_counts(
            {
                "all": total,
                "valid": valid,
                "expiring": expiring,
                "expired": expired,
                "incomplete": without_expiry,
            }
        )

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
        """Перечитывает базу сертификатов с учётом поиска и фильтра."""
        repository = self.app.container.certificate_repository
        try:
            found = repository.search(self._query, limit=_PAGE_SIZE)
        except Exception:
            _LOGGER.exception("Не удалось загрузить базу сертификатов")
            return

        self._certificates = [item for item in found if self._matches_filter(item)]
        self._render()
        self._update_stats()

    def _matches_filter(self, certificate: CertificateProduct) -> bool:
        """Проверяет соответствие позиции активному фильтру."""
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
            return certificate.expiry_date is None
        return True

    def _render(self) -> None:
        """Отображает найденные позиции в таблице."""
        rows: list[tuple[str, dict[str, Any], str]] = []
        for index, certificate in enumerate(self._certificates):
            tag = ""
            if certificate.is_expired:
                tag = "expired"
            elif (certificate.days_until_expiry or 999) <= 90:
                tag = "warning"

            rows.append(
                (
                    str(index),
                    {
                        "product": certificate.product_name,
                        "volume": str(certificate.volume) if certificate.volume else "—",
                        "number": certificate.display_number,
                        "expiry": format_date(certificate.expiry_date),
                        "row": certificate.source_row or "—",
                    },
                    tag,
                )
            )

        self._table.set_rows(rows)
        total = self.app.container.certificate_repository.count()
        self._count_label.configure(text=f"показано {len(rows)} из {total}")

        if total == 0 and not self._empty_visible:
            self._empty_visible = True
            self._table.grid_remove()
            self._empty_state.grid(row=0, column=0, sticky="nsew", padx=(0, Spacing.MD))
        elif total > 0 and self._empty_visible:
            self._empty_visible = False
            self._empty_state.grid_remove()
            self._table.grid(row=0, column=0, sticky="nsew", padx=(0, Spacing.MD))

    def _on_search(self, query: str) -> None:
        """Обрабатывает изменение поискового запроса."""
        self._query = query
        self.refresh()

    def _on_filter(self, value: str) -> None:
        """Обрабатывает смену фильтра."""
        self._filter = value
        self.refresh()

    def _on_select(self, row_id: str) -> None:
        """Показывает сведения и, если найден, документ выбранной позиции."""
        certificate = self._certificate_at(row_id)
        if certificate is None:
            return
        self._show_details(certificate)
        self._viewer.open(self._locate_pdf(certificate))

    def _show_details(self, certificate: CertificateProduct) -> None:
        """Заполняет карточку сведений."""
        for child in self._details_body.winfo_children():
            child.destroy()
        for child in self._details_card.actions.winfo_children():
            child.destroy()

        self._details_card.set_subtitle(certificate.display_number)
        if certificate.is_expired:
            Badge(self._details_card.actions, self.theme, text="Срок истёк", role="danger").pack()

        expiry_role = "danger" if certificate.is_expired else "text"
        fields: list[tuple[str, str, str]] = [
            ("Товар", certificate.product_name, "text"),
            ("Номер сертификата", certificate.display_number, "text"),
            ("Объём", str(certificate.volume) if certificate.volume else "не определён", "text"),
            ("Действует до", format_date(certificate.expiry_date), expiry_role),
            ("Строка в Excel", str(certificate.source_row or "—"), "text"),
        ]

        for label, value, role in fields:
            row = ctk.CTkFrame(self._details_body, fg_color="transparent", width=0, height=0)
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(
                row,
                text=label,
                font=self.theme.font(FontRole.CAPTION),
                text_color=self.theme.color("text_muted"),
                width=140,
                anchor="w",
            ).pack(side="left")
            ctk.CTkLabel(
                row,
                text=value,
                font=self.theme.font(FontRole.CAPTION),
                text_color=self.theme.color(role),
                anchor="w",
                justify="left",
                wraplength=260,
            ).pack(side="left", fill="x", expand=True)

    # -------------------------------------------------------------- действия
    def _certificate_at(self, row_id: str) -> CertificateProduct | None:
        """Возвращает позицию базы по идентификатору строки."""
        try:
            return self._certificates[int(row_id)]
        except (ValueError, IndexError):
            return None

    def _locate_pdf(self, certificate: CertificateProduct) -> Path | None:
        """Ищет PDF-файл сертификата по номеру в настроенной папке."""
        settings = self.app.settings.certificates
        directory = Path(settings.pdf_dir) if settings.pdf_dir else None
        return find_pdf(
            directory, certificate.certificate_number, recursive=settings.recursive_pdf_search
        )

    def _open_external(self, row_id: str) -> None:
        """Открывает PDF во внешней программе."""
        certificate = self._certificate_at(row_id)
        if certificate is None:
            return
        path = self._locate_pdf(certificate)
        if path is None:
            self.app.toasts.warning(f"PDF-файл сертификата {certificate.display_number} не найден")
            return
        self.app.open_path(path)

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
