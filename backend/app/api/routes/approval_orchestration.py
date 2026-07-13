from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.api.deps.tracing import get_trace_id
from app.core.audit_decorator import audit_operation
from app.core.config import get_settings
from app.core.errors import api_problem_detail
from app.core.inbound_webhook_auth import verify_inbound_webhook_body_hmac
from app.core.security import AccessContext, abac
from app.models.document import DocumentVersion
from app.models.models import PackRun, Tenant
from app.models.workflow import (
    ApprovalDecision,
    ApprovalInstance,
    ApprovalRoute,
    ApprovalRouteStep,
    EdoMessage,
    EdoStatusEvent,
    EdoWebhookInbox,
    SignatureRequest,
)
from app.modules.approvals.service import ApprovalDecisionService, ApprovalInstanceService
from app.modules.edo.service import EdoStatusProjectionService, EdoWebhookService
from app.services.pep_signing import (
    PepApprovalRequired,
    PepConflict,
    PepNotFound,
    PepSigningService,
)
from app.services.provider_registry import provider_response_meta

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    value = getattr(tenant, "id", None)
    return str(value) if value is not None else None


_APPROVAL_ORCH_READ_ROLES = ["admin", "employee"]
_APPROVAL_ORCH_WRITE_ROLES = ["admin", "employee"]


ReaderAccess = Annotated[
    AccessContext,
    Depends(
        abac(
            _tenant_resource_id,
            required_roles=_APPROVAL_ORCH_READ_ROLES,
            action="read approval orchestration",
        )
    ),
]
EditorAccess = Annotated[
    AccessContext,
    Depends(
        abac(
            _tenant_resource_id,
            required_roles=_APPROVAL_ORCH_WRITE_ROLES,
            action="manage approval orchestration",
        )
    ),
]


def _approval_orchestration_unprocessable(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=api_problem_detail(
            code="APPROVAL_ORCHESTRATION_VALIDATION_ERROR",
            message=message,
            error_type="approvals",
        ),
    )


def _provider_not_configured(kind: str) -> HTTPException:
    """Честный отказ вместо симуляции: внешний провайдер не настроен (Срез-1).

    Codes: EDO_PROVIDER_NOT_CONFIGURED | SIGNATURE_PROVIDER_NOT_CONFIGURED
    """
    code = f"{kind.upper()}_PROVIDER_NOT_CONFIGURED"
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=api_problem_detail(
            code=code,
            message=f"{kind} provider is not configured",
            error_type="approvals",
        ),
    )


def _approval_orchestration_not_found(resource: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=api_problem_detail(
            code="APPROVAL_ORCHESTRATION_NOT_FOUND",
            message=f"{resource} not found",
            details={"resource": resource},
            error_type="approvals",
        ),
    )


def _correlation_id(request: Request, response: Response) -> str:
    value = get_trace_id(request)
    response.headers["X-Trace-Id"] = value
    response.headers["X-Correlation-Id"] = value
    response.headers["X-Request-Id"] = value
    return value


class ApprovalRouteCreate(BaseModel):
    code: str
    name: str
    description: str | None = None
    applies_to: str = "document"
    conditions_json: dict[str, Any] = Field(default_factory=dict)
    is_default: bool = False
    status: str = "draft"


class ApprovalRouteStepCreate(BaseModel):
    order_no: int
    step_type: str = "approve"
    role_code: str | None = None
    user_id: str | None = None
    can_delegate: bool = True
    deadline_hours: int | None = None
    escalation_role_code: str | None = None
    escalation_user_id: str | None = None
    conditions_json: dict[str, Any] | None = None


class ApprovalStartIn(BaseModel):
    entity_type: str
    entity_id: str
    approval_route_id: str


class ApprovalActionIn(BaseModel):
    comment: str | None = None
    target_user_id: str | None = None


class SignatureRequestIn(BaseModel):
    entity_type: str
    entity_id: str
    signature_type: str
    provider_code: str = "internal-fallback"
    options: dict[str, Any] = Field(default_factory=dict)
    approval_instance_id: str | None = None


class EdoMessageIn(BaseModel):
    entity_type: str
    entity_id: str
    operator_code: str = "internal-fallback"
    message_type: str = "document_package"


def _tenant_id_value(tenant: Tenant) -> str:
    return str(tenant.id)


async def _get_document_for_tenant(
    session: AsyncSession, tenant_id: str, document_version_id: str
) -> DocumentVersion | None:
    row = await session.get(DocumentVersion, document_version_id)
    if row is None or str(row.tenant_id) != tenant_id:
        return None
    return row


