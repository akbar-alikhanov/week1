"""Тесты парсера PDF-сертификатов (требуют PyMuPDF)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")

from app.parsers.pdf_parser import PdfParser, compute_file_hash  # noqa: E402


def _find_font() -> str | None:
    """Находит доступный в системе кириллический шрифт."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def _write_pdf(path: Path, text: str) -> None:
    """Создаёт одностраничный PDF с заданным текстом."""
    document = fitz.open()
    page = document.new_page()
    font = _find_font()
    rect = fitz.Rect(40, 40, 550, 800)
    if font:
        page.insert_textbox(rect, text, fontsize=10, fontfile=font, fontname="F0")
    else:  # pragma: no cover — резервный вариант без кириллицы
        page.insert_textbox(rect, text, fontsize=10, fontname="helv")
    document.save(path)
    document.close()


@pytest.fixture
def sample_certificate(tmp_path: Path) -> Path:
    """Создаёт синтетический PDF-сертификат для тестов."""
    path = tmp_path / "183255.pdf"
    _write_pdf(
        path,
        "СЕРТИФИКАТ СООТВЕТСТВИЯ\n№ UZ.AMT.01.183255\n\n"
        "Продукция: Лечебные травы, сироп 100 мл\n"
        "Торговая марка: «Herbal Doctor»\n"
        "Срок действия: с 22.03.2024 по 22.03.2029\n",
    )
    return path


@pytest.fixture
def sample_appendix_certificate(tmp_path: Path) -> Path:
    """Создаёт синтетический PDF с таблицей «Приложение к сертификату».

    Воспроизводит структуру реального сертификата органа по сертификации:
    титульный лист без данных о конкретном товаре плюс отдельная таблица
    построчных позиций (номер / наименование / срок годности).
    """
    path = tmp_path / "010099227940.pdf"
    cover_text = (
        "СЕРТИФИКАТ СООТВЕТСТВИЯ\n№ UZ.SMT-01-0099-227940\n\n"
        "Продукция согласно приложению\n"
        "Действителен до 04 Февраль 2029 г.\n"
    )
    appendix_text = (
        "ПРИЛОЖЕНИЕ К СЕРТИФИКАТУ\n"
        "№ \nНаименование\nпродукции \nСрок годности \nКоличество \n\n"
        "1\nЗубная паста Colgate TOTAL PRO 75мл 48 шт/кор\n2029-02-04\n7728 шт\n\n"
        "2\nЗубная паста Colgate Optic White 75мл 48 шт/кор\n2029-02-21\n4368 шт\n\n"
        "3\nЗубная паста Colgate Max Blesk 100мл 48 шт/кор\n2029-03-08\n30240 шт\n"
    )
    font = _find_font()
    rect = fitz.Rect(40, 40, 550, 800)
    document = fitz.open()
    for text in (cover_text, appendix_text):
        page = document.new_page()
        if font:
            page.insert_textbox(rect, text, fontsize=10, fontfile=font, fontname="F0")
        else:  # pragma: no cover — резервный вариант без кириллицы
            page.insert_textbox(rect, text, fontsize=10, fontname="helv")
    document.save(path)
    document.close()
    return path


class TestComputeFileHash:
    """Проверки вычисления хэша файла."""

    def test_hash_is_deterministic(self, tmp_path: Path) -> None:
        """Хэш одного и того же содержимого совпадает при повторном вычислении."""
        file_path = tmp_path / "a.bin"
        file_path.write_bytes(b"hello world")
        assert compute_file_hash(file_path) == compute_file_hash(file_path)

    def test_hash_differs_for_different_content(self, tmp_path: Path) -> None:
        """Разное содержимое даёт разные хэши."""
        first = tmp_path / "a.bin"
        second = tmp_path / "b.bin"
        first.write_bytes(b"content-a")
        second.write_bytes(b"content-b")
        assert compute_file_hash(first) != compute_file_hash(second)


