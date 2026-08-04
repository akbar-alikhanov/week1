"""Копирование подобранных PDF-сертификатов в папку результата.

Ключевое требование: если один сертификат подходит нескольким товарам, файл
копируется один раз. Дедупликация выполняется по исходному пути, а конфликты
имён (одинаковые имена файлов из разных подпапок) разрешаются добавлением
суффикса — иначе один сертификат молча затёр бы другой.
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

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class CopyReport:
    """Итог копирования сертификатов.

    Attributes:
        destination: Каталог, в который выполнено копирование.
        copied: Количество скопированных файлов.
        reused: Сколько раз файл уже был скопирован ранее (дедупликация).
        missing: Файлы, отсутствующие на диске.
        failed: Пары «файл → причина ошибки».
        mapping: Соответствие «исходный путь → путь в папке результата».
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
            parts.append(f"отсутствуют {len(self.missing)}")
        if self.failed:
            parts.append(f"ошибок {len(self.failed)}")
        return "Сертификаты: " + ", ".join(parts)


class CertificateCopyService:
    """Копирует PDF-файлы подобранных сертификатов."""

    def __init__(self, *, dirname: str = CERTIFICATES_OUTPUT_DIRNAME) -> None:
        """Создаёт сервис копирования.

        Args:
            dirname: Имя создаваемой папки с сертификатами.
        """
        self._dirname = dirname or CERTIFICATES_OUTPUT_DIRNAME

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

        sources: list[Path] = []
        seen: set[str] = set()
        for result in results:
            certificate = result.certificate
            if certificate is None:
                continue
            key = certificate.pdf_path
            if key in seen:
                report.reused += 1
                continue
            seen.add(key)
            sources.append(certificate.path)

        if not sources:
            _LOGGER.info("Нет сертификатов для копирования")
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
        for source in sources:
            if reporter is not None:
                reporter.token.raise_if_cancelled()

            if not source.exists():
                report.missing.append(source.name)
                _LOGGER.warning("Файл сертификата отсутствует: %s", source)
                if reporter is not None:
                    reporter.advance(1, stage="copying")
                continue

            target = self._unique_target(destination, source.name, used_names)
            try:
                shutil.copy2(source, target)
                used_names.add(target.name)
                report.copied += 1
                report.mapping[str(source)] = target
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
