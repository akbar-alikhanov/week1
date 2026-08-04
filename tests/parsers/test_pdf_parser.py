"""Тесты парсера PDF-сертификатов (требуют PyMuPDF)."""

from __future__ import annotations

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
        certificate = parser.parse(sample_certificate)

        assert "Лечебные травы" in certificate.product_name
        assert certificate.certificate_number == "UZ.AMT.01.183255"
        assert certificate.expiry_date is not None
        assert certificate.expiry_date.year == 2029
        assert certificate.volume_value == pytest.approx(100.0)
        assert certificate.volume_unit == "ml"
        assert certificate.file_hash
        assert certificate.pdf_name == "183255.pdf"

    def test_parse_sets_pdf_path(self, sample_certificate: Path) -> None:
        """Путь к файлу сохраняется в объекте сертификата."""
        certificate = PdfParser().parse(sample_certificate)
        assert certificate.pdf_path == str(sample_certificate)

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
