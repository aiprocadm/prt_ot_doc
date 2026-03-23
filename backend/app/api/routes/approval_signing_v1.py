from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.models.approval_signing import (
    ApprovalDecisionLog,
    ApprovalProcess,
    ApprovalProcessStatus,
    ApprovalRoute,
    ApprovalTask,
    ApprovalTaskStatus,
    EdoEnvelope,
    EdoEnvelopeStatus,
    SignatureRequest,
    SignatureRequestStatus,
    WebhookEndpoint,
)
from app.models.models import IdempotencyStatus, User, UserRole
from app.models.tenanting import Tenant
from app.services.idempotency import IdempotencyService, normalize_idempotency_key
from app.services.outbox import OutboxService
from app.services.provider_registry import provider_response_meta
from app.modules.approval.core import cond_matches, make_request_hash

from app.models.job_engine import InboundWebhookDedup
from app.modules.approval.webhook_utils import build_edo_status_dedup_key, build_webhook_signature

router = APIRouter()


def _approval_signing_unprocessable(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": "approval_signing_validation_error", "message": message},
    )


def _require_document_object_id(document_version_id: str | None, object_id: str | None) -> str:
    resolved = object_id or document_version_id
    if not resolved:
        raise _approval_signing_unprocessable("document_version_id is required")
    return resolved


def _validate_certificate_period(cert_info: dict[str, Any]) -> None:
    valid_from = cert_info.get("valid_from")
    valid_to = cert_info.get("valid_to")
    if valid_from and valid_to and valid_from > valid_to:
        raise _approval_signing_unprocessable("invalid certificate period")


class ApprovalStartIn(BaseModel):
    object_type: str = "document_version"
    object_id: str
    context: dict[str, Any] = Field(default_factory=dict)


class DecideIn(BaseModel):
    decision: str
    comment: str | None = None
    delegate_to_user_id: str | None = None


class DelegateIn(BaseModel):
    to_user_id: str
    reason: str | None = None


class SignRequestIn(BaseModel):
    document_version_id: str | None = None
    object_type: str = "document_version"
    object_id: str | None = None
    provider: str = "stub"
    kind: str | None = None
    payload: dict[str, Any] | None = None


class SignSubmitIn(BaseModel):
    document_version_id: str
    kind: str = "un_ep"
    signed_blob: str
    cert_info: dict[str, Any] = Field(default_factory=dict)


class EdoSendIn(BaseModel):
    document_version_id: str | None = None
    object_type: str = "document_version"
    object_id: str | None = None
    provider: str = "stub"
    operator_code: str | None = None
    recipient: str | None = None
    meta: dict[str, Any] | None = None


class EdoSendOut(BaseModel):
    id: str
    status: str
    external_id: str

class ApprovalRouteIn(BaseModel):
    code: str
    name: str
    conditions: dict[str, Any] = Field(default_factory=dict)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    is_active: bool = True
    priority: int = 0


class WebhookSubscriptionIn(BaseModel):
    event_type: str
    url: str
    secret: str



async def _create_tasks(session: AsyncSession, process: ApprovalProcess, route: ApprovalRoute, step_no: int) -> None:
    steps = route.steps or []
    if step_no >= len(steps):
        process.status = ApprovalProcessStatus.APPROVED
        process.finished_at = datetime.now(timezone.utc)
        await OutboxService(session).enqueue(tenant_id=process.tenant_id, event_type="approval.completed", payload={"event_id": str(uuid4()), "tenant_id": process.tenant_id, "metadata": {"process_id": process.id, "status": process.status.value}})
        return
    step = steps[step_no]
    due = datetime.now(timezone.utc)
    if step.get("due_days"):
        due += timedelta(days=int(step["due_days"]))
    if step.get("due_hours"):
        due += timedelta(hours=int(step["due_hours"]))
    if step.get("type") == "user":
        session.add(ApprovalTask(tenant_id=process.tenant_id, process_id=process.id, step_no=step_no, assignee_type="user", assignee_id=step["user_id"], due_at=due))
        return
    role_code = step.get("role_code")
    users = (await session.execute(select(UserRole.user_id).where(UserRole.tenant_id == process.tenant_id, UserRole.role == role_code))).scalars().all()
    for uid in users:
        session.add(ApprovalTask(tenant_id=process.tenant_id, process_id=process.id, step_no=step_no, assignee_type="user", assignee_id=uid, due_at=due))


