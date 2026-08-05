"""Тесты копирования подобранных PDF-сертификатов по номеру в имени файла."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from app.models.matching import (
    MatchCandidate,
    MatchResult,
    MatchSource,
    MatchStatus,
    ScoreBreakdown,
)
from app.models.order import OrderRow
from app.services.certificate_copy_service import CertificateCopyService
from tests.conftest import make_certificate


def _result_with_certificate(row_number: int, certificate_number: str) -> MatchResult:
    """Создаёт результат подбора, ссылающийся на номер сертификата."""
    certificate = make_certificate(
        "Товар", certificate_number=certificate_number, expiry_date=dt.date(2029, 1, 1)
    )
    score = ScoreBreakdown(name=1.0, volume=1.0, expiry=1.0, total=0.95)
    candidate = MatchCandidate(certificate=certificate, score=score, source=MatchSource.LEXICAL)
    row = OrderRow(row_number=row_number, product_name="Товар")
    return MatchResult(
        row=row, status=MatchStatus.MATCHED, candidates=[candidate], selected_index=0
    )


class TestCopyForResults:
    """Проверки копирования сертификатов, найденных по номеру в имени файла."""

    def test_copies_single_certificate(self, tmp_path: Path) -> None:
        """Единственный сертификат находится по номеру и копируется в Certificates."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "183255.pdf").write_bytes(b"%PDF-1.4 fake content")

        output_file = tmp_path / "output" / "order_result.xlsx"
        results = [_result_with_certificate(1, "183255")]

        service = CertificateCopyService(source_dir=source_dir)
        report = service.copy_for_results(results, output_file)

        assert report.copied == 1
        assert report.destination == tmp_path / "output" / "Certificates"
        assert (report.destination / "183255.pdf").exists()

    def test_finds_file_with_prefix_around_number(self, tmp_path: Path) -> None:
        """Номер, встречающийся как часть более длинного имени файла, находится."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "UZ.SMT-01-0099-183255.pdf").write_bytes(b"%PDF-1.4 fake content")

        output_file = tmp_path / "output" / "order_result.xlsx"
        results = [_result_with_certificate(1, "01-0099-183255")]

        report = CertificateCopyService(source_dir=source_dir).copy_for_results(
            results, output_file
        )

        assert report.copied == 1

    def test_searches_subfolders_recursively(self, tmp_path: Path) -> None:
        """PDF во вложенной папке источника тоже находится."""
        nested = tmp_path / "source" / "2029"
        nested.mkdir(parents=True)
        (nested / "183255.pdf").write_bytes(b"%PDF-1.4 fake content")

        output_file = tmp_path / "output" / "order_result.xlsx"
        results = [_result_with_certificate(1, "183255")]

        report = CertificateCopyService(source_dir=tmp_path / "source").copy_for_results(
            results, output_file
        )

        assert report.copied == 1

    def test_deduplicates_same_certificate_for_multiple_rows(self, tmp_path: Path) -> None:
        """Один и тот же номер сертификата для нескольких строк копируется один раз."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "183255.pdf").write_bytes(b"%PDF-1.4 fake content")

        output_file = tmp_path / "output" / "order_result.xlsx"
        results = [
            _result_with_certificate(1, "183255"),
            _result_with_certificate(2, "183255"),
            _result_with_certificate(3, "183255"),
        ]

        report = CertificateCopyService(source_dir=source_dir).copy_for_results(
            results, output_file
        )

        assert report.copied == 1
        assert report.reused == 2
        assert len(list(report.destination.glob("*.pdf"))) == 1

    def test_missing_pdf_reported(self, tmp_path: Path) -> None:
        """Номер, для которого нет PDF в папке источника, фиксируется как отсутствующий."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        output_file = tmp_path / "output" / "order_result.xlsx"
        results = [_result_with_certificate(1, "999999")]

        report = CertificateCopyService(source_dir=source_dir).copy_for_results(
            results, output_file
        )

        assert report.copied == 0
        assert "999999" in report.missing

    def test_no_source_dir_configured_reports_all_missing(self, tmp_path: Path) -> None:
        """Без настроенной папки источника все сертификаты считаются отсутствующими."""
        output_file = tmp_path / "output" / "order_result.xlsx"
        results = [_result_with_certificate(1, "183255")]

        report = CertificateCopyService(source_dir=None).copy_for_results(results, output_file)

        assert report.copied == 0
        assert "183255" in report.missing

    def test_name_collision_gets_unique_suffix(self, tmp_path: Path) -> None:
        """Существующий в папке результата файл с тем же именем не затирается."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "183255.pdf").write_bytes(b"new content")

        destination = tmp_path / "output" / "Certificates"
        destination.mkdir(parents=True)
        (destination / "183255.pdf").write_bytes(b"pre-existing content")

        output_file = tmp_path / "output" / "order_result.xlsx"
        results = [_result_with_certificate(1, "183255")]

        report = CertificateCopyService(source_dir=source_dir).copy_for_results(
            results, output_file
        )

        assert report.copied == 1
        copied_files = sorted(report.destination.glob("*.pdf"))
        assert len(copied_files) == 2
        contents = {path.read_bytes() for path in copied_files}
        assert contents == {b"new content", b"pre-existing content"}

    def test_no_certificates_to_copy(self, tmp_path: Path) -> None:
        """Отсутствие найденных сертификатов не создаёт папку и не порождает ошибок."""
        row = OrderRow(row_number=1, product_name="Товар")
        results = [MatchResult(row=row, status=MatchStatus.NOT_FOUND)]
        output_file = tmp_path / "output" / "order_result.xlsx"

        report = CertificateCopyService(source_dir=tmp_path / "source").copy_for_results(
            results, output_file
        )

        assert report.copied == 0
        assert not report.destination.exists()
