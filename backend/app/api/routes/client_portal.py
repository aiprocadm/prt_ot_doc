from __future__ import annotations

import json

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.config import get_settings
from app.models.models import (
    ClientPackagePreset,
    ClientPackageRun,
    ClientPortalToken,
    ClientRequestTicket,
    ClientRequestTicketStatus,
    PackageEvent,
    PackageRequirement,
    PackageRequirementStatus,
    PackageRequirementType,
    PackageRunStatus,
    Tenant,
)
from app.services.file_storage import FileStorageService

router = APIRouter(prefix="/portal", tags=["client-portal"])
internal_router = APIRouter(prefix="/packages", tags=["packages"])
presets_router = APIRouter(prefix="/presets/packages", tags=["package-presets"])


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _hash_token(token: str) -> str:
    salt = get_settings().portal_token_salt
    return hashlib.sha256(f"{salt}:{token}".encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_required_inputs(required_inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in required_inputs:
        requirement_type = str(item.get("type") or "file").lower()
        normalized.append(
            {
                "key": str(item.get("key") or secrets.token_hex(4)),
                "title": str(item.get("title") or "Required data"),
                "type": requirement_type,
                "required": bool(item.get("required", True)),
                "description": item.get("description"),
                "artifact_kind": item.get("artifact_kind", requirement_type),
            }
        )
    return normalized


def _resolve_pipeline(preset: ClientPackagePreset) -> dict[str, Any]:
    required_inputs = _normalize_required_inputs(preset.required_inputs_json or [])
    steps_json = dict(preset.steps_json or {})
    steps = list(steps_json.get("steps") or [])
    if not steps:
        steps = [
            {"code": "collect_requirements", "title": "Collect client inputs"},
            {"code": "generate_documents", "title": "Generate package documents"},
            {"code": "quality_check", "title": "Quality check"},
            {"code": "publish_portal", "title": "Publish to client portal"},
        ]
    scenario_map = {
        "OUT_TO_SITE": "Выход на объект",
        "INCIDENT": "Несчастный случай",
        "INSPECTION_PREP": "Подготовка к проверке",
    }
    return {
        "scenario": scenario_map.get(preset.code, preset.name),
        "required_inputs": required_inputs,
        "steps": steps,
        "output_artifacts": list(
            steps_json.get("output_artifacts")
            or [
                {"kind": "zip", "title": f"{preset.name} bundle"},
                {"kind": "pdf", "title": f"{preset.name} summary"},
                {"kind": "manifest", "title": f"{preset.name} manifest"},
            ]
        ),
    }


def _write_package_artifacts(*, run: ClientPackageRun, preset: ClientPackagePreset, pipeline: dict[str, Any]) -> tuple[str, str, str, dict[str, Any]]:
    storage = FileStorageService.default()
    prefix = f"packages/{run.id}"
    manifest_key = f"{prefix}/manifest.json"
    zip_key = f"{prefix}/result.zip"
    pdf_key = f"{prefix}/result.pdf"
    manifest = {
        "run_id": run.id,
        "preset_code": preset.code,
        "preset_name": preset.name,
        "scenario": pipeline["scenario"],
        "status": run.status.value if hasattr(run.status, "value") else str(run.status),
        "steps": pipeline["steps"],
        "required_inputs": pipeline["required_inputs"],
        "output_artifacts": pipeline["output_artifacts"],
        "generated_at": _utcnow().isoformat(),
    }
    storage.put(manifest_key, json.dumps(jsonable_encoder(manifest), ensure_ascii=False).encode("utf-8"), content_type="application/json")
    storage.put(zip_key, f"ZIP bundle for {preset.code} / {run.id}".encode("utf-8"), content_type="application/zip")
    storage.put(pdf_key, f"PDF summary for {preset.name}".encode("utf-8"), content_type="application/pdf")
    qc_report = {
        "scenario": pipeline["scenario"],
        "steps": [{"name": step.get("code", step.get("title", "step")), "status": "done"} for step in pipeline["steps"]],
        "requirements_total": len(pipeline["required_inputs"]),
        "artifacts": [zip_key, pdf_key, manifest_key],
    }
    return zip_key, pdf_key, manifest_key, qc_report


def _artifact_entry(storage: FileStorageService, key: str | None, *, kind: str) -> dict[str, Any] | None:
    if not key:
        return None
    meta = storage.head(key) or {"key": key}
    return {
        "kind": kind,
        "s3_key": key,
        "signed_url": storage.create_signed_url(key),
        "quarantined": meta.get("quarantined", False),
        "sha256": meta.get("sha256"),
        "size": meta.get("size"),
    }


class PackagePresetCreate(BaseModel):
    code: str
    name: str
    description: str | None = None
    steps_json: dict[str, Any] = Field(default_factory=dict)
    required_inputs_json: list[dict[str, Any]] = Field(default_factory=list)
    is_active: bool = True


class PackagePresetPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    steps_json: dict[str, Any] | None = None
    required_inputs_json: list[dict[str, Any]] | None = None
    is_active: bool | None = None


class PackageRunCreate(BaseModel):
    preset_code: str
    client_company_id: str | None = None


class PortalLinkResponse(BaseModel):
    portal_url: str
    expires_at: datetime


class PackageTicketCreate(BaseModel):
    title: str
    message: str


class PortalFilesResponse(BaseModel):
    files: list[dict[str, Any]]


class PortalAuth(BaseModel):
    tenant_id: str
    package_run_ids: set[str]
    can_upload: bool = False
    can_tickets: bool = False
    can_download: bool = False


def _serialize_package_run(run: ClientPackageRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "tenant_id": run.tenant_id,
        "preset_id": run.preset_id,
        "initiated_by_user_id": run.initiated_by_user_id,
        "client_company_id": run.client_company_id,
        "status": run.status.value if isinstance(run.status, PackageRunStatus) else run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "output_zip_s3_key": run.output_zip_s3_key,
        "output_pdf_s3_key": run.output_pdf_s3_key,
        "qc_report_json": run.qc_report_json,
        "error_payload_json": run.error_payload_json,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "deleted_at": run.deleted_at,
    }


async def _portal_auth(
    session: Annotated[AsyncSession, Depends(get_session)],
    x_portal_token: Annotated[str | None, Header(alias="X-Portal-Token")] = None,
    token: Annotated[str | None, Query()] = None,
) -> PortalAuth:
    raw = x_portal_token or token
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Portal token is required")
    token_hash = _hash_token(raw)
    stmt = select(ClientPortalToken).where(ClientPortalToken.token_hash == token_hash)
    record = (await session.execute(stmt)).scalar_one_or_none()
    if record is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid portal token")
    expires_at = _as_utc(record.expires_at)
    if record.revoked_at is not None or expires_at <= _utcnow():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Portal token expired or revoked")
    if not hmac.compare_digest(_hash_token(raw), record.token_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid portal token")
    scope = record.scope_json or {}
    package_ids = set(scope.get("package_run_ids") or [record.package_run_id])
    return PortalAuth(
        tenant_id=str(record.tenant_id),
        package_run_ids=package_ids,
        can_upload=bool(scope.get("upload", True)),
        can_tickets=bool(scope.get("tickets", True)),
        can_download=bool(scope.get("download", True)),
    )


async def _get_run_for_tenant(session: AsyncSession, *, run_id: str, tenant_id: str) -> ClientPackageRun:
    run = await session.get(ClientPackageRun, run_id)
    if run is None or str(run.tenant_id) != str(tenant_id) or run.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return run


@presets_router.get("")
async def list_presets(session: Annotated[AsyncSession, Depends(get_session)], tenant: Annotated[Tenant, Depends(get_tenant_record)]):
    rows = (
        await session.execute(
            select(ClientPackagePreset).where(
                ClientPackagePreset.tenant_id == tenant.id,
                ClientPackagePreset.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    return rows


@presets_router.post("", status_code=status.HTTP_201_CREATED)
async def create_preset(payload: PackagePresetCreate, session: Annotated[AsyncSession, Depends(get_session)], tenant: Annotated[Tenant, Depends(get_tenant_record)]):
    record = ClientPackagePreset(tenant_id=tenant.id, **payload.model_dump())
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


@presets_router.patch("/{preset_id}")
async def patch_preset(preset_id: str, payload: PackagePresetPatch, session: Annotated[AsyncSession, Depends(get_session)], tenant: Annotated[Tenant, Depends(get_tenant_record)]):
    record = await session.get(ClientPackagePreset, preset_id)
    if record is None or record.tenant_id != tenant.id or record.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Preset not found")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(record, key, value)
    await session.commit()
    await session.refresh(record)
    return record


@internal_router.post("/runs", status_code=status.HTTP_201_CREATED)
async def create_run(payload: PackageRunCreate, session: Annotated[AsyncSession, Depends(get_session)], tenant: Annotated[Tenant, Depends(get_tenant_record)]):
    preset = (
        await session.execute(
            select(ClientPackagePreset).where(
                ClientPackagePreset.code == payload.preset_code,
                ClientPackagePreset.deleted_at.is_(None),
                ClientPackagePreset.tenant_id == tenant.id,
            )
        )
    ).scalar_one_or_none()
    if preset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Preset not found")
    pipeline = _resolve_pipeline(preset)
    run = ClientPackageRun(
        tenant_id=tenant.id,
        preset_id=preset.id,
        client_company_id=payload.client_company_id,
        status=PackageRunStatus.RUNNING,
        started_at=_utcnow(),
        qc_report_json={"status_flow": ["running", "published"], "steps": []},
    )
    session.add(run)
    await session.flush()
    zip_key, pdf_key, manifest_key, qc_report = _write_package_artifacts(run=run, preset=preset, pipeline=pipeline)
    run.output_zip_s3_key = zip_key
    run.output_pdf_s3_key = pdf_key
    run.qc_report_json = qc_report
    for req in pipeline["required_inputs"]:
        session.add(
            PackageRequirement(
                tenant_id=tenant.id,
                package_run_id=run.id,
                key=req.get("key", secrets.token_hex(4)),
                title=req.get("title", "Required data"),
                type=PackageRequirementType(req.get("type", "file")),
                status=PackageRequirementStatus.MISSING,
                payload_json=req,
            )
        )
    session.add_all(
        [
            PackageEvent(tenant_id=tenant.id, package_run_id=run.id, type="package_run.started", payload_json={"status": "running", "scenario": pipeline["scenario"]}),
            PackageEvent(tenant_id=tenant.id, package_run_id=run.id, type="package_run.generated", payload_json={"manifest_key": manifest_key, "artifacts": qc_report["artifacts"]}),
            PackageEvent(tenant_id=tenant.id, package_run_id=run.id, type="package_run.published", payload_json={"portal_visible": True, "status": "published"}),
        ]
    )
    await session.commit()
    await session.refresh(run)
    return _serialize_package_run(run)


@internal_router.get("/runs")
async def list_runs(session: Annotated[AsyncSession, Depends(get_session)], tenant: Annotated[Tenant, Depends(get_tenant_record)]):
    rows = (
        await session.execute(
            select(ClientPackageRun).where(
                ClientPackageRun.tenant_id == tenant.id,
                ClientPackageRun.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    return [_serialize_package_run(run) for run in rows]


@internal_router.get("/runs/{run_id}")
async def get_run(run_id: str, session: Annotated[AsyncSession, Depends(get_session)], tenant: Annotated[Tenant, Depends(get_tenant_record)]):
    return _serialize_package_run(await _get_run_for_tenant(session, run_id=run_id, tenant_id=str(tenant.id)))


@internal_router.post("/runs/{run_id}/portal-link", response_model=PortalLinkResponse)
async def create_portal_link(run_id: str, session: Annotated[AsyncSession, Depends(get_session)], tenant: Annotated[Tenant, Depends(get_tenant_record)]):
    run = await _get_run_for_tenant(session, run_id=run_id, tenant_id=str(tenant.id))
    plain = secrets.token_urlsafe(24)
    expires_at = _utcnow() + timedelta(hours=24)
    session.add(
        ClientPortalToken(
            tenant_id=tenant.id,
            token_hash=_hash_token(plain),
            package_run_id=run.id,
            expires_at=expires_at,
            scope_json={"package_run_ids": [run.id], "download": True, "upload": True, "tickets": True},
        )
    )
    await session.commit()
    return PortalLinkResponse(portal_url=f"/portal?token={plain}", expires_at=expires_at)


@router.get("/packages")
async def portal_packages(auth: Annotated[PortalAuth, Depends(_portal_auth)], session: Annotated[AsyncSession, Depends(get_session)]):
    rows = (
        await session.execute(
            select(ClientPackageRun).where(
                ClientPackageRun.id.in_(auth.package_run_ids),
                ClientPackageRun.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    return [_serialize_package_run(run) for run in rows]


@router.get("/packages/{run_id}")
async def portal_package_details(run_id: str, auth: Annotated[PortalAuth, Depends(_portal_auth)], session: Annotated[AsyncSession, Depends(get_session)]):
    if run_id not in auth.package_run_ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    run = await _get_run_for_tenant(session, run_id=run_id, tenant_id=auth.tenant_id)
    reqs = (await session.execute(select(PackageRequirement).where(PackageRequirement.package_run_id == run_id))).scalars().all()
    events = (await session.execute(select(PackageEvent).where(PackageEvent.package_run_id == run_id).order_by(PackageEvent.created_at.asc()))).scalars().all()
    tickets = (await session.execute(select(ClientRequestTicket).where(ClientRequestTicket.package_run_id == run_id).order_by(ClientRequestTicket.created_at.asc()))).scalars().all()
    storage = FileStorageService.default()
    files = [item for item in [_artifact_entry(storage, run.output_zip_s3_key, kind="zip"), _artifact_entry(storage, run.output_pdf_s3_key, kind="pdf")] if item]
    return {
        "run": _serialize_package_run(run),
        "requirements": jsonable_encoder(reqs),
        "events": jsonable_encoder(events),
        "tickets": jsonable_encoder(tickets),
        "files": files,
    }


@router.get("/packages/{run_id}/files", response_model=PortalFilesResponse)
async def portal_package_files(run_id: str, auth: Annotated[PortalAuth, Depends(_portal_auth)], session: Annotated[AsyncSession, Depends(get_session)]):
    if run_id not in auth.package_run_ids or not auth.can_download:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    run = await _get_run_for_tenant(session, run_id=run_id, tenant_id=auth.tenant_id)
    storage = FileStorageService.default()
    files = [item for item in [_artifact_entry(storage, run.output_zip_s3_key, kind="zip"), _artifact_entry(storage, run.output_pdf_s3_key, kind="pdf")] if item]
    manifest_key = run.qc_report_json.get("artifacts", [None, None, None])[-1] if run.qc_report_json else None
    manifest = _artifact_entry(storage, manifest_key, kind="manifest") if manifest_key else None
    if manifest:
        files.append(manifest)
    return {"files": files}


@router.post("/packages/{run_id}/tickets", status_code=status.HTTP_201_CREATED)
async def portal_create_ticket(run_id: str, payload: PackageTicketCreate, auth: Annotated[PortalAuth, Depends(_portal_auth)], session: Annotated[AsyncSession, Depends(get_session)]):
    if run_id not in auth.package_run_ids or not auth.can_tickets:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    await _get_run_for_tenant(session, run_id=run_id, tenant_id=auth.tenant_id)
    ticket = ClientRequestTicket(
        tenant_id=auth.tenant_id,
        package_run_id=run_id,
        title=payload.title,
        message=payload.message,
        status=ClientRequestTicketStatus.OPEN,
        created_by="portal-token",
    )
    session.add(ticket)
    session.add(PackageEvent(tenant_id=auth.tenant_id, package_run_id=run_id, type="ticket.created", payload_json={"title": payload.title}))
    await session.commit()
    await session.refresh(ticket)
    return ticket


@router.get("/packages/{run_id}/tickets")
async def portal_list_tickets(run_id: str, auth: Annotated[PortalAuth, Depends(_portal_auth)], session: Annotated[AsyncSession, Depends(get_session)]):
    if run_id not in auth.package_run_ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    await _get_run_for_tenant(session, run_id=run_id, tenant_id=auth.tenant_id)
    return (await session.execute(select(ClientRequestTicket).where(ClientRequestTicket.package_run_id == run_id))).scalars().all()
