from __future__ import annotations

from sqlalchemy import select

from app.models.models import Company, RoleEnum
from app.modules.headers.models import HeaderFooterPreset


async def test_branding_profile_preview_and_update(async_client, sessionmaker, data_factory, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session, name="АО СеверСтрой")
        session.add(
            HeaderFooterPreset(
                tenant_id=str(tenant.id),
                code="company_brand",
                name="Company brand",
                header_odd_xml="{{organization.short_name}} / {{doc.number}}",
                footer_odd_xml="{{organization.legal_address}}",
                watermark={"enabled": True, "text": "DRAFT"},
            )
        )
        await session.commit()
        company_id = company.id

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

    read_back = await async_client.get(
        "/api/v1/branding/profile",
        headers=headers,
        params={"company_id": company_id},
    )
    assert read_back.status_code == 200, read_back.text
    assert read_back.json()["branding"]["website"] == "https://example.test"

    preview = await async_client.post(
        "/api/v1/branding/preview",
        headers=headers,
        json={
            "company_id": company_id,
            "preset_code": "company_brand",
            "document_title": "Приказ",
            "document_number": "OT-001",
        },
    )
    assert preview.status_code == 200, preview.text
    preview_payload = preview.json()
    assert preview_payload["sections"]["header_odd"] == "СеверСтрой / OT-001"
    assert "organization.short_name" not in preview_payload["unresolved_placeholders"]

    async with sessionmaker() as session:
        company = (await session.execute(select(Company).where(Company.id == company_id))).scalar_one()
        assert company.preferred_header_preset_code == "company_brand"
        assert company.branding_payload["short_name"] == "СеверСтрой"
