"""Конфигурация сборки PyInstaller: один EXE-файл для Windows.

Собирает приложение в единственный исполняемый файл без установки Python на
целевой машине. Запуск (из корня репозитория, на Windows, внутри окружения
с установленными зависимостями из ``pyproject.toml[dev]``)::

    python scripts/build_icon.py
    pyinstaller packaging/certmatcher.spec --noconfirm

Готовый файл появится в ``dist/BaltonCertMatcher.exe``.

Ключевые решения:

* **Оконный режим (без консоли).** Основной сценарий использования —
  двойной клик в Проводнике; консольное окно не должно мигать. Для
  административных команд (``certmatcher.exe index ...``) EXE сам
  подключается к консоли вызвавшего процесса — см.
  :func:`app.main._attach_parent_console`.
* **Семантический поиск не входит в основную сборку.** Пакеты
  ``sentence-transformers``/``torch`` весят более гигабайта и превратили бы
  «один лёгкий EXE» в задачу для сетевого администратора. Приложение
  полностью работоспособно без них (см. каскад подбора: псевдонимы → нечёткий
  поиск → семантика), поэтому они исключены явно, независимо от того,
  установлены ли они в окружении сборки. Для сборки с семантическим поиском
  уберите соответствующие пакеты из ``AI_EXCLUDES`` ниже и убедитесь, что
  ``pip install .[ai]`` выполнен в окружении сборки.
"""

from __future__ import annotations

from pathlib import Path

from PyInstaller.building.api import EXE, PYZ
from PyInstaller.building.build_main import Analysis
from PyInstaller.utils.hooks import collect_data_files

# packaging/certmatcher.spec -> корень репозитория
ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 — SPECPATH инжектируется PyInstaller
APP_NAME = "BaltonCertMatcher"
ICON_PATH = ROOT / "app" / "resources" / "icons" / "app.ico"
VERSION_FILE = ROOT / "packaging" / "version_info.txt"

# --------------------------------------------------------------------------- #
# Данные сторонних пакетов
# --------------------------------------------------------------------------- #
#: CustomTkinter хранит цветовые схемы и параметры масштабирования в JSON
#: внутри пакета и читает их в рантайме — без этих файлов виджеты не
#: создаются вовсе (FileNotFoundError при первом импорте).
datas: list[tuple[str, str]] = collect_data_files("customtkinter")

resources_dir = ROOT / "app" / "resources"
if resources_dir.exists():
    datas.append((str(resources_dir), "app/resources"))

try:
    import tkinterdnd2  # noqa: F401

    datas += collect_data_files("tkinterdnd2")
except ImportError:
    pass

# --------------------------------------------------------------------------- #
# Исключения
# --------------------------------------------------------------------------- #
#: Тяжёлый ML-стек семантического поиска — см. пояснение в докстринге модуля.
AI_EXCLUDES: list[str] = [
    "torch",
    "sentence_transformers",
    "transformers",
    "tokenizers",
    "huggingface_hub",
]

#: Инструменты разработки и тестирования, не нужные в конечном EXE.
DEV_EXCLUDES: list[str] = [
    "pytest",
    "_pytest",
    "mypy",
    "black",
    "ruff",
    "pip",
    "setuptools",
    "pkg_resources",
    "tkinter.test",
    "unittest",
    "doctest",
    "pydoc_data",
]

block_cipher = None

analysis = Analysis(
    [str(ROOT / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "customtkinter",
        "PIL._tkinter_finder",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[*AI_EXCLUDES, *DEV_EXCLUDES],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(analysis.pure, analysis.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.zipfiles,
    analysis.datas,
    [],
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON_PATH) if ICON_PATH.exists() else None,
    version=str(VERSION_FILE) if VERSION_FILE.exists() else None,
)
