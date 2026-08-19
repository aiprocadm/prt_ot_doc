from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import MappingProxyType, SimpleNamespace

import pytest
from sqlalchemy import Column, String, Table, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.routes.workspace import (
    role_workspace_summary,
    workspace_attention,
    workspace_task_inbox,
)
from app.core.security import AccessContext
from app.db.session import TenantBase
from app.models.medical import MedicalExam
from app.models.models import (
    ComplianceDeadline,
    OfflineSyncBatch,
    Person,
    PPEIssue,
    PPEIssueStatus,
)
from app.models.obligations import Task, TaskPriority, TaskStatus


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


def _access(user_id: str, role: str, tenant_id: str, tenant_slug: str) -> AccessContext:
    user = SimpleNamespace(
        id=user_id,
        email=f"{user_id}@tenant.test",
        role=SimpleNamespace(value=role),
        company_id=None,
    )
    return AccessContext(
        user=user,
        claims=MappingProxyType(
            {
                "sub": user_id,
                "tenant": tenant_slug,
                "tenant_id": tenant_id,
                "role": role,
                "roles": [role],
            }
        ),
        tenant_slug=tenant_slug,
        tenant_id=tenant_id,
        company_id=None,
    )


@pytest.mark.asyncio
async def test_workspace_attention_returns_overdue_deadlines_and_sync_counts(db_session) -> None:
    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    access = _access("user-1", "admin", tenant.id, tenant.slug)
    now = datetime.now(timezone.utc)

    db_session.add_all(
        [
            Task(
                tenant_id=tenant.id,
                title="Overdue task",
                status=TaskStatus.OPEN,
                priority=TaskPriority.HIGH,
                due_at=now - timedelta(days=1),
                assignee_id=access.user.id,
            ),
            ComplianceDeadline(
                tenant_id=tenant.id,
                entity_type="training",
                entity_id="tr-1",
                due_at=now - timedelta(hours=1),
                status="overdue",
            ),
            OfflineSyncBatch(
                tenant_id=tenant.id,
                user_id=access.user.id,
                device_id="d-1",
                entity_type="incident",
                status="failed",
                payload={"id": "1"},
                error_payload={"error": "conflict"},
            ),
        ]
    )
    await db_session.commit()

    payload = await workspace_attention(tenant=tenant, session=db_session, access=access, limit=20)

    assert payload.summary.overdue_tasks == 1
    assert payload.summary.overdue_deadlines == 1
    assert payload.summary.failed_sync_batches == 1
    assert payload.summary.readiness_blockers >= 1
    assert payload.items
    assert any(blocker.code == "templates_not_ready" for blocker in payload.blockers)
    assert any("блокеры готовности" in rec for rec in payload.recommendations)
    assert any("просроченные задачи" in rec for rec in payload.recommendations)


# ── BIZ-54-57 срез-1: дисциплины в Центре внимания (Доп. №1 разд. 57.2) ──────


def _person(tenant_id: str, *, email: str | None = None, **extra):
    return Person(
        tenant_id=tenant_id,
        company_id="company-1",
        first_name="Иван",
        last_name="Иванов",
        email=email,
        **extra,
    )


@pytest.mark.asyncio
async def test_attention_shows_overdue_medical_with_discipline(db_session) -> None:
    """Просроченный медосмотр попадает в ленту внимания и размечен дисциплиной.

    До этого среза items собирались ТОЛЬКО из задач: медосмотр, СИЗ и обучение
    в Центр внимания не попадали никогда, хотя агрегатор их уже считал.
    """

    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    access = _access("user-1", "admin", tenant.id, tenant.slug)
    today = datetime.now(timezone.utc).date()

    person = _person(tenant.id)
    db_session.add(person)
    await db_session.flush()
    db_session.add(
        MedicalExam(
            tenant_id=tenant.id,
            person_id=person.id,
            exam_type="периодический",
            exam_date=today - timedelta(days=400),
            valid_until=today - timedelta(days=35),
        )
    )
    await db_session.commit()

    payload = await workspace_attention(tenant=tenant, session=db_session, access=access)

    medical_items = [item for item in payload.items if item.discipline == "medical"]
    assert medical_items, "просроченный медосмотр обязан попасть в Центр внимания"
    assert medical_items[0].severity == "critical"
    assert medical_items[0].item_type == "medical_exam"
    assert any("Просрочено по дисциплинам" in rec for rec in payload.recommendations)