@router.post("/approvals:start")
@audit_operation("start", "approval_process", id_attr="process_id")
async def approvals_start(payload: ApprovalStartIn, request: Request, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record), x_user_id: str = Header(default="system", alias="X-User-Id")):
    key = request.headers.get("Idempotency-Key")
    idem = None
    if key:
        idem = IdempotencyService(session=session, tenant_id=str(tenant.id), endpoint=request.url.path)
        norm = normalize_idempotency_key(key)
        rec, _ = await idem.acquire(key=norm, request_hash=make_request_hash(request.url.path, str(tenant.id), x_user_id, payload.model_dump(mode="json")), method="POST", path=request.url.path)
        if rec.status is IdempotencyStatus.SUCCEEDED:
            return rec.result_json["body"]
    routes = (await session.execute(select(ApprovalRoute).where(ApprovalRoute.tenant_id == str(tenant.id), ApprovalRoute.is_active.is_(True)))).scalars().all()
    ranked = sorted(((r.priority, cond_matches(r.conditions or {}, payload.context), r) for r in routes), key=lambda i: (i[0], i[1]), reverse=True)
    route = next((r for _, m, r in ranked if m >= 0), None)
    if route is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No matching route")
    process = ApprovalProcess(tenant_id=str(tenant.id), object_type=payload.object_type, object_id=payload.object_id, route_id=route.id, status=ApprovalProcessStatus.IN_PROGRESS, started_at=datetime.now(timezone.utc), created_by=x_user_id)
    session.add(process)
    await session.flush()
    await _create_tasks(session, process, route, 0)
    await OutboxService(session).enqueue(tenant_id=str(tenant.id), event_type="approval.started", payload={"event_id": str(uuid4()), "tenant_id": str(tenant.id), "metadata": {"process_id": process.id}})
    body = {"process_id": process.id, "route_id": route.id, "status": process.status.value}
    if idem:
        await idem.store_success(rec, status_code=200, body=body)
    return body


