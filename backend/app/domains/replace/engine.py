from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class ReplacePatch:
    patch_id: str
    created_at: datetime
    before: dict[str, Any]
    after: dict[str, Any]
    replacements: dict[str, str]
    changed_keys: list[str] = field(default_factory=list)
    mode: str = "dry_run"
    status: str = "pending"
    rolled_back_at: datetime | None = None
    audit: dict[str, Any] = field(default_factory=dict)
    diff: list[dict[str, Any]] = field(default_factory=list)


class ReplaceEngine:
    """Persisted replace engine for structured contexts used by package/document flows."""

    def __init__(self, storage_path: str | None = None) -> None:
        self._storage_path = Path(storage_path) if storage_path else None
        self._patches: dict[str, ReplacePatch] = {}
        self._load()

    def _load(self) -> None:
        if not self._storage_path or not self._storage_path.exists():
            return
        payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        for item in payload:
            item["created_at"] = datetime.fromisoformat(item["created_at"])
            if item.get("rolled_back_at"):
                item["rolled_back_at"] = datetime.fromisoformat(item["rolled_back_at"])
            self._patches[item["patch_id"]] = ReplacePatch(**item)

    def _persist(self) -> None:
        if not self._storage_path:
            return
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = []
        for patch in self._patches.values():
            item = asdict(patch)
            item["created_at"] = patch.created_at.isoformat()
            if patch.rolled_back_at:
                item["rolled_back_at"] = patch.rolled_back_at.isoformat()
            payload.append(item)
        self._storage_path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, indent=2), encoding="utf-8")

    @staticmethod
    def _build_diff(before: dict[str, Any], after: dict[str, Any], replacements: dict[str, str]) -> list[dict[str, Any]]:
        diff: list[dict[str, Any]] = []
        for key, replacement in replacements.items():
            before_value = before.get(key)
            after_value = after.get(key)
            if before_value != after_value:
                diff.append({"key": key, "before": before_value, "after": after_value, "replacement": replacement})
        return diff

    def _make_patch(self, context: dict[str, Any], replacements: dict[str, str], *, mode: str) -> ReplacePatch:
        before = copy.deepcopy(context)
        after = self.apply(context, replacements)
        diff = self._build_diff(before, after, replacements)
        patch_id = hashlib.sha256(json.dumps({"before": before, "after": after, "replacements": replacements, "mode": mode}, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        existing = self._patches.get(patch_id)
        if existing is not None:
            return self.get_patch(patch_id) or existing
        patch = ReplacePatch(
            patch_id=patch_id,
            created_at=datetime.now(tz=timezone.utc),
            before=before,
            after=copy.deepcopy(after),
            replacements=dict(replacements),
            changed_keys=sorted(item["key"] for item in diff),
            mode=mode,
            status="applied" if mode == "apply" else "planned",
            audit={"replacements_count": len(replacements), "changed_keys": sorted(item["key"] for item in diff)},
            diff=diff,
        )
        self._patches[patch_id] = patch
        self._persist()
        return patch

    def dry_run(self, context: dict[str, Any], replacements: dict[str, str]) -> ReplacePatch:
        return self._make_patch(context, replacements, mode="dry_run")

    def apply(self, context: dict[str, Any], replacements: dict[str, str]) -> dict[str, Any]:
        updated = copy.deepcopy(context)
        for key, value in replacements.items():
            if key in updated:
                updated[key] = value
        return updated

    def commit(self, context: dict[str, Any], replacements: dict[str, str]) -> ReplacePatch:
        return self._make_patch(context, replacements, mode="apply")

    def rollback(self, patch_id: str) -> dict[str, Any]:
        patch = self._patches[patch_id]
        patch.status = "rolled_back"
        patch.rolled_back_at = datetime.now(tz=timezone.utc)
        self._persist()
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
            mode=patch.mode,
            status=patch.status,
            rolled_back_at=patch.rolled_back_at,
            audit=copy.deepcopy(patch.audit),
            diff=copy.deepcopy(patch.diff),
        )
