from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.models.document import DocumentVersion
from app.models.models import PackRun
from app.models.workflow import (
    ApprovalDecision,
    ApprovalInstance,
    ApprovalInstanceStep,
    ApprovalRoute,
    ApprovalRouteStep,
    EdoMessage,
    EdoStatusEvent,
    EdoWebhookInbox,
    SignatureRequest,
)
from app.modules.approvals.service import ApprovalDecisionService, ApprovalInstanceService
from app.modules.edo.service import EdoStatusProjectionService, EdoWebhookService
from app.modules.sign.service import SignatureRequestService, SignatureVerificationService
from app.services.provider_registry import provider_response_meta

router = APIRouter()


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
    provider_code: str = "mock"
    options: dict[str, Any] = Field(default_factory=dict)
    approval_instance_id: str | None = None


class EdoMessageIn(BaseModel):
    entity_type: str
    entity_id: str
    operator_code: str = "mock_edo"
    message_type: str = "document_package"


@router.post("/approval-routes")
async def create_approval_route(payload: ApprovalRouteCreate, session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record)):
    row = ApprovalRoute(tenant_id=str(tenant.id), **payload.model_dump())
    session.add(row)
    await session.flush()
    return {"id": row.id}


@router.get("/approval-routes")
async def list_approval_routes(session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record)):
    rows = (await session.execute(select(ApprovalRoute).where(ApprovalRoute.tenant_id == str(tenant.id)))).scalars().all()
    return {"items": rows}


@router.get("/approval-routes/{route_id}")
async def get_approval_route(route_id: str, session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record)):
    row = await session.get(ApprovalRoute, route_id)
    if not row or row.tenant_id != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return row


@router.patch("/approval-routes/{route_id}")
async def patch_approval_route(route_id: str, payload: ApprovalRouteCreate, session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record)):
    row = await session.get(ApprovalRoute, route_id)
    if not row or row.tenant_id != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    for k, v in payload.model_dump().items():
        setattr(row, k, v)
    await session.flush()
    return {"id": row.id}


@router.delete("/approval-routes/{route_id}")
async def delete_approval_route(route_id: str, session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record)):
    row = await session.get(ApprovalRoute, route_id)
    if not row or row.tenant_id != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    await session.delete(row)
    return {"ok": True}


@router.post("/approval-routes/{route_id}/steps")
async def create_approval_route_step(route_id: str, payload: ApprovalRouteStepCreate, session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record)):
    row = ApprovalRouteStep(tenant_id=str(tenant.id), approval_route_id=route_id, **payload.model_dump())
    session.add(row)
    await session.flush()
    return {"id": row.id}


@router.patch("/approval-routes/{route_id}/steps/{step_id}")
async def patch_approval_route_step(route_id: str, step_id: str, payload: ApprovalRouteStepCreate, session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record)):
    row = await session.get(ApprovalRouteStep, step_id)
    if not row or row.tenant_id != str(tenant.id) or row.approval_route_id != route_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    for k, v in payload.model_dump().items():
        setattr(row, k, v)
    await session.flush()
    return {"id": row.id}


@router.delete("/approval-routes/{route_id}/steps/{step_id}")
async def delete_approval_route_step(route_id: str, step_id: str, session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record)):
    row = await session.get(ApprovalRouteStep, step_id)
    if not row or row.tenant_id != str(tenant.id) or row.approval_route_id != route_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    await session.delete(row)
    return {"ok": True}


@router.post("/approvals/start")
async def start_approval(payload: ApprovalStartIn, session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record), x_user_id: str = Header(default="system", alias="X-User-Id")):
    service = ApprovalInstanceService(session, str(tenant.id))
    instance = await service.start(**payload.model_dump(), started_by=x_user_id)
    if payload.entity_type == "document":
        dv = await session.get(DocumentVersion, payload.entity_id)
        if dv is not None:
            dv.approval_status = "running"
    if payload.entity_type == "pack":
        run = await session.get(PackRun, payload.entity_id)
        if run is not None:
            run.approval_status = "running"
    return {"id": instance.id, "status": instance.status}


@router.get("/approvals")
async def list_approvals(session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record)):
    rows = (await session.execute(select(ApprovalInstance).where(ApprovalInstance.tenant_id == str(tenant.id)))).scalars().all()
    return {"items": rows}


@router.get("/approvals/{approval_id}")
async def get_approval(approval_id: str, session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record)):
    row = await session.get(ApprovalInstance, approval_id)
    if not row or row.tenant_id != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return row


