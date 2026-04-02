from __future__ import annotations

from pathlib import Path

import pytest

from app.modules.pdf.validators import PdfFontsValidationError, ensure_embedded_fonts


class _Proc:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_ensure_embedded_fonts_ok(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pdf = tmp_path / "out.pdf"
    pdf.write_bytes(b"%PDF")
    monkeypatch.setattr(
        "subprocess.run",
        lambda *_a, **_k: _Proc(0, "name type emb sub uni object ID\nNotoSans CID yes yes yes 7 0"),
    )
    ensure_embedded_fonts(pdf)


def test_ensure_embedded_fonts_fail(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pdf = tmp_path / "out.pdf"
    pdf.write_bytes(b"%PDF")
    monkeypatch.setattr(
        "subprocess.run",
        lambda *_a, **_k: _Proc(0, "name type emb sub uni object ID\nNotoSans CID no yes yes 7 0"),
    )
    with pytest.raises(PdfFontsValidationError) as exc:
        ensure_embedded_fonts(pdf)
    assert exc.value.code == "PDF_FONTS_NOT_EMBEDDED"
