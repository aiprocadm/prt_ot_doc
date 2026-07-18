from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile

from app.modules.branding.service import BrandingService
from app.modules.headers.engine import apply_headers_to_docx


def _docx_stub() -> bytes:
    buf = BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED) as z:
        z.writestr(
            "[Content_Types].xml",
            """<?xml version='1.0' encoding='UTF-8' standalone='yes'?><Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'><Default Extension='rels' ContentType='application/vnd.openxmlformats-package.relationships+xml'/><Default Extension='xml' ContentType='application/xml'/><Override PartName='/word/document.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'/><Override PartName='/word/settings.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml'/></Types>""",
        )
        z.writestr(
            "word/document.xml",
            """<?xml version='1.0' encoding='UTF-8' standalone='yes'?><w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body><w:p/><w:sectPr/></w:body></w:document>""",
        )
        z.writestr(
            "word/settings.xml",
            """<?xml version='1.0' encoding='UTF-8' standalone='yes'?><w:settings xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'/>""",
        )
    return buf.getvalue()


def main() -> None:
    tenant = SimpleNamespace(id="tenant-smoke", settings={"branding": {"watermark_text": "DRAFT", "watermark_enabled": True}})
    company = SimpleNamespace(
        id="company-smoke",
        name="АО Полигон",
        inn="7701000000",
        kpp="770101001",
        ogrn="1027701000000",
        legal_address="г. Москва, ул. Тестовая, 1",
        actual_address="г. Москва, ул. Тестовая, 1",
        email="office@polygon.example",
        contact_email="office@polygon.example",
        phone_numbers=["+7 (495) 000-00-00"],
        contact_person="Иван Иванов",
        contact_phone="+7 (495) 000-00-00",
        director="Генеральный директор",
        logo_file_id="logo-1",
        stamp_file_id="stamp-1",
        branding_payload={
            "short_name": "Полигон",
            "header_details": ["Полигон", "г. Москва, ул. Тестовая, 1"],
            "footer_details": ["ИНН 7701000000", "КПП 770101001"],
            "preferred_letterhead_preset": "brand_smoke",
        },
        preferred_header_preset_code="brand_smoke",
        updated_at=None,
    )
    site = SimpleNamespace(
        id="site-smoke",
        name="Филиал Север",
        address="г. Мурманск, ул. Ледовая, 1",
        branding_payload={"branch_label": "Северный филиал", "watermark_text": "FOR-APPROVAL", "watermark_enabled": True},
        updated_at=None,
    )
    preset = SimpleNamespace(
        code="brand_smoke",
        watermark={"enabled": True, "text": "DRAFT"},
        different_first=True,
        different_odd_even=True,
        header_first_xml="{{organization.short_name}}",
        header_odd_xml="{{organization.short_name}}\n{{branch.name}}\n{{doc.number}}",
        header_even_xml="{{organization.header_details}}",
        footer_first_xml="{{doc.passport}}",
        footer_odd_xml="{{organization.footer_details}}",
        footer_even_xml="{{watermark.text}}",
    )

    service = BrandingService(session=None, tenant=tenant)  # type: ignore[arg-type]
    profile = service.build_profile(company=company, site=site)
    assert profile.branding.header_details == ["Полигон", "г. Москва, ул. Тестовая, 1"]
    assert profile.header_context["branch"]["name"] == "Северный филиал"

    payload = service.build_apply_headers_payload(
        profile=profile,
        preset=preset,
        document_title="Приказ по охране труда",
        document_number="OT-2026-SMOKE",
        generated_at="2026-03-20",
        watermark_override={"enabled": True, "text": "FOR-APPROVAL"},
    )
    out, report = apply_headers_to_docx(
        docx_bytes=_docx_stub(),
        preset=preset,
        context=payload["data"],
        watermark_override=payload["watermark_override"],
    )

    with ZipFile(BytesIO(out), "r") as z:
        header_default = z.read("word/header2.xml").decode("utf-8")
        footer_default = z.read("word/footer2.xml").decode("utf-8")
        assert "Полигон" in header_default
        assert "Северный филиал" in header_default
        assert "OT-2026-SMOKE" in header_default
        assert "ИНН 7701000000" in footer_default

    assert "word/header2.xml" in report.changed_parts
    print("branded document smoke passed")


if __name__ == "__main__":
    main()
