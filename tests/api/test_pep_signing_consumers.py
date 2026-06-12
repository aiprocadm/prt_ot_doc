"""PEP consumers: approval gate (document), signed-dispatch (DocumentVersion,
PPEIssue.signature_doc_ref), verify protocol."""
from __future__ import annotations

import pytest

from app.domains.signing.pep import PepStatus
from app.models.document import DocumentVersion
from app.models.models import ApprovalInstance, ApprovalRoute, PPEIssue
from app.models.approval_workflow import ApprovalInstanceStatus
from app.services.pep_signing import PepApprovalRequired, PepSigningService


async def _doc_version(session, data_factory, *, tag: str):
    """Create a tenant + Document + DocumentVersion via the factory.

    Document requires company_id, template_id, created_by (all NOT NULL) — the
    factory's create_document() provisions all of them automatically. After the
    factory call the session is still open (factory commits internally), so we
    can keep adding objects to it.

    Returns (tenant, doc, ver).
    """
    tenant = await data_factory.ensure_tenant(session=session)
    _doc, ver = await data_factory.create_document(
        tenant=tenant,
        session=session,
        version_file_key=f"docs/{tag}.docx",
    )
    return tenant, _doc, ver


@pytest.mark.asyncio
async def test_document_sign_no_route_projects_status(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, _doc, ver = await _doc_version(session, data_factory, tag="g1")
        svc = PepSigningService(session, str(tenant.id))
        req, _ = await svc.create_request(
            object_type="document_version", object_id=ver.id, purpose="document",
            signer_user_id="user-1", requested_by="user-1",
        )
        assert req.status == PepStatus.SIGNED.value
        assert ver.signature_status == "signed"


@pytest.mark.asyncio
async def test_document_sign_blocked_until_instance_approved(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, doc, ver = await _doc_version(session, data_factory, tag="g2")
        route = ApprovalRoute(tenant_id=tenant.id, code=f"r-{ver.id[:8]}", name="Маршрут")
        session.add(route)
        await session.flush()
        instance = ApprovalInstance(
            tenant_id=tenant.id, entity_type="document", entity_id=ver.id,
            approval_route_id=route.id, status=ApprovalInstanceStatus.RUNNING,
            started_by="user-1",
        )
        session.add(instance)
        await session.flush()
        svc = PepSigningService(session, str(tenant.id))
        # Гейт согласования кидает специализированный подкласс PepConflict.
        with pytest.raises(PepApprovalRequired):
            await svc.create_request(
                object_type="document_version", object_id=ver.id, purpose="document",
                signer_user_id="user-1", requested_by="user-1",
            )
        instance.status = ApprovalInstanceStatus.APPROVED
        await session.flush()
        req, _ = await svc.create_request(
            object_type="document_version", object_id=ver.id, purpose="document",
            signer_user_id="user-1", requested_by="user-1",
        )
        assert req.status == PepStatus.SIGNED.value


@pytest.mark.asyncio
async def test_acknowledgement_skips_approval_gate(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, doc, ver = await _doc_version(session, data_factory, tag="g3")
        route = ApprovalRoute(tenant_id=tenant.id, code=f"r2-{ver.id[:8]}", name="Маршрут")
        session.add(route)
        await session.flush()
        session.add(ApprovalInstance(
            tenant_id=tenant.id, entity_type="document", entity_id=ver.id,
            approval_route_id=route.id, status=ApprovalInstanceStatus.RUNNING,
            started_by="user-1",
        ))
        company = await data_factory.create_company(tenant=tenant, session=session, name="ACK g3")
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        await session.flush()
        svc = PepSigningService(session, str(tenant.id))
        req, code = await svc.create_request(
            object_type="document_version", object_id=ver.id, purpose="acknowledgement",
            signer_person_id=person.id, requested_by="user-1",
        )
        assert req.status == PepStatus.AWAITING_CODE.value
        signed = await svc.confirm(req.id, code=code)
        # ознакомление НЕ трогает signature_status документа
        assert ver.signature_status is None
        assert signed.purpose == "acknowledgement"


@pytest.mark.asyncio
async def test_ppe_issue_signed_sets_signature_doc_ref(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session, name="PPE d1")
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        issue = PPEIssue(
            tenant_id=tenant.id, person_id=person.id,
            item_name="Каска d1", quantity=1, status="issued",
        )
        session.add(issue)
        await session.flush()
        svc = PepSigningService(session, str(tenant.id))
        req, code = await svc.create_request(
            object_type="ppe_issue", object_id=issue.id, purpose="ppe_issue",
            signer_person_id=person.id, requested_by="user-1",
        )
        await svc.confirm(req.id, code=code)
        assert issue.signature_doc_ref == f"pep:{req.id}"


@pytest.mark.asyncio
async def test_verify_detects_content_drift(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session, name="PPE v1")
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        issue = PPEIssue(
            tenant_id=tenant.id, person_id=person.id,
            item_name="Каска v1", quantity=1, status="issued",
        )
        session.add(issue)
        await session.flush()
        svc = PepSigningService(session, str(tenant.id))
        req, code = await svc.create_request(
            object_type="ppe_issue", object_id=issue.id, purpose="ppe_issue",
            signer_person_id=person.id, requested_by="user-1",
        )
        await svc.confirm(req.id, code=code)

        ok = await svc.verify(req.id)
        assert ok["match"] is True

        issue.quantity = 99  # дрейф содержимого после подписи
        await session.flush()
        drifted = await svc.verify(req.id)
        assert drifted["match"] is False
        assert req.verification_result_json["match"] is False


@pytest.mark.asyncio
async def test_create_attested_signs_instantly_for_person(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session, name="ATT a1")
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        issue = PPEIssue(
            tenant_id=tenant.id, person_id=person.id,
            item_name="Каска a1", quantity=1, status="issued",
        )
        session.add(issue)
        await session.flush()
        svc = PepSigningService(session, str(tenant.id))
        req = await svc.create_attested(
            object_type="ppe_issue", object_id=issue.id, purpose="ppe_issue",
            requested_by="user-9", signer_person_id=person.id,
        )
        assert req.status == PepStatus.SIGNED.value
        assert req.result_json["attested_by"] == "user-9"
        assert req.signed_at is not None
        # attested тоже проходит через _mark_signed → _dispatch_signed
        assert issue.signature_doc_ref == f"pep:{req.id}"
