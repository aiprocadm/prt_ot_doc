"""Tests for data quality module (vNext Phase 3.1a)."""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus, DocumentVersion
from app.models.models import (
    EmploymentStatus,
    Permit,
    PermitStatus,
    Position,
    PPEIssue,
    PPEIssueStatus,
    RoleEnum,
    TemplateVersion,
    TemplateVersionStatus,
    Workplace,
)
from app.modules.data_quality import DataQualityService, IssueSeverity, IssueType
from app.modules.data_quality.rules import (
    CompanyRequisitesRule,
    DocumentPersonCompanyMismatchRule,
    DocumentReadinessRule,
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
        assert any(
            "position_id" in i.additional_info.get("missing_fields", []) for i in rule.issues
        )

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
            "orphaned_assignments",
            "company_requisites",
            "document_readiness",
            "document_person_company_mismatch",
            "potential_duplicates",
            # Added by the medical contour (PR #643): flags persons with an
            # unfit medical verdict but no active suspension.
            "unfit_without_suspension",
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
        assert all(i.issue_type == IssueType.EXPIRED_RECORD for i in rule.issues)

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
        assert all(i.affected_entity_type == "ppe_issue" for i in rule.issues)

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
            tenant=tenant, name="Person Co", session=test_db_session
        )
        document_company = await data_factory.create_company(
            tenant=tenant, name="Document Co", session=test_db_session
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
        assert all(i.issue_type == IssueType.DATA_MISMATCH for i in rule.issues)
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
            tenant=tenant, name="Other Co", session=test_db_session
        )
        unlinked = Document(
            tenant_id=tenant.id,
            template_id=(
                await data_factory.create_template(
                    tenant=tenant, name="Unlinked tpl", session=test_db_session
                )
            ).id,
            company_id=other_company.id,
            person_id=None,
            status=DocumentStatus.DRAFT,
            created_by=(
                await data_factory.create_user(
                    tenant=tenant,
                    email="unlinked-creator@example.com",
                    session=test_db_session,
                )
            ).id,
        )
        test_db_session.add(unlinked)
        await test_db_session.commit()

        rule = DocumentPersonCompanyMismatchRule(str(tenant.id), test_db_session)
        await rule.check()

        assert not rule.issues


