from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.modules.pdf.service_pool import LibreOfficePool


def test_pool_runs_soffice(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    called: dict[str, object] = {}

    def _run(cmd, timeout, check, capture_output):  # type: ignore[no-untyped-def]
        called["cmd"] = cmd
        called["timeout"] = timeout
        return None

    monkeypatch.setattr(subprocess, "run", _run)
    source = tmp_path / "source.docx"
    source.write_bytes(b"docx")
    out = LibreOfficePool(workers=1, soffice_bin="soffice").convert(source=source, output_dir=tmp_path, timeout_s=45)
    assert out.name == "source.pdf"
    assert called["timeout"] == 45


def test_pool_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def _run(*_a, **_k):  # type: ignore[no-untyped-def]
        raise subprocess.TimeoutExpired(cmd=["soffice"], timeout=1)

    monkeypatch.setattr(subprocess, "run", _run)
    source = tmp_path / "source.docx"
    source.write_bytes(b"docx")
    with pytest.raises(subprocess.TimeoutExpired):
        LibreOfficePool(workers=1).convert(source=source, output_dir=tmp_path, timeout_s=1)
