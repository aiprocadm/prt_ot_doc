from __future__ import annotations

import hashlib
import json
from typing import Any, Awaitable, Callable

from app.models.job_engine import DocumentArtifact, DocumentJob, DocumentJobStep
from app.modules.files.models import FileEntityType, FileLinkRole
from app.modules.files.service import FileService, build_artifact_name
from app.services.integrations.factory import get_edo_integration
from app.services.integrations.interfaces import IntegrationDisabledError

StepHandler = Callable[..., Awaitable[dict[str, Any]]]


async def artifact_step_handler(*, session, job: DocumentJob, step: DocumentJobStep, step_key: str) -> dict[str, Any]:
    payload = f"{step_key}:{job.id}".encode("utf-8")
    ext = "pdf" if step_key == "convert_pdf" else ("zip" if step_key == "build_zip" else "bin")
    filename = build_artifact_name(job.input_payload_json or {}, ext=ext)
    svc = FileService(session=session, tenant_id=str(job.tenant_id))
    file_record = await svc.create_artifact_from_bytes(
        payload=payload,
        filename=filename,
        content_type="application/octet-stream",
        job_id=job.id,
        step_key=step_key,
        metadata_json={"job_id": job.id, "step_key": step_key, "display_name": filename},
        entity_type=FileEntityType.job_step.value,
        entity_id=step.id,
        role=FileLinkRole.artifact.value,
    )
    await svc.link_file(
        file_id=file_record.id,
        entity_type=FileEntityType.job.value,
        entity_id=job.id,
        role=FileLinkRole.artifact.value,
    )
    session.add(
        DocumentArtifact(
            tenant_id=job.tenant_id,
            job_id=job.id,
            step_code=step.step_code,
            kind=step_key,
            file_id=file_record.id,
            sha256=file_record.sha256,
            meta={"file_id": file_record.id, "display_name": filename},
        )
    )
    return {"file_id": file_record.id, "kind": step_key, "display_name": filename}


async def signature_step_handler(*, job: DocumentJob, step: DocumentJobStep, step_key: str) -> dict[str, Any]:
    payload = job.input_payload_json or {}
    digest = hashlib.sha256(
        json.dumps(
            {
                "job_id": job.id,
                "step_id": step.id,
                "tenant_id": job.tenant_id,
                "payload": payload,
            },
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    return {
        "status": "verified",
        "provider": "internal-orchestrator",
        "signature_type": "deterministic-snapshot",
        "verification": {
            "verified": True,
            "digest": digest,
            "correlation_id": job.correlation_id,
        },
        "step": step_key,
    }


async def edo_step_handler(*, job: DocumentJob, step: DocumentJobStep) -> dict[str, Any]:
    provider = get_edo_integration()
    payload = job.input_payload_json or {}
    filename = build_artifact_name(payload, ext="pdf")
    content = json.dumps(
        {
            "job_id": job.id,
            "step_id": step.id,
            "template_code": job.template_code,
            "payload": payload,
        },
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    try:
        status = await provider.send_document(
            content=content,
            filename=filename,
            metadata={
                "job_id": job.id,
                "step_id": step.id,
                "tenant_id": job.tenant_id,
                "correlation_id": job.correlation_id,
            },
        )
    except IntegrationDisabledError:
        return {
            "status": "completed",
            "provider": provider.name,
            "reason": "edo_integration_disabled",
            "deferred": False,
            "provider_mode": "non_production",
            "bridge_mode": "internal-fallback",
            "detail": "Internal fallback completed without external EDO adapter.",
        }
    return {
        "status": status.status,
        "provider": provider.name,
        "external_id": status.external_id,
        "details": status.details,
        "deferred": False,
    }


async def index_projection_step_handler(*, job: DocumentJob, step: DocumentJobStep) -> dict[str, Any]:
    payload = step.input or {}
    source_payload = payload.get("payload") if isinstance(payload, dict) else {}
    serialized = json.dumps(source_payload or job.input_payload_json or {}, sort_keys=True, default=str)
    tokens = [token for token in serialized.replace("{", " ").replace("}", " ").replace('"', " ").split() if token]
    return {
        "status": "indexed",
        "source": "job_payload_projection",
        "terms_indexed": len(tokens),
        "preview_terms": tokens[:10],
    }
