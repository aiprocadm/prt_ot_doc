from __future__ import annotations

import hashlib
import json
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
            pack_context = {
                **shared_context,
                "pack": {"name": pack.name, "description": pack.description or "", "sequence": index, "preset_code": preset_code},
            }
            fingerprint = hashlib.sha256(
                json.dumps({"template_id": self.template_id, "preset_code": preset_code, "index": index, "name": pack.name}, ensure_ascii=False, sort_keys=True).encode('utf-8')
            ).hexdigest()
            warnings = [] if pack.description else ["pack description is empty"]
            assembled.append(
                {
                    "name": pack.name,
                    "description": pack.description or "",
                    "template_id": self.template_id,
                    "preset_code": preset_code,
                    "sequence": index,
                    "context": pack_context,
                    "warnings": warnings,
                    "metadata": {"fingerprint": fingerprint, "warnings_count": len(warnings)},
                    "idempotency_key": f"{preset_code or 'pack'}:{self.template_id}:{index}:{pack.name}:{fingerprint[:12]}",
                }
            )
        return assembled