async def _get_pack_for_tenant(
    session: AsyncSession, tenant_id: str, pack_id: str
) -> PackRun | None:
    row = await session.get(PackRun, pack_id)
    if row is None or str(row.tenant_id) != tenant_id:
        return None
    return row


async def _assert_entity_belongs_to_tenant(
    *,
    session: AsyncSession,
    tenant_id: str,
    entity_type: str,
    entity_id: str,
) -> None:
    if entity_type == "document":
        if await _get_document_for_tenant(session, tenant_id, entity_id) is None:
            raise _approval_orchestration_not_found("document_version")
    elif entity_type == "pack":
        if await _get_pack_for_tenant(session, tenant_id, entity_id) is None:
            raise _approval_orchestration_not_found("pack_run")


@router.post("/approval-routes")
@audit_operation("create", "approval_route")
async def create_approval_route(
    payload: ApprovalRouteCreate,
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
):
    cid = _correlation_id(request, response)
    row = ApprovalRoute(tenant_id=_tenant_id_value(tenant), **payload.model_dump())
    session.add(row)
    await session.flush()
    return {"id": row.id, "correlation_id": cid}


@router.get("/approval-routes")
async def list_approval_routes(session: SessionDep, tenant: TenantDep, _: ReaderAccess):
    rows = (
        (
            await session.execute(
                select(ApprovalRoute).where(ApprovalRoute.tenant_id == _tenant_id_value(tenant))
            )
        )
        .scalars()
        .all()
    )
    return {"items": rows}


@router.get("/approval-routes/{route_id}")
async def get_approval_route(
    route_id: str, session: SessionDep, tenant: TenantDep, _: ReaderAccess
):
    row = await session.get(ApprovalRoute, route_id)
    if not row or row.tenant_id != _tenant_id_value(tenant):
        raise _approval_orchestration_not_found("approval_route")
    return row


@router.patch("/approval-routes/{route_id}")
@audit_operation("update", "approval_route")
async def patch_approval_route(
    route_id: str,
    payload: ApprovalRouteCreate,
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
):
    cid = _correlation_id(request, response)
    row = await session.get(ApprovalRoute, route_id)
    if not row or row.tenant_id != _tenant_id_value(tenant):
        raise _approval_orchestration_not_found("approval_route")
    for k, v in payload.model_dump().items():
        setattr(row, k, v)
    await session.flush()
    return {"id": row.id, "correlation_id": cid}


@router.delete("/approval-routes/{route_id}")
@audit_operation("delete", "approval_route")
async def delete_approval_route(
    route_id: str,
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
):
    cid = _correlation_id(request, response)
    row = await session.get(ApprovalRoute, route_id)
    if not row or row.tenant_id != _tenant_id_value(tenant):
        raise _approval_orchestration_not_found("approval_route")
    await session.delete(row)
    return {"ok": True, "correlation_id": cid}


@router.post("/approval-routes/{route_id}/steps")
@audit_operation("create", "approval_route_step")
async def create_approval_route_step(
    route_id: str,
    payload: ApprovalRouteStepCreate,
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
):
    cid = _correlation_id(request, response)
    route = await session.get(ApprovalRoute, route_id)
    if route is None or route.tenant_id != _tenant_id_value(tenant):
        raise _approval_orchestration_not_found("approval_route")
    row = ApprovalRouteStep(
        tenant_id=_tenant_id_value(tenant), approval_route_id=route_id, **payload.model_dump()
    )
    session.add(row)
    await session.flush()
    return {"id": row.id, "correlation_id": cid}


@router.patch("/approval-routes/{route_id}/steps/{step_id}")
@audit_operation("update", "approval_route_step")
async def patch_approval_route_step(
    route_id: str,
    step_id: str,
    payload: ApprovalRouteStepCreate,
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
):
    cid = _correlation_id(request, response)
    row = await session.get(ApprovalRouteStep, step_id)
    if not row or row.tenant_id != _tenant_id_value(tenant) or row.approval_route_id != route_id:
        raise _approval_orchestration_not_found("approval_route_step")
    for k, v in payload.model_dump().items():
        setattr(row, k, v)
    await session.flush()
    return {"id": row.id, "correlation_id": cid}


