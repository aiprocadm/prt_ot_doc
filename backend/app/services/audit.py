from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.tracing import get_trace_id
from app.models.models import AuditLog

logger = logging.getLogger(__name__)
settings = get_settings()

_PII_KEY_RE = re.compile(r"(email|phone|passport|snils|inn|birth|address)", re.IGNORECASE)
_SECRET_KEY_RE = re.compile(r"(password|token|secret|key|signature)", re.IGNORECASE)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {key: _normalize_value(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_value(item) for item in value]
    return value


def _normalize_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    return {key: _normalize_value(val) for key, val in (payload or {}).items()}


def _sanitize_mapping(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in (payload or {}).items():
        if _SECRET_KEY_RE.search(str(key)):
            continue
        if isinstance(value, Mapping):
            sanitized[key] = _sanitize_mapping(value)
        elif isinstance(value, list):
            sanitized[key] = [
                _sanitize_mapping(item) if isinstance(item, Mapping) else _normalize_value(item)
                for item in value
            ]
        elif _PII_KEY_RE.search(str(key)):
            sanitized[key] = _mask_value(value)
        else:
            sanitized[key] = _normalize_value(value)
    return sanitized


def _mask_value(value: Any) -> Any:
    if value is None:
        return None
    text = str(value)
    if "@" in text:
        local, _, domain = text.partition("@")
        return f"{(local[:1] or '*')}***@{domain}"
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 4:
        return f"****{digits[-2:]}"
    return "***"


def _flatten(data: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping):
            result.update(_flatten(value, path))
            continue
        if isinstance(value, list):
            result[path] = {"count": len(value)}
            continue
        result[path] = _normalize_value(value)
    return result


def _list_collection_diff(before: list[Any], after: list[Any]) -> dict[str, Any]:
    """Diff list payloads by item id when possible."""

    if not all(isinstance(item, Mapping) for item in [*before, *after]):
        if before != after:
            return {
                "added": [item for item in after if item not in before],
                "removed": [item for item in before if item not in after],
                "updated": [],
            }
        return {"added": [], "removed": [], "updated": []}

    def _item_key(item: Mapping[str, Any]) -> str | None:
        for candidate in ("id", "uuid", "code"):
            if item.get(candidate) is not None:
                return str(item.get(candidate))
        return None

    before_by_id = {
        key: dict(item) for item in before if isinstance(item, Mapping) and (key := _item_key(item))
    }
    after_by_id = {
        key: dict(item) for item in after if isinstance(item, Mapping) and (key := _item_key(item))
    }
    if not before_by_id and not after_by_id:
        if before != after:
            return {"added": list(after), "removed": list(before), "updated": []}
        return {"added": [], "removed": [], "updated": []}

    added = [after_by_id[item_id] for item_id in sorted(after_by_id.keys() - before_by_id.keys())]
    removed = [
        before_by_id[item_id] for item_id in sorted(before_by_id.keys() - after_by_id.keys())
    ]
    updated: list[dict[str, Any]] = []
    for item_id in sorted(before_by_id.keys() & after_by_id.keys()):
        item_diff = field_level_diff(before_by_id[item_id], after_by_id[item_id])
        if item_diff.get("fields"):
            updated.append({"id": item_id, "fields": item_diff["fields"]})
    return {"added": added, "removed": removed, "updated": updated}


def field_level_diff(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    *,
    exclude: set[str] | None = None,
) -> dict[str, Any]:
    excluded = {"updated_at", "created_at", "version", *(exclude or set())}
    changed: dict[str, Any] = {}
    added: dict[str, Any] = {}
    removed: dict[str, Any] = {}
    masked: list[str] = []
    normalized_before = _normalize_payload(before)
    normalized_after = _normalize_payload(after)
    before_flat = _flatten(normalized_before)
    after_flat = _flatten(normalized_after)
    keys = set(before_flat.keys()).union(after_flat.keys())
    for key in keys:
        if key in excluded:
            continue
        prev = before_flat.get(key)
        nxt = after_flat.get(key)
        if prev != nxt:
            pii = bool(_PII_KEY_RE.search(key))
            from_val = _mask_value(prev) if pii else prev
            to_val = _mask_value(nxt) if pii else nxt
            if pii:
                masked.append(key)
            if prev is None:
                added[key] = {"to": to_val}
            elif nxt is None:
                removed[key] = {"from": from_val}
            else:
                changed[key] = {"from": from_val, "to": to_val}

    fields = {
        **{k: {"from": v.get("from"), "to": v.get("to")} for k, v in changed.items()},
        **{k: {"from": None, "to": v.get("to")} for k, v in added.items()},
        **{k: {"from": v.get("from"), "to": None} for k, v in removed.items()},
    }

    collections: dict[str, Any] = {}
    collection_keys = {
        key
        for key in set(normalized_before.keys()) | set(normalized_after.keys())
        if isinstance(normalized_before.get(key), list)
        or isinstance(normalized_after.get(key), list)
    }
    for key in sorted(collection_keys):
        before_list = (
            normalized_before.get(key) if isinstance(normalized_before.get(key), list) else []
        )
        after_list = (
            normalized_after.get(key) if isinstance(normalized_after.get(key), list) else []
        )
        diff = _list_collection_diff(before_list, after_list)
        if diff["added"] or diff["removed"] or diff["updated"]:
            collections[key] = diff

    return {
        "fields": fields,
        "collections": collections,
        "changed": changed,
        "added": added,
        "removed": removed,
        "masked": sorted(set(masked)),
    }


def compute_snapshot_hash(payload: Mapping[str, Any] | None) -> str | None:
    if not payload:
        return None
    import json

    raw = json.dumps(_normalize_payload(payload), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AuditService:
    """Persist audit trail entries for security-sensitive actions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _prev_hash(self) -> str | None:
        stmt = select(AuditLog.hash).order_by(AuditLog.when.desc()).limit(1)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    @staticmethod
    def _canonical_hash_payload(payload: Mapping[str, Any], prev_hash: str | None) -> str:
        raw = json.dumps(
            _normalize_payload(payload), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        return hashlib.sha256(f"{raw}|{prev_hash or ''}".encode("utf-8")).hexdigest()

    async def log_event(
        self,
        *,
        tenant_id: str,
        action: str,
        object_type: str,
        object_id: str,
        user_id: str | None,
        ip: str,
        request_id: str | None = None,
        session_id: str | None = None,
        user_agent: str | None = None,
        changed_fields: Mapping[str, Any] | None = None,
        when: datetime | None = None,
        details: Mapping[str, Any] | None = None,
        actor_type: str = "user",
        actor_email: str | None = None,
        parent_type: str | None = None,
        parent_id: str | None = None,
        before_hash: str | None = None,
        after_hash: str | None = None,
        before_json: Mapping[str, Any] | None = None,
        after_json: Mapping[str, Any] | None = None,
        actor_role_codes: list[str] | None = None,
    ) -> AuditLog:
        """Create and persist a new audit log entry."""

        if not settings.audit_enabled:
            logger.debug("audit.disabled")
            return AuditLog(
                tenant_id=tenant_id,
                action=action,
                object_type=object_type,
                object_id=object_id,
                user_id=user_id,
                ip=ip or "unknown",
            )
        payload = _sanitize_mapping(details)
        safe_diff = _sanitize_mapping(changed_fields)
        correlation_id = request_id or get_trace_id(default="unknown")
        prev_hash = await self._prev_hash()
        hash_payload = {
            "tenant_id": tenant_id,
            "actor_type": actor_type,
            "user_id": user_id,
            "action": action,
            "object_type": object_type,
            "object_id": object_id,
            "correlation_id": correlation_id,
            "diff": safe_diff,
            "meta": payload,
            "ts": (when or datetime.now(tz=timezone.utc)).isoformat(),
        }
        row_hash = self._canonical_hash_payload(hash_payload, prev_hash)
        entry = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            ip=ip or "unknown",
            request_id=correlation_id,
            correlation_id=correlation_id,
            session_id=session_id,
            user_agent=user_agent,
            changed_fields=safe_diff,
            before_json=_sanitize_mapping(before_json),
            after_json=_sanitize_mapping(after_json),
            actor_role_codes=[str(item) for item in (actor_role_codes or [])],
            when=when or datetime.now(tz=timezone.utc),
            details=payload,
            resource_attrs=_sanitize_mapping(
                payload.get("resource_attrs") if isinstance(payload, Mapping) else {}
            ),
            actor_type=actor_type,
            actor_email=actor_email,
            parent_type=parent_type,
            parent_id=parent_id,
            before_hash=before_hash,
            after_hash=after_hash,
            prev_hash=prev_hash,
            hash=row_hash,
        )
        self.session.add(entry)
        await self.session.flush()
        logger.info(
            "audit.log",
            extra={
                "tenant_id": tenant_id,
                "user_id": user_id,
                "action": action,
                "object_type": object_type,
                "object_id": object_id,
            },
        )
        return entry

    async def verify_audit_chain(
        self,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
    ) -> dict[str, Any]:
        stmt = select(AuditLog).order_by(AuditLog.when.asc())
        if entity_type:
            stmt = stmt.where(AuditLog.object_type == entity_type)
        if entity_id:
            stmt = stmt.where(AuditLog.object_id == entity_id)
        if from_ts:
            stmt = stmt.where(AuditLog.when >= from_ts)
        if to_ts:
            stmt = stmt.where(AuditLog.when <= to_ts)
        rows = (await self.session.execute(stmt)).scalars().all()
        prev: str | None = rows[0].prev_hash if rows else None
        broken: list[str] = []
        for row in rows:
            check_payload = {
                "tenant_id": row.tenant_id,
                "actor_type": row.actor_type,
                "user_id": row.user_id,
                "action": row.action,
                "object_type": row.object_type,
                "object_id": row.object_id,
                "correlation_id": row.correlation_id or row.request_id,
                "diff": row.changed_fields or {},
                "meta": row.details or {},
                "ts": row.when.isoformat(),
            }
            expected = self._canonical_hash_payload(check_payload, prev)
            if row.prev_hash != prev or row.hash != expected:
                broken.append(row.id)
            prev = row.hash
        return {"ok": not broken, "checked": len(rows), "broken_ids": broken}

    async def audit_create(
        self,
        *,
        tenant_id: str,
        entity_type: str,
        entity_id: str,
        after: Mapping[str, Any],
        meta: Mapping[str, Any] | None,
        actor: Mapping[str, Any],
    ) -> AuditLog:
        return await self.log_event(
            tenant_id=tenant_id,
            action="create",
            object_type=entity_type,
            object_id=entity_id,
            user_id=actor.get("id"),
            actor_email=actor.get("email"),
            actor_type=str(actor.get("type", "user")),
            ip=str(meta.get("ip", "unknown")) if meta else "unknown",
            request_id=(meta or {}).get("correlation_id"),
            user_agent=(meta or {}).get("user_agent"),
            changed_fields=field_level_diff({}, after),
            before_json={},
            after_json=after,
            details={"meta": dict(meta or {})},
            after_hash=compute_snapshot_hash(after),
        )

    async def audit_update(
        self,
        *,
        tenant_id: str,
        entity_type: str,
        entity_id: str,
        before: Mapping[str, Any],
        after: Mapping[str, Any],
        meta: Mapping[str, Any] | None,
        actor: Mapping[str, Any],
    ) -> AuditLog:
        return await self.log_event(
            tenant_id=tenant_id,
            action="update",
            object_type=entity_type,
            object_id=entity_id,
            user_id=actor.get("id"),
            actor_email=actor.get("email"),
            actor_type=str(actor.get("type", "user")),
            ip=str(meta.get("ip", "unknown")) if meta else "unknown",
            request_id=(meta or {}).get("correlation_id"),
            user_agent=(meta or {}).get("user_agent"),
            changed_fields=field_level_diff(before, after),
            before_json=before,
            after_json=after,
            details={"meta": dict(meta or {})},
            before_hash=compute_snapshot_hash(before),
            after_hash=compute_snapshot_hash(after),
        )

    async def audit_delete(
        self,
        *,
        tenant_id: str,
        entity_type: str,
        entity_id: str,
        before: Mapping[str, Any],
        meta: Mapping[str, Any] | None,
        actor: Mapping[str, Any],
    ) -> AuditLog:
        return await self.log_event(
            tenant_id=tenant_id,
            action="delete",
            object_type=entity_type,
            object_id=entity_id,
            user_id=actor.get("id"),
            actor_email=actor.get("email"),
            actor_type=str(actor.get("type", "user")),
            ip=str(meta.get("ip", "unknown")) if meta else "unknown",
            request_id=(meta or {}).get("correlation_id"),
            user_agent=(meta or {}).get("user_agent"),
            changed_fields=field_level_diff(
                before, {**dict(before), "deleted_at": datetime.now(tz=timezone.utc).isoformat()}
            ),
            before_json=before,
            after_json={"deleted": True},
            details={"meta": dict(meta or {})},
            before_hash=compute_snapshot_hash(before),
        )

    async def audit_restore(
        self,
        *,
        tenant_id: str,
        entity_type: str,
        entity_id: str,
        before: Mapping[str, Any],
        after: Mapping[str, Any],
        meta: Mapping[str, Any] | None,
        actor: Mapping[str, Any],
    ) -> AuditLog:
        return await self.log_event(
            tenant_id=tenant_id,
            action="restore",
            object_type=entity_type,
            object_id=entity_id,
            user_id=actor.get("id"),
            actor_email=actor.get("email"),
            actor_type=str(actor.get("type", "user")),
            ip=str(meta.get("ip", "unknown")) if meta else "unknown",
            request_id=(meta or {}).get("correlation_id"),
            user_agent=(meta or {}).get("user_agent"),
            changed_fields=field_level_diff(before, after),
            before_json=before,
            after_json=after,
            details={"meta": dict(meta or {})},
            before_hash=compute_snapshot_hash(before),
            after_hash=compute_snapshot_hash(after),
        )


    async def log_change(
        self,
        *,
        tenant_id: str,
        entity_type: str,
        entity_id: str,
        action: str,
        before: Mapping[str, Any] | None,
        after: Mapping[str, Any] | None,
        actor_id: str | None,
        actor_role_codes: list[str] | None = None,
        correlation_id: str | None = None,
        ip: str = "unknown",
        user_agent: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> AuditLog:
        return await self.log_event(
            tenant_id=tenant_id,
            action=action,
            object_type=entity_type,
            object_id=entity_id,
            user_id=actor_id,
            ip=ip,
            request_id=correlation_id,
            user_agent=user_agent,
            changed_fields=field_level_diff(before, after),
            before_json=before,
            after_json=after,
            actor_role_codes=actor_role_codes or [],
            details=details or {},
        )

    async def log(
        self,
        *,
        actor_id: str | None,
        action: str,
        entity: str,
        entity_id: str,
        diff: Mapping[str, Any] | None = None,
        ip: str = "system",
        request_id: str | None = None,
        session_id: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLog:
        """Backward-compatible wrapper for logging audit events."""

        tenant_id = str(
            self.session.info.get("tenant_id")
            or self.session.info.get("token_tenant_id")
            or ""
        ).strip()
        return await self.log_event(
            tenant_id=tenant_id,
            action=action,
            object_type=entity,
            object_id=entity_id,
            user_id=actor_id,
            ip=ip,
            request_id=request_id,
            session_id=session_id,
            user_agent=user_agent,
            changed_fields=diff,
            details=diff,
        )
