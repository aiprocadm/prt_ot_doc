"""Document generation API endpoints."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.payload_constraints import PayloadConstraintError, enforce_mapping_constraints
from app.core.idempotency import compute_request_hash
from app.core.tracing import get_trace_id
from app.core.security import AccessContext, abac, rbac
from app.models.models import (
    Company,
    Person,
    PipelineRun,
    PipelineRunStatus,
    Template,
    TemplateVersion,
    TemplateVersionStatus,
    Tenant,
    User,
)
from app.schemas.document import DocumentRead, DocumentStatusUpdate
from app.schemas.task import TaskAcceptedResponse, TaskStatusResponse
from app.services.audit import AuditService
from app.services.documents import (
    DocumentNotFoundError,
    DocumentWorkflowService,
    InvalidStatusTransitionError,
)
from app.services.idempotency import IdempotencyService, normalize_idempotency_key
from app.tasks import generate_document_task

router = APIRouter()

SessionDep = Depends(get_session)
TenantDep = Depends(get_tenant_record)


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> UUID | None:
    return getattr(tenant, "id", None)


_DOCUMENT_RUN_ROLES = ["admin", "employee", "client_admin"]
_DOCUMENT_STATUS_ROLES = ["admin"]

AccessDep = Depends(
    abac(
        _tenant_resource_id,
        required_roles=_DOCUMENT_RUN_ROLES,
        action="manage documents",
    )
)
StatusAccessDep = Depends(rbac(_DOCUMENT_STATUS_ROLES))


class DocGenerateRequest(BaseModel):
    """Incoming payload for document generation requests."""

    model_config = ConfigDict(extra="forbid")

    template_code: str | None = Field(default=None, min_length=1, max_length=255)
    template_id: str | None = Field(default=None, min_length=1)
    company_id: str = Field(..., min_length=1)
    person_id: str | None = Field(default=None)
    data: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _ensure_identifier(self) -> "DocGenerateRequest":
        if not self.template_code and not self.template_id:
            raise ValueError("Either template_id or template_code must be provided")
        return self

def _serialize_payload(payload: dict[str, Any]) -> str:
    try:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "data must be JSON serializable") from exc


def _hash_payload(payload: dict[str, Any]) -> str:
    serialized = _serialize_payload(payload)
    digest = hashlib.sha256(serialized.encode("utf-8"))
    return digest.hexdigest()


async def _fetch_template(
    session: AsyncSession,
    tenant: Tenant,
    *,
    template_code: str | None = None,
    template_id: str | None = None,
) -> tuple[Template, TemplateVersion]:
    tenant_slug = tenant.slug
    filters: list[Any] = [
        Template.tenant_id == tenant_slug,
        TemplateVersion.tenant_id == tenant_slug,
        TemplateVersion.status == TemplateVersionStatus.ACTIVE,
    ]
    if template_id:
        filters.append(Template.id == template_id)
    if template_code:
        filters.append(Template.name == template_code)
    if len(filters) == 2:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "template_id or template_code must be provided",
        )

    stmt = (
        select(Template, TemplateVersion)
        .join(TemplateVersion, TemplateVersion.template_id == Template.id)
        .where(*filters)
        .order_by(TemplateVersion.version.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")
    return row


async def _ensure_company(session: AsyncSession, tenant: Tenant, company_id: str) -> Company:
    company = await session.get(Company, company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    if str(company.tenant_id) != str(tenant.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant mismatch for company resource")
    return company


async def _ensure_person(
    session: AsyncSession, person_id: str | None, company: Company
) -> Person | None:
    if person_id is None:
        return None
    person = await session.get(Person, person_id)
    if person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Person not found")
    if person.company_id != company.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "person_id does not belong to the provided company",
        )
    return person


async def _resolve_run(
    session: AsyncSession,
    *,
    idempotency_key: str,
    tenant: Tenant,
    template: Template,
    template_version: TemplateVersion,
    company: Company,
    person: Person | None,
    payload_hash: str,
    current_user: User,
    context: dict[str, Any],
) -> tuple[PipelineRun, bool]:
    stmt = select(PipelineRun).where(
        PipelineRun.tenant_id == tenant.id,
        PipelineRun.idempotency_key == idempotency_key,
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        metadata = existing.result_metadata or {}
        if existing.template_id != template.id:
            raise HTTPException(status.HTTP_409_CONFLICT, "Idempotency key already used")
        if existing.template_version_id != template_version.id:
            raise HTTPException(status.HTTP_409_CONFLICT, "Idempotency key already used")
        if metadata.get("company_id") != company.id:
            raise HTTPException(status.HTTP_409_CONFLICT, "Idempotency key already used")
        expected_person = person.id if person else None
        if metadata.get("person_id") != expected_person:
            raise HTTPException(status.HTTP_409_CONFLICT, "Idempotency key already used")
        if metadata.get("payload_hash") != payload_hash:
            raise HTTPException(status.HTTP_409_CONFLICT, "Idempotency key already used")
        if existing.context != context:
            raise HTTPException(status.HTTP_409_CONFLICT, "Idempotency key already used")
        if existing.status is PipelineRunStatus.ERROR:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Idempotency key refers to a failed generation task",
            )
        return existing, False

    run = PipelineRun(
        tenant_id=tenant.id,
        template_id=template.id,
        template_version_id=template_version.id,
        status=PipelineRunStatus.QUEUED,
        context=dict(context),
        idempotency_key=idempotency_key,
        result_metadata={
            "company_id": company.id,
            "person_id": person.id if person else None,
            "initiated_by": current_user.id,
            "payload_hash": payload_hash,
        },
    )
    session.add(run)
    await session.flush()
    return run, True


@router.post(
    "/generate",
    response_model=TaskAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_document(
    payload: DocGenerateRequest,
    request: Request,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    access: AccessContext = AccessDep,
) -> TaskAcceptedResponse:
    try:
        enforce_mapping_constraints(payload.data, field="data")
    except PayloadConstraintError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc

    normalized_key = normalize_idempotency_key(idempotency_key)
    idem_state = getattr(request.state, "idempotency", {})
    request_hash = idem_state.get("fingerprint")
    if request_hash is None:
        request_hash = compute_request_hash(payload)
        idem_state = {"key": normalized_key, "fingerprint": request_hash}
        request.state.idempotency = idem_state
    idempotency = IdempotencyService(
        session=session,
        tenant_id=str(tenant.id),
        endpoint="documents.generate",
    )
    record, created_record = await idempotency.acquire(
        key=normalized_key,
        request_hash=request_hash,
        method=request.method.upper(),
        path=request.url.path,
    )

    created_run = False
    try:
        payload_hash = _hash_payload(payload.data)

        template, template_version = await _fetch_template(
            session,
            tenant,
            template_code=payload.template_code,
            template_id=payload.template_id,
        )
        company = await _ensure_company(session, tenant, payload.company_id)
        person = await _ensure_person(session, payload.person_id, company)
        current_user: User = access.user
        if access.role in {"client_admin", "client_user"}:
            access.ensure_company_access(company.id, action="generate documents")

        run, created_run = await _resolve_run(
            session,
            idempotency_key=normalized_key,
            tenant=tenant,
            template=template,
            template_version=template_version,
            company=company,
            person=person,
            payload_hash=payload_hash,
            current_user=current_user,
            context=payload.data,
        )

        if created_run:
            audit_service = AuditService(session)
            ip = request.client.host if request.client else "unknown"
            await audit_service.log_event(
                tenant_id=str(tenant.id),
                action="render_start",
                object_type="pipeline_run",
                object_id=run.id,
                user_id=current_user.id,
                ip=ip,
                details={
                    "template_id": template.id,
                    "company_id": company.id,
                    "person_id": person.id if person else None,
                },
            )

        if not created_record:
            await session.commit()
            return await idempotency.respond_from_store(
                record, model=TaskAcceptedResponse, response=response
            )

        status_url = f"/api/v1/documents/tasks/{run.id}"
        result = TaskAcceptedResponse(task_id=run.id, status_url=status_url)
        await idempotency.store_success(
            record,
            status_code=status.HTTP_202_ACCEPTED,
            body=result.model_dump(mode="json"),
        )
        await session.commit()
    except HTTPException as exc:
        await idempotency.store_failure(
            record,
            status_code=exc.status_code,
            detail={"detail": exc.detail},
        )
        await session.commit()
        raise
    except Exception as exc:
        await idempotency.store_failure(
            record,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"detail": str(exc)},
        )
        await session.commit()
        raise

    if created_run:
        try:
            trace_id = get_trace_id()
            generate_document_task.apply_async(
                args=[run.id],
                kwargs={"tenant_slug": tenant.slug},
                task_id=run.id,
                headers={"trace_id": trace_id},
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            stored = await idempotency.get(key=normalized_key)
            if stored is not None:
                await idempotency.store_failure(
                    stored,
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={"detail": str(exc)},
                )
                await session.commit()
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc)) from exc

    response.status_code = status.HTTP_202_ACCEPTED
    return result


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_generation_task_status(
    task_id: str,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    access: AccessContext = AccessDep,
) -> TaskStatusResponse:
    stmt = select(PipelineRun).where(
        PipelineRun.id == task_id,
        PipelineRun.tenant_id == tenant.id,
    )
    run = (await session.execute(stmt)).scalar_one_or_none()
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")

    metadata = dict(run.result_metadata or {})
    outputs = dict(run.outputs or {})
    if outputs:
        metadata.setdefault("outputs", outputs)

    pipeline_status = (
        run.status.value if hasattr(run.status, "value") else str(run.status)
    )
    metadata.setdefault("pipeline_status", pipeline_status)

    document_id = metadata.get("document_id") or outputs.get("document_id")

    return TaskStatusResponse(
        task_id=run.id,
        status=pipeline_status,
        document_id=document_id,
        error=run.error,
        metadata=metadata or None,
    )


@router.patch("/{document_id}/status", response_model=DocumentRead)
async def update_document_status(
    document_id: str,
    payload: DocumentStatusUpdate,
    request: Request,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    access: AccessContext = StatusAccessDep,
) -> DocumentRead:
    access.ensure_tenant_access(tenant.id, action="manage document status")
    service = DocumentWorkflowService(session=session)
    actor_id = getattr(access.user, "id", None)
    ip = request.client.host if request.client else "unknown"
    try:
        document = await service.change_status(
            document_id=document_id,
            tenant_id=str(tenant.id),
            new_status=payload.to,
            actor_id=actor_id,
            ip=ip,
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except InvalidStatusTransitionError as exc:
        await session.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    await session.commit()
    await session.refresh(document)
    return DocumentRead.model_validate(document)