@router.get("/approvals/{approval_id}/timeline")
async def approval_timeline(approval_id: str, session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record)):
    decisions = (
        await session.execute(select(ApprovalDecision).where(ApprovalDecision.approval_instance_id == approval_id, ApprovalDecision.tenant_id == str(tenant.id)).order_by(ApprovalDecision.created_at.asc()))
    ).scalars().all()
    return {"items": decisions}


async def _act(approval_id: str, action: str, payload: ApprovalActionIn, session: AsyncSession, tenant_id: str, actor: str):
    service = ApprovalDecisionService(session, tenant_id)
    instance = await service.decide(instance_id=approval_id, actor_user_id=actor, decision=action, comment=payload.comment, target_user_id=payload.target_user_id)
    if instance.entity_type == "document":
        dv = await session.get(DocumentVersion, instance.entity_id)
        if dv is not None:
            dv.approval_status = instance.status.value
    if instance.entity_type == "pack":
        run = await session.get(PackRun, instance.entity_id)
        if run is not None:
            run.approval_status = instance.status.value
    return {"id": instance.id, "status": instance.status}


@router.post("/approvals/{approval_id}/approve")
async def approval_approve(approval_id: str, payload: ApprovalActionIn, session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record), x_user_id: str = Header(default="system", alias="X-User-Id")):
    return await _act(approval_id, "approve", payload, session, str(tenant.id), x_user_id)


@router.post("/approvals/{approval_id}/reject")
async def approval_reject(approval_id: str, payload: ApprovalActionIn, session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record), x_user_id: str = Header(default="system", alias="X-User-Id")):
    return await _act(approval_id, "reject", payload, session, str(tenant.id), x_user_id)


@router.post("/approvals/{approval_id}/delegate")
async def approval_delegate(approval_id: str, payload: ApprovalActionIn, session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record), x_user_id: str = Header(default="system", alias="X-User-Id")):
    return await _act(approval_id, "delegate", payload, session, str(tenant.id), x_user_id)


@router.post("/approvals/{approval_id}/comment")
async def approval_comment(approval_id: str, payload: ApprovalActionIn, session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record), x_user_id: str = Header(default="system", alias="X-User-Id")):
    return await _act(approval_id, "comment", payload, session, str(tenant.id), x_user_id)


@router.post("/approvals/{approval_id}/cancel")
async def approval_cancel(approval_id: str, session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record)):
    row = await session.get(ApprovalInstance, approval_id)
    if not row or row.tenant_id != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    row.status = "canceled"
    return {"id": row.id, "status": row.status}


@router.post("/sign/requests")
async def create_sign_request(payload: SignatureRequestIn, session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record), x_user_id: str = Header(default="system", alias="X-User-Id")):
    req = SignatureRequest(
        tenant_id=str(tenant.id),
        object_type=payload.entity_type,
        object_id=payload.entity_id,
        provider=payload.provider_code,
        provider_code=payload.provider_code,
        signature_type=payload.signature_type,
        payload_json=payload.options,
        requested_by=x_user_id,
        approval_instance_id=payload.approval_instance_id,
    )
    req = await SignatureRequestService(session, str(tenant.id)).create(req)
    return {"id": req.id, "status": req.status, **provider_response_meta(payload.provider_code)}


@router.get("/sign/requests")
async def list_sign_requests(session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record)):
    rows = (await session.execute(select(SignatureRequest).where(SignatureRequest.tenant_id == str(tenant.id)))).scalars().all()
    return {"items": [{"id": row.id, "status": row.status, "provider": row.provider, **provider_response_meta(getattr(row, "provider_code", row.provider))} for row in rows]}


@router.get("/sign/requests/{request_id}")
async def get_sign_request(request_id: str, session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record)):
    row = await session.get(SignatureRequest, request_id)
    if not row or row.tenant_id != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return {"id": row.id, "status": row.status, "provider": row.provider, **provider_response_meta(getattr(row, "provider_code", row.provider))}


@router.post("/sign/requests/{request_id}/cancel")
async def cancel_sign_request(request_id: str, session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record)):
    row = await session.get(SignatureRequest, request_id)
    if not row or row.tenant_id != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    row.status = "canceled"
    return {"id": row.id, "status": row.status}


@router.post("/sign/requests/{request_id}/refresh-status")
async def refresh_sign_status(request_id: str, session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record)):
    row = await session.get(SignatureRequest, request_id)
    if not row or row.tenant_id != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    await SignatureVerificationService(session, str(tenant.id)).refresh(row)
    return {"id": row.id, "status": row.status}


