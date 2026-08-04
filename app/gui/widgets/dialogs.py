"""Модальные диалоги приложения."""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

from app.core.constants import APP_COMPANY, APP_DESCRIPTION, APP_NAME, APP_VERSION
from app.gui.icons import icons
from app.gui.theme import FontRole, Radius, Spacing, Theme
from app.gui.widgets.base import center_on_parent
from app.gui.widgets.controls import ghost_button, primary_button, secondary_button


class ModalDialog(ctk.CTkToplevel):
    """Базовое модальное окно с единым оформлением.

    Обеспечивает захват фокуса, закрытие по ``Esc``, центрирование
    относительно родителя и корректное освобождение захвата — всё то, что
    приходится повторять в каждом диалоге.
    """

    def __init__(
        self,
        master: Any,
        theme: Theme,
        *,
        title: str,
        width: int = 520,
        height: int = 300,
        resizable: bool = False,
    ) -> None:
        """Создаёт модальное окно.

        Args:
            master: Родительское окно.
            theme: Активная тема оформления.
            title: Заголовок окна.
            width: Ширина.
            height: Высота.
            resizable: Разрешено ли изменение размера.
        """
        super().__init__(master)
        self._theme = theme
        self._result: Any = None

        self.title(title)
        self.resizable(resizable, resizable)
        self.configure(fg_color=theme.color("background"))
        center_on_parent(self, master, width, height)

        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _: self.close())

        self.container = ctk.CTkFrame(self, fg_color="transparent", width=0, height=0)
        self.container.pack(fill="both", expand=True, padx=Spacing.XL, pady=Spacing.XL)

        # Захват ввода откладывается: окно должно быть отображено, иначе
        # grab_set завершается ошибкой на некоторых оконных менеджерах.
        self.after(80, self._grab)

    def _grab(self) -> None:
        """Захватывает ввод для модального режима."""
        try:
            self.lift()
            self.focus_force()
            self.grab_set()
        except Exception:
            pass

    @property
    def result(self) -> Any:
        """Результат работы диалога."""
        return self._result

    def close(self, result: Any = None) -> None:
        """Закрывает диалог.

        Args:
            result: Значение, возвращаемое как результат.
        """
        if result is not None:
            self._result = result
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    def wait_result(self) -> Any:
        """Блокирует выполнение до закрытия диалога.

        Returns:
            Результат работы диалога.
        """
        self.wait_window()
        return self._result


class ConfirmDialog(ModalDialog):
    """Диалог подтверждения действия."""

    def __init__(
        self,
        master: Any,
        theme: Theme,
        *,
        title: str,
        message: str,
        confirm_text: str = "Подтвердить",
        cancel_text: str = "Отмена",
        danger: bool = False,
        detail: str = "",
    ) -> None:
        """Создаёт диалог подтверждения.

        Args:
            master: Родительское окно.
            theme: Активная тема оформления.
            title: Заголовок.
            message: Основной вопрос.
            confirm_text: Надпись кнопки подтверждения.
            cancel_text: Надпись кнопки отмены.
            danger: Оформить ли подтверждение как опасное действие.
            detail: Дополнительное пояснение.
        """
        super().__init__(master, theme, title=title, width=520, height=250 if detail else 210)

        header = ctk.CTkFrame(self.container, fg_color="transparent", width=0, height=0)
        header.pack(fill="x")

        ctk.CTkLabel(
            header,
            text="",
            image=icons.colored(
                "alert" if danger else "info", theme, "danger" if danger else "accent", 28
            ),
            width=34,
        ).pack(side="left", padx=(0, Spacing.MD))

        texts = ctk.CTkFrame(header, fg_color="transparent", width=0, height=0)
        texts.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(
            texts,
            text=message,
            font=theme.font(FontRole.SUBHEADING),
            text_color=theme.color("text"),
            anchor="w",
            justify="left",
            wraplength=400,
        ).pack(fill="x", anchor="w")

        if detail:
            ctk.CTkLabel(
                texts,
                text=detail,
                font=theme.font(FontRole.SMALL),
                text_color=theme.color("text_muted"),
                anchor="w",
                justify="left",
                wraplength=400,
            ).pack(fill="x", anchor="w", pady=(Spacing.SM, 0))

        buttons = ctk.CTkFrame(self.container, fg_color="transparent", width=0, height=0)
        buttons.pack(fill="x", side="bottom", pady=(Spacing.XL, 0))

        confirm = primary_button(
            buttons, theme, text=confirm_text, command=lambda: self.close(True)
        )
        if danger:
            confirm.configure(fg_color=theme.color("danger"), hover_color=theme.color("danger"))
        confirm.pack(side="right")

        secondary_button(buttons, theme, text=cancel_text, command=lambda: self.close(False)).pack(
            side="right", padx=(0, Spacing.SM)
        )

        self._result = False


