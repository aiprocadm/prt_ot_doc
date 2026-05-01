from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.security import AccessContext
from app.models.models import RoleEnum, User


def _user(role: RoleEnum, user_id: str = "user-1") -> User:
    return User(
        id=user_id,
        tenant_id="tenant-1",
        email=f"{user_id}@example.com",
        full_name="User",
        role=role,
        hashed_password="hashed",
        is_active=True,
    )


def test_abac_site_scope_denies_mismatch():
    access = AccessContext(
        user=_user(RoleEnum.EMPLOYEE),
        claims={"site_ids": ["site-1"]},
        tenant_slug="test",
        tenant_id=None,
        company_id=None,
    )
    with pytest.raises(HTTPException):
        access.ensure_abac(site_id="site-2")


def test_abac_document_draft_restricted():
    access = AccessContext(
        user=_user(RoleEnum.EMPLOYEE),
        claims={},
        tenant_slug="test",
        tenant_id=None,
        company_id=None,
    )
    with pytest.raises(HTTPException):
        access.ensure_abac(
            document_id="doc-1",
            document_status="draft",
            document_owner_id="someone-else",
        )


def test_abac_risk_level_high_requires_privilege():
    access = AccessContext(
        user=_user(RoleEnum.EMPLOYEE),
        claims={},
        tenant_slug="test",
        tenant_id=None,
        company_id=None,
    )
    with pytest.raises(HTTPException):
        access.ensure_abac(risk_level="high")

    privileged = AccessContext(
        user=_user(RoleEnum.ADMIN, user_id="admin"),
        claims={},
        tenant_slug="test",
        tenant_id=None,
        company_id=None,
    )
    privileged.ensure_abac(risk_level="high")


def test_abac_company_scope_denies_mismatch():
    access = AccessContext(
        user=_user(RoleEnum.MANAGER),
        claims={"company_ids": ["company-1"]},
        tenant_slug="test",
        tenant_id=None,
        company_id=None,
    )
    with pytest.raises(HTTPException):
        access.ensure_abac(company_id="company-2")


def test_abac_project_scope_denies_mismatch():
    access = AccessContext(
        user=_user(RoleEnum.EMPLOYEE),
        claims={"project_ids": ["proj-1"]},
        tenant_slug="test",
        tenant_id=None,
        company_id=None,
    )
    with pytest.raises(HTTPException):
        access.ensure_abac(project_id="proj-2")


def test_abac_contractor_scope_denies_mismatch():
    access = AccessContext(
        user=_user(RoleEnum.ADMIN),
        claims={"contractor_ids": ["contr-1"]},
        tenant_slug="test",
        tenant_id=None,
        company_id=None,
    )
    with pytest.raises(HTTPException):
        access.ensure_abac(contractor_id="contr-2")
