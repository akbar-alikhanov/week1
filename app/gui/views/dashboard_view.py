"""Главный раздел: подбор сертификатов для заказа.

Сценарий, ради которого написана программа, уместился в два действия: выбрать
файл заказа и нажать одну кнопку. Всё остальное на экране — обратная связь:
что происходит сейчас, что получилось и где лежит результат.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import customtkinter as ctk

from app.core.constants import EXCEL_EXTENSIONS
from app.core.events import ProgressReporter
from app.gui.theme import FontRole, Sizes, Spacing
from app.gui.views.base_view import BaseView
from app.gui.widgets.ambiguity_dialog import SKIP, AmbiguityDialog
from app.gui.widgets.base import format_duration
from app.gui.widgets.card import SectionCard, StatCard
from app.gui.widgets.controls import SegmentedFilter, ghost_button, primary_button, secondary_button
from app.gui.widgets.data_table import Column, DataTable
from app.gui.widgets.drop_zone import FileDropZone
from app.gui.widgets.expiry_suggestion_dialog import ExpirySuggestionDialog
from app.gui.widgets.progress_panel import ProgressPanel
from app.models.matching import MatchResult, MatchStatus
from app.services.expiry_resolution_service import ExpirySuggestion, ManualExpiryReview
from app.services.order_processing_service import ProcessingOutcome, ProcessingRequest

_LOGGER = logging.getLogger(__name__)

#: Имя фоновой задачи обработки заказа.
TASK_PROCESS = "process-order"

#: Имя фоновой задачи импорта базы сертификатов.
TASK_IMPORT = "import-certificates"


class DashboardView(BaseView):
    """Раздел подбора сертификатов."""

    title = "Подбор сертификатов"
    subtitle = "Выберите файл заказа и папку сертификатов — остальное программа сделает сама"

    def __init__(self, master: Any, app: Any, **kwargs: Any) -> None:
        """Создаёт раздел.

        Args:
            master: Родительский виджет.
            app: Главное окно приложения.
            **kwargs: Дополнительные параметры ``CTkFrame``.
        """
        super().__init__(master, app, **kwargs)
        self._order_path: Path | None = None
        self._database_path: Path | None = None
        self._outcome: ProcessingOutcome | None = None
        self._results: list[MatchResult] = []
        self._filter = "all"
        self._stat_cards: dict[str, StatCard] = {}

    # ---------------------------------------------------------------- разметка
    def build(self) -> None:
        """Создаёт содержимое раздела."""
        self._build_actions()
        self._build_stats()
        self._build_workspace()
        self._build_results()
        self.refresh()

    def _build_actions(self) -> None:
        """Создаёт кнопки в шапке раздела."""
        secondary_button(
            self.actions,
            self.theme,
            text="Импортировать заново",
            icon="refresh",
            command=self.reimport,
        ).pack(side="right")

    def _build_stats(self) -> None:
        """Создаёт полосу ключевых показателей."""
        row = ctk.CTkFrame(self.content, fg_color="transparent", width=0, height=0)
        row.pack(fill="x", pady=(0, Spacing.LG))
        for index in range(4):
            row.grid_columnconfigure(index, weight=1, uniform="stats")

        definitions = [
            ("certificates", "Сертификатов в базе", "certificate", "accent"),
            ("aliases", "Запомнено соответствий", "alias", "info"),
            ("processed", "Позиций за 30 дней", "chart", "success"),
            ("rate", "Успешность подбора", "shield", "success"),
        ]
        for column, (key, title, icon, role) in enumerate(definitions):
            card = StatCard(
                row,
                self.theme,
                title=title,
                icon=icon,
                accent_role=role,
                animator=self.app.animator,
            )
            card.grid(
                row=0, column=column, sticky="nsew", padx=(0 if column == 0 else Spacing.MD, 0)
            )
            self._stat_cards[key] = card

    def _build_workspace(self) -> None:
        """Создаёт зону выбора файлов и запуска обработки."""
        card = SectionCard(
            self.content,
            self.theme,
            title="Новая обработка",
            subtitle="Перетащите файлы или нажмите, чтобы выбрать",
            icon="play",
            animator=self.app.animator,
        )
        card.pack(fill="x")

        zones = ctk.CTkFrame(card.content, fg_color="transparent", width=0, height=0)
        zones.pack(fill="x")
        zones.grid_columnconfigure(0, weight=1, uniform="zones")
        zones.grid_columnconfigure(1, weight=1, uniform="zones")

        self._order_zone = FileDropZone(
            zones,
            self.theme,
            title="Файл заказа",
            hint="Excel-файл со списком товаров (.xlsx)",
            icon="excel",
            extensions=tuple(EXCEL_EXTENSIONS),
            on_selected=self._set_order,
            animator=self.app.animator,
            dialog_title="Выберите файл заказа",
        )
        self._order_zone.grid(row=0, column=0, sticky="nsew", padx=(0, Spacing.SM))

        self._database_zone = FileDropZone(
            zones,
            self.theme,
            title="База сертификатов",
            hint="Excel-файл: наименование, срок годности, номер сертификата",
            icon="database",
            extensions=tuple(EXCEL_EXTENSIONS),
            on_selected=self._set_database_path,
            animator=self.app.animator,
            dialog_title="Выберите файл базы сертификатов",
        )
        self._database_zone.grid(row=0, column=1, sticky="nsew", padx=(Spacing.SM, 0))

        controls = ctk.CTkFrame(card.content, fg_color="transparent", width=0, height=0)
        controls.pack(fill="x", pady=(Spacing.LG, 0))

        self._run_button = primary_button(
            controls,
            self.theme,
            text="Подобрать сертификаты",
            icon="sparkles",
            command=self.run_processing,
            height=Sizes.BUTTON_HEIGHT_LG,
            width=260,
        )
        self._run_button.pack(side="left")

        self._hint_label = ctk.CTkLabel(
            controls,
            text="Ctrl + Enter",
            font=self.theme.font(FontRole.CAPTION),
            text_color=self.theme.color("text_muted"),
        )
        self._hint_label.pack(side="left", padx=(Spacing.MD, 0))

        self._progress = ProgressPanel(
            card.content, self.theme, self.app.animator, on_cancel=self.cancel_processing
        )
        self._progress.pack(fill="x", pady=(Spacing.LG, 0))

        self._update_run_state()

    def _build_results(self) -> None:
        """Создаёт таблицу результатов последней обработки."""
        self._results_card = SectionCard(
            self.content,
            self.theme,
            title="Результат обработки",
            subtitle="Здесь появятся подобранные сертификаты",
            icon="certificate",
            animator=self.app.animator,
        )
        self._results_card.pack(fill="both", expand=True, pady=(Spacing.LG, 0))

        self._filter_control = SegmentedFilter(
            self._results_card.actions,
            self.theme,
            options=[
                ("all", "Все"),
                (MatchStatus.MATCHED.value, "Найдены"),
                (MatchStatus.AMBIGUOUS.value, "Проверить"),
                (MatchStatus.NOT_FOUND.value, "Не найдены"),
            ],
            on_change=self._apply_filter,
        )
        self._filter_control.pack(side="right")

        self._table = DataTable(
            self._results_card.content,
            self.theme,
            columns=(
                Column("row", "Строка", width=70, anchor="center", numeric=True),
                Column("product", "Товар из заказа", width=280, stretch=True),
                Column("status", "Статус", width=140),
                Column("certificate", "Сертификат", width=170),
                Column("expiry", "Срок", width=100, anchor="center"),
                Column("score", "Совпадение", width=100, anchor="center", numeric=True),
                Column("matched_product", "Товар в базе", width=220, stretch=True),
            ),
            on_activate=self._open_result_pdf,
            context_actions=(
                ("Открыть PDF сертификата", self._open_result_pdf),
                ("Изменить сертификат…", self._change_certificate),
                ("-", lambda _: None),
                ("Копировать наименование", self._copy_product_name),
            ),
            height=10,
        )
        self._table.pack(fill="both", expand=True)

        self._output_row = ctk.CTkFrame(
            self._results_card.content, fg_color="transparent", width=0, height=0
        )
        self._output_row.pack(fill="x", pady=(Spacing.MD, 0))

    # ------------------------------------------------------------- состояние
    def on_show(self) -> None:
        """Обновляет показатели при открытии раздела."""
        self.refresh()

    def refresh(self) -> None:
        """Перечитывает показатели и восстанавливает выбранные пути."""
        if not self._stat_cards:
            return

        container = self.app.container
        try:
            certificates = container.certificate_repository.statistics()
            history = container.history_repository.statistics()
            aliases = container.alias_repository.count()
        except Exception:
            _LOGGER.debug("Не удалось обновить показатели", exc_info=True)
            return

        expired = certificates.get("expired", 0)
        self._stat_cards["certificates"].update_value(
            str(certificates.get("total", 0)),
            f"просрочено: {expired}" if expired else "все действительны",
        )
        self._stat_cards["aliases"].update_value(str(aliases), "программа учится на ваших решениях")
        self._stat_cards["processed"].update_value(
            str(history.get("rows_total", 0)), f"обработок: {history.get('runs', 0)}"
        )
        rate = history.get("success_rate", 0.0) * 100
        self._stat_cards["rate"].update_value(
            f"{rate:.0f} %" if history.get("rows_total") else "—",
            f"требует проверки: {history.get('ambiguous', 0)}",
        )
        self._stat_cards["rate"].set_accent(
            "success" if rate >= 90 else "warning" if rate >= 70 else "danger"
        )

        if self._database_path is None:
            stored = container.certificate_import_service.last_path()
            if stored and Path(stored).is_file():
                self._database_zone.set_path(Path(stored), notify=False)
                self._database_path = Path(stored)
                self._update_run_state()

    def _set_order(self, path: Path) -> None:
        """Запоминает выбранный файл заказа."""
        self._order_path = path
        self.app.settings_service.update(
            lambda settings: setattr(settings.ui, "last_order_file", str(path))
        )
        self._update_run_state()

    def _set_database_path(self, path: Path) -> None:
        """Запоминает выбранный файл базы сертификатов и запускает импорт."""
        self._database_path = path
        self.app.settings_service.update(
            lambda settings: setattr(settings.certificates, "excel_path", str(path))
        )
        self._update_run_state()
        self.reimport(silent=True)

    def browse_order(self) -> None:
        """Открывает диалог выбора файла заказа."""
        self.ensure_built()
        self._order_zone.browse()

    def browse_database(self) -> None:
        """Открывает диалог выбора файла базы сертификатов."""
        self.ensure_built()
        self._database_zone.browse()

    def set_paths(self, order: Path | None = None, database: Path | None = None) -> None:
        """Устанавливает пути извне (перетаскивание в окно, аргументы запуска).

        Args:
            order: Путь к файлу заказа.
            database: Путь к файлу базы сертификатов.
        """
        self.ensure_built()
        if order is not None:
            self._order_zone.set_path(order)
        if database is not None:
            self._database_zone.set_path(database)

    def _update_run_state(self) -> None:
        """Включает или выключает кнопку запуска."""
        ready = self._order_path is not None
        try:
            self._run_button.configure(state="normal" if ready else "disabled")
            self._hint_label.configure(
                text="Ctrl + Enter" if ready else "Сначала выберите файл заказа"
            )
        except Exception:
            pass

    # -------------------------------------------------------------- импорт
    def reimport(self, *, silent: bool = False) -> None:
        """Запускает (пере)импорт Excel-базы сертификатов.

        Args:
            silent: Не показывать уведомление об успехе.
        """
        path = self._database_path
        if path is None:
            stored = self.app.container.certificate_import_service.last_path()
            path = Path(stored) if stored else None
        if path is None or not path.is_file():
            self.app.toasts.warning("Сначала выберите файл базы сертификатов")
            return

        service = self.app.container.certificate_import_service
        self._progress.start(f"Импорт базы {path.name}…")

        def _work(_reporter: ProgressReporter) -> Any:
            return service.import_file(path)

        def _done(result: Any) -> None:
            self._progress.finish(result.summary(), success=not result.failed)
            self.app.container.matching_service.invalidate()
            self.refresh()
            if result.failed:
                self.app.toasts.warning(result.summary(), title="Импорт не выполнен")
            elif not silent:
                self.app.toasts.success(result.summary(), title="База сертификатов обновлена")

        self.app.tasks.run(
            TASK_IMPORT,
            _work,
            on_success=_done,
            on_progress=self._progress.update,
            on_error=lambda error: self._handle_error(error, "Ошибка импорта базы сертификатов"),
            on_cancelled=lambda: self._progress.finish("Импорт отменён", success=False),
        )

    # -------------------------------------------------------------- обработка
    def run_processing(self) -> None:
        """Запускает подбор сертификатов для выбранного заказа."""
        if self._order_path is None:
            self.app.toasts.warning("Выберите файл заказа")
            return
        if self.app.tasks.is_running(TASK_PROCESS):
            self.app.toasts.info("Обработка уже выполняется")
            return

        order_path = self._order_path
        container = self.app.container
        self._progress.start("Подготовка…")
        self._run_button.configure(state="disabled")

        def _work(reporter: ProgressReporter) -> ProcessingOutcome:
            request = ProcessingRequest(
                order_path=order_path,
                resolve_ambiguities=self._resolve_ambiguity,
                resolve_expiry_manually=self._resolve_expiry_manually,
                learn_from_choices=True,
            )
            return container.order_service.process(request, reporter=reporter)

        def _done(outcome: ProcessingOutcome) -> None:
            self._outcome = outcome
            self._results = outcome.results
            self._progress.finish(outcome.summary(), success=outcome.not_found == 0)
            self._show_results(outcome)
            self.refresh()
            self._run_button.configure(state="normal")

            level = "success" if outcome.not_found == 0 else "warning"
            self.app.toasts.show(
                f"{outcome.summary()} · {format_duration(outcome.run.duration_seconds)}",
                level=level,
                title="Обработка завершена",
                duration=7.0,
                action_text="Открыть папку",
                on_action=lambda: self._open_output_folder(),
            )
            if self.app.settings.export.open_output_after_run:
                self._open_output_folder()

        def _cancelled() -> None:
            self._progress.finish("Обработка отменена", success=False)
            self._run_button.configure(state="normal")

        self.app.tasks.run(
            TASK_PROCESS,
            _work,
            on_success=_done,
            on_progress=self._progress.update,
            on_error=self._handle_processing_error,
            on_cancelled=_cancelled,
        )

    def cancel_processing(self) -> None:
        """Отменяет активную фоновую операцию."""
        for task in (TASK_PROCESS, TASK_IMPORT):
            if self.app.tasks.cancel(task):
                self.app.toasts.info("Операция будет остановлена…")
                return

    def _resolve_ambiguity(self, result: MatchResult, remaining: int) -> int | None:
        """Показывает окно выбора и ждёт решения пользователя.

        Метод вызывается из фонового потока, поэтому окно создаётся через
        планировщик главного потока, а рабочий поток блокируется на событии
        до получения ответа.

        Args:
            result: Неоднозначный результат подбора.
            remaining: Сколько позиций ещё предстоит разобрать после текущей.

        Returns:
            Индекс выбранного кандидата, :data:`SKIP` для пропуска строки
            либо ``None``, чтобы прекратить разбор оставшихся позиций.
        """
        answer: dict[str, Any] = {}
        finished = threading.Event()

        def _ask() -> None:
            try:
                dialog = AmbiguityDialog(
                    self.app,
                    self.theme,
                    result=result,
                    animator=self.app.animator,
                    on_preview=self.app.preview_pdf,
                    on_search=self._search_candidates,
                    remaining=remaining,
                )
                answer["value"] = dialog.wait_result()
                answer["remember"] = bool(dialog.remember.get())
            except Exception:
                _LOGGER.exception("Ошибка окна выбора сертификата")
                answer["value"] = SKIP
            finally:
                finished.set()

        try:
            self.app.after(0, _ask)
        except Exception:
            return None

        finished.wait()
        value = answer.get("value")
        if value == "stop" or value is None:
            return None
        if not answer.get("remember", True):
            # Пользователь отказался запоминать выбор: помечаем результат,
            # чтобы оркестратор не создавал псевдоним.
            result.note = "Выбор не сохранён в псевдонимы"
            result.alias_applied = True
        return int(value)

    def _resolve_expiry_manually(
        self, review: ManualExpiryReview, remaining: int
    ) -> dict[int, ExpirySuggestion] | None:
        """Показывает окно ручного подтверждения партий и ждёт решения пользователя.

        Тот же приём, что и в :meth:`_resolve_ambiguity` (метод вызывается
        из фонового потока обработки заказа — окно должно быть создано в
        главном потоке, поток обработки блокируется на событии до ответа).
        Выбор пользователя ни при каких обстоятельствах не создаёт и не
        изменяет запись в словаре товаров — это отдельное подтверждение
        конкретного сертификата для конкретной партии, а не соответствие
        «наименование → товар».

        Args:
            review: Обзор партий срока годности с предложенными вариантами.
            remaining: Сколько позиций ещё предстоит разобрать после текущей.

        Returns:
            Словарь «индекс партии → подтверждённый вариант», пустой словарь
            (ничего не подтверждено для этой строки) либо ``None``, чтобы
            прекратить разбор оставшихся позиций.
        """
        answer: dict[str, Any] = {}
        finished = threading.Event()

        def _ask() -> None:
            try:
                dialog = ExpirySuggestionDialog(
                    self.app,
                    self.theme,
                    review=review,
                    tolerance_days=self.app.settings.matching.expiry_tolerance_days,
                    animator=self.app.animator,
                    remaining=remaining,
                )
                answer["value"] = dialog.wait_result()
            except Exception:
                _LOGGER.exception("Ошибка окна ручного подтверждения срока годности")
                answer["value"] = {}
            finally:
                finished.set()

        try:
            self.app.after(0, _ask)
        except Exception:
            return None

        finished.wait()
        value = answer.get("value")
        if value == "stop" or value is None:
            return None
        return dict(value)

    def _search_candidates(self, query: str) -> list[Any]:
        """Ищет кандидатов для уточняющего запроса из окна выбора."""
        return self.app.container.matching_service.find_candidates(query, limit=12)

    # -------------------------------------------------------------- результаты
    def _show_results(self, outcome: ProcessingOutcome) -> None:
        """Отображает результаты обработки."""
        self._results = outcome.results
        self._apply_filter(self._filter)

        self._results_card.set_subtitle(
            f"{outcome.run.order_name} · {len(outcome.results)} позиций · "
            f"{format_duration(outcome.run.duration_seconds)}"
        )

        for child in self._output_row.winfo_children():
            child.destroy()

        # Значения присваиваются локальным переменным перед созданием замыканий:
        # mypy сужает Path | None -> Path только для локальной переменной
        # внутри проверки `if`, но не для повторного обращения к атрибуту
        # outcome.* из тела лямбды, которая формально может быть вызвана позже.
        output_file = outcome.output_file
        if output_file is not None:
            secondary_button(
                self._output_row,
                self.theme,
                text="Открыть Excel",
                icon="excel",
                command=lambda: self.app.open_path(output_file),
            ).pack(side="left")

        copy_report = outcome.copy_report
        if copy_report is not None and copy_report.copied:
            destination = copy_report.destination
            secondary_button(
                self._output_row,
                self.theme,
                text=f"Сертификаты ({copy_report.copied})",
                icon="folder",
                command=lambda: self.app.open_path(destination),
            ).pack(side="left", padx=(Spacing.SM, 0))

        report_file = outcome.report_file
        if report_file is not None:
            secondary_button(
                self._output_row,
                self.theme,
                text="Отчёт",
                icon="chart",
                command=lambda: self.app.open_path(report_file),
            ).pack(side="left", padx=(Spacing.SM, 0))

        if outcome.ambiguous or outcome.not_found:
            ghost_button(
                self._output_row,
                self.theme,
                text="Показать проблемные позиции",
                icon="filter",
                command=lambda: self._filter_control.select(MatchStatus.AMBIGUOUS.value),
            ).pack(side="right")

    def _apply_filter(self, value: str) -> None:
        """Фильтрует таблицу результатов по статусу."""
        self._filter = value
        rows: list[tuple[str, dict[str, Any], str]] = []

        for index, result in enumerate(self._results):
            if result.status is MatchStatus.SKIPPED:
                continue
            status_value = result.status.value
            if value == MatchStatus.MATCHED.value and not result.status.is_resolved:
                continue
            if value not in ("all", MatchStatus.MATCHED.value) and status_value != value:
                continue

            certificate = result.certificate
            rows.append(
                (
                    str(index),
                    {
                        "row": result.row.row_number,
                        "product": result.row.product_name,
                        "status": result.status.label,
                        "certificate": result.certificate_number or "—",
                        "expiry": _format_expiry(result),
                        "score": f"{int(result.score * 100)} %" if result.score else "—",
                        "matched_product": certificate.product_name if certificate else "—",
                    },
                    _row_tag(result.status),
                )
            )

        self._table.set_rows(rows)

    def _open_result_pdf(self, row_id: str) -> None:
        """Открывает PDF сертификата выбранной строки."""
        result = self._result_at(row_id)
        certificate = result.certificate if result else None
        if certificate is None:
            self.app.toasts.info("Для этой позиции сертификат не подобран")
            return
        self.app.preview_pdf(certificate.certificate_number)

    def _change_certificate(self, row_id: str) -> None:
        """Открывает окно выбора для повторного подбора."""
        result = self._result_at(row_id)
        if result is None:
            return

        candidates = self.app.container.matching_service.find_candidates(
            result.row.search_text, limit=12
        )
        if not candidates:
            self.app.toasts.warning("Подходящих сертификатов не найдено")
            return

        result.candidates = candidates
        dialog = AmbiguityDialog(
            self.app,
            self.theme,
            result=result,
            animator=self.app.animator,
            on_preview=self.app.preview_pdf,
            on_search=self._search_candidates,
        )
        choice = dialog.wait_result()
        if choice is None or choice == "stop" or choice == SKIP:
            return

        result.select(int(choice), manual=True)
        if dialog.remember.get():
            certificate = result.certificate
            if certificate is not None:
                self.app.container.alias_service.learn(
                    result.row.search_text, certificate, note="Исправление после обработки"
                )
                self.app.toasts.success(
                    f"Соответствие запомнено: {result.row.product_name} → "
                    f"{certificate.product_name}"
                )
        self._apply_filter(self._filter)
        self.app.toasts.info(
            "Сертификат изменён. Нажмите «Подобрать сертификаты», чтобы пересобрать файл."
        )

    def _copy_product_name(self, row_id: str) -> None:
        """Копирует наименование товара в буфер обмена."""
        result = self._result_at(row_id)
        if result is None:
            return
        try:
            self.app.clipboard_clear()
            self.app.clipboard_append(result.row.product_name)
            self.app.toasts.info("Наименование скопировано")
        except Exception:
            pass

    def _result_at(self, row_id: str) -> MatchResult | None:
        """Возвращает результат по идентификатору строки таблицы."""
        try:
            return self._results[int(row_id)]
        except (ValueError, IndexError):
            return None

    def _open_output_folder(self) -> None:
        """Открывает папку с результатами обработки."""
        if self._outcome is None or self._outcome.output_file is None:
            return
        self.app.open_path(self._outcome.output_file.parent)

    # ---------------------------------------------------------------- ошибки
    def _handle_processing_error(self, error: Exception) -> None:
        """Обрабатывает ошибку обработки заказа."""
        try:
            self._run_button.configure(state="normal")
        except Exception:
            pass
        self._progress.finish("Обработка прервана", success=False)
        self._handle_error(error, "Не удалось обработать заказ")

    def _handle_error(self, error: Exception, title: str) -> None:
        """Показывает сообщение об ошибке."""
        message = getattr(error, "message", str(error))
        details = getattr(error, "details", "") or ""
        self.app.show_error(title, message, details)

    def refresh_theme(self) -> None:
        """Обновляет цвета после смены темы."""
        super().refresh_theme()
        for widget in (self._order_zone, self._database_zone, self._progress, self._table):
            refresher = getattr(widget, "refresh_theme", None)
            if callable(refresher):
                refresher()


def _row_tag(status: MatchStatus) -> str:
    """Возвращает тег окраски строки таблицы для статуса."""
    if status in (MatchStatus.MATCHED, MatchStatus.MANUAL):
        return "matched"
    if status is MatchStatus.AMBIGUOUS:
        return "ambiguous"
    return "not_found"


def _format_expiry(result: MatchResult) -> str:
    """Форматирует срок действия сертификата для таблицы."""
    from app.core.dates import format_date

    return format_date(result.expiry_date)


def open_in_system(path: Path) -> None:
    """Открывает файл или папку средствами операционной системы.

    Args:
        path: Путь к объекту.
    """
    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception:
        _LOGGER.warning("Не удалось открыть %s средствами системы", path)