@pytest.mark.anyio
class TestDocumentReadinessRuleRequiredFields:
    """Draft documents: stale without template version, or missing required wizard fields."""

    async def test_flags_stale_draft_without_template_version(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            first_name="Stale",
            last_name="Draft",
            email="stale-draft@example.com",
            session=test_db_session,
        )
        template = await data_factory.create_template(
            tenant=tenant, name="ReadinessTpl", session=test_db_session
        )
        creator = await data_factory.create_user(
            tenant=tenant, email="stale-creator@example.com", session=test_db_session
        )
        doc = Document(
            tenant_id=tenant.id,
            company_id=company.id,
            person_id=person.id,
            template_id=template.id,
            template_version_id=None,
            status=DocumentStatus.DRAFT,
            created_by=creator.id,
        )
        test_db_session.add(doc)
        await test_db_session.commit()
        await test_db_session.refresh(doc)
        doc.created_at = datetime.now(tz=timezone.utc) - timedelta(days=14)
        await test_db_session.commit()

        rule = DocumentReadinessRule(str(tenant.id), test_db_session)
        await rule.check()

        assert any(
            i.affected_entity_id == str(doc.id)
            and i.additional_info.get("reason") == "stale_draft_missing_template_version"
            for i in rule.issues
        )
        assert any(i.severity == IssueSeverity.MEDIUM for i in rule.issues)

    async def test_skips_recent_draft_without_template_version(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            first_name="Fresh",
            last_name="Draft",
            email="fresh-draft@example.com",
            session=test_db_session,
        )
        template = await data_factory.create_template(
            tenant=tenant, name="ReadinessTpl2", session=test_db_session
        )
        creator = await data_factory.create_user(
            tenant=tenant, email="fresh-creator@example.com", session=test_db_session
        )
        doc = Document(
            tenant_id=tenant.id,
            company_id=company.id,
            person_id=person.id,
            template_id=template.id,
            template_version_id=None,
            status=DocumentStatus.DRAFT,
            created_by=creator.id,
        )
        test_db_session.add(doc)
        await test_db_session.commit()

        rule = DocumentReadinessRule(str(tenant.id), test_db_session)
        await rule.check()

        assert not any(i.affected_entity_id == str(doc.id) for i in rule.issues)

    async def test_flags_missing_required_fields_from_template_schema(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            first_name="Incomplete",
            last_name="Wizard",
            email="incomplete-wizard@example.com",
            session=test_db_session,
        )
        template = await data_factory.create_template(
            tenant=tenant, name="SchemaTpl", session=test_db_session
        )
        creator = await data_factory.create_user(
            tenant=tenant, email="schema-creator@example.com", session=test_db_session
        )
        checksum = hashlib.sha256(b"v1").digest()
        tv = TemplateVersion(
            tenant_id=tenant.id,
            template_id=template.id,
            version=1,
            checksum=checksum,
            status=TemplateVersionStatus.ACTIVE,
            payload_key="templates/schema.docx",
            required_fields_schema={
                "type": "object",
                "required": ["full_name", "sign_date"],
                "properties": {
                    "full_name": {"type": "string"},
                    "sign_date": {"type": "string"},
                },
            },
        )
        test_db_session.add(tv)
        await test_db_session.flush()

        doc = Document(
            tenant_id=tenant.id,
            company_id=company.id,
            person_id=person.id,
            template_id=template.id,
            template_version_id=tv.id,
            status=DocumentStatus.DRAFT,
            created_by=creator.id,
        )
        version = DocumentVersion(
            tenant_id=tenant.id,
            document=doc,
            template_version="1",
            data_json={"full_name": "Ada"},
            file_key="stub.docx",
        )
        test_db_session.add(doc)
        test_db_session.add(version)
        await test_db_session.commit()

        rule = DocumentReadinessRule(str(tenant.id), test_db_session)
        await rule.check()

        flagged = [
            i
            for i in rule.issues
            if i.affected_entity_id == str(doc.id)
            and i.additional_info.get("reason") == "missing_required_wizard_fields"
        ]
        assert flagged
        assert "sign_date" in flagged[0].additional_info.get("missing_fields", [])

    async def test_ok_when_nested_values_contains_required_fields(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            first_name="Nested",
            last_name="Ok",
            email="nested-ok@example.com",
            session=test_db_session,
        )
        template = await data_factory.create_template(
            tenant=tenant, name="NestedTpl", session=test_db_session
        )
        creator = await data_factory.create_user(
            tenant=tenant, email="nested-creator@example.com", session=test_db_session
        )
        checksum = hashlib.sha256(b"v2").digest()
        tv = TemplateVersion(
            tenant_id=tenant.id,
            template_id=template.id,
            version=1,
            checksum=checksum,
            status=TemplateVersionStatus.ACTIVE,
            payload_key="templates/nested.docx",
            required_fields_schema={
                "type": "object",
                "required": ["title"],
                "properties": {"title": {"type": "string"}},
            },
        )
        test_db_session.add(tv)
        await test_db_session.flush()

        doc = Document(
            tenant_id=tenant.id,
            company_id=company.id,
            person_id=person.id,
            template_id=template.id,
            template_version_id=tv.id,
            status=DocumentStatus.DRAFT,
            created_by=creator.id,
        )
        version = DocumentVersion(
            tenant_id=tenant.id,
            document=doc,
            template_version="1",
            data_json={"values": {"title": "Safety briefing"}},
            file_key="stub2.docx",
        )
        test_db_session.add(doc)
        test_db_session.add(version)
        await test_db_session.commit()

        rule = DocumentReadinessRule(str(tenant.id), test_db_session)
        await rule.check()

        assert not any(i.affected_entity_id == str(doc.id) for i in rule.issues)


