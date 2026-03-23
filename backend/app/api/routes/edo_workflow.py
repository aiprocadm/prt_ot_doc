from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.tracing import get_trace_id
from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.security import AccessContext, abac
from app.models.document import DocumentVersion
from app.models.job_engine import InboundWebhookDedup
from app.models.models import RoleEnum, Tenant
from app.models.workflow import (
    ApprovalDecision,
    ApprovalDecisionType,
    ApprovalRequest,
    ApprovalRequestStatus,
    ApprovalRoute,
    EdoDirection,
    EdoMessage,
    EdoReceipt,
    EdoStatus,
    EdoStatusHistory,
    Signature,
    SignatureStatus,
    SignatureType,
)
from app.services.events import EventType
from app.services.file_storage import FileStorageService
from app.models.models import IdempotencyStatus
from app.services.idempotency import IdempotencyService, normalize_idempotency_key
from app.services.billing import BillingService
from app.services.outbox import OutboxService
from app.services.provider_registry import provider_response_meta
from app.tasks import edo_status_simulation_job, process_inbound_webhook, send_edo_job

router = APIRouter()
SessionDep = Depends(get_session)
TenantDep = Depends(get_tenant_record)


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> UUID | None:
    return getattr(tenant, "id", None)


AccessDep = Depends(abac(_tenant_resource_id, required_roles=["admin", "employee"], action="manage edo"))


class ApiError(BaseModel):
    code: str
    type: str
    message: str
    correlation_id: str


class ApprovalStep(BaseModel):
    order: int
    role: RoleEnum
    allow_delegate: bool = False
    deadline_hours: int | None = None


class ApprovalRules(BaseModel):
    steps: list[ApprovalStep]

    @classmethod
    def validate_rules(cls, raw: dict[str, Any]) -> "ApprovalRules":
        parsed = cls.model_validate(raw)
        if not parsed.steps:
            raise ValueError("steps must not be empty")
        orders = [step.order for step in parsed.steps]
        if sorted(orders) != list(range(1, len(parsed.steps) + 1)):
            raise ValueError("step order must be sequential and unique")
        return parsed


class ApprovalRouteCreate(BaseModel):
    code: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    rules_json: dict[str, Any]
    version: int = Field(default=1, ge=1)
    is_active: bool = True


class ApprovalRequestCreate(BaseModel):
    document_version_id: str
    route_id: str | None = None
    route_code: str | None = None


class ApprovalDecisionCreate(BaseModel):
    decision: ApprovalDecisionType
    comment: str | None = None
    delegate_to_user_id: str | None = None


class SignatureCreate(BaseModel):
    document_version_id: str
    type: SignatureType = SignatureType.INTERNAL


class EdoSendRequest(BaseModel):
    document_version_id: str
    provider_code: str = "mock"
    recipient: str | None = None
    operator_code: str | None = None

    def resolved_provider(self) -> str:
        return self.operator_code or self.provider_code


class SignatureRequestIn(BaseModel):
    document_version_id: str
    kind: SignatureType = SignatureType.INTERNAL


class SignatureSubmitIn(BaseModel):
    document_version_id: str
    kind: SignatureType = SignatureType.INTERNAL
    signed_blob: str
    cert_info: dict[str, Any] = Field(default_factory=dict)


class EdoWebhookPayload(BaseModel):
    event_id: str
    external_id: str
    status: EdoStatus
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


