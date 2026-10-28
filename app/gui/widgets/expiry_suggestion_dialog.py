"""Окно ручного подтверждения сертификата по сроку годности (Этап 3).

Показывается ТОЛЬКО когда строгий автоматический поиск (Этап 1 — допуск
``expiry_tolerance_days``) не подтвердил сертификат ни для одной партии
товара. Ничего из показанного здесь не используется автоматически: пока
пользователь не нажал «Выбрать» для конкретного варианта и не завершил
разбор строки кнопкой «Готово», ни один сертификат не считается выбранным.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from app.core.dates import format_date
from app.gui.animations import Animator
from app.gui.theme import FontRole, Radius, Spacing, Theme
from app.gui.widgets.controls import Badge, ghost_button, primary_button, secondary_button
from app.gui.widgets.dialogs import ModalDialog
from app.services.expiry_resolution_service import (
    BatchSuggestions,
    ExpirySuggestion,
    ManualExpiryReview,
)

_LOGGER = logging.getLogger(__name__)


class _SuggestionRow(ctk.CTkFrame):
    """Строка одного варианта сертификата — «зелёный/жёлтый/красный» по расхождению."""

    def __init__(
        self,
        master: Any,
        theme: Theme,
        *,
        suggestion: ExpirySuggestion,
        tolerance_days: int,
        selected: bool,
        on_choose: Callable[[], None],
        on_clear: Callable[[], None],
        **kwargs: Any,
    ) -> None:
        """Создаёт строку варианта.

        Args:
            master: Родительский виджет.
            theme: Активная тема оформления.
            suggestion: Предложенный вариант сертификата.
            tolerance_days: Допуск по сроку — для цветовой метки расхождения.
            selected: Подтверждён ли этот вариант для партии сейчас.
            on_choose: Обработчик подтверждения (не закрывает диалог).
            on_clear: Обработчик отмены подтверждения этого варианта.
            **kwargs: Дополнительные параметры ``CTkFrame``.
        """
        super().__init__(
            master,
            fg_color=theme.color("surface"),
            corner_radius=Radius.MD,
            border_width=2 if selected else 1,
            border_color=theme.color("accent" if selected else "border"),
            **kwargs,
        )
        certificate = suggestion.certificate
        body = ctk.CTkFrame(self, fg_color="transparent", width=0, height=0)
        body.pack(fill="both", expand=True, padx=Spacing.MD, pady=Spacing.SM)

        role = _difference_role(suggestion.difference_days, tolerance_days)
        box = ctk.CTkFrame(
            body, fg_color=theme.color(f"{role}_soft"), corner_radius=Radius.MD, width=84
        )
        box.pack(side="left", fill="y", padx=(0, Spacing.MD))
        box.pack_propagate(False)
        ctk.CTkLabel(
            box,
            text=f"{suggestion.difference_days} дн.",
            font=theme.font(FontRole.BODY_STRONG),
            text_color=theme.color(role),
        ).pack(expand=True, pady=(Spacing.SM, 0))
        ctk.CTkLabel(
            box,
            text=_difference_caption(role),
            font=theme.font(FontRole.CAPTION),
            text_color=theme.color(role),
            wraplength=72,
            justify="center",
        ).pack(pady=(0, Spacing.XS))

        details = ctk.CTkFrame(body, fg_color="transparent", width=0, height=0)
        details.pack(side="left", fill="both", expand=True)
        ctk.CTkLabel(
            details,
            text=certificate.display_number or "номер не распознан",
            font=theme.font(FontRole.SUBHEADING),
            text_color=theme.color("text"),
            anchor="w",
        ).pack(fill="x", anchor="w")
        ctk.CTkLabel(
            details,
            text=f"Срок сертификата: {format_date(certificate.expiry_date)}",
            font=theme.font(FontRole.CAPTION),
            text_color=theme.color("text_muted"),
            anchor="w",
        ).pack(fill="x", anchor="w", pady=(2, 0))

        actions = ctk.CTkFrame(body, fg_color="transparent", width=0, height=0)
        actions.pack(side="right")
        if selected:
            Badge(actions, theme, text="Выбрано", role="success").pack()
            ghost_button(actions, theme, text="Отменить", command=on_clear, height=26).pack(
                pady=(Spacing.XS, 0)
            )
        else:
            primary_button(
                actions, theme, text="Выбрать", command=on_choose, height=32, width=104
            ).pack()


class _BatchSection(ctk.CTkFrame):
    """Раздел одной партии с её вариантами (или пояснением, что вариантов нет)."""

    def __init__(
        self,
        master: Any,
        theme: Theme,
        *,
        batch: BatchSuggestions,
        tolerance_days: int,
        selected: ExpirySuggestion | None,
        on_choose: Callable[[ExpirySuggestion], None],
        on_clear: Callable[[], None],
        **kwargs: Any,
    ) -> None:
        """Создаёт раздел партии.

        Args:
            master: Родительский виджет.
            theme: Активная тема оформления.
            batch: Партия с предложенными вариантами.
            tolerance_days: Допуск по сроку — для цветовой метки расхождения.
            selected: Подтверждённый для этой партии вариант, если есть.
            on_choose: Обработчик подтверждения варианта.
            on_clear: Обработчик отмены подтверждения.
            **kwargs: Дополнительные параметры ``CTkFrame``.
        """
        super().__init__(
            master, fg_color=theme.color("surface_alt"), corner_radius=Radius.MD, **kwargs
        )

        header = ctk.CTkFrame(self, fg_color="transparent", width=0, height=0)
        header.pack(fill="x", padx=Spacing.MD, pady=(Spacing.SM, 0))
        ctk.CTkLabel(
            header,
            text=(
                f"Партия: {format_date(batch.entry.expiry_date)} · "
                f"остаток {_format_quantity(batch.entry.quantity)}"
            ),
            font=theme.font(FontRole.SUBHEADING),
            text_color=theme.color("text"),
            anchor="w",
        ).pack(side="left")
        if selected is not None:
            Badge(header, theme, text="партия подтверждена", role="success").pack(side="right")

        body = ctk.CTkFrame(self, fg_color="transparent", width=0, height=0)
        body.pack(fill="x", padx=Spacing.MD, pady=(Spacing.SM, Spacing.MD))

        if not batch.suggestions:
            ctk.CTkLabel(
                body,
                text="Сертификатов для этого товара и объёма не найдено.",
                font=theme.font(FontRole.CAPTION),
                text_color=theme.color("text_muted"),
                anchor="w",
            ).pack(fill="x", anchor="w")
            return

        for suggestion in batch.suggestions:
            _SuggestionRow(
                body,
                theme,
                suggestion=suggestion,
                tolerance_days=tolerance_days,
                selected=selected is suggestion,
                on_choose=_bind_choice(on_choose, suggestion),
                on_clear=on_clear,
            ).pack(fill="x", pady=(0, Spacing.SM))


class ExpirySuggestionDialog(ModalDialog):
    """Окно ручного подтверждения сертификата для партий срока годности.

    Один диалог на строку заказа: разделы по всем проверенным партиям сразу
    (см. :class:`~app.services.expiry_resolution_service.ManualExpiryReview`),
    а не по одной партии за раз — иначе пользователь не увидел бы, сколько
    в сумме удастся набрать до того, как закроет окно.
    """

    def __init__(
        self,
        master: Any,
        theme: Theme,
        *,
        review: ManualExpiryReview,
        tolerance_days: int,
        animator: Animator | None = None,
        remaining: int = 0,
    ) -> None:
        """Создаёт окно ручного подтверждения.

        Args:
            master: Родительское окно.
            theme: Активная тема оформления.
            review: Обзор партий с предложенными вариантами.
            tolerance_days: Допуск по сроку — для цветовой метки расхождения
                (только оформление, на бизнес-логику не влияет).
            animator: Менеджер анимаций (зарезервировано, как и в остальных
                диалогах подбора).
            remaining: Сколько позиций ещё предстоит разобрать.
        """
        super().__init__(
            master,
            theme,
            title="Подтверждение сертификата по сроку",
            width=980,
            height=720,
            resizable=True,
        )
        self._review = review
        self._tolerance_days = tolerance_days
        self._animator = animator
        self._choices: dict[int, ExpirySuggestion] = {}

        self._build_header(remaining)
        self._build_footer()
        self._list = ctk.CTkScrollableFrame(self.container, fg_color="transparent", corner_radius=0)
        self._list.pack(fill="both", expand=True, pady=(Spacing.MD, 0))
        self._render_batches()

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
            text="СТРОГИЙ ПОИСК НЕ НАШЁЛ СЕРТИФИКАТ НИ ДЛЯ ОДНОЙ ПАРТИИ",
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
            text=self._review.row.product_name,
            font=theme.font(FontRole.TITLE),
            text_color=theme.color("text"),
            anchor="w",
            justify="left",
            wraplength=860,
        ).pack(fill="x", anchor="w", pady=(Spacing.XS, 0))

        details = [
            f"строка {self._review.row.row_number}",
            f"требуется {_format_quantity(self._review.required_quantity)} шт.",
            f"допуск по сроку ±{self._tolerance_days} дн.",
        ]
        ctk.CTkLabel(
            inner,
            text="  ·  ".join(details),
            font=theme.font(FontRole.SMALL),
            text_color=theme.color("text_muted"),
            anchor="w",
        ).pack(fill="x", anchor="w", pady=(Spacing.SM, 0))

    def _build_footer(self) -> None:
        """Строит нижнюю панель со сводкой и кнопками."""
        theme = self._theme
        footer = ctk.CTkFrame(self.container, fg_color="transparent", width=0, height=0)
        footer.pack(fill="x", side="bottom", pady=(Spacing.MD, 0))

        self._summary_label = ctk.CTkLabel(
            footer,
            text="",
            font=theme.font(FontRole.SMALL),
            text_color=theme.color("text_muted"),
            anchor="w",
            justify="left",
        )
        self._summary_label.pack(side="left", fill="x", expand=True)
        self._update_summary()

        buttons = ctk.CTkFrame(footer, fg_color="transparent", width=0, height=0)
        buttons.pack(side="right")

        ghost_button(
            buttons, theme, text="Прекратить разбор", command=lambda: self.close("stop")
        ).pack(side="right")

        secondary_button(
            buttons, theme, text="Пропустить позицию", command=lambda: self.close({})
        ).pack(side="right", padx=(0, Spacing.SM))

        primary_button(
            buttons, theme, text="Готово", command=lambda: self.close(dict(self._choices))
        ).pack(side="right", padx=(0, Spacing.SM))

    def _render_batches(self) -> None:
        """Отрисовывает разделы всех партий по текущему состоянию выбора."""
        for child in self._list.winfo_children():
            child.destroy()

        for index, batch in enumerate(self._review.batches):
            _BatchSection(
                self._list,
                self._theme,
                batch=batch,
                tolerance_days=self._tolerance_days,
                selected=self._choices.get(index),
                on_choose=self._make_choose(index),
                on_clear=self._make_clear(index),
            ).pack(fill="x", pady=(0, Spacing.SM))

    def _update_summary(self) -> None:
        """Обновляет сводку подтверждённого количества в футере."""
        confirmed = len(self._choices)
        total = len(self._review.batches)
        available = sum(self._review.batches[index].entry.quantity for index in self._choices)
        required = self._review.required_quantity
        is_enough = available >= required
        enough = "хватает" if is_enough else "не хватает"
        self._summary_label.configure(
            text=(
                f"Подтверждено партий: {confirmed} из {total}  ·  "
                f"доступно {_format_quantity(available)} из "
                f"{_format_quantity(required)} шт. ({enough})"
            ),
            text_color=self._theme.color("success" if is_enough else "warning"),
        )

    # -------------------------------------------------------------- действия
    def _choose(self, batch_index: int, suggestion: ExpirySuggestion) -> None:
        """Подтверждает вариант для партии — не закрывает диалог."""
        self._choices[batch_index] = suggestion
        self._render_batches()
        self._update_summary()

    def _clear(self, batch_index: int) -> None:
        """Отменяет подтверждение варианта для партии."""
        self._choices.pop(batch_index, None)
        self._render_batches()
        self._update_summary()

    def _make_choose(self, batch_index: int) -> Callable[[ExpirySuggestion], None]:
        """Создаёт обработчик подтверждения варианта для конкретной партии.

        Именованная фабрика вместо ``lambda i=batch_index: ...`` — устраняет
        и трудности вывода типов у лямбды с аргументом по умолчанию, и
        ловушку позднего связывания замыкания в цикле (см. тот же приём в
        ``AliasEditDialog._make_select``).
        """
        return lambda suggestion: self._choose(batch_index, suggestion)

    def _make_clear(self, batch_index: int) -> Callable[[], None]:
        """Создаёт обработчик отмены подтверждения для конкретной партии."""
        return lambda: self._clear(batch_index)


def _bind_choice(
    on_choose: Callable[[ExpirySuggestion], None], suggestion: ExpirySuggestion
) -> Callable[[], None]:
    """Возвращает обработчик без аргументов, привязанный к конкретному варианту.

    Именованная функция вместо ``lambda s=suggestion: on_choose(s)`` — по
    той же причине, что и ``ExpirySuggestionDialog._make_choose``.
    """
    return lambda: on_choose(suggestion)


def _difference_role(difference_days: int, tolerance_days: int) -> str:
    """Определяет цветовую роль расхождения в днях относительно допуска.

    Только оформление интерфейса (🟢/🟡/🔴 из требования) — сам вариант
    доступен для выбора независимо от этой метки, бизнес-логику она не
    меняет.

    Args:
        difference_days: Расхождение в днях.
        tolerance_days: Допуск по сроку.

    Returns:
        ``"success"``, ``"warning"`` или ``"danger"``.
    """
    window = max(1, tolerance_days)
    if difference_days <= window:
        return "success"
    if difference_days <= window * 3:
        return "warning"
    return "danger"


def _difference_caption(role: str) -> str:
    """Возвращает подпись под расхождением по цветовой роли."""
    return {"success": "в допуске", "warning": "больше допуска", "danger": "значительно больше"}[
        role
    ]


def _format_quantity(value: float) -> str:
    """Форматирует количество без лишних нулей после запятой."""
    return f"{value:g}"