@router.delete("/approval-routes/{route_id}/steps/{step_id}")
@audit_operation("delete", "approval_route_step")
async def delete_approval_route_step(
    route_id: str,
    step_id: str,
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
):
    cid = _correlation_id(request, response)
    row = await session.get(ApprovalRouteStep, step_id)
    if not row or row.tenant_id != _tenant_id_value(tenant) or row.approval_route_id != route_id:
        raise _approval_orchestration_not_found("approval_route_step")
    await session.delete(row)
    return {"ok": True, "correlation_id": cid}


@router.post("/approvals/start")
@audit_operation("start", "approval_instance")
async def start_approval(
    payload: ApprovalStartIn,
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
    x_user_id: str = Header(default="system", alias="X-User-Id"),
):
    cid = _correlation_id(request, response)
    tenant_id = _tenant_id_value(tenant)
    await _assert_entity_belongs_to_tenant(
        session=session,
        tenant_id=tenant_id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
    )
    service = ApprovalInstanceService(session, tenant_id)
    instance = await service.start(**payload.model_dump(), started_by=x_user_id)
    if payload.entity_type == "document":
        dv = await _get_document_for_tenant(session, tenant_id, payload.entity_id)
        if dv is not None:
            # Core UPDATE — обходит before_update гард иммутабельности DocumentVersion.
            await session.execute(
                update(DocumentVersion)
                .where(DocumentVersion.id == payload.entity_id)
                .values(approval_status="running")
                .execution_options(synchronize_session="evaluate")
            )
    if payload.entity_type == "pack":
        run = await _get_pack_for_tenant(session, tenant_id, payload.entity_id)
        if run is not None:
            run.approval_status = "running"
    return {"id": instance.id, "status": instance.status, "correlation_id": cid}


@router.get("/approvals")
async def list_approvals(session: SessionDep, tenant: TenantDep, _: ReaderAccess):
    rows = (
        (
            await session.execute(
                select(ApprovalInstance).where(
                    ApprovalInstance.tenant_id == _tenant_id_value(tenant)
                )
            )
        )
        .scalars()
        .all()
    )
    return {"items": rows}


@router.get("/approvals/{approval_id}")
async def get_approval(approval_id: str, session: SessionDep, tenant: TenantDep, _: ReaderAccess):
    row = await session.get(ApprovalInstance, approval_id)
    if not row or row.tenant_id != _tenant_id_value(tenant):
        raise _approval_orchestration_not_found("approval_instance")
    return row


