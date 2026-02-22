from __future__ import annotations

import subprocess
from pathlib import Path


class PdfFontsValidationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def ensure_embedded_fonts(pdf_path: Path) -> None:
    proc = subprocess.run(["pdffonts", str(pdf_path)], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise PdfFontsValidationError("PDF_FONTS_CHECK_FAILED", proc.stderr.strip() or "pdffonts_failed")

    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    data_lines = [line for line in lines if not line.startswith("name") and not line.startswith("-")]
    for line in data_lines:
        chunks = [c for c in line.split(" ") if c]
        if len(chunks) < 4:
            continue
        emb = chunks[2].lower()
        if emb not in {"yes", "y"}:
            raise PdfFontsValidationError("PDF_FONTS_NOT_EMBEDDED", line)
