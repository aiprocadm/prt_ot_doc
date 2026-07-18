"""Periodic domain-tick Celery tasks — extracted from _core.py (ARCH-4 decomposition).

Pure move: identical task definitions, explicit ``name=`` preserved, so Celery
registration is unchanged. Re-exported from _core for back-compat.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import get_settings
from app.core.tenant import tenant_context
from app.db import AsyncSessionLocal, ensure_tenant_schema, session_scope
from app.models.models import Tenant
from app.modules.workflow.service import WorkflowService
from app.services.celery_app import celery_app
from app.tasks._shared import (
    RETRYABLE_EXCEPTIONS,
    _resolve_task_tenant_scope,
    _run_coroutine,
)

settings = get_settings()


@celery_app.task(
    name="workflow.sla.tick",
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def workflow_sla_tick(tenant_slug: str) -> int:
    async def _run() -> int:
        with tenant_context(tenant_slug):
            ensure_tenant_schema(tenant_slug)
            async with session_scope(tenant=tenant_slug) as session:
                tenant_id, _tenant_scope = await _resolve_task_tenant_scope(session, tenant_slug)
                processed = await WorkflowService(session, tenant_id).sweep_task_sla()
                await session.commit()
                return processed

    return _run_coroutine(_run())


@celery_app.task(
    name="workflow.timers.tick",
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def workflow_timers_tick(tenant_slug: str) -> int:
    async def _run() -> int:
        with tenant_context(tenant_slug):
            ensure_tenant_schema(tenant_slug)
            async with session_scope(tenant=tenant_slug) as session:
                tenant_id, _tenant_scope = await _resolve_task_tenant_scope(session, tenant_slug)
                processed = await WorkflowService(session, tenant_id).run_due_timers()
                await session.commit()
                return processed

    return _run_coroutine(_run())


@celery_app.task(
    name="medical.contingent.tick",
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def medical_contingent_tick() -> int:
    return _run_coroutine(_medical_contingent_tick())


async def _medical_contingent_tick() -> int:
    from app.domains.medical.service import notify_overdue

    today = datetime.now(tz=timezone.utc).date()
    async with AsyncSessionLocal(tenant=settings.default_tenant_slug) as session:
        tenants = list(
            (await session.execute(select(Tenant).where(Tenant.is_active.is_(True))))
            .scalars()
            .all()
        )
    processed = 0
    for tenant in tenants:
        with tenant_context(tenant.slug):
            ensure_tenant_schema(tenant.slug)
            async with session_scope(tenant=tenant.slug) as session:
                tenant_id, _scope = await _resolve_task_tenant_scope(session, tenant.slug)
                processed += await notify_overdue(
                    session, tenant_id=tenant_id, actor_id=None, today=today
                )
                await session.commit()
    return processed


@celery_app.task(
    name="contractors.readiness.tick",
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def contractors_readiness_tick() -> int:
    return _run_coroutine(_contractors_readiness_tick())


async def _contractors_readiness_tick() -> int:
    from app.modules.projections.services import ContractorReadinessProjectionService
    from app.services.contractor_admission import notify_readiness

    async with AsyncSessionLocal(tenant=settings.default_tenant_slug) as session:
        tenants = list(
            (await session.execute(select(Tenant).where(Tenant.is_active.is_(True))))
            .scalars()
            .all()
        )
    total = 0
    # Per-tenant isolation matches _medical_contingent_tick (no per-tenant try/except):
    # a tenant failure aborts the run and Celery autoretry re-runs it; both steps are
    # idempotent (rebuild upserts, notify dedups by (employee, status, day)).
    for tenant in tenants:
        with tenant_context(tenant.slug):
            ensure_tenant_schema(tenant.slug)
            async with session_scope(tenant=tenant.slug) as session:
                tenant_id, _scope = await _resolve_task_tenant_scope(session, tenant.slug)
                # Enqueue notifications first, THEN rebuild — rebuild() commits, making the
                # outbox events and the refreshed projection a single atomic unit (avoids a
                # projection/notification split-brain if either step fails midway).
                total += await notify_readiness(session, tenant_id=tenant_id)
                await ContractorReadinessProjectionService(session, tenant_id).rebuild()
                await session.commit()
    return total


@celery_app.task(
    name="contractors.documents.tick",
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def contractors_documents_tick() -> int:
    return _run_coroutine(_contractors_documents_tick())


async def _contractors_documents_tick() -> int:
    from app.services.contractor_documents import notify_document_expiry

    async with AsyncSessionLocal(tenant=settings.default_tenant_slug) as session:
        tenants = list(
            (await session.execute(select(Tenant).where(Tenant.is_active.is_(True))))
            .scalars()
            .all()
        )
    total = 0
    for tenant in tenants:
        with tenant_context(tenant.slug):
            ensure_tenant_schema(tenant.slug)
            async with session_scope(tenant=tenant.slug) as session:
                tenant_id, _scope = await _resolve_task_tenant_scope(session, tenant.slug)
                # Enqueue then commit — outbox events are atomic with the read (notify dedups
                # by (document, status, day), so autoretry is safe).
                total += await notify_document_expiry(session, tenant_id=tenant_id)
                await session.commit()
    return total


@celery_app.task(
    name="ppe.expiry.tick",
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def ppe_expiry_tick() -> int:
    return _run_coroutine(_ppe_expiry_tick())


async def _ppe_expiry_tick() -> int:
    from app.services.ppe_notifications import notify_replacement_due

    async with AsyncSessionLocal(tenant=settings.default_tenant_slug) as session:
        tenants = list(
            (await session.execute(select(Tenant).where(Tenant.is_active.is_(True))))
            .scalars()
            .all()
        )
    total = 0
    for tenant in tenants:
        with tenant_context(tenant.slug):
            ensure_tenant_schema(tenant.slug)
            async with session_scope(tenant=tenant.slug) as session:
                tenant_id, _scope = await _resolve_task_tenant_scope(session, tenant.slug)
                # Enqueue then commit — события атомарны с чтением; notify дедупит
                # по (issue, status, day), поэтому autoretry безопасен.
                total += await notify_replacement_due(session, tenant_id=tenant_id)
                await session.commit()
    return total


@celery_app.task(
    name="permits.expiry.tick",
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def permits_expiry_tick() -> int:
    return _run_coroutine(_permits_expiry_tick())


async def _permits_expiry_tick() -> int:
    from app.domains.permits.service import expire_due

    async with AsyncSessionLocal(tenant=settings.default_tenant_slug) as session:
        tenants = list(
            (await session.execute(select(Tenant).where(Tenant.is_active.is_(True))))
            .scalars()
            .all()
        )
    total = 0
    for tenant in tenants:
        with tenant_context(tenant.slug):
            ensure_tenant_schema(tenant.slug)
            async with session_scope(tenant=tenant.slug) as session:
                tenant_id, _scope = await _resolve_task_tenant_scope(session, tenant.slug)
                # Idempotent: re-running on the same day flips nothing new.
                total += await expire_due(session, tenant_id=tenant_id)
                await session.commit()
    return total


@celery_app.task(
    name="prescriptions.escalate.tick",
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def prescriptions_escalate_tick() -> int:
    return _run_coroutine(_prescriptions_escalate_tick())


async def _prescriptions_escalate_tick() -> int:
    # imported lazily to avoid import cycles at task-module load time
    from app.domains.prescriptions.service import notify_overdue

    today = datetime.now(tz=timezone.utc).date()
    async with AsyncSessionLocal(tenant=settings.default_tenant_slug) as session:
        tenants = list(
            (await session.execute(select(Tenant).where(Tenant.is_active.is_(True))))
            .scalars()
            .all()
        )
    processed = 0
    for tenant in tenants:
        with tenant_context(tenant.slug):
            ensure_tenant_schema(tenant.slug)
            async with session_scope(tenant=tenant.slug) as session:
                tenant_id, _scope = await _resolve_task_tenant_scope(session, tenant.slug)
                overdue = await notify_overdue(
                    session, tenant_id=tenant_id, actor_id=None, today=today
                )
                await session.commit()
                processed += len(overdue)
    return processed