class TestPdfParser:
    """Проверки полного разбора PDF в доменный объект."""

    def test_parse_extracts_all_fields(self, sample_certificate: Path) -> None:
        """Разбор синтетического сертификата извлекает все ключевые поля."""
        parser = PdfParser()
        certificates = parser.parse(sample_certificate)

        assert len(certificates) == 1
        certificate = certificates[0]
        assert "Лечебные травы" in certificate.product_name
        # Номер сертификата всегда берётся из имени файла, а не из текста —
        # на практике оно совпадает с номером и не зависит от разночтений
        # распознавания текста внутри PDF.
        assert certificate.certificate_number == "183255"
        assert certificate.row_index == 0
        assert certificate.expiry_date is not None
        assert certificate.expiry_date.year == 2029
        assert certificate.volume_value == pytest.approx(100.0)
        assert certificate.volume_unit == "ml"
        assert certificate.file_hash
        assert certificate.pdf_name == "183255.pdf"

    def test_parse_sets_pdf_path(self, sample_certificate: Path) -> None:
        """Путь к файлу сохраняется в объекте сертификата."""
        certificates = PdfParser().parse(sample_certificate)
        assert certificates[0].pdf_path == str(sample_certificate)

    def test_page_count(self, sample_certificate: Path) -> None:
        """Количество страниц определяется корректно."""
        assert PdfParser().page_count(sample_certificate) == 1

    def test_render_page_produces_png(self, sample_certificate: Path) -> None:
        """Отрисовка страницы возвращает непустые данные PNG."""
        payload, width, height = PdfParser().render_page(sample_certificate, 0, zoom=1.0)
        assert payload[:8] == b"\x89PNG\r\n\x1a\n"
        assert width > 0
        assert height > 0

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        """Отсутствующий файл порождает ожидаемое исключение."""
        from app.core.exceptions import PdfParsingError

        with pytest.raises(PdfParsingError):
            PdfParser().parse(tmp_path / "does-not-exist.pdf")


class TestPdfParserAppendix:
    """Проверки разбора сертификата с таблицей «Приложение к сертификату»."""

    def test_parse_returns_one_certificate_per_appendix_row(
        self, sample_appendix_certificate: Path
    ) -> None:
        """Каждая строка таблицы приложения даёт отдельный объект Certificate."""
        certificates = PdfParser().parse(sample_appendix_certificate)

        assert len(certificates) == 3
        # row_index зеркалит собственную нумерацию таблицы (с 1) — 0 отдельно
        # зарезервирован под сертификаты без приложения (единственная позиция).
        assert [c.row_index for c in certificates] == [1, 2, 3]
        assert "TOTAL PRO" in certificates[0].product_name
        assert "Optic White" in certificates[1].product_name
        assert "Max Blesk" in certificates[2].product_name

    def test_appendix_rows_have_own_expiry_dates(self, sample_appendix_certificate: Path) -> None:
        """У каждой позиции — собственный срок годности из таблицы, а не из титула."""
        certificates = PdfParser().parse(sample_appendix_certificate)
        expiry_by_row = {c.row_index: c.expiry_date for c in certificates}

        assert expiry_by_row[1] == date(2029, 2, 4)
        assert expiry_by_row[2] == date(2029, 2, 21)
        # Строка 3 истекает позже даты "Действителен до" с титульного листа —
        # доказательство, что дата с титула для построчного срока не берётся.
        assert expiry_by_row[3] == date(2029, 3, 8)

    def test_appendix_rows_share_certificate_number_from_filename(
        self, sample_appendix_certificate: Path
    ) -> None:
        """Все позиции одного файла получают номер сертификата из его имени."""
        certificates = PdfParser().parse(sample_appendix_certificate)
        assert all(c.certificate_number == "010099227940" for c in certificates)
        assert all(c.pdf_path == str(sample_appendix_certificate) for c in certificates)

    def test_appendix_rows_extract_volume_from_product_name(
        self, sample_appendix_certificate: Path
    ) -> None:
        """Объём в позициях приложения извлекается из наименования, не из титула."""
        certificates = PdfParser().parse(sample_appendix_certificate)
        volumes = {round(c.volume_value or 0): c.volume_unit for c in certificates}
        assert volumes == {75: "ml", 100: "ml"}

    def test_certificate_without_appendix_falls_back_to_single_record(
        self, sample_certificate: Path
    ) -> None:
        """Сертификат без таблицы приложения по-прежнему даёт одну запись."""
        certificates = PdfParser().parse(sample_certificate)
        assert len(certificates) == 1
        assert certificates[0].row_index == 0
