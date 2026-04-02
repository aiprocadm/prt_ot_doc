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