def _request_hash(*, request: Request, tenant: Tenant, user_id: str | None, body: Any) -> str:
    payload = {
        "route": request.url.path,
        "tenant": str(tenant.id),
        "body": body,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _correlation_id(request: Request, response: Response) -> str:
    value = get_trace_id(request)
    response.headers["X-Trace-Id"] = value
    response.headers["X-Correlation-Id"] = value
    response.headers["X-Request-Id"] = value
    return value


async def _idempotent_or_replay(
    *,
    request: Request,
    response: Response,
    session: AsyncSession,
    tenant: Tenant,
    user_id: str | None,
    model: BaseModel,
) -> tuple[IdempotencyService | None, Any]:
    key_header = request.headers.get("Idempotency-Key")
    if key_header is None:
        return None, None
    key = normalize_idempotency_key(key_header)
    service = IdempotencyService(session=session, tenant_id=str(tenant.id), endpoint=request.url.path)
    digest = _request_hash(request=request, tenant=tenant, user_id=user_id, body=model.model_dump(mode="json"))
    record, created = await service.acquire(
        key=key,
        request_hash=digest,
        method=request.method.upper(),
        path=request.url.path,
    )
    if not created and record.status is IdempotencyStatus.SUCCEEDED:
        payload = record.result_json or {}
        response.status_code = int(payload.get("status_code", 200))
        return service, payload.get("body", {})
    request.state.idempotency_record = record
    return service, None


@router.post("/approvals/routes")
@audit_operation("create", "approval_route")
async def create_approval_route(
    payload: ApprovalRouteCreate,
    request: Request,
    response: Response,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    _: AccessContext = AccessDep,
):
    cid = _correlation_id(request, response)
    try:
        ApprovalRules.validate_rules(payload.rules_json)
    except Exception as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    route = ApprovalRoute(
        tenant_id=str(tenant.id),
        code=payload.code,
        name=payload.name,
        rules_json=payload.rules_json,
        version=payload.version,
        is_active=payload.is_active,
    )
    session.add(route)
    await session.flush()
    return {"id": route.id, "correlation_id": cid}


@router.get("/approvals/routes")
async def list_approval_routes(session: AsyncSession = SessionDep, tenant: Tenant = TenantDep, _: AccessContext = AccessDep):
    rows = (await session.execute(select(ApprovalRoute).where(ApprovalRoute.tenant_id == str(tenant.id)))).scalars().all()
    return {"items": [{"id": row.id, "code": row.code, "name": row.name, "version": row.version} for row in rows]}


@router.patch("/approvals/routes/{route_id}")
@audit_operation("update", "approval_route")
async def update_approval_route(
    route_id: str,
    payload: ApprovalRouteCreate,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    _: AccessContext = AccessDep,
):
    route = await session.get(ApprovalRoute, route_id)
    if route is None or route.tenant_id != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Approval route not found")
    ApprovalRules.validate_rules(payload.rules_json)
    route.code = payload.code
    route.name = payload.name
    route.rules_json = payload.rules_json
    route.version = payload.version
    route.is_active = payload.is_active
    await session.flush()
    return {"id": route.id, "version": route.version, "is_active": route.is_active}


@router.post("/approvals/requests")
@audit_operation("start", "approval_request")
async def start_approval_request(
    payload: ApprovalRequestCreate,
    request: Request,
    response: Response,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    access: AccessContext = AccessDep,
):
    _correlation_id(request, response)
    await BillingService(session).assert_allowed(tenant, "edo.send")
    idem_service, replay = await _idempotent_or_replay(
        request=request, response=response, session=session, tenant=tenant, user_id=str(access.user.id), model=payload
    )
    if replay is not None:
        return replay
    route = None
    if payload.route_id:
        route = await session.get(ApprovalRoute, payload.route_id)
    elif payload.route_code:
        route = (
            await session.execute(
                select(ApprovalRoute).where(
                    ApprovalRoute.tenant_id == str(tenant.id),
                    ApprovalRoute.code == payload.route_code,
                    ApprovalRoute.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
    if route is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Approval route not found")
    if await session.get(DocumentVersion, payload.document_version_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document version not found")

    approval_request = ApprovalRequest(
        tenant_id=str(tenant.id),
        document_version_id=payload.document_version_id,
        route_id=route.id,
        status=ApprovalRequestStatus.RUNNING,
        started_at=datetime.now(tz=timezone.utc),
        created_by=access.user.id,
    )
    session.add(approval_request)
    await OutboxService(session).enqueue(
        tenant_id=str(tenant.id),
        event_type="approval.started",
        payload={"tenant_id": str(tenant.id), "event_id": str(uuid4()), "metadata": {"request_id": approval_request.id}},
        destination="internal://approval",
        idempotency_key=f"approval.started:{approval_request.id}",
    )
    await session.flush()
    body = {"id": approval_request.id, "status": approval_request.status.value}
    if idem_service is not None:
        record = getattr(request.state, "idempotency_record", None)
        if record is not None:
            await idem_service.store_success(record, status_code=200, body=body)
    return body


@router.post("/approvals/start")
@audit_operation("start", "approval_request")
async def start_approval_request_v1(
    payload: ApprovalRequestCreate,
    request: Request,
    response: Response,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    access: AccessContext = AccessDep,
):
    return await start_approval_request(payload, request, response, session, tenant, access)


@router.get("/approvals/instances")
async def list_approval_instances(
    document_version_id: str | None = None,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    _: AccessContext = AccessDep,
):
    stmt = select(ApprovalRequest).where(ApprovalRequest.tenant_id == str(tenant.id))
    if document_version_id:
        stmt = stmt.where(ApprovalRequest.document_version_id == document_version_id)
    items = (await session.execute(stmt.order_by(ApprovalRequest.created_at.desc()))).scalars().all()
    return {"items": [{"id": row.id, "status": row.status.value, "document_version_id": row.document_version_id} for row in items]}


@router.get("/approvals/tasks")
async def list_approval_tasks(
    mine: int = 0,
    status_filter: str | None = None,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    access: AccessContext = AccessDep,
):
    stmt = select(ApprovalDecision).where(ApprovalDecision.tenant_id == str(tenant.id))
    if mine:
        stmt = stmt.where(ApprovalDecision.actor_user_id == access.user.id)
    if status_filter:
        stmt = stmt.where(ApprovalDecision.decision == ApprovalDecisionType(status_filter))
    items = (await session.execute(stmt.order_by(ApprovalDecision.created_at.desc()))).scalars().all()
    return {"items": [{"id": row.id, "request_id": row.request_id, "decision": row.decision.value} for row in items]}


@router.post("/approvals/requests/{request_id}/decide")
@audit_operation("decide", "approval_request")
async def decide_approval_request(
    request_id: str,
    payload: ApprovalDecisionCreate,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    access: AccessContext = AccessDep,
):
    approval_request = await session.get(ApprovalRequest, request_id)
    if approval_request is None or approval_request.tenant_id != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Approval request not found")

    decision = ApprovalDecision(
        tenant_id=str(tenant.id),
        request_id=approval_request.id,
        step_index=approval_request.current_step_index,
        actor_user_id=access.user.id,
        decision=payload.decision,
        comment=payload.comment or payload.delegate_to_user_id,
    )
    session.add(decision)

    if payload.decision is ApprovalDecisionType.APPROVE:
        route = await session.get(ApprovalRoute, approval_request.route_id)
        if route is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Approval route not found")
        rules = ApprovalRules.validate_rules(route.rules_json)
        next_index = approval_request.current_step_index + 1
        if next_index >= len(rules.steps):
            approval_request.status = ApprovalRequestStatus.APPROVED
            approval_request.finished_at = datetime.now(tz=timezone.utc)
        else:
            approval_request.current_step_index = next_index
    elif payload.decision is ApprovalDecisionType.REJECT:
        approval_request.status = ApprovalRequestStatus.REJECTED
        approval_request.finished_at = datetime.now(tz=timezone.utc)

    outbox = OutboxService(session)
    await outbox.enqueue(
        tenant_id=str(tenant.id),
        event_type="approval.decision_made",
        payload={"tenant_id": str(tenant.id), "event_id": str(uuid4()), "metadata": {"request_id": approval_request.id}},
        destination="internal://approval",
        idempotency_key=f"approval.decision:{decision.id}",
    )
    if approval_request.status in {ApprovalRequestStatus.APPROVED, ApprovalRequestStatus.REJECTED}:
        await outbox.enqueue(
            tenant_id=str(tenant.id),
            event_type="approval.completed",
            payload={"tenant_id": str(tenant.id), "event_id": str(uuid4()), "metadata": {"request_id": approval_request.id}},
            destination="internal://approval",
            idempotency_key=f"approval.completed:{approval_request.id}",
        )
    await session.flush()
    return {"status": approval_request.status.value, "current_step_index": approval_request.current_step_index}


@router.post("/signatures")
@audit_operation("create", "signature")
async def create_signature(
    payload: SignatureCreate,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    access: AccessContext = AccessDep,
):
    if await session.get(DocumentVersion, payload.document_version_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document version not found")
    now = datetime.now(tz=timezone.utc)
    signature = Signature(
        tenant_id=str(tenant.id),
        document_version_id=payload.document_version_id,
        type=payload.type,
        status=SignatureStatus.PENDING,
        signer_user_id=access.user.id,
    )
    if payload.type is SignatureType.INTERNAL:
        signature.status = SignatureStatus.SIGNED
        signature.signed_at = now
    session.add(signature)
    await session.flush()
    storage = FileStorageService.default()
    receipt = {"signature_id": signature.id, "status": signature.status.value, "signed_at": now.isoformat()}
    receipt_key = f"{tenant.slug}/signatures/{uuid4().hex}.json"
    storage.put(receipt_key, json.dumps(receipt).encode("utf-8"), content_type="application/json")
    signature.receipts_s3_key = receipt_key
    await session.flush()
    await OutboxService(session).enqueue(
        tenant_id=str(tenant.id),
        event_type=EventType.DOCUMENT_SIGNED.value,
        payload={
            "tenant_id": str(tenant.id),
            "event_id": str(uuid4()),
            "document_id": payload.document_version_id,
            "document_version_id": payload.document_version_id,
            "status": signature.status.value,
            "signed_at": (signature.signed_at or now).isoformat(),
        },
        idempotency_key=f"signature:{signature.id}",
    )
    return {"id": signature.id, "status": signature.status.value, "receipts_s3_key": signature.receipts_s3_key}


@router.post("/sign/request")
@audit_operation("request", "signature")
async def sign_request(
    payload: SignatureRequestIn,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    access: AccessContext = AccessDep,
):
    return await create_signature(SignatureCreate(document_version_id=payload.document_version_id, type=payload.kind), session, tenant, access)


@router.post("/sign/submit")
@audit_operation("submit", "signature")
async def sign_submit(
    payload: SignatureSubmitIn,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    access: AccessContext = AccessDep,
):
    signature = Signature(
        tenant_id=str(tenant.id),
        document_version_id=payload.document_version_id,
        type=payload.kind,
        status=SignatureStatus.SIGNED,
        signer_user_id=access.user.id,
        cert_info_json=payload.cert_info,
        signed_at=datetime.now(tz=timezone.utc),
    )
    session.add(signature)
    await session.flush()
    await OutboxService(session).enqueue(
        tenant_id=str(tenant.id),
        event_type=EventType.DOCUMENT_SIGNED.value,
        payload={"tenant_id": str(tenant.id), "event_id": str(uuid4()), "document_version_id": payload.document_version_id, "status": signature.status.value},
        idempotency_key=f"signature:submit:{signature.id}",
    )
    return {"id": signature.id, "status": signature.status.value}


@router.get("/sign/status")
async def sign_status(
    document_version_id: str,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    _: AccessContext = AccessDep,
):
    items = (
        await session.execute(
            select(Signature).where(Signature.tenant_id == str(tenant.id), Signature.document_version_id == document_version_id)
        )
    ).scalars().all()
    return {"items": [{"id": row.id, "status": row.status.value, "kind": row.type.value} for row in items]}


@router.get("/signatures")
async def list_signatures(document_version_id: str | None = None, session: AsyncSession = SessionDep, tenant: Tenant = TenantDep, _: AccessContext = AccessDep):
    stmt = select(Signature).where(Signature.tenant_id == str(tenant.id))
    if document_version_id:
        stmt = stmt.where(Signature.document_version_id == document_version_id)
    items = (await session.execute(stmt.order_by(Signature.created_at.desc()))).scalars().all()
    return {"items": [{"id": row.id, "status": row.status.value, "type": row.type.value} for row in items]}


@router.post("/edo/send")
@audit_operation("send", "edo_message")
async def send_to_edo(
    payload: EdoSendRequest,
    request: Request,
    response: Response,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    access: AccessContext = AccessDep
):
    _correlation_id(request, response)
    await BillingService(session).assert_allowed(tenant, "edo.send")
    idem_service, replay = await _idempotent_or_replay(
        request=request, response=response, session=session, tenant=tenant, user_id=str(access.user.id), model=payload
    )
    if replay is not None:
        return replay
    message = EdoMessage(
        tenant_id=str(tenant.id),
        direction=EdoDirection.OUTGOING,
        document_version_id=payload.document_version_id,
        provider_code=payload.resolved_provider(),
        status=EdoStatus.QUEUED,
        payload_json={"document_version_id": payload.document_version_id},
    )
    session.add(message)
    await session.flush()
    message.external_id = f"{payload.resolved_provider()}-{message.id}"
    message.status = EdoStatus.SENT
    history = EdoStatusHistory(
        tenant_id=str(tenant.id),
        edo_message_id=message.id,
        status=EdoStatus.SENT,
        raw_payload_json={"provider": payload.resolved_provider()},
    )
    session.add(history)
    await OutboxService(session).enqueue(
        tenant_id=str(tenant.id),
        event_type="edo.sent",
        payload={"tenant_id": str(tenant.id), "event_id": str(uuid4()), "metadata": {"edo_message_id": message.id}},
        destination="internal://edo",
        idempotency_key=f"edo.sent:{message.id}",
    )
    await BillingService(session).add_usage(tenant_id=str(tenant.id), edo_outgoing=1)
    body = {
        "id": message.id,
        "external_id": message.external_id,
        "status": message.status.value,
        **provider_response_meta(payload.resolved_provider()),
    }
    send_edo_job.delay(message_id=message.id, tenant_id=str(tenant.id), provider_code=payload.resolved_provider())
    edo_status_simulation_job.delay(message_id=message.id, tenant_id=str(tenant.id), status="delivered")
    edo_status_simulation_job.delay(message_id=message.id, tenant_id=str(tenant.id), status="accepted")
    if idem_service is not None:
        record = getattr(request.state, "idempotency_record", None)
        if record is not None:
            await idem_service.store_success(record, status_code=200, body=body)
    return body


@router.get("/edo/messages")
async def edo_messages(
    document_version_id: str | None = None,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    _: AccessContext = AccessDep,
):
    stmt = select(EdoMessage).where(EdoMessage.tenant_id == str(tenant.id))
    if document_version_id:
        stmt = stmt.where(EdoMessage.document_version_id == document_version_id)
    rows = (await session.execute(stmt.order_by(EdoMessage.created_at.desc()))).scalars().all()
    return {
        "items": [
            {
                "id": row.id,
                "external_id": row.external_id,
                "status": row.status.value,
                **provider_response_meta(getattr(row, "provider_code", None)),
            }
            for row in rows
        ]
    }


@router.post("/edo/webhook/status")
@audit_operation("ingest_webhook", "edo_webhook")
async def edo_status_webhook_v1(
    payload: EdoWebhookPayload,
    request: Request,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
):
    return await edo_webhook("stub", payload, request, session, tenant, None)


@router.post("/edo/webhooks/{provider_code}")
@audit_operation("ingest_webhook", "edo_webhook")
async def edo_webhook(
    provider_code: str,
    payload: EdoWebhookPayload,
    request: Request,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    x_signature: str | None = Header(default=None, alias="X-Signature"),
):
    secret = str((tenant.settings or {}).get("edo_webhook_secret", "dev-secret"))
    raw = await request.body()
    expected = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    if x_signature and not hmac.compare_digest(expected, x_signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature")

    payload_hash = hashlib.sha256(raw).hexdigest()
    dedup_key = str(payload.event_id or payload_hash)
    dedup = InboundWebhookDedup(
        tenant_id=str(tenant.id),
        source=f"edo_operator:{provider_code}",
        dedup_key=dedup_key,
        payload_hash=payload_hash,
        received_at=datetime.now(tz=timezone.utc),
    )
    session.add(dedup)
    try:
        await session.flush()
    except Exception:
        await session.rollback()
        return {"status": "duplicate", **provider_response_meta(provider_code)}

    process_inbound_webhook.delay(
        source="edo",
        tenant_slug=tenant.slug,
        payload={
            "provider_code": provider_code,
            "external_id": payload.external_id,
            "status": payload.status.value,
            "event_id": payload.event_id,
            "correlation_id": request.headers.get("X-Correlation-Id"),
            "raw_payload": payload.raw_payload,
        },
    )
    return {"status": "accepted", **provider_response_meta(provider_code)}
