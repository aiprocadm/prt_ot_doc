from __future__ import annotations

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

from app.api.dependencies import get_session
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
)

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
    probe = _hash_token(raw)
    if not hmac.compare_digest(probe, record.token_hash):
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


@presets_router.get("")
async def list_presets(session: Annotated[AsyncSession, Depends(get_session)]):
    rows = (await session.execute(select(ClientPackagePreset).where(ClientPackagePreset.deleted_at.is_(None)))).scalars().all()
    return rows


@presets_router.post("", status_code=status.HTTP_201_CREATED)
async def create_preset(payload: PackagePresetCreate, session: Annotated[AsyncSession, Depends(get_session)]):
    record = ClientPackagePreset(**payload.model_dump())
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


@presets_router.patch("/{preset_id}")
async def patch_preset(preset_id: str, payload: PackagePresetPatch, session: Annotated[AsyncSession, Depends(get_session)]):
    record = await session.get(ClientPackagePreset, preset_id)
    if record is None or record.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Preset not found")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(record, key, value)
    await session.commit()
    await session.refresh(record)
    return record


@internal_router.post("/runs", status_code=status.HTTP_201_CREATED)
async def create_run(payload: PackageRunCreate, session: Annotated[AsyncSession, Depends(get_session)]):
    preset = (
        await session.execute(
            select(ClientPackagePreset).where(
                ClientPackagePreset.code == payload.preset_code,
                ClientPackagePreset.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if preset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Preset not found")
    run = ClientPackageRun(
        preset_id=preset.id,
        client_company_id=payload.client_company_id,
        tenant_id=preset.tenant_id,
        status=PackageRunStatus.RUNNING,
        started_at=_utcnow(),
        qc_report_json={"steps": [{"name": "template", "status": "done"}]},
        output_zip_s3_key=f"packages/{secrets.token_hex(8)}/result.zip",
        output_pdf_s3_key=f"packages/{secrets.token_hex(8)}/result.pdf",
    )
    session.add(run)
    await session.flush()
    for req in preset.required_inputs_json:
        session.add(
            PackageRequirement(
                package_run_id=run.id,
                tenant_id=run.tenant_id,
                key=req.get("key", secrets.token_hex(4)),
                title=req.get("title", "Required data"),
                type=PackageRequirementType(req.get("type", "file")),
                status=PackageRequirementStatus.MISSING,
                payload_json=req,
            )
        )
    session.add(
        PackageEvent(
            package_run_id=run.id,
            type="package_run.started",
            payload_json={"status": "running"},
            tenant_id=run.tenant_id,
        )
    )
    await session.commit()
    await session.refresh(run)
    return _serialize_package_run(run)


@internal_router.get("/runs")
async def list_runs(session: Annotated[AsyncSession, Depends(get_session)]):
    rows = (await session.execute(select(ClientPackageRun).where(ClientPackageRun.deleted_at.is_(None)))).scalars().all()
    return [_serialize_package_run(run) for run in rows]


@internal_router.get("/runs/{run_id}")
async def get_run(run_id: str, session: Annotated[AsyncSession, Depends(get_session)]):
    run = await session.get(ClientPackageRun, run_id)
    if run is None or run.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return _serialize_package_run(run)


@internal_router.post("/runs/{run_id}/portal-link", response_model=PortalLinkResponse)
async def create_portal_link(run_id: str, session: Annotated[AsyncSession, Depends(get_session)]):
    run = await session.get(ClientPackageRun, run_id)
    if run is None or run.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    plain = secrets.token_urlsafe(24)
    expires_at = _utcnow() + timedelta(hours=24)
    session.add(
        ClientPortalToken(
            token_hash=_hash_token(plain),
            package_run_id=run.id,
            expires_at=expires_at,
            scope_json={"package_run_ids": [run.id], "download": True, "upload": True, "tickets": True},
            tenant_id=run.tenant_id,
        )
    )
    await session.commit()
    return PortalLinkResponse(portal_url=f"/portal?token={plain}", expires_at=expires_at)


@router.get("/packages")
async def portal_packages(auth: Annotated[PortalAuth, Depends(_portal_auth)], session: Annotated[AsyncSession, Depends(get_session)]):
    rows = (
        await session.execute(
            select(ClientPackageRun).where(ClientPackageRun.id.in_(auth.package_run_ids), ClientPackageRun.deleted_at.is_(None))
        )
    ).scalars().all()
    return [_serialize_package_run(run) for run in rows]


@router.get("/packages/{run_id}")
async def portal_package_details(run_id: str, auth: Annotated[PortalAuth, Depends(_portal_auth)], session: Annotated[AsyncSession, Depends(get_session)]):
    if run_id not in auth.package_run_ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    run = await session.get(ClientPackageRun, run_id)
    if run is None or run.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    reqs = (await session.execute(select(PackageRequirement).where(PackageRequirement.package_run_id == run_id))).scalars().all()
    events = (await session.execute(select(PackageEvent).where(PackageEvent.package_run_id == run_id))).scalars().all()
    return {
        "run": _serialize_package_run(run),
        "requirements": jsonable_encoder(reqs),
        "events": jsonable_encoder(events),
    }


@router.get("/packages/{run_id}/files", response_model=PortalFilesResponse)
async def portal_package_files(run_id: str, auth: Annotated[PortalAuth, Depends(_portal_auth)], session: Annotated[AsyncSession, Depends(get_session)]):
    if run_id not in auth.package_run_ids or not auth.can_download:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    run = await session.get(ClientPackageRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return {
        "files": [
            {"kind": "zip", "s3_key": run.output_zip_s3_key},
            {"kind": "pdf", "s3_key": run.output_pdf_s3_key},
        ]
    }


@router.post("/packages/{run_id}/tickets", status_code=status.HTTP_201_CREATED)
async def portal_create_ticket(
    run_id: str,
    payload: PackageTicketCreate,
    auth: Annotated[PortalAuth, Depends(_portal_auth)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    if run_id not in auth.package_run_ids or not auth.can_tickets:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    ticket = ClientRequestTicket(
        package_run_id=run_id,
        title=payload.title,
        message=payload.message,
        status=ClientRequestTicketStatus.OPEN,
        created_by="portal-token",
        tenant_id=auth.tenant_id,
    )
    session.add(ticket)
    session.add(
        PackageEvent(
            package_run_id=run_id,
            type="ticket.created",
            payload_json={"title": payload.title},
            tenant_id=auth.tenant_id,
        )
    )
    await session.commit()
    await session.refresh(ticket)
    return ticket


@router.get("/packages/{run_id}/tickets")
async def portal_list_tickets(run_id: str, auth: Annotated[PortalAuth, Depends(_portal_auth)], session: Annotated[AsyncSession, Depends(get_session)]):
    if run_id not in auth.package_run_ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    return (await session.execute(select(ClientRequestTicket).where(ClientRequestTicket.package_run_id == run_id))).scalars().all()
