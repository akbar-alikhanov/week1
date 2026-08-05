"""Тесты индексации папки сертификатов, включая инкрементальность."""

from __future__ import annotations

from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")

from app.config.settings import SettingsService  # noqa: E402
from app.core.events import EventBus  # noqa: E402
from app.database.connection import Database  # noqa: E402
from app.repositories.alias_repository import AliasRepository  # noqa: E402
from app.repositories.certificate_repository import CertificateRepository  # noqa: E402
from app.repositories.settings_repository import SettingsRepository  # noqa: E402
from app.services.indexing_service import IndexingService  # noqa: E402


def _find_font() -> str | None:
    """Находит в системе шрифт с поддержкой кириллицы.

    Базовый шрифт PyMuPDF (``helv``) не содержит кириллических глифов: текст
    на русском языке извлекается из него как последовательность заполнителей.
    Без реального кириллического шрифта эти тесты проверяли бы не разбор
    наименования, а деградацию к имени файла.
    """
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def _write_pdf(path: Path, text: str) -> None:
    """Создаёт минимальный PDF-файл с заданным текстом."""
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


def _write_appendix_pdf(path: Path, row_count: int, *, rows_per_page: int = 0) -> None:
    """Создаёт PDF с таблицей «Приложение к сертификату» из ``row_count`` позиций.

    Args:
        path: Путь создаваемого файла.
        row_count: Количество позиций таблицы.
        rows_per_page: Сколько позиций размещать на одной странице приложения
            (``0`` — все на одной, как раньше). Реальные сертификаты
            растягивают таблицу на много страниц — этот параметр нужен для
            проверки, что такой файл не обрезается лимитом страниц.
    """
    font = _find_font()
    rect = fitz.Rect(40, 40, 550, 800)

    def _row_text(i: int) -> str:
        return f"{i}\nТовар приложения {i} 75мл 48 шт/кор\n2029-0{(i % 9) + 1}-15\n100 шт"

    document = fitz.open()

    def _add_page(text: str) -> None:
        page = document.new_page()
        if font:
            page.insert_textbox(rect, text, fontsize=10, fontfile=font, fontname="F0")
        else:  # pragma: no cover — резервный вариант без кириллицы
            page.insert_textbox(rect, text, fontsize=10, fontname="helv")

    _add_page("Продукция согласно приложению")

    if rows_per_page <= 0:
        rows_text = "\n\n".join(_row_text(i) for i in range(1, row_count + 1))
        _add_page("ПРИЛОЖЕНИЕ К СЕРТИФИКАТУ\n" + rows_text)
    else:
        for start in range(1, row_count + 1, rows_per_page):
            chunk = range(start, min(start + rows_per_page, row_count + 1))
            rows_text = "\n\n".join(_row_text(i) for i in chunk)
            prefix = "ПРИЛОЖЕНИЕ К СЕРТИФИКАТУ\n" if start == 1 else ""
            _add_page(prefix + rows_text)

    document.save(path)
    document.close()


@pytest.fixture
def indexing_service(tmp_path: Path, database: Database) -> IndexingService:
    """Собранный сервис индексации поверх временной базы данных."""
    settings_service = SettingsService(tmp_path / "settings.json")
    settings_service.load()
    return IndexingService(
        CertificateRepository(database),
        AliasRepository(database),
        SettingsRepository(database),
        settings_service,
        EventBus(),
    )


