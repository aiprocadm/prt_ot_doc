from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.session import session_scope, tenant_context, ensure_tenant_schema
from app.models.models import AuditExportJob, AuditLog
from app.services.celery_app import celery_app
from app.services.file_storage import FileStorageService


@celery_app.task(name="app.tasks.audit_export_job")
def export_audit_job(*, export_id: str, tenant_id: str) -> dict[str, str]:
    from app.tasks import _run_coroutine

    async def _run() -> dict[str, str]:
        with tenant_context(tenant_id):
            ensure_tenant_schema(tenant_id)
            async with session_scope(tenant=tenant_id) as session:
                job = await session.get(AuditExportJob, export_id)
                if job is None:
                    return {"status": "missing"}
                job.status = "running"
                await session.flush()

                stmt = select(AuditLog).where(AuditLog.tenant_id == tenant_id)
                filters = job.filters or {}
                if filters.get("entity_type"):
                    stmt = stmt.where(AuditLog.object_type == filters["entity_type"])
                if filters.get("entity_id"):
                    stmt = stmt.where(AuditLog.object_id == filters["entity_id"])
                if filters.get("actor_id"):
                    stmt = stmt.where(AuditLog.user_id == filters["actor_id"])
                if filters.get("action"):
                    stmt = stmt.where(AuditLog.action == filters["action"])
                if filters.get("from"):
                    stmt = stmt.where(AuditLog.when >= datetime.fromisoformat(filters["from"]))
                if filters.get("to"):
                    stmt = stmt.where(AuditLog.when <= datetime.fromisoformat(filters["to"]))
                rows = (await session.execute(stmt.order_by(AuditLog.when.asc()))).scalars().all()

                if job.format == "csv":
                    buff = io.StringIO()
                    writer = csv.writer(buff)
                    writer.writerow(["ts", "actor", "action", "entity_type", "entity_id", "correlation_id", "diff_json"])
                    for row in rows:
                        writer.writerow([
                            row.when.isoformat(),
                            row.user_id or "",
                            row.action,
                            row.object_type,
                            row.object_id,
                            row.request_id or "",
                            json.dumps(row.changed_fields or {}, ensure_ascii=False),
                        ])
                    body = buff.getvalue().encode("utf-8")
                else:
                    lines = []
                    for row in rows:
                        lines.append(json.dumps({
                            "ts": row.when.isoformat(),
                            "actor_id": row.user_id,
                            "action": row.action,
                            "entity_type": row.object_type,
                            "entity_id": row.object_id,
                            "correlation_id": row.request_id,
                            "diff": row.changed_fields or {},
                            "meta": row.details or {},
                        }, ensure_ascii=False))
                    body = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")

                extension = "csv" if job.format == "csv" else "jsonl"
                key = f"{tenant_id}/exports/audit/{job.id}.{extension}"
                FileStorageService.default().put(key, body, content_type="text/csv" if extension == "csv" else "application/x-ndjson")

                job.storage_key = key
                job.sha256 = hashlib.sha256(body).hexdigest()
                job.size_bytes = len(body)
                job.expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=1)
                job.signed_url = f"/api/v1/audit/exports/{job.id}/download"
                job.status = "success"
                await session.commit()
                return {"status": "ok", "export_id": export_id}

    return _run_coroutine(_run())


__all__ = ["export_audit_job"]
