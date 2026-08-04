"""Встроенный просмотрщик PDF-сертификатов.

Открывать сертификат во внешней программе — значит выбрасывать пользователя
из рабочего контекста и заставлять его возвращаться обратно. Встроенный
просмотр решает задачу «убедиться, что подобран нужный документ» за секунду.

Страница отрисовывается средствами PyMuPDF в растр и отображается как
изображение. Рендеринг выполняется в фоновом потоке: страница формата A4
при высоком масштабе строится десятки миллисекунд, и делать это в потоке
интерфейса недопустимо.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import customtkinter as ctk

from app.gui.icons import icons
from app.gui.theme import FontRole, Radius, Spacing, Theme
from app.gui.widgets.controls import icon_button

_LOGGER = logging.getLogger(__name__)

#: Доступные коэффициенты масштабирования.
ZOOM_LEVELS: tuple[float, ...] = (0.75, 1.0, 1.35, 1.75, 2.25, 3.0)


class PdfViewer(ctk.CTkFrame):
    """Просмотр PDF с постраничной навигацией и масштабированием."""

    def __init__(
        self,
        master: Any,
        theme: Theme,
        *,
        render: Callable[[Path, int, float], tuple[bytes, int, int]],
        page_count: Callable[[Path], int],
        submit: Callable[[Callable[[], Any], Callable[[Any], None]], None] | None = None,
        on_open_external: Callable[[Path], None] | None = None,
        **kwargs: Any,
    ) -> None:
        """Создаёт просмотрщик.

        Args:
            master: Родительский виджет.
            theme: Активная тема оформления.
            render: Функция отрисовки страницы в PNG.
            page_count: Функция подсчёта страниц документа.
            submit: Планировщик фоновой работы ``(работа, обработчик)``.
                При ``None`` отрисовка выполняется синхронно.
            on_open_external: Обработчик открытия во внешней программе.
            **kwargs: Дополнительные параметры ``CTkFrame``.
        """
        self._theme = theme
        self._render = render
        self._page_count_fn = page_count
        self._submit = submit
        self._on_open_external = on_open_external

        self._path: Path | None = None
        self._page = 0
        self._pages = 0
        self._zoom_index = 1
        self._image: Any = None
        self._render_token = 0

        super().__init__(
            master,
            fg_color=theme.color("surface"),
            corner_radius=Radius.MD,
            border_width=1,
            border_color=theme.color("border"),
            **kwargs,
        )

        toolbar = ctk.CTkFrame(self, fg_color="transparent", height=40)
        toolbar.pack(fill="x", padx=Spacing.SM, pady=(Spacing.SM, 0))

        self._prev_button = icon_button(
            toolbar, theme, icon="chevron_right", command=self.previous_page, size=30
        )
        self._prev_button.pack(side="left")

        self._page_label = ctk.CTkLabel(
            toolbar,
            text="—",
            font=theme.font(FontRole.SMALL),
            text_color=theme.color("text_muted"),
            width=80,
        )
        self._page_label.pack(side="left", padx=Spacing.XS)

        self._next_button = icon_button(
            toolbar, theme, icon="chevron_right", command=self.next_page, size=30
        )
        self._next_button.pack(side="left")

        if on_open_external is not None:
            icon_button(
                toolbar,
                theme,
                icon="external",
                command=self._open_external,
                tooltip="Открыть во внешней программе",
                size=30,
            ).pack(side="right")

        self._zoom_label = ctk.CTkLabel(
            toolbar,
            text="100 %",
            font=theme.font(FontRole.CAPTION),
            text_color=theme.color("text_muted"),
            width=52,
        )
        self._zoom_label.pack(side="right", padx=Spacing.XS)

        icon_button(
            toolbar, theme, icon="plus", command=self.zoom_in, tooltip="Увеличить", size=30
        ).pack(side="right")

        self._canvas_frame = ctk.CTkScrollableFrame(
            self, fg_color=theme.color("surface_alt"), corner_radius=Radius.SM
        )
        self._canvas_frame.pack(fill="both", expand=True, padx=Spacing.SM, pady=Spacing.SM)

        self._page_label_image = ctk.CTkLabel(self._canvas_frame, text="", image=None)
        self._page_label_image.pack(pady=Spacing.SM)

        self._placeholder = ctk.CTkLabel(
            self._canvas_frame,
            text="Выберите сертификат для просмотра",
            font=theme.font(FontRole.SMALL),
            text_color=theme.color("text_muted"),
            image=icons.colored("pdf", theme, "text_muted", 40),
            compound="top",
        )
        self._placeholder.pack(pady=Spacing.XXL)

        self.bind("<Control-plus>", lambda _: self.zoom_in())
        self.bind("<Control-minus>", lambda _: self.zoom_out())

    # ---------------------------------------------------------------- API
    @property
    def path(self) -> Path | None:
        """Открытый документ либо ``None``."""
        return self._path

    def open(self, path: Path | None) -> None:
        """Открывает документ для просмотра.

        Args:
            path: Путь к PDF-файлу; ``None`` — очистить просмотр.
        """
        if path is None or not path.exists():
            self.clear(
                "Файл сертификата недоступен" if path else "Выберите сертификат для просмотра"
            )
            return

        self._path = path
        self._page = 0
        self._pages = 0
        self._placeholder.pack_forget()
        self._refresh_page()

        def _count() -> int:
            return self._page_count_fn(path)

        def _apply(count: Any) -> None:
            self._pages = int(count or 0)
            self._update_navigation()

        if self._submit is not None:
            self._submit(_count, _apply)
        else:
            _apply(_count())

    def clear(self, message: str = "Выберите сертификат для просмотра") -> None:
        """Очищает область просмотра.

        Args:
            message: Текст заглушки.
        """
        self._path = None
        self._pages = 0
        self._page = 0
        self._image = None
        try:
            self._page_label_image.configure(image=None, text="")
            self._placeholder.configure(text=message)
            self._placeholder.pack(pady=Spacing.XXL)
            self._page_label.configure(text="—")
        except Exception:
            pass

    def next_page(self) -> None:
        """Переходит к следующей странице."""
        if self._path is not None and self._page + 1 < max(1, self._pages):
            self._page += 1
            self._refresh_page()

    def previous_page(self) -> None:
        """Переходит к предыдущей странице."""
        if self._path is not None and self._page > 0:
            self._page -= 1
            self._refresh_page()

    def zoom_in(self) -> None:
        """Увеличивает масштаб."""
        if self._zoom_index + 1 < len(ZOOM_LEVELS):
            self._zoom_index += 1
            self._refresh_page()

    def zoom_out(self) -> None:
        """Уменьшает масштаб."""
        if self._zoom_index > 0:
            self._zoom_index -= 1
            self._refresh_page()

    # ------------------------------------------------------------ внутреннее
    def _refresh_page(self) -> None:
        """Перерисовывает текущую страницу."""
        path = self._path
        if path is None:
            return

        zoom = ZOOM_LEVELS[self._zoom_index]
        self._zoom_label.configure(text=f"{int(zoom * 100)} %")
        self._render_token += 1
        token = self._render_token
        page = self._page

        def _work() -> tuple[bytes, int, int] | None:
            try:
                return self._render(path, page, zoom)
            except Exception as error:
                _LOGGER.debug("Не удалось отрисовать страницу: %s", error)
                return None

        def _apply(result: Any) -> None:
            if token != self._render_token:
                return  # пришёл ответ на устаревший запрос
            if not result:
                self.clear("Не удалось отобразить документ")
                return
            payload, width, height = result
            self._show_image(payload, width, height)
            self._update_navigation()

        if self._submit is not None:
            self._submit(_work, _apply)
        else:
            _apply(_work())

    def _show_image(self, payload: bytes, width: int, height: int) -> None:
        """Отображает отрисованную страницу."""
        try:
            from PIL import Image

            image = Image.open(io.BytesIO(payload))
            self._image = ctk.CTkImage(light_image=image, dark_image=image, size=(width, height))
            self._placeholder.pack_forget()
            self._page_label_image.configure(image=self._image, text="")
        except Exception:
            _LOGGER.debug("Ошибка отображения страницы PDF", exc_info=True)

    def _update_navigation(self) -> None:
        """Обновляет состояние кнопок навигации."""
        total = max(1, self._pages)
        try:
            self._page_label.configure(text=f"{self._page + 1} из {total}")
            self._prev_button.configure(state="normal" if self._page > 0 else "disabled")
            self._next_button.configure(state="normal" if self._page + 1 < total else "disabled")
        except Exception:
            pass

    def _open_external(self) -> None:
        """Открывает документ во внешней программе."""
        if self._path is not None and self._on_open_external is not None:
            self._on_open_external(self._path)