@router.post("/sign/requests/{request_id}/verify")
async def verify_sign_request(request_id: str, session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record)):
    row = await session.get(SignatureRequest, request_id)
    if not row or row.tenant_id != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    await SignatureVerificationService(session, str(tenant.id)).verify(row)
    return {"id": row.id, "status": row.status, "verification_result": row.verification_result_json}


@router.post("/edo/messages")
async def create_edo_message(payload: EdoMessageIn, session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record), x_user_id: str = Header(default="system", alias="X-User-Id")):
    row = EdoMessage(
        tenant_id=str(tenant.id),
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
    return {"id": row.id, "status": row.status, **provider_response_meta(payload.operator_code)}


@router.get("/edo/messages")
async def list_edo_messages(session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record)):
    rows = (await session.execute(select(EdoMessage).where(EdoMessage.tenant_id == str(tenant.id)))).scalars().all()
    return {"items": [{"id": row.id, "status": row.status, "operator_code": row.operator_code, **provider_response_meta(getattr(row, "provider_code", row.operator_code))} for row in rows]}


@router.get("/edo/messages/{message_id}")
async def get_edo_message(message_id: str, session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record)):
    row = await session.get(EdoMessage, message_id)
    if not row or row.tenant_id != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return {"id": row.id, "status": row.status, "operator_code": row.operator_code, **provider_response_meta(getattr(row, "provider_code", row.operator_code))}


@router.get("/edo/messages/{message_id}/events")
async def list_edo_events(message_id: str, session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record)):
    rows = (await session.execute(select(EdoStatusEvent).where(EdoStatusEvent.edo_message_id == message_id, EdoStatusEvent.tenant_id == str(tenant.id)))).scalars().all()
    return {"items": rows}


@router.post("/edo/messages/{message_id}/refresh-status")
async def refresh_edo_status(message_id: str, session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record)):
    row = await session.get(EdoMessage, message_id)
    if not row or row.tenant_id != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    next_status = "sent" if row.status == "queued" else "delivered"
    await EdoStatusProjectionService(session, str(tenant.id)).apply_event(row, next_status, {"source": "refresh"}, None)
    return {"id": row.id, "status": row.status}


@router.post("/edo/messages/{message_id}/cancel")
async def cancel_edo(message_id: str, session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record)):
    row = await session.get(EdoMessage, message_id)
    if not row or row.tenant_id != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    row.status = "failed"
    return {"id": row.id, "status": row.status}


@router.get("/edo/messages/{message_id}/protocol")
async def get_edo_protocol(message_id: str, session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record)):
    row = await session.get(EdoMessage, message_id)
    if not row or row.tenant_id != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return {"message_id": row.id, "protocol": {"status": row.status}}


@router.post("/webhooks/edo/{operator_code}")
async def edo_webhook(operator_code: str, payload: dict[str, Any], request: Request, session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record)):
    dedupe_key = request.headers.get("X-Dedupe-Key") or payload.get("external_event_id") or f"{operator_code}:{hash(str(payload))}"
    exists = (await session.execute(select(EdoWebhookInbox).where(EdoWebhookInbox.dedupe_key == dedupe_key))).scalar_one_or_none()
    if exists:
        return {"status": "ignored", "dedupe_key": dedupe_key, **provider_response_meta(operator_code)}
    inbox = await EdoWebhookService(session, str(tenant.id)).ingest(operator_code=operator_code, dedupe_key=dedupe_key, headers_json=dict(request.headers), payload_json=payload)
    message_id = payload.get("message_id")
    if message_id:
        row = await session.get(EdoMessage, message_id)
        if row and row.tenant_id == str(tenant.id):
            await EdoStatusProjectionService(session, str(tenant.id)).apply_event(row, payload.get("status", row.status), payload, dedupe_key)
    inbox.status = "processed"
    return {"status": "processed", "dedupe_key": dedupe_key, **provider_response_meta(operator_code)}


@router.post("/webhooks/sign/{provider_code}")
async def sign_webhook(provider_code: str, payload: dict[str, Any], session: AsyncSession = Depends(get_session), tenant=Depends(get_tenant_record)):
    request_id = payload.get("request_id")
    if not request_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "request_id required")
    row = await session.get(SignatureRequest, request_id)
    if not row or row.tenant_id != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    row.status = payload.get("status", row.status)
    return {"id": row.id, "status": row.status, "provider": provider_code, **provider_response_meta(provider_code)}
