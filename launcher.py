"""Единая точка входа для сборки PyInstaller.

PyInstaller анализирует граф импортов начиная с указанного ему файла.
Отдельный тонкий launcher на верхнем уровне репозитория (а не
``app/main.py`` напрямую) — общепринятая практика: он не зависит от того,
как именно упакован пакет ``app``, и одинаково хорошо работает и при запуске
``python launcher.py``, и после сборки в EXE.
"""

from __future__ import annotations

from app.main import main

if __name__ == "__main__":
    raise SystemExit(main())
