"""Ф4 API печати наряда: DOCX 200 + заголовки; cross-tenant 404; невалидный формат 422."""
from __future__ import annotations

import pytest

from app.models.models import RoleEnum

BASE = "/api/v1/work-permits"


@pytest.mark.asyncio
async def test_print_docx_returns_file(async_client, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    r = await async_client.post(
        f"{BASE}", headers=headers,
        json={"work_type": "height", "zone_text": "фасад", "number": "НД-9"},
    )
    assert r.status_code == 201, r.text
    wp_id = r.json()["id"]

    resp = await async_client.get(f"{BASE}/{wp_id}/print?format=docx", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert "attachment" in resp.headers.get("content-disposition", "")
    assert resp.content[:2] == b"PK"  # DOCX = zip


@pytest.mark.asyncio
async def test_print_invalid_format_422(async_client, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    r = await async_client.post(
        f"{BASE}", headers=headers,
        json={"work_type": "height", "zone_text": "z"},
    )
    assert r.status_code == 201, r.text
    wp_id = r.json()["id"]
    resp = await async_client.get(f"{BASE}/{wp_id}/print?format=xml", headers=headers)
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_print_cross_tenant_404(async_client, make_auth_headers, data_factory):
    # Создаём два разных тенанта и получаем хедеры с уникальными email-ами
    tenant_a = await data_factory.ensure_tenant(slug="wp-print-ta")
    tenant_b = await data_factory.ensure_tenant(slug="wp-print-tb")
    headers_a = await make_auth_headers(
        RoleEnum.ADMIN, tenant="wp-print-ta", email="admin-wp-print-ta@example.com"
    )
    headers_b = await make_auth_headers(
        RoleEnum.ADMIN, tenant="wp-print-tb", email="admin-wp-print-tb@example.com"
    )
    # Создаём наряд в тенанте A
    r = await async_client.post(
        f"{BASE}", headers=headers_a,
        json={"work_type": "height", "zone_text": "z"},
    )
    assert r.status_code == 201, r.text
    wp_id = r.json()["id"]
    # Запрашиваем печать от тенанта B → 404
    resp = await async_client.get(f"{BASE}/{wp_id}/print?format=docx", headers=headers_b)
    assert resp.status_code == 404, resp.text
