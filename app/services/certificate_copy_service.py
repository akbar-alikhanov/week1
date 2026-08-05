"""Копирование подобранных PDF-сертификатов в папку результата.

PDF не читаются и не анализируются — они только копируются. Связь между
строкой базы сертификатов и файлом на диске устанавливается исключительно
по имени файла: он находится по номеру сертификата
(:mod:`app.services.certificate_file_locator`), затем просто копируется.
Если один и тот же номер сертификата нужен нескольким товарам заказа, файл
копируется один раз — дедупликация выполняется по номеру, а конфликты имён
(одинаковые имена файлов из разных подпапок) разрешаются добавлением
суффикса, иначе один сертификат молча затёр бы другой.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from app.core.constants import CERTIFICATES_OUTPUT_DIRNAME
from app.core.events import ProgressReporter
from app.core.exceptions import ExportError
from app.models.matching import MatchResult
from app.services.certificate_file_locator import CertificateFileIndex

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class CopyReport:
    """Итог копирования сертификатов.

    Attributes:
        destination: Каталог, в который выполнено копирование.
        copied: Количество скопированных файлов.
        reused: Сколько раз файл уже был скопирован ранее (дедупликация).
        missing: Номера сертификатов, для которых PDF не найден в папке.
        failed: Пары «файл → причина ошибки».
        mapping: Соответствие «номер сертификата → путь в папке результата».
    """

    destination: Path
    copied: int = 0
    reused: int = 0
    missing: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    mapping: dict[str, Path] = field(default_factory=dict)

    def summary(self) -> str:
        """Возвращает однострочную сводку для журнала и уведомления."""
        parts = [f"скопировано {self.copied}"]
        if self.reused:
            parts.append(f"повторных ссылок {self.reused}")
        if self.missing:
            parts.append(f"файл не найден {len(self.missing)}")
        if self.failed:
            parts.append(f"ошибок {len(self.failed)}")
        return "Сертификаты: " + ", ".join(parts)


class CertificateCopyService:
    """Находит и копирует PDF-файлы подобранных сертификатов по номеру."""

    def __init__(
        self,
        *,
        source_dir: Path | None,
        dirname: str = CERTIFICATES_OUTPUT_DIRNAME,
        recursive: bool = True,
    ) -> None:
        """Создаёт сервис копирования.

        Args:
            source_dir: Папка, в которой ищутся PDF-файлы сертификатов.
            dirname: Имя создаваемой папки с сертификатами.
            recursive: Искать ли PDF во вложенных папках ``source_dir``.
        """
        self._source_dir = source_dir
        self._dirname = dirname or CERTIFICATES_OUTPUT_DIRNAME
        self._recursive = recursive

    def target_directory(self, output_file: Path) -> Path:
        """Определяет папку для копий сертификатов.

        Args:
            output_file: Путь итогового файла Excel.

        Returns:
            Путь папки ``Certificates`` рядом с итоговым файлом.
        """
        return output_file.parent / self._dirname

    def copy_for_results(
        self,
        results: list[MatchResult],
        output_file: Path,
        *,
        reporter: ProgressReporter | None = None,
    ) -> CopyReport:
        """Копирует сертификаты, выбранные для строк заказа.

        Args:
            results: Результаты подбора.
            output_file: Путь итогового файла Excel.
            reporter: Приёмник прогресса.

        Returns:
            Итог копирования.

        Raises:
            ExportError: Если папку назначения не удалось создать.
        """
        destination = self.target_directory(output_file)
        report = CopyReport(destination=destination)

        numbers: list[str] = []
        seen: set[str] = set()
        for result in results:
            certificate = result.certificate
            if certificate is None or not certificate.certificate_number:
                continue
            number = certificate.certificate_number
            if number in seen:
                report.reused += 1
                continue
            seen.add(number)
            numbers.append(number)

        if not numbers:
            _LOGGER.info("Нет сертификатов для копирования")
            return report

        index = CertificateFileIndex(self._source_dir, recursive=self._recursive)
        sources: list[tuple[str, Path]] = []
        for number in numbers:
            path = index.find(number)
            if path is None:
                report.missing.append(number)
                _LOGGER.warning("PDF-файл сертификата не найден: %s", number)
                continue
            sources.append((number, path))

        if not sources:
            return report

        try:
            destination.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise ExportError(
                f"Не удалось создать папку {destination}", details=str(error)
            ) from error

        if reporter is not None:
            reporter.start(len(sources), "Копирование сертификатов", "copying")

        used_names: set[str] = set()
        for number, source in sources:
            if reporter is not None:
                reporter.token.raise_if_cancelled()

            target = self._unique_target(destination, source.name, used_names)
            try:
                shutil.copy2(source, target)
                used_names.add(target.name)
                report.copied += 1
                report.mapping[number] = target
            except OSError as error:
                report.failed.append((source.name, str(error)))
                _LOGGER.warning("Не удалось скопировать %s: %s", source.name, error)

            if reporter is not None:
                reporter.advance(1, f"Скопировано {report.copied}", "copying")

        if reporter is not None:
            reporter.finish(report.summary(), "copying")

        _LOGGER.info("%s → %s", report.summary(), destination)
        return report

    def _unique_target(self, destination: Path, name: str, used: set[str]) -> Path:
        """Подбирает свободное имя файла в папке назначения.

        Args:
            destination: Папка назначения.
            name: Исходное имя файла.
            used: Имена, занятые в текущем запуске.

        Returns:
            Путь, по которому можно безопасно писать.
        """
        candidate = destination / name
        if name not in used and not candidate.exists():
            return candidate

        stem = candidate.stem
        suffix = candidate.suffix
        index = 2
        while True:
            attempt = destination / f"{stem}_{index}{suffix}"
            if attempt.name not in used and not attempt.exists():
                return attempt
            index += 1
