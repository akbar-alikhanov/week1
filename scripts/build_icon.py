"""Генерирует значок приложения (.ico) из программной иконки-щита.

Иконки интерфейса рисуются во время выполнения (см. :mod:`app.gui.icons`),
чтобы не тащить в сборку папку с картинками. Значок EXE — исключение: он
нужен ДО запуска Python (Проводник Windows, панель задач, ярлык), поэтому
для него один раз генерируется статический файл ``.ico`` с несколькими
размерами, встроенными в один контейнер.

Запуск::

    python scripts/build_icon.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

#: Размеры, которые Windows ожидает найти внутри .ico (ярлык, Проводник,
#: панель задач, крупные значки).
ICON_SIZES: tuple[int, ...] = (16, 20, 24, 32, 40, 48, 64, 128, 256)

#: Фирменный цвет иконки (совпадает с акцентом палитры «emerald»).
ICON_COLOR: str = "#146B5C"

#: Путь итогового файла.
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "app" / "resources" / "icons" / "app.ico"


def main() -> int:
    """Строит .ico-файл со значком приложения.

    Returns:
        Код возврата процесса.
    """
    from app.gui.icons import icons

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    base_size = max(ICON_SIZES)

    # Добавляем непрозрачную подложку: значок в стиле Windows 11 выглядит
    # как плитка со скруглёнными углами, а не «голая» векторная линия.
    from PIL import Image, ImageDraw

    padded = Image.new("RGBA", (base_size, base_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(padded)
    margin = base_size * 0.06
    draw.rounded_rectangle(
        (margin, margin, base_size - margin, base_size - margin),
        radius=base_size * 0.22,
        fill="#FFFFFF",
    )
    icon_size = int(base_size * 0.62)
    icon_image = icons.render_image("shield_check", icon_size, ICON_COLOR).convert("RGBA")
    offset = ((base_size - icon_size) // 2, (base_size - icon_size) // 2)
    padded.alpha_composite(icon_image, offset)

    padded.save(OUTPUT_PATH, format="ICO", sizes=[(size, size) for size in ICON_SIZES])
    print(f"Значок сохранён: {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size} байт)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
