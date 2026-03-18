from __future__ import annotations

import pytest
from app.models.models import RoleEnum


@pytest.mark.anyio
async def test_marketplace_publish_and_install_package_preset(async_client, sessionmaker, data_factory, make_auth_headers):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    created = await async_client.post(
        "/api/v1/marketplace",
        json={
            "item_type": "package_preset",
            "code": "out-to-site",
            "name": "Out to site",
            "version_label": "1.0.0",
            "category": "packages",
            "preview_json": {
                "package_preset": {
                    "code": "OUT_TO_SITE_COPY",
                    "name": "Выход на объект",
                    "description": "Preset",
                    "steps_json": {"steps": [{"code": "collect_requirements"}]},
                    "required_inputs_json": [{"code": "fio"}],
                }
            },
            "compatibility_json": {"platform": "v2"},
            "dependency_json": {"required_dictionaries": ["positions"]},
        },
        headers={**headers, "X-Tenant": "test"},
    )
    assert created.status_code == 201, created.text

    installed = await async_client.post(
        f"/api/v1/marketplace/{created.json()['id']}/install",
        json={"mode": "copy", "target_code": "OUT_TO_SITE_TENANT"},
        headers={**headers, "X-Tenant": "test"},
    )
    assert installed.status_code == 200, installed.text
    assert installed.json()["installed_ref"]["entity_type"] == "package_preset"
