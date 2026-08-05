"""Поиск PDF-файла сертификата по номеру в имени файла.

Единственная связь между Excel-базой сертификатов и PDF-файлами — номер
сертификата, встречающийся в имени файла (``01-0099-183255.pdf``,
``UZ.SMT-01-0099-183255.pdf``). Содержимое PDF никогда не читается: поиск
выполняется по имени файла, найденный файл только копируется.
"""

from __future__ import annotations

from pathlib import Path

from app.core.constants import PDF_EXTENSIONS


def normalize_number(value: str) -> str:
    """Приводит номер сертификата к виду, пригодному для сравнения имён файлов.

    Оставляет только буквы и цифры в верхнем регистре — так «01-0099-183255»
    и «01.0099.183255» или «uz.smt-01-0099-183255» совпадают независимо от
    разделителей и регистра, которые органы по сертификации не унифицируют.

    Args:
        value: Номер сертификата либо фрагмент имени файла.

    Returns:
        Строка только из букв и цифр в верхнем регистре.
    """
    return "".join(character for character in value.upper() if character.isalnum())


class CertificateFileIndex:
    """Кэшированный индекс PDF-файлов папки для повторного поиска по номеру.

    Строится один раз (один обход папки) и затем используется для поиска
    множества номеров подряд — важно при копировании сертификатов для
    десятков позиций одного заказа, где линейный поиск по диску на каждую
    позицию был бы избыточно медленным.
    """

    def __init__(self, directory: Path | None, *, recursive: bool = True) -> None:
        """Строит индекс PDF-файлов заданной папки.

        Args:
            directory: Папка с PDF-файлами сертификатов; ``None`` или
                несуществующий путь — индекс останется пустым.
            recursive: Обходить ли вложенные папки.
        """
        self._entries: list[tuple[str, Path]] = []
        if directory is None or not directory.is_dir():
            return
        pattern = "**/*" if recursive else "*"
        for path in directory.glob(pattern):
            try:
                if path.is_file() and path.suffix.lower() in PDF_EXTENSIONS:
                    self._entries.append((normalize_number(path.stem), path))
            except OSError:  # pragma: no cover — недоступный сетевой путь
                continue

    def __len__(self) -> int:
        """Количество проиндексированных PDF-файлов."""
        return len(self._entries)

    def find(self, certificate_number: str) -> Path | None:
        """Находит PDF-файл, имя которого содержит номер сертификата.

        Args:
            certificate_number: Номер сертификата из базы.

        Returns:
            Путь к файлу либо ``None``, если совпадение не найдено.
        """
        key = normalize_number(certificate_number)
        if not key:
            return None
        for stem_key, path in self._entries:
            if key in stem_key:
                return path
        return None


def find_pdf(
    directory: Path | None, certificate_number: str, *, recursive: bool = True
) -> Path | None:
    """Ищет один PDF-файл по номеру сертификата без построения долгоживущего индекса.

    Удобно для одиночных запросов интерфейса (просмотр одного сертификата);
    при поиске множества номеров подряд эффективнее построить
    :class:`CertificateFileIndex` один раз и переиспользовать его.

    Args:
        directory: Папка с PDF-файлами сертификатов.
        certificate_number: Номер сертификата.
        recursive: Обходить ли вложенные папки.

    Returns:
        Путь к найденному файлу либо ``None``.
    """
    return CertificateFileIndex(directory, recursive=recursive).find(certificate_number)
