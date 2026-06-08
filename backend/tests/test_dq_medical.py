"""Task 8.3 — Data Quality: verify UnfitWithoutSuspensionRule produces issues correctly.

Tests the new rule directly against an in-memory SQLite DB, mirroring the pattern
in test_briefings_service.py and the existing data_quality rule structure.
"""

from __future__ import annotations

from datetime import date, datetime, timezone, timedelta

import pytest
from sqlalchemy import Column, String, Table
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.session import TenantBase
from app.models.models import (
    MedicalExam,
    MedicalExamKind,
    MedicalFitness,
    MedicalSuspension,
    MedicalSuspensionReason,
    MedicalSuspensionStatus,
)
from app.modules.data_quality.rules import UnfitWithoutSuspensionRule
from app.modules.data_quality.schemas import IssueSeverity, IssueType


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


TENANT = "test-tenant"


def _exam(person_id: str, fitness: MedicalFitness, exam_date: date | None = None) -> MedicalExam:
    return MedicalExam(
        tenant_id=TENANT,
        person_id=person_id,
        exam_type="periodic",
        exam_date=exam_date or date.today(),
        valid_until=date.today() + timedelta(days=365),
        fitness=fitness,
    )


def _active_suspension(person_id: str) -> MedicalSuspension:
    return MedicalSuspension(
        tenant_id=TENANT,
        person_id=person_id,
        reason=MedicalSuspensionReason.UNFIT,
        started_at=datetime.now(tz=timezone.utc),
        status=MedicalSuspensionStatus.ACTIVE,
    )


@pytest.mark.asyncio
async def test_unfit_without_suspension_flags_issue(db_session) -> None:
    """Person with UNFIT latest exam and no suspension gets flagged."""
    person_id = "person-unfit-no-susp"
    db_session.add(_exam(person_id, MedicalFitness.UNFIT))
    await db_session.flush()

    rule = UnfitWithoutSuspensionRule(TENANT, db_session)
    await rule.check()

    person_issues = [i for i in rule.issues if i.affected_entity_id == person_id]
    assert person_issues, f"expected issue for {person_id}, got {rule.issues}"
    issue = person_issues[0]
    assert issue.severity == IssueSeverity.HIGH
    assert issue.issue_type == IssueType.DATA_MISMATCH
    assert issue.affected_entity_type == "person"


@pytest.mark.asyncio
async def test_unfit_with_active_suspension_no_issue(db_session) -> None:
    """Person with UNFIT latest exam AND active suspension is clean."""
    person_id = "person-unfit-with-susp"
    db_session.add(_exam(person_id, MedicalFitness.UNFIT))
    db_session.add(_active_suspension(person_id))
    await db_session.flush()

    rule = UnfitWithoutSuspensionRule(TENANT, db_session)
    await rule.check()

    person_issues = [i for i in rule.issues if i.affected_entity_id == person_id]
    assert not person_issues, (
        f"person with active suspension should not be flagged, got {person_issues}"
    )


@pytest.mark.asyncio
async def test_fit_person_not_flagged(db_session) -> None:
    """Person with FIT latest exam is never flagged regardless of suspensions."""
    person_id = "person-fit"
    db_session.add(_exam(person_id, MedicalFitness.FIT))
    await db_session.flush()

    rule = UnfitWithoutSuspensionRule(TENANT, db_session)
    await rule.check()

    person_issues = [i for i in rule.issues if i.affected_entity_id == person_id]
    assert not person_issues


@pytest.mark.asyncio
async def test_latest_exam_wins(db_session) -> None:
    """Only the LATEST exam determines fitness — older UNFIT exam + newer FIT exam = no issue."""
    person_id = "person-latest"
    older_date = date.today() - timedelta(days=30)
    newer_date = date.today()

    db_session.add(_exam(person_id, MedicalFitness.UNFIT, exam_date=older_date))
    db_session.add(_exam(person_id, MedicalFitness.FIT, exam_date=newer_date))
    await db_session.flush()

    rule = UnfitWithoutSuspensionRule(TENANT, db_session)
    await rule.check()

    person_issues = [i for i in rule.issues if i.affected_entity_id == person_id]
    assert not person_issues, (
        f"latest exam is FIT; older UNFIT should not trigger issue, got {person_issues}"
    )


@pytest.mark.asyncio
async def test_lifted_suspension_still_flagged(db_session) -> None:
    """Person with UNFIT exam and only a LIFTED suspension is still flagged."""
    person_id = "person-lifted-susp"
    db_session.add(_exam(person_id, MedicalFitness.UNFIT))
    lifted = MedicalSuspension(
        tenant_id=TENANT,
        person_id=person_id,
        reason=MedicalSuspensionReason.UNFIT,
        started_at=datetime.now(tz=timezone.utc) - timedelta(days=5),
        lifted_at=datetime.now(tz=timezone.utc),
        status=MedicalSuspensionStatus.LIFTED,
    )
    db_session.add(lifted)
    await db_session.flush()

    rule = UnfitWithoutSuspensionRule(TENANT, db_session)
    await rule.check()

    person_issues = [i for i in rule.issues if i.affected_entity_id == person_id]
    assert person_issues, (
        "LIFTED suspension does not protect — person should still be flagged"
    )


@pytest.mark.asyncio
async def test_tenant_scoped(db_session) -> None:
    """Persons from another tenant are not flagged."""
    person_id = "person-other-tenant"
    exam = MedicalExam(
        tenant_id="other-tenant",
        person_id=person_id,
        exam_type="periodic",
        exam_date=date.today(),
        valid_until=date.today() + timedelta(days=365),
        fitness=MedicalFitness.UNFIT,
    )
    db_session.add(exam)
    await db_session.flush()

    rule = UnfitWithoutSuspensionRule(TENANT, db_session)
    await rule.check()

    person_issues = [i for i in rule.issues if i.affected_entity_id == person_id]
    assert not person_issues, "cross-tenant person should not appear in DQ issues"


@pytest.mark.asyncio
async def test_no_exams_at_all(db_session) -> None:
    """Empty DB produces zero issues and no exception."""
    rule = UnfitWithoutSuspensionRule(TENANT, db_session)
    await rule.check()

    assert rule.issues == []
    assert rule.total_checked == 0
