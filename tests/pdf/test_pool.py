from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.modules.pdf import service_pool
from app.modules.pdf.service_pool import LibreOfficePool


def test_pool_runs_soffice_in_sandbox(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """SEC-64.2: конвертация идёт ТОЛЬКО через песочницу с лимитами из настроек."""

    called: dict[str, object] = {}

    def _run(cmd, *, timeout_s, max_memory_mb, max_cpu_s, max_output_mb):  # type: ignore[no-untyped-def]
        called["cmd"] = cmd
        called["timeout_s"] = timeout_s
        called["limits"] = (max_memory_mb, max_cpu_s, max_output_mb)
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(service_pool, "run_sandboxed", _run)
    source = tmp_path / "source.docx"
    source.write_bytes(b"docx")
    out = LibreOfficePool(workers=1, soffice_bin="soffice").convert(
        source=source, output_dir=tmp_path, timeout_s=45
    )
    assert out.name == "source.pdf"
    assert called["timeout_s"] == 45
    cmd = called["cmd"]
    assert "--headless" in cmd and "--convert-to" in cmd
    mem, cpu, out_mb = called["limits"]
    assert mem > 0 and cpu > 0 and out_mb > 0


def test_pool_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def _run(*_a, **_k):  # type: ignore[no-untyped-def]
        raise subprocess.TimeoutExpired(cmd=["soffice"], timeout=1)

    monkeypatch.setattr(service_pool, "run_sandboxed", _run)
    source = tmp_path / "source.docx"
    source.write_bytes(b"docx")
    with pytest.raises(subprocess.TimeoutExpired):
        LibreOfficePool(workers=1).convert(source=source, output_dir=tmp_path, timeout_s=1)
