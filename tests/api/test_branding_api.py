from __future__ import annotations

from sqlalchemy import select

from app.models.models import Company, RoleEnum, Site
from app.modules.headers.models import HeaderFooterPreset


async def test_branding_profile_preview_and_update(async_client, sessionmaker, data_factory, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session, name="АО СеверСтрой")
        site = await data_factory.create_site(
            tenant=tenant,
            company=company,
            session=session,
            name="Филиал Север",
            address="г. Мурманск, ул. Ледовая, 1",
        )
        session.add(
            HeaderFooterPreset(
                tenant_id=str(tenant.id),
                code="company_brand",
                name="Company brand",
                header_odd_xml="{{organization.short_name}} / {{branch.name}} / {{watermark.text}} / {{doc.number}}",
                footer_odd_xml="{{organization.legal_address}}",
                watermark={"enabled": True, "text": "DRAFT"},
            )
        )
        await session.commit()
        company_id = company.id
        site_id = site.id

    update = await async_client.patch(
        f"/api/v1/branding/profile/{company_id}",
        headers=headers,
        json={
            "preferred_header_preset_code": "company_brand",
            "branding": {
                "legal_name": "АО СеверСтрой",
                "short_name": "СеверСтрой",
                "website": "https://example.test",
                "email": "office@example.test",
                "phones": ["+7 800 555-35-35"],
                "footer_details": ["ИНН 123", "КПП 456"],
                "passport_label": "Passport-1",
                "watermark_text": "DRAFT",
                "watermark_enabled": True,
                "contacts": [{"full_name": "Иван Иванов", "position": "Директор"}],
            },
        },
    )
    assert update.status_code == 200, update.text
    payload = update.json()
    assert payload["preferred_header_preset_code"] == "company_brand"
    assert payload["branding"]["short_name"] == "СеверСтрой"

    site_update = await async_client.patch(
        f"/api/v1/branding/profile/{company_id}",
        headers=headers,
        json={
            "site_id": site_id,
            "preferred_header_preset_code": "company_brand",
            "branding": {
                "branch_label": "Северный филиал",
                "service_notes": ["Площадка №7"],
                "preferred_letterhead_preset": "company_brand",
                "watermark_text": "SITE-DRAFT",
                "watermark_enabled": True,
            },
        },
    )
    assert site_update.status_code == 200, site_update.text
    site_payload = site_update.json()
    assert site_payload["scope"] == "site"
    assert site_payload["preferred_header_preset_code"] == "company_brand"
    assert site_payload["branding"]["branch_label"] == "Северный филиал"

    read_back = await async_client.get(
        "/api/v1/branding/profile",
        headers=headers,
        params={"company_id": company_id, "site_id": site_id},
    )
    assert read_back.status_code == 200, read_back.text
    assert read_back.json()["branding"]["website"] == "https://example.test"
    assert read_back.json()["branding"]["watermark_text"] == "SITE-DRAFT"

    preview = await async_client.post(
        "/api/v1/branding/preview",
        headers=headers,
        json={
            "company_id": company_id,
            "site_id": site_id,
            "document_title": "Приказ",
            "document_number": "OT-001",
            "watermark_override": {"text": "FOR-APPROVAL"},
        },
    )
    assert preview.status_code == 200, preview.text
    preview_payload = preview.json()
    assert preview_payload["sections"]["header_odd"] == "СеверСтрой / Филиал Север / FOR-APPROVAL / OT-001"
    assert preview_payload["watermark"]["text"] == "FOR-APPROVAL"
    assert preview_payload["profile"]["reproducibility"]["preferred_header_preset_code"] == "company_brand"
    assert preview_payload["profile"]["reproducibility"]["preset_id"]
    assert preview_payload["apply_headers_payload"]["preset_code"] == "company_brand"
    assert preview_payload["apply_headers_payload"]["data"]["branch"]["name"] == "Филиал Север"
    assert preview_payload["apply_headers_payload"]["data"]["reproducibility"]["preferred_header_preset_code"] == "company_brand"
    assert preview_payload["wizard_defaults"]["site_id"] == site_id
    assert preview_payload["profile"]["resolution"]["scope_chain"] == ["tenant", "company", "site"]
    assert preview_payload["profile"]["resolution"]["effective_preset_source"] == "site.branding.preferred_letterhead_preset"
    assert "organization.short_name" not in preview_payload["unresolved_placeholders"]

    async with sessionmaker() as session:
        company = (await session.execute(select(Company).where(Company.id == company_id))).scalar_one()
        site = (await session.execute(select(Site).where(Site.id == site_id))).scalar_one()
        assert company.preferred_header_preset_code == "company_brand"
        assert company.branding_payload["short_name"] == "СеверСтрой"
        assert company.branding_payload["website"] == "https://example.test"
        assert site.branding_payload["preferred_letterhead_preset"] == "company_brand"
        assert site.branding_payload["watermark_text"] == "SITE-DRAFT"


async def test_branding_patch_merges_existing_payload_and_validates_preset(async_client, sessionmaker, data_factory, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(
            tenant=tenant,
            session=session,
            name="ООО Мердж",
        )
        company.branding_payload = {
            "website": "https://before.example",
            "metadata": {"source": "seed"},
            "images": {"logo_file_id": "logo-1"},
        }
        session.add(
            HeaderFooterPreset(
                tenant_id=str(tenant.id),
                code="gost_brand",
                name="GOST",
                header_odd_xml="{{organization.short_name}}",
            )
        )
        await session.commit()
        company_id = company.id

    missing_preset = await async_client.patch(
        f"/api/v1/branding/profile/{company_id}",
        headers=headers,
        json={
            "preferred_header_preset_code": "unknown-preset",
            "branding": {"short_name": "Мердж"},
        },
    )
    assert missing_preset.status_code == 404, missing_preset.text

    merged = await async_client.patch(
        f"/api/v1/branding/profile/{company_id}",
        headers=headers,
        json={
            "preferred_header_preset_code": "gost_brand",
            "branding": {
                "short_name": "Мердж",
                "metadata": {"updated_by": "test"},
            },
        },
    )
    assert merged.status_code == 200, merged.text
    payload = merged.json()
    assert payload["branding"]["website"] == "https://before.example"
    assert payload["branding"]["images"]["logo_file_id"] == "logo-1"
    assert payload["branding"]["metadata"]["source"] == "seed"
    assert payload["branding"]["metadata"]["updated_by"] == "test"
    assert payload["reproducibility"]["branding_payload_hash"]
    assert payload["resolution"]["effective_preset_source"] == "company.preferred_header_preset_code"
