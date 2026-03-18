from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ReplacePatch:
    patch_id: str
    created_at: datetime
    before: dict[str, Any]
    after: dict[str, Any]
    replacements: dict[str, str]
    changed_keys: list[str] = field(default_factory=list)


class ReplaceEngine:
    """Simple persisted replace engine for structured contexts used by package/document flows."""

    def __init__(self) -> None:
        self._patches: dict[str, ReplacePatch] = {}

    def dry_run(self, context: dict[str, Any], replacements: dict[str, str]) -> ReplacePatch:
        before = copy.deepcopy(context)
        after = self.apply(context, replacements)
        changed_keys = sorted(key for key in replacements if before.get(key) != after.get(key))
        patch_id = hashlib.sha256(
            json.dumps({"before": before, "after": after, "replacements": replacements}, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        patch = ReplacePatch(
            patch_id=patch_id,
            created_at=datetime.now(tz=timezone.utc),
            before=before,
            after=copy.deepcopy(after),
            replacements=dict(replacements),
            changed_keys=changed_keys,
        )
        self._patches[patch_id] = patch
        return patch

    def apply(self, context: dict[str, Any], replacements: dict[str, str]) -> dict[str, Any]:
        updated = copy.deepcopy(context)
        for key, value in replacements.items():
            if key in updated:
                updated[key] = value
        return updated

    def rollback(self, patch_id: str) -> dict[str, Any]:
        patch = self._patches[patch_id]
        return copy.deepcopy(patch.before)

    def get_patch(self, patch_id: str) -> ReplacePatch | None:
        patch = self._patches.get(patch_id)
        if patch is None:
            return None
        return ReplacePatch(
            patch_id=patch.patch_id,
            created_at=patch.created_at,
            before=copy.deepcopy(patch.before),
            after=copy.deepcopy(patch.after),
            replacements=dict(patch.replacements),
            changed_keys=list(patch.changed_keys),
        )
