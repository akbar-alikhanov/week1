"""Базовый класс разделов приложения."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from app.gui.theme import FontRole, Spacing, Theme

if TYPE_CHECKING:  # pragma: no cover — только для проверки типов
    from app.gui.app import ApplicationWindow

_LOGGER = logging.getLogger(__name__)


class BaseView(ctk.CTkFrame):
    """Общий каркас раздела: заголовок, панель действий, содержимое.

    Раздел ничего не знает о других разделах и обращается к приложению только
    через переданную ссылку на главное окно — там сосредоточены общие службы
    (уведомления, фоновые задачи, диалоги).
    """

    #: Заголовок раздела.
    title: str = ""

    #: Пояснение под заголовком.
    subtitle: str = ""

    def __init__(self, master: Any, app: ApplicationWindow, **kwargs: Any) -> None:
        """Создаёт раздел.

        Args:
            master: Родительский виджет (область содержимого окна).
            app: Главное окно приложения.
            **kwargs: Дополнительные параметры ``CTkFrame``.
        """
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app = app
        self.theme: Theme = app.theme
        self._built = False

        header = ctk.CTkFrame(self, fg_color="transparent", width=0, height=0)
        header.pack(fill="x", padx=Spacing.XL, pady=(Spacing.XL, Spacing.MD))

        titles = ctk.CTkFrame(header, fg_color="transparent", width=0, height=0)
        titles.pack(side="left", fill="x", expand=True)

        self.title_label = ctk.CTkLabel(
            titles,
            text=self.title,
            font=self.theme.font(FontRole.TITLE),
            text_color=self.theme.color("text"),
            anchor="w",
        )
        self.title_label.pack(fill="x", anchor="w")

        self.subtitle_label = ctk.CTkLabel(
            titles,
            text=self.subtitle,
            font=self.theme.font(FontRole.SMALL),
            text_color=self.theme.color("text_muted"),
            anchor="w",
            justify="left",
        )
        self.subtitle_label.pack(fill="x", anchor="w", pady=(2, 0))

        self.actions = ctk.CTkFrame(header, fg_color="transparent", width=0, height=0)
        self.actions.pack(side="right")

        self.content = ctk.CTkFrame(self, fg_color="transparent", width=0, height=0)
        self.content.pack(fill="both", expand=True, padx=Spacing.XL, pady=(0, Spacing.XL))

    # ------------------------------------------------------------ жизненный цикл
    def build(self) -> None:
        """Создаёт содержимое раздела.

        Вызывается один раз при первом открытии — это заметно ускоряет старт
        приложения, поскольку тяжёлые разделы (таблицы, просмотр PDF) не
        создаются, пока пользователь их не открыл.
        """

    def on_show(self) -> None:
        """Вызывается при каждом открытии раздела."""

    def on_hide(self) -> None:
        """Вызывается при уходе из раздела."""

    def refresh(self) -> None:
        """Перечитывает данные раздела."""

    def focus_search(self) -> None:
        """Передаёт фокус строке поиска раздела, если она есть.

        Разделы без поиска (например, «Подбор») оставляют реализацию пустой —
        вызывающему коду (горячая клавиша ``Ctrl+F``) не нужно знать, какие
        разделы умеют искать, а какие нет.
        """

    def refresh_theme(self) -> None:
        """Обновляет цвета после смены темы."""
        try:
            self.title_label.configure(text_color=self.theme.color("text"))
            self.subtitle_label.configure(text_color=self.theme.color("text_muted"))
        except Exception:
            pass

    def ensure_built(self) -> None:
        """Гарантирует, что содержимое раздела создано."""
        if self._built:
            return
        self._built = True
        try:
            self.build()
        except Exception:
            _LOGGER.exception("Ошибка построения раздела %s", type(self).__name__)

    def set_subtitle(self, text: str) -> None:
        """Обновляет пояснение под заголовком.

        Args:
            text: Новый текст.
        """
        try:
            self.subtitle_label.configure(text=text)
        except Exception:
            pass
