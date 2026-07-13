from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.api.deps.tracing import get_trace_id
from app.core.audit_decorator import audit_operation
from app.core.errors import api_problem_detail
from app.core.security import abac
from app.models.approval_signing import (
    ApprovalDecisionLog,
    ApprovalProcess,
    ApprovalProcessStatus,
    ApprovalRoute,
    ApprovalTask,
    ApprovalTaskStatus,
    SignatureRequest,
    WebhookEndpoint,
)
from app.models.models import IdempotencyStatus, UserRole
from app.models.tenanting import Tenant
from app.modules.approval.core import cond_matches, make_request_hash
from app.services.idempotency import IdempotencyService, normalize_idempotency_key
from app.services.outbox import OutboxService
from app.services.pep_signing import PepConflict, PepNotFound, PepSigningService
from app.services.provider_registry import provider_response_meta


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> UUID | None:
    return getattr(tenant, "id", None)


# The bespoke X-User-Id assignee check below is not authentication (the header is
# attacker-controlled). Enforce real authn + roles at router level for every route,
# mirroring approval_orchestration / pep_signing (admin/employee).
_ApprovalSigningAccess = Depends(
    abac(_tenant_resource_id, required_roles=["admin", "employee"], action="approval signing")
)

router = APIRouter(dependencies=[_ApprovalSigningAccess])


def _approval_signing_error(*, code: str, message: str, status_code: int) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=api_problem_detail(code=code, message=message, error_type="approval_signing"),
    )


