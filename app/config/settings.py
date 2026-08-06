"""Модель конфигурации приложения и её персистентное хранение.

Конфигурация вынесена из кода полностью: веса ранжирования, пороги принятия
решений, допуски по срокам, цвета подсветки Excel и параметры интерфейса —
всё редактируется пользователем и переживает перезапуск.

Файл настроек — человекочитаемый JSON. Запись атомарна (временный файл +
``Path.replace``), поэтому сбой питания не приводит к потере конфигурации.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, TypeVar

from app.core.constants import DEFAULT_EMBEDDING_MODEL
from app.core.exceptions import ConfigurationError

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


# --------------------------------------------------------------------------- #
# Группы настроек
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class MatchingSettings:
    """Параметры алгоритма подбора сертификатов.

    Attributes:
        weight_name: Вес совпадения наименования в итоговой оценке.
        weight_volume: Вес совпадения объёма.
        weight_expiry: Вес соответствия срока.
        auto_accept_threshold: Оценка, начиная с которой результат принимается
            автоматически, без участия пользователя.
        review_threshold: Нижняя граница, ниже которой кандидат считается
            отсутствующим.
        ambiguity_margin: Минимальный отрыв лидера от второго кандидата.
            Меньший отрыв означает неоднозначность.
        auto_resolve_duplicates: Разрешать ли автоматически случай, когда
            близкие кандидаты — это один и тот же товар того же объёма,
            различающийся только сроком. В этом случае выбирается сертификат
            с ближайшим сроком окончания (принцип FEFO), и окно выбора не
            открывается. Выключение заставляет программу спрашивать всегда.
        max_candidates: Сколько кандидатов показывать в окне выбора.
        fuzzy_prefilter_limit: Сколько кандидатов отбирает быстрый лексический
            этап перед дорогим семантическим.
        volume_tolerance_ratio: Относительный допуск сравнения объёмов.
        strict_volume_match: Отбраковывать ли кандидатов с несовпадающим
            объёмом безусловно. В аптечной практике сертификат выдаётся на
            конкретную фасовку, поэтому «похожий объём» недопустим.
        min_name_score: Минимальная оценка совпадения наименования, ниже
            которой кандидат отбраковывается независимо от объёма и срока.
        expiry_tolerance_days: Ширина окна допуска по сроку годности в днях
            (в каждую сторону от требуемой даты). За пределами окна оценка не
            обнуляется, а продолжает плавно снижаться — благодаря этому, даже
            если ни один сертификат не попал в окно, подбор всё равно
            предложит ближайший по сроку вариант вместо отказа.
        require_valid_expiry: Исключать ли сертификаты с истёкшим сроком.
        missing_volume_score: Нейтральная оценка при отсутствии объёма.
        missing_expiry_score: Нейтральная оценка при отсутствии срока.
        prefer_alias: Использовать ли таблицу псевдонимов раньше ИИ.
        use_semantic: Включён ли семантический этап.
        semantic_trigger_threshold: Лексическая оценка, ниже которой
            подключается семантическая модель.
        semantic_weight: Доля семантической оценки в комбинированной оценке
            наименования.
        embedding_model: Идентификатор модели Sentence Transformers.
    """

    weight_name: float = 0.50
    weight_volume: float = 0.30
    weight_expiry: float = 0.20
    auto_accept_threshold: float = 0.86
    review_threshold: float = 0.55
    ambiguity_margin: float = 0.06
    auto_resolve_duplicates: bool = True
    max_candidates: int = 8
    fuzzy_prefilter_limit: int = 40
    volume_tolerance_ratio: float = 0.02
    strict_volume_match: bool = True
    min_name_score: float = 0.55
    expiry_tolerance_days: int = 45
    require_valid_expiry: bool = True
    missing_volume_score: float = 0.55
    missing_expiry_score: float = 0.60
    prefer_alias: bool = True
    use_semantic: bool = True
    semantic_trigger_threshold: float = 0.92
    semantic_weight: float = 0.45
    embedding_model: str = DEFAULT_EMBEDDING_MODEL

    def normalized_weights(self) -> tuple[float, float, float]:
        """Возвращает веса, нормированные к сумме 1.0.

        Пользователь может задать любые значения — нормировка гарантирует,
        что итоговая оценка остаётся в диапазоне ``[0, 1]``.

        Returns:
            Кортеж ``(вес наименования, вес объёма, вес срока)``.
        """
        total = self.weight_name + self.weight_volume + self.weight_expiry
        if total <= 0:
            return (0.5, 0.3, 0.2)
        return (self.weight_name / total, self.weight_volume / total, self.weight_expiry / total)

    def validate(self) -> None:
        """Приводит значения к допустимым диапазонам.

        Raises:
            ConfigurationError: Если исправить значения невозможно.
        """
        for name in ("weight_name", "weight_volume", "weight_expiry"):
            value = getattr(self, name)
            if value < 0:
                raise ConfigurationError(f"Вес «{name}» не может быть отрицательным")
        self.auto_accept_threshold = _clamp(self.auto_accept_threshold, 0.05, 1.0)
        self.review_threshold = _clamp(self.review_threshold, 0.0, self.auto_accept_threshold)
        self.ambiguity_margin = _clamp(self.ambiguity_margin, 0.0, 0.5)
        self.semantic_trigger_threshold = _clamp(self.semantic_trigger_threshold, 0.0, 1.0)
        self.semantic_weight = _clamp(self.semantic_weight, 0.0, 1.0)
        self.volume_tolerance_ratio = _clamp(self.volume_tolerance_ratio, 0.0, 0.5)
        self.max_candidates = int(_clamp(self.max_candidates, 3, 50))
        self.fuzzy_prefilter_limit = int(_clamp(self.fuzzy_prefilter_limit, 5, 500))
        self.expiry_tolerance_days = int(_clamp(self.expiry_tolerance_days, 0, 3650))


@dataclass(slots=True)
class CertificatesSettings:
    """Параметры источника данных о сертификатах.

    Excel — единственный источник данных; SQLite — только его индекс. Папка
    PDF используется исключительно для копирования найденного сертификата в
    результат — её содержимое никогда не читается и не разбирается.

    Attributes:
        excel_path: Путь к Excel-файлу базы сертификатов.
        pdf_dir: Папка с PDF-файлами сертификатов (для копирования по номеру
            в имени файла).
        rescan_on_start: Проверять ли изменение Excel-файла при запуске
            приложения и переимпортировать его при необходимости.
        recursive_pdf_search: Искать ли PDF во вложенных папках ``pdf_dir``.
    """

    excel_path: str = ""
    pdf_dir: str = ""
    rescan_on_start: bool = True
    recursive_pdf_search: bool = True

    def validate(self) -> None:
        """Приводит значения к допустимым диапазонам (нет числовых полей)."""


@dataclass(slots=True)
class ExportSettings:
    """Параметры формирования результата.

    Attributes:
        output_dir: Каталог результатов (пусто — рядом с файлом заказа).
        copy_certificates: Копировать ли PDF в папку результата.
        certificates_dirname: Имя создаваемой папки с сертификатами.
        highlight_rows: Подсвечивать ли строки Excel по статусу.
        color_matched: Цвет подсветки найденных строк (RRGGBB).
        color_ambiguous: Цвет подсветки неоднозначных строк.
        color_not_found: Цвет подсветки ненайденных строк.
        write_report: Формировать ли отчёт о совпадениях.
        report_format: Формат отчёта (``xlsx`` или ``csv``).
        open_output_after_run: Открывать ли папку результата по завершении.
        date_format: Формат вывода дат в Excel.
        certificate_column_title: Заголовок колонки с номером НАЙДЕННОГО
            сертификата (создаётся программой; требуемый срок годности
            заказа — отдельная, всегда нетронутая колонка исходного файла).
        expiry_column_title: Заголовок колонки со сроком годности
            НАЙДЕННОГО сертификата (создаётся программой).
        add_score_column: Добавлять ли служебную колонку с оценкой совпадения.
        filename_suffix: Суффикс имени итогового файла.
    """

    output_dir: str = ""
    copy_certificates: bool = True
    certificates_dirname: str = "Certificates"
    highlight_rows: bool = True
    color_matched: str = "D6F5DD"
    color_ambiguous: str = "FFF3CD"
    color_not_found: str = "FBD5D5"
    write_report: bool = True
    report_format: str = "xlsx"
    open_output_after_run: bool = True
    date_format: str = "%d.%m.%Y"
    certificate_column_title: str = "Сертификат"
    expiry_column_title: str = "С.Г. сертификата"
    add_score_column: bool = False
    filename_suffix: str = "_с_сертификатами"

    def validate(self) -> None:
        """Приводит значения к допустимым."""
        self.report_format = self.report_format.lower().strip() or "xlsx"
        if self.report_format not in {"xlsx", "csv"}:
            self.report_format = "xlsx"
        self.certificates_dirname = self.certificates_dirname.strip() or "Certificates"
        for name in ("color_matched", "color_ambiguous", "color_not_found"):
            value = str(getattr(self, name)).lstrip("#").upper()
            setattr(self, name, value if len(value) == 6 else "FFFFFF")


@dataclass(slots=True)
class UiSettings:
    """Параметры интерфейса.

    Attributes:
        theme: ``light``, ``dark`` или ``system``.
        accent: Идентификатор акцентной палитры.
        scaling: Масштаб интерфейса (для мониторов 4K).
        animations: Включены ли анимации.
        notifications: Показывать ли всплывающие уведомления.
        notification_seconds: Время показа уведомления.
        confirm_on_exit: Спрашивать ли подтверждение при закрытии.
        remember_window_state: Сохранять ли геометрию окна.
        last_order_file: Последний обработанный файл заказа.
        rows_per_page: Размер страницы в таблицах.
    """

    theme: str = "system"
    accent: str = "emerald"
    scaling: float = 1.0
    animations: bool = True
    notifications: bool = True
    notification_seconds: float = 4.0
    confirm_on_exit: bool = False
    remember_window_state: bool = True
    last_order_file: str = ""
    rows_per_page: int = 200

    def validate(self) -> None:
        """Приводит значения к допустимым."""
        if self.theme not in {"light", "dark", "system"}:
            self.theme = "system"
        self.scaling = _clamp(self.scaling, 0.8, 2.0)
        self.notification_seconds = _clamp(self.notification_seconds, 1.0, 30.0)
        self.rows_per_page = int(_clamp(self.rows_per_page, 25, 5000))


@dataclass(slots=True)
class MaintenanceSettings:
    """Параметры обслуживания базы данных.

    Attributes:
        auto_backup: Делать ли резервную копию базы при запуске.
        backup_retention: Сколько копий хранить.
        vacuum_on_start: Выполнять ли ``VACUUM`` при запуске.
        log_level: Уровень журналирования.
        keep_logs_days: Сколько дней хранить журналы.
    """

    auto_backup: bool = True
    backup_retention: int = 10
    vacuum_on_start: bool = False
    log_level: str = "INFO"
    keep_logs_days: int = 60

    def validate(self) -> None:
        """Приводит значения к допустимым."""
        self.backup_retention = int(_clamp(self.backup_retention, 1, 100))
        self.keep_logs_days = int(_clamp(self.keep_logs_days, 1, 3650))
        if self.log_level.upper() not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            self.log_level = "INFO"
        else:
            self.log_level = self.log_level.upper()


@dataclass(slots=True)
class AppSettings:
    """Полная конфигурация приложения.

    Attributes:
        matching: Параметры алгоритма подбора.
        certificates: Параметры источника данных о сертификатах.
        export: Параметры выгрузки результата.
        ui: Параметры интерфейса.
        maintenance: Параметры обслуживания.
    """

    matching: MatchingSettings = field(default_factory=MatchingSettings)
    certificates: CertificatesSettings = field(default_factory=CertificatesSettings)
    export: ExportSettings = field(default_factory=ExportSettings)
    ui: UiSettings = field(default_factory=UiSettings)
    maintenance: MaintenanceSettings = field(default_factory=MaintenanceSettings)

    def validate(self) -> None:
        """Проверяет и нормализует все группы настроек."""
        self.matching.validate()
        self.certificates.validate()
        self.export.validate()
        self.ui.validate()
        self.maintenance.validate()

    def to_dict(self) -> dict[str, Any]:
        """Сериализует конфигурацию в словарь.

        Returns:
            Словарь, пригодный для записи в JSON.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppSettings:
        """Восстанавливает конфигурацию из словаря.

        Неизвестные ключи игнорируются, отсутствующие заполняются значениями
        по умолчанию — это делает формат совместимым «вперёд и назад» при
        обновлении версий приложения.

        Args:
            data: Словарь, прочитанный из JSON.

        Returns:
            Экземпляр конфигурации.
        """
        settings = cls()
        for group_field in fields(cls):
            group_data = data.get(group_field.name)
            if isinstance(group_data, dict):
                setattr(
                    settings,
                    group_field.name,
                    _build_dataclass(getattr(settings, group_field.name), group_data),
                )
        settings.validate()
        return settings


