from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_correlation_id, get_session, get_tenant_record
from app.api.models.webhook_admin import (
    WebhookDeliveryWithDiagnostics,
    WebhookFailureDiagnostics,
    WebhookRetryEligibility,
)
from app.api.tenant_row_http import enforce_row_belongs_to_tenant
from app.core.audit_decorator import audit_operation
from app.core.config import get_settings
from app.core.errors import api_problem_detail
from app.core.inbound_webhook_auth import verify_inbound_webhook_body_hmac
from app.core.secret_cipher import encrypt_secret
from app.core.security import AccessContext, rbac
from app.core.tenant_validation import TenantContextValidator
from app.db.session import rearm_session_tenant_context
from app.models.job_engine import InboundWebhookDedup
from app.models.models import Outbox, OutboxStatus, Tenant, WebhookDelivery, WebhookEndpoint
from app.services.inbound_dedup import compute_inbound_dedup_key
from app.services.webhook_retry_telemetry import (
    FailureCategory,
    classify_failure,
)
from app.tasks import process_inbound_webhook

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_WEBHOOK_ENDPOINT_NOT_FOUND = api_problem_detail(
    code="WEBHOOK_ENDPOINT_NOT_FOUND",
    message="Webhook endpoint not found",
    error_type="webhooks",
)
_WEBHOOK_DELIVERY_NOT_FOUND = api_problem_detail(
    code="WEBHOOK_DELIVERY_NOT_FOUND",
    message="Delivery not found",
    error_type="webhooks",
)
_OUTBOX_EVENT_NOT_FOUND = api_problem_detail(
    code="OUTBOX_EVENT_NOT_FOUND",
    message="Outbox event not found",
    error_type="webhooks",
)
_WEBHOOK_DELIVERY_ALREADY_SUCCEEDED = api_problem_detail(
    code="WEBHOOK_DELIVERY_ALREADY_SUCCEEDED",
    message="Already delivered successfully",
    error_type="webhooks",
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]
AdminAccess = Annotated[AccessContext, Depends(rbac(["admin", "owner", "integrations"]))]


class WebhookEndpointIn(BaseModel):
    name: str | None = None
    url: str
    secret: str | None = None
    enabled: bool = True
    subscribed_events: list[str] = Field(default_factory=list)
    timeout_ms: int = 5000
    headers: dict[str, Any] = Field(default_factory=dict)


class WebhookEndpointOut(BaseModel):
    id: str
    name: str | None = None
    url: str
    secret_masked: str | None = None
    enabled: bool
    subscribed_events: list[str]
    timeout_ms: int
    headers: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class WebhookEndpointCreateOut(WebhookEndpointOut):
    secret: str | None = None


class WebhookDeliveryOut(BaseModel):
    id: str
    event_id: str
    endpoint_id: str
    attempts: int
    status: str
    next_attempt_at: datetime | None = None
    response_status: int | None = None
    last_response_body: str | None = None
    last_error: dict[str, Any] | None = None
    latency_ms: int | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


def _mask_secret(secret: str | None) -> str | None:
    if not secret:
        return None
    if len(secret) <= 4:
        return "*" * len(secret)
    return f"{secret[:2]}***{secret[-2:]}"


