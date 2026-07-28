"""SEC-64 (разд. 64.2): безопасное вскрытие загруженных офисных архивов.

Три угрозы, которые ТЗ называет прямо, и одна подмена, которую нашла сверка:

* zip-бомба — несколько килобайт распаковываются в гигабайты;
* path traversal в именах записей — распаковка пишет мимо целевого каталога;
* макросы — до этого модуля отсекались ТОЛЬКО по расширению файла, то есть
  переименование ``.docm`` → ``.docx`` полностью обходило проверку;
* легитимный DOCX обязан проходить: гард, отвергающий нормальные документы,
  будет отключён при первой же жалобе и защитит ноль.
"""

from __future__ import annotations

import zipfile
from io import BytesIO

import pytest

from app.core.archive_safety import (
    ArchiveLimits,
    ArchiveSafetyError,
    assert_safe_office_archive,
)

_LIMITS = ArchiveLimits(
    max_entries=10,
    max_uncompressed_bytes=1_000_000,
    max_entry_bytes=500_000,
    max_compression_ratio=100.0,
)


def _zip(entries: dict[str, bytes], *, compression: int = zipfile.ZIP_DEFLATED) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=compression) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def _minimal_docx() -> bytes:
    return _zip(
        {
            "[Content_Types].xml": b"<?xml version='1.0'?><Types/>",
            "word/document.xml": b"<?xml version='1.0'?><document><body/></document>",
        }
    )


def test_legitimate_docx_passes() -> None:
    assert_safe_office_archive(_minimal_docx(), limits=_LIMITS)


def test_non_zip_payload_is_ignored() -> None:
    """PDF/картинки идут своим путём — этот гард отвечает только за архивы."""

    assert_safe_office_archive(b"%PDF-1.7 not a zip at all", limits=_LIMITS)
    assert_safe_office_archive(b"", limits=_LIMITS)


def test_zip_bomb_is_rejected_by_absolute_limit() -> None:
    """Настоящая бомба: килобайты на входе, мегабайты на выходе."""

    bomb = _zip({"payload.bin": b"\0" * 5_000_000})
    assert len(bomb) < 50_000, "тест бессмыслен, если архив не сжался"

    with pytest.raises(ArchiveSafetyError) as excinfo:
        assert_safe_office_archive(bomb, limits=_LIMITS)
    assert excinfo.value.code in {"archive_entry_too_large", "archive_too_large_uncompressed"}


def test_compression_ratio_is_a_secondary_signal() -> None:
    limits = ArchiveLimits(
        max_entries=10,
        max_uncompressed_bytes=100_000_000,
        max_entry_bytes=100_000_000,
        max_compression_ratio=50.0,
    )
    with pytest.raises(ArchiveSafetyError) as excinfo:
        assert_safe_office_archive(_zip({"a.bin": b"\0" * 2_000_000}), limits=limits)
    assert excinfo.value.code == "archive_compression_ratio"


def test_too_many_entries_is_rejected() -> None:
    many = _zip({f"f{i}.txt": b"x" for i in range(11)})
    with pytest.raises(ArchiveSafetyError) as excinfo:
        assert_safe_office_archive(many, limits=_LIMITS)
    assert excinfo.value.code == "archive_too_many_entries"


@pytest.mark.parametrize(
    "name",
    [
        "../../etc/cron.d/pwn",
        "/absolute/path",
        "word/../../../escape.xml",
        "..\\..\\windows\\system32\\evil.dll",
        "C:/windows/evil.dll",
    ],
)
def test_path_traversal_entries_are_rejected(name: str) -> None:
    with pytest.raises(ArchiveSafetyError) as excinfo:
        assert_safe_office_archive(_zip({name: b"payload"}), limits=_LIMITS)
    assert excinfo.value.code == "archive_path_traversal"


def test_macro_is_detected_by_content_not_extension() -> None:
    """Ключевой пробел: раньше хватало переименовать .docm в .docx."""

    renamed_macro_doc = _zip(
        {
            "[Content_Types].xml": b"<Types/>",
            "word/document.xml": b"<document/>",
            "word/vbaProject.bin": b"\x00macro payload",
        }
    )
    with pytest.raises(ArchiveSafetyError) as excinfo:
        assert_safe_office_archive(renamed_macro_doc, limits=_LIMITS)
    assert excinfo.value.code == "archive_macro_enabled"


def test_macro_marker_matching_is_case_insensitive() -> None:
    with pytest.raises(ArchiveSafetyError):
        assert_safe_office_archive(_zip({"word/VBAProject.BIN": b"x"}), limits=_LIMITS)


def test_macros_can_be_allowed_explicitly() -> None:
    """Внутренние пайплайны, которые сами собирают DOCX, не должны спотыкаться."""

    assert_safe_office_archive(
        _zip({"word/vbaProject.bin": b"x"}), limits=_LIMITS, allow_macros=True
    )


def test_corrupted_zip_is_rejected_not_crashing() -> None:
    with pytest.raises(ArchiveSafetyError) as excinfo:
        assert_safe_office_archive(b"PK\x03\x04 broken tail", limits=_LIMITS)
    assert excinfo.value.code == "archive_corrupted"


def test_limits_come_from_settings() -> None:
    from types import SimpleNamespace

    limits = ArchiveLimits.from_settings(
        SimpleNamespace(
            archive_max_entries=7,
            archive_max_uncompressed_bytes=123,
            archive_max_entry_bytes=45,
            archive_max_compression_ratio=6.5,
        )
    )
    assert (limits.max_entries, limits.max_uncompressed_bytes) == (7, 123)
    assert (limits.max_entry_bytes, limits.max_compression_ratio) == (45, 6.5)
