"""Раздел «Словарь товаров» — полноценный редактор соответствий.

Программа запоминает каждое ручное решение пользователя и применяет его
раньше любых алгоритмов подбора. Этот раздел даёт полный контроль над
накопленной «памятью»: поиск, фильтры, создание и редактирование записей
вручную, массовые операции, проверку дубликатов, журнал изменений с отменой
последнего действия и резервное копирование словаря — без необходимости
трогать базу данных напрямую.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import customtkinter as ctk

from app.core.exceptions import DuplicateAliasError
from app.gui.theme import FontRole, Radius, Spacing
from app.gui.views.base_view import BaseView
from app.gui.widgets.alias_dialog import AliasAuditDialog, AliasEditDialog
from app.gui.widgets.base import focus_in_text_entry
from app.gui.widgets.card import SectionCard
from app.gui.widgets.controls import Badge, ghost_button, icon_button, secondary_button
from app.gui.widgets.data_table import Column, DataTable, EmptyState
from app.gui.widgets.dialogs import ask_confirmation
from app.gui.widgets.search_entry import SearchEntry
from app.models.alias import Alias
from app.models.certificate_product import CertificateProduct
from app.models.matching import MatchCandidate
from app.services.alias_service import DuplicateWarning

_LOGGER = logging.getLogger(__name__)

#: Максимум записей, отображаемых одновременно (постраничная загрузка не
#: нужна — таблица на базе ``ttk.Treeview`` спокойно держит тысячи строк).
_PAGE_SIZE = 2000

_ALL_BRANDS = "Все бренды"
_ALL_VOLUMES = "Любой объём"

#: Варианты сортировки: ``(ключ для сервиса, подпись в списке)``.
_SORT_OPTIONS: tuple[tuple[str, str], ...] = (
    ("updated_desc", "Сначала изменённые"),
    ("created_desc", "Сначала новые"),
    ("hits_desc", "По числу применений"),
    ("confidence_desc", "По уровню доверия"),
    ("name_asc", "По названию А→Я"),
)


class AliasesView(BaseView):
    """Просмотр, редактирование, импорт и экспорт словаря соответствий."""

    title = "Словарь товаров"
    subtitle = (
        "Соответствия наименований и товаров в сертификатах — применяются раньше любых алгоритмов"
    )

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
        self._brand = ""
        self._volume: float | None = None
        self._sort = _SORT_OPTIONS[0][0]
        self._volume_lookup: dict[str, float] = {}
        self._sort_lookup: dict[str, str] = {label: key for key, label in _SORT_OPTIONS}

    # ---------------------------------------------------------------- разметка
    def build(self) -> None:
        """Создаёт содержимое раздела."""
        self._build_actions()
        self._build_toolbar()
        self._build_bulk_bar()
        self._build_body()

        self._empty = EmptyState(
            self.content,
            self.theme,
            icon="alias",
            title="Словарь пока пуст",
            message=(
                "Соответствия появляются автоматически, когда вы выбираете сертификат "
                "в окне проверки. Добавьте первую запись вручную или импортируйте "
                "словарь с другого рабочего места через меню «Ещё» выше."
            ),
            action_text="Добавить соответствие",
            on_action=self.add_alias,
        )

        self.refresh()

    def _build_actions(self) -> None:
        """Создаёт кнопки в шапке раздела (справа налево по расположению).

        Шапка раздела заметно уже, чем в остальных разделах программы (там
        обычно одна-две кнопки): у словаря их семь. Даже в окне размера по
        умолчанию (1360×860) семь и пять кнопок подряд не помещаются и
        обрезаются краем окна, поэтому на виду остаётся только самое частое
        действие — «Добавить», а все остальные собраны в меню «Ещё».
        """
        self._undo_button = icon_button(
            self.actions,
            self.theme,
            icon="undo",
            command=self.undo,
            tooltip="Отменить последнее действие",
        )
        self._undo_button.pack(side="left", padx=(0, Spacing.MD))

        self._more_button = secondary_button(
            self.actions, self.theme, text="Ещё", icon="chevron_down", command=self._open_more_menu
        )
        self._more_button.pack(side="left", padx=(0, Spacing.SM))
        secondary_button(
            self.actions, self.theme, text="Добавить", icon="plus", command=self.add_alias
        ).pack(side="left")

    def _open_more_menu(self) -> None:
        """Открывает меню дополнительных действий под кнопкой «Ещё»."""
        import tkinter as tk

        menu = tk.Menu(self, tearoff=0)
        menu.configure(
            background=self.theme.resolved("surface"),
            foreground=self.theme.resolved("text"),
            activebackground=self.theme.resolved("accent_soft"),
            activeforeground=self.theme.resolved("text"),
            borderwidth=0,
            relief="flat",
        )
        menu.add_command(label="Импорт из файла…", command=self.import_aliases)
        menu.add_command(label="Экспорт в файл…", command=self.export_aliases)
        menu.add_separator()
        menu.add_command(label="Журнал изменений", command=self._open_audit_log)
        menu.add_command(label="Создать резервную копию", command=self._backup)
        menu.add_command(label="Восстановить из файла…", command=self._restore)

        x = self._more_button.winfo_rootx()
        y = self._more_button.winfo_rooty() + self._more_button.winfo_height()
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _build_toolbar(self) -> None:
        """Создаёт строку поиска, фильтров и сортировки."""
        toolbar = ctk.CTkFrame(self.content, fg_color="transparent", width=0, height=0)
        toolbar.pack(fill="x", pady=(0, Spacing.SM))

        self.search = SearchEntry(
            toolbar,
            self.theme,
            placeholder="Системное название, товар, бренд, файл или комментарий…",
            on_search=self._on_search,
            width=360,
        )
        self.search.pack(side="left")

        self._brand_menu = self._option_menu(
            toolbar, values=[_ALL_BRANDS], current=_ALL_BRANDS, command=self._on_brand_change
        )
        self._brand_menu.pack(side="left", padx=(Spacing.SM, 0))

        self._volume_menu = self._option_menu(
            toolbar, values=[_ALL_VOLUMES], current=_ALL_VOLUMES, command=self._on_volume_change
        )
        self._volume_menu.pack(side="left", padx=(Spacing.SM, 0))

        self._sort_menu = self._option_menu(
            toolbar,
            values=[label for _, label in _SORT_OPTIONS],
            current=_SORT_OPTIONS[0][1],
            command=self._on_sort_change,
        )
        self._sort_menu.pack(side="left", padx=(Spacing.SM, 0))

        self._count_label = ctk.CTkLabel(
            toolbar,
            text="",
            font=self.theme.font(FontRole.SMALL),
            text_color=self.theme.color("text_muted"),
        )
        self._count_label.pack(side="right")

    def _option_menu(
        self, master: Any, *, values: list[str], current: str, command: Any
    ) -> ctk.CTkOptionMenu:
        """Создаёт выпадающий список, оформленный под тему приложения."""
        theme = self.theme
        menu = ctk.CTkOptionMenu(
            master,
            values=values,
            width=170,
            command=command,
            font=theme.font(FontRole.SMALL),
            fg_color=theme.color("surface_alt"),
            button_color=theme.color("surface_hover"),
            button_hover_color=theme.color("accent_soft"),
            text_color=theme.color("text"),
            dropdown_fg_color=theme.color("surface"),
            dropdown_text_color=theme.color("text"),
            dropdown_hover_color=theme.color("accent_soft"),
            corner_radius=Radius.SM,
        )
        menu.set(current)
        return menu

    def _build_bulk_bar(self) -> None:
        """Создаёт скрытую по умолчанию панель массовых действий."""
        self._bulk_bar = ctk.CTkFrame(
            self.content, fg_color=self.theme.color("accent_soft"), corner_radius=Radius.SM
        )
        self._bulk_label = ctk.CTkLabel(
            self._bulk_bar,
            text="",
            font=self.theme.font(FontRole.SMALL),
            text_color=self.theme.color("accent"),
        )
        self._bulk_label.pack(side="left", padx=Spacing.MD, pady=Spacing.SM)

        ghost_button(
            self._bulk_bar,
            self.theme,
            text="Удалить выбранные",
            icon="trash",
            danger=True,
            command=self._delete_selected,
        ).pack(side="right", padx=(0, Spacing.SM))
        ghost_button(
            self._bulk_bar,
            self.theme,
            text="Указать бренд…",
            command=self._bulk_set_brand,
        ).pack(side="right", padx=(0, Spacing.SM))

    def _build_body(self) -> None:
        """Создаёт таблицу словаря и панель предпросмотра."""
        self._split = ctk.CTkFrame(self.content, fg_color="transparent", width=0, height=0)
        self._split.pack(fill="both", expand=True)
        self._split.grid_columnconfigure(0, weight=3, uniform="split")
        self._split.grid_columnconfigure(1, weight=2, uniform="split")
        self._split.grid_rowconfigure(0, weight=1)

        self._table = DataTable(
            self._split,
            self.theme,
            columns=(
                Column("source", "Системное название", width=220, stretch=True),
                Column("target", "Товар в сертификате", width=220, stretch=True),
                Column("brand", "Бренд", width=110),
                Column("volume", "Объём", width=90, anchor="center"),
                Column("hits", "Применений", width=90, anchor="center", numeric=True),
                Column("confidence", "Доверие", width=150),
                Column("last_used", "Последнее применение", width=150),
                Column("created", "Создано", width=100),
            ),
            on_select=self._on_table_select,
            on_activate=lambda row_id: self._open_edit(self._alias_at(row_id)),
            context_actions=(
                ("Изменить…", lambda row_id: self._open_edit(self._alias_at(row_id))),
                ("Открыть сертификат", self._preview),
                ("История записи", lambda row_id: self._open_alias_history(self._alias_at(row_id))),
                ("-", lambda _: None),
                ("Удалить", lambda row_id: self._delete_by_row(row_id)),
            ),
            selectmode="extended",
            height=20,
        )
        self._table.grid(row=0, column=0, sticky="nsew", padx=(0, Spacing.MD))

        side = ctk.CTkFrame(self._split, fg_color="transparent", width=0, height=0)
        side.grid(row=0, column=1, sticky="nsew")

        self._details_card = SectionCard(
            side,
            self.theme,
            title="Сведения",
            subtitle="Выберите запись в списке",
            icon="info",
            animator=self.app.animator,
        )
        self._details_card.pack(fill="both", expand=True)

        self._details_body = ctk.CTkFrame(
            self._details_card.content, fg_color="transparent", width=0, height=0
        )
        self._details_body.pack(fill="both", expand=True)
        self._render_empty_details()

    # ------------------------------------------------------------- поведение
    def on_show(self) -> None:
        """Обновляет список и включает горячие клавиши раздела."""
        self.refresh()
        self._bind_shortcuts()

    def on_hide(self) -> None:
        """Отключает горячие клавиши раздела."""
        self._unbind_shortcuts()

    def focus_search(self) -> None:
        """Передаёт фокус строке поиска."""
        self.ensure_built()
        self.search.focus_input()

    def refresh(self) -> None:
        """Перечитывает словарь с учётом поиска, фильтров и сортировки."""
        if not hasattr(self, "_table"):
            return
        service = self.app.container.alias_service
        try:
            self._aliases = service.search(
                self._query,
                brand=self._brand,
                volume_ml=self._volume,
                sort=self._sort,
                limit=_PAGE_SIZE,
            )
            total = service.count_search(self._query, brand=self._brand, volume_ml=self._volume)
            total_all = service.count()
        except Exception:
            _LOGGER.exception("Не удалось загрузить словарь соответствий")
            return

        self._render_rows()
        self._count_label.configure(text=f"показано {len(self._aliases)} из {total}")
        self._refresh_filter_options(service)
        self._update_undo_button(service)
        self._update_bulk_bar(0)
        self._render_empty_details()

        if total_all == 0:
            self._split.pack_forget()
            self._empty.pack(fill="both", expand=True)
        else:
            self._empty.pack_forget()
            self._split.pack(fill="both", expand=True)

    def _refresh_filter_options(self, service: Any) -> None:
        """Обновляет значения выпадающих фильтров бренда и объёма."""
        try:
            brands = service.list_brands()
            volumes = service.list_volumes()
        except Exception:
            return

        current_brand = self._brand_menu.get()
        self._brand_menu.configure(values=[_ALL_BRANDS, *brands])
        if current_brand not in (_ALL_BRANDS, *brands):
            self._brand_menu.set(_ALL_BRANDS)

        self._volume_lookup = {_format_volume(value): value for value in volumes}
        labels = [_ALL_VOLUMES, *self._volume_lookup]
        current_volume = self._volume_menu.get()
        self._volume_menu.configure(values=labels)
        if current_volume not in labels:
            self._volume_menu.set(_ALL_VOLUMES)

    def _update_undo_button(self, service: Any) -> None:
        """Обновляет доступность и подсказку кнопки отмены."""
        try:
            pending = service.pending_undo()
        except Exception:
            pending = None
        try:
            if pending is None:
                self._undo_button.configure(state="disabled")
            else:
                self._undo_button.configure(state="normal")
        except Exception:
            pass

    def _render_rows(self) -> None:
        """Отображает найденные записи в таблице."""
        rows: list[tuple[str, dict[str, Any], str]] = []
        for index, alias in enumerate(self._aliases):
            tag = "matched" if alias.is_manual else ("" if alias.hit_count else "muted")
            rows.append(
                (
                    str(index),
                    {
                        "source": alias.source_text,
                        "target": alias.target_name or "—",
                        "brand": alias.brand or "—",
                        "volume": alias.volume_label or "—",
                        "hits": alias.hit_count,
                        "confidence": f"{alias.confidence:.0f} % · {alias.source_label}",
                        "last_used": (
                            alias.last_used_at.strftime("%d.%m.%Y %H:%M")
                            if alias.last_used_at
                            else "ещё не применялся"
                        ),
                        "created": alias.created_at.strftime("%d.%m.%Y"),
                    },
                    tag,
                )
            )
        self._table.set_rows(rows)

    # ---------------------------------------------------------- фильтры/поиск
    def _on_search(self, query: str) -> None:
        """Обрабатывает изменение поискового запроса."""
        self._query = query
        self.refresh()

    def _on_brand_change(self, value: str) -> None:
        """Обрабатывает выбор бренда в фильтре."""
        self._brand = "" if value == _ALL_BRANDS else value
        self.refresh()

    def _on_volume_change(self, value: str) -> None:
        """Обрабатывает выбор объёма в фильтре."""
        self._volume = None if value == _ALL_VOLUMES else self._volume_lookup.get(value)
        self.refresh()

    def _on_sort_change(self, value: str) -> None:
        """Обрабатывает выбор варианта сортировки."""
        self._sort = self._sort_lookup.get(value, _SORT_OPTIONS[0][0])
        self.refresh()

    # -------------------------------------------------------------- выбор
    def _alias_at(self, row_id: str) -> Alias | None:
        """Возвращает запись по идентификатору строки таблицы."""
        try:
            return self._aliases[int(row_id)]
        except (ValueError, IndexError):
            return None

    def _selected_aliases(self) -> list[Alias]:
        """Возвращает все выбранные в таблице записи."""
        result = []
        for row_id in self._table.selected_ids:
            alias = self._alias_at(row_id)
            if alias is not None:
                result.append(alias)
        return result

    def _on_table_select(self, row_id: str) -> None:
        """Показывает сведения о записи или включает панель массовых действий."""
        selected = self._table.selected_ids
        self._update_bulk_bar(len(selected))
        if len(selected) == 1:
            alias = self._alias_at(row_id)
            if alias is not None:
                self._show_details(alias)
        else:
            self._render_empty_details()

    def _update_bulk_bar(self, count: int) -> None:
        """Показывает или скрывает панель массовых действий."""
        if count >= 2:
            self._bulk_label.configure(text=f"Выбрано записей: {count}")
            self._bulk_bar.pack(fill="x", pady=(0, Spacing.SM), before=self._split)
        else:
            self._bulk_bar.pack_forget()

    # ------------------------------------------------------------ предпросмотр
    def _render_empty_details(self) -> None:
        """Показывает заглушку в панели сведений."""
        for child in self._details_body.winfo_children():
            child.destroy()
        self._details_card.set_subtitle("Выберите запись в списке")
        ctk.CTkLabel(
            self._details_body,
            text="Нет выбранной записи",
            font=self.theme.font(FontRole.SMALL),
            text_color=self.theme.color("text_muted"),
        ).pack(pady=Spacing.LG)

    def _show_details(self, alias: Alias) -> None:
        """Заполняет панель сведений выбранной записью."""
        for child in self._details_body.winfo_children():
            child.destroy()

        self._details_card.set_subtitle(alias.target_name or "русское название не указано")

        def _field_row(label: str, value: str) -> None:
            row = ctk.CTkFrame(self._details_body, fg_color="transparent", width=0, height=0)
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(
                row,
                text=label,
                font=self.theme.font(FontRole.CAPTION),
                text_color=self.theme.color("text_muted"),
                width=170,
                anchor="w",
            ).pack(side="left")
            ctk.CTkLabel(
                row,
                text=value,
                font=self.theme.font(FontRole.CAPTION),
                text_color=self.theme.color("text"),
                anchor="w",
                justify="left",
                wraplength=210,
            ).pack(side="left", fill="x", expand=True)

        _field_row("Товар в сертификате", alias.target_name or "—")
        _field_row("Бренд", alias.brand or "—")
        _field_row("Объём", alias.volume_label or "не указан")

        confidence_row = ctk.CTkFrame(self._details_body, fg_color="transparent", width=0, height=0)
        confidence_row.pack(fill="x", pady=1)
        ctk.CTkLabel(
            confidence_row,
            text="Доверие",
            font=self.theme.font(FontRole.CAPTION),
            text_color=self.theme.color("text_muted"),
            width=170,
            anchor="w",
        ).pack(side="left")
        Badge(
            confidence_row,
            self.theme,
            text=f"{alias.confidence:.0f} % · {alias.source_label}",
            role=_confidence_role(alias.confidence),
        ).pack(side="left")

        _field_row("Применений", str(alias.hit_count))
        _field_row(
            "Последнее применение",
            (
                alias.last_used_at.strftime("%d.%m.%Y %H:%M")
                if alias.last_used_at
                else "ещё не применялся"
            ),
        )
        _field_row(
            "Создано",
            f"{alias.created_at.strftime('%d.%m.%Y %H:%M')}"
            + (f" · {alias.created_by}" if alias.created_by else ""),
        )
        _field_row("Изменено", alias.updated_at.strftime("%d.%m.%Y %H:%M"))
        _field_row("Комментарий", alias.note or "—")

        actions = ctk.CTkFrame(self._details_body, fg_color="transparent", width=0, height=0)
        actions.pack(fill="x", pady=(Spacing.MD, 0))
        secondary_button(
            actions,
            self.theme,
            text="Изменить",
            icon="edit",
            command=lambda: self._open_edit(alias),
        ).pack(side="left")
        ghost_button(
            actions,
            self.theme,
            text="Сертификат",
            icon="eye",
            command=lambda: self._open_certificate(alias),
        ).pack(side="left", padx=(Spacing.SM, 0))
        ghost_button(
            actions,
            self.theme,
            text="Удалить",
            icon="trash",
            danger=True,
            command=lambda: self._delete_one(alias),
        ).pack(side="left", padx=(Spacing.SM, 0))

        related = self.app.container.alias_service.find_related_certificates(alias)
        ctk.CTkLabel(
            self._details_body,
            text="СЕЙЧАС РАЗРЕШАЕТСЯ В (строгий поиск по базе)",
            font=self.theme.font(FontRole.CAPTION),
            text_color=self.theme.color("text_muted"),
            anchor="w",
        ).pack(fill="x", anchor="w", pady=(Spacing.LG, Spacing.XS))
        if related:
            for certificate in related:
                self._render_related_row(certificate)
        else:
            ctk.CTkLabel(
                self._details_body,
                text="Ничего не найдено — при подборе строка будет считаться ненайденной",
                font=self.theme.font(FontRole.CAPTION),
                text_color=self.theme.color("warning"),
                anchor="w",
                justify="left",
                wraplength=260,
            ).pack(fill="x", anchor="w")

        history = self.app.container.alias_service.audit_log(alias_id=alias.id, limit=3)
        if history:
            ctk.CTkLabel(
                self._details_body,
                text="ПОСЛЕДНИЕ ИЗМЕНЕНИЯ",
                font=self.theme.font(FontRole.CAPTION),
                text_color=self.theme.color("text_muted"),
                anchor="w",
            ).pack(fill="x", anchor="w", pady=(Spacing.LG, Spacing.XS))
            for entry in history:
                ctk.CTkLabel(
                    self._details_body,
                    text=f"{entry.at.strftime('%d.%m.%Y %H:%M')} · {entry.action.label}",
                    font=self.theme.font(FontRole.CAPTION),
                    text_color=self.theme.color("text_muted"),
                    anchor="w",
                ).pack(fill="x", anchor="w")
            ghost_button(
                self._details_body,
                self.theme,
                text="Вся история записи",
                command=lambda: self._open_alias_history(alias),
            ).pack(anchor="w", pady=(Spacing.XS, 0))

    def _render_related_row(self, certificate: CertificateProduct) -> None:
        """Отображает одну строку найденной позиции базы в панели сведений."""
        row = ctk.CTkFrame(
            self._details_body, fg_color=self.theme.color("surface_alt"), corner_radius=Radius.MD
        )
        row.pack(fill="x", pady=2)
        ctk.CTkLabel(
            row,
            text=certificate.summary(),
            font=self.theme.font(FontRole.CAPTION),
            text_color=self.theme.color("text"),
            anchor="w",
            justify="left",
            wraplength=230,
        ).pack(side="left", fill="x", expand=True, padx=Spacing.SM, pady=4)
        ghost_button(
            row,
            self.theme,
            text="",
            icon="eye",
            command=lambda: self.app.preview_pdf(certificate.certificate_number),
        ).pack(side="right")

    # -------------------------------------------------------------- действия
    def add_alias(self) -> None:
        """Открывает окно добавления новой записи словаря."""
        self.ensure_built()
        dialog = AliasEditDialog(
            self.app,
            self.theme,
            search_certificates=self._search_certificates,
            suggest_certificates=self._suggest_certificates,
        )
        result = dialog.wait_result()
        if result is None:
            return
        self._commit_new(result)

    def _edit_selected(self) -> None:
        """Открывает окно редактирования выбранной записи (Ctrl+E)."""
        aliases = self._selected_aliases()
        if len(aliases) != 1:
            self.app.toasts.info("Выберите одну запись для изменения")
            return
        self._open_edit(aliases[0])

    def _open_edit(self, alias: Alias | None) -> None:
        """Открывает окно редактирования заданной записи."""
        if alias is None:
            return
        dialog = AliasEditDialog(
            self.app,
            self.theme,
            search_certificates=self._search_certificates,
            suggest_certificates=self._suggest_certificates,
            alias=alias,
        )
        result = dialog.wait_result()
        if result is None:
            return
        self._commit_edit(alias, result)

    def _search_certificates(self, query: str) -> list[CertificateProduct]:
        """Ищет позиции базы сертификатов для ручного поиска в диалоге."""
        return self.app.container.certificate_repository.search(query, limit=15)

    def _suggest_certificates(self, source_text: str) -> list[MatchCandidate]:
        """Подбирает ИИ-предложения для окна добавления/редактирования."""
        return self.app.container.alias_service.suggest_certificates(source_text, limit=5)

    def _commit_new(self, result: dict[str, Any]) -> None:
        """Сохраняет новую запись после проверки на дубликаты."""
        service = self.app.container.alias_service
        warning = service.find_potential_duplicates(result["source_text"], result["target_name"])
        if warning.has_matches and not self._confirm_duplicates(warning):
            return

        try:
            service.add(
                result["source_text"],
                result["target_name"],
                certificate_product_id=result["certificate_product_id"],
                brand=result["brand"],
                volume_ml=result["volume_ml"],
                note=result["note"],
            )
        except (DuplicateAliasError, ValueError) as error:
            self.app.show_error("Не удалось добавить соответствие", str(error))
            return

        self.app.toasts.success("Соответствие добавлено")
        self.refresh()

    def _commit_edit(self, alias: Alias, result: dict[str, Any]) -> None:
        """Сохраняет изменения записи после проверки на дубликаты."""
        if alias.id is None:
            return
        service = self.app.container.alias_service
        warning = service.find_potential_duplicates(
            result["source_text"], result["target_name"], exclude_id=alias.id
        )
        if warning.has_matches and not self._confirm_duplicates(warning):
            return

        try:
            service.update(
                alias.id,
                source_text=result["source_text"],
                target_name=result["target_name"],
                certificate_product_id=result["certificate_product_id"],
                brand=result["brand"],
                volume_ml=result["volume_ml"],
                note=result["note"],
            )
        except DuplicateAliasError as error:
            self.app.show_error("Не удалось сохранить изменения", str(error))
            return

        self.app.toasts.success("Изменения сохранены")
        self.refresh()

    def _confirm_duplicates(self, warning: DuplicateWarning) -> bool:
        """Предупреждает о похожих записях и спрашивает подтверждение."""
        detail = "\n".join(f"• {item.describe()}" for item in warning.candidates[:5])
        return ask_confirmation(
            self.app,
            self.theme,
            title="Похожие записи уже есть в словаре",
            message="Сохранить всё равно как новое соответствие?",
            detail=detail,
            confirm_text="Сохранить всё равно",
        )

    def _preview(self, row_id: str) -> None:
        """Открывает сертификат, на который ссылается запись."""
        self._open_certificate(self._alias_at(row_id))

    def _open_certificate(self, alias: Alias | None) -> None:
        """Открывает сертификат, на который сейчас разрешается запись."""
        if alias is None:
            return
        related = self.app.container.alias_service.find_related_certificates(alias, limit=1)
        if not related:
            self.app.toasts.warning("Сертификат не найден в базе по текущим данным словаря")
            return
        self.app.preview_pdf(related[0].certificate_number)

    def _delete_by_row(self, row_id: str) -> None:
        """Удаляет одну запись (действие контекстного меню строки).

        Открытие контекстного меню всегда сворачивает выбор к одной строке
        (см. ``DataTable._build_context_menu``), поэтому массовое удаление
        доступно только через панель массовых действий, а не через это меню.
        """
        alias = self._alias_at(row_id)
        self._delete_many([alias] if alias is not None else [])

    def _delete_selected(self) -> None:
        """Удаляет все выбранные записи (кнопка массовых действий, Delete)."""
        self._delete_many(self._selected_aliases())

    def _delete_one(self, alias: Alias) -> None:
        """Удаляет одну запись из панели сведений."""
        self._delete_many([alias])

    def _delete_many(self, aliases: list[Alias]) -> None:
        """Удаляет одну или несколько записей с подтверждением."""
        if not aliases:
            self.app.toasts.info("Выберите запись для удаления")
            return

        if len(aliases) == 1:
            alias = aliases[0]
            if alias.id is None:
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
            return

        if not ask_confirmation(
            self.app,
            self.theme,
            title="Удалить соответствия",
            message=f"Удалить выбранные записи ({len(aliases)})?",
            detail="Действие можно отменить кнопкой «Отменить», пока вы не закрыли программу.",
            confirm_text="Удалить",
            danger=True,
        ):
            return

        ids = [alias.id for alias in aliases if alias.id is not None]
        removed = self.app.container.alias_service.bulk_delete(ids)
        if removed:
            self.app.toasts.success(f"Удалено записей: {removed}")
            self.refresh()

    def _bulk_set_brand(self) -> None:
        """Массово задаёт бренд у выбранных записей."""
        aliases = self._selected_aliases()
        if len(aliases) < 2:
            self.app.toasts.info("Выберите несколько записей (2 и более)")
            return
        dialog = ctk.CTkInputDialog(
            text=f"Новое значение бренда для {len(aliases)} записей:", title="Изменить бренд"
        )
        value = dialog.get_input()
        if value is None:
            return
        ids = [alias.id for alias in aliases if alias.id is not None]
        changed = self.app.container.alias_service.bulk_update(ids, brand=value.strip())
        if changed:
            self.app.toasts.success(f"Бренд изменён у {changed} записей")
            self.refresh()

    def undo(self) -> None:
        """Отменяет последнее действие в словаре (Ctrl+Z)."""
        entry = self.app.container.alias_service.undo_last()
        if entry is None:
            self.app.toasts.info("Нечего отменять")
            return
        self.app.toasts.success(f"Отменено: {entry.action.label.lower()} — {entry.source_text}")
        self.refresh()

    def _open_audit_log(self) -> None:
        """Открывает полный журнал изменений словаря."""
        entries = self.app.container.alias_service.audit_log(limit=300)
        AliasAuditDialog(self.app, self.theme, entries=entries)

    def _open_alias_history(self, alias: Alias | None) -> None:
        """Открывает журнал изменений одной записи."""
        if alias is None or alias.id is None:
            return
        entries = self.app.container.alias_service.audit_log(alias_id=alias.id, limit=100)
        AliasAuditDialog(
            self.app, self.theme, entries=entries, title=f"История записи «{alias.source_text}»"
        )

    def _backup(self) -> None:
        """Создаёт резервную копию словаря."""
        try:
            path = self.app.container.alias_service.backup()
        except Exception as error:
            self.app.show_error("Резервная копия не создана", str(error))
            return
        self.app.toasts.success(f"Резервная копия создана: {path.name}")

    def _restore(self) -> None:
        """Восстанавливает словарь из ранее сохранённого файла."""
        from tkinter import filedialog

        initial_dir = self.app.container.alias_service.backups_dir
        source = filedialog.askopenfilename(
            title="Восстановить словарь из файла",
            initialdir=str(initial_dir) if initial_dir else None,
            filetypes=[("Резервные копии и экспорт", "*.json *.csv *.xlsx"), ("Все файлы", "*.*")],
        )
        if not source:
            return
        try:
            added, merged, skipped = self.app.container.alias_service.restore(Path(source))
        except Exception as error:
            self.app.show_error("Восстановление не выполнено", str(error))
            return
        self.refresh()
        self.app.toasts.success(
            f"Восстановлено: добавлено {added}, объединено {merged}, пропущено {skipped}"
        )

    def export_aliases(self) -> None:
        """Экспортирует словарь в файл."""
        from tkinter import filedialog

        target = filedialog.asksaveasfilename(
            title="Экспорт словаря",
            defaultextension=".xlsx",
            initialfile="Словарь соответствий.xlsx",
            filetypes=[("Excel", "*.xlsx"), ("JSON", "*.json"), ("CSV", "*.csv")],
        )
        if not target:
            return
        try:
            count = self.app.container.alias_service.export(Path(target))
        except Exception as error:
            self.app.show_error("Экспорт не выполнен", str(error))
            return
        self.app.toasts.success(f"Экспортировано записей: {count}")

    def import_aliases(self) -> None:
        """Импортирует словарь из файла."""
        from tkinter import filedialog

        source = filedialog.askopenfilename(
            title="Импорт словаря",
            filetypes=[("Excel, JSON или CSV", "*.xlsx *.xlsm *.json *.csv"), ("Все файлы", "*.*")],
        )
        if not source:
            return
        try:
            added, merged, skipped = self.app.container.alias_service.import_from(Path(source))
        except Exception as error:
            self.app.show_error("Импорт не выполнен", str(error))
            return

        self.refresh()
        message = f"Добавлено: {added}, объединено: {merged}"
        if skipped:
            message += f", пропущено: {skipped}"
        self.app.toasts.success(message)

    # ------------------------------------------------------------ горячие клавиши
    def _bind_shortcuts(self) -> None:
        """Включает горячие клавиши раздела, пока он активен."""
        self.app.bind_all("<Control-n>", self._guard(lambda: self.add_alias()))
        self.app.bind_all("<Control-e>", self._guard(lambda: self._edit_selected()))
        self.app.bind_all("<Control-z>", self._guard(lambda: self.undo()))
        self.app.bind_all("<Delete>", self._guard_delete)

    def _unbind_shortcuts(self) -> None:
        """Отключает горячие клавиши раздела при уходе с экрана."""
        for sequence in ("<Control-n>", "<Control-e>", "<Control-z>", "<Delete>"):
            try:
                self.app.unbind_all(sequence)
            except Exception:
                pass

    def _guard(self, action: Any) -> Any:
        """Оборачивает обработчик горячей клавиши раздела.

        Не срабатывает поверх модальных окон и, что не менее важно, пока
        фокус ввода находится в текстовом поле (строка поиска, поля формы
        добавления/редактирования) — иначе, например, Ctrl+Z как рефлекс
        «отменить» посреди правки текста откатывал бы последнее действие в
        словаре вместо обычной работы поля ввода.
        """

        def _run(_event: Any = None) -> str | None:
            if self.app.grab_current() is not None or focus_in_text_entry(self.app):
                return None
            try:
                action()
            except Exception:
                _LOGGER.exception("Ошибка горячей клавиши словаря")
            return "break"

        return _run

    def _guard_delete(self, _event: Any = None) -> str | None:
        """Обрабатывает клавишу Delete только когда фокус на таблице.

        Без этой проверки нажатие Delete во время ввода текста (например, в
        строке поиска или в диалоге добавления) удаляло бы выбранную строку
        словаря вместо обычного удаления символа.
        """
        if self.app.grab_current() is not None:
            return None
        if self.app.focus_get() is not self._table.tree:
            return None
        self._delete_selected()
        return "break"

    def refresh_theme(self) -> None:
        """Обновляет цвета после смены темы."""
        super().refresh_theme()
        try:
            self._table.refresh_theme()
            self._bulk_bar.configure(fg_color=self.theme.color("accent_soft"))
        except Exception:
            pass


def _format_volume(value: float) -> str:
    """Форматирует значение объёма для списка фильтра."""
    return f"{value:g} мл"


def _confidence_role(confidence: float) -> str:
    """Определяет роль цвета бейджа уровня доверия записи.

    Три значения соответствуют уровням ``Alias.confidence`` — 100
    (запись пользователя), 95 (ИИ, подтверждено частым применением),
    80 (ИИ, не подтверждено).
    """
    if confidence >= 100:
        return "success"
    if confidence >= 95:
        return "accent"
    return "warning"