@pytest.mark.asyncio
async def test_attention_reports_unmeasured_disciplines_honestly(db_session) -> None:
    """Пять дисциплин ТЗ без данных отдаются с причиной, а не нулём.

    Ноль по неизмеряемой дисциплине читался бы как «нарушений нет» — это ложь
    вместо «мы это не считаем» (правило not_measured из BIZ-51).
    """

    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    access = _access("user-1", "admin", tenant.id, tenant.slug)

    payload = await workspace_attention(tenant=tenant, session=db_session, access=access)

    by_code = {row.code: row for row in payload.disciplines}
    assert len(payload.disciplines) == 8, "все дисциплины ТЗ обязаны быть в ответе"
    for code in ("fire_safety", "industrial_safety", "ecology", "civil_defense", "road_safety"):
        assert by_code[code].measured is False
        assert by_code[code].reason and "не ведётся" in by_code[code].reason
    for code in ("medical", "ppe", "training"):
        assert by_code[code].measured is True
        assert by_code[code].reason is None
    # Источники без дисциплины названы, а не спрятаны.
    assert payload.unclassified_sources
    assert any("Наряд-допуск" in reason for reason in payload.unclassified_sources)


@pytest.mark.asyncio
async def test_attention_worker_without_person_sees_no_foreign_records(db_session) -> None:
    """Рабочая роль без связанного сотрудника не получает ЧУЖИХ записей.

    Связи User→Person в моделях нет, она ищется по e-mail. Нет совпадения —
    персональных записей нет; откат на общий список арендатора был бы утечкой
    персональных данных.
    """

    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    worker = _access("worker-1", "worker", tenant.id, tenant.slug)
    today = datetime.now(timezone.utc).date()

    stranger = _person(tenant.id, email="stranger@tenant.test")
    db_session.add(stranger)
    await db_session.flush()
    db_session.add(
        MedicalExam(
            tenant_id=tenant.id,
            person_id=stranger.id,
            exam_type="периодический",
            exam_date=today - timedelta(days=400),
            valid_until=today - timedelta(days=35),
        )
    )
    await db_session.commit()

    payload = await workspace_attention(tenant=tenant, session=db_session, access=worker)

    assert not [item for item in payload.items if item.discipline == "medical"], (
        "рабочая роль без своей кадровой записи не должна видеть чужой медосмотр"
    )


@pytest.mark.asyncio
async def test_attention_ordinary_role_does_not_see_foreign_medical(db_session) -> None:
    """Роль без доступа к профильным экранам не видит ЧУЖИХ медосмотров.

    Найдено адверсарной проверкой среза: ручка висит на ``rbac()`` без ролей,
    поэтому сотрудник, ученик или бухгалтер получали построчный перечень
    медосмотров и выдач СИЗ по всему арендатору — обход прав профильных
    модулей, где СИЗ отдаётся одному администратору.
    """

    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    today = datetime.now(timezone.utc).date()

    stranger = _person(tenant.id, email="stranger@tenant.test")
    db_session.add(stranger)
    await db_session.flush()
    db_session.add(
        MedicalExam(
            tenant_id=tenant.id,
            person_id=stranger.id,
            exam_type="периодический",
            exam_date=today - timedelta(days=400),
            valid_until=today - timedelta(days=35),
        )
    )
    await db_session.commit()

    for role in ("employee", "student", "accountant", "contractor_inspector"):
        access = _access(f"user-{role}", role, tenant.id, tenant.slug)
        payload = await workspace_attention(tenant=tenant, session=db_session, access=access)
        assert not [item for item in payload.items if item.discipline == "medical"], (
            f"роль {role} не должна видеть чужой медосмотр"
        )


@pytest.mark.asyncio
async def test_attention_counts_come_from_totals_not_from_page(db_session) -> None:
    """Число просрочек — это количество, а не размер показанной страницы.

    Найдено адверсарной проверкой: счётчики считались по уже обрезанному
    лимитом списку, поэтому при тридцати семи просрочках и лимите 5 экран
    писал «5», а дисциплина, чьи строки не влезли, уходила в зелёный ноль.
    """

    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    access = _access("user-1", "admin", tenant.id, tenant.slug)
    today = datetime.now(timezone.utc).date()

    person = _person(tenant.id)
    db_session.add(person)
    await db_session.flush()
    for shift in range(8):
        db_session.add(
            MedicalExam(
                tenant_id=tenant.id,
                person_id=person.id,
                exam_type="периодический",
                exam_date=today - timedelta(days=400 + shift),
                valid_until=today - timedelta(days=35 + shift),
            )
        )
    await db_session.commit()

    payload = await workspace_attention(
        tenant=tenant, session=db_session, access=access, limit=3
    )

    medical = next(row for row in payload.disciplines if row.code == "medical")
    assert medical.overdue == 8, "счётчик обязан показывать все просрочки, а не страницу"
    assert len([item for item in payload.items if item.discipline == "medical"]) == 3
    assert payload.items_truncated is True, "обрезанный список обязан назвать себя обрезанным"