@router.get("/approvals/processes")
async def approval_processes(status: str | None = None, object_id: str | None = None, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    stmt = select(ApprovalProcess).where(ApprovalProcess.tenant_id == str(tenant.id))
    if status:
        stmt = stmt.where(ApprovalProcess.status == status)
    if object_id:
        stmt = stmt.where(ApprovalProcess.object_id == object_id)
    items = (await session.execute(stmt.order_by(ApprovalProcess.created_at.desc()))).scalars().all()
    return {"items": [{"id": i.id, "status": i.status.value, "object_id": i.object_id, "current_step": i.current_step} for i in items]}


@router.get("/approvals/processes/{process_id}")
async def approval_process_detail(process_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    p = await session.get(ApprovalProcess, process_id)
    if not p or p.tenant_id != str(tenant.id):
        raise HTTPException(404, "Process not found")
    logs = (await session.execute(select(ApprovalDecisionLog).where(ApprovalDecisionLog.tenant_id == str(tenant.id), ApprovalDecisionLog.process_id == process_id).order_by(ApprovalDecisionLog.created_at.asc()))).scalars().all()
    return {"id": p.id, "status": p.status.value, "route_id": p.route_id, "current_step": p.current_step, "logs": [{"decision": l.decision, "comment": l.comment, "step_no": l.step_no} for l in logs]}


@router.get("/approvals/tasks")
async def approval_tasks(mine: bool = True, status: str = "open", session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record), x_user_id: str = Header(default="system", alias="X-User-Id")):
    stmt = select(ApprovalTask).where(ApprovalTask.tenant_id == str(tenant.id), ApprovalTask.status == status)
    if mine:
        stmt = stmt.where(ApprovalTask.assignee_id == x_user_id)
    rows = (await session.execute(stmt.order_by(ApprovalTask.created_at.desc()))).scalars().all()
    return {"items": [{"id": t.id, "process_id": t.process_id, "status": t.status.value, "due_at": t.due_at.isoformat() if t.due_at else None} for t in rows]}


@router.post("/approvals/tasks/{task_id}:decide")
@audit_operation("decide", "approval_task")
async def approval_decide(task_id: str, payload: DecideIn, request: Request, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record), x_user_id: str = Header(default="system", alias="X-User-Id")):
    task = await session.get(ApprovalTask, task_id)
    if not task or task.tenant_id != str(tenant.id):
        raise HTTPException(404, "Task not found")
    if task.assignee_id != x_user_id:
        raise HTTPException(403, "Task assignee mismatch")
    process = await session.get(ApprovalProcess, task.process_id)
    route = await session.get(ApprovalRoute, process.route_id)
    task.status = ApprovalTaskStatus.DONE
    task.decision = payload.decision
    task.comment = payload.comment
    task.decided_at = datetime.now(timezone.utc)
    session.add(ApprovalDecisionLog(tenant_id=str(tenant.id), process_id=process.id, task_id=task.id, step_no=task.step_no, actor_user_id=x_user_id, decision=payload.decision, comment=payload.comment, ip=request.client.host if request.client else None, user_agent=request.headers.get("user-agent")))
    if payload.decision == "reject":
        process.status = ApprovalProcessStatus.REJECTED
        process.finished_at = datetime.now(timezone.utc)
        await session.execute(
            ApprovalTask.__table__.update().where(and_(ApprovalTask.process_id == process.id, ApprovalTask.status == ApprovalTaskStatus.OPEN)).values(status=ApprovalTaskStatus.CANCELED)
        )
        await OutboxService(session).enqueue(tenant_id=str(tenant.id), event_type="approval.completed", payload={"event_id": str(uuid4()), "tenant_id": str(tenant.id), "metadata": {"process_id": process.id, "status": "rejected"}})
        return {"status": process.status.value}
    step = (route.steps or [])[task.step_no] if route.steps else {}
    quorum = int(step.get("quorum", 1))
    approved_count = await session.scalar(select(func.count()).select_from(ApprovalTask).where(ApprovalTask.process_id == process.id, ApprovalTask.step_no == task.step_no, ApprovalTask.decision == "approve"))
    if approved_count >= quorum:
        await session.execute(ApprovalTask.__table__.update().where(and_(ApprovalTask.process_id == process.id, ApprovalTask.step_no == task.step_no, ApprovalTask.status == ApprovalTaskStatus.OPEN)).values(status=ApprovalTaskStatus.CANCELED))
        process.current_step = task.step_no + 1
        await _create_tasks(session, process, route, process.current_step)
    return {"status": process.status.value, "current_step": process.current_step}


@router.post("/approvals/tasks/{task_id}:delegate")
@audit_operation("delegate", "approval_task", id_attr="new_task_id")
async def approval_delegate(task_id: str, payload: DelegateIn, request: Request, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record), x_user_id: str = Header(default="system", alias="X-User-Id")):
    task = await session.get(ApprovalTask, task_id)
    if not task or task.tenant_id != str(tenant.id):
        raise HTTPException(404, "Task not found")
    if task.assignee_id != x_user_id:
        raise HTTPException(403, "Task assignee mismatch")
    task.status = ApprovalTaskStatus.CANCELED
    new_task = ApprovalTask(tenant_id=str(tenant.id), process_id=task.process_id, step_no=task.step_no, assignee_type="user", assignee_id=payload.to_user_id, due_at=task.due_at, delegated_from=task.id)
    session.add(new_task)
    session.add(ApprovalDecisionLog(tenant_id=str(tenant.id), process_id=task.process_id, task_id=task.id, step_no=task.step_no, actor_user_id=x_user_id, decision="delegate", comment=payload.reason, ip=request.client.host if request.client else None, user_agent=request.headers.get("user-agent")))
    return {"status": "delegated", "new_task_id": new_task.id}


