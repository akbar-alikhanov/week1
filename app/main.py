"""Точка входа приложения.

Один исполняемый файл обслуживает два режима:

* без аргументов — графический интерфейс (основной сценарий);
* с командой — консольный режим для пакетной обработки и диагностики.

Разделение сделано так, чтобы тяжёлые модули графики не импортировались,
когда они не нужны: это ускоряет запуск консольных команд и делает EXE
пригодным для планировщика задач.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from app.core.constants import APP_NAME, APP_VERSION
from app.core.container import ApplicationContainer
from app.core.logging_setup import install_excepthook

_LOGGER = logging.getLogger(__name__)

#: Команды, обрабатываемые консольным режимом.
_CLI_COMMANDS = frozenset({"index", "process", "search", "stats", "selfcheck"})

#: Глобальные флаги консольного парсера, поглощающие следующий аргумент —
#: нужны, чтобы отличить их значение от имени подкоманды при сканировании.
_VALUE_FLAGS = frozenset({"--data-dir"})


def _wants_cli_mode(args: list[str]) -> bool:
    """Определяет, относится ли команда к консольному режиму.

    Простая проверка ``args[0] in _CLI_COMMANDS`` ломается на естественном
    порядке аргументов вида ``certmatcher --data-dir X selfcheck``: подкоманда
    консольного парсера (:func:`app.cli.build_parser`) может стоять не первой,
    если ей предшествуют глобальные флаги. Функция пропускает такие флаги и
    их значения, находя первый содержательный токен.

    Args:
        args: Аргументы командной строки без имени программы.

    Returns:
        ``True``, если первый значимый токен — известная консольная команда.
    """
    skip_next = False
    for token in args:
        if skip_next:
            skip_next = False
            continue
        if token in _VALUE_FLAGS:
            skip_next = True
            continue
        if token.startswith("-"):
            continue
        return token in _CLI_COMMANDS
    return False


def _parse_gui_arguments(argv: list[str]) -> argparse.Namespace:
    """Разбирает аргументы графического режима.

    Args:
        argv: Аргументы командной строки.

    Returns:
        Разобранные аргументы.
    """
    parser = argparse.ArgumentParser(
        prog="certmatcher",
        description=f"{APP_NAME} {APP_VERSION}",
        add_help=True,
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {APP_VERSION}")
    parser.add_argument("--data-dir", help="каталог данных приложения")
    parser.add_argument("--order", help="файл заказа, открываемый при запуске")
    parser.add_argument("--certificates", help="папка сертификатов")
    parser.add_argument(
        "--reset-window", action="store_true", help="сбросить сохранённое положение окна"
    )
    return parser.parse_args(argv)


def run_gui_mode(argv: list[str]) -> int:
    """Запускает приложение с графическим интерфейсом.

    Args:
        argv: Аргументы командной строки.

    Returns:
        Код возврата процесса.
    """
    arguments = _parse_gui_arguments(argv)
    container = ApplicationContainer.create(data_dir=arguments.data_dir)
    install_excepthook()

    try:
        import customtkinter  # noqa: F401 — проверка доступности графики
    except ImportError as error:
        print(
            "Не удалось запустить графический интерфейс: не установлен пакет customtkinter.\n"
            f"Подробности: {error}\n"
            "Доступен консольный режим: certmatcher --help",
            file=sys.stderr,
        )
        return 2

    try:
        container.startup()
    except Exception as error:
        _LOGGER.exception("Не удалось инициализировать приложение")
        _show_startup_failure(str(error))
        return 1

    if arguments.reset_window:
        try:
            container.paths.window_state_file.unlink(missing_ok=True)
        except OSError:  # pragma: no cover
            pass

    if arguments.certificates:
        container.settings_service.update(
            lambda settings: setattr(
                settings.indexing, "certificates_dir", str(Path(arguments.certificates).resolve())
            )
        )
    if arguments.order:
        container.settings_service.update(
            lambda settings: setattr(
                settings.ui, "last_order_file", str(Path(arguments.order).resolve())
            )
        )

    from app.gui.app import run_gui

    try:
        return run_gui(container)
    except Exception:
        _LOGGER.exception("Аварийное завершение графического интерфейса")
        return 1
    finally:
        container.shutdown()


def _show_startup_failure(details: str) -> None:
    """Сообщает о невозможности запуска доступным способом.

    В собранном без консоли приложении вывод в ``stderr`` не виден, поэтому
    используется системное окно сообщения.

    Args:
        details: Текст ошибки.
    """
    message = (
        f"{APP_NAME} не смог запуститься.\n\n{details}\n\n"
        "Проверьте права доступа к папке данных и журналы в подпапке logs."
    )
    print(message, file=sys.stderr)
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_NAME, message)
        root.destroy()
    except Exception:
        pass


def _attach_parent_console() -> None:
    """Подключает вывод к консоли, из которой запущен процесс (Windows).

    EXE собирается в оконном режиме (``console=False``), чтобы двойной клик
    в Проводнике не мигал чёрным окном консоли. Но тот же EXE поддерживает
    консольные команды (``certmatcher.exe index ...``) для запуска из
    PowerShell/cmd — без вызова этой функции их вывод улетал бы в никуда,
    поскольку у оконного процесса Windows нет присоединённых стандартных
    потоков. Функция запрашивает у Windows консоль процесса-родителя и
    перепривязывает к ней stdout/stderr; при запуске двойным кликом
    родительской консоли нет, и вызов безопасно ничего не делает.
    """
    if sys.platform != "win32":  # pragma: no cover — актуально только для Windows
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        attach_parent_process = -1
        if kernel32.AttachConsole(attach_parent_process):
            sys.stdout = open("CONOUT$", "w", encoding="utf-8")  # noqa: SIM115, PTH123
            sys.stderr = open("CONOUT$", "w", encoding="utf-8")  # noqa: SIM115, PTH123
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    """Точка входа приложения.

    Args:
        argv: Аргументы командной строки; ``None`` — взять из ``sys.argv``.

    Returns:
        Код возврата процесса.
    """
    args = list(sys.argv[1:] if argv is None else argv)

    if _wants_cli_mode(args):
        _attach_parent_console()
        from app.cli import run

        return run(args)

    if args and args[0] in {"-h", "--help"} and len(args) == 1:
        _attach_parent_console()
        from app.cli import build_parser

        build_parser().print_help()
        print("\nБез аргументов запускается графический интерфейс.")
        return 0

    return run_gui_mode(args)


if __name__ == "__main__":
    raise SystemExit(main())