class MessageDialog(ModalDialog):
    """Диалог с текстовым сообщением и техническими подробностями."""

    def __init__(
        self,
        master: Any,
        theme: Theme,
        *,
        title: str,
        message: str,
        level: str = "info",
        details: str = "",
    ) -> None:
        """Создаёт информационный диалог.

        Args:
            master: Родительское окно.
            theme: Активная тема оформления.
            title: Заголовок.
            message: Сообщение.
            level: ``info``, ``success``, ``warning`` или ``error``.
            details: Технические подробности (скрыты за раскрывающимся блоком).
        """
        super().__init__(master, theme, title=title, width=560, height=340 if details else 220)

        role = {"error": "danger", "warning": "warning", "success": "success"}.get(level, "accent")
        icon = {"error": "alert", "warning": "alert", "success": "check"}.get(level, "info")

        header = ctk.CTkFrame(self.container, fg_color="transparent", width=0, height=0)
        header.pack(fill="x")

        ctk.CTkLabel(header, text="", image=icons.colored(icon, theme, role, 28), width=34).pack(
            side="left", padx=(0, Spacing.MD)
        )

        ctk.CTkLabel(
            header,
            text=message,
            font=theme.font(FontRole.BODY),
            text_color=theme.color("text"),
            anchor="w",
            justify="left",
            wraplength=440,
        ).pack(side="left", fill="both", expand=True)

        if details:
            box = ctk.CTkTextbox(
                self.container,
                height=120,
                font=theme.font(FontRole.CAPTION, mono=True),
                fg_color=theme.color("surface_alt"),
                text_color=theme.color("text_muted"),
                corner_radius=Radius.SM,
                wrap="word",
            )
            box.pack(fill="both", expand=True, pady=(Spacing.LG, 0))
            box.insert("1.0", details)
            box.configure(state="disabled")

        buttons = ctk.CTkFrame(self.container, fg_color="transparent", width=0, height=0)
        buttons.pack(fill="x", side="bottom", pady=(Spacing.LG, 0))
        primary_button(buttons, theme, text="Закрыть", command=self.close).pack(side="right")


class AboutDialog(ModalDialog):
    """Окно «О программе» со сведениями о среде выполнения."""

    def __init__(self, master: Any, theme: Theme, *, diagnostics: dict[str, Any]) -> None:
        """Создаёт окно «О программе».

        Args:
            master: Родительское окно.
            theme: Активная тема оформления.
            diagnostics: Сведения о состоянии приложения.
        """
        super().__init__(master, theme, title="О программе", width=620, height=560)

        header = ctk.CTkFrame(self.container, fg_color="transparent", width=0, height=0)
        header.pack(fill="x")

        ctk.CTkLabel(header, text="", image=icons.accent("shield", theme, 46), width=54).pack(
            side="left", padx=(0, Spacing.LG)
        )

        titles = ctk.CTkFrame(header, fg_color="transparent", width=0, height=0)
        titles.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(
            titles,
            text=APP_NAME,
            font=theme.font(FontRole.TITLE),
            text_color=theme.color("text"),
            anchor="w",
        ).pack(fill="x", anchor="w")
        ctk.CTkLabel(
            titles,
            text=f"Версия {APP_VERSION} · {APP_COMPANY}",
            font=theme.font(FontRole.SMALL),
            text_color=theme.color("text_muted"),
            anchor="w",
        ).pack(fill="x", anchor="w")
        ctk.CTkLabel(
            titles,
            text=APP_DESCRIPTION,
            font=theme.font(FontRole.SMALL),
            text_color=theme.color("text_muted"),
            anchor="w",
            justify="left",
            wraplength=420,
        ).pack(fill="x", anchor="w", pady=(Spacing.SM, 0))

        scroll = ctk.CTkScrollableFrame(
            self.container, fg_color=theme.color("surface"), corner_radius=Radius.MD
        )
        scroll.pack(fill="both", expand=True, pady=(Spacing.XL, 0))

        for key, value in diagnostics.items():
            row = ctk.CTkFrame(scroll, fg_color="transparent", width=0, height=0)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(
                row,
                text=key,
                font=theme.font(FontRole.CAPTION),
                text_color=theme.color("text_muted"),
                width=190,
                anchor="w",
            ).pack(side="left")
            ctk.CTkLabel(
                row,
                text=str(value),
                font=theme.font(FontRole.CAPTION),
                text_color=theme.color("text"),
                anchor="w",
                justify="left",
                wraplength=350,
            ).pack(side="left", fill="x", expand=True)

        buttons = ctk.CTkFrame(self.container, fg_color="transparent", width=0, height=0)
        buttons.pack(fill="x", pady=(Spacing.LG, 0))
        primary_button(buttons, theme, text="Закрыть", command=self.close).pack(side="right")

        ghost_button(
            buttons,
            theme,
            text="Копировать сведения",
            icon="copy",
            command=lambda: self._copy(diagnostics),
        ).pack(side="right", padx=(0, Spacing.SM))

    def _copy(self, diagnostics: dict[str, Any]) -> None:
        """Копирует сведения о системе в буфер обмена."""
        text = "\n".join(f"{key}: {value}" for key, value in diagnostics.items())
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
        except Exception:
            pass