class TestScan:
    """Проверки полного и инкрементального сканирования."""

    def test_scan_indexes_all_pdf_files(
        self,
        indexing_service: IndexingService,
        tmp_path: Path,
        certificate_repository: CertificateRepository,
    ) -> None:
        """Первичное сканирование индексирует все найденные PDF-файлы."""
        directory = tmp_path / "certificates"
        directory.mkdir()
        for index in range(3):
            _write_pdf(directory / f"{1000 + index}.pdf", f"Товар {index}\n№ {1000 + index}")

        result = indexing_service.scan(directory)

        assert result.scanned == 3
        assert result.added == 3
        assert certificate_repository.count("is_active = 1") == 3

    def test_rescan_without_changes_skips_all(
        self, indexing_service: IndexingService, tmp_path: Path
    ) -> None:
        """Повторное сканирование без изменений файлов не переиндексирует их."""
        directory = tmp_path / "certificates"
        directory.mkdir()
        _write_pdf(directory / "1000.pdf", "Товар")

        indexing_service.scan(directory)
        result = indexing_service.scan(directory)

        assert result.added == 0
        assert result.updated == 0
        assert result.skipped == 1

    def test_new_file_is_indexed_incrementally(
        self,
        indexing_service: IndexingService,
        tmp_path: Path,
        certificate_repository: CertificateRepository,
    ) -> None:
        """Новый файл, добавленный после первого скана, индексируется отдельно."""
        directory = tmp_path / "certificates"
        directory.mkdir()
        _write_pdf(directory / "1000.pdf", "Товар А")
        indexing_service.scan(directory)

        _write_pdf(directory / "1001.pdf", "Товар Б")
        result = indexing_service.scan(directory)

        assert result.added == 1
        assert result.skipped == 1
        assert certificate_repository.count("is_active = 1") == 2

    def test_modified_file_is_reindexed(
        self,
        indexing_service: IndexingService,
        tmp_path: Path,
        certificate_repository: CertificateRepository,
    ) -> None:
        """Изменённое содержимое файла приводит к переиндексации записи."""
        import time

        directory = tmp_path / "certificates"
        directory.mkdir()
        path = directory / "1000.pdf"
        _write_pdf(path, "Старое наименование товара")
        indexing_service.scan(directory)

        time.sleep(1.1)  # гарантирует изменение mtime на большинстве файловых систем
        _write_pdf(path, "Новое наименование товара после правки")
        result = indexing_service.scan(directory)

        assert result.updated == 1
        certificate = certificate_repository.get_by_path(str(path))
        assert certificate is not None
        assert "Новое" in certificate.product_name

    def test_deleted_file_deactivates_record(
        self,
        indexing_service: IndexingService,
        tmp_path: Path,
        certificate_repository: CertificateRepository,
    ) -> None:
        """Файл, удалённый из папки, деактивируется, а не стирается из базы."""
        directory = tmp_path / "certificates"
        directory.mkdir()
        path = directory / "1000.pdf"
        _write_pdf(path, "Товар")
        indexing_service.scan(directory)

        path.unlink()
        result = indexing_service.scan(directory)

        assert result.removed == 1
        assert certificate_repository.count("is_active = 1") == 0
        assert certificate_repository.count() == 1  # запись сохранена, не удалена

    def test_empty_directory_returns_zero_results(
        self, indexing_service: IndexingService, tmp_path: Path
    ) -> None:
        """Пустая папка не вызывает ошибок и даёт нулевые результаты."""
        directory = tmp_path / "empty"
        directory.mkdir()
        result = indexing_service.scan(directory)
        assert result.scanned == 0
        assert result.added == 0

    def test_missing_directory_returns_zero_results(
        self, indexing_service: IndexingService, tmp_path: Path
    ) -> None:
        """Несуществующая папка обрабатывается без исключения."""
        result = indexing_service.scan(tmp_path / "does-not-exist")
        assert result.scanned == 0

    def test_force_reindexes_unchanged_files(
        self, indexing_service: IndexingService, tmp_path: Path
    ) -> None:
        """Флаг force переиндексирует файлы, даже если они не изменились."""
        directory = tmp_path / "certificates"
        directory.mkdir()
        _write_pdf(directory / "1000.pdf", "Товар")
        indexing_service.scan(directory)

        result = indexing_service.scan(directory, force=True)
        assert result.updated == 1
        assert result.skipped == 0


