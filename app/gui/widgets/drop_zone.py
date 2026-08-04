"""Зона выбора файла или папки с поддержкой перетаскивания."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import customtkinter as ctk

from app.gui import dnd
from app.gui.animations import Animator
from app.gui.icons import icons
from app.gui.theme import FontRole, Radius, Spacing, Theme
from app.gui.widgets.base import bind_recursive, format_bytes, set_cursor


class FileDropZone(ctk.CTkFrame):
    """Область, принимающая файл или папку.

    Поддерживает три способа выбора — перетаскивание, щелчок и горячую
    клавишу, — потому что в реальной работе используются все три: одни
    пользователи тянут файл из проводника, другие привыкли к диалогу.
    """

    def __init__(
        self,
        master: Any,
        theme: Theme,
        *,
        title: str,
        hint: str,
        icon: str = "excel",
        select_directory: bool = False,
        extensions: Iterable[str] = (),
        on_selected: Callable[[Path], None] | None = None,
        animator: Animator | None = None,
        dialog_title: str = "Выберите файл",
        **kwargs: Any,
    ) -> None:
        """Создаёт зону выбора.

        Args:
            master: Родительский виджет.
            theme: Активная тема оформления.
            title: Заголовок зоны.
            hint: Подсказка о допустимом содержимом.
            icon: Имя иконки.
            select_directory: Выбирать папку вместо файла.
            extensions: Допустимые расширения файлов.
            on_selected: Обработчик выбора.
            animator: Менеджер анимаций.
            dialog_title: Заголовок системного диалога выбора.
            **kwargs: Дополнительные параметры ``CTkFrame``.
        """
        self._theme = theme
        self._animator = animator
        self._on_selected = on_selected
        self._select_directory = select_directory
        self._extensions = tuple(extensions)
        self._dialog_title = dialog_title
        self._title = title
        self._hint = hint
        self._path: Path | None = None
        self._active = False

        super().__init__(
            master,
            fg_color=theme.color("surface"),
            corner_radius=Radius.LG,
            border_width=2,
            border_color=theme.color("border"),
            **kwargs,
        )

        container = ctk.CTkFrame(self, fg_color="transparent", width=0, height=0)
        container.pack(fill="both", expand=True, padx=Spacing.LG, pady=Spacing.LG)

        self._icon_label = ctk.CTkLabel(
            container,
            text="",
            image=icons.colored(icon, theme, "text_muted", 34),
            width=40,
        )
        self._icon_label.pack(side="left", padx=(0, Spacing.MD))
        self._icon_name = icon

        texts = ctk.CTkFrame(container, fg_color="transparent", width=0, height=0)
        texts.pack(side="left", fill="both", expand=True)

        self._title_label = ctk.CTkLabel(
            texts,
            text=title,
            font=theme.font(FontRole.SUBHEADING),
            text_color=theme.color("text"),
            anchor="w",
        )
        self._title_label.pack(fill="x", anchor="w")

        self._hint_label = ctk.CTkLabel(
            texts,
            text=hint,
            font=theme.font(FontRole.SMALL),
            text_color=theme.color("text_muted"),
            anchor="w",
            justify="left",
        )
        self._hint_label.pack(fill="x", anchor="w", pady=(2, 0))

        self._clear_button = ctk.CTkButton(
            container,
            text="",
            image=icons.colored("close", theme, "text_muted", 16),
            width=28,
            height=28,
            corner_radius=Radius.SM,
            fg_color="transparent",
            hover_color=theme.color("surface_hover"),
            command=self.clear,
        )

        self.after(60, self._setup_interaction)

    # ------------------------------------------------------------ свойства
    @property
    def path(self) -> Path | None:
        """Выбранный путь либо ``None``."""
        return self._path

    @property
    def has_selection(self) -> bool:
        """Признак того, что выбор сделан."""
        return self._path is not None

    # --------------------------------------------------------- взаимодействие
    def _setup_interaction(self) -> None:
        """Подключает щелчок, наведение и перетаскивание."""
        set_cursor(self, "hand2")
        bind_recursive(self, "<Button-1>", lambda _: self.browse())
        bind_recursive(self, "<Enter>", lambda _: self._set_active(True))
        bind_recursive(self, "<Leave>", lambda _: self._set_active(False))

        dnd.register_drop_target(
            self,
            self._handle_drop,
            on_enter=lambda: self._set_active(True),
            on_leave=lambda: self._set_active(False),
            extensions=self._extensions,
        )

    def _handle_drop(self, paths: list[Path]) -> None:
        """Обрабатывает перетаскивание файлов."""
        for path in paths:
            if self._select_directory and path.is_dir():
                self.set_path(path)
                return
            if not self._select_directory and path.is_file() and (
                not self._extensions or path.suffix.lower() in self._extensions
            ):
                self.set_path(path)
                return
        self._flash_error()

    def _set_active(self, value: bool) -> None:
        """Подсвечивает зону при наведении."""
        if value == self._active:
            return
        self._active = value
        role = "accent" if value else "border"
        try:
            self.configure(border_color=self._theme.color(role))
            self._icon_label.configure(
                image=icons.colored(
                    self._icon_name, self._theme, "accent" if value else "text_muted", 34
                )
            )
        except Exception:
            pass

    def _flash_error(self) -> None:
        """Кратковременно подсвечивает зону цветом ошибки."""
        try:
            self.configure(border_color=self._theme.color("danger"))
            self.after(900, lambda: self.configure(border_color=self._theme.color("border")))
        except Exception:
            pass

    def browse(self) -> None:
        """Открывает системный диалог выбора."""
        from tkinter import filedialog

        if self._select_directory:
            selected = filedialog.askdirectory(title=self._dialog_title, mustexist=True)
        else:
            file_types = [("Файлы Excel", "*.xlsx *.xlsm"), ("Все файлы", "*.*")]
            selected = filedialog.askopenfilename(title=self._dialog_title, filetypes=file_types)

        if selected:
            self.set_path(Path(selected))

    def set_path(self, path: Path | None, *, notify: bool = True) -> None:
        """Устанавливает выбранный путь.

        Args:
            path: Новый путь либо ``None`` для сброса.
            notify: Вызывать ли обработчик выбора.
        """
        self._path = path
        if path is None:
            self._title_label.configure(text=self._title, text_color=self._theme.color("text"))
            self._hint_label.configure(text=self._hint)
            self._clear_button.pack_forget()
            self._icon_label.configure(
                image=icons.colored(self._icon_name, self._theme, "text_muted", 34)
            )
            return

        self._title_label.configure(text=path.name, text_color=self._theme.color("text"))
        self._hint_label.configure(text=self._describe(path))
        self._icon_label.configure(image=icons.colored(self._icon_name, self._theme, "accent", 34))
        self._clear_button.pack(side="right", padx=(Spacing.SM, 0))

        if notify and self._on_selected is not None:
            self._on_selected(path)

    def clear(self) -> None:
        """Сбрасывает выбор."""
        self.set_path(None, notify=False)

    def _describe(self, path: Path) -> str:
        """Формирует подпись с характеристиками выбранного объекта."""
        try:
            if path.is_dir():
                count = sum(1 for item in path.rglob("*.pdf") if item.is_file())
                return f"{_short_path(path)} · PDF-файлов: {count}"
            size = path.stat().st_size
            return f"{_short_path(path.parent)} · {format_bytes(size)}"
        except OSError:
            return _short_path(path)

    def refresh_theme(self) -> None:
        """Обновляет цвета после смены темы."""
        try:
            self.configure(
                fg_color=self._theme.color("surface"), border_color=self._theme.color("border")
            )
            self._title_label.configure(text_color=self._theme.color("text"))
            self._hint_label.configure(text_color=self._theme.color("text_muted"))
        except Exception:
            pass


def _short_path(path: Path, limit: int = 52) -> str:
    r"""Сокращает путь для отображения, сохраняя начало и конец.

    Длинные сетевые пути не помещаются в карточку и вытесняют полезную
    информацию, поэтому середина пути заменяется многоточием.

    Args:
        path: Отображаемый путь.
        limit: Максимальная длина результата.

    Returns:
        Сокращённая строка вида ``C:\Общие\…\Сертификаты``.
    """
    text = str(path)
    if len(text) <= limit:
        return text
    parts = path.parts
    if len(parts) <= 2:
        return "…" + text[-(limit - 1) :]
    head = parts[0]
    tail = str(Path(*parts[-2:]))
    candidate = f"{head}{os.sep}…{os.sep}{tail}"
    if len(candidate) <= limit:
        return candidate
    return "…" + text[-(limit - 1) :]
