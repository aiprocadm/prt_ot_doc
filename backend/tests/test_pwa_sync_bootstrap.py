from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import MappingProxyType, SimpleNamespace

import pytest
from sqlalchemy import Column, String, Table
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.routes.pwa_sync import bootstrap
from app.core.security import AccessContext
from app.db.session import TenantBase
from app.models.models import (
    BriefingJournal,
    BriefingTemplate,
    ComplianceDeadline,
    OfflineMediaQueue,
    OfflineSyncBatch,
    Person,
    TrainingEnrollment,
)


def _access_for(user, tenant):
    return AccessContext(
        user=user,
        claims=MappingProxyType(
            {
                "sub": user.id,
                "tenant": tenant.slug,
                "tenant_id": tenant.id,
                "role": user.role.value,
                "roles": [user.role.value],
            }
        ),
        tenant_slug=tenant.slug,
        tenant_id=tenant.id,
        company_id=getattr(user, "company_id", None),
    )


@pytest.fixture()
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    if "tenant" not in TenantBase.metadata.tables:
        Table("tenant", TenantBase.metadata, Column("id", String(36), primary_key=True))
    async with engine.begin() as conn:
        await conn.run_sync(TenantBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_pwa_bootstrap_returns_authenticated_projection_payload(db_session) -> None:
    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A")
    user = SimpleNamespace(
        id="user-1",
        email="admin@tenant-a.test",
        role=SimpleNamespace(value="admin"),
        company_id=None,
    )

    template = BriefingTemplate(
        tenant_id=tenant.id,
        code="bt-1",
        title="Intro",
        briefing_type="introductory",
        status="active",
        validity_days=30,
    )
    journal = BriefingJournal(
        tenant_id=tenant.id,
        code="bj-1",
        title="Main Journal",
        journal_type="ot",
        status="active",
    )
    person = Person(
        id="person-1",
        tenant_id=tenant.id,
        company_id="company-1",
        first_name="Test",
        last_name="Person",
        email=user.email,
    )
    enrollment = TrainingEnrollment(
        tenant_id=tenant.id,
        person_id=person.id,
        training_program_id="program-1",
        status="in_progress",
        progress_percent=55,
        attempt_count=2,
        due_at=datetime.now(timezone.utc) + timedelta(days=2),
    )
    deadline = ComplianceDeadline(
        tenant_id=tenant.id,
        person_id=person.id,
        entity_type="training",
        entity_id="program-1",
        due_at=datetime.now(timezone.utc) + timedelta(days=1),
        status="due",
    )
    pending_batch = OfflineSyncBatch(
        tenant_id=tenant.id,
        user_id=user.id,
        device_id="device-1",
        entity_type="briefing_entry",
        status="pending",
        payload={"id": "entry-1"},
    )
    failed_batch = OfflineSyncBatch(
        tenant_id=tenant.id,
        user_id=user.id,
        device_id="device-1",
        entity_type="briefing_entry",
        status="failed",
        payload={"id": "entry-2"},
        error_payload={"error": "conflict_final_record"},
    )
    failed_media = OfflineMediaQueue(
        tenant_id=tenant.id,
        user_id=user.id,
        device_id="device-1",
        local_ref="photo://1",
        upload_status="failed",
        metadata_json={"kind": "photo"},
    )
    db_session.add_all(
        [person, template, journal, enrollment, deadline, pending_batch, failed_batch, failed_media]
    )
    await db_session.commit()

    access = AccessContext(
        user=user,
        claims=MappingProxyType(
            {
                "sub": user.id,
                "tenant": tenant.slug,
                "tenant_id": tenant.id,
                "role": "admin",
                "roles": ["admin"],
            }
        ),
        tenant_slug=tenant.slug,
        tenant_id=tenant.id,
        company_id=None,
    )

    payload = await bootstrap(tenant=tenant, session=db_session, access=access)

    assert payload.current_user.id == user.id
    assert payload.current_user.tenant_slug == tenant.slug
    assert payload.current_user.permissions
    assert any(item.route == "documents" for item in payload.route_permissions)
    assert payload.briefing_templates[0].code == "bt-1"
    assert payload.active_journals[0].code == "bj-1"
    assert payload.assigned_training[0].progress_percent == 55.0
    assert payload.compliance_deadlines_summary["count"] == 1
    assert payload.compliance_deadlines_summary["by_status"]["due"] == 1
    assert payload.sync_state["pending_batches"] == 1
    assert payload.sync_state["failed_media"] == 1
    assert payload.sync_state["has_blocking_failures"] is True
    assert payload.offline_queue["conflict_count"] == 1
    assert payload.offline_queue["failed_conflicts"][0]["conflict_code"] == "conflict_final_record"
    assert payload.offline_queue["capabilities"]["briefing_mark"] is True
    assert payload.offline_queue["capabilities"]["media_photo_sync"] is True
    assert payload.offline_queue["draft_policy"]["local_persistence"] is True
    assert payload.offline_queue["draft_policy"]["requires_review_before_retry"] is True
    assert payload.offline_queue["conflict_resolution"]["required"] is True
    assert payload.offline_queue["conflict_resolution"]["recommended_action"] == "manual_review"
    assert payload.diagnostics["auth_required"] is True
    assert payload.diagnostics["bootstrap_version"] == 4
    assert payload.diagnostics["conflict_resolution_required"] is True
    assert payload.diagnostics["route_permission_count"] >= 1
    assert payload.diagnostics["user_scoped"] is True
    assert len(payload.diagnostics["permissions_etag"]) == 64
    assert "offline_media_statuses" in payload.dictionaries
    assert "offline_capabilities" in payload.dictionaries


def _worker(user_id: str, email: str):
    return SimpleNamespace(
        id=user_id, email=email, role=SimpleNamespace(value="worker"), company_id=None
    )


@pytest.mark.asyncio
async def test_pwa_bootstrap_scopes_training_and_deadlines_to_callers_person(db_session) -> None:
    """assigned_training / compliance_deadlines_summary expose only the caller's own
    person records, never another person's — the bootstrap is the caller's offline set."""
    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A")
    caller = _worker("user-1", "me@tenant-a.test")

    my_person = Person(
        id="person-1",
        tenant_id=tenant.id,
        company_id="c1",
        first_name="Me",
        last_name="Mine",
        email=caller.email,
    )
    other_person = Person(
        id="person-2",
        tenant_id=tenant.id,
        company_id="c1",
        first_name="Some",
        last_name="Body",
        email="other@tenant-a.test",
    )
    template = BriefingTemplate(
        tenant_id=tenant.id,
        code="bt-1",
        title="Intro",
        briefing_type="introductory",
        status="active",
        validity_days=30,
    )
    mine = TrainingEnrollment(
        tenant_id=tenant.id,
        person_id=my_person.id,
        training_program_id="p1",
        status="assigned",
        due_at=datetime.now(timezone.utc) + timedelta(days=3),
    )
    theirs = TrainingEnrollment(
        tenant_id=tenant.id,
        person_id=other_person.id,
        training_program_id="p2",
        status="assigned",
        due_at=datetime.now(timezone.utc) + timedelta(days=3),
    )
    my_deadline = ComplianceDeadline(
        tenant_id=tenant.id,
        person_id=my_person.id,
        entity_type="training",
        entity_id="p1",
        due_at=datetime.now(timezone.utc) + timedelta(days=1),
        status="due",
    )
    their_deadline = ComplianceDeadline(
        tenant_id=tenant.id,
        person_id=other_person.id,
        entity_type="training",
        entity_id="p2",
        due_at=datetime.now(timezone.utc) + timedelta(days=1),
        status="overdue",
    )
    db_session.add_all(
        [my_person, other_person, template, mine, theirs, my_deadline, their_deadline]
    )
    await db_session.commit()

    payload = await bootstrap(tenant=tenant, session=db_session, access=_access_for(caller, tenant))

    # only my enrollment / deadline — never the other person's
    assert len(payload.assigned_training) == 1
    assert payload.compliance_deadlines_summary["count"] == 1
    assert payload.compliance_deadlines_summary["by_status"]["due"] == 1
    assert payload.compliance_deadlines_summary["by_status"]["overdue"] == 0
    # catalog data (templates) stays tenant-wide — not over-scoped
    assert payload.briefing_templates[0].code == "bt-1"


@pytest.mark.asyncio
async def test_pwa_bootstrap_unlinked_user_sees_no_personal_records(db_session) -> None:
    """A user with no linked Person has no personal assignments — must not fall back to
    the tenant-wide list (the pre-fix over-exposure)."""
    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A")
    caller = _worker("user-unlinked", "nobody@tenant-a.test")

    # another person's records exist in the tenant, but the caller has no Person row
    other_person = Person(
        id="person-2",
        tenant_id=tenant.id,
        company_id="c1",
        first_name="Some",
        last_name="Body",
        email="other@tenant-a.test",
    )
    theirs = TrainingEnrollment(
        tenant_id=tenant.id,
        person_id=other_person.id,
        training_program_id="p2",
        status="assigned",
        due_at=datetime.now(timezone.utc) + timedelta(days=3),
    )
    their_deadline = ComplianceDeadline(
        tenant_id=tenant.id,
        person_id=other_person.id,
        entity_type="training",
        entity_id="p2",
        due_at=datetime.now(timezone.utc) + timedelta(days=1),
        status="overdue",
    )
    db_session.add_all([other_person, theirs, their_deadline])
    await db_session.commit()

    payload = await bootstrap(tenant=tenant, session=db_session, access=_access_for(caller, tenant))

    assert payload.assigned_training == []
    assert payload.compliance_deadlines_summary["count"] == 0