@router.get("/approvals/{approval_id}/timeline")
async def approval_timeline(
    approval_id: str, session: SessionDep, tenant: TenantDep, _: ReaderAccess
):
    decisions = (
        (
            await session.execute(
                select(ApprovalDecision)
                .where(
                    ApprovalDecision.approval_instance_id == approval_id,
                    ApprovalDecision.tenant_id == _tenant_id_value(tenant),
                )
                .order_by(ApprovalDecision.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return {"items": decisions}


async def _act(
    approval_id: str,
    action: str,
    payload: ApprovalActionIn,
    session: AsyncSession,
    tenant_id: str,
    actor: str,
    correlation_id: str,
):
    current = await session.get(ApprovalInstance, approval_id)
    if current is None or current.tenant_id != tenant_id:
        raise _approval_orchestration_not_found("approval_instance")
    service = ApprovalDecisionService(session, tenant_id)
    instance = await service.decide(
        instance_id=approval_id,
        actor_user_id=actor,
        decision=action,
        comment=payload.comment,
        target_user_id=payload.target_user_id,
    )
    if instance.entity_type == "document":
        dv = await _get_document_for_tenant(session, tenant_id, instance.entity_id)
        if dv is not None:
            # Core UPDATE — обходит before_update гард иммутабельности DocumentVersion.
            await session.execute(
                update(DocumentVersion)
                .where(DocumentVersion.id == instance.entity_id)
                .values(approval_status=instance.status.value)
                .execution_options(synchronize_session="evaluate")
            )
    if instance.entity_type == "pack":
        run = await _get_pack_for_tenant(session, tenant_id, instance.entity_id)
        if run is not None:
            run.approval_status = instance.status.value
    return {"id": instance.id, "status": instance.status, "correlation_id": correlation_id}


@router.post("/approvals/{approval_id}/approve")
@audit_operation("approve", "approval_instance")
async def approval_approve(
    approval_id: str,
    payload: ApprovalActionIn,
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
    x_user_id: str = Header(default="system", alias="X-User-Id"),
):
    cid = _correlation_id(request, response)
    return await _act(
        approval_id, "approve", payload, session, _tenant_id_value(tenant), x_user_id, cid
    )


@router.post("/approvals/{approval_id}/reject")
@audit_operation("reject", "approval_instance")
async def approval_reject(
    approval_id: str,
    payload: ApprovalActionIn,
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
    x_user_id: str = Header(default="system", alias="X-User-Id"),
):
    cid = _correlation_id(request, response)
    return await _act(
        approval_id, "reject", payload, session, _tenant_id_value(tenant), x_user_id, cid
    )


@router.post("/approvals/{approval_id}/delegate")
@audit_operation("delegate", "approval_instance")
async def approval_delegate(
    approval_id: str,
    payload: ApprovalActionIn,
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
    x_user_id: str = Header(default="system", alias="X-User-Id"),
):
    cid = _correlation_id(request, response)
    return await _act(
        approval_id, "delegate", payload, session, _tenant_id_value(tenant), x_user_id, cid
    )


@router.post("/approvals/{approval_id}/comment")
@audit_operation("comment", "approval_instance")
async def approval_comment(
    approval_id: str,
    payload: ApprovalActionIn,
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
    x_user_id: str = Header(default="system", alias="X-User-Id"),
):
    cid = _correlation_id(request, response)
    return await _act(
        approval_id, "comment", payload, session, _tenant_id_value(tenant), x_user_id, cid
    )


@router.post("/approvals/{approval_id}/cancel")
@audit_operation("cancel", "approval_instance")
async def approval_cancel(
    approval_id: str,
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
):
    cid = _correlation_id(request, response)
    row = await session.get(ApprovalInstance, approval_id)
    if not row or row.tenant_id != _tenant_id_value(tenant):
        raise _approval_orchestration_not_found("approval_instance")
    row.status = "canceled"
    return {"id": row.id, "status": row.status, "correlation_id": cid}


@router.post("/sign/requests")
@audit_operation("create", "signature_request")
async def create_sign_request(
    payload: SignatureRequestIn,
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
    x_user_id: str = Header(default="system", alias="X-User-Id"),
):
    # Side effect: stamps X-Trace-Id / X-Correlation-Id / X-Request-Id on the
    # response so the always-raised error carries tracing headers. The returned
    # id and tenant id are unused here (this endpoint only ever rejects).
    _correlation_id(request, response)
    # ПЭП-запросы создаются через /sign/pep/requests — не через этот роутер.
    if payload.signature_type == "pep":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_problem_detail(
                code="PEP_CONFLICT",
                message="use /sign/pep/requests for internal PEP signing",
                error_type="approvals",
            ),
        )
    # Внешние провайдеры подписи (KEP/UNEP/МЧД и любые неизвестные типы) не сконфигурированы.
    raise _provider_not_configured("signature")


@router.get("/sign/requests")
async def list_sign_requests(session: SessionDep, tenant: TenantDep, _: ReaderAccess):
    rows = (
        (
            await session.execute(
                select(SignatureRequest).where(
                    SignatureRequest.tenant_id == _tenant_id_value(tenant)
                )
            )
        )
        .scalars()
        .all()
    )
    return {
        "items": [
            {
                "id": row.id,
                "status": row.status,
                "provider": row.provider,
                **provider_response_meta(getattr(row, "provider_code", row.provider)),
            }
            for row in rows
        ]
    }


@router.get("/sign/requests/{request_id}")
async def get_sign_request(
    request_id: str, session: SessionDep, tenant: TenantDep, _: ReaderAccess
):
    row = await session.get(SignatureRequest, request_id)
    if not row or row.tenant_id != _tenant_id_value(tenant):
        raise _approval_orchestration_not_found("signature_request")
    return {
        "id": row.id,
        "status": row.status,
        "provider": row.provider,
        **provider_response_meta(getattr(row, "provider_code", row.provider)),
    }


@router.post("/sign/requests/{request_id}/cancel")
@audit_operation("cancel", "signature_request")
async def cancel_sign_request(
    request_id: str,
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
):
    cid = _correlation_id(request, response)
    row = await session.get(SignatureRequest, request_id)
    if not row or row.tenant_id != _tenant_id_value(tenant):
        raise _approval_orchestration_not_found("signature_request")
    if getattr(row, "signature_type", None) == "pep":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_problem_detail(
                code="PEP_CONFLICT",
                message="pep requests are managed via /sign/pep (decline)",
                error_type="approvals",
            ),
        )
    row.status = "canceled"
    return {"id": row.id, "status": row.status, "correlation_id": cid}


@router.post("/sign/requests/{request_id}/refresh-status")
@audit_operation("refresh_status", "signature_request")
async def refresh_sign_status(
    request_id: str,
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
):
    cid = _correlation_id(request, response)
    row = await session.get(SignatureRequest, request_id)
    if not row or row.tenant_id != _tenant_id_value(tenant):
        raise _approval_orchestration_not_found("signature_request")
    if getattr(row, "signature_type", None) != "pep":
        # Внешние провайдеры подписи не сконфигурированы.
        raise _provider_not_configured("signature")
    # ПЭП: нет внешнего провайдера — возвращаем текущий статус без изменений.
    return {"id": row.id, "status": row.status, "correlation_id": cid}


@router.post("/sign/requests/{request_id}/verify")
@audit_operation("verify", "signature_request")
async def verify_sign_request(
    request_id: str,
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
):
    cid = _correlation_id(request, response)
    row = await session.get(SignatureRequest, request_id)
    if not row or row.tenant_id != _tenant_id_value(tenant):
        raise _approval_orchestration_not_found("signature_request")
    if getattr(row, "signature_type", None) != "pep":
        raise _provider_not_configured("signature")
    # ПЭП: делегируем в PepSigningService.verify (пересчёт hash + протокол).
    tenant_id = _tenant_id_value(tenant)
    try:
        protocol = await PepSigningService(session, tenant_id).verify(request_id)
    except PepNotFound:
        raise _approval_orchestration_not_found("signature_request")
    except PepConflict as exc:
        # PepApprovalRequired (гейт согласования) — отдельный код; прочее — PEP_CONFLICT.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_problem_detail(
                code=(
                    "PEP_APPROVAL_REQUIRED"
                    if isinstance(exc, PepApprovalRequired)
                    else "PEP_CONFLICT"
                ),
                message=str(exc),
                error_type="approvals",
            ),
        ) from exc
    await session.commit()
    return {
        "id": row.id,
        "status": row.status,
        "verification_result": protocol,
        "correlation_id": cid,
    }


