"""API contract for prescription evidence-FILE attachment (TZ-3.4-V12-01, W-A).

A prescription may be completed with attached evidence files (linked via
FileLink, role="evidence") instead of — or in addition to — a textual note.
Attached files must be tenant-owned and antivirus-clean.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import status
from sqlalchemy import select

from app.models.models import PrescriptionStatus, RoleEnum, Tenant
from app.modules.files.models import FileLink, FileRecord


async def _seed_company_site(sessionmaker, data_factory) -> tuple[str, str, str]:
    """Seed tenant + company + site; return (tenant_id, company_id, site_id)."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(tenant=tenant, company=company, session=session)
        await session.commit()
        return tenant.id, company.id, site.id


async def _make_file(
    sessionmaker,
    tenant_id: str,
    *,
    status_value: str = "clean",
    original_filename: str | None = "evidence.pdf",
) -> str:
    """Insert a FileRecord directly and return its id."""
    async with sessionmaker() as session:
        record = FileRecord(
            tenant_id=tenant_id,
            bucket="ptd",
            object_key=f"tenants/{tenant_id}/files/evidence-{status_value}.pdf",
            content_type="application/pdf",
            size_bytes=1024,
            sha256="0" * 64,
            status=status_value,
            original_filename=original_filename,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record.id


async def _seed_prescription(async_client, headers, company_id: str, site_id: str) -> str:
    insp = await async_client.post(
        "/api/v1/inspections",
        json={
            "company_id": company_id,
            "site_id": site_id,
            "authority": "Ростехнадзор",
            "scheduled_at": date.today().isoformat(),
        },
        headers=headers,
    )
    assert insp.status_code == status.HTTP_201_CREATED, insp.text
    pres = await async_client.post(
        "/api/v1/prescriptions",
        json={"inspection_id": insp.json()["id"], "description": "Fix guardrail"},
        headers=headers,
    )
    assert pres.status_code == status.HTTP_201_CREATED, pres.text
    return pres.json()["id"]


async def _transition(async_client, pid, headers, to, **extra):
    return await async_client.post(
        f"/api/v1/prescriptions/{pid}/transition",
        json={"to": to, **extra},
        headers=headers,
    )


@pytest.mark.asyncio
async def test_complete_with_evidence_file_only_links_and_lists(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    tenant_id, company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    pid = await _seed_prescription(async_client, headers, company_id, site_id)
    await _transition(async_client, pid, headers, PrescriptionStatus.IN_PROGRESS.value)
    file_id = await _make_file(sessionmaker, tenant_id, status_value="clean")

    # No text evidence — a single clean file alone must satisfy completion.
    r = await _transition(
        async_client,
        pid,
        headers,
        PrescriptionStatus.COMPLETED.value,
        evidence_file_ids=[file_id],
    )
    assert r.status_code == status.HTTP_200_OK, r.text
    body = r.json()
    assert body["status"] == PrescriptionStatus.COMPLETED.value
    returned_ids = [f["file_id"] for f in body["evidence_files"]]
    assert returned_ids == [file_id]

    # A FileLink row was created with entity_type=prescription, role=evidence.
    async with sessionmaker() as session:
        link = (
            await session.execute(
                select(FileLink).where(
                    FileLink.entity_type == "prescription",
                    FileLink.entity_id == pid,
                    FileLink.file_id == file_id,
                    FileLink.role == "evidence",
                )
            )
        ).scalar_one_or_none()
        assert link is not None

    # GET surfaces the same evidence file.
    g = await async_client.get(f"/api/v1/prescriptions/{pid}", headers=headers)
    assert g.status_code == status.HTTP_200_OK, g.text
    assert [f["file_id"] for f in g.json()["evidence_files"]] == [file_id]


@pytest.mark.asyncio
async def test_complete_rejects_unclean_file_422(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    tenant_id, company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    pid = await _seed_prescription(async_client, headers, company_id, site_id)
    await _transition(async_client, pid, headers, PrescriptionStatus.IN_PROGRESS.value)
    file_id = await _make_file(sessionmaker, tenant_id, status_value="uploaded")  # not scanned

    r = await _transition(
        async_client,
        pid,
        headers,
        PrescriptionStatus.COMPLETED.value,
        evidence_file_ids=[file_id],
    )
    assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text
    assert r.json()["detail"]["code"] == "evidence_file_not_clean"


@pytest.mark.asyncio
async def test_complete_rejects_cross_tenant_file_404(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    _tenant_id, company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    pid = await _seed_prescription(async_client, headers, company_id, site_id)
    await _transition(async_client, pid, headers, PrescriptionStatus.IN_PROGRESS.value)

    # A clean file owned by a DIFFERENT tenant must not be linkable.
    async with sessionmaker() as session:
        other = (await session.execute(select(Tenant).where(Tenant.slug == "beta"))).scalar_one()
        other_tenant_id = other.id
    foreign_file_id = await _make_file(sessionmaker, other_tenant_id, status_value="clean")

    r = await _transition(
        async_client,
        pid,
        headers,
        PrescriptionStatus.COMPLETED.value,
        evidence_file_ids=[foreign_file_id],
    )
    assert r.status_code == status.HTTP_404_NOT_FOUND, r.text
    assert r.json()["detail"]["code"] == "evidence_file_not_found"


@pytest.mark.asyncio
async def test_relinking_same_file_is_idempotent(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    tenant_id, company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    pid = await _seed_prescription(async_client, headers, company_id, site_id)
    await _transition(async_client, pid, headers, PrescriptionStatus.IN_PROGRESS.value)
    file_id = await _make_file(sessionmaker, tenant_id, status_value="clean")

    # Complete with the file, rework back, then complete again with the SAME file.
    await _transition(
        async_client,
        pid,
        headers,
        PrescriptionStatus.COMPLETED.value,
        evidence_file_ids=[file_id],
    )
    await _transition(
        async_client, pid, headers, PrescriptionStatus.IN_PROGRESS.value, note="rework"
    )
    r = await _transition(
        async_client,
        pid,
        headers,
        PrescriptionStatus.COMPLETED.value,
        evidence_file_ids=[file_id],
    )
    assert r.status_code == status.HTTP_200_OK, r.text
    # Still a single evidence file — re-linking the same file must not duplicate.
    assert [f["file_id"] for f in r.json()["evidence_files"]] == [file_id]

    async with sessionmaker() as session:
        links = (
            (
                await session.execute(
                    select(FileLink).where(
                        FileLink.entity_type == "prescription",
                        FileLink.entity_id == pid,
                        FileLink.file_id == file_id,
                        FileLink.role == "evidence",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(links) == 1


@pytest.mark.asyncio
async def test_evidence_display_name_falls_back_to_object_key(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    tenant_id, company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    pid = await _seed_prescription(async_client, headers, company_id, site_id)
    await _transition(async_client, pid, headers, PrescriptionStatus.IN_PROGRESS.value)
    # No original_filename — display_name must fall back to the object_key basename.
    file_id = await _make_file(
        sessionmaker, tenant_id, status_value="clean", original_filename=None
    )

    r = await _transition(
        async_client,
        pid,
        headers,
        PrescriptionStatus.COMPLETED.value,
        evidence_file_ids=[file_id],
    )
    assert r.status_code == status.HTTP_200_OK, r.text
    ref = r.json()["evidence_files"][0]
    assert ref["display_name"] == "evidence-clean.pdf"
