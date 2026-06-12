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

from app.api.dependencies import get_session, get_tenant_record
from app.api.deps.tracing import get_trace_id
from app.core.audit_decorator import audit_operation
from app.core.errors import api_problem_detail
from app.core.security import AccessContext, abac
from app.models.document import DocumentVersion
from app.models.job_engine import InboundWebhookDedup
from app.models.models import IdempotencyStatus, RoleEnum, Tenant
from app.models.workflow import (
    ApprovalDecision,
    ApprovalDecisionType,
    ApprovalRequest,
    ApprovalRequestStatus,
    ApprovalRoute,
    EdoMessage,
    EdoStatus,
    Signature,
    SignatureType,
)
from app.services.billing import BillingService
from app.services.idempotency import IdempotencyService, normalize_idempotency_key
from app.services.outbox import OutboxService
from app.services.provider_registry import provider_response_meta
from app.services.pep_signing import PepConflict, PepNotFound, PepSigningService
from app.tasks import process_inbound_webhook

router = APIRouter()
SessionDep = Depends(get_session)
TenantDep = Depends(get_tenant_record)


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> UUID | None:
    return getattr(tenant, "id", None)


AccessDep = Depends(abac(_tenant_resource_id, required_roles=["admin", "employee"], action="manage edo"))


def _edo_unprocessable(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=api_problem_detail(code="EDO_VALIDATION_ERROR", message=message, error_type="edo"),
    )


def _provider_not_configured(kind: str) -> HTTPException:
    """Честный отказ вместо симуляции: внешний провайдер не настроен (Срез-1 ПЭП).

    Codes: EDO_PROVIDER_NOT_CONFIGURED | SIGNATURE_PROVIDER_NOT_CONFIGURED
    """
    code = f"{kind.upper()}_PROVIDER_NOT_CONFIGURED"
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=api_problem_detail(
            code=code,
            message=(
                f"external {kind} provider is not configured; "
                "internal PEP signing is available at /sign/pep"
            ),
            error_type="edo",
        ),
    )


def _edo_not_found(resource: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=api_problem_detail(
            code="EDO_NOT_FOUND",
            message=f"{resource} not found",
            details={"resource": resource},
            error_type="edo",
        ),
    )


def _edo_unauthorized(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=api_problem_detail(code="EDO_UNAUTHORIZED", message=message, error_type="edo"),
    )


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


def _validate_approval_rules(raw: dict[str, Any]) -> ApprovalRules:
    try:
        return ApprovalRules.validate_rules(raw)
    except ValueError as exc:
        raise _edo_unprocessable(str(exc)) from exc


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
    provider_code: str = "internal-fallback"
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
    if not created and record.status == IdempotencyStatus.SUCCEEDED:
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
    _validate_approval_rules(payload.rules_json)
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
    request: Request,
    response: Response,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    _: AccessContext = AccessDep,
):
    cid = _correlation_id(request, response)
    route = await session.get(ApprovalRoute, route_id)
    if route is None or route.tenant_id != str(tenant.id):
        raise _edo_not_found("approval_route")
    _validate_approval_rules(payload.rules_json)
    route.code = payload.code
    route.name = payload.name
    route.rules_json = payload.rules_json
    route.version = payload.version
    route.is_active = payload.is_active
    await session.flush()
    return {"id": route.id, "version": route.version, "is_active": route.is_active, "correlation_id": cid}


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
        cand = await session.get(ApprovalRoute, payload.route_id)
        if cand is not None and str(cand.tenant_id) == str(tenant.id):
            route = cand
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
        raise _edo_not_found("approval_route")
    doc_ver = await session.get(DocumentVersion, payload.document_version_id)
    if doc_ver is None or str(doc_ver.tenant_id) != str(tenant.id):
        raise _edo_not_found("document_version")

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
    body = {"id": approval_request.id, "status": approval_request.status.value, "correlation_id": get_trace_id(request)}
    if idem_service is not None:
        record = getattr(request.state, "idempotency_record", None)
        if record is not None:
            await idem_service.store_success(record, status_code=200, body=body)
    return body


