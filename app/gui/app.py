"""Главное окно приложения.

Окно выполняет роль оболочки: держит боковую панель, переключает разделы и
предоставляет им общие службы — уведомления, фоновые задачи, диалоги, тему.
Бизнес-логики здесь нет: она целиком в сервисном слое, доступном через
контейнер зависимостей.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import customtkinter as ctk

from app.config.settings import AppSettings, SettingsService
from app.core.constants import APP_NAME, APP_VERSION, EXCEL_EXTENSIONS
from app.core.container import ApplicationContainer
from app.gui import dnd
from app.gui.animations import Animator
from app.gui.icons import icons
from app.gui.task_runner import TaskRunner
from app.gui.theme import Sizes, Theme
from app.gui.views.aliases_view import AliasesView
from app.gui.views.base_view import BaseView
from app.gui.views.certificates_view import CertificatesView
from app.gui.views.dashboard_view import DashboardView
from app.gui.views.history_view import HistoryView
from app.gui.views.logs_view import LogsView
from app.gui.views.settings_view import SettingsView
from app.gui.widgets.dialogs import AboutDialog, ShortcutsDialog, ask_confirmation, show_message
from app.gui.widgets.sidebar import NavItem, Sidebar
from app.gui.widgets.toast import ToastManager
from app.gui.window_state import WindowStateStore

_LOGGER = logging.getLogger(__name__)

#: Разделы приложения в порядке отображения.
NAV_ITEMS: tuple[NavItem, ...] = (
    NavItem("dashboard", "Подбор", "dashboard", "Ctrl+1"),
    NavItem("certificates", "Сертификаты", "certificate", "Ctrl+2"),
    NavItem("aliases", "Словарь товаров", "alias", "Ctrl+3"),
    NavItem("history", "История", "history", "Ctrl+4"),
    NavItem("logs", "Журнал", "log", "Ctrl+5"),
    NavItem("settings", "Настройки", "settings", "Ctrl+6"),
)

#: Классы разделов по идентификатору.
VIEW_CLASSES: dict[str, type[BaseView]] = {
    "dashboard": DashboardView,
    "certificates": CertificatesView,
    "aliases": AliasesView,
    "history": HistoryView,
    "logs": LogsView,
    "settings": SettingsView,
}


class ApplicationWindow(ctk.CTk):
    """Главное окно приложения."""

    def __init__(self, container: ApplicationContainer) -> None:
        """Создаёт и настраивает окно.

        Args:
            container: Контейнер зависимостей приложения.
        """
        self.container = container
        self.settings_service: SettingsService = container.settings_service
        settings = self.settings_service.current

        ctk.set_appearance_mode(settings.ui.theme)
        ctk.set_widget_scaling(settings.ui.scaling)

        super().__init__()

        self.theme = Theme(settings.ui.accent, settings.ui.theme)
        self.theme.detect_fonts(self)
        self.animator = Animator(settings.ui.animations)
        self.tasks = TaskRunner(self, container.background_pool)
        self.toasts = ToastManager(self, self.theme, self.animator)
        self.toasts.set_enabled(settings.ui.notifications)

        self._state_store = WindowStateStore(container.paths.window_state_file)
        self._state = self._state_store.load()
        self._views: dict[str, BaseView] = {}
        self._active_view = ""
        self._closing = False

        self._configure_window()
        self._build_layout()
        self._bind_shortcuts()
        self._enable_dnd()

        self.navigate(self._state.active_view or "dashboard")
        self.after(400, self._post_startup)

    # ------------------------------------------------------------- настройка
    @property
    def settings(self) -> AppSettings:
        """Текущая конфигурация приложения."""
        return self.settings_service.current

    def _configure_window(self) -> None:
        """Задаёт заголовок, размеры и обработчик закрытия."""
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.minsize(*Sizes.MIN_WINDOW)
        self.configure(fg_color=self.theme.color("background"))
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        if self.settings.ui.remember_window_state:
            self._state_store.apply(self, self._state)
        else:
            width, height = Sizes.DEFAULT_WINDOW
            self.geometry(f"{width}x{height}")

        self._apply_window_icon()

    def _apply_window_icon(self) -> None:
        """Устанавливает иконку окна."""
        try:
            from PIL import ImageTk

            image = icons.render_image("shield", 64, self.theme.resolved("accent"))
            self._icon_image = ImageTk.PhotoImage(image)
            self.iconphoto(True, self._icon_image)
        except Exception:
            _LOGGER.debug("Иконка окна не установлена", exc_info=True)

    def _build_layout(self) -> None:
        """Строит боковую панель и область содержимого."""
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = Sidebar(
            self,
            self.theme,
            self.animator,
            items=NAV_ITEMS,
            on_navigate=self.navigate,
            on_toggle_theme=self.toggle_theme,
            on_toggle_collapse=lambda expanded: setattr(self._state, "sidebar_expanded", expanded),
            expanded=self._state.sidebar_expanded,
        )
        self.sidebar.grid(row=0, column=0, sticky="nsw")

        self.content = ctk.CTkFrame(self, fg_color="transparent", width=0, height=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self._update_sidebar_status()

    def _bind_shortcuts(self) -> None:
        """Привязывает горячие клавиши."""
        bindings: dict[str, Callable[[], None]] = {
            "<Control-o>": lambda: self._dashboard().browse_order(),
            "<Control-d>": lambda: self._dashboard().browse_certificates(),
            "<Control-Return>": lambda: self._dashboard().run_processing(),
            "<F5>": lambda: self._dashboard().reindex(),
            "<Control-f>": self.focus_search,
            "<Control-t>": self.toggle_theme,
            "<Control-l>": lambda: self.navigate("logs"),
            "<Control-s>": lambda: self.navigate("settings"),
            "<Control-b>": lambda: self.sidebar.toggle_collapse(),
            "<F1>": self.show_shortcuts,
            "<Escape>": self._handle_escape,
        }
        for sequence, handler in bindings.items():
            self.bind_all(sequence, lambda _, action=handler: _safe_call(action))

        for index, item in enumerate(NAV_ITEMS, start=1):
            self.bind_all(
                f"<Control-Key-{index}>",
                lambda _, key=item.key: self.navigate(key),
            )

    def _enable_dnd(self) -> None:
        """Подключает перетаскивание файлов в окно."""
        if not dnd.enable_dnd(self):
            _LOGGER.info("Перетаскивание файлов недоступно — используйте выбор через диалог")
            return

        def _on_drop(paths: list[Path]) -> None:
            order = next(
                (
                    path
                    for path in paths
                    if path.is_file() and path.suffix.lower() in EXCEL_EXTENSIONS
                ),
                None,
            )
            directory = next((path for path in paths if path.is_dir()), None)
            if order is None and directory is None:
                self.toasts.warning("Перетащите файл заказа (.xlsx) или папку с сертификатами")
                return
            self.navigate("dashboard")
            self._dashboard().set_paths(order=order, certificates=directory)

        dnd.register_drop_target(self, _on_drop)

    # -------------------------------------------------------------- навигация
    def navigate(self, key: str, *, action: str = "") -> None:
        """Переключает активный раздел.

        Args:
            key: Идентификатор раздела.
            action: Дополнительное действие, выполняемое после перехода.
        """
        if key not in VIEW_CLASSES:
            return

        if self._active_view and self._active_view in self._views:
            try:
                self._views[self._active_view].on_hide()
                self._views[self._active_view].grid_forget()
            except Exception:
                pass

        view = self._views.get(key)
        if view is None:
            view = VIEW_CLASSES[key](self.content, self)
            self._views[key] = view

        view.grid(row=0, column=0, sticky="nsew")
        view.ensure_built()
        view.on_show()

        self._active_view = key
        self._state.active_view = key
        self.sidebar.set_active(key)
        self._animate_view_in(view)

        if action == "reindex":
            self._dashboard().reindex()
        elif action == "reindex_force":
            self._dashboard().reindex(force=True)

    def rebuild_view(self, key: str) -> None:
        """Пересоздаёт раздел (после сброса настроек).

        Args:
            key: Идентификатор раздела.
        """
        view = self._views.pop(key, None)
        if view is not None:
            try:
                view.destroy()
            except Exception:
                pass
        if self._active_view == key:
            self.navigate(key)

    def _animate_view_in(self, view: BaseView) -> None:
        """Показывает раздел с лёгким сдвигом."""
        if not self.animator.enabled:
            return

        def _apply(value: float) -> None:
            try:
                view.grid_configure(pady=(int(value), 0))
            except Exception:
                pass

        self.animator.animate(
            self, f"view-{id(view)}", start=14.0, end=0.0, duration=0.18, on_frame=_apply
        )

    def _dashboard(self) -> DashboardView:
        """Возвращает раздел подбора, создавая его при необходимости."""
        view = self._views.get("dashboard")
        if view is None:
            view = DashboardView(self.content, self)
            self._views["dashboard"] = view
            view.ensure_built()
        return view

    def focus_search(self) -> None:
        """Передаёт фокус строке поиска активного раздела.

        Разделы без собственного поиска (например, «Подбор») унаследованно
        ничего не делают — тогда фокус передаётся в справочник сертификатов,
        где строка поиска есть всегда.
        """
        view = self._views.get(self._active_view)
        if view is not None and type(view).focus_search is not BaseView.focus_search:
            view.focus_search()
            return
        self.navigate("certificates")
        self._views["certificates"].focus_search()

    def _handle_escape(self) -> None:
        """Отменяет активную операцию по клавише Esc."""
        if self.tasks.active_tasks:
            self._dashboard().cancel_processing()

    # ----------------------------------------------------------------- тема
    def toggle_theme(self) -> None:
        """Переключает светлое и тёмное оформление."""
        mode = self.theme.toggle_mode()
        self.settings_service.update(lambda settings: setattr(settings.ui, "theme", mode))
        self._on_theme_changed()

    def apply_theme(self, *, mode: str | None = None, palette: str | None = None) -> None:
        """Применяет тему и палитру.

        Args:
            mode: Режим оформления.
            palette: Идентификатор палитры.
        """
        self.theme.apply(mode=mode, palette_name=palette)
        if palette is not None:
            icons.clear()
        self._on_theme_changed()

    def _on_theme_changed(self) -> None:
        """Обновляет виджеты, которые CustomTkinter не перекрашивает сам."""
        try:
            self.configure(fg_color=self.theme.color("background"))
            self.sidebar.refresh_theme()
            for view in self._views.values():
                view.refresh_theme()
        except Exception:
            _LOGGER.debug("Ошибка обновления темы", exc_info=True)

    def apply_scaling(self, value: float) -> None:
        """Меняет масштаб интерфейса.

        Args:
            value: Коэффициент масштабирования.
        """
        try:
            ctk.set_widget_scaling(value)
        except Exception:
            pass

    def apply_settings(self) -> None:
        """Применяет конфигурацию целиком (после импорта или сброса)."""
        settings = self.settings
        self.animator.set_enabled(settings.ui.animations)
        self.toasts.set_enabled(settings.ui.notifications)
        self.apply_scaling(settings.ui.scaling)
        self.apply_theme(mode=settings.ui.theme, palette=settings.ui.accent)

    # ----------------------------------------------------------- общие службы
    def submit_background(self, work: Callable[[], Any], on_done: Callable[[Any], None]) -> None:
        """Выполняет короткую операцию в фоне и возвращает результат в интерфейс.

        Args:
            work: Функция без аргументов.
            on_done: Обработчик результата.
        """
        self.tasks.run(
            f"inline-{id(work)}",
            lambda _: work(),
            on_success=on_done,
            on_error=lambda error: _LOGGER.debug("Фоновая операция не выполнена: %s", error),
        )

    def open_path(self, path: Path) -> None:
        """Открывает файл или папку средствами операционной системы.

        Args:
            path: Путь к объекту.
        """
        if not path.exists():
            self.toasts.warning(f"Объект не найден: {path.name}")
            return
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", str(path)], check=False)
            else:
                subprocess.run(["xdg-open", str(path)], check=False)
        except Exception:
            self.toasts.warning("Не удалось открыть объект средствами системы")

    def preview_pdf(self, path: Path) -> None:
        """Показывает сертификат во встроенном просмотрщике.

        Args:
            path: Путь к PDF-файлу.
        """
        if not path.exists():
            self.toasts.warning(f"Файл сертификата не найден: {path.name}")
            return
        self.navigate("certificates")
        view = self._views.get("certificates")
        opener = getattr(view, "open_certificate", None)
        if callable(opener):
            opener(path)

    def show_error(self, title: str, message: str, details: str = "") -> None:
        """Показывает диалог с ошибкой.

        Args:
            title: Заголовок.
            message: Описание проблемы.
            details: Технические подробности.
        """
        show_message(self, self.theme, title=title, message=message, level="error", details=details)

    def show_about(self) -> None:
        """Открывает окно «О программе»."""
        AboutDialog(self, self.theme, diagnostics=self.container.diagnostics())

    def show_shortcuts(self) -> None:
        """Открывает справку по горячим клавишам."""
        ShortcutsDialog(self, self.theme)

    def _update_sidebar_status(self) -> None:
        """Обновляет строку состояния боковой панели."""
        try:
            indexed = self.container.indexing_service.last_indexed_at()
            count = self.container.certificate_repository.count("is_active = 1")
            text = f"Сертификатов: {count}"
            if indexed:
                text += f"\nОбновлено: {indexed}"
            self.sidebar.set_status(text)
        except Exception:
            pass

    # ------------------------------------------------------------- запуск
    def _post_startup(self) -> None:
        """Выполняет действия после появления окна на экране."""
        settings = self.settings

        if settings.ui.last_order_file:
            path = Path(settings.ui.last_order_file)
            if path.exists():
                self._dashboard().set_paths(order=path)

        if self.container.indexing_service.needs_initial_scan():
            self._offer_initial_scan()
        elif settings.indexing.rescan_on_start:
            directory = self.container.indexing_service.last_directory()
            if directory and Path(directory).is_dir():
                self._dashboard().reindex(silent=True)

        if self.container.start_watcher():
            _LOGGER.info("Наблюдение за папкой сертификатов активно")

        self.container.events.subscribe("index.auto_updated", self._on_auto_index)
        self._update_sidebar_status()

    def _offer_initial_scan(self) -> None:
        """Предлагает выполнить первичное сканирование справочника."""
        stored = self.container.indexing_service.last_directory()
        if stored and Path(stored).is_dir():
            self._dashboard().reindex()
            return

        self.toasts.info(
            "Укажите папку с PDF-сертификатами — программа прочитает их один раз "
            "и дальше будет обновлять только новые файлы.",
            title="Первый запуск",
            duration=12.0,
            action_text="Выбрать папку",
            on_action=lambda: self._dashboard().browse_certificates(),
        )

    def _on_auto_index(self, indexed: int = 0, removed: int = 0, **_: Any) -> None:
        """Реагирует на автоматическое обновление справочника."""

        def _notify() -> None:
            parts = []
            if indexed:
                parts.append(f"добавлено {indexed}")
            if removed:
                parts.append(f"удалено {removed}")
            if parts:
                self.toasts.info(
                    "Справочник обновлён: " + ", ".join(parts), title="Папка сертификатов"
                )
            self._update_sidebar_status()
            dashboard = self._views.get("dashboard")
            if dashboard is not None:
                dashboard.refresh()

        try:
            self.after(0, _notify)
        except Exception:
            pass

    # ------------------------------------------------------------- завершение
    def on_close(self) -> None:
        """Обрабатывает закрытие окна."""
        if self._closing:
            return

        if self.tasks.active_tasks and not ask_confirmation(
            self,
            self.theme,
            title="Выполняется операция",
            message="Прервать выполняющуюся операцию и закрыть программу?",
            detail="Незавершённая обработка не будет сохранена.",
            confirm_text="Закрыть",
            danger=True,
        ):
            return

        if self.settings.ui.confirm_on_exit and not ask_confirmation(
            self, self.theme, title="Выход", message="Закрыть программу?", confirm_text="Закрыть"
        ):
            return

        self._closing = True
        try:
            if self.settings.ui.remember_window_state:
                state = self._state_store.capture(
                    self,
                    sidebar_expanded=self.sidebar.expanded,
                    active_view=self._active_view,
                )
                self._state_store.save(state)
        except Exception:
            _LOGGER.debug("Состояние окна не сохранено", exc_info=True)

        try:
            self.tasks.cancel_all()
            self.animator.stop_all()
            self.container.shutdown()
        except Exception:
            _LOGGER.debug("Ошибка при завершении работы", exc_info=True)

        _LOGGER.info("Приложение закрыто")
        self.destroy()


def _safe_call(action: Callable[[], None]) -> str:
    """Вызывает обработчик горячей клавиши, подавляя исключения.

    Args:
        action: Обработчик.

    Returns:
        ``"break"``, чтобы событие не обрабатывалось дальше.
    """
    try:
        action()
    except Exception:
        _LOGGER.exception("Ошибка обработчика горячей клавиши")
    return "break"


def run_gui(container: ApplicationContainer) -> int:
    """Запускает графический интерфейс.

    Args:
        container: Контейнер зависимостей.

    Returns:
        Код возврата процесса.
    """
    window = ApplicationWindow(container)
    window.mainloop()
    return 0