@router.post("/edo/messages")
@audit_operation("create", "edo_message")
async def create_edo_message(
    payload: EdoMessageIn,
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
    x_user_id: str = Header(default="system", alias="X-User-Id"),
):
    cid = _correlation_id(request, response)
    tenant_id = _tenant_id_value(tenant)
    await _assert_entity_belongs_to_tenant(
        session=session,
        tenant_id=tenant_id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
    )
    row = EdoMessage(
        tenant_id=tenant_id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        operator_code=payload.operator_code,
        provider_code=payload.operator_code,
        message_type=payload.message_type,
        direction="outgoing",
        status="queued",
        created_by=x_user_id,
    )
    session.add(row)
    await session.flush()
    return {
        "id": row.id,
        "status": row.status,
        "correlation_id": cid,
        **provider_response_meta(payload.operator_code),
    }


@router.get("/edo/messages")
async def list_edo_messages(session: SessionDep, tenant: TenantDep, _: ReaderAccess):
    rows = (
        (
            await session.execute(
                select(EdoMessage).where(EdoMessage.tenant_id == _tenant_id_value(tenant))
            )
        )
        .scalars()
        .all()
    )
    return {
        "items": [
            {
                "id": row.id,
                "status": row.status,
                "operator_code": row.operator_code,
                **provider_response_meta(getattr(row, "provider_code", row.operator_code)),
            }
            for row in rows
        ]
    }


@router.get("/edo/messages/{message_id}")
async def get_edo_message(message_id: str, session: SessionDep, tenant: TenantDep, _: ReaderAccess):
    row = await session.get(EdoMessage, message_id)
    if not row or row.tenant_id != _tenant_id_value(tenant):
        raise _approval_orchestration_not_found("edo_message")
    return {
        "id": row.id,
        "status": row.status,
        "operator_code": row.operator_code,
        **provider_response_meta(getattr(row, "provider_code", row.operator_code)),
    }


@router.get("/edo/messages/{message_id}/events")
async def list_edo_events(message_id: str, session: SessionDep, tenant: TenantDep, _: ReaderAccess):
    rows = (
        (
            await session.execute(
                select(EdoStatusEvent).where(
                    EdoStatusEvent.edo_message_id == message_id,
                    EdoStatusEvent.tenant_id == _tenant_id_value(tenant),
                )
            )
        )
        .scalars()
        .all()
    )
    return {"items": rows}


