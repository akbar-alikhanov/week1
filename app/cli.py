"""Консольный интерфейс приложения.

Графическая оболочка — основной способ работы, но консольный режим обязателен
для трёх сценариев корпоративной эксплуатации:

* пакетная обработка заказов по расписанию (планировщик задач Windows);
* проверка работоспособности установки (``--selfcheck``);
* диагностика проблем подбора без запуска окна.

Все команды используют тот же контейнер зависимостей, что и графический режим,
поэтому поведение полностью идентично.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from app.core.constants import APP_COMPANY, APP_NAME, APP_VERSION
from app.core.container import ApplicationContainer
from app.core.events import ProgressReporter, ProgressUpdate
from app.core.exceptions import CertMatcherError
from app.services.order_processing_service import ProcessingRequest

_LOGGER = logging.getLogger(__name__)


def _console_progress(update: ProgressUpdate) -> None:
    """Выводит прогресс операции в консоль одной перезаписываемой строкой."""
    if update.total <= 0:
        if update.message:
            print(f"  {update.message}")
        return
    bar_width = 28
    filled = int(bar_width * update.fraction)
    bar = "█" * filled + "·" * (bar_width - filled)
    eta = update.eta_seconds
    tail = f" · осталось ~{eta:.0f} с" if eta and eta > 1 else ""
    sys.stdout.write(f"\r  [{bar}] {update.percent:3d}%  {update.message}{tail}".ljust(100))
    sys.stdout.flush()
    if update.fraction >= 1.0:
        sys.stdout.write("\n")


def command_import(container: ApplicationContainer, arguments: argparse.Namespace) -> int:
    """Импортирует Excel-базу сертификатов в SQLite.

    Args:
        container: Контейнер зависимостей.
        arguments: Разобранные аргументы командной строки.

    Returns:
        Код возврата процесса.
    """
    path = Path(arguments.file).expanduser().resolve()
    if not path.is_file():
        print(f"Ошибка: файл не найден — {path}", file=sys.stderr)
        return 2

    print(f"Импорт базы сертификатов: {path}")
    result = container.certificate_import_service.import_file(path)

    print(f"\n{result.summary()}")
    print(f"Длительность: {result.duration_ms / 1000:.1f} с")

    container.settings_service.update(
        lambda settings: setattr(settings.certificates, "excel_path", str(path))
    )
    return 0 if not result.failed else 1


def command_process(container: ApplicationContainer, arguments: argparse.Namespace) -> int:
    """Обрабатывает файл заказа.

    Args:
        container: Контейнер зависимостей.
        arguments: Разобранные аргументы командной строки.

    Returns:
        Код возврата процесса.
    """
    order_path = Path(arguments.order).expanduser().resolve()
    if not order_path.is_file():
        print(f"Ошибка: файл заказа не найден — {order_path}", file=sys.stderr)
        return 2

    if arguments.certificates:
        excel_path = Path(arguments.certificates).expanduser().resolve()
        print(f"Импорт базы сертификатов: {excel_path}")
        container.certificate_import_service.import_file(excel_path)
        print()

    print(f"Обработка заказа: {order_path.name}")
    reporter = ProgressReporter(_console_progress)
    request = ProcessingRequest(
        order_path=order_path,
        sheet_name=arguments.sheet,
        output_dir=Path(arguments.output).expanduser().resolve() if arguments.output else None,
        copy_certificates=not arguments.no_copy,
        write_report=not arguments.no_report,
        resolve_ambiguities=None,
    )

    outcome = container.order_service.process(request, reporter=reporter)

    print(f"\n{outcome.summary()}")
    print(f"Длительность: {outcome.run.duration_seconds:.2f} с")
    if outcome.output_file:
        print(f"Файл результата:  {outcome.output_file}")
    if outcome.copy_report:
        print(
            f"Папка сертификатов: {outcome.copy_report.destination} "
            f"({outcome.copy_report.copied} файлов)"
        )
    if outcome.report_file:
        print(f"Отчёт:            {outcome.report_file}")

    if arguments.verbose:
        print("\nПозиции, требующие внимания:")
        for result in outcome.results:
            if result.status.is_resolved:
                continue
            best = result.best
            detail = (
                f" (лучший вариант: {best.certificate.product_name}, {best.percent} %)"
                if best
                else ""
            )
            print(f"  · строка {result.row.row_number}: {result.row.product_name}{detail}")

    return 0


def command_search(container: ApplicationContainer, arguments: argparse.Namespace) -> int:
    """Ищет сертификаты по произвольному запросу.

    Args:
        container: Контейнер зависимостей.
        arguments: Разобранные аргументы командной строки.

    Returns:
        Код возврата процесса.
    """
    query = " ".join(arguments.query)
    candidates = container.matching_service.find_candidates(query, limit=arguments.limit)
    if not candidates:
        print("Ничего не найдено")
        return 1

    print(f"Результаты для «{query}»:\n")
    for candidate in candidates:
        certificate = candidate.certificate
        expiry = certificate.expiry_date.strftime("%d.%m.%Y") if certificate.expiry_date else "—"
        print(f"  {candidate.percent:3d}%  {certificate.product_name}")
        print(
            f"        срок {expiry} · № {certificate.display_number} · {candidate.score.explain()}"
        )
    return 0


def command_stats(container: ApplicationContainer, _: argparse.Namespace) -> int:
    """Показывает статистику базы данных.

    Args:
        container: Контейнер зависимостей.
        _: Аргументы командной строки (не используются).

    Returns:
        Код возврата процесса.
    """
    certificates = container.certificate_repository.statistics()
    history = container.history_repository.statistics()
    products = container.product_repository.statistics()

    print("База сертификатов")
    print(f"  всего:              {certificates['total']}")
    print(f"  просроченных:       {certificates['expired']}")
    print(f"  истекают за 90 дн.: {certificates['expiring_soon']}")
    print(f"  без срока:          {certificates['without_expiry']}")
    print(f"\nПсевдонимы: {container.alias_repository.count()}")
    print(f"Товары: {products['total']} (успешность подбора {products['match_rate'] * 100:.1f} %)")
    print("\nОбработка за 30 дней")
    print(f"  запусков:  {history['runs']}")
    print(f"  позиций:   {history['rows_total']}")
    print(f"  успешно:   {history['success_rate'] * 100:.1f} %")

    unmatched = container.history_repository.unmatched_products(limit=10)
    if unmatched:
        print("\nЧаще всего не находятся:")
        for name, count in unmatched:
            print(f"  {count:3d}×  {name}")
    return 0


def command_selfcheck(container: ApplicationContainer, _: argparse.Namespace) -> int:
    """Проверяет работоспособность установки.

    Args:
        container: Контейнер зависимостей.
        _: Аргументы командной строки (не используются).

    Returns:
        Код возврата процесса.
    """
    print(f"{APP_NAME} {APP_VERSION} — {APP_COMPANY}\n")
    for key, value in container.diagnostics().items():
        print(f"  {key:.<28} {value}")

    print("\nПроверка зависимостей:")
    modules = [
        ("customtkinter", "графический интерфейс"),
        ("PIL", "иконки и изображения"),
        ("fitz", "просмотр PDF (только отрисовка страниц)"),
        ("openpyxl", "чтение и запись Excel"),
        ("pandas", "отчёты"),
        ("rapidfuzz", "нечёткий поиск"),
        ("numpy", "векторные вычисления"),
        ("sentence_transformers", "семантический поиск (необязательно)"),
    ]
    missing_required = 0
    for module_name, purpose in modules:
        try:
            __import__(module_name)
            status = "OK"
        except ImportError:
            status = "НЕТ"
            if "необязательно" not in purpose:
                missing_required += 1
        print(f"  {module_name:.<28} {status:>4}  ({purpose})")

    print("\nПроверка записи в рабочие каталоги:")
    for name, directory in (
        ("данные", container.paths.data_dir),
        ("журналы", container.paths.logs_dir),
        ("кэш", container.paths.cache_dir),
        ("результаты", container.paths.output_dir),
    ):
        probe = directory / ".probe"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            print(f"  {name:.<28}   OK")
        except OSError as error:
            print(f"  {name:.<28}  СБОЙ  ({error})")
            missing_required += 1

    print("\nИтог:", "готово к работе" if missing_required == 0 else "есть проблемы")
    return 0 if missing_required == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    """Строит разборщик аргументов командной строки.

    Returns:
        Настроенный :class:`argparse.ArgumentParser`.
    """
    parser = argparse.ArgumentParser(
        prog="certmatcher",
        description=f"{APP_NAME} {APP_VERSION} — подбор сертификатов соответствия",
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {APP_VERSION}")
    parser.add_argument("--data-dir", help="каталог данных приложения")
    parser.add_argument("--verbose", "-v", action="store_true", help="подробный вывод")

    subparsers = parser.add_subparsers(dest="command")

    import_parser = subparsers.add_parser("import", help="импортировать Excel-базу сертификатов")
    import_parser.add_argument("file", help="путь к Excel-файлу базы сертификатов")

    process_parser = subparsers.add_parser("process", help="обработать файл заказа")
    process_parser.add_argument("order", help="путь к файлу заказа (.xlsx)")
    process_parser.add_argument(
        "--certificates", "-c", help="файл базы сертификатов (Excel) для импорта перед обработкой"
    )
    process_parser.add_argument("--output", "-o", help="каталог результата")
    process_parser.add_argument("--sheet", help="имя листа книги")
    process_parser.add_argument("--no-copy", action="store_true", help="не копировать PDF")
    process_parser.add_argument("--no-report", action="store_true", help="не формировать отчёт")
    # default=SUPPRESS обязателен: иначе значение подкоманды затрёт глобальный флаг.
    process_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=argparse.SUPPRESS,
        help="показать позиции, требующие внимания",
    )

    search_parser = subparsers.add_parser("search", help="найти сертификат по наименованию")
    search_parser.add_argument("query", nargs="+", help="поисковый запрос")
    search_parser.add_argument("--limit", type=int, default=10, help="количество результатов")

    subparsers.add_parser("stats", help="показать статистику базы")
    subparsers.add_parser("selfcheck", help="проверить работоспособность установки")

    return parser


def run(argv: list[str] | None = None) -> int:
    """Точка входа консольного режима.

    Args:
        argv: Аргументы командной строки; ``None`` — взять из ``sys.argv``.

    Returns:
        Код возврата процесса.
    """
    parser = build_parser()
    arguments = parser.parse_args(argv)

    if not arguments.command:
        parser.print_help()
        return 0

    commands = {
        "import": command_import,
        "process": command_process,
        "search": command_search,
        "stats": command_stats,
        "selfcheck": command_selfcheck,
    }

    container = ApplicationContainer.create(data_dir=arguments.data_dir)
    if arguments.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        container.startup()
        return commands[arguments.command](container, arguments)
    except CertMatcherError as error:
        print(f"\nОшибка: {error.message}", file=sys.stderr)
        if error.details:
            _LOGGER.debug("Подробности: %s", error.details)
        return 1
    except KeyboardInterrupt:
        print("\nПрервано пользователем", file=sys.stderr)
        return 130
    finally:
        # Последняя точка кода перед завершением процесса — исключение
        # отсюда никто дальше не поймает, поэтому оно гасится здесь.
        try:
            container.shutdown()
        except Exception:
            _LOGGER.exception("Не удалось корректно завершить работу приложения")


if __name__ == "__main__":
    raise SystemExit(run())
