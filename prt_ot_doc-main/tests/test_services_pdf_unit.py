from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.pdf import PdfConversionError, PdfConverter


@dataclass
class FakeSettings:
    libreoffice_bin: str = "soffice"
    pdf_fallback: str = "auto"
    pdf_libreoffice_timeout_seconds: float = 1.0
    pdf_libreoffice_max_attempts: int = 2
    pdf_libreoffice_retry_backoff_seconds: float = 0.0
    pdf_libreoffice_retry_backoff_max_seconds: float = 0.0
    enable_metrics: bool = False


def _make_converter(**overrides: object) -> PdfConverter:
    settings = FakeSettings(**overrides)
    return PdfConverter(settings=settings)


def test_convert_forces_fallback_when_configured(tmp_path: Path) -> None:
    converter = _make_converter(pdf_fallback="always")
    input_path = tmp_path / "file.docx"
    input_path.write_bytes(b"doc")
    result = converter.convert(input_path, tmp_path)
    assert result.fallback_used is True
    assert result.error_code == "pdf_fallback_forced"
    assert result.path.exists()


def test_convert_raises_when_binary_missing_and_no_fallback(tmp_path: Path) -> None:
    converter = _make_converter(pdf_fallback="never", libreoffice_bin="")
    input_path = tmp_path / "file.docx"
    input_path.write_bytes(b"doc")
    with pytest.raises(RuntimeError):
        converter.convert(input_path, tmp_path)


def test_convert_uses_fallback_when_binary_unavailable(tmp_path: Path) -> None:
    converter = _make_converter(libreoffice_bin="")
    input_path = tmp_path / "data.docx"
    input_path.write_bytes(b"doc")
    result = converter.convert(input_path, tmp_path)
    assert result.fallback_used is True
    assert result.error_code == "pdf_converter_not_found"


def test_convert_success_creates_pdf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    converter = _make_converter()
    input_path = tmp_path / "source.docx"
    input_path.write_bytes(b"doc")

    monkeypatch.setattr(converter, "_bin_available", lambda: True)

    def fake_run(input_path: Path, output_dir: Path) -> float:
        output_file = output_dir / f"{input_path.stem}.pdf"
        output_file.write_bytes(b"%PDF")
        return 0.1

    monkeypatch.setattr(converter, "_run_with_retries", fake_run)

    result = converter.convert(input_path, tmp_path)
    assert result.fallback_used is False
    assert result.error_code is None
    assert result.path.read_bytes().startswith(b"%PDF")


def test_convert_falls_back_on_conversion_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    converter = _make_converter()
    input_path = tmp_path / "sample.docx"
    input_path.write_bytes(b"doc")

    monkeypatch.setattr(converter, "_bin_available", lambda: True)

    def failing_run(*_: object) -> float:
        raise PdfConversionError("pdf_format_error")

    monkeypatch.setattr(converter, "_run_with_retries", failing_run)

    result = converter.convert(input_path, tmp_path)
    assert result.fallback_used is True
    assert result.error_code == "pdf_format_error"


def test_convert_missing_output_falls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    converter = _make_converter()
    input_path = tmp_path / "ghost.docx"
    input_path.write_bytes(b"doc")

    monkeypatch.setattr(converter, "_bin_available", lambda: True)
    monkeypatch.setattr(converter, "_run_with_retries", lambda *_: 0.1)

    result = converter.convert(input_path, tmp_path)
    assert result.fallback_used is True
    assert result.error_code == "pdf_conversion_missing_output"


def test_convert_missing_output_raises_when_fallback_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    converter = _make_converter(pdf_fallback="never")
    input_path = tmp_path / "ghost.docx"
    input_path.write_bytes(b"doc")

    monkeypatch.setattr(converter, "_bin_available", lambda: True)
    monkeypatch.setattr(converter, "_run_with_retries", lambda *_: 0.1)

    with pytest.raises(RuntimeError, match="pdf_conversion_missing_output"):
        converter.convert(input_path, tmp_path)


@pytest.mark.anyio()
async def test_run_with_retries_retries_and_succeeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    converter = _make_converter(pdf_libreoffice_max_attempts=3)
    input_path = tmp_path / "doc.docx"
    output_dir = tmp_path / "out"
    call_counter = SimpleNamespace(count=0)

    def fake_invoke(path: Path, out_dir: Path) -> float:
        call_counter.count += 1
        if call_counter.count == 1:
            raise PdfConversionError("pdf_conversion_timeout")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{path.stem}.pdf").write_bytes(b"%PDF")
        return 0.2

    monkeypatch.setattr(converter, "_invoke_libreoffice", fake_invoke)
    monkeypatch.setattr("app.services.pdf.sleep", lambda _: None)

    duration = converter._run_with_retries(input_path, output_dir)
    assert duration == 0.2
    assert call_counter.count == 2


def test_run_with_retries_raises_last_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    converter = _make_converter(pdf_libreoffice_max_attempts=2)
    input_path = tmp_path / "doc.docx"
    output_dir = tmp_path / "out"

    def always_fail(*_: object) -> float:
        raise PdfConversionError("pdf_conversion_timeout")

    monkeypatch.setattr(converter, "_invoke_libreoffice", always_fail)
    monkeypatch.setattr("app.services.pdf.sleep", lambda *_: None)

    with pytest.raises(PdfConversionError):
        converter._run_with_retries(input_path, output_dir)


@pytest.mark.parametrize(
    "exc_factory",
    [
        lambda: FileNotFoundError("missing"),
        lambda: subprocess.TimeoutExpired(cmd=["soffice"], timeout=1),
        lambda: subprocess.CalledProcessError(returncode=1, cmd=["soffice"], stderr=b"boom"),
    ],
)
def test_invoke_libreoffice_error_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exc_factory
) -> None:
    converter = _make_converter()
    input_path = tmp_path / "input.docx"
    input_path.write_bytes(b"doc")

    def fake_run(*_: object, **__: object) -> None:
        raise exc_factory()

    monkeypatch.setattr("app.services.pdf.subprocess.run", fake_run)

    with pytest.raises(PdfConversionError):
        converter._invoke_libreoffice(input_path, tmp_path)


def test_record_attempt_with_metrics() -> None:
    converter = _make_converter()

    class DummyMetrics:
        def __init__(self) -> None:
            self.samples: list[tuple[float, str]] = []

        def observe_pdf_libreoffice(self, *, seconds: float, status: str) -> None:
            self.samples.append((seconds, status))

    converter._metrics = DummyMetrics()
    converter._record_attempt(-5.0, "failed")
    assert converter._metrics.samples == [(0.0, "failed")]


def test_compute_backoff_caps_value() -> None:
    converter = _make_converter(
        pdf_libreoffice_retry_backoff_seconds=1.0,
        pdf_libreoffice_retry_backoff_max_seconds=2.0,
    )
    assert converter._compute_backoff(1) == 1.0
    assert converter._compute_backoff(5) == 2.0
