"""HTTP contract: BriefingTemplate.require_signature_code CRUD + code-flow cycle."""
from __future__ import annotations

import pytest

from app.models.models import RoleEnum


@pytest.mark.asyncio
async def test_template_require_signature_code_roundtrip(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)

    created = await async_client.post(
        "/api/v1/briefings/templates",
        json={
            "code": "BRF-CODE-T1",
            "title": "Вводный с кодом",
            "briefing_type": "primary",
            "require_signature_code": True,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["require_signature_code"] is True

    # default остаётся false, когда поле не передано
    created2 = await async_client.post(
        "/api/v1/briefings/templates",
        json={"code": "BRF-CODE-T2", "title": "Без кода", "briefing_type": "primary"},
        headers=headers,
    )
    assert created2.status_code == 201, created2.text
    assert created2.json()["require_signature_code"] is False
