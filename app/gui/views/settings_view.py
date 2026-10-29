"""Раздел настроек приложения.

Настройки применяются немедленно и сохраняются на диск с небольшой задержкой:
пользователь видит результат сразу, а частые изменения (перетаскивание
ползунка) не приводят к десяткам записей файла.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import customtkinter as ctk

from app.config.settings import AppSettings
from app.gui.theme import FontRole, Radius, Spacing
from app.gui.views.base_view import BaseView
from app.gui.widgets.base import format_bytes
from app.gui.widgets.card import SectionCard
from app.gui.widgets.controls import Badge, ghost_button, secondary_button
from app.gui.widgets.dialogs import ask_confirmation

_LOGGER = logging.getLogger(__name__)

#: Задержка перед записью настроек на диск, мс.
_SAVE_DELAY_MS = 600

#: Имя фоновой задачи импорта базы сроков годности.
_TASK_IMPORT_EXPIRY = "import-expiry-stock"


class SettingsView(BaseView):
    """Настройки алгоритма, индексации, результата и интерфейса."""

    title = "Настройки"
    subtitle = "Веса подбора, пороги принятия решений, оформление результата и обслуживание базы"

    def __init__(self, master: Any, app: Any, **kwargs: Any) -> None:
        """Создаёт раздел.

        Args:
            master: Родительский виджет.
            app: Главное окно приложения.
            **kwargs: Дополнительные параметры ``CTkFrame``.
        """
        super().__init__(master, app, **kwargs)
        self._save_after: str | None = None
        self._weight_labels: dict[str, ctk.CTkLabel] = {}
        self._semantic_badge: Badge | None = None

    # ---------------------------------------------------------------- разметка
    def build(self) -> None:
        """Создаёт содержимое раздела."""
        ghost_button(
            self.actions,
            self.theme,
            text="Сбросить к заводским",
            icon="refresh",
            command=self._reset,
        ).pack(side="right")

        self._scroll = ctk.CTkScrollableFrame(self.content, fg_color=self.theme.color("background"))
        self._scroll.pack(fill="both", expand=True)

        self._build_matching_section()
        self._build_certificates_section()
        self._build_expiry_stock_section()
        self._build_export_section()
        self._build_interface_section()
        self._build_maintenance_section()

    @property
    def _settings(self) -> AppSettings:
        """Текущая конфигурация приложения."""
        return self.app.settings

    def _card(self, title: str, subtitle: str, icon: str) -> SectionCard:
        """Создаёт карточку группы настроек."""
        card = SectionCard(
            self._scroll,
            self.theme,
            title=title,
            subtitle=subtitle,
            icon=icon,
            animator=self.app.animator,
        )
        card.pack(fill="x", pady=(0, Spacing.LG))
        return card

    def _subgroup(self, master: Any, title: str) -> ctk.CTkFrame:
        """Создаёт именованный подблок настроек на фоне ``surface_alt``.

        Группирует несколько родственных строк внутри карточки — например,
        «что создавать» отдельно от «названия колонок» в результате
        обработки, вместо одного плоского списка переключателей.

        Returns:
            Внутренний контейнер с отступами — строки настроек пакуются в
            него, как и в ``card.content`` самой карточки.
        """
        container = ctk.CTkFrame(
            master, fg_color=self.theme.color("surface_alt"), corner_radius=Radius.MD
        )
        container.pack(fill="x", pady=(0, Spacing.MD))
        ctk.CTkLabel(
            container,
            text=title.upper(),
            font=self.theme.font(FontRole.CAPTION, mono=True),
            text_color=self.theme.color("text_muted"),
            anchor="w",
        ).pack(fill="x", anchor="w", padx=Spacing.MD, pady=(Spacing.MD, 0))

        body = ctk.CTkFrame(container, fg_color="transparent", width=0, height=0)
        body.pack(fill="x", padx=Spacing.MD, pady=(0, Spacing.SM))
        return body

    # ------------------------------------------------------------- подбор
    def _build_matching_section(self) -> None:
        """Создаёт группу настроек алгоритма подбора."""
        card = self._card(
            "Алгоритм подбора",
            "Весовые коэффициенты определяют, что важнее при выборе сертификата",
            "sparkles",
        )
        matching = self._settings.matching

        weights = ctk.CTkFrame(
            card.content, fg_color=self.theme.color("surface_alt"), corner_radius=Radius.MD
        )
        weights.pack(fill="x", pady=(0, Spacing.MD))

        for key, label, initial in (
            ("weight_name", "Совпадение наименования", matching.weight_name),
            ("weight_volume", "Совпадение объёма", matching.weight_volume),
            ("weight_expiry", "Соответствие срока", matching.weight_expiry),
        ):
            self._weight_row(weights, key, label, initial)

        self._weights_hint = ctk.CTkLabel(
            weights,
            text="",
            font=self.theme.font(FontRole.CAPTION),
            text_color=self.theme.color("text_muted"),
        )
        self._weights_hint.pack(anchor="w", padx=Spacing.MD, pady=(0, Spacing.MD))
        self._update_weights_hint()

        self._slider_row(
            card.content,
            "Порог автоматического принятия",
            "Ниже этого значения программа спросит подтверждение",
            matching.auto_accept_threshold,
            0.5,
            1.0,
            lambda value: self._set("matching", "auto_accept_threshold", value),
            percent=True,
        )
        self._slider_row(
            card.content,
            "Порог «не найдено»",
            "Кандидаты с меньшей оценкой отбрасываются",
            matching.review_threshold,
            0.2,
            0.9,
            lambda value: self._set("matching", "review_threshold", value),
            percent=True,
        )
        self._slider_row(
            card.content,
            "Минимальный отрыв лидера",
            "Меньший отрыв от второго варианта считается неоднозначностью",
            matching.ambiguity_margin,
            0.0,
            0.3,
            lambda value: self._set("matching", "ambiguity_margin", value),
            percent=True,
        )
        self._slider_row(
            card.content,
            "Допустимая разница сроков, дней",
            "Используется, когда в заказе указан требуемый срок годности",
            float(matching.expiry_tolerance_days),
            0.0,
            720.0,
            lambda value: self._set("matching", "expiry_tolerance_days", int(value)),
            fmt=lambda value: f"{int(value)} дн.",
        )

        self._switch_row(
            card.content,
            "Строгое совпадение объёма",
            "Сертификат на 150 мл не подтверждает товар 100 мл",
            matching.strict_volume_match,
            lambda value: self._set("matching", "strict_volume_match", value),
        )
        self._switch_row(
            card.content,
            "Исключать просроченные сертификаты",
            "Сертификаты с истёкшим сроком не предлагаются",
            matching.require_valid_expiry,
            lambda value: self._set("matching", "require_valid_expiry", value),
        )
        self._switch_row(
            card.content,
            "Автовыбор ближайшего срока",
            "Если варианты различаются только сроком — выбирать ближайший без вопросов",
            matching.auto_resolve_duplicates,
            lambda value: self._set("matching", "auto_resolve_duplicates", value),
        )
        badge_text, badge_role = self._semantic_badge_state()
        self._semantic_badge = self._switch_row(
            card.content,
            "Семантический поиск (ИИ)",
            self.app.container.embedding_backend.status().message,
            matching.use_semantic,
            self._toggle_semantic,
            badge_text=badge_text,
            badge_role=badge_role,
        )

    def _weight_row(self, master: Any, key: str, label: str, initial: float) -> None:
        """Создаёт строку настройки весового коэффициента."""
        row = ctk.CTkFrame(master, fg_color="transparent", width=0, height=0)
        row.pack(fill="x", padx=Spacing.MD, pady=(Spacing.MD, 0))

        ctk.CTkLabel(
            row,
            text=label,
            font=self.theme.font(FontRole.BODY),
            text_color=self.theme.color("text"),
            anchor="w",
            width=220,
        ).pack(side="left")

        value_label = ctk.CTkLabel(
            row,
            text=f"{initial * 100:.0f} %",
            font=self.theme.font(FontRole.BODY_STRONG),
            text_color=self.theme.color("accent"),
            width=54,
        )
        value_label.pack(side="right")
        self._weight_labels[key] = value_label

        slider = ctk.CTkSlider(
            row,
            from_=0.0,
            to=1.0,
            number_of_steps=100,
            progress_color=self.theme.color("accent"),
            button_color=self.theme.color("accent"),
            button_hover_color=self.theme.color("accent_hover"),
            fg_color=self.theme.color("surface_hover"),
        )
        slider.set(initial)
        slider.configure(command=lambda value, item=key: self._on_weight(item, value))
        slider.pack(side="left", fill="x", expand=True, padx=Spacing.MD)

    def _on_weight(self, key: str, value: float) -> None:
        """Применяет изменение весового коэффициента."""
        self._set("matching", key, round(float(value), 3))
        label = self._weight_labels.get(key)
        if label is not None:
            label.configure(text=f"{value * 100:.0f} %")
        self._update_weights_hint()

    def _update_weights_hint(self) -> None:
        """Показывает нормированные веса."""
        name, volume, expiry = self._settings.matching.normalized_weights()
        try:
            self._weights_hint.configure(
                text=(
                    f"Фактический вклад после нормировки: наименование {name * 100:.0f} %, "
                    f"объём {volume * 100:.0f} %, срок {expiry * 100:.0f} %"
                )
            )
        except Exception:
            pass

    def _toggle_semantic(self, value: bool) -> None:
        """Включает или выключает семантический поиск."""
        self._set("matching", "use_semantic", value)
        self.app.container.embedding_backend.set_enabled(value)
        self.app.container.matching_service.invalidate()
        if value and not self.app.container.embedding_backend.library_available():
            self.app.toasts.warning(
                "Пакет sentence-transformers не установлен. Подбор продолжит работать "
                "на нечётком поиске и соответствиях.",
                title="Семантический поиск недоступен",
            )
        if self._semantic_badge is not None:
            text, role = self._semantic_badge_state()
            self._semantic_badge.update_state(text, role)

    def _semantic_badge_state(self) -> tuple[str, str]:
        """Определяет надпись и роль бейджа статуса семантического поиска."""
        status = self.app.container.embedding_backend.status()
        if not status.available:
            return "недоступно", "muted"
        if not self._settings.matching.use_semantic:
            return "выключено", "muted"
        if status.failed:
            return "ошибка загрузки", "danger"
        if status.loaded:
            return "активно", "success"
        return "загрузится при использовании", "warning"

    # ------------------------------------------------------ база сертификатов
    def _build_certificates_section(self) -> None:
        """Создаёт группу настроек источника данных о сертификатах."""
        card = self._card(
            "База сертификатов",
            "Excel — единственный источник данных; PDF используются только для копирования",
            "database",
        )
        certificates = self._settings.certificates

        self._path_row(
            card.content,
            "Файл базы сертификатов",
            "Excel: порядковый номер, наименование, срок годности, номер сертификата",
            certificates.excel_path,
            lambda value: self._set("certificates", "excel_path", value),
            file_mode=True,
        )
        self._path_row(
            card.content,
            "Папка с PDF-файлами",
            "Используется только для копирования найденного сертификата в результат",
            certificates.pdf_dir,
            lambda value: self._set("certificates", "pdf_dir", value),
        )
        self._switch_row(
            card.content,
            "Проверять изменения при запуске",
            "Если Excel-файл изменился со времени последнего импорта — переимпортировать его",
            certificates.rescan_on_start,
            lambda value: self._set("certificates", "rescan_on_start", value),
        )
        self._switch_row(
            card.content,
            "Искать PDF во вложенных папках",
            "Учитывать сертификаты в подпапках при поиске по номеру",
            certificates.recursive_pdf_search,
            lambda value: self._set("certificates", "recursive_pdf_search", value),
        )

        buttons = ctk.CTkFrame(card.content, fg_color="transparent", width=0, height=0)
        buttons.pack(fill="x", pady=(Spacing.SM, 0))
        secondary_button(
            buttons,
            self.theme,
            text="Импортировать заново",
            icon="refresh",
            command=lambda: self.app.navigate("dashboard", action="reimport"),
        ).pack(side="left")

    # ------------------------------------------------------- база сроков годности
    def _build_expiry_stock_section(self) -> None:
        """Создаёт группу настроек источника данных о сроках годности и остатках."""
        card = self._card(
            "База сроков годности",
            "Отдельная Excel-таблица остатков — используется, чтобы подобрать "
            "срок годности ДО поиска сертификата (этап выполняется автоматически)",
            "chart",
        )
        expiry_stock = self._settings.expiry_stock

        self._path_row(
            card.content,
            "Файл базы сроков годности",
            "Excel: полное системное название товара, срок годности, количество",
            expiry_stock.excel_path,
            lambda value: self._set("expiry_stock", "excel_path", value),
            file_mode=True,
        )
        self._switch_row(
            card.content,
            "Проверять изменения при запуске",
            "Если Excel-файл изменился со времени последнего импорта — переимпортировать его",
            expiry_stock.rescan_on_start,
            lambda value: self._set("expiry_stock", "rescan_on_start", value),
        )

        self._expiry_stock_label = ctk.CTkLabel(
            card.content,
            text="",
            font=self.theme.font(FontRole.CAPTION),
            text_color=self.theme.color("text_muted"),
            anchor="w",
            justify="left",
        )
        self._expiry_stock_label.pack(fill="x", pady=(Spacing.MD, Spacing.SM))
        self._update_expiry_stock_label()

        buttons = ctk.CTkFrame(card.content, fg_color="transparent", width=0, height=0)
        buttons.pack(fill="x", pady=(Spacing.SM, 0))
        self._expiry_import_button = secondary_button(
            buttons,
            self.theme,
            text="Импортировать заново",
            icon="refresh",
            command=self._reimport_expiry_stock,
        )
        self._expiry_import_button.pack(side="left")

    def _update_expiry_stock_label(self) -> None:
        """Обновляет сводку о состоянии базы сроков годности."""
        try:
            stats = self.app.container.expiry_stock_repository.statistics()
            imported_at = self.app.container.expiry_import_service.last_imported_at()
            text = (
                f"Партий: {stats.get('total', 0)} · "
                f"уникальных товаров: {stats.get('unique_products', 0)}"
            )
            text += (
                f" · последний импорт {imported_at}" if imported_at else " · импорт не выполнялся"
            )
            self._expiry_stock_label.configure(text=text)
        except Exception:
            pass

    def _reimport_expiry_stock(self) -> None:
        """Запускает (пере)импорт Excel-базы сроков годности в фоновом потоке."""
        path_text = self._settings.expiry_stock.excel_path
        path = Path(path_text) if path_text else None
        if path is None or not path.is_file():
            self.app.toasts.warning("Сначала выберите файл базы сроков годности")
            return
        if self.app.tasks.is_running(_TASK_IMPORT_EXPIRY):
            self.app.toasts.info("Импорт уже выполняется")
            return

        service = self.app.container.expiry_import_service
        try:
            self._expiry_import_button.configure(state="disabled")
        except Exception:
            pass

        def _work(_reporter: Any) -> Any:
            return service.import_file(path)

        def _done(result: Any) -> None:
            self._update_expiry_stock_label()
            summary = result.summary("База сроков годности")
            if result.failed:
                self.app.toasts.warning(summary, title="Импорт не выполнен")
            else:
                self.app.toasts.success(summary, title="База сроков годности обновлена")

        def _error(error: Exception) -> None:
            self.app.show_error("Импорт базы сроков годности не выполнен", str(error))

        def _finished() -> None:
            try:
                self._expiry_import_button.configure(state="normal")
            except Exception:
                pass

        self.app.tasks.run(
            _TASK_IMPORT_EXPIRY,
            _work,
            on_success=_done,
            on_error=_error,
            on_finally=_finished,
        )

    # -------------------------------------------------------------- результат
    def _build_export_section(self) -> None:
        """Создаёт группу настроек формирования результата."""
        card = self._card(
            "Результат обработки",
            "Что программа создаёт после подбора",
            "excel",
        )
        export = self._settings.export

        self._path_row(
            card.content,
            "Папка результатов",
            "Пусто — сохранять рядом с файлом заказа",
            export.output_dir,
            lambda value: self._set("export", "output_dir", value),
        )

        creation = self._subgroup(card.content, "Что создавать")
        self._switch_row(
            creation,
            "Копировать PDF сертификатов",
            "Создавать папку Certificates рядом с итоговым файлом",
            export.copy_certificates,
            lambda value: self._set("export", "copy_certificates", value),
        )
        self._switch_row(
            creation,
            "Подсвечивать строки в Excel",
            "Зелёный — найдено, жёлтый — требует проверки, красный — не найдено",
            export.highlight_rows,
            lambda value: self._set("export", "highlight_rows", value),
        )
        self._switch_row(
            creation,
            "Формировать отчёт",
            "Отдельная книга со сводкой и детализацией по каждой позиции",
            export.write_report,
            lambda value: self._set("export", "write_report", value),
        )
        self._switch_row(
            creation,
            "Добавлять колонку с оценкой",
            "Служебная колонка с процентом совпадения",
            export.add_score_column,
            lambda value: self._set("export", "add_score_column", value),
        )
        self._switch_row(
            creation,
            "Открывать папку после обработки",
            "Сразу показывать результат в проводнике",
            export.open_output_after_run,
            lambda value: self._set("export", "open_output_after_run", value),
        )
        self._entry_row(
            creation,
            "Суффикс имени файла",
            export.filename_suffix,
            lambda value: self._set("export", "filename_suffix", value),
        )

        titles = self._subgroup(card.content, "Названия колонок")
        self._entry_row(
            titles,
            "Заголовок колонки номера сертификата",
            export.certificate_column_title,
            lambda value: self._set("export", "certificate_column_title", value),
        )
        self._entry_row(
            titles,
            "Заголовок колонки срока сертификата",
            export.expiry_column_title,
            lambda value: self._set("export", "expiry_column_title", value),
        )

    # -------------------------------------------------------------- интерфейс
    def _build_interface_section(self) -> None:
        """Создаёт группу настроек интерфейса."""
        card = self._card("Интерфейс", "Оформление и поведение окна", "settings")
        ui = self._settings.ui

        self._option_row(
            card.content,
            "Тема оформления",
            ["Как в системе", "Светлая", "Тёмная"],
            {"system": "Как в системе", "light": "Светлая", "dark": "Тёмная"}[ui.theme],
            self._change_theme,
        )
        self._option_row(
            card.content,
            "Акцентный цвет",
            ["Изумрудный", "Сапфировый"],
            {"emerald": "Изумрудный", "sapphire": "Сапфировый"}.get(ui.accent, "Изумрудный"),
            self._change_palette,
        )
        self._slider_row(
            card.content,
            "Масштаб интерфейса",
            "Для мониторов с высоким разрешением",
            ui.scaling,
            0.8,
            1.6,
            self._change_scaling,
            fmt=lambda value: f"{value * 100:.0f} %",
        )
        self._switch_row(
            card.content,
            "Анимации",
            "Отключите на слабых машинах и в удалённых сессиях",
            ui.animations,
            self._toggle_animations,
        )
        self._switch_row(
            card.content,
            "Всплывающие уведомления",
            "Сообщения о завершении операций в углу окна",
            ui.notifications,
            self._toggle_notifications,
        )
        self._switch_row(
            card.content,
            "Запоминать размер окна",
            "Восстанавливать положение и размеры при следующем запуске",
            ui.remember_window_state,
            lambda value: self._set("ui", "remember_window_state", value),
        )

    def _change_theme(self, label: str) -> None:
        """Применяет выбранную тему оформления."""
        mode = {"Как в системе": "system", "Светлая": "light", "Тёмная": "dark"}[label]
        self._set("ui", "theme", mode)
        self.app.apply_theme(mode=mode)

    def _change_palette(self, label: str) -> None:
        """Применяет выбранную палитру."""
        palette = {"Изумрудный": "emerald", "Сапфировый": "sapphire"}[label]
        self._set("ui", "accent", palette)
        self.app.apply_theme(palette=palette)

    def _change_scaling(self, value: float) -> None:
        """Меняет масштаб интерфейса."""
        self._set("ui", "scaling", round(float(value), 2))
        self.app.apply_scaling(float(value))

    def _toggle_animations(self, value: bool) -> None:
        """Включает или выключает анимации."""
        self._set("ui", "animations", value)
        self.app.animator.set_enabled(value)

    def _toggle_notifications(self, value: bool) -> None:
        """Включает или выключает уведомления."""
        self._set("ui", "notifications", value)
        self.app.toasts.set_enabled(value)

    # ------------------------------------------------------------ обслуживание
    def _build_maintenance_section(self) -> None:
        """Создаёт группу настроек обслуживания."""
        card = self._card(
            "Обслуживание базы",
            "Резервные копии, журналы и служебные операции",
            "shield",
        )
        maintenance = self._settings.maintenance

        self._switch_row(
            card.content,
            "Автоматическая резервная копия",
            "Копия базы создаётся не чаще одного раза в сутки при запуске",
            maintenance.auto_backup,
            lambda value: self._set("maintenance", "auto_backup", value),
        )
        self._slider_row(
            card.content,
            "Хранить копий",
            "Более старые копии удаляются автоматически",
            float(maintenance.backup_retention),
            1.0,
            50.0,
            lambda value: self._set("maintenance", "backup_retention", int(value)),
            fmt=lambda value: f"{int(value)}",
        )
        self._option_row(
            card.content,
            "Уровень журналирования",
            ["DEBUG", "INFO", "WARNING", "ERROR"],
            maintenance.log_level,
            self._change_log_level,
        )

        self._database_label = ctk.CTkLabel(
            card.content,
            text="",
            font=self.theme.font(FontRole.CAPTION),
            text_color=self.theme.color("text_muted"),
            anchor="w",
            justify="left",
        )
        self._database_label.pack(fill="x", pady=(Spacing.MD, Spacing.SM))
        self._update_database_label()

        buttons = ctk.CTkFrame(card.content, fg_color="transparent", width=0, height=0)
        buttons.pack(fill="x")

        secondary_button(
            buttons, self.theme, text="Создать копию", icon="download", command=self._backup
        ).pack(side="left")
        secondary_button(
            buttons, self.theme, text="Восстановить", icon="upload", command=self._restore
        ).pack(side="left", padx=(Spacing.SM, 0))
        ghost_button(
            buttons, self.theme, text="Очистить кэш", icon="trash", command=self._clear_cache
        ).pack(side="right")

    def _update_database_label(self) -> None:
        """Обновляет сводку о состоянии базы."""
        try:
            stats = self.app.container.database.statistics()
            backup = self.app.container.backup_service.last_backup_at()
            text = (
                f"База: {format_bytes(int(stats.get('size_bytes', 0)))} · "
                f"сертификатов {stats.get('certificates', 0)} · "
                f"соответствий {stats.get('aliases', 0)} · "
                f"обработок {stats.get('history', 0)}"
            )
            if backup is not None:
                text += f" · последняя копия {backup:%d.%m.%Y %H:%M}"
            self._database_label.configure(text=text)
        except Exception:
            pass

    def _backup(self) -> None:
        """Создаёт резервную копию базы."""
        try:
            info = self.app.container.backup_service.create()
        except Exception as error:
            self.app.show_error("Резервная копия не создана", str(error))
            return
        self._update_database_label()
        self.app.toasts.success(
            f"Копия создана: {info.path.name}",
            action_text="Открыть папку",
            on_action=lambda: self.app.open_path(info.path.parent),
        )

    def _restore(self) -> None:
        """Восстанавливает базу из резервной копии."""
        from tkinter import filedialog

        backups = self.app.container.backup_service.directory
        source = filedialog.askopenfilename(
            title="Выберите резервную копию",
            initialdir=str(backups),
            filetypes=[("База данных", "*.db"), ("Все файлы", "*.*")],
        )
        if not source:
            return
        if not ask_confirmation(
            self.app,
            self.theme,
            title="Восстановление базы",
            message="Заменить текущую базу данных выбранной копией?",
            detail=(
                "Текущая база будет сохранена рядом с суффиксом .before-restore. "
                "После восстановления потребуется перезапуск программы."
            ),
            confirm_text="Восстановить",
            danger=True,
        ):
            return

        try:
            self.app.container.backup_service.restore(Path(source))
        except Exception as error:
            self.app.show_error("Восстановление не выполнено", str(error))
            return
        self.app.toasts.success("База восстановлена. Перезапустите программу.")

    def _clear_cache(self) -> None:
        """Очищает кэш и векторный индекс."""
        try:
            removed = self.app.container.cache_repository.clear_namespace("thumbnails")
            removed += self.app.container.cache_repository.clear_embeddings()
            self.app.container.vector_index.clear()
            self.app.container.matching_service.invalidate()
        except Exception as error:
            self.app.show_error("Не удалось очистить кэш", str(error))
            return
        self._update_database_label()
        self.app.toasts.success(f"Кэш очищен, удалено записей: {removed}")

    def _change_log_level(self, value: str) -> None:
        """Меняет уровень журналирования."""
        self._set("maintenance", "log_level", value)
        logging.getLogger().setLevel(getattr(logging, value, logging.INFO))
        for handler in logging.getLogger().handlers:
            if handler.__class__.__name__ == "RotatingFileHandler":
                handler.setLevel(getattr(logging, value, logging.INFO))

    def _reset(self) -> None:
        """Сбрасывает настройки к заводским значениям."""
        if not ask_confirmation(
            self.app,
            self.theme,
            title="Сброс настроек",
            message="Вернуть все настройки к заводским значениям?",
            detail="Соответствия, справочник сертификатов и история не пострадают.",
            confirm_text="Сбросить",
            danger=True,
        ):
            return
        self.app.settings_service.reset_to_defaults()
        self.app.apply_settings()
        self.app.toasts.success("Настройки сброшены")
        self.app.rebuild_view("settings")

    # ----------------------------------------------------- строительные блоки
    def _row(self, master: Any, title: str, description: str) -> ctk.CTkFrame:
        """Создаёт строку настройки с заголовком и описанием."""
        row = ctk.CTkFrame(master, fg_color="transparent", width=0, height=0)
        row.pack(fill="x", pady=Spacing.SM)

        texts = ctk.CTkFrame(row, fg_color="transparent", width=0, height=0)
        texts.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            texts,
            text=title,
            font=self.theme.font(FontRole.BODY),
            text_color=self.theme.color("text"),
            anchor="w",
        ).pack(fill="x", anchor="w")

        if description:
            ctk.CTkLabel(
                texts,
                text=description,
                font=self.theme.font(FontRole.CAPTION),
                text_color=self.theme.color("text_muted"),
                anchor="w",
                justify="left",
                wraplength=560,
            ).pack(fill="x", anchor="w")
        return row

    def _switch_row(
        self,
        master: Any,
        title: str,
        description: str,
        value: bool,
        on_change: Callable[[bool], None],
        *,
        badge_text: str = "",
        badge_role: str = "muted",
    ) -> Badge | None:
        """Создаёт строку с переключателем.

        Args:
            master: Родительский виджет.
            title: Заголовок строки.
            description: Пояснение под заголовком.
            value: Текущее значение.
            on_change: Обработчик изменения значения.
            badge_text: Надпись бейджа статуса рядом с переключателем;
                пустая строка — без бейджа.
            badge_role: Роль цвета бейджа (см. :class:`Badge`).

        Returns:
            Созданный бейдж — вызывающий код обновляет его при изменении
            состояния без пересборки строки; ``None``, если ``badge_text``
            не передан.
        """
        row = self._row(master, title, description)
        variable = ctk.BooleanVar(value=value)
        switch = ctk.CTkSwitch(
            row,
            text="",
            variable=variable,
            width=44,
            progress_color=self.theme.color("accent"),
            button_color=self.theme.color("surface"),
            fg_color=self.theme.color("surface_hover"),
            command=lambda: on_change(bool(variable.get())),
        )
        switch.pack(side="right", padx=(Spacing.MD, 0))

        if not badge_text:
            return None
        badge = Badge(row, self.theme, text=badge_text, role=badge_role)
        badge.pack(side="right", padx=(Spacing.MD, 0))
        return badge

    def _slider_row(
        self,
        master: Any,
        title: str,
        description: str,
        value: float,
        minimum: float,
        maximum: float,
        on_change: Callable[[float], None],
        *,
        percent: bool = False,
        fmt: Callable[[float], str] | None = None,
    ) -> None:
        """Создаёт строку с ползунком."""
        row = self._row(master, title, description)

        formatter = fmt or (
            (lambda item: f"{item * 100:.0f} %") if percent else (lambda item: f"{item:.2f}")
        )

        value_label = ctk.CTkLabel(
            row,
            text=formatter(value),
            font=self.theme.font(FontRole.BODY_STRONG),
            text_color=self.theme.color("accent"),
            width=64,
        )
        value_label.pack(side="right")

        slider = ctk.CTkSlider(
            row,
            from_=minimum,
            to=maximum,
            width=220,
            progress_color=self.theme.color("accent"),
            button_color=self.theme.color("accent"),
            button_hover_color=self.theme.color("accent_hover"),
            fg_color=self.theme.color("surface_hover"),
        )
        slider.set(value)

        def _on_slide(item: float) -> None:
            value_label.configure(text=formatter(item))
            on_change(item)

        slider.configure(command=_on_slide)
        slider.pack(side="right", padx=Spacing.MD)

    def _option_row(
        self,
        master: Any,
        title: str,
        options: list[str],
        current: str,
        on_change: Callable[[str], None],
    ) -> None:
        """Создаёт строку с выпадающим списком."""
        row = self._row(master, title, "")
        menu = ctk.CTkOptionMenu(
            row,
            values=options,
            width=190,
            command=on_change,
            font=self.theme.font(FontRole.SMALL),
            fg_color=self.theme.color("surface_alt"),
            button_color=self.theme.color("surface_hover"),
            button_hover_color=self.theme.color("accent_soft"),
            text_color=self.theme.color("text"),
            dropdown_fg_color=self.theme.color("surface"),
            dropdown_text_color=self.theme.color("text"),
            dropdown_hover_color=self.theme.color("accent_soft"),
            corner_radius=Radius.SM,
        )
        menu.set(current)
        menu.pack(side="right", padx=(Spacing.MD, 0))

    def _entry_row(
        self, master: Any, title: str, value: str, on_change: Callable[[str], None]
    ) -> None:
        """Создаёт строку с текстовым полем."""
        row = self._row(master, title, "")
        variable = ctk.StringVar(value=value)
        entry = ctk.CTkEntry(
            row,
            textvariable=variable,
            width=240,
            height=32,
            font=self.theme.font(FontRole.SMALL),
            fg_color=self.theme.color("surface_alt"),
            border_color=self.theme.color("border"),
            corner_radius=Radius.SM,
        )
        entry.pack(side="right", padx=(Spacing.MD, 0))
        variable.trace_add("write", lambda *_: on_change(variable.get()))

    def _path_row(
        self,
        master: Any,
        title: str,
        description: str,
        value: str,
        on_change: Callable[[str], None],
        *,
        file_mode: bool = False,
    ) -> None:
        """Создаёт строку выбора каталога или файла.

        Args:
            master: Родительский виджет.
            title: Заголовок строки (также заголовок системного диалога).
            description: Пояснение под заголовком.
            value: Текущее значение пути.
            on_change: Обработчик изменения значения.
            file_mode: Выбирать файл вместо каталога.
        """
        row = self._row(master, title, description)
        variable = ctk.StringVar(value=value)

        def _browse() -> None:
            from tkinter import filedialog

            if file_mode:
                selected = filedialog.askopenfilename(
                    title=title, filetypes=[("Excel", "*.xlsx *.xlsm"), ("Все файлы", "*.*")]
                )
            else:
                selected = filedialog.askdirectory(title=title)
            if selected:
                variable.set(selected)
                on_change(selected)

        secondary_button(row, self.theme, text="Выбрать", icon="folder", command=_browse).pack(
            side="right", padx=(Spacing.SM, 0)
        )
        entry = ctk.CTkEntry(
            row,
            textvariable=variable,
            width=260,
            height=32,
            font=self.theme.font(FontRole.SMALL),
            fg_color=self.theme.color("surface_alt"),
            border_color=self.theme.color("border"),
            corner_radius=Radius.SM,
            placeholder_text="Рядом с файлом заказа",
        )
        entry.pack(side="right")
        variable.trace_add("write", lambda *_: on_change(variable.get()))

    # ---------------------------------------------------------------- запись
    def _set(self, group: str, key: str, value: Any) -> None:
        """Изменяет настройку и планирует сохранение."""
        settings = self.app.settings
        target = getattr(settings, group, None)
        if target is None or not hasattr(target, key):
            return
        setattr(target, key, value)
        self._schedule_save()

    def _schedule_save(self) -> None:
        """Планирует отложенную запись настроек на диск."""
        if self._save_after is not None:
            try:
                self.after_cancel(self._save_after)
            except Exception:
                pass
        try:
            self._save_after = self.after(_SAVE_DELAY_MS, self._save)
        except Exception:
            pass

    def _save(self) -> None:
        """Записывает настройки на диск."""
        self._save_after = None
        try:
            self.app.settings_service.save()
        except Exception as error:
            _LOGGER.error("Не удалось сохранить настройки: %s", error)
            self.app.toasts.error("Не удалось сохранить настройки")

    def on_hide(self) -> None:
        """Сохраняет настройки при уходе из раздела."""
        if self._save_after is not None:
            self._save()

    def refresh_theme(self) -> None:
        """Обновляет цвета после смены темы.

        Прокручиваемая область строится с явным ``fg_color`` вместо
        ``"transparent"`` — у ``CTkScrollableFrame`` это не «настоящая»
        прозрачность, а разовое наследование цвета ближайшего непрозрачного
        предка на момент создания виджета; раз зафиксировав его, сам холст
        прокрутки за сменой темы потом не следит. Остальные виджеты раздела
        (карточки, ползунки, переключатели) не перекрашиваются даже сейчас —
        это общая черта всех разделов с карточками в этой версии программы,
        а не особенность настроек, и правится отдельной, более крупной
        задачей, а не здесь.
        """
        super().refresh_theme()
        try:
            self._scroll.configure(fg_color=self.theme.color("background"))
        except Exception:
            pass
