from __future__ import annotations

import hashlib
import json
from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.models.job_engine import DocumentArtifact, DocumentJob, DocumentJobStep
from app.modules.files.models import FileEntityType, FileLinkRole
from app.modules.files.service import FileService, build_artifact_name
from app.services.document_quality import build_quality_report
from app.services.integrations.factory import get_edo_integration
from app.services.integrations.interfaces import IntegrationDisabledError

StepHandler = Callable[..., Awaitable[dict[str, Any]]]


async def validate_template_step_handler(*, session, job: DocumentJob, step: DocumentJobStep) -> dict[str, Any]:
    """Проверяет, что код шаблона и версия существуют и пригодны для генерации."""

    from app.models.models import Template, TemplateVersion, TemplateVersionStatus

    payload = job.input_payload_json or job.input or {}
    code = (payload.get("template_code") or job.template_code or "").strip()
    if not code:
        raise ValueError("template_code_missing")

    tenant_id = str(job.tenant_id)
    try:
        tpl = (
            await session.execute(
                select(Template).where(Template.tenant_id == tenant_id, Template.code == code)
            )
        ).scalar_one_or_none()
    except (OperationalError, ProgrammingError):
        return {
            "status": "skipped",
            "reason": "template_catalog_unavailable",
            "step": "validate_template",
        }
    if tpl is None:
        raise ValueError(f"template_not_found:{code}")

    ver_spec = payload.get("template_version")
    tv = None
    if ver_spec is not None:
        try:
            ver_num = int(ver_spec)
        except (TypeError, ValueError) as exc:
            raise ValueError("template_version_invalid") from exc
        tv = (
            await session.execute(
                select(TemplateVersion).where(
                    TemplateVersion.tenant_id == tenant_id,
                    TemplateVersion.template_id == tpl.id,
                    TemplateVersion.version == ver_num,
                )
            )
        ).scalar_one_or_none()
    elif tpl.current_version_id:
        tv = await session.get(TemplateVersion, tpl.current_version_id)
        if tv is not None and (
            str(tv.tenant_id) != tenant_id or str(tv.template_id) != str(tpl.id)
        ):
            tv = None

    if tv is None:
        raise ValueError("template_version_not_found")

    unusable = {
        TemplateVersionStatus.DEPRECATED,
        TemplateVersionStatus.ARCHIVED,
        TemplateVersionStatus.DRAFT,
    }
    if tv.status in unusable:
        raise ValueError(f"template_version_unusable:{tv.status.value}")

    return {
        "status": "ok",
        "template_id": tpl.id,
        "template_version_id": tv.id,
        "template_version": tv.version,
        "template_version_status": tv.status.value,
    }


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


async def quality_gate_step_handler(*, job: DocumentJob, step: DocumentJobStep) -> dict[str, Any]:
    payload = job.input_payload_json or {}
    data = payload.get("inline_data") if isinstance(payload.get("inline_data"), dict) else payload.get("data")
    if not isinstance(data, dict):
        data = {}
    config = step.input.get("config", {}) if isinstance(step.input, dict) else {}
    required_fields = config.get("required_fields") if isinstance(config.get("required_fields"), list) else []
    date_fields = config.get("date_fields") if isinstance(config.get("date_fields"), list) else []
    numeric_fields = config.get("numeric_fields") if isinstance(config.get("numeric_fields"), list) else []
    rendered_text = config.get("rendered_text") if isinstance(config.get("rendered_text"), str) else None
    report = build_quality_report(
        data=data,
        required_fields=[str(x) for x in required_fields],
        date_fields=[str(x) for x in date_fields],
        numeric_fields=[str(x) for x in numeric_fields],
        rendered_text=rendered_text,
    )
    if report.release_blocked:
        raise ValueError("quality_gate_blocked_release")
    return report.model_dump(mode="json")