@pytest.mark.anyio
class TestOrphanedAssignmentsRule:
    """Active persons assigned to soft-deleted positions/workplaces must be flagged."""

    async def test_flags_active_person_with_deleted_position(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        position = Position(
            tenant_id=tenant.id,
            company_id=company.id,
            name="Retired role",
            deleted_at=datetime.now(tz=timezone.utc),
        )
        test_db_session.add(position)
        await test_db_session.commit()
        await test_db_session.refresh(position)

        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            first_name="Orphaned",
            last_name="Worker",
            email="orphan@example.com",
            position_id=position.id,
            employment_status=EmploymentStatus.ACTIVE,
            session=test_db_session,
        )

        rule = OrphanedAssignmentsRule(str(tenant.id), test_db_session)
        await rule.check()

        flagged = [i for i in rule.issues if i.affected_entity_id == str(person.id)]
        assert flagged, "Expected an orphaned-assignment issue for the test person"
        assert any(i.additional_info.get("reason") == "position_soft_deleted" for i in flagged)
        assert all(i.severity == IssueSeverity.HIGH for i in flagged)

    async def test_flags_active_person_with_deleted_workplace(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        workplace = Workplace(
            tenant_id=tenant.id,
            company_id=company.id,
            name="Decommissioned bench",
            deleted_at=datetime.now(tz=timezone.utc),
        )
        test_db_session.add(workplace)
        await test_db_session.commit()
        await test_db_session.refresh(workplace)

        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            first_name="Bench",
            last_name="Worker",
            email="bench@example.com",
            workplace_id=workplace.id,
            employment_status=EmploymentStatus.ACTIVE,
            session=test_db_session,
        )

        rule = OrphanedAssignmentsRule(str(tenant.id), test_db_session)
        await rule.check()

        assert any(
            i.affected_entity_id == str(person.id)
            and i.additional_info.get("reason") == "workplace_soft_deleted"
            for i in rule.issues
        )

    async def test_ignores_healthy_assignment(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        position = Position(
            tenant_id=tenant.id,
            company_id=company.id,
            name="Active role",
        )
        workplace = Workplace(
            tenant_id=tenant.id,
            company_id=company.id,
            name="Active bench",
        )
        test_db_session.add_all([position, workplace])
        await test_db_session.commit()
        await test_db_session.refresh(position)
        await test_db_session.refresh(workplace)

        await data_factory.create_person(
            tenant=tenant,
            company=company,
            first_name="Happy",
            last_name="Worker",
            email="happy@example.com",
            position_id=position.id,
            workplace_id=workplace.id,
            employment_status=EmploymentStatus.ACTIVE,
            session=test_db_session,
        )

        rule = OrphanedAssignmentsRule(str(tenant.id), test_db_session)
        await rule.check()

        assert not rule.issues


@pytest.mark.anyio
class TestCompanyRequisitesRule:
    """Companies missing INN/OGRN must be flagged with appropriate severity."""

    async def test_flags_company_missing_inn_high_severity(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(
            tenant=tenant,
            name="No-INN LLC",
            session=test_db_session,
        )
        company.inn = None
        company.ogrn = None
        company.legal_address = None
        await test_db_session.commit()

        rule = CompanyRequisitesRule(str(tenant.id), test_db_session)
        await rule.check()

        flagged = [i for i in rule.issues if i.affected_entity_id == str(company.id)]
        assert flagged
        assert all(i.severity == IssueSeverity.HIGH for i in flagged)
        assert any("inn" in i.additional_info.get("missing_critical", []) for i in flagged)

    async def test_flags_only_recommended_with_low_severity(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(
            tenant=tenant,
            name="INN-Only LLC",
            inn="7700000001",
            session=test_db_session,
        )

        rule = CompanyRequisitesRule(str(tenant.id), test_db_session)
        await rule.check()

        flagged = [i for i in rule.issues if i.affected_entity_id == str(company.id)]
        assert flagged
        assert all(i.severity == IssueSeverity.LOW for i in flagged)
        assert all(not i.additional_info.get("missing_critical") for i in flagged)
        recommended = {
            field
            for issue in flagged
            for field in issue.additional_info.get("missing_recommended", [])
        }
        assert {"ogrn", "legal_address"}.issubset(recommended)

    async def test_skips_complete_company(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(
            tenant=tenant,
            name="Complete LLC",
            inn="7700000002",
            ogrn="1027700000002",
            legal_address="Moscow, Tverskaya 1",
            session=test_db_session,
        )

        rule = CompanyRequisitesRule(str(tenant.id), test_db_session)
        await rule.check()

        assert not any(i.affected_entity_id == str(company.id) for i in rule.issues)


@pytest.mark.anyio
class TestDocumentReadinessRule:
    """Stale DRAFT documents missing template version or generated file."""

    async def test_flags_old_draft_without_template_version(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        document, _ = await data_factory.create_document(
            tenant=tenant,
            company=company,
            status=DocumentStatus.DRAFT,
            session=test_db_session,
        )
        document.template_version_id = None
        document.created_at = datetime.now(tz=timezone.utc) - timedelta(days=14)
        await test_db_session.commit()

        rule = DocumentReadinessRule(str(tenant.id), test_db_session)
        await rule.check()

        flagged = [i for i in rule.issues if i.affected_entity_id == str(document.id)]
        assert flagged, "Expected a readiness issue for the stale DRAFT"
        assert all(i.severity == IssueSeverity.MEDIUM for i in flagged)
        assert all(i.issue_type == IssueType.MISSING_FIELD for i in flagged)
        assert any(
            "missing_template_version" in i.additional_info.get("missing", []) for i in flagged
        )
        assert all(i.additional_info.get("age_days", 0) >= 14 for i in flagged)

    async def test_flags_old_draft_without_generated_file(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        document = Document(
            tenant_id=tenant.id,
            template_id=(
                await data_factory.create_template(
                    tenant=tenant, name="Stale tpl", session=test_db_session
                )
            ).id,
            template_version_id=None,
            company_id=company.id,
            person_id=None,
            status=DocumentStatus.DRAFT,
            created_by=(
                await data_factory.create_user(
                    tenant=tenant,
                    email="stale-creator@example.com",
                    session=test_db_session,
                )
            ).id,
        )
        test_db_session.add(document)
        await test_db_session.commit()
        await test_db_session.refresh(document)
        document.created_at = datetime.now(tz=timezone.utc) - timedelta(days=10)
        await test_db_session.commit()

        rule = DocumentReadinessRule(str(tenant.id), test_db_session)
        await rule.check()

        flagged = [i for i in rule.issues if i.affected_entity_id == str(document.id)]
        assert flagged
        assert any(
            "missing_generated_file" in i.additional_info.get("missing", []) for i in flagged
        )

    async def test_ignores_recent_drafts(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        document, _ = await data_factory.create_document(
            tenant=tenant,
            company=company,
            status=DocumentStatus.DRAFT,
            session=test_db_session,
        )
        document.template_version_id = None
        document.created_at = datetime.now(tz=timezone.utc) - timedelta(days=2)
        await test_db_session.commit()

        rule = DocumentReadinessRule(str(tenant.id), test_db_session)
        await rule.check()

        assert not any(i.affected_entity_id == str(document.id) for i in rule.issues)

    async def test_ignores_non_draft_status(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        document, _ = await data_factory.create_document(
            tenant=tenant,
            company=company,
            status=DocumentStatus.GENERATED,
            session=test_db_session,
        )
        document.template_version_id = None
        document.created_at = datetime.now(tz=timezone.utc) - timedelta(days=30)
        await test_db_session.commit()

        rule = DocumentReadinessRule(str(tenant.id), test_db_session)
        await rule.check()

        assert not any(i.affected_entity_id == str(document.id) for i in rule.issues)
