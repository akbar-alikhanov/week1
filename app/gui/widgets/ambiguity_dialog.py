"""Окно разрешения неоднозначного подбора.

Ключевой элемент взаимодействия: именно здесь пользователь принимает решение,
которое программа запомнит навсегда. Требования к окну:

* решение принимается одним щелчком, без чтения инструкций;
* видны все различающие признаки — наименование, объём, срок, файл;
* видно, *почему* программа предложила именно этот вариант;
* сертификат можно посмотреть, не покидая окна;
* по умолчанию выбор запоминается, но это можно отключить.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import customtkinter as ctk

from app.core.dates import format_date
from app.gui.animations import Animator
from app.gui.icons import icons
from app.gui.theme import FontRole, Radius, Spacing, Theme
from app.gui.widgets.base import bind_recursive, set_cursor
from app.gui.widgets.controls import Badge, ghost_button, primary_button, secondary_button
from app.gui.widgets.dialogs import ModalDialog
from app.models.matching import MatchCandidate, MatchResult

_LOGGER = logging.getLogger(__name__)

#: Результат «пропустить строку».
SKIP = -1


class CandidateRow(ctk.CTkFrame):
    """Строка одного кандидата в окне выбора."""

    def __init__(
        self,
        master: Any,
        theme: Theme,
        *,
        candidate: MatchCandidate,
        index: int,
        on_choose: Callable[[int], None],
        on_preview: Callable[[Path], None] | None = None,
        animator: Animator | None = None,
        recommended: bool = False,
        **kwargs: Any,
    ) -> None:
        """Создаёт строку кандидата.

        Args:
            master: Родительский виджет.
            theme: Активная тема оформления.
            candidate: Кандидат.
            index: Порядковый номер (для горячих клавиш 1…9).
            on_choose: Обработчик выбора.
            on_preview: Обработчик просмотра PDF.
            animator: Менеджер анимаций.
            recommended: Признак рекомендованного варианта.
            **kwargs: Дополнительные параметры ``CTkFrame``.
        """
        self._theme = theme
        self._animator = animator
        self._on_choose = on_choose
        self._index = index
        self._hovered = False

        super().__init__(
            master,
            fg_color=theme.color("surface"),
            corner_radius=Radius.MD,
            border_width=2 if recommended else 1,
            border_color=theme.color("accent" if recommended else "border"),
            **kwargs,
        )

        certificate = candidate.certificate
        body = ctk.CTkFrame(self, fg_color="transparent", width=0, height=0)
        body.pack(fill="both", expand=True, padx=Spacing.MD, pady=Spacing.MD)

        # --- Левая колонка: оценка ------------------------------------------
        score_box = ctk.CTkFrame(
            body,
            fg_color=theme.color(_score_background(candidate.total)),
            corner_radius=Radius.MD,
            width=76,
        )
        score_box.pack(side="left", fill="y", padx=(0, Spacing.MD))
        score_box.pack_propagate(False)

        ctk.CTkLabel(
            score_box,
            text=f"{candidate.percent}%",
            font=theme.font(FontRole.HEADING),
            text_color=theme.color(_score_color(candidate.total)),
        ).pack(expand=True, pady=(Spacing.SM, 0))

        ctk.CTkLabel(
            score_box,
            text=f"клавиша {index + 1}" if index < 9 else "",
            font=theme.font(FontRole.CAPTION),
            text_color=theme.color("text_muted"),
        ).pack(pady=(0, Spacing.XS))

        # --- Центральная колонка: описание ----------------------------------
        details = ctk.CTkFrame(body, fg_color="transparent", width=0, height=0)
        details.pack(side="left", fill="both", expand=True)

        title_row = ctk.CTkFrame(details, fg_color="transparent", width=0, height=0)
        title_row.pack(fill="x")

        ctk.CTkLabel(
            title_row,
            text=certificate.product_name,
            font=theme.font(FontRole.SUBHEADING),
            text_color=theme.color("text"),
            anchor="w",
            justify="left",
            wraplength=420,
        ).pack(side="left", fill="x", expand=True)

        if recommended:
            Badge(title_row, theme, text="рекомендуется", role="accent").pack(
                side="right", padx=(Spacing.SM, 0)
            )

        meta = ctk.CTkFrame(details, fg_color="transparent", width=0, height=0)
        meta.pack(fill="x", pady=(Spacing.XS, 0))

        expiry_role = "danger" if certificate.is_expired else "text_muted"
        for icon_name, text, role in (
            ("certificate", certificate.display_number or "номер не распознан", "text_muted"),
            ("history", f"до {format_date(certificate.expiry_date)}", expiry_role),
            (
                "chart",
                str(certificate.volume) if certificate.volume else "объём не указан",
                "text_muted",
            ),
        ):
            chip = ctk.CTkFrame(meta, fg_color="transparent", width=0, height=0)
            chip.pack(side="left", padx=(0, Spacing.MD))
            ctk.CTkLabel(
                chip, text="", image=icons.colored(icon_name, theme, role, 14), width=16
            ).pack(side="left", padx=(0, 4))
            ctk.CTkLabel(
                chip,
                text=text,
                font=theme.font(FontRole.CAPTION),
                text_color=theme.color(role),
            ).pack(side="left")

        ctk.CTkLabel(
            details,
            text=(
                f"{candidate.score.explain()}  ·  {candidate.source.label}  ·  "
                f"{certificate.pdf_name}"
            ),
            font=theme.font(FontRole.CAPTION),
            text_color=theme.color("text_muted"),
            anchor="w",
            justify="left",
            wraplength=520,
        ).pack(fill="x", anchor="w", pady=(Spacing.XS, 0))

        # --- Правая колонка: действия ---------------------------------------
        actions = ctk.CTkFrame(body, fg_color="transparent", width=0, height=0)
        actions.pack(side="right", padx=(Spacing.MD, 0))

        primary_button(
            actions,
            theme,
            text="Выбрать",
            command=lambda: on_choose(index),
            height=32,
            width=104,
        ).pack()

        if on_preview is not None and certificate.path.exists():
            ghost_button(
                actions,
                theme,
                text="Просмотр",
                icon="eye",
                command=lambda: on_preview(certificate.path),
                height=28,
            ).pack(pady=(Spacing.XS, 0))

        self.after(40, self._enable_interaction)

    def _enable_interaction(self) -> None:
        """Включает подсветку и выбор по щелчку на строке."""
        set_cursor(self, "hand2")
        bind_recursive(self, "<Enter>", lambda _: self._set_hover(True))
        bind_recursive(self, "<Leave>", lambda _: self._set_hover(False))

    def _set_hover(self, value: bool) -> None:
        """Меняет подсветку строки."""
        if value == self._hovered:
            return
        self._hovered = value
        try:
            self.configure(fg_color=self._theme.color("surface_hover" if value else "surface"))
        except Exception:
            pass


class AmbiguityDialog(ModalDialog):
    """Окно выбора сертификата из нескольких вариантов."""

    def __init__(
        self,
        master: Any,
        theme: Theme,
        *,
        result: MatchResult,
        animator: Animator | None = None,
        on_preview: Callable[[Path], None] | None = None,
        on_search: Callable[[str], list[MatchCandidate]] | None = None,
        remaining: int = 0,
    ) -> None:
        """Создаёт окно неоднозначного выбора.

        Args:
            master: Родительское окно.
            theme: Активная тема оформления.
            result: Результат подбора с несколькими кандидатами.
            animator: Менеджер анимаций.
            on_preview: Обработчик просмотра PDF.
            on_search: Функция поиска по произвольному запросу.
            remaining: Сколько позиций ещё предстоит разобрать.
        """
        super().__init__(
            master, theme, title="Выбор сертификата", width=940, height=680, resizable=True
        )
        self._result_row = result
        self._animator = animator
        self._on_preview = on_preview
        self._on_search = on_search
        self._candidates: list[MatchCandidate] = list(result.candidates)
        self.remember = ctk.BooleanVar(value=True)
        self.apply_to_all = ctk.BooleanVar(value=False)
        self._result = None

        self._build_header(remaining)
        self._build_footer()
        self._list = ctk.CTkScrollableFrame(self.container, fg_color="transparent", corner_radius=0)
        self._list.pack(fill="both", expand=True, pady=(Spacing.MD, 0))
        self._render_candidates()
        self._bind_shortcuts()

    # ------------------------------------------------------------- разметка
    def _build_header(self, remaining: int) -> None:
        """Строит шапку окна с наименованием из заказа."""
        theme = self._theme
        header = ctk.CTkFrame(
            self.container, fg_color=theme.color("surface"), corner_radius=Radius.MD
        )
        header.pack(fill="x")

        inner = ctk.CTkFrame(header, fg_color="transparent", width=0, height=0)
        inner.pack(fill="x", padx=Spacing.LG, pady=Spacing.MD)

        top = ctk.CTkFrame(inner, fg_color="transparent", width=0, height=0)
        top.pack(fill="x")

        ctk.CTkLabel(
            top,
            text="ПОЗИЦИЯ ЗАКАЗА",
            font=theme.font(FontRole.CAPTION),
            text_color=theme.color("text_muted"),
            anchor="w",
        ).pack(side="left")

        if remaining > 0:
            Badge(top, theme, text=f"осталось разобрать: {remaining}", role="warning").pack(
                side="right"
            )

        ctk.CTkLabel(
            inner,
            text=self._result_row.row.product_name,
            font=theme.font(FontRole.TITLE),
            text_color=theme.color("text"),
            anchor="w",
            justify="left",
            wraplength=820,
        ).pack(fill="x", anchor="w", pady=(Spacing.XS, 0))

        facts = ctk.CTkFrame(inner, fg_color="transparent", width=0, height=0)
        facts.pack(fill="x", pady=(Spacing.SM, 0))

        row = self._result_row.row
        details = [f"строка {row.row_number}"]
        if row.volume:
            details.append(f"объём {row.volume}")
        if row.quantity:
            details.append(f"количество {row.quantity:g}")
        if row.requested_expiry:
            details.append(f"требуемый срок {format_date(row.requested_expiry)}")
        if self._result_row.note:
            details.append(self._result_row.note)

        ctk.CTkLabel(
            facts,
            text="  ·  ".join(details),
            font=theme.font(FontRole.SMALL),
            text_color=theme.color("text_muted"),
            anchor="w",
            justify="left",
            wraplength=820,
        ).pack(fill="x", anchor="w")

        if self._on_search is not None:
            search_row = ctk.CTkFrame(inner, fg_color="transparent", width=0, height=0)
            search_row.pack(fill="x", pady=(Spacing.MD, 0))

            self._search_variable = ctk.StringVar(value=row.product_name)
            entry = ctk.CTkEntry(
                search_row,
                textvariable=self._search_variable,
                height=34,
                font=theme.font(FontRole.BODY),
                fg_color=theme.color("surface_alt"),
                border_color=theme.color("border"),
                placeholder_text="Уточните запрос и нажмите «Найти»",
            )
            entry.pack(side="left", fill="x", expand=True)
            entry.bind("<Return>", lambda _: self._run_search())

            secondary_button(
                search_row, theme, text="Найти", command=self._run_search, icon="search", height=34
            ).pack(side="left", padx=(Spacing.SM, 0))

    def _build_footer(self) -> None:
        """Строит нижнюю панель с флагами и кнопками."""
        theme = self._theme
        footer = ctk.CTkFrame(self.container, fg_color="transparent", width=0, height=0)
        footer.pack(fill="x", side="bottom", pady=(Spacing.MD, 0))

        options = ctk.CTkFrame(footer, fg_color="transparent", width=0, height=0)
        options.pack(side="left", fill="x", expand=True)

        ctk.CTkCheckBox(
            options,
            text="Запомнить выбор (создать псевдоним)",
            variable=self.remember,
            font=theme.font(FontRole.SMALL),
            text_color=theme.color("text"),
            fg_color=theme.color("accent"),
            hover_color=theme.color("accent_hover"),
            checkbox_width=18,
            checkbox_height=18,
            corner_radius=Radius.SM,
        ).pack(anchor="w")

        ctk.CTkLabel(
            options,
            text="При следующей обработке такой товар будет подобран мгновенно",
            font=theme.font(FontRole.CAPTION),
            text_color=theme.color("text_muted"),
            anchor="w",
        ).pack(anchor="w", padx=(26, 0))

        buttons = ctk.CTkFrame(footer, fg_color="transparent", width=0, height=0)
        buttons.pack(side="right")

        ghost_button(
            buttons,
            theme,
            text="Прекратить разбор",
            command=lambda: self.close("stop"),
        ).pack(side="right")

        secondary_button(
            buttons,
            theme,
            text="Пропустить позицию",
            command=lambda: self.close(SKIP),
        ).pack(side="right", padx=(0, Spacing.SM))

    def _render_candidates(self) -> None:
        """Отрисовывает список кандидатов."""
        for child in self._list.winfo_children():
            child.destroy()

        if not self._candidates:
            ctk.CTkLabel(
                self._list,
                text="Подходящих сертификатов не найдено.\nУточните запрос или пропустите позицию.",
                font=self._theme.font(FontRole.BODY),
                text_color=self._theme.color("text_muted"),
                justify="center",
            ).pack(pady=Spacing.XXL)
            return

        for index, candidate in enumerate(self._candidates):
            CandidateRow(
                self._list,
                self._theme,
                candidate=candidate,
                index=index,
                on_choose=self._choose,
                on_preview=self._on_preview,
                animator=self._animator,
                recommended=index == 0,
            ).pack(fill="x", pady=(0, Spacing.SM))

    def _bind_shortcuts(self) -> None:
        """Привязывает выбор кандидата к цифровым клавишам."""
        for number in range(1, 10):
            self.bind(str(number), lambda _, value=number: self._choose(value - 1))
        self.bind("<Return>", lambda _: self._choose(0))

    # -------------------------------------------------------------- действия
    def _choose(self, index: int) -> None:
        """Фиксирует выбор кандидата."""
        if not 0 <= index < len(self._candidates):
            return
        # Кандидаты могли быть заменены результатом уточняющего поиска,
        # поэтому список результата синхронизируется с показанным.
        self._result_row.candidates = self._candidates
        self.close(index)

    def _run_search(self) -> None:
        """Выполняет уточняющий поиск по введённому запросу."""
        if self._on_search is None:
            return
        query = self._search_variable.get().strip()
        if not query:
            return
        try:
            self._candidates = self._on_search(query)
        except Exception:
            _LOGGER.exception("Ошибка уточняющего поиска")
            return
        self._render_candidates()


def _score_color(score: float) -> str:
    """Возвращает роль цвета для оценки совпадения."""
    if score >= 0.9:
        return "success"
    if score >= 0.75:
        return "accent"
    if score >= 0.6:
        return "warning"
    return "danger"


def _score_background(score: float) -> str:
    """Возвращает роль цвета подложки для оценки совпадения."""
    if score >= 0.9:
        return "success_soft"
    if score >= 0.75:
        return "accent_soft"
    if score >= 0.6:
        return "warning_soft"
    return "danger_soft"