class ShortcutsDialog(ModalDialog):
    """Справка по горячим клавишам."""

    #: Список сочетаний: (клавиши, описание).
    SHORTCUTS: tuple[tuple[str, str], ...] = (
        ("Ctrl + O", "Выбрать файл заказа"),
        ("Ctrl + D", "Выбрать папку сертификатов"),
        ("Ctrl + Enter", "Подобрать сертификаты"),
        ("F5", "Переиндексировать папку"),
        ("Ctrl + F", "Перейти к поиску"),
        ("Ctrl + T", "Переключить светлую и тёмную тему"),
        ("Ctrl + 1 … 6", "Перейти к разделу"),
        ("Ctrl + L", "Открыть журнал операций"),
        ("Ctrl + S", "Открыть настройки"),
        ("Ctrl + B", "Свернуть боковую панель"),
        ("F1", "Справка по горячим клавишам"),
        ("Esc", "Закрыть окно или отменить операцию"),
        ("Ctrl + N", "Словарь товаров: добавить соответствие"),
        ("Ctrl + E", "Словарь товаров: изменить выбранную запись"),
        ("Delete", "Словарь товаров: удалить выбранное"),
        ("Ctrl + Z", "Словарь товаров: отменить последнее действие"),
    )

    def __init__(self, master: Any, theme: Theme) -> None:
        """Создаёт окно справки.

        Args:
            master: Родительское окно.
            theme: Активная тема оформления.
        """
        super().__init__(master, theme, title="Горячие клавиши", width=520, height=520)

        ctk.CTkLabel(
            self.container,
            text="Горячие клавиши",
            font=theme.font(FontRole.HEADING),
            text_color=theme.color("text"),
            anchor="w",
        ).pack(fill="x", anchor="w", pady=(0, Spacing.MD))

        for keys, description in self.SHORTCUTS:
            row = ctk.CTkFrame(self.container, fg_color="transparent", width=0, height=0)
            row.pack(fill="x", pady=3)

            chip = ctk.CTkLabel(
                row,
                text=keys,
                font=theme.font(FontRole.CAPTION, mono=True),
                text_color=theme.color("accent"),
                fg_color=theme.color("accent_soft"),
                corner_radius=Radius.SM,
                width=130,
            )
            chip.pack(side="left", ipady=4)

            ctk.CTkLabel(
                row,
                text=description,
                font=theme.font(FontRole.SMALL),
                text_color=theme.color("text"),
                anchor="w",
            ).pack(side="left", padx=(Spacing.MD, 0), fill="x", expand=True)

        primary_button(self.container, theme, text="Понятно", command=self.close).pack(
            side="bottom", anchor="e", pady=(Spacing.LG, 0)
        )


def ask_confirmation(
    master: Any,
    theme: Theme,
    *,
    title: str,
    message: str,
    confirm_text: str = "Подтвердить",
    danger: bool = False,
    detail: str = "",
) -> bool:
    """Показывает диалог подтверждения и ждёт ответа.

    Args:
        master: Родительское окно.
        theme: Активная тема оформления.
        title: Заголовок.
        message: Вопрос.
        confirm_text: Надпись кнопки подтверждения.
        danger: Оформить ли действие как опасное.
        detail: Пояснение.

    Returns:
        ``True``, если пользователь подтвердил действие.
    """
    dialog = ConfirmDialog(
        master,
        theme,
        title=title,
        message=message,
        confirm_text=confirm_text,
        danger=danger,
        detail=detail,
    )
    return bool(dialog.wait_result())


def show_message(
    master: Any,
    theme: Theme,
    *,
    title: str,
    message: str,
    level: str = "info",
    details: str = "",
) -> None:
    """Показывает информационный диалог.

    Args:
        master: Родительское окно.
        theme: Активная тема оформления.
        title: Заголовок.
        message: Сообщение.
        level: Уровень важности.
        details: Технические подробности.
    """
    MessageDialog(master, theme, title=title, message=message, level=level, details=details)
