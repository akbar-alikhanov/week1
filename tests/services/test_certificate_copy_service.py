"""Тесты копирования подобранных PDF-сертификатов."""

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


def _result_with_certificate(row_number: int, source: Path) -> MatchResult:
    """Создаёт результат подбора, ссылающийся на реальный файл на диске."""
    certificate = make_certificate("Товар", str(source), expiry_date=dt.date(2029, 1, 1))
    score = ScoreBreakdown(name=1.0, volume=1.0, expiry=1.0, total=0.95)
    candidate = MatchCandidate(certificate=certificate, score=score, source=MatchSource.LEXICAL)
    row = OrderRow(row_number=row_number, product_name="Товар")
    return MatchResult(
        row=row, status=MatchStatus.MATCHED, candidates=[candidate], selected_index=0
    )


class TestCopyForResults:
    """Проверки копирования сертификатов."""

    def test_copies_single_certificate(self, tmp_path: Path) -> None:
        """Единственный сертификат копируется в папку Certificates."""
        source = tmp_path / "source" / "183255.pdf"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"%PDF-1.4 fake content")

        output_file = tmp_path / "output" / "order_result.xlsx"
        results = [_result_with_certificate(1, source)]

        report = CertificateCopyService().copy_for_results(results, output_file)

        assert report.copied == 1
        assert report.destination == tmp_path / "output" / "Certificates"
        assert (report.destination / "183255.pdf").exists()

    def test_deduplicates_same_certificate_for_multiple_rows(self, tmp_path: Path) -> None:
        """Один и тот же сертификат для нескольких строк копируется один раз."""
        source = tmp_path / "source" / "183255.pdf"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"%PDF-1.4 fake content")

        output_file = tmp_path / "output" / "order_result.xlsx"
        results = [
            _result_with_certificate(1, source),
            _result_with_certificate(2, source),
            _result_with_certificate(3, source),
        ]

        report = CertificateCopyService().copy_for_results(results, output_file)

        assert report.copied == 1
        assert report.reused == 2
        assert len(list(report.destination.glob("*.pdf"))) == 1

    def test_missing_source_file_reported(self, tmp_path: Path) -> None:
        """Отсутствующий на диске файл сертификата фиксируется как пропущенный."""
        source = tmp_path / "source" / "missing.pdf"
        output_file = tmp_path / "output" / "order_result.xlsx"
        results = [_result_with_certificate(1, source)]

        report = CertificateCopyService().copy_for_results(results, output_file)

        assert report.copied == 0
        assert "missing.pdf" in report.missing

    def test_name_collision_gets_unique_suffix(self, tmp_path: Path) -> None:
        """Одинаковые имена файлов из разных папок не затирают друг друга."""
        first_source = tmp_path / "a" / "183255.pdf"
        second_source = tmp_path / "b" / "183255.pdf"
        first_source.parent.mkdir(parents=True)
        second_source.parent.mkdir(parents=True)
        first_source.write_bytes(b"first")
        second_source.write_bytes(b"second")

        output_file = tmp_path / "output" / "order_result.xlsx"
        results = [
            _result_with_certificate(1, first_source),
            _result_with_certificate(2, second_source),
        ]

        report = CertificateCopyService().copy_for_results(results, output_file)

        assert report.copied == 2
        copied_files = sorted(report.destination.glob("*.pdf"))
        assert len(copied_files) == 2
        contents = {path.read_bytes() for path in copied_files}
        assert contents == {b"first", b"second"}

    def test_no_certificates_to_copy(self, tmp_path: Path) -> None:
        """Отсутствие найденных сертификатов не создаёт папку и не порождает ошибок."""
        row = OrderRow(row_number=1, product_name="Товар")
        results = [MatchResult(row=row, status=MatchStatus.NOT_FOUND)]
        output_file = tmp_path / "output" / "order_result.xlsx"

        report = CertificateCopyService().copy_for_results(results, output_file)

        assert report.copied == 0
        assert not report.destination.exists()
