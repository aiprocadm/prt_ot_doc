from __future__ import annotations

from uuid import uuid4

from app.core.policy_engine import policy_engine
from app.models.models import RoleEnum, User


def _user(*, role: RoleEnum, company_id: str | None = None) -> User:
    return User(
        id=str(uuid4()),
        tenant_id=str(uuid4()),
        email=f"{role.value}@example.local",
        full_name=role.value,
        role=role,
        hashed_password="hash",
        company_id=company_id,
        is_active=True,
    )


def test_policy_engine_allows_documents_write_for_admin_same_company() -> None:
    user = _user(role=RoleEnum.ADMIN, company_id="cmp-1")

    decision = policy_engine.evaluate(
        user,
        action="write:documents.pipeline.run",
        resource="documents",
        attrs={"resource_company_id": "cmp-1"},
    )

    assert decision.allowed is True
    assert "tenant_scope" in decision.conditions


def test_policy_engine_denies_risk_write_for_worker() -> None:
    user = _user(role=RoleEnum.WORKER, company_id="cmp-1")

    decision = policy_engine.evaluate(
        user,
        action="write:risks.assessment.create",
        resource="risks",
        attrs={"resource_company_id": "cmp-1"},
    )

    assert decision.allowed is False
    assert decision.reason == "role_write_denied"
