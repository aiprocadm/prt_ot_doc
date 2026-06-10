# tests/api/test_contractor_document_requirements_api.py
"""Contractor document-requirement policy CRUD + isolation + feature-gate + checklist."""
from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import RoleEnum

BASE = "/api/v1/contractors/document-requirements"


@pytest.mark.asyncio
async def test_create_list_delete_requirement(async_client: AsyncClient, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.ADMIN)

    resp = await async_client.post(
        BASE, headers=headers,
        json={"doc_type": "sro", "scope": "company", "mandatory": True},
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    req_id = resp.json()["id"]
    assert resp.json()["doc_type"] == "sro"
    assert resp.json()["scope"] == "company"
    assert resp.json()["mandatory"] is True

    listed = await async_client.get(BASE, headers=headers)
    assert listed.status_code == status.HTTP_200_OK, listed.text
    assert any(item["id"] == req_id for item in listed.json()["items"])

    deleted = await async_client.delete(f"{BASE}/{req_id}", headers=headers)
    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    listed2 = await async_client.get(BASE, headers=headers)
    assert all(item["id"] != req_id for item in listed2.json()["items"])


@pytest.mark.asyncio
async def test_duplicate_requirement_returns_409(async_client, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    payload = {"doc_type": "insurance", "scope": "company", "mandatory": True}
    first = await async_client.post(BASE, headers=headers, json=payload)
    assert first.status_code == status.HTTP_201_CREATED, first.text
    dup = await async_client.post(BASE, headers=headers, json=payload)
    assert dup.status_code == status.HTTP_409_CONFLICT, dup.text


@pytest.mark.asyncio
async def test_invalid_scope_returns_422(async_client, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.post(
        BASE, headers=headers,
        json={"doc_type": "sro", "scope": "bogus", "mandatory": True},
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, resp.text


@pytest.mark.asyncio
async def test_reader_cannot_create_requirement(async_client, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.INSPECTOR_CONTRACTOR)
    resp = await async_client.post(
        BASE, headers=headers,
        json={"doc_type": "sro", "scope": "company", "mandatory": True},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.text


# ---------------------------------------------------------------------------
# Document checklist (wizard deliverable)
# ---------------------------------------------------------------------------

from datetime import date, datetime, timedelta, timezone

from app.modules.contractors.models import (
    ComplianceStatus,
    ContractorDocument,
    ContractorEmployee,
    ContractorRegistry,
)

TODAY = date.today()


async def _seed_employee(sessionmaker, data_factory) -> tuple[str, str, str]:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        contractor = ContractorRegistry(tenant_id=tid, name="Chk Contractor")
        session.add(contractor)
        await session.flush()
        emp = ContractorEmployee(tenant_id=tid, contractor_id=contractor.id, full_name="Chk Worker")
        session.add(emp)
        await session.commit()
        return tid, str(contractor.id), str(emp.id)


@pytest.mark.asyncio
async def test_checklist_reports_status_and_satisfied_by(async_client, sessionmaker, data_factory, make_auth_headers):
    tid, contractor_id, emp_id = await _seed_employee(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    # one company rule (satisfied) + one employee rule (missing)
    await async_client.post(BASE, headers=headers, json={"doc_type": "sro", "scope": "company", "mandatory": True})
    await async_client.post(BASE, headers=headers, json={"doc_type": "medical_cert", "scope": "employee", "mandatory": True})

    # satisfying company document
    async with sessionmaker() as session:
        session.add(ContractorDocument(
            tenant_id=tid, contractor_id=contractor_id, doc_type="sro", title="СРО",
            valid_until=TODAY + timedelta(days=90), status="active",
        ))
        await session.commit()

    resp = await async_client.get(f"/api/v1/contractors/employees/{emp_id}/document-checklist", headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
    items = {i["doc_type"]: i for i in resp.json()["items"]}
    assert items["sro"]["status"] == "ok"
    assert items["sro"]["satisfied_by"] is not None
    assert items["medical_cert"]["status"] == "missing"
    assert items["medical_cert"]["satisfied_by"] is None


# ---------------------------------------------------------------------------
# Admission e2e: documents gate /admit
# ---------------------------------------------------------------------------


async def _seed_ready_employee_db(sessionmaker, data_factory) -> tuple[str, str]:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        contractor = ContractorRegistry(tenant_id=tid, name="Admit Contractor")
        session.add(contractor)
        await session.flush()
        now = datetime.now(timezone.utc)
        emp = ContractorEmployee(
            tenant_id=tid, contractor_id=contractor.id, full_name="Admit Worker",
            access_status=ComplianceStatus.VALID, training_status=ComplianceStatus.VALID,
            medical_status=ComplianceStatus.VALID, last_training_at=now,
            next_medical_at=now + timedelta(days=200),
        )
        session.add(emp)
        await session.commit()
        return tid, str(emp.id)


@pytest.mark.asyncio
async def test_admit_blocked_by_missing_mandatory_document(async_client, sessionmaker, data_factory, make_auth_headers):
    _tid, emp_id = await _seed_ready_employee_db(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    # base 3 dims are clear; add a mandatory employee document rule with no document
    await async_client.post(BASE, headers=headers, json={"doc_type": "medical_cert", "scope": "employee", "mandatory": True})

    resp = await async_client.post(f"/api/v1/contractors/employees/{emp_id}/admit", headers=headers)
    assert resp.status_code == status.HTTP_409_CONFLICT, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "requirements_not_met"
    violations = [v for d in detail["details"] for v in d["violations"]]
    assert "document:medical_cert" in violations


@pytest.mark.asyncio
async def test_admit_passes_when_document_present(async_client, sessionmaker, data_factory, make_auth_headers):
    tid, emp_id = await _seed_ready_employee_db(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    await async_client.post(BASE, headers=headers, json={"doc_type": "medical_cert", "scope": "employee", "mandatory": True})
    async with sessionmaker() as session:
        from sqlalchemy import select as _select
        emp = (await session.execute(_select(ContractorEmployee).where(ContractorEmployee.id == emp_id))).scalar_one()
        session.add(ContractorDocument(
            tenant_id=tid, contractor_id=emp.contractor_id, employee_id=emp_id,
            doc_type="medical_cert", title="Медзаключение",
            valid_until=TODAY + timedelta(days=90), status="active",
        ))
        await session.commit()

    resp = await async_client.post(f"/api/v1/contractors/employees/{emp_id}/admit", headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
    assert resp.json()["status"] == "allowed"
