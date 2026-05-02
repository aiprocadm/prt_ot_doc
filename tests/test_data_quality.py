"""Tests for data quality module."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.models import TenantContext
from app.models.base_models import Employee
from app.modules.data_quality import DataQualityService, IssueSeverity, IssueType
from app.modules.data_quality.rules import (
    BrokenRelationshipsRule,
    DuplicateRecordsRule,
    ExpiredRecordsRule,
    MissingMandatoryFieldsRule,
)


class TestMissingMandatoryFieldsRule:
    """Test missing mandatory fields rule."""

    async def test_detects_missing_last_name(
        self, db: AsyncSession, test_tenant: str, test_employees: list
    ) -> None:
        """Test rule detects employees without last name."""
        rule = MissingMandatoryFieldsRule(test_tenant, db)
        await rule.check()

        assert len(rule.issues) > 0
        assert any(i.issue_type == IssueType.MISSING_FIELD for i in rule.issues)

    async def test_detects_missing_email(
        self, db: AsyncSession, test_tenant: str
    ) -> None:
        """Test rule detects employees without email."""
        # Create employee without email
        emp = Employee(
            tenant_id=test_tenant,
            first_name="John",
            last_name="Doe",
            email=None,
            position="Manager",
        )
        db.add(emp)
        await db.commit()

        rule = MissingMandatoryFieldsRule(test_tenant, db)
        await rule.check()

        assert any("email" in i.additional_info.get("missing_fields", []) for i in rule.issues)

    async def test_detects_missing_position(
        self, db: AsyncSession, test_tenant: str
    ) -> None:
        """Test rule detects employees without position."""
        emp = Employee(
            tenant_id=test_tenant,
            first_name="Jane",
            last_name="Smith",
            email="jane@example.com",
            position=None,
        )
        db.add(emp)
        await db.commit()

        rule = MissingMandatoryFieldsRule(test_tenant, db)
        await rule.check()

        assert any("position" in i.additional_info.get("missing_fields", []) for i in rule.issues)

    async def test_skips_complete_employees(
        self, db: AsyncSession, test_tenant: str
    ) -> None:
        """Test rule doesn't flag complete employee records."""
        emp = Employee(
            tenant_id=test_tenant,
            first_name="Complete",
            last_name="Employee",
            email="complete@example.com",
            position="Worker",
        )
        db.add(emp)
        await db.commit()

        rule = MissingMandatoryFieldsRule(test_tenant, db)
        await rule.check()

        # Check that our employee doesn't have issues
        assert not any(
            i.affected_entity_id == emp.id and i.issue_type == IssueType.MISSING_FIELD
            for i in rule.issues
        )


class TestDuplicateRecordsRule:
    """Test duplicate records detection."""

    async def test_detects_duplicate_emails(
        self, db: AsyncSession, test_tenant: str
    ) -> None:
        """Test rule detects employees with duplicate emails."""
        email = "duplicate@example.com"
        emp1 = Employee(
            tenant_id=test_tenant,
            first_name="User1",
            last_name="Test",
            email=email,
            position="Worker",
        )
        emp2 = Employee(
            tenant_id=test_tenant,
            first_name="User2",
            last_name="Test",
            email=email,
            position="Worker",
        )
        db.add(emp1)
        db.add(emp2)
        await db.commit()

        rule = DuplicateRecordsRule(test_tenant, db)
        await rule.check()

        # Should find at least one duplicate
        assert any(
            i.issue_type == IssueType.DUPLICATE and i.additional_info.get("duplicate_email") == email
            for i in rule.issues
        )

    async def test_skips_unique_emails(
        self, db: AsyncSession, test_tenant: str
    ) -> None:
        """Test rule doesn't flag unique emails."""
        emp1 = Employee(
            tenant_id=test_tenant,
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            position="Worker",
        )
        emp2 = Employee(
            tenant_id=test_tenant,
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            position="Worker",
        )
        db.add(emp1)
        db.add(emp2)
        await db.commit()

        rule = DuplicateRecordsRule(test_tenant, db)
        await rule.check()

        # Should not find duplicates
        assert not any(i.issue_type == IssueType.DUPLICATE for i in rule.issues)


