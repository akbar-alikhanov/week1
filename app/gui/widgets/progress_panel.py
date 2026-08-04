"""Панель хода выполнения длительной операции."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from app.core.events import ProgressUpdate
from app.gui.animations import DURATION_FAST, Animator
from app.gui.theme import FontRole, Radius, Spacing, Theme
from app.gui.widgets.base import format_duration
from app.gui.widgets.controls import ghost_button


class ProgressPanel(ctk.CTkFrame):
    """Отображает прогресс, текущий шаг и оценку оставшегося времени.

    Значение полосы анимируется, а не выставляется скачком: при пакетной
    обработке прогресс приходит порциями, и без сглаживания полоса дёргалась
    бы, создавая ощущение нестабильной работы.
    """

    def __init__(
        self,
        master: Any,
        theme: Theme,
        animator: Animator,
        *,
        on_cancel: Callable[[], None] | None = None,
        **kwargs: Any,
    ) -> None:
        """Создаёт панель прогресса.

        Args:
            master: Родительский виджет.
            theme: Активная тема оформления.
            animator: Менеджер анимаций.
            on_cancel: Обработчик кнопки отмены; ``None`` — кнопка скрыта.
            **kwargs: Дополнительные параметры ``CTkFrame``.
        """
        self._theme = theme
        self._animator = animator
        self._value = 0.0

        super().__init__(
            master,
            fg_color=theme.color("surface_alt"),
            corner_radius=Radius.MD,
            **kwargs,
        )

        header = ctk.CTkFrame(self, fg_color="transparent", width=0, height=0)
        header.pack(fill="x", padx=Spacing.LG, pady=(Spacing.MD, Spacing.XS))

        self._stage_label = ctk.CTkLabel(
            header,
            text="Готово к работе",
            font=theme.font(FontRole.BODY_STRONG),
            text_color=theme.color("text"),
            anchor="w",
        )
        self._stage_label.pack(side="left", fill="x", expand=True)

        self._percent_label = ctk.CTkLabel(
            header,
            text="",
            font=theme.font(FontRole.BODY_STRONG),
            text_color=theme.color("accent"),
        )
        self._percent_label.pack(side="right", padx=(Spacing.SM, 0))

        self._bar = ctk.CTkProgressBar(
            self,
            height=8,
            corner_radius=Radius.PILL,
            fg_color=theme.color("surface_hover"),
            progress_color=theme.color("accent"),
        )
        self._bar.set(0.0)
        self._bar.pack(fill="x", padx=Spacing.LG)

        footer = ctk.CTkFrame(self, fg_color="transparent", width=0, height=0)
        footer.pack(fill="x", padx=Spacing.LG, pady=(Spacing.XS, Spacing.MD))

        self._detail_label = ctk.CTkLabel(
            footer,
            text="",
            font=theme.font(FontRole.CAPTION),
            text_color=theme.color("text_muted"),
            anchor="w",
        )
        self._detail_label.pack(side="left", fill="x", expand=True)

        self._cancel_button: ctk.CTkButton | None = None
        if on_cancel is not None:
            self._cancel_button = ghost_button(
                footer, theme, text="Отменить", command=on_cancel, icon="close", height=26
            )

    # ---------------------------------------------------------------- API
    def start(self, message: str = "Выполняется…", *, indeterminate: bool = False) -> None:
        """Переводит панель в состояние выполнения.

        Args:
            message: Название текущей операции.
            indeterminate: Использовать ли бесконечную анимацию (когда объём
                работы неизвестен).
        """
        self._stage_label.configure(text=message)
        self._detail_label.configure(text="")
        self._percent_label.configure(text="")
        self._value = 0.0

        if indeterminate:
            self._bar.configure(mode="indeterminate")
            self._bar.start()
        else:
            self._bar.configure(mode="determinate")
            self._bar.set(0.0)

        if self._cancel_button is not None:
            self._cancel_button.pack(side="right")

    def update(self, progress: ProgressUpdate) -> None:
        """Применяет обновление прогресса.

        Args:
            progress: Снимок хода выполнения.
        """
        if progress.message:
            self._stage_label.configure(text=progress.message)

        if progress.total > 0:
            self._percent_label.configure(text=f"{progress.percent} %")
            self._animate_to(progress.fraction)
            details = [f"{progress.current} из {progress.total}"]
            eta = progress.eta_seconds
            if eta is not None and eta > 1:
                details.append(f"осталось ≈ {format_duration(eta)}")
            if progress.elapsed > 1:
                details.append(f"прошло {format_duration(progress.elapsed)}")
            self._detail_label.configure(text="  ·  ".join(details))

    def finish(self, message: str = "Готово", *, success: bool = True) -> None:
        """Переводит панель в завершённое состояние.

        Args:
            message: Итоговое сообщение.
            success: Успешно ли завершилась операция.
        """
        try:
            self._bar.stop()
            self._bar.configure(mode="determinate")
        except Exception:
            pass

        self._animate_to(1.0 if success else self._value)
        self._stage_label.configure(text=message)
        self._percent_label.configure(
            text="100 %" if success else "",
            text_color=self._theme.color("success" if success else "danger"),
        )
        self._bar.configure(progress_color=self._theme.color("success" if success else "danger"))
        if self._cancel_button is not None:
            self._cancel_button.pack_forget()

    def reset(self, message: str = "Готово к работе") -> None:
        """Возвращает панель в исходное состояние.

        Args:
            message: Текст в состоянии покоя.
        """
        try:
            self._bar.stop()
            self._bar.configure(mode="determinate", progress_color=self._theme.color("accent"))
            self._bar.set(0.0)
        except Exception:
            pass
        self._value = 0.0
        self._stage_label.configure(text=message)
        self._percent_label.configure(text="", text_color=self._theme.color("accent"))
        self._detail_label.configure(text="")
        if self._cancel_button is not None:
            self._cancel_button.pack_forget()

    def _animate_to(self, value: float) -> None:
        """Плавно переводит полосу к новому значению."""
        target = max(0.0, min(1.0, value))
        start = self._value
        self._value = target

        def _apply(current: float) -> None:
            try:
                self._bar.set(current)
            except Exception:
                pass

        self._animator.animate(
            self,
            f"progress-{id(self)}",
            start=start,
            end=target,
            duration=DURATION_FAST,
            on_frame=_apply,
        )

    def refresh_theme(self) -> None:
        """Обновляет цвета после смены темы."""
        try:
            self.configure(fg_color=self._theme.color("surface_alt"))
            self._bar.configure(
                fg_color=self._theme.color("surface_hover"),
                progress_color=self._theme.color("accent"),
            )
            self._stage_label.configure(text_color=self._theme.color("text"))
            self._detail_label.configure(text_color=self._theme.color("text_muted"))
        except Exception:
            pass
