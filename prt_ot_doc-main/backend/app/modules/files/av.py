from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class AVResult:
    status: str
    signature: str | None = None


def scan_file(path: Path) -> AVResult:
    name = path.name.lower()
    if "eicar" in name or "virus" in name:
        return AVResult(status="infected", signature="simulated.eicar")
    return AVResult(status="clean")