@router.post("/edo/messages/{message_id}/refresh-status")
@audit_operation("refresh_status", "edo_message")
async def refresh_edo_status(
    message_id: str,
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
):
    _correlation_id(request, response)
    row = await session.get(EdoMessage, message_id)
    if not row or row.tenant_id != _tenant_id_value(tenant):
        raise _approval_orchestration_not_found("edo_message")
    raise _provider_not_configured("edo")


@router.post("/edo/messages/{message_id}/cancel")
@audit_operation("cancel", "edo_message")
async def cancel_edo(
    message_id: str,
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
):
    cid = _correlation_id(request, response)
    row = await session.get(EdoMessage, message_id)
    if not row or row.tenant_id != _tenant_id_value(tenant):
        raise _approval_orchestration_not_found("edo_message")
    row.status = "failed"
    return {"id": row.id, "status": row.status, "correlation_id": cid}


@router.get("/edo/messages/{message_id}/protocol")
async def get_edo_protocol(
    message_id: str, session: SessionDep, tenant: TenantDep, _: ReaderAccess
):
    row = await session.get(EdoMessage, message_id)
    if not row or row.tenant_id != _tenant_id_value(tenant):
        raise _approval_orchestration_not_found("edo_message")
    return {"message_id": row.id, "protocol": {"status": row.status}}


@router.post("/webhooks/edo/{operator_code}")
@audit_operation("ingest_webhook", "edo_webhook")
async def edo_webhook(
    operator_code: str,
    payload: dict[str, Any],
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
):
    # Inbound machine webhook — authenticate the payload by HMAC (there is no user
    # token). Mirrors webhooks.py /inbound/{source}; enforced when the global
    # INBOUND_WEBHOOK_HMAC_SECRET is configured.
    verify_inbound_webhook_body_hmac(
        settings=get_settings(), raw_body=await request.body(), request=request
    )
    cid = _correlation_id(request, response)
    dedupe_key = (
        request.headers.get("X-Dedupe-Key")
        or payload.get("external_event_id")
        # Stable content hash: builtin hash() is per-process randomized (PYTHONHASHSEED),
        # so identical retried webhooks would produce different keys across workers and
        # bypass dedup. sha256 over a canonical JSON serialization is deterministic.
        or f"{operator_code}:{hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode('utf-8')).hexdigest()}"
    )
    exists = (
        await session.execute(
            select(EdoWebhookInbox).where(EdoWebhookInbox.dedupe_key == dedupe_key)
        )
    ).scalar_one_or_none()
    if exists:
        return {
            "status": "ignored",
            "dedupe_key": dedupe_key,
            "correlation_id": cid,
            **provider_response_meta(operator_code),
        }
    inbox = await EdoWebhookService(session, _tenant_id_value(tenant)).ingest(
        operator_code=operator_code,
        dedupe_key=dedupe_key,
        headers_json=dict(request.headers),
        payload_json=payload,
    )
    message_id = payload.get("message_id")
    if message_id:
        row = await session.get(EdoMessage, message_id)
        if row and row.tenant_id == _tenant_id_value(tenant):
            await EdoStatusProjectionService(session, _tenant_id_value(tenant)).apply_event(
                row, payload.get("status", row.status), payload, dedupe_key
            )
    inbox.status = "processed"
    return {
        "status": "processed",
        "dedupe_key": dedupe_key,
        "correlation_id": cid,
        **provider_response_meta(operator_code),
    }


@router.post("/webhooks/sign/{provider_code}")
@audit_operation("ingest_webhook", "sign_webhook")
async def sign_webhook(
    provider_code: str,
    payload: dict[str, Any],
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
):
    # Inbound machine webhook — authenticate the payload by HMAC before touching
    # signing state (enforced when INBOUND_WEBHOOK_HMAC_SECRET is configured).
    verify_inbound_webhook_body_hmac(
        settings=get_settings(), raw_body=await request.body(), request=request
    )
    cid = _correlation_id(request, response)
    request_id = payload.get("request_id")
    if not request_id:
        raise _approval_orchestration_unprocessable("request_id required")
    row = await session.get(SignatureRequest, request_id)
    if not row or row.tenant_id != _tenant_id_value(tenant):
        raise _approval_orchestration_not_found("signature_request")
    row.status = payload.get("status", row.status)
    return {
        "id": row.id,
        "status": row.status,
        "provider": provider_code,
        "correlation_id": cid,
        **provider_response_meta(provider_code),
    }
