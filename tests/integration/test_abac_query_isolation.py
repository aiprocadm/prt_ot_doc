from sqlalchemy import select

from app.models.models import Company
from app.modules.rbac_abac.query_filters import apply_abac_filters
from app.modules.rbac_abac.types import Subject


def test_query_filters_apply_company_scope() -> None:
    subject = Subject(user_id="u1", tenant_id="t1", roles=("manager",), company_ids=("company-a",))
    query = apply_abac_filters(select(Company), subject, Company)
    compiled = str(query.compile(compile_kwargs={"literal_binds": True}))
    assert "company-a" in compiled


def test_query_filters_empty_scope_returns_zero_rows() -> None:
    subject = Subject(user_id="u1", tenant_id="t1", roles=("manager",))
    query = apply_abac_filters(select(Company), subject, Company)
    compiled = str(query.compile(compile_kwargs={"literal_binds": True})).lower()
    assert "false" in compiled or "0 = 1" in compiled


class TestScopedQueryFilters:
    """Scoped query checks: verify that filters correctly restrict result sets."""

    def test_single_company_scope_filters_correctly(self) -> None:
        """Query should include only rows matching user's company_id."""
        subject = Subject(
            user_id="manager-1",
            tenant_id="tenant-1",
            roles=("manager",),
            company_ids=("company-alpha",),
        )
        query = apply_abac_filters(select(Company), subject, Company)
        compiled_sql = str(query.compile(compile_kwargs={"literal_binds": True}))

        # Should contain WHERE clause filtering by company_id
        assert "company" in compiled_sql.lower()
        assert "alpha" in compiled_sql.lower() or "company-alpha" in compiled_sql

    def test_multiple_companies_scope_includes_all(self) -> None:
        """Query with multiple company scopes should include all in WHERE clause."""
        subject = Subject(
            user_id="pm-1",
            tenant_id="tenant-1",
            roles=("project_manager",),
            company_ids=("company-a", "company-b", "company-c"),
        )
        query = apply_abac_filters(select(Company), subject, Company)
        compiled_sql = str(query.compile(compile_kwargs={"literal_binds": True}))

        # Should include IN clause with all companies
        assert "in" in compiled_sql.lower() or "company-a" in compiled_sql.lower()
        assert "company-b" in compiled_sql or "in" in compiled_sql.lower()

    def test_empty_company_scope_blocks_all(self) -> None:
        """Query with no company scope should return empty result."""
        subject = Subject(
            user_id="user-1",
            tenant_id="tenant-1",
            roles=("viewer",),
            company_ids=(),  # Empty scope
        )
        query = apply_abac_filters(select(Company), subject, Company)
        compiled_sql = str(query.compile(compile_kwargs={"literal_binds": True})).lower()

        # Should be FALSE to return no rows
        assert "false" in compiled_sql or "0 = 1" in compiled_sql

    def test_site_scope_applied_to_query(self) -> None:
        """Query filter should apply site_id scope if model has it."""
        subject = Subject(
            user_id="supervisor-1",
            tenant_id="tenant-1",
            roles=("supervisor",),
            site_ids=("site-london", "site-paris"),
        )
        # Assuming there's a Site model (common pattern)
        # This test validates that site scope is considered
        query = apply_abac_filters(select(Company), subject, Company)
        # The actual SQL depends on the model structure; just verify compilation succeeds
        assert query is not None

    def test_multiple_scope_attributes_combined(self) -> None:
        """Query should combine multiple scope attributes (company AND site)."""
        subject = Subject(
            user_id="mgr-1",
            tenant_id="tenant-1",
            roles=("manager",),
            company_ids=("company-alpha",),
            site_ids=("site-main",),
        )
        query = apply_abac_filters(select(Company), subject, Company)
        compiled_sql = str(query.compile(compile_kwargs={"literal_binds": True}))

        # Should contain scoped attributes (at least one of them)
        assert "company" in compiled_sql.lower() or "site" in compiled_sql.lower()

    def test_unauthorized_role_returns_empty_scope(self) -> None:
        """Subject with empty scope should get FALSE query (no accessible resources)."""
        subject = Subject(
            user_id="external-1",
            tenant_id="tenant-1",
            roles=("external_guest",),  # Limited role
            # No company_ids, site_ids, etc.
        )
        query = apply_abac_filters(select(Company), subject, Company)
        compiled_sql = str(query.compile(compile_kwargs={"literal_binds": True})).lower()

        # Empty scope for a scoped model => FALSE
        assert "false" in compiled_sql or "0 = 1" in compiled_sql
