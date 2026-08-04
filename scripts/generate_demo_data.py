"""Генератор демонстрационного набора данных.

Создаёт реалистичную папку сертификатов (PDF) и файл заказа (Excel), чтобы
приложение можно было оценить сразу после установки, не имея под рукой
рабочих документов.

Запуск::

    python scripts/generate_demo_data.py --output demo --certificates 120
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

#: Каталог товаров: (наименование, объёмы, торговая марка).
CATALOG: list[tuple[str, list[str], str]] = [
    ("Лечебные травы, сироп", ["100 мл", "150 мл", "200 мл"], "Herbal Doctor"),
    ("Витамин C, таблетки жевательные", ["30 таб", "60 таб"], "VitaLife"),
    ("Масло облепиховое", ["50 мл", "100 мл"], "Oblepiha Gold"),
    ("Сироп шиповника", ["100 мл", "250 мл"], "RoseHip"),
    ("Настойка эхинацеи", ["25 мл", "50 мл"], "ImmunoPlus"),
    ("Крем детский увлажняющий", ["45 г", "75 г"], "BabySoft"),
    ("Гель для суставов согревающий", ["50 г", "100 г"], "ArtroForte"),
    ("Чай травяной успокаивающий", ["20 саше", "40 саше"], "CalmTea"),
    ("Капли для глаз увлажняющие", ["10 мл", "15 мл"], "OptiClear"),
    ("Сироп подорожника", ["100 мл", "200 мл"], "PlantagoMed"),
    ("Мазь календулы", ["25 г", "40 г"], "CalendulaCare"),
    ("Порошок регидратационный", ["10 саше", "20 саше"], "RehydroSalt"),
    ("Спрей для горла с прополисом", ["30 мл", "50 мл"], "PropoSpray"),
    ("Капсулы рыбьего жира Омега-3", ["60 caps", "90 caps"], "OmegaPure"),
    ("Бальзам для губ защитный", ["4 г", "10 г"], "LipShield"),
    ("Раствор перекиси водорода 3%", ["100 мл", "200 мл"], "AntiseptPro"),
    ("Сироп алтея от кашля", ["100 мл", "125 мл"], "AltheaMed"),
    ("Таблетки активированного угля", ["10 таб", "50 таб"], "CarboMed"),
    ("Гель антисептический для рук", ["50 мл", "100 мл", "500 мл"], "CleanHands"),
    ("Пластырь бактерицидный", ["20 шт", "100 шт"], "MediPlast"),
]

MANUFACTURERS = [
    'ООО "ФИТО-ФАРМ", Республика Узбекистан, г. Ташкент',
    'СП ООО "MEDIPHARM ASIA", Республика Узбекистан, г. Самарканд',
    'АО "БИОСИНТЕЗ", Российская Федерация, г. Пенза',
    "Zhejiang Health Products Co. Ltd, Китайская Народная Республика",
]

ISSUERS = [
    'Орган по сертификации продукции "UZTEST" ООО',
    'Орган по сертификации "SIFAT NAZORAT" при Узстандарт',
    'Испытательный центр "MEDCERT" ООО',
]

CERTIFICATE_TEMPLATE = """РЕСПУБЛИКА УЗБЕКИСТАН
{issuer}

СЕРТИФИКАТ СООТВЕТСТВИЯ
№ {number}

Продукция: {product}
Торговая марка: «{brand}»
Изготовитель: {manufacturer}
Заявитель: ООО "BALTON TRADING ASIA", г. Ташкент, ул. Амира Темура, 15
Страна происхождения: {country}
Код ТН ВЭД: {tnved}

Соответствует требованиям нормативных документов:
O'z DSt {standard}

Срок действия: с {issued} по {expiry}
Дата регистрации: {issued}
Схема сертификации: 3а