class TestDataQualityService:
    """Test data quality service."""

    async def test_comprehensive_check_runs_all_rules(
        self, db: AsyncSession, test_tenant: str, test_employees: list
    ) -> None:
        """Test comprehensive check executes all rules."""
        service = DataQualityService(test_tenant, db)
        report = await service.run_comprehensive_check()

        assert report.tenant_id == test_tenant
        assert report.total_issues >= 0
        assert len(report.check_results) == 4  # 4 rules
        assert all(result.rule_name for result in report.check_results)

    async def test_report_includes_completeness_percent(
        self, db: AsyncSession, test_tenant: str, test_employees: list
    ) -> None:
        """Test report includes data completeness percentage."""
        service = DataQualityService(test_tenant, db)
        report = await service.run_comprehensive_check()

        assert 0 <= report.completeness_percent <= 100

    async def test_report_categorizes_issues_by_severity(
        self, db: AsyncSession, test_tenant: str
    ) -> None:
        """Test report categorizes issues by severity."""
        # Create a missing field issue
        emp = Employee(
            tenant_id=test_tenant,
            first_name="Test",
            last_name=None,
            email="test@example.com",
            position="Worker",
        )
        db.add(emp)
        await db.commit()

        service = DataQualityService(test_tenant, db)
        report = await service.run_comprehensive_check()

        # Should have severity breakdown
        assert report.critical_issues >= 0
        assert report.high_issues >= 0
        assert report.medium_issues >= 0
        assert report.low_issues >= 0

    async def test_report_breaks_down_by_issue_type(
        self, db: AsyncSession, test_tenant: str
    ) -> None:
        """Test report includes issue type breakdown."""
        service = DataQualityService(test_tenant, db)
        report = await service.run_comprehensive_check()

        assert isinstance(report.issue_breakdown, dict)
        # Should have keys for issue types found
        for issue in report.issues:
            assert issue.issue_type.value in report.issue_breakdown or report.total_issues == 0

    async def test_report_limits_top_issues(
        self, db: AsyncSession, test_tenant: str
    ) -> None:
        """Test report returns limited top issues."""
        service = DataQualityService(test_tenant, db)
        report = await service.run_comprehensive_check()

        # Should be max 20 issues in report (even if more found)
        assert len(report.issues) <= 20


class TestDataQualityEndpoints:
    """Test data quality API endpoints."""

    async def test_get_data_quality_report_endpoint(
        self, client, authenticated_headers: dict, test_tenant: str
    ) -> None:
        """Test /api/v1/data-quality/report endpoint."""
        headers = authenticated_headers.copy()
        headers["X-Tenant-Id"] = test_tenant

        response = client.get("/api/v1/data-quality/report", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert "tenant_id" in data
        assert "total_issues" in data
        assert "completeness_percent" in data
        assert "critical_issues" in data
        assert "issues" in data
        assert "check_results" in data

    async def test_endpoint_requires_auth(
        self, client
    ) -> None:
        """Test endpoint requires authentication."""
        response = client.get("/api/v1/data-quality/report")
        assert response.status_code == 401

    async def test_endpoint_requires_tenant_header(
        self, client, authenticated_headers: dict
    ) -> None:
        """Test endpoint requires X-Tenant-Id header."""
        response = client.get("/api/v1/data-quality/report", headers=authenticated_headers)
        assert response.status_code == 400

    async def test_check_endpoint_backward_compat(
        self, client, authenticated_headers: dict, test_tenant: str
    ) -> None:
        """Test /api/v1/data-quality/check endpoint (backward compat)."""
        headers = authenticated_headers.copy()
        headers["X-Tenant-Id"] = test_tenant

        response = client.get("/api/v1/data-quality/check", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert "tenant_id" in data

    async def test_report_includes_all_issue_fields(
        self, client, authenticated_headers: dict, test_tenant: str
    ) -> None:
        """Test report includes all required issue fields."""
        headers = authenticated_headers.copy()
        headers["X-Tenant-Id"] = test_tenant

        response = client.get("/api/v1/data-quality/report", headers=headers)

        assert response.status_code == 200
        data = response.json()

        for issue in data.get("issues", []):
            assert "id" in issue
            assert "issue_type" in issue
            assert "severity" in issue
            assert "title" in issue
            assert "affected_entity_type" in issue
            assert "affected_entity_id" in issue

    async def test_report_includes_check_results(
        self, client, authenticated_headers: dict, test_tenant: str
    ) -> None:
        """Test report includes results from each check."""
        headers = authenticated_headers.copy()
        headers["X-Tenant-Id"] = test_tenant

        response = client.get("/api/v1/data-quality/report", headers=headers)

        assert response.status_code == 200
        data = response.json()
        results = data.get("check_results", [])

        # Should have results from all 4 rules
        rule_names = {r["rule_name"] for r in results}
        expected_rules = {
            "missing_mandatory_fields",
            "broken_relationships",
            "expired_records",
            "potential_duplicates",
        }
        assert expected_rules.issubset(rule_names)
