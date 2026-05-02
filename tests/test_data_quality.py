"""Tests for data quality module (vNext Phase 3.1a)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import EmploymentStatus, Position, RoleEnum
from app.modules.data_quality import DataQualityService, IssueType
from app.modules.data_quality.rules import (
    DuplicateRecordsRule,
    MissingMandatoryFieldsRule,
)
from tests.utils.factories import TestDataFactory

API_PREFIX = "/api/v1"


def _dq_headers(base: dict[str, str]) -> dict[str, str]:
    merged = {**base}
    tid = merged.get("x-tenant") or merged.get("X-Tenant-Id")
    if tid:
        merged.setdefault("X-Tenant-Id", str(tid))
    return merged


@pytest.mark.anyio
class TestMissingMandatoryFieldsRule:
    """Test missing mandatory fields rule on Person model."""

    async def test_flags_blank_names(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            first_name=" ",
            last_name=" ",
            email=" spaced@example.com",
            employment_status=EmploymentStatus.ACTIVE,
            session=test_db_session,
        )

        rule = MissingMandatoryFieldsRule(str(tenant.id), test_db_session)
        await rule.check()

        assert any(str(person.id) in i.affected_entity_id for i in rule.issues)
        assert any(i.issue_type == IssueType.MISSING_FIELD for i in rule.issues)

    async def test_flags_active_without_email_or_position(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            first_name="John",
            last_name="NoEmail",
            email=None,
            session=test_db_session,
        )

        rule = MissingMandatoryFieldsRule(str(tenant.id), test_db_session)
        await rule.check()

        assert any(i.affected_entity_id == person.id for i in rule.issues)
        assert any("email" in i.additional_info.get("missing_fields", []) for i in rule.issues)
        assert any("position_id" in i.additional_info.get("missing_fields", []) for i in rule.issues)

    async def test_ok_complete_person(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        pos = Position(
            tenant_id=tenant.id,
            company_id=company.id,
            name="Tester",
        )
        test_db_session.add(pos)
        await test_db_session.commit()
        await test_db_session.refresh(pos)

        await data_factory.create_person(
            tenant=tenant,
            company=company,
            first_name="Good",
            last_name="Employee",
            email="good@example.com",
            position_id=pos.id,
            employment_status=EmploymentStatus.ACTIVE,
            session=test_db_session,
        )

        rule = MissingMandatoryFieldsRule(str(tenant.id), test_db_session)
        await rule.check()

        assert not rule.issues


@pytest.mark.anyio
class TestDuplicateRecordsRule:
    """Duplicate email detection."""

    async def test_detects_duplicate_emails(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        email = "dup@Example.com "
        await data_factory.create_person(
            tenant=tenant,
            company=company,
            first_name="A",
            last_name="One",
            email=email,
            session=test_db_session,
        )
        await data_factory.create_person(
            tenant=tenant,
            company=company,
            first_name="B",
            last_name="Two",
            email=email.strip().lower(),
            session=test_db_session,
        )

        rule = DuplicateRecordsRule(str(tenant.id), test_db_session)
        await rule.check()

        assert any(
            i.issue_type == IssueType.DUPLICATE
            and i.additional_info.get("duplicate_email") == "dup@example.com"
            for i in rule.issues
        )


@pytest.mark.anyio
class TestDataQualityService:
    async def test_comprehensive_check_runs_all_rules(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        service = DataQualityService(str(tenant.id), test_db_session)
        report = await service.run_comprehensive_check()

        assert report.tenant_id == str(tenant.id)
        assert report.total_issues >= 0
        assert len(report.check_results) == 4
        assert {r.rule_name for r in report.check_results} == {
            "missing_mandatory_fields",
            "broken_relationships",
            "expired_records",
            "potential_duplicates",
        }


@pytest.mark.anyio
class TestDataQualityEndpoints:
    async def test_report_ok(
        self,
        async_client: AsyncClient,
        make_auth_headers,
    ) -> None:
        base = await make_auth_headers(RoleEnum.ADMIN)
        resp = await async_client.get(
            f"{API_PREFIX}/data-quality/report",
            headers=_dq_headers(dict(base)),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "tenant_id" in data
        assert "check_results" in data

    async def test_requires_auth(self, async_client: AsyncClient) -> None:
        resp = await async_client.get(f"{API_PREFIX}/data-quality/report")
        assert resp.status_code in (
            400,
            401,
            403,
            404,
        )

    async def test_check_alias(
        self,
        async_client: AsyncClient,
        make_auth_headers,
    ) -> None:
        base = await make_auth_headers(RoleEnum.ADMIN)
        resp = await async_client.get(
            f"{API_PREFIX}/data-quality/check",
            headers=_dq_headers(dict(base)),
        )
        assert resp.status_code == 200
