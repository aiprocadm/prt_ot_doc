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
    history: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


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
        self._storage_path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _iter_paths(value: Any, prefix: str = "") -> dict[str, Any]:
        result: dict[str, Any] = {}
        if isinstance(value, dict):
            for key, child in value.items():
                path = f"{prefix}.{key}" if prefix else str(key)
                result[path] = child
                result.update(ReplaceEngine._iter_paths(child, path))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                path = f"{prefix}[{index}]"
                result[path] = child
                result.update(ReplaceEngine._iter_paths(child, path))
        return result

    @staticmethod
    def _parse_path(path: str) -> list[str | int]:
        tokens: list[str | int] = []
        current = ""
        i = 0
        while i < len(path):
            char = path[i]
            if char == ".":
                if current:
                    tokens.append(current)
                    current = ""
                i += 1
                continue
            if char == "[":
                if current:
                    tokens.append(current)
                    current = ""
                end = path.index("]", i)
                tokens.append(int(path[i + 1 : end]))
                i = end + 1
                continue
            current += char
            i += 1
        if current:
            tokens.append(current)
        return tokens

    @classmethod
    def _get_value(cls, payload: dict[str, Any], path: str) -> Any:
        current: Any = payload
        for token in cls._parse_path(path):
            if isinstance(token, int):
                if not isinstance(current, list) or token >= len(current):
                    return None
                current = current[token]
            else:
                if not isinstance(current, dict) or token not in current:
                    return None
                current = current[token]
        return current

    @classmethod
    def _set_value(cls, payload: dict[str, Any], path: str, value: Any) -> bool:
        tokens = cls._parse_path(path)
        if not tokens:
            return False
        current: Any = payload
        for token in tokens[:-1]:
            if isinstance(token, int):
                if not isinstance(current, list) or token >= len(current):
                    return False
                current = current[token]
            else:
                if not isinstance(current, dict) or token not in current:
                    return False
                current = current[token]
        last = tokens[-1]
        if isinstance(last, int):
            if not isinstance(current, list) or last >= len(current):
                return False
            current[last] = value
            return True
        if not isinstance(current, dict) or last not in current:
            return False
        current[last] = value
        return True

    @classmethod
    def _build_diff(
        cls, before: dict[str, Any], after: dict[str, Any], replacements: dict[str, str]
    ) -> list[dict[str, Any]]:
        diff: list[dict[str, Any]] = []
        before_paths = cls._iter_paths(before)
        after_paths = cls._iter_paths(after)
        for key, replacement in replacements.items():
            before_value = cls._get_value(before, key)
            after_value = cls._get_value(after, key)
            if before_value is None and key in before_paths:
                before_value = before_paths[key]
            if after_value is None and key in after_paths:
                after_value = after_paths[key]
            if before_value != after_value:
                diff.append(
                    {
                        "key": key,
                        "before": before_value,
                        "after": after_value,
                        "replacement": replacement,
                    }
                )
        return diff

    @staticmethod
    def _fingerprint(payload: dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

    def _make_patch(
        self, context: dict[str, Any], replacements: dict[str, str], *, mode: str
    ) -> ReplacePatch:
        before = copy.deepcopy(context)
        after = self.apply(context, replacements)
        diff = self._build_diff(before, after, replacements)
        patch_id = self._fingerprint(
            {"before": before, "after": after, "replacements": replacements, "mode": mode}
        )
        existing = self._patches.get(patch_id)
        if existing is not None:
            return self.get_patch(patch_id) or existing
        created_at = datetime.now(tz=timezone.utc)
        summary = {
            "changed_count": len(diff),
            "replacements_count": len(replacements),
            "has_changes": bool(diff),
            "target_fingerprint_before": self._fingerprint(before),
            "target_fingerprint_after": self._fingerprint(after),
        }
        patch = ReplacePatch(
            patch_id=patch_id,
            created_at=created_at,
            before=before,
            after=copy.deepcopy(after),
            replacements=dict(replacements),
            changed_keys=sorted(item["key"] for item in diff),
            mode=mode,
            status="applied" if mode == "apply" else "planned",
            audit={
                "replacements_count": len(replacements),
                "changed_keys": sorted(item["key"] for item in diff),
                "changed_count": len(diff),
                "idempotency_fingerprint": patch_id,
                "before_fingerprint": summary["target_fingerprint_before"],
                "after_fingerprint": summary["target_fingerprint_after"],
            },
            diff=diff,
            history=[
                {
                    "at": created_at.isoformat(),
                    "action": mode,
                    "status": "applied" if mode == "apply" else "planned",
                }
            ],
            summary=summary,
        )
        self._patches[patch_id] = patch
        self._persist()
        return patch

    def dry_run(self, context: dict[str, Any], replacements: dict[str, str]) -> ReplacePatch:
        return self._make_patch(context, replacements, mode="dry_run")

    @classmethod
    def apply(cls, context: dict[str, Any], replacements: dict[str, str]) -> dict[str, Any]:
        updated = copy.deepcopy(context)
        for key, value in replacements.items():
            if not cls._set_value(updated, key, value) and key in updated:
                updated[key] = value
        return updated

    def commit(self, context: dict[str, Any], replacements: dict[str, str]) -> ReplacePatch:
        return self._make_patch(context, replacements, mode="apply")

    def rollback(self, patch_id: str) -> dict[str, Any]:
        patch = self._patches[patch_id]
        if patch.status == "rolled_back":
            if not any(item.get("action") == "rollback_noop" for item in patch.history):
                patch.history.append(
                    {
                        "at": datetime.now(tz=timezone.utc).isoformat(),
                        "action": "rollback_noop",
                        "status": patch.status,
                    }
                )
                self._persist()
            return copy.deepcopy(patch.before)
        patch.status = "rolled_back"
        patch.rolled_back_at = datetime.now(tz=timezone.utc)
        patch.audit = {
            **patch.audit,
            "rolled_back": True,
            "rolled_back_at": patch.rolled_back_at.isoformat(),
        }
        patch.history.append(
            {"at": patch.rolled_back_at.isoformat(), "action": "rollback", "status": patch.status}
        )
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
            history=copy.deepcopy(patch.history),
            summary=copy.deepcopy(patch.summary),
        )
