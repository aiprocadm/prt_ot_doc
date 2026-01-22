from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.models.models import DocumentPack


@dataclass
class PackAssembler:
    template_id: str

    def assemble(self, packs: Iterable[DocumentPack]) -> list[dict[str, str]]:
        return [{"name": pack.name, "description": pack.description or ""} for pack in packs]
