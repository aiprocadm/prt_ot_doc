from __future__ import annotations

import logging
import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter, sleep
from typing import Final

from app.core.config import Settings, get_settings
from app.core.metrics import Metrics, get_metrics

logger = logging.getLogger(__name__)

MINI_PDF_BYTES: Final[bytes] = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]/Contents 4 0 R>>endobj\n"
    b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 72 128 Td (Generated) Tj ET\nendstream\nendobj\n"
    b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica/Name/F1>>endobj\n"
    b"xref\n0 6\n0000000000 65535 f \n"
    b"0000000010 00000 n \n0000000060 00000 n \n0000000112 00000 n \n"
    b"0000000200 00000 n \n0000000330 00000 n \n"
    b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n420\n%%EOF"
)


@dataclass(frozen=True)
class PdfConversionResult:
    """Result of converting a DOCX document to PDF."""

    path: Path
    fallback_used: bool
    error_code: str | None


class PdfConversionError(RuntimeError):
    """Raised when LibreOffice conversion fails with a well-defined error code."""

    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code


class PdfConverter:
    """Convert DOCX documents to PDF by invoking a headless LibreOffice process."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self.bin = self._settings.libreoffice_bin
        self._resolved_bin = self._resolve_bin(self.bin)
        self._fallback_mode = self._settings.pdf_fallback
        self._timeout = self._settings.pdf_libreoffice_timeout_seconds
        self._max_attempts = max(1, self._settings.pdf_libreoffice_max_attempts)
        self._backoff = float(self._settings.pdf_libreoffice_retry_backoff_seconds)
        self._backoff_max = float(self._settings.pdf_libreoffice_retry_backoff_max_seconds)
        self._retryable_errors: Final[frozenset[str]] = frozenset(
            {"pdf_conversion_timeout", "pdf_conversion_failed"}
        )
        self._metrics: Metrics | None = get_metrics() if self._settings.enable_metrics else None

    def convert(self, input_path: Path, output_dir: Path) -> PdfConversionResult:
        """Convert ``input_path`` into a PDF stored inside ``output_dir``.

        Returns a :class:`PdfConversionResult` describing the outcome. When LibreOffice
        conversion fails (or fallback mode forces it) a minimal PDF is generated instead
        of raising, unless the fallback mode is explicitly set to ``"never"``.
        """

        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{input_path.stem}.pdf"

        if self._fallback_mode == "always":
            logger.info("Forcing mini PDF fallback mode")
            return self._build_fallback(
                output_path=output_path,
                error_code="pdf_fallback_forced",
            )

        if not self._bin_available():
            if self._fallback_mode == "never":
                raise RuntimeError("pdf_converter_not_found")
            logger.warning(
                "LibreOffice binary not available, using fallback",
                extra={"bin": str(self.bin)},
            )
            return self._build_fallback(
                output_path=output_path,
                error_code="pdf_converter_not_found",
            )

        try:
            duration = self._run_with_retries(input_path, output_dir)
        except PdfConversionError as exc:
            error_code = exc.code or "pdf_conversion_failed"
            if exc.code in self._retryable_errors:
                logger.exception(
                    "LibreOffice PDF conversion failed with retryable error",
                    extra={"error_code": error_code},
                )
                raise
            if self._fallback_mode == "never":
                raise
            logger.exception("LibreOffice PDF conversion failed")
            logger.warning(
                "Falling back to mini PDF after LibreOffice error",
                extra={"error_code": error_code},
            )
            return self._build_fallback(
                output_path=output_path,
                error_code=error_code,
            )

        if not output_path.exists():
            logger.error(
                "LibreOffice completed but no PDF was produced", extra={"output": str(output_path)}
            )
            self._record_attempt(duration, "missing_output")
            if self._fallback_mode == "never":
                raise RuntimeError("pdf_conversion_missing_output")
            return self._build_fallback(
                output_path=output_path,
                error_code="pdf_conversion_missing_output",
            )

        self._record_attempt(duration, "success")
        return PdfConversionResult(path=output_path, fallback_used=False, error_code=None)

    def _run_with_retries(self, input_path: Path, output_dir: Path) -> float:
        attempts = self._max_attempts
        last_error: PdfConversionError | None = None
        for attempt in range(1, attempts + 1):
            try:
                return self._invoke_libreoffice(input_path, output_dir)
            except PdfConversionError as exc:
                last_error = exc
                if not self._should_retry(exc.code, attempt):
                    raise
                delay = self._compute_backoff(attempt)
                logger.warning(
                    "Retrying LibreOffice conversion",
                    extra={
                        "attempt": attempt,
                        "max_attempts": attempts,
                        "error_code": exc.code,
                        "sleep_seconds": delay,
                    },
                )
                sleep(delay)
        if last_error is not None:
            raise last_error
        raise PdfConversionError("pdf_conversion_failed")

    def _invoke_libreoffice(self, input_path: Path, output_dir: Path) -> float:
        profile_dir = Path(tempfile.mkdtemp(prefix="lo-profile-"))
        cmd: list[str] = [
            str(self._resolved_bin),
            "--headless",
            f"-env:UserInstallation=file://{profile_dir.as_posix()}",
            "--convert-to",
            "pdf",
            str(input_path),
            "--outdir",
            str(output_dir),
        ]
        started = perf_counter()
        try:
            subprocess.run(
                cmd,
                check=True,
                timeout=self._timeout,
                capture_output=True,
                shell=False,
            )
        except FileNotFoundError as exc:
            duration = perf_counter() - started
            logger.exception("LibreOffice binary not found", extra={"bin": self._resolved_bin})
            self._record_attempt(duration, "pdf_converter_not_found")
            raise PdfConversionError("pdf_converter_not_found") from exc
        except subprocess.TimeoutExpired as exc:
            duration = perf_counter() - started
            logger.exception("LibreOffice conversion timed out", extra={"timeout": exc.timeout})
            self._record_attempt(duration, "pdf_conversion_timeout")
            raise PdfConversionError("pdf_conversion_timeout") from exc
        except subprocess.CalledProcessError as exc:
            duration = perf_counter() - started
            stderr = exc.stderr.decode(errors="ignore") if exc.stderr else ""
            logger.error(
                "LibreOffice conversion failed",
                extra={"returncode": exc.returncode, "stderr": stderr[-400:]},
            )
            self._record_attempt(duration, "pdf_conversion_failed")
            raise PdfConversionError("pdf_conversion_failed") from exc
        finally:
            shutil.rmtree(profile_dir, ignore_errors=True)
        duration = perf_counter() - started
        return duration

    def _compute_backoff(self, attempt: int) -> float:
        raw_delay = self._backoff * math.pow(2.0, attempt - 1)
        return min(raw_delay, self._backoff_max)

    @staticmethod
    def _resolve_bin(configured_bin: str) -> str:
        candidate = str(configured_bin).strip()
        if not candidate:
            return ""
        looks_like_python = Path(candidate).name.lower().startswith("python")
        if not looks_like_python and PdfConverter._binary_exists(candidate):
            return candidate
        for fallback in ("soffice", "libreoffice"):
            if PdfConverter._binary_exists(fallback):
                logger.warning(
                    "Resolved LibreOffice binary override",
                    extra={"configured_bin": candidate, "resolved_bin": fallback},
                )
                return fallback
        return "soffice" if looks_like_python else candidate

    @staticmethod
    def _binary_exists(candidate: str) -> bool:
        if not candidate:
            return False
        if any(sep in candidate for sep in ("/", "\\")):
            return Path(candidate).exists()
        return shutil.which(candidate) is not None

    def _should_retry(self, error_code: str, attempt: int) -> bool:
        if attempt >= self._max_attempts:
            return False
        return error_code in self._retryable_errors

    def _record_attempt(self, duration: float, status: str) -> None:
        if self._metrics is None:
            return
        safe_duration = duration if duration >= 0 else 0.0
        self._metrics.observe_pdf_libreoffice(seconds=safe_duration, status=status)

    @staticmethod
    def _write_fallback(output_path: Path) -> None:
        output_path.write_bytes(MINI_PDF_BYTES)

    def _build_fallback(self, output_path: Path, error_code: str) -> PdfConversionResult:
        self._write_fallback(output_path)
        return PdfConversionResult(
            path=output_path,
            fallback_used=True,
            error_code=error_code,
        )

    def _bin_available(self) -> bool:
        return self._binary_exists(str(self._resolved_bin))
