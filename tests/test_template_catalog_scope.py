from __future__ import annotations

from io import BytesIO

import pytest
from docx import Document as DocxDocument
from httpx import AsyncClient

from app.models.models import Template, TemplateVersion

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _build_template() -> bytes:
    doc = DocxDocument()
    doc.add_paragraph("Hello {{ company.name }}")
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


@pytest.mark.anyio
async def test_template_catalog_persists_scope_metadata(
    async_client: AsyncClient,
    make_auth_headers,
    sessionmaker,
) -> None:
    headers = await make_auth_headers()
    response = await async_client.post(
        "/api/v1/templates/catalog",
        json={
            "code": "org-order",
            "name": "Приказ по филиалу",
            "description": "Шаблон для филиала",
            "category": "orders",
            "status": "active",
            "scope": {
                "level": "site",
                "company_id": "company-1",
                "site_id": "branch-77",
                "label": "Филиал Север",
                "applicability": "Использовать только для северного филиала",
            },
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "active"
    assert body["category"] == "orders"
    assert body["scope"]["level"] == "site"
    assert body["scope"]["site_id"] == "branch-77"

    async with sessionmaker() as session:
        template = await session.get(Template, body["id"])
        assert template is not None
        assert template.metadata_json["category"] == "orders"
        assert template.metadata_json["scope"]["label"] == "Филиал Север"


@pytest.mark.anyio
async def test_upload_template_version_sets_current_version_id(
    async_client: AsyncClient,
    make_auth_headers,
    sessionmaker,
) -> None:
    headers = await make_auth_headers()
    create_response = await async_client.post(
        "/api/v1/templates/catalog",
        json={"code": "safety-briefing", "name": "Инструктаж", "scope": {"level": "tenant"}},
        headers=headers,
    )
    assert create_response.status_code == 201, create_response.text
    template_id = create_response.json()["id"]

    upload_response = await async_client.post(
        f"/api/v1/templates/{template_id}/versions:upload",
        files={"file": ("briefing.docx", _build_template(), DOCX_CONTENT_TYPE)},
        headers=headers,
    )
    assert upload_response.status_code == 201, upload_response.text
    version_id = upload_response.json()["id"]

    async with sessionmaker() as session:
        template = await session.get(Template, template_id)
        version = await session.get(TemplateVersion, version_id)
        assert template is not None
        assert version is not None
        assert template.current_version_id == version.id