@router.post("/approvals/processes/{process_id}:cancel")
@audit_operation("cancel", "approval_process")
async def approval_cancel(process_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    p = await session.get(ApprovalProcess, process_id)
    if not p or p.tenant_id != str(tenant.id):
        raise HTTPException(404, "Process not found")
    p.status = ApprovalProcessStatus.CANCELED
    p.finished_at = datetime.now(timezone.utc)
    await session.execute(ApprovalTask.__table__.update().where(and_(ApprovalTask.process_id == process_id, ApprovalTask.status == ApprovalTaskStatus.OPEN)).values(status=ApprovalTaskStatus.CANCELED))
    return {"status": p.status.value}


@router.post("/sign:request")
@audit_operation("request", "signature_request", id_attr="signature_request_id")
async def sign_request(payload: SignRequestIn, request: Request, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record), x_user_id: str = Header(default="system", alias="X-User-Id")):
    object_id = _require_document_object_id(payload.document_version_id, payload.object_id)
    key = request.headers.get("Idempotency-Key")
    idem = None
    if key:
        idem = IdempotencyService(session=session, tenant_id=str(tenant.id), endpoint=request.url.path)
        rec, _ = await idem.acquire(key=normalize_idempotency_key(key), request_hash=make_request_hash(request.url.path, str(tenant.id), x_user_id, payload.model_dump(mode="json")), method="POST", path=request.url.path)
        if rec.status is IdempotencyStatus.SUCCEEDED:
            return rec.result_json["body"]
    sig = SignatureRequest(tenant_id=str(tenant.id), object_type=payload.object_type, object_id=object_id, provider=payload.provider, status=SignatureRequestStatus.REQUESTED, payload_json={"kind": payload.kind or "un_ep", **(payload.payload or {})})
    session.add(sig)
    await session.flush()
    if payload.provider == "stub":
        sig.status = SignatureRequestStatus.SIGNED
        sig.result_json = {"signed_by": x_user_id, "verified": True}
        await OutboxService(session).enqueue(tenant_id=str(tenant.id), event_type="Signed", payload={"event_id": str(uuid4()), "tenant_id": str(tenant.id), "document_id": object_id, "document_version_id": object_id, "status": "signed", "signed_at": datetime.now(timezone.utc).isoformat()})
    body = {"signature_request_id": sig.id, "status": sig.status.value, **provider_response_meta(payload.provider)}
    if idem:
        await idem.store_success(rec, status_code=200, body=body)
    return body


