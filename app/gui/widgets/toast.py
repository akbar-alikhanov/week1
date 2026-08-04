"""Всплывающие уведомления.

Уведомления появляются в правом нижнем углу окна, живут несколько секунд и
исчезают. Они не блокируют работу, поэтому подходят для сообщений об успешном
завершении. Для сообщений, требующих решения, используются модальные диалоги.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Final

import customtkinter as ctk

from app.gui.animations import DURATION_NORMAL, Animator, ease_out_cubic
from app.gui.icons import icons
from app.gui.theme import FontRole, Radius, Spacing, Theme
from app.gui.widgets.base import safe_destroy

_LOGGER = logging.getLogger(__name__)

#: Соответствие «уровень → (иконка, роль цвета, роль подложки)».
_LEVELS: Final[dict[str, tuple[str, str, str]]] = {
    "success": ("check", "success", "success_soft"),
    "warning": ("alert", "warning", "warning_soft"),
    "error": ("alert", "danger", "danger_soft"),
    "info": ("info", "info", "accent_soft"),
}

#: Максимальное число одновременно видимых уведомлений.
_MAX_VISIBLE: Final[int] = 4


class Toast(ctk.CTkFrame):
    """Одно всплывающее уведомление."""

    def __init__(
        self,
        master: Any,
        theme: Theme,
        *,
        message: str,
        level: str = "info",
        title: str = "",
        action_text: str = "",
        on_action: Callable[[], None] | None = None,
        on_close: Callable[[Toast], None] | None = None,
        **kwargs: Any,
    ) -> None:
        """Создаёт уведомление.

        Args:
            master: Родительский виджет (слой уведомлений).
            theme: Активная тема оформления.
            message: Текст сообщения.
            level: ``success``, ``warning``, ``error`` или ``info``.
            title: Заголовок (необязателен).
            action_text: Надпись кнопки действия.
            on_action: Обработчик кнопки действия.
            on_close: Обработчик закрытия.
            **kwargs: Дополнительные параметры ``CTkFrame``.
        """
        icon_name, color_role, background_role = _LEVELS.get(level, _LEVELS["info"])
        self._theme = theme
        self._on_close = on_close

        super().__init__(
            master,
            fg_color=theme.color("surface"),
            corner_radius=Radius.MD,
            border_width=1,
            border_color=theme.color("border"),
            **kwargs,
        )

        accent_strip = ctk.CTkFrame(
            self, fg_color=theme.color(color_role), corner_radius=Radius.SM, width=4
        )
        accent_strip.pack(side="left", fill="y", padx=(4, 0), pady=4)

        content = ctk.CTkFrame(self, fg_color="transparent", width=0, height=0)
        content.pack(side="left", fill="both", expand=True, padx=Spacing.MD, pady=Spacing.MD)

        header = ctk.CTkFrame(content, fg_color="transparent", width=0, height=0)
        header.pack(fill="x")

        ctk.CTkLabel(
            header,
            text="",
            image=icons.colored(icon_name, theme, color_role, 18),
            width=22,
        ).pack(side="left", padx=(0, Spacing.SM))

        ctk.CTkLabel(
            header,
            text=title
            or {"success": "Готово", "warning": "Внимание", "error": "Ошибка"}.get(
                level, "Сообщение"
            ),
            font=theme.font(FontRole.BODY_STRONG),
            text_color=theme.color("text"),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            header,
            text="",
            image=icons.colored("close", theme, "text_muted", 14),
            width=22,
            height=22,
            corner_radius=Radius.SM,
            fg_color="transparent",
            hover_color=theme.color("surface_hover"),
            command=self.close,
        ).pack(side="right")

        ctk.CTkLabel(
            content,
            text=message,
            font=theme.font(FontRole.SMALL),
            text_color=theme.color("text_muted"),
            anchor="w",
            justify="left",
            wraplength=300,
        ).pack(fill="x", anchor="w", pady=(Spacing.XS, 0))

        if action_text and on_action is not None:
            action_callback = on_action

            def _run_action() -> None:
                action_callback()
                self.close()

            ctk.CTkButton(
                content,
                text=action_text,
                command=_run_action,
                height=28,
                corner_radius=Radius.SM,
                font=theme.font(FontRole.SMALL),
                fg_color=theme.color(background_role),
                hover_color=theme.color("surface_hover"),
                text_color=theme.color(color_role),
            ).pack(anchor="w", pady=(Spacing.SM, 0))

        _ = accent_strip

    def close(self) -> None:
        """Закрывает уведомление."""
        if self._on_close is not None:
            self._on_close(self)
        else:
            safe_destroy(self)


class ToastManager:
    """Управляет очередью и размещением уведомлений."""

    def __init__(self, master: Any, theme: Theme, animator: Animator) -> None:
        """Создаёт менеджер уведомлений.

        Args:
            master: Окно, в котором размещаются уведомления.
            theme: Активная тема оформления.
            animator: Менеджер анимаций.
        """
        self._master = master
        self._theme = theme
        self._animator = animator
        self._toasts: list[Toast] = []
        self._enabled = True

    def set_enabled(self, value: bool) -> None:
        """Включает или выключает показ уведомлений.

        Args:
            value: Новое состояние.
        """
        self._enabled = value
        if not value:
            self.clear()

    def show(
        self,
        message: str,
        *,
        level: str = "info",
        title: str = "",
        duration: float = 4.0,
        action_text: str = "",
        on_action: Callable[[], None] | None = None,
    ) -> Toast | None:
        """Показывает уведомление.

        Args:
            message: Текст сообщения.
            level: Уровень важности.
            title: Заголовок.
            duration: Время показа в секундах (0 — до закрытия вручную).
            action_text: Надпись кнопки действия.
            on_action: Обработчик кнопки действия.

        Returns:
            Созданное уведомление либо ``None``, если показ выключен.
        """
        if not self._enabled:
            _LOGGER.debug("Уведомление подавлено настройками: %s", message)
            return None

        while len(self._toasts) >= _MAX_VISIBLE:
            self._dismiss(self._toasts[0])

        toast = Toast(
            self._master,
            self._theme,
            message=message,
            level=level,
            title=title,
            action_text=action_text,
            on_action=on_action,
            on_close=self._dismiss,
            width=360,
        )
        self._toasts.append(toast)
        self._layout()
        self._animate_in(toast)

        if duration > 0:
            try:
                self._master.after(int(duration * 1000), lambda: self._dismiss(toast))
            except Exception:
                pass
        return toast

    def success(self, message: str, **kwargs: Any) -> Toast | None:
        """Показывает уведомление об успехе.

        Args:
            message: Текст сообщения.
            **kwargs: Дополнительные параметры :meth:`show`.

        Returns:
            Созданное уведомление.
        """
        return self.show(message, level="success", **kwargs)

    def warning(self, message: str, **kwargs: Any) -> Toast | None:
        """Показывает предупреждение.

        Args:
            message: Текст сообщения.
            **kwargs: Дополнительные параметры :meth:`show`.

        Returns:
            Созданное уведомление.
        """
        return self.show(message, level="warning", **kwargs)

    def error(self, message: str, **kwargs: Any) -> Toast | None:
        """Показывает сообщение об ошибке.

        Args:
            message: Текст сообщения.
            **kwargs: Дополнительные параметры :meth:`show`.

        Returns:
            Созданное уведомление.
        """
        kwargs.setdefault("duration", 8.0)
        return self.show(message, level="error", **kwargs)

    def info(self, message: str, **kwargs: Any) -> Toast | None:
        """Показывает информационное уведомление.

        Args:
            message: Текст сообщения.
            **kwargs: Дополнительные параметры :meth:`show`.

        Returns:
            Созданное уведомление.
        """
        return self.show(message, level="info", **kwargs)

    def clear(self) -> None:
        """Закрывает все уведомления."""
        for toast in list(self._toasts):
            self._dismiss(toast)

    # ------------------------------------------------------------ внутреннее
    def _dismiss(self, toast: Toast) -> None:
        """Убирает уведомление с экрана."""
        if toast not in self._toasts:
            return
        self._toasts.remove(toast)
        safe_destroy(toast)
        self._layout()

    def _layout(self) -> None:
        """Размещает уведомления стопкой в правом нижнем углу."""
        offset = Spacing.LG
        for toast in reversed(self._toasts):
            try:
                toast.place(relx=1.0, rely=1.0, anchor="se", x=-Spacing.LG, y=-offset)
                toast.update_idletasks()
                offset += toast.winfo_reqheight() + Spacing.SM
            except Exception:
                continue

    def _animate_in(self, toast: Toast) -> None:
        """Анимирует появление уведомления сдвигом снизу."""
        try:
            info = toast.place_info()
            target_y = int(float(info.get("y", 0)))
        except Exception:
            return

        def _apply(value: float) -> None:
            try:
                toast.place_configure(y=int(value))
            except Exception:
                pass

        self._animator.animate(
            self._master,
            f"toast-{id(toast)}",
            start=float(target_y + 40),
            end=float(target_y),
            duration=DURATION_NORMAL,
            easing=ease_out_cubic,
            on_frame=_apply,
        )
