"""Диалоги словаря соответствий: добавление/редактирование и журнал изменений."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from app.core.product_code import parse_product_name
from app.gui.theme import FontRole, Radius, Spacing, Theme
from app.gui.widgets.controls import ghost_button, primary_button, secondary_button
from app.gui.widgets.data_table import Column, DataTable
from app.gui.widgets.dialogs import ModalDialog
from app.models.alias import Alias
from app.models.alias_audit import AliasAuditEntry
from app.models.certificate_product import CertificateProduct
from app.models.matching import MatchCandidate

_LOGGER = logging.getLogger(__name__)

#: Пауза после последнего нажатия клавиши перед запуском ИИ-подбора: печать
#: не должна дёргать RapidFuzz/Sentence Transformers на каждый символ.
_SUGGEST_DELAY_MS = 350


class AliasEditDialog(ModalDialog):
    """Окно добавления или редактирования записи словаря соответствий.

    Разделено на две колонки, как и задумано для этого раздела: слева — что
    программа поняла из системного названия (код товара, тип, название,
    объём, количество в коробке — разбирается на лету, вводить руками не
    нужно), справа — подбор конкретного товара из базы сертификатов, который
    и станет целью соответствия.

    Правая колонка — единственный способ задать целевой товар: свободный
    ввод русского названия убран умышленно, соответствие всегда должно
    указывать на конкретную запись базы, а не на текст, который мог разойтись
    с тем, что реально есть в Excel. Подбор сразу предлагает варианты через
    ИИ (RapidFuzz + Sentence Transformers, тот же алгоритм, что и при
    обработке заказа) и одновременно даёт строку ручного поиска — на случай,
    когда предложенные варианты не подходят.
    """

    def __init__(
        self,
        master: Any,
        theme: Theme,
        *,
        search_certificates: Callable[[str], list[CertificateProduct]],
        suggest_certificates: Callable[[str], list[MatchCandidate]],
        alias: Alias | None = None,
    ) -> None:
        """Создаёт диалог добавления/редактирования.

        Args:
            master: Родительское окно.
            theme: Активная тема оформления.
            search_certificates: Функция ручного поиска по базе сертификатов.
            suggest_certificates: Функция ИИ-подбора по системному названию.
            alias: Редактируемая запись; ``None`` — создание новой.
        """
        editing = alias is not None
        super().__init__(
            master,
            theme,
            title="Изменить соответствие" if editing else "Добавить соответствие",
            width=1080,
            height=760,
            resizable=True,
        )
        self._search_certificates = search_certificates
        self._suggest_certificates = suggest_certificates
        self._alias = alias
        self._selected_certificate: CertificateProduct | None = None
        self._suggest_after_id: str | None = None

        # Кнопки сохранения собираются и занимают своё место ПЕРВЫМИ, до
        # остального содержимого. В ``pack()`` порядок вызова определяет,
        # кто первым получает место в контейнере фиксированного размера:
        # прокручиваемые списки ниже упаковываются с ``expand=True`` и в
        # противном случае забирали бы себе всю оставшуюся высоту, не
        # оставляя кнопкам «Сохранить»/«Отмена» ни пикселя.
        self._build_footer()
        self._build_source_row()
        self._build_columns()

        self._update_parsed_preview()
        self._render_selection_summary()
        self.after(150, self._run_suggestions)

    # ------------------------------------------------------------- разметка
    def _build_source_row(self) -> None:
        """Строит поле системного названия — единственный обязательный ввод."""
        theme = self._theme
        ctk.CTkLabel(
            self.container,
            text="Системное название товара (как в заказе)",
            font=theme.font(FontRole.CAPTION),
            text_color=theme.color("text_muted"),
            anchor="w",
        ).pack(fill="x", anchor="w", pady=(0, 2))

        self.source_var = ctk.StringVar(value=self._alias.source_text if self._alias else "")
        entry = ctk.CTkEntry(
            self.container,
            textvariable=self.source_var,
            height=38,
            font=theme.font(FontRole.BODY_STRONG),
            fg_color=theme.color("surface_alt"),
            border_color=theme.color("border"),
            placeholder_text="Например: 61004628 TP Dr Rabbit Kids Bubblegum 50ml [48]",
        )
        entry.pack(fill="x")
        entry.after(120, entry.focus_set)
        self.source_var.trace_add("write", lambda *_: self._on_source_changed())

    def _build_columns(self) -> None:
        """Строит левую (разбор названия) и правую (подбор товара) колонки."""
        columns = ctk.CTkFrame(self.container, fg_color="transparent", width=0, height=0)
        columns.pack(fill="both", expand=True, pady=(Spacing.MD, 0))
        columns.grid_columnconfigure(0, weight=2, uniform="cols")
        columns.grid_columnconfigure(1, weight=3, uniform="cols")
        columns.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(columns, fg_color="transparent", width=0, height=0)
        left.grid(row=0, column=0, sticky="new", padx=(0, Spacing.MD))
        self._build_left_panel(left)

        right = ctk.CTkFrame(columns, fg_color="transparent", width=0, height=0)
        right.grid(row=0, column=1, sticky="nsew")
        self._build_right_panel(right)

    def _build_left_panel(self, master: Any) -> None:
        """Строит левую колонку: разбор системного названия и заметки."""
        theme = self._theme
        ctk.CTkLabel(
            master,
            text="ИНФОРМАЦИЯ О СИСТЕМНОМ ТОВАРЕ",
            font=theme.font(FontRole.CAPTION),
            text_color=theme.color("text_muted"),
            anchor="w",
        ).pack(fill="x", anchor="w", pady=(0, Spacing.XS))

        card = ctk.CTkFrame(master, fg_color=theme.color("surface_alt"), corner_radius=Radius.MD)
        card.pack(fill="x")
        inner = ctk.CTkFrame(card, fg_color="transparent", width=0, height=0)
        inner.pack(fill="x", padx=Spacing.MD, pady=Spacing.MD)

        self._parsed_labels: dict[str, ctk.CTkLabel] = {}
        for key, label in (
            ("code", "Код товара"),
            ("type", "Тип товара"),
            ("name", "Название"),
            ("volume", "Объём"),
            ("box", "Кол-во в коробке"),
        ):
            row = ctk.CTkFrame(inner, fg_color="transparent", width=0, height=0)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(
                row,
                text=label,
                font=theme.font(FontRole.CAPTION),
                text_color=theme.color("text_muted"),
                width=140,
                anchor="w",
            ).pack(side="left")
            value_label = ctk.CTkLabel(
                row,
                text="—",
                font=theme.font(FontRole.SMALL),
                text_color=theme.color("text"),
                anchor="w",
                justify="left",
                wraplength=220,
            )
            value_label.pack(side="left", fill="x", expand=True)
            self._parsed_labels[key] = value_label

        self.brand_var = ctk.StringVar(value=self._alias.brand if self._alias else "")
        _field(master, theme, "Бренд", self.brand_var)

        self.note_var = ctk.StringVar(value=self._alias.note if self._alias else "")
        _field(master, theme, "Комментарий", self.note_var)

    def _build_right_panel(self, master: Any) -> None:
        """Строит правую колонку: сводку выбора, ИИ-предложения и ручной поиск."""
        theme = self._theme
        ctk.CTkLabel(
            master,
            text="ПОДБОР ТОВАРА ИЗ БАЗЫ СЕРТИФИКАТОВ",
            font=theme.font(FontRole.CAPTION),
            text_color=theme.color("text_muted"),
            anchor="w",
        ).pack(fill="x", anchor="w", pady=(0, Spacing.XS))

        self._summary_label = ctk.CTkLabel(
            master,
            text="Товар не выбран",
            font=theme.font(FontRole.BODY_STRONG),
            text_color=theme.color("text_muted"),
            anchor="w",
            justify="left",
            wraplength=560,
        )
        self._summary_label.pack(fill="x", anchor="w", pady=(0, Spacing.SM))

        ctk.CTkLabel(
            master,
            text="ИИ-ПРЕДЛОЖЕНИЯ (режим 1)",
            font=theme.font(FontRole.CAPTION),
            text_color=theme.color("text_muted"),
            anchor="w",
        ).pack(fill="x", anchor="w")

        self._suggestions = ctk.CTkScrollableFrame(
            master, fg_color=theme.color("surface_alt"), corner_radius=Radius.MD, height=190
        )
        self._suggestions.pack(fill="x", pady=(Spacing.XS, Spacing.MD))
        self._render_empty_suggestions("Введите системное название, чтобы получить предложения")

        ctk.CTkLabel(
            master,
            text="РУЧНОЙ ПОИСК (режим 2)",
            font=theme.font(FontRole.CAPTION),
            text_color=theme.color("text_muted"),
            anchor="w",
        ).pack(fill="x", anchor="w")

        search_row = ctk.CTkFrame(master, fg_color="transparent", width=0, height=0)
        search_row.pack(fill="x", pady=(Spacing.XS, 0))

        self._search_var = ctk.StringVar()
        search_entry = ctk.CTkEntry(
            search_row,
            textvariable=self._search_var,
            height=34,
            font=theme.font(FontRole.BODY),
            fg_color=theme.color("surface_alt"),
            border_color=theme.color("border"),
            placeholder_text="Название, часть слова, объём…",
        )
        search_entry.pack(side="left", fill="x", expand=True)
        search_entry.bind("<Return>", lambda _: self._run_search())

        secondary_button(
            search_row, theme, text="Найти", icon="search", command=self._run_search, height=34
        ).pack(side="left", padx=(Spacing.SM, 0))

        self._results = ctk.CTkScrollableFrame(
            master, fg_color=theme.color("surface_alt"), corner_radius=Radius.MD
        )
        self._results.pack(fill="both", expand=True, pady=(Spacing.XS, 0))
        self._render_empty_results("Введите запрос и нажмите «Найти»")

    def _build_footer(self) -> None:
        """Строит кнопки сохранения/отмены и место для сообщения об ошибке.

        Оба виджета закреплены за нижним краем контейнера (``side="bottom"``)
        и упаковываются в порядке «снизу вверх»: кнопки — первыми, чтобы
        занять самый нижний ряд, сообщение об ошибке — следом, чтобы
        оказаться сразу над ними.
        """
        theme = self._theme
        buttons = ctk.CTkFrame(self.container, fg_color="transparent", width=0, height=0)
        buttons.pack(fill="x", side="bottom", pady=(Spacing.MD, 0))

        primary_button(buttons, theme, text="Сохранить", command=self._submit).pack(side="right")
        secondary_button(buttons, theme, text="Отмена", command=self.close).pack(
            side="right", padx=(0, Spacing.SM)
        )

        self._error_label = ctk.CTkLabel(
            self.container,
            text="",
            font=theme.font(FontRole.CAPTION),
            text_color=theme.color("danger"),
            anchor="w",
        )
        self._error_label.pack(fill="x", anchor="w", side="bottom", pady=(Spacing.SM, 0))

    # --------------------------------------------------------- разбор названия
    def _on_source_changed(self) -> None:
        """Обновляет разбор названия сразу и планирует новый ИИ-подбор."""
        self._update_parsed_preview()
        if self._suggest_after_id is not None:
            try:
                self.after_cancel(self._suggest_after_id)
            except Exception:
                pass
        self._suggest_after_id = self.after(_SUGGEST_DELAY_MS, self._run_suggestions)

    def _update_parsed_preview(self) -> None:
        """Пересчитывает разбор системного названия для левой колонки."""
        parsed = parse_product_name(self.source_var.get())
        self._parsed_labels["code"].configure(text=parsed.code or "—")
        self._parsed_labels["type"].configure(text=parsed.product_type or "—")
        self._parsed_labels["name"].configure(text=parsed.name or "—")
        self._parsed_labels["volume"].configure(text=str(parsed.volume) if parsed.volume else "—")
        self._parsed_labels["box"].configure(
            text=f"{parsed.box_quantity} шт" if parsed.box_quantity is not None else "—"
        )

    # --------------------------------------------------------- ИИ-предложения
    def _run_suggestions(self) -> None:
        """Запускает ИИ-подбор для текущего системного названия."""
        self._suggest_after_id = None
        text = self.source_var.get().strip()
        if not text:
            self._render_empty_suggestions("Введите системное название, чтобы получить предложения")
            return
        try:
            candidates = self._suggest_certificates(text)
        except Exception:
            _LOGGER.exception("Ошибка ИИ-подбора для словаря")
            candidates = []
        self._render_suggestions(candidates)

    def _render_empty_suggestions(self, message: str) -> None:
        """Показывает пояснение вместо списка ИИ-предложений."""
        for child in self._suggestions.winfo_children():
            child.destroy()
        ctk.CTkLabel(
            self._suggestions,
            text=message,
            font=self._theme.font(FontRole.SMALL),
            text_color=self._theme.color("text_muted"),
            wraplength=440,
            justify="left",
        ).pack(pady=Spacing.LG, padx=Spacing.SM)

    def _render_suggestions(self, candidates: list[MatchCandidate]) -> None:
        """Отображает ИИ-предложения списком со звёздным рейтингом."""
        for child in self._suggestions.winfo_children():
            child.destroy()

        if not candidates:
            self._render_empty_suggestions("Ничего не найдено — попробуйте ручной поиск ниже")
            return

        for candidate in candidates:
            self._render_suggestion_row(candidate)

    def _render_suggestion_row(self, candidate: MatchCandidate) -> None:
        """Отображает одно ИИ-предложение с рейтингом и кнопкой выбора."""
        theme = self._theme
        certificate = candidate.certificate
        row = ctk.CTkFrame(
            self._suggestions, fg_color=theme.color("surface"), corner_radius=Radius.SM
        )
        row.pack(fill="x", padx=Spacing.XS, pady=Spacing.XS)

        score = ctk.CTkFrame(row, fg_color="transparent", width=88, height=0)
        score.pack(side="left", padx=Spacing.SM, pady=Spacing.XS)
        score.pack_propagate(False)
        ctk.CTkLabel(
            score,
            text=_star_rating(candidate.percent),
            font=theme.font(FontRole.BODY),
            text_color=theme.color(_score_color(candidate.total)),
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            score,
            text=f"{candidate.percent}%",
            font=theme.font(FontRole.CAPTION),
            text_color=theme.color("text_muted"),
            anchor="w",
        ).pack(anchor="w")

        texts = ctk.CTkFrame(row, fg_color="transparent", width=0, height=0)
        texts.pack(side="left", fill="both", expand=True, pady=Spacing.XS)
        ctk.CTkLabel(
            texts,
            text=certificate.product_name,
            font=theme.font(FontRole.SMALL),
            text_color=theme.color("text"),
            anchor="w",
            justify="left",
            wraplength=320,
        ).pack(fill="x", anchor="w")

        details = " · ".join(
            part
            for part in (
                str(certificate.volume) if certificate.volume else "",
                certificate.display_number,
            )
            if part
        )
        if details:
            ctk.CTkLabel(
                texts,
                text=details,
                font=theme.font(FontRole.CAPTION),
                text_color=theme.color("text_muted"),
                anchor="w",
            ).pack(fill="x", anchor="w")

        ghost_button(row, theme, text="Выбрать", command=self._make_select(certificate)).pack(
            side="right", padx=Spacing.SM
        )

    # ------------------------------------------------------------- ручной поиск
    def _run_search(self) -> None:
        """Ищет позиции базы сертификатов по введённому запросу."""
        query = self._search_var.get().strip()
        if not query:
            self._render_empty_results("Введите запрос и нажмите «Найти»")
            return
        try:
            results = self._search_certificates(query)
        except Exception:
            _LOGGER.exception("Ошибка поиска сертификата для словаря")
            results = []
        self._render_results(results)

    def _render_empty_results(self, message: str) -> None:
        """Показывает пояснение вместо списка результатов ручного поиска."""
        for child in self._results.winfo_children():
            child.destroy()
        ctk.CTkLabel(
            self._results,
            text=message,
            font=self._theme.font(FontRole.SMALL),
            text_color=self._theme.color("text_muted"),
        ).pack(pady=Spacing.LG)

    def _render_results(self, results: list[CertificateProduct]) -> None:
        """Отображает найденные позиции базы списком с кнопкой выбора."""
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
                wraplength=380,
            ).pack(fill="x", anchor="w")

            details = " · ".join(
                part
                for part in (
                    str(certificate.volume) if certificate.volume else "",
                    certificate.display_number,
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

    # -------------------------------------------------------------- выбор
    def _make_select(self, certificate: CertificateProduct) -> Callable[[], None]:
        """Создаёт обработчик выбора для конкретной позиции в списке.

        Именованная фабрика вместо ``lambda item=certificate: ...`` — так же,
        как и в остальном интерфейсе, это устраняет и трудности вывода типов
        у лямбды с аргументом по умолчанию, и ловушку позднего связывания
        замыкания в цикле.

        Args:
            certificate: Позиция базы, которую нужно выбрать целью соответствия.

        Returns:
            Обработчик без аргументов, пригодный для ``command=``.
        """
        return lambda: self._select_certificate(certificate)

    def _select_certificate(self, certificate: CertificateProduct) -> None:
        """Фиксирует выбранную позицию базы как цель соответствия.

        В отличие от прежней версии диалога, выбор не подсказка для полей
        ручного ввода — он и есть окончательная цель: свободного ввода
        русского названия в этом диалоге больше нет (см. класс-докстринг).

        Args:
            certificate: Выбранная позиция базы сертификатов.
        """
        self._selected_certificate = certificate
        self._render_selection_summary()

    def _render_selection_summary(self) -> None:
        """Обновляет строку с описанием текущей цели соответствия."""
        theme = self._theme
        if self._selected_certificate is not None:
            certificate = self._selected_certificate
            details = " · ".join(
                part
                for part in (
                    str(certificate.volume) if certificate.volume else "",
                    certificate.display_number,
                )
                if part
            )
            text = f"Выбрано: {certificate.product_name}"
            if details:
                text += f" ({details})"
            self._summary_label.configure(text=text, text_color=theme.color("text"))
            return

        if self._alias is not None and self._alias.target_name:
            text = f"Сейчас в словаре: {self._alias.target_name}"
            if self._alias.volume_label:
                text += f" ({self._alias.volume_label})"
            self._summary_label.configure(text=text, text_color=theme.color("text"))
            return

        self._summary_label.configure(text="Товар не выбран", text_color=theme.color("warning"))

    # -------------------------------------------------------------- отправка
    def _submit(self) -> None:
        """Проверяет форму и закрывает диалог с собранными данными."""
        source_text = self.source_var.get().strip()
        if not source_text:
            self._show_error("Укажите системное название товара")
            return

        target_name = ""
        volume_ml: float | None = None
        certificate_product_id: int | None = None
        if self._selected_certificate is not None:
            target_name = self._selected_certificate.product_name
            volume_ml = self._selected_certificate.volume_ml
            certificate_product_id = self._selected_certificate.id
        elif self._alias is not None:
            target_name = self._alias.target_name
            volume_ml = self._alias.volume_ml
            certificate_product_id = self._alias.certificate_product_id

        if not target_name:
            self._show_error(
                "Выберите товар из базы сертификатов — через ИИ-предложение или ручной поиск"
            )
            return

        self.close(
            {
                "source_text": source_text,
                "target_name": target_name,
                "certificate_product_id": certificate_product_id,
                "brand": self.brand_var.get().strip(),
                "volume_ml": volume_ml,
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


def _star_rating(percent: int) -> str:
    """Преобразует оценку совпадения в звёздный рейтинг (до пяти звёзд).

    Границы подобраны так, чтобы совпадать с примером из требований:
    99 % → пять звёзд, 93 % → четыре, 85 % → три.

    Args:
        percent: Оценка совпадения в процентах ``[0..100]``.

    Returns:
        Строка вида ``"★★★★☆"``.
    """
    if percent >= 95:
        filled = 5
    elif percent >= 90:
        filled = 4
    elif percent >= 75:
        filled = 3
    elif percent >= 60:
        filled = 2
    elif percent >= 40:
        filled = 1
    else:
        filled = 0
    return "★" * filled + "☆" * (5 - filled)


def _score_color(score: float) -> str:
    """Возвращает роль цвета темы для оценки совпадения ``[0..1]``."""
    if score >= 0.9:
        return "success"
    if score >= 0.75:
        return "accent"
    if score >= 0.6:
        return "warning"
    return "danger"


__all__ = ["AliasAuditDialog", "AliasEditDialog"]