Руководитель органа по сертификации _______________ {official}
"""


def _find_cyrillic_font() -> str | None:
    """Находит в системе шрифт с поддержкой кириллицы.

    Returns:
        Путь к файлу шрифта либо ``None``.
    """
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def generate_certificates(
    destination: Path, count: int, seed: int = 20240401
) -> list[dict[str, str]]:
    """Создаёт PDF-сертификаты в указанной папке.

    Args:
        destination: Каталог для файлов.
        count: Количество генерируемых сертификатов.
        seed: Зерно генератора случайных чисел (для воспроизводимости).

    Returns:
        Список описаний созданных сертификатов.
    """
    import fitz

    rng = random.Random(seed)
    destination.mkdir(parents=True, exist_ok=True)
    font_file = _find_cyrillic_font()
    created: list[dict[str, str]] = []
    number_base = 180000

    combinations = [(name, volume, brand) for name, volumes, brand in CATALOG for volume in volumes]
    rng.shuffle(combinations)

    for index in range(count):
        name, volume, brand = combinations[index % len(combinations)]
        issued = date(2023, 1, 1) + timedelta(days=rng.randint(0, 900))
        expiry = issued + timedelta(days=rng.choice([365 * 3, 365 * 5, 365 * 5 + 30]))
        number = f"UZ.AMT.01.{number_base + index * 7}"
        payload = CERTIFICATE_TEMPLATE.format(
            issuer=rng.choice(ISSUERS),
            number=number,
            product=f"{name} {volume}",
            brand=brand,
            manufacturer=rng.choice(MANUFACTURERS),
            country=rng.choice(["Узбекистан", "Россия", "Китай", "Турция"]),
            tnved=f"{rng.randint(2000, 3900)} {rng.randint(10, 99)} {rng.randint(100, 999)} 0",
            standard=f"{rng.randint(1000, 3200)}:{rng.randint(2015, 2023)}",
            issued=issued.strftime("%d.%m.%Y"),
            expiry=expiry.strftime("%d.%m.%Y"),
            official=rng.choice(["Иванов И.И.", "Каримов А.Б.", "Юсупов Ш.Т."]),
        )

        file_path = destination / f"{number_base + index * 7}.pdf"
        document = fitz.open()
        page = document.new_page()
        rect = fitz.Rect(45, 45, 550, 800)
        if font_file:
            page.insert_textbox(rect, payload, fontsize=10, fontfile=font_file, fontname="F0")
        else:  # pragma: no cover — резервный вариант без кириллицы
            page.insert_textbox(rect, payload, fontsize=10, fontname="helv")
        document.save(file_path)
        document.close()

        created.append(
            {
                "file": file_path.name,
                "number": number,
                "product": f"{name} {volume}",
                "expiry": expiry.strftime("%d.%m.%Y"),
            }
        )

    return created


def generate_order(destination: Path, certificates: list[dict[str, str]], rows: int = 40) -> Path:
    """Создаёт файл заказа в формате Excel.

    В заказ намеренно попадают позиции трёх типов: точно совпадающие с
    сертификатами, записанные иначе (сокращения, латиница) и отсутствующие
    в справочнике — чтобы продемонстрировать все ветви алгоритма.

    Args:
        destination: Путь создаваемого файла.
        certificates: Описания созданных сертификатов.
        rows: Количество строк заказа.

    Returns:
        Путь созданного файла.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    rng = random.Random(4242)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Заказ"

    sheet["A1"] = 'ООО "BALTON TRADING ASIA"'
    sheet["A2"] = f"Заказ на поставку № {rng.randint(1000, 9999)} от {date.today():%d.%m.%Y}"
    sheet["A1"].font = Font(bold=True, size=13)
    sheet["A2"].font = Font(size=10, italic=True)

    headers = [
        "№",
        "Код",
        "Наименование товара",
        "Кол-во",
        "Ед.",
        "Цена",
        "Сертификат",
        "Срок сертификата",
    ]
    header_row = 4
    for column, title in enumerate(headers, start=1):
        cell = sheet.cell(row=header_row, column=column, value=title)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="2F5D62")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    variants: list[str] = []
    for record in certificates:
        product = record["product"]
        variants.append(product)
        variants.append(product.replace(" мл", "мл").replace(", ", " "))
        variants.append(product.upper())
    rng.shuffle(variants)

    unknown = [
        "Шампунь лечебный дегтярный 250 мл",
        "Крем-гель для душа морской 400 мл",
        "Витамины для волос и ногтей 90 таб",
    ]

    for index in range(rows):
        source = rng.choice(unknown) if index % 13 == 12 else variants[index % len(variants)]
        row = header_row + 1 + index
        sheet.cell(row=row, column=1, value=index + 1)
        sheet.cell(row=row, column=2, value=f"BT-{10000 + index * 3}")
        sheet.cell(row=row, column=3, value=source)
        sheet.cell(row=row, column=4, value=rng.choice([10, 20, 50, 100, 200]))
        sheet.cell(row=row, column=5, value="шт")
        sheet.cell(row=row, column=6, value=round(rng.uniform(5000, 90000), 2))

    widths = {"A": 6, "B": 12, "C": 46, "D": 9, "E": 7, "F": 12, "G": 22, "H": 18}
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = f"A{header_row + 1}"

    destination.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(destination)
    return destination


def main() -> int:
    """Точка входа генератора демонстрационных данных.

    Returns:
        Код возврата процесса.
    """
    parser = argparse.ArgumentParser(description="Генератор демонстрационных данных")
    parser.add_argument("--output", type=Path, default=Path("demo"), help="Каталог результата")
    parser.add_argument("--certificates", type=int, default=120, help="Количество сертификатов")
    parser.add_argument("--rows", type=int, default=40, help="Количество строк заказа")
    arguments = parser.parse_args()

    certificates_dir = arguments.output / "Сертификаты"
    order_file = arguments.output / "Заказ_демо.xlsx"

    print(f"Генерация {arguments.certificates} сертификатов в {certificates_dir} …")
    created = generate_certificates(certificates_dir, arguments.certificates)
    print(f"Генерация заказа ({arguments.rows} строк) в {order_file} …")
    generate_order(order_file, created, arguments.rows)
    print("Готово.")
    print(f"  Папка сертификатов: {certificates_dir.resolve()}")
    print(f"  Файл заказа:        {order_file.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
