from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from threading import BoundedSemaphore


class LibreOfficePool:
    def __init__(self, *, workers: int = 4, soffice_bin: str = "soffice") -> None:
        self._sem = BoundedSemaphore(max(1, workers))
        self._soffice_bin = self._resolve_soffice_bin(soffice_bin)

    def convert(self, *, source: Path, output_dir: Path, timeout_s: int) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        with self._sem:
            profile_dir = Path(tempfile.mkdtemp(prefix="lo-profile-"))
            try:
                cmd = [
                    self._soffice_bin,
                    "--headless",
                    f"-env:UserInstallation=file://{profile_dir}",
                    "--convert-to",
                    "pdf",
                    str(source),
                    "--outdir",
                    str(output_dir),
                ]
                subprocess.run(cmd, timeout=timeout_s, check=True, capture_output=True)
            finally:
                shutil.rmtree(profile_dir, ignore_errors=True)
        return output_dir / f"{source.stem}.pdf"

    @staticmethod
    def _resolve_soffice_bin(candidate: str) -> str:
        normalized = str(candidate).strip()
        if not normalized:
            return normalized
        looks_like_python = Path(normalized).name.lower().startswith("python")
        if not looks_like_python and LibreOfficePool._binary_exists(normalized):
            return normalized
        for fallback in ("soffice", "libreoffice"):
            if LibreOfficePool._binary_exists(fallback):
                return fallback
        return "soffice" if looks_like_python else normalized

    @staticmethod
    def _binary_exists(candidate: str) -> bool:
        if not candidate:
            return False
        if any(sep in candidate for sep in ("/", "\\")):
            return Path(candidate).exists()
        return shutil.which(candidate) is not None