def _to_endpoint_out(row: WebhookEndpoint) -> WebhookEndpointOut:
    return WebhookEndpointOut(
        id=row.id,
        name=row.name,
        url=row.url,
        secret_masked=_mask_secret(row.secret),
        enabled=row.is_enabled,
        subscribed_events=row.subscribed_events or [],
        timeout_ms=row.timeout_ms,
        headers=row.headers or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/endpoints", response_model=list[WebhookEndpointOut])
async def list_webhooks(
    tenant: TenantDep,
    _: AdminAccess,
    session: SessionDep,
    correlation_id: str = Depends(get_correlation_id),
) -> list[WebhookEndpointOut]:
    TenantContextValidator.ensure_tenant_context(tenant)

    rows = (
        (
            await session.execute(
                select(WebhookEndpoint)
                .where(WebhookEndpoint.tenant_id == tenant.id)
                .order_by(WebhookEndpoint.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_to_endpoint_out(row) for row in rows]


@router.post(
    "/endpoints", response_model=WebhookEndpointCreateOut, status_code=status.HTTP_201_CREATED
)
@audit_operation("create", "webhook_endpoint")
async def create_webhook(
    payload: WebhookEndpointIn,
    tenant: TenantDep,
    _: AdminAccess,
    session: SessionDep,
    correlation_id: str = Depends(get_correlation_id),
) -> WebhookEndpointOut:
    TenantContextValidator.ensure_tenant_context(tenant)

    generated_secret = payload.secret or secrets.token_urlsafe(32)
    row = WebhookEndpoint(
        tenant_id=tenant.id,
        name=payload.name,
        url=payload.url,
        secret=encrypt_secret(generated_secret, tenant_id=str(tenant.id)),  # SEC-67
        is_enabled=payload.enabled,
        subscribed_events=payload.subscribed_events,
        timeout_ms=payload.timeout_ms,
        headers=payload.headers,
    )
    session.add(row)
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before refresh (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(row)
    return WebhookEndpointCreateOut(**_to_endpoint_out(row).model_dump(), secret=generated_secret)


@router.patch("/endpoints/{webhook_id}", response_model=WebhookEndpointOut)
@audit_operation("update", "webhook_endpoint")
async def update_webhook(
    webhook_id: str,
    payload: WebhookEndpointIn,
    tenant: TenantDep,
    _: AdminAccess,
    session: SessionDep,
    correlation_id: str = Depends(get_correlation_id),
) -> WebhookEndpointOut:
    TenantContextValidator.ensure_tenant_context(tenant)

    row = await session.get(WebhookEndpoint, webhook_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_WEBHOOK_ENDPOINT_NOT_FOUND)
    enforce_row_belongs_to_tenant(
        session,
        row,
        tenant_id=str(tenant.id),
        mismatch_event="api.webhooks.endpoint_by_id.tenant_scope_mismatch",
        detail="webhook_not_found",
    )
    row.name = payload.name
    row.url = payload.url
    # Сохраняем существующий секрет, если новый не передан (SEC-67: шифруем новый)
    row.secret = (
        encrypt_secret(payload.secret, tenant_id=str(row.tenant_id or "") or None)
        if payload.secret
        else row.secret
    )
    row.is_enabled = payload.enabled
    row.subscribed_events = payload.subscribed_events
    row.timeout_ms = payload.timeout_ms
    row.headers = payload.headers
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before refresh (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(row)
    return _to_endpoint_out(row)


@router.delete(
    "/endpoints/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
@audit_operation("delete", "webhook_endpoint")
async def delete_webhook(
    webhook_id: str,
    tenant: TenantDep,
    _: AdminAccess,
    session: SessionDep,
    correlation_id: str = Depends(get_correlation_id),
) -> None:
    TenantContextValidator.ensure_tenant_context(tenant)

    row = await session.get(WebhookEndpoint, webhook_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_WEBHOOK_ENDPOINT_NOT_FOUND)
    enforce_row_belongs_to_tenant(
        session,
        row,
        tenant_id=str(tenant.id),
        mismatch_event="api.webhooks.endpoint_by_id.tenant_scope_mismatch",
        detail="webhook_not_found",
    )
    await session.delete(row)
    await session.commit()


@router.post("/endpoints/{webhook_id}:rotate-secret", response_model=WebhookEndpointCreateOut)
@audit_operation("rotate_secret", "webhook_endpoint")
async def rotate_webhook_secret(
    webhook_id: str,
    tenant: TenantDep,
    _: AdminAccess,
    session: SessionDep,
    correlation_id: str = Depends(get_correlation_id),
) -> WebhookEndpointCreateOut:
    TenantContextValidator.ensure_tenant_context(tenant)

    row = await session.get(WebhookEndpoint, webhook_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_WEBHOOK_ENDPOINT_NOT_FOUND)
    enforce_row_belongs_to_tenant(
        session,
        row,
        tenant_id=str(tenant.id),
        mismatch_event="api.webhooks.endpoint_by_id.tenant_scope_mismatch",
        detail="webhook_not_found",
    )
    new_secret = secrets.token_urlsafe(32)
    # Область ключа берём У СТРОКИ, а не у запроса: глобальная подписка
    # (tenant_id IS NULL) обязана шифроваться платформенной областью, иначе
    # её секрет перестанет читаться в фоновой доставке.
    row.secret = encrypt_secret(new_secret, tenant_id=str(row.tenant_id or "") or None)
    row.updated_at = datetime.now(timezone.utc)
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before refresh (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(row)
    return WebhookEndpointCreateOut(**_to_endpoint_out(row).model_dump(), secret=new_secret)


@router.post("/endpoints/{webhook_id}:disable", response_model=WebhookEndpointOut)
@audit_operation("disable", "webhook_endpoint")
async def disable_webhook(
    webhook_id: str,
    tenant: TenantDep,
    _: AdminAccess,
    session: SessionDep,
    correlation_id: str = Depends(get_correlation_id),
) -> WebhookEndpointOut:
    TenantContextValidator.ensure_tenant_context(tenant)

    row = await session.get(WebhookEndpoint, webhook_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_WEBHOOK_ENDPOINT_NOT_FOUND)
    enforce_row_belongs_to_tenant(
        session,
        row,
        tenant_id=str(tenant.id),
        mismatch_event="api.webhooks.endpoint_by_id.tenant_scope_mismatch",
        detail="webhook_not_found",
    )
    row.is_enabled = False
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before refresh (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(row)
    return _to_endpoint_out(row)


@router.post("/endpoints/{webhook_id}:enable", response_model=WebhookEndpointOut)
@audit_operation("enable", "webhook_endpoint")
async def enable_webhook(
    webhook_id: str,
    tenant: TenantDep,
    _: AdminAccess,
    session: SessionDep,
    correlation_id: str = Depends(get_correlation_id),
) -> WebhookEndpointOut:
    TenantContextValidator.ensure_tenant_context(tenant)

    row = await session.get(WebhookEndpoint, webhook_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_WEBHOOK_ENDPOINT_NOT_FOUND)
    enforce_row_belongs_to_tenant(
        session,
        row,
        tenant_id=str(tenant.id),
        mismatch_event="api.webhooks.endpoint_by_id.tenant_scope_mismatch",
        detail="webhook_not_found",
    )
    row.is_enabled = True
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before refresh (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(row)
    return _to_endpoint_out(row)


@router.get("/deliveries", response_model=list[WebhookDeliveryOut])
async def list_deliveries(
    tenant: TenantDep,
    _: AdminAccess,
    session: SessionDep,
    status_filter: str | None = Query(default=None, alias="status"),
    endpoint_id: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
) -> list[WebhookDeliveryOut]:
    TenantContextValidator.ensure_tenant_context(tenant)

    stmt = (
        select(WebhookDelivery, Outbox.event_type)
        .join(Outbox, Outbox.id == WebhookDelivery.event_id)
        .where(WebhookDelivery.tenant_id == tenant.id)
    )
    if status_filter:
        stmt = stmt.where(WebhookDelivery.status == status_filter)
    if endpoint_id:
        stmt = stmt.where(WebhookDelivery.endpoint_id == endpoint_id)
    if event_type:
        stmt = stmt.where(Outbox.event_type == event_type)
    rows = (await session.execute(stmt.order_by(WebhookDelivery.updated_at.desc()))).all()
    return [
        WebhookDeliveryOut(
            id=delivery.id,
            event_id=delivery.event_id,
            endpoint_id=delivery.endpoint_id,
            attempts=delivery.attempts,
            status=delivery.status,
            next_attempt_at=delivery.next_attempt_at,
            response_status=delivery.last_status_code,
            last_response_body=delivery.last_response_body,
            last_error=delivery.last_error,
            latency_ms=delivery.latency_ms,
            started_at=delivery.started_at,
            ended_at=delivery.ended_at,
        )
        for delivery, _ in rows
    ]


@router.get("/endpoints/{webhook_id}/deliveries", response_model=list[WebhookDeliveryOut])
async def list_endpoint_deliveries(
    webhook_id: str,
    tenant: TenantDep,
    _: AdminAccess,
    session: SessionDep,
    correlation_id: str = Depends(get_correlation_id),
) -> list[WebhookDeliveryOut]:
    TenantContextValidator.ensure_tenant_context(tenant)

    row = await session.get(WebhookEndpoint, webhook_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_WEBHOOK_ENDPOINT_NOT_FOUND)
    enforce_row_belongs_to_tenant(
        session,
        row,
        tenant_id=str(tenant.id),
        mismatch_event="api.webhooks.endpoint_by_id.tenant_scope_mismatch",
        detail="webhook_not_found",
    )
    rows = (
        (
            await session.execute(
                select(WebhookDelivery)
                .where(
                    WebhookDelivery.tenant_id == tenant.id,
                    WebhookDelivery.endpoint_id == webhook_id,
                )
                .order_by(WebhookDelivery.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        WebhookDeliveryOut(
            id=delivery.id,
            event_id=delivery.event_id,
            endpoint_id=delivery.endpoint_id,
            attempts=delivery.attempts,
            status=delivery.status,
            next_attempt_at=delivery.next_attempt_at,
            response_status=delivery.last_status_code,
            last_response_body=delivery.last_response_body,
            last_error=delivery.last_error,
            latency_ms=delivery.latency_ms,
            started_at=delivery.started_at,
            ended_at=delivery.ended_at,
        )
        for delivery in rows
    ]


@router.post("/endpoints/{webhook_id}:test")
@audit_operation("test", "webhook_endpoint")
async def test_endpoint(
    webhook_id: str,
    tenant: TenantDep,
    _: AdminAccess,
    session: SessionDep,
    correlation_id: str = Depends(get_correlation_id),
) -> dict[str, str]:
    TenantContextValidator.ensure_tenant_context(tenant)

    row = await session.get(WebhookEndpoint, webhook_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_WEBHOOK_ENDPOINT_NOT_FOUND)
    enforce_row_belongs_to_tenant(
        session,
        row,
        tenant_id=str(tenant.id),
        mismatch_event="api.webhooks.endpoint_by_id.tenant_scope_mismatch",
        detail="webhook_not_found",
    )
    event = Outbox(
        tenant_id=str(tenant.id),
        event_type="DocumentGenerated",
        destination=row.url,
        payload={
            "tenant_id": str(tenant.id),
            "event_id": f"test-{webhook_id}",
            "document_id": "test",
            "document_version_id": "test",
            "template_id": "test",
            "template_version_id": "test",
            "company_id": "test",
            "status": "generated",
        },
        headers={"X-Webhook-Endpoint-Id": row.id, "X-Correlation-Id": f"test-{webhook_id}"},
        idempotency_key=f"webhook-test:{webhook_id}:{datetime.now(timezone.utc).timestamp()}",
        status=OutboxStatus.PENDING,
        next_attempt_at=datetime.now(tz=timezone.utc),
    )
    session.add(event)
    await session.commit()
    return {"status": "queued"}


def _extract_failure_diagnostics(
    delivery: WebhookDelivery,
    max_attempts: int = 5,
    backoff_base: int = 5,
    backoff_max: int = 300,
) -> WebhookFailureDiagnostics | None:
    """Extract failure diagnostics from WebhookDelivery last_error payload.

    Args:
        delivery: WebhookDelivery record with last_error diagnostics.
        max_attempts: Maximum retry limit for context.
        backoff_base: Exponential backoff base for context.
        backoff_max: Maximum backoff cap for context.

    Returns:
        WebhookFailureDiagnostics if last_error contains structured diagnostics, else None.
    """
    if not delivery.last_error or not isinstance(delivery.last_error, dict):
        return None

    error = delivery.last_error
    category = error.get("failure_category") or "unknown"

    # Try to parse as enum, fall back to string
    try:
        failure_category = FailureCategory(category)
    except (ValueError, KeyError):
        failure_category = category  # type: ignore

    return WebhookFailureDiagnostics(
        failure_category=failure_category,
        retry_eligible=error.get("retry_eligible", False),
        http_status_code=error.get("http_status_code"),
        error_class=error.get("error_class"),
        error_message=error.get("error_message"),
        current_attempt=error.get("current_attempt", delivery.attempts),
        max_attempts=error.get("max_attempts", max_attempts),
        attempts_remaining=error.get(
            "attempts_remaining", max(0, max_attempts - delivery.attempts)
        ),
        next_attempt_in_seconds=error.get("next_attempt_in_seconds"),
        timestamp=error.get("timestamp"),
    )


@router.get("/deliveries/{delivery_id}/diagnostics", response_model=WebhookFailureDiagnostics)
async def get_delivery_diagnostics(
    delivery_id: str,
    tenant: TenantDep,
    _: AdminAccess,
    session: SessionDep,
) -> WebhookFailureDiagnostics:
    """Get failure diagnostics for a webhook delivery."""
    TenantContextValidator.ensure_tenant_context(tenant)

    delivery = await session.get(WebhookDelivery, delivery_id)
    if delivery is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_WEBHOOK_DELIVERY_NOT_FOUND)
    enforce_row_belongs_to_tenant(
        session,
        delivery,
        tenant_id=str(tenant.id),
        mismatch_event="api.webhooks.delivery_diagnostics.tenant_scope_mismatch",
        detail=_WEBHOOK_DELIVERY_NOT_FOUND,
    )

    diag = _extract_failure_diagnostics(delivery)
    if diag is None:
        # Return minimal diagnostics if none available
        category = classify_failure(status_code=delivery.last_status_code)
        diag = WebhookFailureDiagnostics(
            failure_category=category,
            retry_eligible=isinstance(category, FailureCategory)
            and category.value.startswith("retryable_"),
            http_status_code=delivery.last_status_code,
            current_attempt=delivery.attempts,
        )
    return diag


@router.get("/deliveries/{delivery_id}/retry-eligibility", response_model=WebhookRetryEligibility)
async def get_delivery_retry_eligibility(
    delivery_id: str,
    tenant: TenantDep,
    _: AdminAccess,
    session: SessionDep,
) -> WebhookRetryEligibility:
    """Check if a webhook delivery is eligible for retry."""
    TenantContextValidator.ensure_tenant_context(tenant)

    delivery = await session.get(WebhookDelivery, delivery_id)
    if delivery is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_WEBHOOK_DELIVERY_NOT_FOUND)
    enforce_row_belongs_to_tenant(
        session,
        delivery,
        tenant_id=str(tenant.id),
        mismatch_event="api.webhooks.delivery_retry_eligibility.tenant_scope_mismatch",
        detail=_WEBHOOK_DELIVERY_NOT_FOUND,
    )

    diag = _extract_failure_diagnostics(delivery)
    if diag is None:
        # Determine eligibility from status and last_status_code
        if delivery.status == "success":
            return WebhookRetryEligibility(
                delivery_id=delivery_id,
                eligible=False,
                reason="Delivery succeeded, no retry needed",
            )
        elif delivery.status == "pending":
            return WebhookRetryEligibility(
                delivery_id=delivery_id,
                eligible=True,
                reason="Delivery pending, retry already scheduled",
                next_attempt_in_seconds=(
                    int((delivery.next_attempt_at - datetime.now(tz=timezone.utc)).total_seconds())
                    if delivery.next_attempt_at
                    else None
                ),
            )
        else:
            # Infer from status code
            category = classify_failure(status_code=delivery.last_status_code)
            eligible = isinstance(category, FailureCategory) and category.value.startswith(
                "retryable_"
            )
            return WebhookRetryEligibility(
                delivery_id=delivery_id,
                eligible=eligible,
                reason=(
                    "Terminal failure, retries exhausted"
                    if not eligible
                    else "Transient failure, retryable"
                ),
                failure_category=category,
            )

    # Use structured diagnostics
    return WebhookRetryEligibility(
        delivery_id=delivery_id,
        eligible=diag.retry_eligible,
        reason=(
            f"{diag.failure_category}: {diag.error_message or 'See diagnostics for details'}"
            if not diag.retry_eligible
            else f"{diag.failure_category}: Retryable after {diag.next_attempt_in_seconds}s"
        ),
        failure_category=diag.failure_category,
        next_attempt_in_seconds=diag.next_attempt_in_seconds,
    )


@router.get(
    "/endpoints/{endpoint_id}/failed-deliveries",
    response_model=list[WebhookDeliveryWithDiagnostics],
)
async def list_failed_deliveries_with_diagnostics(
    endpoint_id: str,
    tenant: TenantDep,
    _: AdminAccess,
    session: SessionDep,
    limit: int = Query(default=50, le=500),
) -> list[WebhookDeliveryWithDiagnostics]:
    """List failed deliveries for an endpoint with retry diagnostics."""
    TenantContextValidator.ensure_tenant_context(tenant)

    endpoint = await session.get(WebhookEndpoint, endpoint_id)
    if endpoint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_WEBHOOK_ENDPOINT_NOT_FOUND)
    enforce_row_belongs_to_tenant(
        session,
        endpoint,
        tenant_id=str(tenant.id),
        mismatch_event="api.webhooks.failed_deliveries_endpoint.tenant_scope_mismatch",
        detail=_WEBHOOK_ENDPOINT_NOT_FOUND,
    )

    rows = (
        (
            await session.execute(
                select(WebhookDelivery)
                .where(
                    WebhookDelivery.tenant_id == tenant.id,
                    WebhookDelivery.endpoint_id == endpoint_id,
                    WebhookDelivery.status.in_(["failed", "pending"]),
                )
                .order_by(WebhookDelivery.updated_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    result = []
    for delivery in rows:
        diag = _extract_failure_diagnostics(delivery)
        result.append(
            WebhookDeliveryWithDiagnostics(
                id=delivery.id,
                event_id=delivery.event_id,
                endpoint_id=delivery.endpoint_id,
                attempts=delivery.attempts,
                status=delivery.status,
                next_attempt_at=delivery.next_attempt_at,
                response_status=delivery.last_status_code,
                last_response_body=delivery.last_response_body,
                latency_ms=delivery.latency_ms,
                started_at=delivery.started_at,
                ended_at=delivery.ended_at,
                diagnostics=diag,
            )
        )
    return result


@router.post("/deliveries/{delivery_id}:retry", response_model=dict[str, str])
@audit_operation("retry", "webhook_delivery")
async def retry_delivery(
    delivery_id: str,
    tenant: TenantDep,
    _: AdminAccess,
    session: SessionDep,
    correlation_id: str = Depends(get_correlation_id),
) -> dict[str, str]:
    TenantContextValidator.ensure_tenant_context(tenant)

    delivery = await session.get(WebhookDelivery, delivery_id)
    if delivery is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_WEBHOOK_DELIVERY_NOT_FOUND)
    enforce_row_belongs_to_tenant(
        session,
        delivery,
        tenant_id=str(tenant.id),
        mismatch_event="api.webhooks.delivery_retry.tenant_scope_mismatch",
        detail=_WEBHOOK_DELIVERY_NOT_FOUND,
    )

    if delivery.status == "success":
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_WEBHOOK_DELIVERY_ALREADY_SUCCEEDED)

    # Check retry eligibility from diagnostics
    diag = _extract_failure_diagnostics(delivery)
    if diag and not diag.retry_eligible:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=api_problem_detail(
                code="WEBHOOK_DELIVERY_NOT_RETRYABLE",
                message=f"Not retryable: {diag.failure_category}",
                error_type="webhooks",
            ),
        )

    delivery.status = "pending"
    delivery.next_attempt_at = datetime.now(tz=timezone.utc)
    # Re-drive the source Outbox entry — WebhookDelivery is only a status mirror, the
    # OutboxProcessor is what actually delivers. Prefer the explicit outbox_id; fall
    # back to event_id (which the /deliveries join already treats as the Outbox id) for
    # legacy rows written before outbox_id existed.
    outbox_ref = delivery.outbox_id or delivery.event_id
    outbox_entry = await session.get(Outbox, outbox_ref) if outbox_ref else None
    if outbox_entry is not None and str(outbox_entry.tenant_id) == str(tenant.id):
        outbox_entry.status = OutboxStatus.PENDING
        outbox_entry.attempts = 0
        outbox_entry.next_attempt_at = datetime.now(tz=timezone.utc)
    await session.commit()
    return {"status": "queued"}


@router.post("/events/{event_id}:replay")
@audit_operation("replay", "outbox_event")
async def replay_event(
    event_id: str,
    tenant: TenantDep,
    _: AdminAccess,
    session: SessionDep,
    correlation_id: str = Depends(get_correlation_id),
) -> dict[str, str]:
    TenantContextValidator.ensure_tenant_context(tenant)

    event = await session.get(Outbox, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_OUTBOX_EVENT_NOT_FOUND)
    enforce_row_belongs_to_tenant(
        session,
        event,
        tenant_id=str(tenant.id),
        mismatch_event="api.webhooks.replay_outbox.tenant_scope_mismatch",
        detail=_OUTBOX_EVENT_NOT_FOUND,
    )
    event.status = OutboxStatus.PENDING
    # Reset the exhausted retry counter, else a DEAD event (attempts > max) is picked
    # up, immediately re-incremented past the cap and re-killed without a redelivery.
    event.attempts = 0
    event.next_attempt_at = datetime.now(tz=timezone.utc)
    await session.commit()
    return {"status": "queued"}


@router.post("/inbound/{source}", status_code=status.HTTP_202_ACCEPTED)
@audit_operation("inbound", "webhook_event")
async def inbound_webhook(
    source: str,
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
) -> dict[str, str]:
    raw = await request.body()
    verify_inbound_webhook_body_hmac(settings=get_settings(), raw_body=raw, request=request)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=api_problem_detail(
                code="INVALID_JSON",
                message="Request body must be valid JSON",
                error_type="validation",
            ),
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=api_problem_detail(
                code="INVALID_JSON",
                message="Inbound webhook JSON must be an object",
                error_type="validation",
            ),
        )
    dedup_key = compute_inbound_dedup_key(payload, raw)
    row = InboundWebhookDedup(
        tenant_id=tenant.id,
        source=source,
        dedup_key=dedup_key,
        payload_hash=hashlib.sha256(raw).hexdigest(),
        received_at=datetime.now(timezone.utc),
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return {"status": "duplicate"}
    process_inbound_webhook.delay(source=source, tenant_slug=tenant.slug, payload=payload)
    return {"status": "accepted"}