@router.get("/sign/requests")
async def sign_requests(status: str | None = None, object_id: str | None = None, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    stmt = select(SignatureRequest).where(SignatureRequest.tenant_id == str(tenant.id))
    if status:
        stmt = stmt.where(SignatureRequest.status == status)
    if object_id:
        stmt = stmt.where(SignatureRequest.object_id == object_id)
    rows = (await session.execute(stmt.order_by(SignatureRequest.created_at.desc()))).scalars().all()
    return {
        "items": [
            {"id": r.id, "status": r.status.value, "provider": r.provider, **provider_response_meta(r.provider)}
            for r in rows
        ]
    }


@router.get("/sign/requests/{request_id}")
async def sign_request_get(request_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    row = await session.get(SignatureRequest, request_id)
    if not row or row.tenant_id != str(tenant.id):
        raise HTTPException(404, "Signature request not found")
    return {"id": row.id, "status": row.status.value, "result_json": row.result_json}


@router.post("/edo:send")
@audit_operation("send", "edo_envelope")
async def edo_send(
    payload: EdoSendIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
):
    key = normalize_idempotency_key(request.headers.get("Idempotency-Key"))
    request_hash = make_request_hash(request.url.path, str(tenant.id), None, payload.model_dump(mode="json"))
    idem = IdempotencyService(session=session, tenant_id=str(tenant.id), endpoint="approval.edo_send")
    rec, created = await idem.acquire(key=key, request_hash=request_hash, method="POST", path=request.url.path)
    if not created:
        return await idem.respond_from_store(rec, model=EdoSendOut, response=response)

    object_id = _require_document_object_id(payload.document_version_id, payload.object_id)
    env = EdoEnvelope(
        tenant_id=str(tenant.id),
        object_type=payload.object_type,
        object_id=object_id,
        provider=payload.operator_code or payload.provider,
        status=EdoEnvelopeStatus.SENT,
        external_id=f"{(payload.operator_code or payload.provider)}-{uuid4().hex[:12]}",
        last_event_at=datetime.now(timezone.utc),
    )
    session.add(env)
    await session.flush()
    outbox = OutboxService(session)
    await outbox.enqueue(
        tenant_id=str(tenant.id),
        event_type="Exported",
        payload={"event_id": str(uuid4()), "tenant_id": str(tenant.id), "metadata": {"envelope_id": env.id}},
    )
    await outbox.enqueue(
        tenant_id=str(tenant.id),
        event_type="EdoStatusChanged",
        payload={"event_id": str(uuid4()), "tenant_id": str(tenant.id), "metadata": {"envelope_id": env.id, "status": EdoEnvelopeStatus.DELIVERED.value}},
    )
    body = {"id": env.id, "status": env.status.value, "external_id": env.external_id}
    await idem.store_success(
        rec,
        status_code=200,
        body=body,
        headers={"correlation-id": request.headers.get("x-correlation-id", "")},
    )
    await session.commit()
    return body


@router.get("/edo/envelopes")
async def edo_list(status: str | None = None, object_id: str | None = None, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    stmt = select(EdoEnvelope).where(EdoEnvelope.tenant_id == str(tenant.id))
    if status:
        stmt = stmt.where(EdoEnvelope.status == status)
    if object_id:
        stmt = stmt.where(EdoEnvelope.object_id == object_id)
    rows = (await session.execute(stmt.order_by(EdoEnvelope.created_at.desc()))).scalars().all()
    return {"items": [{"id": e.id, "status": e.status.value, "external_id": e.external_id} for e in rows]}


@router.get("/edo/envelopes/{envelope_id}")
async def edo_get(envelope_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    e = await session.get(EdoEnvelope, envelope_id)
    if not e or e.tenant_id != str(tenant.id):
        raise HTTPException(404, "Envelope not found")
    return {"id": e.id, "status": e.status.value, "external_id": e.external_id, "last_event_at": e.last_event_at}


@router.post("/edo/webhooks/{provider}")
@audit_operation("ingest_webhook", "edo_webhook")
async def edo_webhook(provider: str, payload: dict[str, Any], request: Request, x_signature: str | None = Header(default=None, alias="X-Signature"), session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    secret = str((tenant.settings or {}).get("edo_webhook_secret", "dev-secret"))
    expected = build_webhook_signature(secret=secret, body=await request.body())
    if x_signature and not hmac.compare_digest(x_signature, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")
    external_id = payload.get("external_id")
    env = (await session.execute(select(EdoEnvelope).where(EdoEnvelope.tenant_id == str(tenant.id), EdoEnvelope.provider == provider, EdoEnvelope.external_id == external_id))).scalar_one_or_none()
    if not env:
        raise HTTPException(404, "Envelope not found")
    new_status = payload.get("status", "failed")
    env.status = EdoEnvelopeStatus(new_status)
    env.last_event_at = datetime.now(timezone.utc)
    await OutboxService(session).enqueue(tenant_id=str(tenant.id), event_type="edo.status_changed", payload={"event_id": str(uuid4()), "tenant_id": str(tenant.id), "metadata": {"envelope_id": env.id, "status": env.status.value}})
    return {"status": "ok"}


@router.post("/approvals/start")
async def approvals_start_v1(payload: ApprovalStartIn, request: Request, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record), x_user_id: str = Header(default="system", alias="X-User-Id")):
    return await approvals_start(payload, request, session, tenant, x_user_id)


@router.get("/approvals/instances")
async def approval_instances(document_version_id: str | None = None, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    items = (await session.execute(select(ApprovalProcess).where(ApprovalProcess.tenant_id == str(tenant.id), ApprovalProcess.object_id == (document_version_id or ApprovalProcess.object_id)).order_by(ApprovalProcess.created_at.desc()))).scalars().all()
    return {"items": [{"id": i.id, "document_version_id": i.object_id, "status": i.status.value, "started_at": i.started_at, "finished_at": i.finished_at} for i in items]}


@router.get("/approvals/tasks")
async def approval_tasks_v1(mine: int = 1, status: str = "pending", session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record), x_user_id: str = Header(default="system", alias="X-User-Id")):
    stmt = select(ApprovalTask).where(ApprovalTask.tenant_id == str(tenant.id))
    if mine:
        stmt = stmt.where(ApprovalTask.assignee_id == x_user_id)
    stmt = stmt.where(ApprovalTask.status == (ApprovalTaskStatus.OPEN if status == "pending" else ApprovalTaskStatus.DONE))
    items = (await session.execute(stmt.order_by(ApprovalTask.created_at.desc()))).scalars().all()
    return {"items": [{"id": t.id, "instance_id": t.process_id, "status": "pending" if t.status == ApprovalTaskStatus.OPEN else "approved", "assignee_user_id": t.assignee_id, "deadline_at": t.due_at} for t in items]}


@router.post("/approvals/tasks/{task_id}/decision")
async def approval_decision_v1(task_id: str, payload: DecideIn, request: Request, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record), x_user_id: str = Header(default="system", alias="X-User-Id")):
    if payload.delegate_to_user_id:
        return await approval_delegate(task_id, DelegateIn(to_user_id=payload.delegate_to_user_id, reason=payload.comment), request, session, tenant, x_user_id)
    return await approval_decide(task_id, DecideIn(decision=payload.decision, comment=payload.comment), request, session, tenant, x_user_id)


@router.post("/sign/request")
async def sign_request_v1(payload: SignRequestIn, request: Request, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record), x_user_id: str = Header(default="system", alias="X-User-Id")):
    return await sign_request(payload, request, session, tenant, x_user_id)


@router.post("/sign/submit")
@audit_operation("submit", "signature_request")
async def sign_submit_v1(payload: SignSubmitIn, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record), x_user_id: str = Header(default="system", alias="X-User-Id")):
    cert_info = payload.cert_info or {}
    _validate_certificate_period(cert_info)
    sig = SignatureRequest(tenant_id=str(tenant.id), object_type="document_version", object_id=payload.document_version_id, provider="stub", status=SignatureRequestStatus.SIGNED, payload_json={"kind": payload.kind, "signed_blob": payload.signed_blob[:64]}, result_json={"cert_info": cert_info, "ocsp_status": cert_info.get("ocsp_status", "unknown")})
    session.add(sig)
    await session.flush()
    await OutboxService(session).enqueue(tenant_id=str(tenant.id), event_type="Signed", payload={"event_id": str(uuid4()), "tenant_id": str(tenant.id), "document_version_id": payload.document_version_id, "signature_id": sig.id})
    return {"id": sig.id, "status": sig.status.value}


@router.get("/sign/status")
async def sign_status_v1(document_version_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    rows = (await session.execute(select(SignatureRequest).where(SignatureRequest.tenant_id == str(tenant.id), SignatureRequest.object_id == document_version_id).order_by(SignatureRequest.created_at.desc()))).scalars().all()
    return {"items": [{"id": s.id, "status": s.status.value, "payload": s.payload_json, "result": s.result_json} for s in rows]}


@router.post("/edo/send")
async def edo_send_v1(payload: EdoSendIn, request: Request, response: Response, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    return await edo_send(payload, request, response, session, tenant)


@router.get("/edo/messages")
async def edo_messages_v1(document_version_id: str | None = None, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    stmt = select(EdoEnvelope).where(EdoEnvelope.tenant_id == str(tenant.id))
    if document_version_id:
        stmt = stmt.where(EdoEnvelope.object_id == document_version_id)
    items = (await session.execute(stmt.order_by(EdoEnvelope.created_at.desc()))).scalars().all()
    return {"items": [{"id": e.id, "document_version_id": e.object_id, "status": e.status.value, "external_id": e.external_id, "last_status_at": e.last_event_at} for e in items]}


@router.post("/edo/webhook/status")
@audit_operation("ingest_webhook", "edo_status")
async def edo_webhook_status(payload: dict[str, Any], session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    provider = str(payload.get("provider") or "stub")
    external_id = payload.get("external_id")
    if not external_id:
        raise _approval_signing_unprocessable("external_id is required")
    status_value = str(payload.get("status", "failed"))
    dedup_key = build_edo_status_dedup_key(external_id=external_id, status=status_value)
    dedup = InboundWebhookDedup(
        tenant_id=str(tenant.id),
        source=f"edo_status:{provider}",
        dedup_key=dedup_key,
        payload_hash=hashlib.sha256(str(payload).encode("utf-8")).hexdigest(),
        received_at=datetime.now(timezone.utc),
    )
    session.add(dedup)
    try:
        await session.flush()
    except Exception:
        await session.rollback()
        return {"status": "duplicate"}

    env = (await session.execute(select(EdoEnvelope).where(EdoEnvelope.tenant_id == str(tenant.id), EdoEnvelope.provider == provider, EdoEnvelope.external_id == external_id))).scalar_one_or_none()
    if not env:
        raise HTTPException(404, "Envelope not found")
    env.status = EdoEnvelopeStatus(status_value)
    env.last_event_at = datetime.now(timezone.utc)
    await OutboxService(session).enqueue(tenant_id=str(tenant.id), event_type="EdoStatusChanged", payload={"event_id": str(uuid4()), "tenant_id": str(tenant.id), "metadata": {"envelope_id": env.id, "status": env.status.value}})
    return {"status": "ok"}


@router.get("/approvals/routes")
async def approval_routes_v1(session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    rows = (await session.execute(select(ApprovalRoute).where(ApprovalRoute.tenant_id == str(tenant.id)).order_by(ApprovalRoute.created_at.desc()))).scalars().all()
    return {"items": [{"id": r.id, "code": r.code, "name": r.name, "conditions": r.conditions, "steps": r.steps, "is_active": r.is_active} for r in rows]}


@router.post("/approvals/routes")
@audit_operation("create", "approval_route")
async def approval_routes_create_v1(payload: ApprovalRouteIn, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    row = ApprovalRoute(tenant_id=str(tenant.id), code=payload.code, name=payload.name, conditions=payload.conditions, steps=payload.steps, is_active=payload.is_active, priority=payload.priority, version=1)
    session.add(row)
    await session.flush()
    return {"id": row.id, "code": row.code, "name": row.name}


@router.patch("/approvals/routes/{route_id}")
@audit_operation("update", "approval_route")
async def approval_routes_patch_v1(route_id: str, payload: ApprovalRouteIn, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    row = await session.get(ApprovalRoute, route_id)
    if not row or row.tenant_id != str(tenant.id):
        raise HTTPException(404, "Route not found")
    row.name = payload.name
    row.conditions = payload.conditions
    row.steps = payload.steps
    row.is_active = payload.is_active
    row.priority = payload.priority
    row.version = int((row.version or 1) + 1)
    return {"id": row.id, "code": row.code, "name": row.name, "version": row.version}


@router.get("/webhooks")
async def webhooks_v1(session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    rows = (await session.execute(select(WebhookEndpoint).where(WebhookEndpoint.tenant_id == str(tenant.id)).order_by(WebhookEndpoint.created_at.desc()))).scalars().all()
    return {"items": [{"id": r.id, "event_type": (r.subscribed_events or [None])[0], "url": r.url, "is_active": r.is_enabled} for r in rows]}


@router.post("/webhooks")
@audit_operation("create", "webhook_endpoint")
async def webhooks_create_v1(payload: WebhookSubscriptionIn, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    row = WebhookEndpoint(tenant_id=str(tenant.id), name=f"{payload.event_type} subscription", url=payload.url, secret=payload.secret, is_enabled=True, subscribed_events=[payload.event_type])
    session.add(row)
    await session.flush()
    return {"id": row.id, "event_type": payload.event_type, "url": row.url, "is_active": row.is_enabled}


@router.patch("/webhooks/{webhook_id}/disable")
@audit_operation("disable", "webhook_endpoint")
async def webhooks_disable_v1(webhook_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    row = await session.get(WebhookEndpoint, webhook_id)
    if not row or row.tenant_id != str(tenant.id):
        raise HTTPException(404, "Webhook not found")
    row.is_enabled = False
    return {"id": row.id, "is_active": row.is_enabled}