@pytest.mark.asyncio
async def test_attention_closed_ppe_is_not_overdue(db_session) -> None:
    """Возвращённая выдача СИЗ с прошедшим сроком просрочкой не считается.

    Найдено адверсарной проверкой: признак брался у полосы SLA, а она означает
    лишь «дата в прошлом» — закрытые записи попадали бы в просрочку.
    """

    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    access = _access("user-1", "admin", tenant.id, tenant.slug)
    now = datetime.now(timezone.utc)

    person = _person(tenant.id)
    db_session.add(person)
    await db_session.flush()
    db_session.add(
        PPEIssue(
            tenant_id=tenant.id,
            person_id=person.id,
            item_name="Каска",
            quantity=1,
            status=PPEIssueStatus.RETURNED,
            issued_at=now - timedelta(days=400),
            expires_at=now - timedelta(days=30),
            returned_at=now - timedelta(days=25),
        )
    )
    await db_session.commit()

    payload = await workspace_attention(tenant=tenant, session=db_session, access=access)

    ppe_row = next(row for row in payload.disciplines if row.code == "ppe")
    assert ppe_row.overdue == 0, "возвращённый СИЗ не просрочен — он уже не у человека"


@pytest.mark.asyncio
async def test_attention_worker_sees_own_records_only(db_session) -> None:
    """Рабочая роль со своей кадровой записью видит СВОЙ медосмотр и только его."""

    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    worker = _access("worker-1", "worker", tenant.id, tenant.slug)
    today = datetime.now(timezone.utc).date()

    mine = _person(tenant.id, email=worker.user.email)
    stranger = _person(tenant.id, email="stranger@tenant.test")
    db_session.add_all([mine, stranger])
    await db_session.flush()
    db_session.add_all(
        [
            MedicalExam(
                tenant_id=tenant.id,
                person_id=mine.id,
                exam_type="периодический",
                exam_date=today - timedelta(days=400),
                valid_until=today - timedelta(days=35),
            ),
            MedicalExam(
                tenant_id=tenant.id,
                person_id=stranger.id,
                exam_type="периодический",
                exam_date=today - timedelta(days=400),
                valid_until=today - timedelta(days=40),
            ),
        ]
    )
    await db_session.commit()

    payload = await workspace_attention(tenant=tenant, session=db_session, access=worker)

    medical_items = [item for item in payload.items if item.discipline == "medical"]
    assert len(medical_items) == 1, "видна ровно одна запись — своя"
    assert medical_items[0].entity_id == str(
        (await db_session.execute(select(MedicalExam.id).where(MedicalExam.person_id == mine.id)))
        .scalars()
        .first()
    )


@pytest.mark.asyncio
async def test_workspace_task_inbox_worker_sees_only_own_tasks(db_session) -> None:
    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    worker = _access("worker-1", "worker", tenant.id, tenant.slug)
    now = datetime.now(timezone.utc)

    db_session.add_all(
        [
            Task(
                tenant_id=tenant.id,
                title="Worker task",
                status=TaskStatus.OPEN,
                priority=TaskPriority.MEDIUM,
                due_at=now + timedelta(hours=6),
                assignee_id=worker.user.id,
            ),
            Task(
                tenant_id=tenant.id,
                title="Other task",
                status=TaskStatus.OPEN,
                priority=TaskPriority.MEDIUM,
                due_at=now + timedelta(hours=12),
                assignee_id="another-user",
            ),
        ]
    )
    await db_session.commit()

    payload = await workspace_task_inbox(
        tenant=tenant,
        session=db_session,
        access=worker,
        limit=50,
        offset=0,
    )

    assert payload.total == 1
    assert len(payload.items) == 1
    assert payload.items[0].title == "Worker task"


@pytest.mark.asyncio
async def test_role_workspace_summary_for_manager_scopes_to_assignee(db_session) -> None:
    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    manager = _access("manager-1", "line_manager", tenant.id, tenant.slug)
    now = datetime.now(timezone.utc)

    db_session.add_all(
        [
            Task(
                tenant_id=tenant.id,
                title="Own overdue task",
                status=TaskStatus.OPEN,
                priority=TaskPriority.HIGH,
                due_at=now - timedelta(hours=2),
                assignee_id=manager.user.id,
            ),
            Task(
                tenant_id=tenant.id,
                title="Other user task",
                status=TaskStatus.OPEN,
                priority=TaskPriority.MEDIUM,
                due_at=now + timedelta(hours=2),
                assignee_id="other-user",
            ),
        ]
    )
    await db_session.commit()

    payload = await role_workspace_summary(tenant=tenant, session=db_session, access=manager)

    assert payload.role == "line_manager"
    assert payload.open_tasks == 1
    assert payload.overdue_tasks == 1
    assert payload.open_incidents == 0
