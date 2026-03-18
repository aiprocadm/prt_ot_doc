from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.models.models import DocumentPack


@dataclass
class PackAssembler:
    template_id: str

    def assemble(self, packs: Iterable[DocumentPack], *, preset_code: str | None = None, context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        shared_context = dict(context or {})
        assembled: list[dict[str, Any]] = []
        for index, pack in enumerate(packs, start=1):
            assembled.append(
                {
                    "name": pack.name,
                    "description": pack.description or "",
                    "template_id": self.template_id,
                    "preset_code": preset_code,
                    "sequence": index,
                    "context": dict(shared_context),
                }
            )
        return assembled
