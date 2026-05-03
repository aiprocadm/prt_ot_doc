"""Tests for data quality module (vNext Phase 3.1a)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import date, datetime, timedelta, timezone

from app.models.document import Document, DocumentStatus
from app.models.models import (
    EmploymentStatus,
    Permit,
    PermitStatus,
    Position,
    PPEIssue,
    PPEIssueStatus,
    RoleEnum,
    Workplace,
)
from app.modules.data_quality import DataQualityService, IssueSeverity, IssueType
from app.modules.data_quality.rules import (
    DocumentPersonCompanyMismatchRule,
    DuplicateRecordsRule,
    ExpiredPermitsRule,
    ExpiredPPEIssuesRule,
    MissingMandatoryFieldsRule,
    OrphanedAssignmentsRule,
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
        rule_names = {r.rule_name for r in report.check_results}
        expected_rules = {
            "missing_mandatory_fields",
            "broken_relationships",
            "expired_records",
            "expired_permits",
            "expired_ppe_issues",
            "document_person_company_mismatch",
            "potential_duplicates",
        }
        assert expected_rules.issubset(rule_names)
        assert len(report.check_results) == len(expected_rules)


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


@pytest.mark.anyio
class TestExpiredPermitsRule:
    """Permits past valid_until that are still ACTIVE must be flagged."""

    async def test_flags_expired_active_permit(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            first_name="Permit",
            last_name="Holder",
            email="permit@example.com",
            session=test_db_session,
        )
        expired = Permit(
            tenant_id=tenant.id,
            person_id=person.id,
            permit_type="height_works",
            issued_at=date.today() - timedelta(days=400),
            valid_until=date.today() - timedelta(days=10),
            status=PermitStatus.ACTIVE,
        )
        test_db_session.add(expired)
        await test_db_session.commit()
        await test_db_session.refresh(expired)

        rule = ExpiredPermitsRule(str(tenant.id), test_db_session)
        await rule.check()

        assert any(i.affected_entity_id == str(expired.id) for i in rule.issues)
        assert all(
            i.issue_type == IssueType.EXPIRED_RECORD for i in rule.issues
        )

    async def test_ignores_revoked_or_future_permits(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            first_name="Other",
            last_name="Holder",
            email="other@example.com",
            session=test_db_session,
        )

        revoked = Permit(
            tenant_id=tenant.id,
            person_id=person.id,
            permit_type="height_works",
            issued_at=date.today() - timedelta(days=400),
            valid_until=date.today() - timedelta(days=20),
            status=PermitStatus.REVOKED,
        )
        future = Permit(
            tenant_id=tenant.id,
            person_id=person.id,
            permit_type="electrical",
            issued_at=date.today() - timedelta(days=10),
            valid_until=date.today() + timedelta(days=30),
            status=PermitStatus.ACTIVE,
        )
        test_db_session.add_all([revoked, future])
        await test_db_session.commit()

        rule = ExpiredPermitsRule(str(tenant.id), test_db_session)
        await rule.check()

        assert not rule.issues


@pytest.mark.anyio
class TestExpiredPPEIssuesRule:
    """PPE issuances with expires_at past now while ISSUED must be flagged."""

    async def test_flags_expired_issued_ppe(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            first_name="PPE",
            last_name="Wearer",
            email="ppe@example.com",
            session=test_db_session,
        )
        issuance = PPEIssue(
            tenant_id=tenant.id,
            person_id=person.id,
            item_name="Hard hat",
            quantity=1,
            issued_at=datetime.now(tz=timezone.utc) - timedelta(days=400),
            expires_at=datetime.now(tz=timezone.utc) - timedelta(days=5),
            status=PPEIssueStatus.ISSUED,
        )
        test_db_session.add(issuance)
        await test_db_session.commit()
        await test_db_session.refresh(issuance)

        rule = ExpiredPPEIssuesRule(str(tenant.id), test_db_session)
        await rule.check()

        assert any(i.affected_entity_id == str(issuance.id) for i in rule.issues)
        assert all(
            i.affected_entity_type == "ppe_issue" for i in rule.issues
        )

    async def test_ignores_returned_or_unexpired_ppe(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            first_name="PPE2",
            last_name="Wearer",
            email="ppe2@example.com",
            session=test_db_session,
        )
        returned = PPEIssue(
            tenant_id=tenant.id,
            person_id=person.id,
            item_name="Old gloves",
            quantity=2,
            issued_at=datetime.now(tz=timezone.utc) - timedelta(days=400),
            expires_at=datetime.now(tz=timezone.utc) - timedelta(days=10),
            status=PPEIssueStatus.RETURNED,
        )
        unexpired = PPEIssue(
            tenant_id=tenant.id,
            person_id=person.id,
            item_name="New helmet",
            quantity=1,
            issued_at=datetime.now(tz=timezone.utc) - timedelta(days=5),
            expires_at=datetime.now(tz=timezone.utc) + timedelta(days=30),
            status=PPEIssueStatus.ISSUED,
        )
        test_db_session.add_all([returned, unexpired])
        await test_db_session.commit()

        rule = ExpiredPPEIssuesRule(str(tenant.id), test_db_session)
        await rule.check()

        assert not rule.issues


@pytest.mark.anyio
class TestDocumentPersonCompanyMismatchRule:
    """Documents whose company differs from the linked person's employer must be flagged."""

    async def test_flags_document_when_companies_differ(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        person_company = await data_factory.create_company(
            tenant=tenant, session=test_db_session
        )
        document_company = await data_factory.create_company(
            tenant=tenant, session=test_db_session
        )
        person = await data_factory.create_person(
            tenant=tenant,
            company=person_company,
            first_name="Mismatch",
            last_name="Subject",
            email="mismatch@example.com",
            session=test_db_session,
        )
        document, _ = await data_factory.create_document(
            tenant=tenant,
            company=document_company,
            person=person,
            session=test_db_session,
        )

        rule = DocumentPersonCompanyMismatchRule(str(tenant.id), test_db_session)
        await rule.check()

        assert any(i.affected_entity_id == str(document.id) for i in rule.issues)
        assert all(
            i.issue_type == IssueType.DATA_MISMATCH for i in rule.issues
        )
        flagged = next(i for i in rule.issues if i.affected_entity_id == str(document.id))
        assert flagged.additional_info["person_company_id"] == str(person_company.id)
        assert flagged.additional_info["document_company_id"] == str(document_company.id)

    async def test_ignores_aligned_company_or_unlinked_documents(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            first_name="Aligned",
            last_name="Subject",
            email="aligned@example.com",
            session=test_db_session,
        )
        # Aligned: document.company_id == person.company_id
        await data_factory.create_document(
            tenant=tenant,
            company=company,
            person=person,
            session=test_db_session,
        )
        # Unlinked: document without person — must not be flagged even if company differs
        other_company = await data_factory.create_company(
            tenant=tenant, session=test_db_session
        )
        unlinked = Document(
            tenant_id=tenant.id,
            template_id=(
                await data_factory.create_template(
                    tenant=tenant, session=test_db_session
                )
            ).id,
            company_id=other_company.id,
            person_id=None,
            status=DocumentStatus.DRAFT,
            created_by=(
                await data_factory.create_user(tenant=tenant, session=test_db_session)
            ).id,
        )
        test_db_session.add(unlinked)
        await test_db_session.commit()

        rule = DocumentPersonCompanyMismatchRule(str(tenant.id), test_db_session)
        await rule.check()

        assert not rule.issues