def _approval_signing_unprocessable(message: str) -> HTTPException:
    return _approval_signing_error(
        code="APPROVAL_SIGNING_VALIDATION_ERROR",
        message=message,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


def _approval_signing_not_found(resource: str) -> HTTPException:
    return _approval_signing_error(
        code="APPROVAL_SIGNING_NOT_FOUND",
        message=f"{resource} not found",
        status_code=status.HTTP_404_NOT_FOUND,
    )


def _approval_signing_forbidden(message: str) -> HTTPException:
    return _approval_signing_error(
        code="APPROVAL_SIGNING_FORBIDDEN",
        message=message,
        status_code=status.HTTP_403_FORBIDDEN,
    )


def _approval_signing_conflict(message: str) -> HTTPException:
    return _approval_signing_error(
        code="APPROVAL_SIGNING_CONFLICT",
        message=message,
        status_code=status.HTTP_409_CONFLICT,
    )


def _provider_not_configured(kind: str) -> HTTPException:
    """Честный отказ вместо симуляции (зеркало edo_workflow._provider_not_configured).

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


def _pep_conflict(exc: PepConflict) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=api_problem_detail(code="PEP_CONFLICT", message=str(exc), error_type="edo"),
    )


def _status_str(value: Any) -> str:
    """Диалект-безопасная строка статуса: после ed01 колонка status — VARCHAR,
    из БД приходит str; до flush может попасться enum-инстанс."""
    return str(getattr(value, "value", value))


def _correlation_id(request: Request, response: Response) -> str:
    value = get_trace_id(request)
    response.headers["X-Trace-Id"] = value
    response.headers["X-Correlation-Id"] = value
    response.headers["X-Request-Id"] = value
    return value


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
    provider: str = "internal-fallback"
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
    provider: str = "internal-fallback"
    operator_code: str | None = None
    recipient: str | None = None
    meta: dict[str, Any] | None = None


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


async def _create_tasks(
    session: AsyncSession, process: ApprovalProcess, route: ApprovalRoute, step_no: int
) -> None:
    steps = route.steps or []
    if step_no >= len(steps):
        process.status = ApprovalProcessStatus.APPROVED
        process.finished_at = datetime.now(timezone.utc)
        await OutboxService(session).enqueue(
            tenant_id=process.tenant_id,
            event_type="approval.completed",
            payload={
                "event_id": str(uuid4()),
                "tenant_id": process.tenant_id,
                "metadata": {"process_id": process.id, "status": process.status.value},
            },
        )
        return
    step = steps[step_no]
    due = datetime.now(timezone.utc)
    if step.get("due_days"):
        due += timedelta(days=int(step["due_days"]))
    if step.get("due_hours"):
        due += timedelta(hours=int(step["due_hours"]))
    if step.get("type") == "user":
        session.add(
            ApprovalTask(
                tenant_id=process.tenant_id,
                process_id=process.id,
                step_no=step_no,
                assignee_type="user",
                assignee_id=step["user_id"],
                due_at=due,
            )
        )
        return
    role_code = step.get("role_code")
    users = (
        (
            await session.execute(
                select(UserRole.user_id).where(
                    UserRole.tenant_id == process.tenant_id, UserRole.role == role_code
                )
            )
        )
        .scalars()
        .all()
    )
    for uid in users:
        session.add(
            ApprovalTask(
                tenant_id=process.tenant_id,
                process_id=process.id,
                step_no=step_no,
                assignee_type="user",
                assignee_id=uid,
                due_at=due,
            )
        )


@router.post("/approvals:start")
@audit_operation("start", "approval_process", id_attr="process_id")
async def approvals_start(
    payload: ApprovalStartIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    x_user_id: str = Header(default="system", alias="X-User-Id"),
):
    cid = _correlation_id(request, response)
    key = request.headers.get("Idempotency-Key")
    idem = None
    if key:
        idem = IdempotencyService(
            session=session, tenant_id=str(tenant.id), endpoint=request.url.path
        )
        norm = normalize_idempotency_key(key)
        rec, _ = await idem.acquire(
            key=norm,
            request_hash=make_request_hash(
                request.url.path, str(tenant.id), x_user_id, payload.model_dump(mode="json")
            ),
            method="POST",
            path=request.url.path,
        )
        if rec.status == IdempotencyStatus.SUCCEEDED:
            return rec.result_json["body"]
    routes = (
        (
            await session.execute(
                select(ApprovalRoute).where(
                    ApprovalRoute.tenant_id == str(tenant.id), ApprovalRoute.is_active.is_(True)
                )
            )
        )
        .scalars()
        .all()
    )
    ranked = sorted(
        ((r.priority, cond_matches(r.conditions or {}, payload.context), r) for r in routes),
        key=lambda i: (i[0], i[1]),
        reverse=True,
    )
    route = next((r for _, m, r in ranked if m >= 0), None)
    if route is None:
        raise _approval_signing_conflict("No matching route")
    process = ApprovalProcess(
        tenant_id=str(tenant.id),
        object_type=payload.object_type,
        object_id=payload.object_id,
        route_id=route.id,
        status=ApprovalProcessStatus.IN_PROGRESS,
        started_at=datetime.now(timezone.utc),
        created_by=x_user_id,
    )
    session.add(process)
    await session.flush()
    await _create_tasks(session, process, route, 0)
    await OutboxService(session).enqueue(
        tenant_id=str(tenant.id),
        event_type="approval.started",
        payload={
            "event_id": str(uuid4()),
            "tenant_id": str(tenant.id),
            "metadata": {"process_id": process.id},
        },
    )
    body = {
        "process_id": process.id,
        "route_id": route.id,
        "status": process.status.value,
        "correlation_id": cid,
    }
    if idem:
        await idem.store_success(rec, status_code=200, body=body)
    return body


@router.get("/approvals/processes")
async def approval_processes(
    status: str | None = None,
    object_id: str | None = None,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
):
    stmt = select(ApprovalProcess).where(ApprovalProcess.tenant_id == str(tenant.id))
    if status:
        stmt = stmt.where(ApprovalProcess.status == status)
    if object_id:
        stmt = stmt.where(ApprovalProcess.object_id == object_id)
    items = (
        (await session.execute(stmt.order_by(ApprovalProcess.created_at.desc()))).scalars().all()
    )
    return {
        "items": [
            {
                "id": i.id,
                "status": i.status.value,
                "object_id": i.object_id,
                "current_step": i.current_step,
            }
            for i in items
        ]
    }


@router.get("/approvals/processes/{process_id}")
async def approval_process_detail(
    process_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
):
    p = await session.get(ApprovalProcess, process_id)
    if not p or p.tenant_id != str(tenant.id):
        raise _approval_signing_not_found("process")
    logs = (
        (
            await session.execute(
                select(ApprovalDecisionLog)
                .where(
                    ApprovalDecisionLog.tenant_id == str(tenant.id),
                    ApprovalDecisionLog.process_id == process_id,
                )
                .order_by(ApprovalDecisionLog.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return {
        "id": p.id,
        "status": p.status.value,
        "route_id": p.route_id,
        "current_step": p.current_step,
        "logs": [
            {"decision": log.decision, "comment": log.comment, "step_no": log.step_no}
            for log in logs
        ],
    }


@router.get("/approvals/process-tasks")
async def approval_tasks(
    mine: bool = True,
    status: str = "open",
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    x_user_id: str = Header(default="system", alias="X-User-Id"),
):
    stmt = select(ApprovalTask).where(
        ApprovalTask.tenant_id == str(tenant.id), ApprovalTask.status == status
    )
    if mine:
        stmt = stmt.where(ApprovalTask.assignee_id == x_user_id)
    rows = (await session.execute(stmt.order_by(ApprovalTask.created_at.desc()))).scalars().all()
    return {
        "items": [
            {
                "id": t.id,
                "process_id": t.process_id,
                "status": t.status.value,
                "due_at": t.due_at.isoformat() if t.due_at else None,
            }
            for t in rows
        ]
    }


@router.post("/approvals/tasks/{task_id}:decide")
@audit_operation("decide", "approval_task")
async def approval_decide(
    task_id: str,
    payload: DecideIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    x_user_id: str = Header(default="system", alias="X-User-Id"),
):
    cid = _correlation_id(request, response)
    task = await session.get(ApprovalTask, task_id)
    if not task or task.tenant_id != str(tenant.id):
        raise _approval_signing_not_found("task")
    if task.assignee_id != x_user_id:
        raise _approval_signing_forbidden("Task assignee mismatch")
    # Only an OPEN task may be decided; re-deciding a DONE/CANCELED/EXPIRED task would
    # re-advance the process and spawn duplicate next-step tasks.
    if task.status is not ApprovalTaskStatus.OPEN:
        raise _approval_signing_conflict("Task is not open")
    process = await session.get(ApprovalProcess, task.process_id)
    if process is None or str(process.tenant_id) != str(tenant.id):
        raise _approval_signing_not_found("process")
    route = await session.get(ApprovalRoute, process.route_id)
    if route is None or str(route.tenant_id) != str(tenant.id):
        raise _approval_signing_not_found("route")
    task.status = ApprovalTaskStatus.DONE
    task.decision = payload.decision
    task.comment = payload.comment
    task.decided_at = datetime.now(timezone.utc)
    session.add(
        ApprovalDecisionLog(
            tenant_id=str(tenant.id),
            process_id=process.id,
            task_id=task.id,
            step_no=task.step_no,
            actor_user_id=x_user_id,
            decision=payload.decision,
            comment=payload.comment,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    if payload.decision == "reject":
        process.status = ApprovalProcessStatus.REJECTED
        process.finished_at = datetime.now(timezone.utc)
        await session.execute(
            ApprovalTask.__table__.update()
            .where(
                and_(
                    ApprovalTask.process_id == process.id,
                    ApprovalTask.status == ApprovalTaskStatus.OPEN,
                )
            )
            .values(status=ApprovalTaskStatus.CANCELED)
        )
        await OutboxService(session).enqueue(
            tenant_id=str(tenant.id),
            event_type="approval.completed",
            payload={
                "event_id": str(uuid4()),
                "tenant_id": str(tenant.id),
                "metadata": {"process_id": process.id, "status": "rejected"},
            },
        )
        return {"status": process.status.value, "correlation_id": cid}
    step = (route.steps or [])[task.step_no] if route.steps else {}
    quorum = int(step.get("quorum", 1))
    approved_count = await session.scalar(
        select(func.count())
        .select_from(ApprovalTask)
        .where(
            ApprovalTask.process_id == process.id,
            ApprovalTask.step_no == task.step_no,
            ApprovalTask.decision == "approve",
        )
    )
    if approved_count >= quorum:
        await session.execute(
            ApprovalTask.__table__.update()
            .where(
                and_(
                    ApprovalTask.process_id == process.id,
                    ApprovalTask.step_no == task.step_no,
                    ApprovalTask.status == ApprovalTaskStatus.OPEN,
                )
            )
            .values(status=ApprovalTaskStatus.CANCELED)
        )
        process.current_step = task.step_no + 1
        await _create_tasks(session, process, route, process.current_step)
    return {
        "status": process.status.value,
        "current_step": process.current_step,
        "correlation_id": cid,
    }


@router.post("/approvals/tasks/{task_id}:delegate")
@audit_operation("delegate", "approval_task", id_attr="new_task_id")
async def approval_delegate(
    task_id: str,
    payload: DelegateIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    x_user_id: str = Header(default="system", alias="X-User-Id"),
):
    cid = _correlation_id(request, response)
    task = await session.get(ApprovalTask, task_id)
    if not task or task.tenant_id != str(tenant.id):
        raise _approval_signing_not_found("task")
    if task.assignee_id != x_user_id:
        raise _approval_signing_forbidden("Task assignee mismatch")
    task.status = ApprovalTaskStatus.CANCELED
    new_task = ApprovalTask(
        tenant_id=str(tenant.id),
        process_id=task.process_id,
        step_no=task.step_no,
        assignee_type="user",
        assignee_id=payload.to_user_id,
        due_at=task.due_at,
        delegated_from=task.id,
    )
    session.add(new_task)
    session.add(
        ApprovalDecisionLog(
            tenant_id=str(tenant.id),
            process_id=task.process_id,
            task_id=task.id,
            step_no=task.step_no,
            actor_user_id=x_user_id,
            decision="delegate",
            comment=payload.reason,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    return {"status": "delegated", "new_task_id": new_task.id, "correlation_id": cid}


@router.post("/approvals/processes/{process_id}:cancel")
@audit_operation("cancel", "approval_process")
async def approval_cancel(
    process_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
):
    p = await session.get(ApprovalProcess, process_id)
    if not p or p.tenant_id != str(tenant.id):
        raise _approval_signing_not_found("process")
    p.status = ApprovalProcessStatus.CANCELED
    p.finished_at = datetime.now(timezone.utc)
    await session.execute(
        ApprovalTask.__table__.update()
        .where(
            and_(
                ApprovalTask.process_id == process_id,
                ApprovalTask.status == ApprovalTaskStatus.OPEN,
            )
        )
        .values(status=ApprovalTaskStatus.CANCELED)
    )
    return {"status": p.status.value}


@router.post("/sign:request")
@audit_operation("request", "signature_request", id_attr="signature_request_id")
async def sign_request(
    payload: SignRequestIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    x_user_id: str = Header(default="system", alias="X-User-Id"),
):
    cid = _correlation_id(request, response)
    object_id = _require_document_object_id(payload.document_version_id, payload.object_id)
    key = request.headers.get("Idempotency-Key")
    idem = None
    if key:
        idem = IdempotencyService(
            session=session, tenant_id=str(tenant.id), endpoint=request.url.path
        )
        rec, _ = await idem.acquire(
            key=normalize_idempotency_key(key),
            request_hash=make_request_hash(
                request.url.path, str(tenant.id), x_user_id, payload.model_dump(mode="json")
            ),
            method="POST",
            path=request.url.path,
        )
        if rec.status == IdempotencyStatus.SUCCEEDED:
            return rec.result_json["body"]
    if payload.provider != "internal-fallback":
        # Внешние провайдеры подписи не сконфигурированы — честный 409 вместо
        # прежнего мгновенного SIGNED (симуляция, вычищена в ЭДО Срез-1).
        raise _provider_not_configured("signature")
    svc = PepSigningService(session, str(tenant.id))
    try:
        req, _code = await svc.create_request(
            object_type="document_version",
            object_id=object_id,
            purpose="document",
            requested_by=x_user_id,
            signer_user_id=x_user_id,
        )
    except PepNotFound:
        raise _approval_signing_not_found("document_version")
    except PepConflict as exc:
        raise _pep_conflict(exc) from exc
    body = {
        "signature_request_id": req.id,
        "status": _status_str(req.status),
        "correlation_id": cid,
        **provider_response_meta(payload.provider),
    }
    if idem:
        await idem.store_success(rec, status_code=200, body=body)
    return body


@router.get("/sign/requests")
async def sign_requests(
    status: str | None = None,
    object_id: str | None = None,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
):
    stmt = select(SignatureRequest).where(SignatureRequest.tenant_id == str(tenant.id))
    if status:
        stmt = stmt.where(SignatureRequest.status == status)
    if object_id:
        stmt = stmt.where(SignatureRequest.object_id == object_id)
    rows = (
        (await session.execute(stmt.order_by(SignatureRequest.created_at.desc()))).scalars().all()
    )
    return {
        "items": [
            {
                "id": r.id,
                "status": _status_str(r.status),
                "provider": r.provider,
                **provider_response_meta(r.provider),
            }
            for r in rows
        ]
    }


@router.get("/sign/requests/{request_id}")
async def sign_request_get(
    request_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
):
    row = await session.get(SignatureRequest, request_id)
    if not row or row.tenant_id != str(tenant.id):
        raise _approval_signing_not_found("signature_request")
    return {"id": row.id, "status": _status_str(row.status), "result_json": row.result_json}


@router.post("/edo:send")
@audit_operation("send", "edo_envelope")
async def edo_send(
    payload: EdoSendIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
):
    _correlation_id(request, response)
    key = request.headers.get("Idempotency-Key")
    if key:
        idem = IdempotencyService(
            session=session, tenant_id=str(tenant.id), endpoint="approval.edo_send"
        )
        rec, created = await idem.acquire(
            key=normalize_idempotency_key(key),
            request_hash=make_request_hash(
                request.url.path, str(tenant.id), None, payload.model_dump(mode="json")
            ),
            method="POST",
            path=request.url.path,
        )
        if not created and rec.status == IdempotencyStatus.SUCCEEDED:
            return rec.result_json["body"]
    # Внешний ЭДО-оператор не сконфигурирован — честный 409, ничего не пишем
    # (прежняя симуляция SENT→DELIVERED вычищена в ЭДО Срез-1).
    raise _provider_not_configured("edo")


@router.get("/edo/envelopes")
async def edo_list(
    status: str | None = None,
    object_id: str | None = None,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
):
    # Легаси-таблица edo_envelopes дропнута (ed02): конвертов не существует.
    return {"items": []}


@router.get("/edo/envelopes/{envelope_id}")
async def edo_get(
    envelope_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
):
    raise _approval_signing_not_found("envelope")


@router.post("/edo/webhooks/{provider}")
@audit_operation("ingest_webhook", "edo_webhook")
async def edo_webhook(
    provider: str,
    payload: dict[str, Any],
    request: Request,
    response: Response,
    x_signature: str | None = Header(default=None, alias="X-Signature"),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
):
    _correlation_id(request, response)
    # Провайдер не сконфигурирован — входящих вебхуков быть не может.
    raise _provider_not_configured("edo")


@router.post("/approvals/start")
async def approvals_start_v1(
    payload: ApprovalStartIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    x_user_id: str = Header(default="system", alias="X-User-Id"),
):
    return await approvals_start(payload, request, response, session, tenant, x_user_id)


@router.get("/approvals/instances")
async def approval_instances(
    document_version_id: str | None = None,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
):
    items = (
        (
            await session.execute(
                select(ApprovalProcess)
                .where(
                    ApprovalProcess.tenant_id == str(tenant.id),
                    ApprovalProcess.object_id == (document_version_id or ApprovalProcess.object_id),
                )
                .order_by(ApprovalProcess.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return {
        "items": [
            {
                "id": i.id,
                "document_version_id": i.object_id,
                "status": i.status.value,
                "started_at": i.started_at,
                "finished_at": i.finished_at,
            }
            for i in items
        ]
    }


@router.get("/approvals/tasks")
async def approval_tasks_v1(
    mine: int = 1,
    status: str = "pending",
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    x_user_id: str = Header(default="system", alias="X-User-Id"),
):
    stmt = select(ApprovalTask).where(ApprovalTask.tenant_id == str(tenant.id))
    if mine:
        stmt = stmt.where(ApprovalTask.assignee_id == x_user_id)
    stmt = stmt.where(
        ApprovalTask.status
        == (ApprovalTaskStatus.OPEN if status == "pending" else ApprovalTaskStatus.DONE)
    )
    items = (await session.execute(stmt.order_by(ApprovalTask.created_at.desc()))).scalars().all()
    return {
        "items": [
            {
                "id": t.id,
                "instance_id": t.process_id,
                "status": "pending" if t.status == ApprovalTaskStatus.OPEN else "approved",
                "assignee_user_id": t.assignee_id,
                "deadline_at": t.due_at,
            }
            for t in items
        ]
    }


@router.post("/approvals/tasks/{task_id}/decision")
async def approval_decision_v1(
    task_id: str,
    payload: DecideIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    x_user_id: str = Header(default="system", alias="X-User-Id"),
):
    if payload.delegate_to_user_id:
        return await approval_delegate(
            task_id,
            DelegateIn(to_user_id=payload.delegate_to_user_id, reason=payload.comment),
            request,
            response,
            session,
            tenant,
            x_user_id,
        )
    return await approval_decide(
        task_id,
        DecideIn(decision=payload.decision, comment=payload.comment),
        request,
        response,
        session,
        tenant,
        x_user_id,
    )


@router.post("/sign/request")
async def sign_request_v1(
    payload: SignRequestIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    x_user_id: str = Header(default="system", alias="X-User-Id"),
):
    return await sign_request(payload, request, response, session, tenant, x_user_id)


@router.post("/sign/submit")
@audit_operation("submit", "signature_request")
async def sign_submit_v1(
    payload: SignSubmitIn,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    x_user_id: str = Header(default="system", alias="X-User-Id"),
):
    cert_info = payload.cert_info or {}
    _validate_certificate_period(cert_info)
    if payload.kind != "internal":
        # Внешние виды подписи (un_ep/kep/...) не сконфигурированы — честный 409
        # (зеркало edo_workflow.sign_submit; прежний мгновенный SIGNED — симуляция).
        raise _provider_not_configured("signature")
    svc = PepSigningService(session, str(tenant.id))
    try:
        req, _code = await svc.create_request(
            object_type="document_version",
            object_id=payload.document_version_id,
            purpose="document",
            requested_by=x_user_id,
            signer_user_id=x_user_id,
        )
    except PepNotFound:
        raise _approval_signing_not_found("document_version")
    except PepConflict as exc:
        raise _pep_conflict(exc) from exc
    return {"id": req.id, "status": _status_str(req.status)}


@router.get("/sign/status")
async def sign_status_v1(
    document_version_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
):
    rows = (
        (
            await session.execute(
                select(SignatureRequest)
                .where(
                    SignatureRequest.tenant_id == str(tenant.id),
                    SignatureRequest.object_id == document_version_id,
                )
                .order_by(SignatureRequest.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return {
        "items": [
            {
                "id": s.id,
                "status": _status_str(s.status),
                "payload": s.payload_json,
                "result": s.result_json,
            }
            for s in rows
        ]
    }


@router.post("/edo/send")
async def edo_send_v1(
    payload: EdoSendIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
):
    return await edo_send(payload, request, response, session, tenant)


@router.get("/edo/messages")
async def edo_messages_v1(
    document_version_id: str | None = None,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
):
    # Легаси-таблица edo_envelopes дропнута (ed02): сообщений не существует.
    return {"items": []}


@router.post("/edo/webhook/status")
@audit_operation("ingest_webhook", "edo_status")
async def edo_webhook_status(
    payload: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
):
    # Провайдер не сконфигурирован — входящих статусов быть не может.
    raise _provider_not_configured("edo")


@router.get("/approvals/routes")
async def approval_routes_v1(
    session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)
):
    rows = (
        (
            await session.execute(
                select(ApprovalRoute)
                .where(ApprovalRoute.tenant_id == str(tenant.id))
                .order_by(ApprovalRoute.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return {
        "items": [
            {
                "id": r.id,
                "code": r.code,
                "name": r.name,
                "conditions": r.conditions,
                "steps": r.steps,
                "is_active": r.is_active,
            }
            for r in rows
        ]
    }


@router.post("/approvals/routes")
@audit_operation("create", "approval_route")
async def approval_routes_create_v1(
    payload: ApprovalRouteIn,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
):
    row = ApprovalRoute(
        tenant_id=str(tenant.id),
        code=payload.code,
        name=payload.name,
        conditions=payload.conditions,
        steps=payload.steps,
        is_active=payload.is_active,
        priority=payload.priority,
        version=1,
    )
    session.add(row)
    await session.flush()
    return {"id": row.id, "code": row.code, "name": row.name}


@router.patch("/approvals/routes/{route_id}")
@audit_operation("update", "approval_route")
async def approval_routes_patch_v1(
    route_id: str,
    payload: ApprovalRouteIn,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
):
    row = await session.get(ApprovalRoute, route_id)
    if not row or row.tenant_id != str(tenant.id):
        raise _approval_signing_not_found("route")
    row.name = payload.name
    row.conditions = payload.conditions
    row.steps = payload.steps
    row.is_active = payload.is_active
    row.priority = payload.priority
    row.version = int((row.version or 1) + 1)
    return {"id": row.id, "code": row.code, "name": row.name, "version": row.version}


@router.get("/webhooks")
async def webhooks_v1(
    session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)
):
    rows = (
        (
            await session.execute(
                select(WebhookEndpoint)
                .where(WebhookEndpoint.tenant_id == str(tenant.id))
                .order_by(WebhookEndpoint.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return {
        "items": [
            {
                "id": r.id,
                "event_type": (r.subscribed_events or [None])[0],
                "url": r.url,
                "is_active": r.is_enabled,
            }
            for r in rows
        ]
    }


@router.post("/webhooks")
@audit_operation("create", "webhook_endpoint")
async def webhooks_create_v1(
    payload: WebhookSubscriptionIn,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
):
    row = WebhookEndpoint(
        tenant_id=str(tenant.id),
        name=f"{payload.event_type} subscription",
        url=payload.url,
        secret=payload.secret,
        is_enabled=True,
        subscribed_events=[payload.event_type],
    )
    session.add(row)
    await session.flush()
    return {
        "id": row.id,
        "event_type": payload.event_type,
        "url": row.url,
        "is_active": row.is_enabled,
    }


@router.patch("/webhooks/{webhook_id}/disable")
@audit_operation("disable", "webhook_endpoint")
async def webhooks_disable_v1(
    webhook_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
):
    row = await session.get(WebhookEndpoint, webhook_id)
    if not row or row.tenant_id != str(tenant.id):
        raise _approval_signing_not_found("webhook")
    row.is_enabled = False
    return {"id": row.id, "is_active": row.is_enabled}
