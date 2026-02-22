from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.idempotency import compute_request_hash
from app.models.job_engine import DocumentJob
from app.models.models import Tenant
from app.modules.pipelines.repo import PipelineProfileRepo
from app.modules.pipelines.schemas import (
    PipelineProfileCreate,
    PipelineProfilePatch,
    PipelineProfileRead,
    PipelineRunAccepted,
    PipelineRunRequest,
)
from app.services.idempotency import IdempotencyService, normalize_idempotency_key
from app.services.pipelines_orchestrator import DocumentPipelineOrchestrator

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


@router.post("/profiles", response_model=PipelineProfileRead, status_code=status.HTTP_201_CREATED)
async def create_profile(payload: PipelineProfileCreate, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> PipelineProfileRead:
    repo = PipelineProfileRepo(session)
    try:
        model = await repo.create(tenant_id=str(tenant.id), payload=payload)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "profile code already exists") from exc
    return PipelineProfileRead.model_validate(model, from_attributes=True)


@router.get("/profiles", response_model=list[PipelineProfileRead])
async def list_profiles(active: bool | None = None, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> list[PipelineProfileRead]:
    rows = await PipelineProfileRepo(session).list(tenant_id=str(tenant.id), active=active)
    return [PipelineProfileRead.model_validate(r, from_attributes=True) for r in rows]


@router.get("/profiles/{profile_id}", response_model=PipelineProfileRead)
async def get_profile(profile_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> PipelineProfileRead:
    model = await PipelineProfileRepo(session).get(tenant_id=str(tenant.id), profile_id=profile_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
    return PipelineProfileRead.model_validate(model, from_attributes=True)


@router.patch("/profiles/{profile_id}", response_model=PipelineProfileRead)
async def patch_profile(profile_id: str, payload: PipelineProfilePatch, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> PipelineProfileRead:
    repo = PipelineProfileRepo(session)
    model = await repo.get(tenant_id=str(tenant.id), profile_id=profile_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
    await repo.patch(model=model, payload=payload)
    await session.commit()
    return PipelineProfileRead.model_validate(model, from_attributes=True)


@router.delete("/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(profile_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> Response:
    repo = PipelineProfileRepo(session)
    model = await repo.get(tenant_id=str(tenant.id), profile_id=profile_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
    active_job = (
        await session.execute(select(DocumentJob).where(DocumentJob.tenant_id == str(tenant.id), DocumentJob.profile_id == profile_id, DocumentJob.status.in_(["queued", "running"])))
    ).scalar_one_or_none()
    if active_job:
        raise HTTPException(status.HTTP_409_CONFLICT, "profile has active jobs")
    await repo.soft_delete(model=model)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/run", response_model=PipelineRunAccepted, status_code=status.HTTP_202_ACCEPTED)
async def run_pipeline(
    payload: PipelineRunRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> PipelineRunAccepted:
    profile = await PipelineProfileRepo(session).get_by_code(tenant_id=str(tenant.id), code=payload.profile_code)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")

    request_hash = compute_request_hash(payload.model_dump())
    idem_service = IdempotencyService(session=session, tenant_id=str(tenant.id), endpoint="pipelines.run")
    idem_key = normalize_idempotency_key(idempotency_key)
    record, created = await idem_service.acquire(key=idem_key, request_hash=request_hash, method="POST", path="/v1/pipelines/run")
    if not created:
        return await idem_service.respond_from_store(record, model=PipelineRunAccepted, response=response)

    orchestrator = DocumentPipelineOrchestrator(session)
    job = await orchestrator.start_document_job(
        tenant_id=str(tenant.id),
        created_by=None,
        payload={"template_code": payload.profile_code, "template_version": 1, "pipeline_profile_id": profile.id, "input": payload.input, "options": payload.overrides or {}},
        idempotency_key=idem_key,
        request_hash=request_hash,
    )
    job.profile_id = profile.id
    job.input = payload.input
    await session.flush()
    accepted = PipelineRunAccepted(job_id=job.id, status_url=f"/v1/jobs/{job.id}", ws_channel=f"jobs:{tenant.id}:{job.id}")
    await idem_service.store_success(record, status_code=status.HTTP_202_ACCEPTED, body=accepted.model_dump())
    await session.commit()
    return accepted
