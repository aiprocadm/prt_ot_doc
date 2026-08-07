"""SEC-64 (разд. 64.2): безопасное вскрытие загруженных офисных архивов.

DOCX/XLSX/PPTX — это ZIP с XML внутри, и загружает их кто угодно. XXE закрыт
отдельно (``core/xml_security.py``), но сам архив остаётся поверхностью атаки:

* **zip-бомба** — несколько килобайт распаковываются в гигабайты и кладут воркер
  по памяти. ТЗ: «лимит на распакованный размер и число файлов внутри».
* **path traversal** — запись с именем ``../../etc/cron.d/x`` при распаковке
  пишет мимо целевого каталога. ТЗ: «валидация путей при распаковке».
* **макросы** — до этого модуля они отсекались ТОЛЬКО по расширению файла
  (``.docm``/``.xlsm``), то есть переименование в ``.docx`` полностью обходило
  проверку. Настоящий признак — наличие ``vbaProject.bin`` внутри архива.

Модуль намеренно не распаковывает ничего на диск: все проверки делаются по
оглавлению ZIP (``infolist``), поэтому стоят миллисекунды и выполняются ДО того,
как содержимое куда-то попадёт.

Пороги — в настройках, чтобы арендатор с тяжёлыми документами мог их поднять, не
патча код:

* ``ARCHIVE_MAX_ENTRIES``            — число файлов внутри архива;
* ``ARCHIVE_MAX_UNCOMPRESSED_BYTES`` — суммарный распакованный размер;
* ``ARCHIVE_MAX_ENTRY_BYTES``        — распакованный размер одной записи;
* ``ARCHIVE_MAX_COMPRESSION_RATIO``  — отношение распакованного к сжатому.

Порог отношения намеренно высокий: XML сжимается в десятки раз и на легитимных
документах, поэтому основным рубежом служат абсолютные лимиты, а отношение — лишь
дополнительный сигнал для явно аномальных файлов.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from io import BytesIO

__all__ = [
    "ArchiveSafetyError",
    "ArchiveLimits",
    "assert_safe_office_archive",
    "MACRO_MARKERS",
]

# Признаки макросов в OOXML. ``vbaProject.bin`` — сам VBA-проект; ``vbaData.xml``
# сопровождает его в Word. Проверяем по СОДЕРЖИМОМУ архива, а не по расширению.
MACRO_MARKERS: tuple[str, ...] = ("vbaproject.bin", "vbadata.xml")


class ArchiveSafetyError(ValueError):
    """Архив отвергнут: бомба, traversal, макросы или битая структура."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ArchiveLimits:
    max_entries: int = 2_000
    max_uncompressed_bytes: int = 200 * 1024 * 1024
    max_entry_bytes: int = 100 * 1024 * 1024
    max_compression_ratio: float = 500.0

    @classmethod
    def from_settings(cls, settings=None) -> "ArchiveLimits":
        if settings is None:
            from app.core.config import get_settings

            settings = get_settings()
        return cls(
            max_entries=int(getattr(settings, "archive_max_entries", cls.max_entries)),
            max_uncompressed_bytes=int(
                getattr(settings, "archive_max_uncompressed_bytes", cls.max_uncompressed_bytes)
            ),
            max_entry_bytes=int(getattr(settings, "archive_max_entry_bytes", cls.max_entry_bytes)),
            max_compression_ratio=float(
                getattr(settings, "archive_max_compression_ratio", cls.max_compression_ratio)
            ),
        )


def _is_traversal(name: str) -> bool:
    """Имя записи, которое при распаковке ушло бы за пределы целевого каталога."""

    normalized = name.replace("\\", "/")
    if normalized.startswith("/"):
        return True
    # Диск в Windows-стиле: ``C:/...``
    if len(normalized) > 1 and normalized[1] == ":":
        return True
    return any(part == ".." for part in normalized.split("/"))


def assert_safe_office_archive(
    data: bytes,
    *,
    limits: ArchiveLimits | None = None,
    allow_macros: bool = False,
) -> None:
    """Проверить загруженный ZIP/OOXML. Бросает :class:`ArchiveSafetyError`.

    Не-ZIP данные пропускаются молча: PDF, картинки и текст проходят своим путём,
    а этот гард отвечает только за архивы.
    """

    if not data[:2] == b"PK":
        return

    limits = limits or ArchiveLimits.from_settings()

    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ArchiveSafetyError("archive_corrupted", "Archive is not a readable ZIP") from exc

    with archive:
        entries = archive.infolist()
        if len(entries) > limits.max_entries:
            raise ArchiveSafetyError(
                "archive_too_many_entries",
                f"Archive has {len(entries)} entries, limit is {limits.max_entries}",
            )

        total_uncompressed = 0
        total_compressed = 0
        for entry in entries:
            if _is_traversal(entry.filename):
                raise ArchiveSafetyError(
                    "archive_path_traversal",
                    f"Archive entry escapes the extraction directory: {entry.filename!r}",
                )
            if not allow_macros and entry.filename.rsplit("/", 1)[-1].lower() in MACRO_MARKERS:
                raise ArchiveSafetyError(
                    "archive_macro_enabled",
                    "Macro-enabled documents are forbidden "
                    f"(found {entry.filename!r} inside the archive)",
                )
            if entry.file_size > limits.max_entry_bytes:
                raise ArchiveSafetyError(
                    "archive_entry_too_large",
                    f"Archive entry {entry.filename!r} unpacks to {entry.file_size} bytes, "
                    f"limit is {limits.max_entry_bytes}",
                )
            total_uncompressed += entry.file_size
            total_compressed += entry.compress_size
            if total_uncompressed > limits.max_uncompressed_bytes:
                raise ArchiveSafetyError(
                    "archive_too_large_uncompressed",
                    f"Archive unpacks to more than {limits.max_uncompressed_bytes} bytes",
                )

        # Отношение считаем по архиву целиком: на одной маленькой записи оно
        # шумит (заголовок ZIP сопоставим с данными), а бомбу видно в сумме.
        if total_compressed > 0:
            ratio = total_uncompressed / total_compressed
            if ratio > limits.max_compression_ratio:
                raise ArchiveSafetyError(
                    "archive_compression_ratio",
                    f"Archive compression ratio {ratio:.0f}:1 exceeds "
                    f"{limits.max_compression_ratio:.0f}:1",
                )