class TestScanAppendixCertificates:
    """Проверки сканирования файлов с таблицей «Приложение к сертификату»."""

    def test_scan_stores_one_row_per_appendix_position(
        self,
        indexing_service: IndexingService,
        tmp_path: Path,
        certificate_repository: CertificateRepository,
    ) -> None:
        """Один файл с таблицей из 5 позиций даёт 5 записей в справочнике."""
        directory = tmp_path / "certificates"
        directory.mkdir()
        _write_appendix_pdf(directory / "010099227940.pdf", row_count=5)

        result = indexing_service.scan(directory)

        assert result.scanned == 1
        assert result.added == 5
        assert certificate_repository.count("is_active = 1") == 5
        assert certificate_repository.count("certificate_number = '010099227940'") == 5

    def test_default_settings_read_appendix_spanning_many_pages(
        self,
        indexing_service: IndexingService,
        tmp_path: Path,
        certificate_repository: CertificateRepository,
    ) -> None:
        """Индексация с настройками по умолчанию не обрезает длинное приложение.

        Регрессия: настройка ``IndexingSettings.max_pages`` (сколько страниц
        PDF читать) когда-то по умолчанию ограничивала разбор четырьмя
        страницами — этого хватало для титульного листа, но не для таблицы
        приложения, растянутой на много страниц отдельными позициями
        (реальный сертификат может занимать десяток страниц и больше).
        Здесь используются настройки по умолчанию (фикстура их не меняет),
        чтобы поймать именно такую регрессию, а не скрыть её завышенным
        лимитом, заданным вручную в тесте.
        """
        directory = tmp_path / "certificates"
        directory.mkdir()
        _write_appendix_pdf(directory / "010099227940.pdf", row_count=8, rows_per_page=1)

        result = indexing_service.scan(directory)

        assert result.added == 8
        assert certificate_repository.count("pdf_path LIKE '%010099227940.pdf'") == 8

    def test_rescan_after_appendix_shrinks_removes_stale_rows(
        self,
        indexing_service: IndexingService,
        tmp_path: Path,
        certificate_repository: CertificateRepository,
    ) -> None:
        """Позиции, пропавшие из файла между сканами, удаляются из справочника."""
        directory = tmp_path / "certificates"
        directory.mkdir()
        path = directory / "010099227940.pdf"
        _write_appendix_pdf(path, row_count=5)
        indexing_service.scan(directory)
        assert certificate_repository.count() == 5

        import time

        time.sleep(1.1)  # гарантирует изменение mtime на большинстве файловых систем
        _write_appendix_pdf(path, row_count=2)
        result = indexing_service.scan(directory)

        assert result.updated == 2
        assert certificate_repository.count() == 2


class TestDiscoverFiles:
    """Проверки поиска PDF-файлов в файловой системе."""

    def test_finds_only_pdf_files(self, indexing_service: IndexingService, tmp_path: Path) -> None:
        """Находятся только файлы с расширением .pdf."""
        directory = tmp_path / "mixed"
        directory.mkdir()
        (directory / "a.pdf").write_bytes(b"%PDF")
        (directory / "b.txt").write_text("не сертификат")
        (directory / "c.PDF").write_bytes(b"%PDF")  # регистр расширения

        files = indexing_service.discover_files(directory)
        assert len(files) == 2

    def test_recursive_scan_finds_nested_files(
        self, indexing_service: IndexingService, tmp_path: Path
    ) -> None:
        """При включённой рекурсии находятся файлы во вложенных папках."""
        nested = tmp_path / "root" / "sub"
        nested.mkdir(parents=True)
        (nested / "deep.pdf").write_bytes(b"%PDF")

        files = indexing_service.discover_files(tmp_path / "root", recursive=True)
        assert len(files) == 1

    def test_non_recursive_scan_ignores_nested_files(
        self, indexing_service: IndexingService, tmp_path: Path
    ) -> None:
        """Без рекурсии вложенные файлы не находятся."""
        nested = tmp_path / "root" / "sub"
        nested.mkdir(parents=True)
        (nested / "deep.pdf").write_bytes(b"%PDF")

        files = indexing_service.discover_files(tmp_path / "root", recursive=False)
        assert files == []


class TestIndexSingleFile:
    """Проверки точечной индексации одного файла (для наблюдателя за папкой)."""

    def test_indexes_valid_file(
        self,
        indexing_service: IndexingService,
        tmp_path: Path,
        certificate_repository: CertificateRepository,
    ) -> None:
        """Корректный PDF индексируется и сохраняется в базе."""
        path = tmp_path / "1000.pdf"
        _write_pdf(path, "Новый товар")
        certificates = indexing_service.index_single_file(path)
        assert len(certificates) == 1
        assert certificate_repository.get_by_path(str(path)) is not None

    def test_non_pdf_file_ignored(self, indexing_service: IndexingService, tmp_path: Path) -> None:
        """Файл, не являющийся PDF, игнорируется."""
        path = tmp_path / "note.txt"
        path.write_text("не сертификат")
        assert indexing_service.index_single_file(path) == []