# --------------------------------------------------------------------------- #
# Вспомогательные функции
# --------------------------------------------------------------------------- #
def _clamp(value: float, minimum: float, maximum: float) -> float:
    """Ограничивает значение заданным диапазоном."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return minimum
    return max(minimum, min(maximum, numeric))


def _build_dataclass(prototype: T, data: dict[str, Any]) -> T:
    """Заполняет копию dataclass-объекта значениями из словаря.

    Значения приводятся к типам, объявленным в dataclass; несовместимые
    игнорируются, чтобы повреждённый файл настроек не ломал запуск.
    """
    if not is_dataclass(prototype):  # pragma: no cover — защита от ошибок вызова
        return prototype
    for data_field in fields(prototype):
        if data_field.name not in data:
            continue
        raw = data[data_field.name]
        current = getattr(prototype, data_field.name)
        try:
            if isinstance(current, bool):
                setattr(prototype, data_field.name, bool(raw))
            elif isinstance(current, int) and not isinstance(current, bool):
                setattr(prototype, data_field.name, int(raw))
            elif isinstance(current, float):
                setattr(prototype, data_field.name, float(raw))
            elif isinstance(current, str):
                setattr(prototype, data_field.name, str(raw))
        except (TypeError, ValueError):
            _LOGGER.warning(
                "Некорректное значение настройки %s=%r — используется значение по умолчанию",
                data_field.name,
                raw,
            )
    return prototype


# --------------------------------------------------------------------------- #
# Хранилище настроек
# --------------------------------------------------------------------------- #
class SettingsService:
    """Загружает, сохраняет и раздаёт конфигурацию приложения.

    Единственный владелец объекта :class:`AppSettings` в процессе. Изменения
    публикуются подписчикам, что позволяет интерфейсу мгновенно реагировать
    на смену темы или порогов подбора.
    """

    def __init__(self, path: Path) -> None:
        """Создаёт сервис, привязанный к файлу настроек.

        Args:
            path: Путь к JSON-файлу конфигурации.
        """
        self._path = path
        self._settings = AppSettings()
        self._lock = threading.RLock()
        self._listeners: list[Callable[[AppSettings], None]] = []
        self._loaded = False

    @property
    def path(self) -> Path:
        """Путь к файлу настроек."""
        return self._path

    @property
    def current(self) -> AppSettings:
        """Текущая конфигурация (загружается при первом обращении)."""
        if not self._loaded:
            self.load()
        return self._settings

    def load(self) -> AppSettings:
        """Читает конфигурацию с диска.

        Повреждённый файл не приводит к отказу запуска: он переименовывается
        в ``*.corrupted``, а приложение стартует со значениями по умолчанию.

        Returns:
            Загруженная конфигурация.
        """
        with self._lock:
            if self._path.exists():
                try:
                    raw = json.loads(self._path.read_text(encoding="utf-8"))
                    self._settings = AppSettings.from_dict(raw)
                    _LOGGER.info("Настройки загружены из %s", self._path)
                except (json.JSONDecodeError, OSError, TypeError) as error:
                    _LOGGER.error(
                        "Файл настроек повреждён (%s) — применены значения по умолчанию", error
                    )
                    self._quarantine_corrupted_file()
                    self._settings = AppSettings()
            else:
                self._settings = AppSettings()
                _LOGGER.info("Файл настроек не найден — создана конфигурация по умолчанию")
            self._loaded = True
            return self._settings

    def save(self, settings: AppSettings | None = None) -> None:
        """Атомарно сохраняет конфигурацию на диск и уведомляет подписчиков.

        Args:
            settings: Конфигурация для сохранения; ``None`` — текущая.

        Raises:
            ConfigurationError: Если записать файл не удалось.
        """
        with self._lock:
            if settings is not None:
                self._settings = settings
            self._settings.validate()
            payload = json.dumps(self._settings.to_dict(), ensure_ascii=False, indent=2)
            temporary = self._path.with_suffix(".json.tmp")
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                temporary.write_text(payload, encoding="utf-8")
                temporary.replace(self._path)
            except OSError as error:
                raise ConfigurationError(
                    "Не удалось сохранить настройки", details=str(error)
                ) from error
            snapshot = self._settings

        _LOGGER.debug("Настройки сохранены в %s", self._path)
        self._notify(snapshot)

    def update(self, mutator: Callable[[AppSettings], None]) -> AppSettings:
        """Изменяет конфигурацию под блокировкой и сохраняет результат.

        Args:
            mutator: Функция, применяющая изменения к объекту настроек.

        Returns:
            Обновлённая конфигурация.
        """
        with self._lock:
            mutator(self.current)
        self.save()
        return self._settings

    def reset_to_defaults(self) -> AppSettings:
        """Сбрасывает конфигурацию к заводским значениям.

        Returns:
            Конфигурация по умолчанию.
        """
        with self._lock:
            preserved_excel = self._settings.certificates.excel_path
            preserved_pdf_dir = self._settings.certificates.pdf_dir
            self._settings = AppSettings()
            self._settings.certificates.excel_path = preserved_excel
            self._settings.certificates.pdf_dir = preserved_pdf_dir
        self.save()
        return self._settings

    def subscribe(self, listener: Callable[[AppSettings], None]) -> Callable[[], None]:
        """Подписывает обработчик на изменение конфигурации.

        Args:
            listener: Вызывается после каждого сохранения.

        Returns:
            Функция отписки.
        """
        with self._lock:
            self._listeners.append(listener)

        def _unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return _unsubscribe

    def export_to(self, destination: Path) -> None:
        """Экспортирует конфигурацию в указанный файл.

        Args:
            destination: Путь файла назначения.

        Raises:
            ConfigurationError: При ошибке записи.
        """
        try:
            destination.write_text(
                json.dumps(self.current.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as error:
            raise ConfigurationError(
                "Не удалось экспортировать настройки", details=str(error)
            ) from error

    def import_from(self, source: Path) -> AppSettings:
        """Импортирует конфигурацию из файла и сохраняет её.

        Args:
            source: Путь файла-источника.

        Returns:
            Импортированная конфигурация.

        Raises:
            ConfigurationError: Если файл нечитаем или некорректен.
        """
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ConfigurationError(
                "Не удалось импортировать настройки", details=str(error)
            ) from error
        with self._lock:
            self._settings = AppSettings.from_dict(raw)
        self.save()
        return self._settings

    def _quarantine_corrupted_file(self) -> None:
        """Переименовывает повреждённый файл настроек, сохраняя его для анализа."""
        try:
            self._path.replace(self._path.with_suffix(".json.corrupted"))
        except OSError:  # pragma: no cover — файл может быть заблокирован
            _LOGGER.debug("Не удалось переименовать повреждённый файл настроек")

    def _notify(self, settings: AppSettings) -> None:
        """Оповещает подписчиков об изменении конфигурации."""
        with self._lock:
            listeners = tuple(self._listeners)
        for listener in listeners:
            try:
                listener(settings)
            except Exception:
                _LOGGER.exception("Ошибка обработчика изменения настроек")
