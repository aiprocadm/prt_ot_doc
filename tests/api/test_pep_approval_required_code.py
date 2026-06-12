"""Отдельный код ошибки PEP_APPROVAL_REQUIRED для гейта согласования.

Контракт: непройденный гейт по ApprovalInstance → 409 code="PEP_APPROVAL_REQUIRED"
(подкласс PepApprovalRequired(PepConflict)); все прочие ПЭП-конфликты остаются
409 code="PEP_CONFLICT".
"""
from __future__ import annotations

import pytest

from app.models.models import ApprovalInstance, ApprovalRoute, PPEIssue, RoleEnum
from app.models.approval_workflow import ApprovalInstanceStatus
from app.services.pep_signing import PepApprovalRequired, PepConflict, PepSigningService


def test_pep_approval_required_is_pep_conflict_subclass():
    """Минимальная инвазивность: старые except PepConflict продолжают ловить гейт."""
    assert issubclass(PepApprovalRequired, PepConflict)


async def _doc_with_running_instance(session, data_factory, *, tag: str):
    tenant = await data_factory.ensure_tenant(session=session)
    _doc, ver = await data_factory.create_document(
        tenant=tenant, session=session, version_file_key=f"docs/apr-{tag}.docx"
    )
    route = ApprovalRoute(tenant_id=tenant.id, code=f"apr-{ver.id[:8]}", name="Маршрут")
    session.add(route)
    await session.flush()
    session.add(
        ApprovalInstance(
            tenant_id=tenant.id, entity_type="document", entity_id=ver.id,
            approval_route_id=route.id, status=ApprovalInstanceStatus.RUNNING,
            started_by="user-1",
        )
    )
    await session.flush()
    return tenant, ver


@pytest.mark.asyncio
async def test_service_gate_raises_pep_approval_required(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, ver = await _doc_with_running_instance(session, data_factory, tag="svc")
        svc = PepSigningService(session, str(tenant.id))
        with pytest.raises(PepApprovalRequired):
            await svc.create_request(
                object_type="document_version", object_id=ver.id, purpose="document",
                signer_user_id="user-1", requested_by="user-1",
            )


@pytest.mark.asyncio
async def test_pep_requests_endpoint_maps_gate_to_approval_required_code(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:
        tenant, ver = await _doc_with_running_instance(session, data_factory, tag="api")
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)
    resp = await async_client.post(
        "/api/v1/sign/pep/requests",
        json={
            "object_type": "document_version", "object_id": ver.id,
            "purpose": "document", "signer_user_id": "user-1",
        },
        headers=headers,
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "PEP_APPROVAL_REQUIRED"


@pytest.mark.asyncio
async def test_edo_signatures_endpoint_maps_gate_to_approval_required_code(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    """edo_workflow POST /signatures: тот же гейт → PEP_APPROVAL_REQUIRED."""
    async with sessionmaker() as session:
        tenant, ver = await _doc_with_running_instance(session, data_factory, tag="edo")
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)
    resp = await async_client.post(
        "/api/v1/signatures",
        json={"document_version_id": ver.id, "type": "INTERNAL"},
        headers=headers,
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "PEP_APPROVAL_REQUIRED"


@pytest.mark.asyncio
async def test_edo_sign_submit_endpoint_maps_gate_to_approval_required_code(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    """edo_workflow POST /sign/submit: тот же гейт → PEP_APPROVAL_REQUIRED."""
    async with sessionmaker() as session:
        tenant, ver = await _doc_with_running_instance(session, data_factory, tag="sub")
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)
    resp = await async_client.post(
        "/api/v1/sign/submit",
        json={"document_version_id": ver.id, "kind": "INTERNAL", "signed_blob": "stub"},
        headers=headers,
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "PEP_APPROVAL_REQUIRED"


@pytest.mark.asyncio
async def test_generic_conflict_keeps_pep_conflict_code(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    """Не-гейтовый конфликт (активный дубль запроса) остаётся PEP_CONFLICT."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session, name="PEP DUP")
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        issue = PPEIssue(
            tenant_id=tenant.id, person_id=person.id,
            item_name="Каска dup", quantity=1, status="issued",
        )
        session.add(issue)
        await session.commit()
        issue_id = issue.id
        person_id = person.id
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)
    payload = {
        "object_type": "ppe_issue", "object_id": issue_id,
        "purpose": "ppe_issue", "signer_person_id": person_id,
    }
    first = await async_client.post("/api/v1/sign/pep/requests", json=payload, headers=headers)
    assert first.status_code == 201, first.text
    dup = await async_client.post("/api/v1/sign/pep/requests", json=payload, headers=headers)
    assert dup.status_code == 409, dup.text
    assert dup.json()["detail"]["code"] == "PEP_CONFLICT"
