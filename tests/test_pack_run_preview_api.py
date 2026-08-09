"""BIZ-50 срез-1 — предпросмотр комплекта до генерации (разд. 50.2, шаг 3).

До этого среза третьего шага мастера не было вовсе: специалист узнавал о
нехватке либо ответом 400 на ПЕРВОЙ же ненайденной колонке, либо получив
комплект с пустыми местами в документах и отдав его клиенту.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.models.models import PackagePresetConfig, PackagePresetItem, PackRun
from app.models.templates import Template, TemplateVersion


async def _add_document(sessionmaker, preset_id: str) -> None:
    """Положить в пресет один документ.

    Пресет без документов — законный блокер («генерировать нечего»), поэтому
    проверки предупреждений обязаны идти на пресете с содержимым, иначе они
    проверяли бы совсем другую причину.
    """

    async with sessionmaker() as session:
        preset = (
            await session.execute(
                select(PackagePresetConfig).where(PackagePresetConfig.id == preset_id)
            )
        ).scalar_one()
        template = Template(
            tenant_id=preset.tenant_id, name="Приказ", code=f"t-{uuid.uuid4().hex[:8]}"
        )
        session.add(template)
        await session.flush()
        version = TemplateVersion(
            tenant_id=preset.tenant_id,
            template_id=template.id,
            version=1,
            checksum=b"x",
            payload_key="tenants/test/templates/t.docx",
        )
        session.add(version)
        await session.flush()
        session.add(
            PackagePresetItem(
                tenant_id=preset.tenant_id,
                package_preset_id=preset.id,
                order_no=1,
                template_id=template.id,
                template_version_id=version.id,
            )
        )
        await session.commit()


async def _preset(async_client: AsyncClient, headers: dict, *, mapping: dict, status="active"):
    profile = await async_client.post(
        "/api/v1/package-profiles",
        json={
            "code": f"pp-{uuid.uuid4().hex[:8]}",
            "name": "Profile",
            "pipeline_steps_json": [{"step": "render_docx", "enabled": True}],
            "status": "active",
        },
        headers=headers,
    )
    assert profile.status_code == 201, profile.text
    preset = await async_client.post(
        "/api/v1/package-presets",
        json={
            "code": f"preset-{uuid.uuid4().hex[:8]}",
            "name": "Preset",
            "package_profile_id": profile.json()["id"],
            "naming_rule": "<fio>",
            "source_type": "json",
            "mapping_json": mapping,
            "status": status,
        },
        headers=headers,
    )
    assert preset.status_code == 201, preset.text
    return preset.json()["id"]


@pytest.mark.anyio
async def test_preview_lists_every_missing_column_at_once(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = {**await make_auth_headers(), **dict(async_client.headers)}
    preset_id = await _preset(
        async_client,
        headers,
        mapping={"fio": "фио", "position": "должность", "site": "объект"},
    )

    response = await async_client.post(
        "/api/v1/pack-runs:preview",
        json={"package_preset_id": preset_id, "rows": [{"фио": "Иванов"}]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["ready"] is False
    problem = next(p for p in body["problems"] if p["code"] == "SOURCE_COLUMN_MISSING")
    assert problem["blocking"] is True
    # Обе нехватки названы сразу: чинить по одной за прогон больше не нужно.
    assert "должность" in problem["message"]
    assert "объект" in problem["message"]
    # Пока генерация невозможна, обещать документы нельзя.
    assert body["documents_total"] == 0


@pytest.mark.anyio
async def test_preview_separates_warning_from_blocker(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    """Пустое значение — не запрет, а предупреждение о пробеле в документе."""

    headers = {**await make_auth_headers(), **dict(async_client.headers)}
    preset_id = await _preset(async_client, headers, mapping={"fio": "фио"})
    await _add_document(sessionmaker, preset_id)

    response = await async_client.post(
        "/api/v1/pack-runs:preview",
        json={
            "package_preset_id": preset_id,
            "rows": [{"фио": "Иванов"}, {"фио": ""}],
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["ready"] is True
    assert body["rows_selected"] == 2
    assert body["rows_ready"] == 1
    assert body["score"] == 50
    problem = next(p for p in body["problems"] if p["code"] == "VALUE_EMPTY")
    assert problem["blocking"] is False
    assert problem["rows"] == [2]


@pytest.mark.anyio
async def test_preview_creates_nothing(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    """«Посмотреть, что получится» не должно тратить прогон.

    Иначе предпросмотром перестанут пользоваться ровно тогда, когда он нужнее
    всего — на черновом файле.
    """

    headers = {**await make_auth_headers(), **dict(async_client.headers)}
    preset_id = await _preset(
        async_client, headers, mapping={"fio": {"type": "literal", "value": "Иванов"}}
    )

    async with sessionmaker() as session:
        before = (await session.execute(select(func.count()).select_from(PackRun))).scalar_one()

    # Ключ идемпотентности намеренно НЕ передаём: запуску он обязателен,
    # предпросмотру — нет.
    response = await async_client.post(
        "/api/v1/pack-runs:preview",
        json={"package_preset_id": preset_id, "rows": [{"фио": "Иванов"}]},
        headers=headers,
    )
    assert response.status_code == 200, response.text

    async with sessionmaker() as session:
        after = (await session.execute(select(func.count()).select_from(PackRun))).scalar_one()
    assert after == before


@pytest.mark.anyio
async def test_preview_of_unknown_preset_is_404(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = {**await make_auth_headers(), **dict(async_client.headers)}
    response = await async_client.post(
        "/api/v1/pack-runs:preview",
        json={"package_preset_id": "нет-такого", "rows": []},
        headers=headers,
    )
    assert response.status_code == 404
