from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.models import DocumentPack
from tests.test_packs_run import _prepare_pack_environment


@pytest.mark.anyio
async def test_list_packs_pagination(async_client: AsyncClient, sessionmaker, make_auth_headers) -> None:
    async with sessionmaker() as session:
        data = await _prepare_pack_environment(session, persons_count=1, items_count=1)
        tenant = data.tenant
        session.info["tenant"] = tenant.slug
        for index in range(3):
            session.add(
                DocumentPack(
                    tenant_id=tenant.id,
                    code=f"EXTRA_{index}",
                    name=f"Extra Pack {index}",
                    description=f"Generated {index}",
                    is_active=index % 2 == 0,
                )
            )
        await session.commit()

    headers = {**await make_auth_headers(), **dict(async_client.headers)}
    response = await async_client.get(
        "/api/v1/packs",
        params={"per_page": 2, "sort": "name:-1", "filter": "is_active:true,eq"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["meta"]["per_page"] == 2
    assert body["meta"]["total"] >= 2
    names = [item["name"] for item in body["data"]]
    assert names == sorted(names, reverse=True)


@pytest.mark.anyio
async def test_pack_run_idempotency_conflict(async_client: AsyncClient, sessionmaker, make_auth_headers, monkeypatch: pytest.MonkeyPatch) -> None:
    async with sessionmaker() as session:
        data = await _prepare_pack_environment(session, persons_count=1, items_count=1)
    tenant = data.tenant
    _ = tenant
    person = data.persons[0]
    pack = data.pack
    company = data.company
    headers = {**await make_auth_headers(), **dict(async_client.headers)}
    class StubResult:
        def __init__(self, task_id: str) -> None:
            self.id = task_id

    def fake_apply_async(*, args: list[str], kwargs: dict[str, str], task_id: str, headers: dict[str, str]):
        return StubResult(task_id)

    monkeypatch.setattr(
        "app.api.routes.packs.generate_document_task.apply_async", fake_apply_async
    )

    idem_key = f"pack-{uuid.uuid4()}"
    payload = {
        "pack_code": pack.code,
        "company_id": company.id,
        "site_id": data.site.id,
        "person_ids": [person.id],
        "data": {"shift": "day"},
    }

    first = await async_client.post(
        "/api/v1/packs/run",
        json=payload,
        headers={**headers, "Idempotency-Key": idem_key},
    )
    assert first.status_code == 202, first.text

    second_payload = dict(payload)
    second_payload["data"] = {"shift": "night"}
    second = await async_client.post(
        "/api/v1/packs/run",
        json=second_payload,
        headers={**headers, "Idempotency-Key": idem_key},
    )
    assert second.status_code == 409, second.text

    async with sessionmaker() as session:
        stmt = select(DocumentPack).where(DocumentPack.id == pack.id)
        stored_pack = (await session.execute(stmt)).scalar_one()
        assert stored_pack is not None