@router.post("/edo-workflow/approvals/start")
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
    request: Request,
    response: Response,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    access: AccessContext = AccessDep,
):
    cid = _correlation_id(request, response)
    approval_request = await session.get(ApprovalRequest, request_id)
    if approval_request is None or approval_request.tenant_id != str(tenant.id):
        raise _edo_not_found("approval_request")

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
        if route is None or str(route.tenant_id) != str(tenant.id):
            raise _edo_not_found("approval_route")
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
    return {"status": approval_request.status.value, "current_step_index": approval_request.current_step_index, "correlation_id": cid}


@router.post("/signatures")
@audit_operation("create", "signature")
async def create_signature(
    payload: SignatureCreate,
    request: Request,
    response: Response,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    access: AccessContext = AccessDep,
):
    cid = _correlation_id(request, response)
    if payload.type is not SignatureType.INTERNAL:
        raise _provider_not_configured("signature")
    doc_ver = await session.get(DocumentVersion, payload.document_version_id)
    if doc_ver is None or str(doc_ver.tenant_id) != str(tenant.id):
        raise _edo_not_found("document_version")
    svc = PepSigningService(session, str(tenant.id))
    try:
        req, _code = await svc.create_request(
            object_type="document_version",
            object_id=payload.document_version_id,
            purpose="document",
            requested_by=str(access.user.id),
            signer_user_id=str(access.user.id),
        )
    except PepNotFound:
        raise _edo_not_found("document_version")
    except PepConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_problem_detail(code="PEP_CONFLICT", message=str(exc), error_type="edo"),
        ) from exc
    await session.commit()
    return {
        "id": req.id,
        "status": req.status,
        "receipts_s3_key": None,
        "correlation_id": cid,
    }


@router.post("/sign/request")
@audit_operation("request", "signature")
async def sign_request(
    payload: SignatureRequestIn,
    request: Request,
    response: Response,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    access: AccessContext = AccessDep,
):
    return await create_signature(SignatureCreate(document_version_id=payload.document_version_id, type=payload.kind), request, response, session, tenant, access)


@router.post("/sign/submit")
@audit_operation("submit", "signature")
async def sign_submit(
    payload: SignatureSubmitIn,
    request: Request,
    response: Response,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    access: AccessContext = AccessDep,
):
    cid = _correlation_id(request, response)
    if payload.kind is not SignatureType.INTERNAL:
        raise _provider_not_configured("signature")
    doc_ver = await session.get(DocumentVersion, payload.document_version_id)
    if doc_ver is None or str(doc_ver.tenant_id) != str(tenant.id):
        raise _edo_not_found("document_version")
    svc = PepSigningService(session, str(tenant.id))
    try:
        req, _code = await svc.create_request(
            object_type="document_version",
            object_id=payload.document_version_id,
            purpose="document",
            requested_by=str(access.user.id),
            signer_user_id=str(access.user.id),
        )
    except PepNotFound:
        raise _edo_not_found("document_version")
    except PepConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_problem_detail(code="PEP_CONFLICT", message=str(exc), error_type="edo"),
        ) from exc
    await session.commit()
    return {"id": req.id, "status": req.status, "correlation_id": cid}


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
    idem_service, replay = await _idempotent_or_replay(
        request=request, response=response, session=session, tenant=tenant, user_id=str(access.user.id), model=payload
    )
    if replay is not None:
        return replay
    raise _provider_not_configured("edo")


@router.get("/edo-workflow/messages")
async def edo_messages_v1(
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
    response: Response,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
):
    return await edo_webhook("internal-fallback", payload, request, response, session, tenant, None)


@router.post("/edo/webhooks/{provider_code}")
@audit_operation("ingest_webhook", "edo_webhook")
async def edo_webhook(
    provider_code: str,
    payload: EdoWebhookPayload,
    request: Request,
    response: Response,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    x_signature: str | None = Header(default=None, alias="X-Signature"),
):
    cid = _correlation_id(request, response)
    raw = await request.body()
    configured_secret = (tenant.settings or {}).get("edo_webhook_secret")
    if configured_secret:
        expected = hmac.new(str(configured_secret).encode("utf-8"), raw, hashlib.sha256).hexdigest()
        if x_signature and not hmac.compare_digest(expected, x_signature):
            raise _edo_unauthorized("Invalid webhook signature")

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
        return {"status": "duplicate", "correlation_id": cid, **provider_response_meta(provider_code)}

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
    return {"status": "accepted", "correlation_id": cid, **provider_response_meta(provider_code)}
