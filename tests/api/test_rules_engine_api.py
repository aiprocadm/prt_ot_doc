"""API contract: flag gate, RBAC, CRUD, dry-run, test, triggers (P10-10 rules engine)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.models.models import RoleEnum
from app.services.outbox import OutboxService
from tests.utils.factories import TestDataFactory

BASE = "/api/v1/rules"


async def _enable_flag(sessionmaker, data_factory: TestDataFactory, *, on: bool = True) -> str:
    from app.models.feature import Feature, FeatureEnablement

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        feature = (
            await session.execute(select(Feature).where(Feature.code == "rules_engine"))
        ).scalar_one_or_none()
        if feature is None:
            feature = Feature(code="rules_engine", title="Движок правил")
            session.add(feature)
            await session.flush()
        session.add(FeatureEnablement(tenant_id=str(tenant.id), feature_id=feature.id, on=on))
        await session.commit()
        return str(tenant.id)


RULE = {
    "name": "Критичные инциденты",
    "event_type": "IncidentCreated",
    "conditions_json": {
        "match": "all",
        "conditions": [{"field": "severity", "op": "in", "value": ["high", "critical"]}],
    },
    "actions_json": [
        {
            "type": "notify",
            "recipient_mode": "role",
            "roles": ["admin"],
            "title_template": "Инцидент {severity}",
            "body_template": "Тип: {incident_type}",
        }
    ],
    "priority": 10,
}


def _incident_payload(tenant_id: str, *, severity: str = "critical") -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "incident_id": str(uuid4()),
        "company_id": "comp-1",
        "site_id": "site-1",
        "status": "reported",
        "severity": severity,
        "incident_type": "injury",
    }


async def _enqueue_incidents(sessionmaker, tenant_id: str, severities: list[str]) -> None:
    async with sessionmaker() as session:
        for severity in severities:
            await OutboxService(session).enqueue(
                tenant_id=tenant_id,
                event_type="IncidentCreated",
                payload=_incident_payload(tenant_id, severity=severity),
            )
        await session.commit()


@pytest.mark.asyncio
async def test_flag_off_404(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.get(BASE, headers=headers)
    assert resp.status_code == status.HTTP_404_NOT_FOUND  # default-off, без FeatureEnablement
    assert "feature is not enabled" in resp.text


@pytest.mark.asyncio
async def test_rbac(async_client, make_auth_headers, sessionmaker, data_factory):
    await _enable_flag(sessionmaker, data_factory)
    worker = await make_auth_headers(RoleEnum.WORKER)
    assert (await async_client.get(BASE, headers=worker)).status_code == status.HTTP_403_FORBIDDEN
    denied_post = await async_client.post(BASE, json=RULE, headers=worker)
    assert denied_post.status_code == status.HTTP_403_FORBIDDEN
    # ot_specialist — офисная роль, но правила admin/owner-only.
    ot = await make_auth_headers(RoleEnum.OT_SPECIALIST)
    assert (await async_client.get(BASE, headers=ot)).status_code == status.HTTP_403_FORBIDDEN
    admin = await make_auth_headers(RoleEnum.ADMIN)
    assert (await async_client.get(BASE, headers=admin)).status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_rule_rejects_cross_tenant_user_id(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    await _enable_flag(sessionmaker, data_factory)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        own_user = await data_factory.create_user(
            tenant=tenant, email="own-rule-user@example.com", session=session
        )
        foreign_tenant = await data_factory.ensure_tenant(slug="foreign-rules", session=session)
        foreign_user = await data_factory.create_user(
            tenant=foreign_tenant, email="foreign-rule-user@example.com", session=session
        )
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)

    task_action = {
        "type": "create_task",
        "title_template": "Задача",
        "assignee_mode": "user_id",
        "user_id": str(foreign_user.id),
    }
    denied_task = await async_client.post(
        BASE,
        json={**RULE, "name": "Чужой assignee", "actions_json": [task_action]},
        headers=headers,
    )
    assert denied_task.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, denied_task.text
    assert "unknown_user_id" in denied_task.text

    notify_action = {
        "type": "notify",
        "recipient_mode": "user_id",
        "user_id": str(foreign_user.id),
        "title_template": "Т",
        "body_template": "Б",
    }
    denied_notify = await async_client.post(
        BASE,
        json={**RULE, "name": "Чужой получатель", "actions_json": [notify_action]},
        headers=headers,
    )
    assert denied_notify.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, denied_notify.text
    assert "unknown_user_id" in denied_notify.text

    allowed = await async_client.post(
        BASE,
        json={
            **RULE,
            "name": "Свой assignee",
            "actions_json": [{**task_action, "user_id": str(own_user.id)}],
        },
        headers=headers,
    )
    assert allowed.status_code == status.HTTP_201_CREATED, allowed.text


@pytest.mark.asyncio
async def test_crud_flow(async_client, make_auth_headers, sessionmaker, data_factory):
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    created = await async_client.post(BASE, json=RULE, headers=headers)
    assert created.status_code == status.HTTP_201_CREATED, created.text
    rule_id = created.json()["id"]
    assert created.json()["is_enabled"] is True

    dup = await async_client.post(BASE, json=RULE, headers=headers)
    assert dup.status_code == status.HTTP_409_CONFLICT
    assert "RULE_NAME_EXISTS" in dup.text

    bad_event = await async_client.post(
        BASE, json={**RULE, "name": "Неизвестное событие", "event_type": "Bogus"}, headers=headers
    )
    assert bad_event.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "unknown_event_type" in bad_event.text

    bad_op = await async_client.post(
        BASE,
        json={
            **RULE,
            "name": "Битый op",
            "conditions_json": {
                "match": "all",
                "conditions": [{"field": "severity", "op": "bogus", "value": "x"}],
            },
        },
        headers=headers,
    )
    assert bad_op.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "invalid_condition_op" in bad_op.text

    lst = await async_client.get(BASE, headers=headers)
    assert lst.status_code == status.HTTP_200_OK
    assert lst.json()["total"] == 1
    etag = lst.headers.get("etag")
    assert etag
    not_modified = await async_client.get(BASE, headers={**headers, "If-None-Match": etag})
    assert not_modified.status_code == status.HTTP_304_NOT_MODIFIED

    patched = await async_client.patch(
        f"{BASE}/{rule_id}",
        json={"description": "обновлено", "priority": 5},
        headers=headers,
    )
    assert patched.status_code == status.HTTP_200_OK
    assert patched.json()["description"] == "обновлено"
    assert patched.json()["priority"] == 5

    disabled = await async_client.patch(
        f"{BASE}/{rule_id}", json={"is_enabled": False}, headers=headers
    )
    assert disabled.status_code == status.HTTP_200_OK
    assert disabled.json()["is_enabled"] is False

    # Explicit null на NOT NULL полях → 422 (не 409/500 от IntegrityError на flush).
    null_priority = await async_client.patch(
        f"{BASE}/{rule_id}", json={"priority": None}, headers=headers
    )
    assert null_priority.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "invalid_field_null" in null_priority.text
    null_enabled = await async_client.patch(
        f"{BASE}/{rule_id}", json={"is_enabled": None}, headers=headers
    )
    assert null_enabled.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "invalid_field_null" in null_enabled.text
    null_name = await async_client.patch(f"{BASE}/{rule_id}", json={"name": None}, headers=headers)
    assert null_name.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "invalid_field_null" in null_name.text
    # Nullable-поле по-прежнему очищается explicit null'ом.
    cleared = await async_client.patch(
        f"{BASE}/{rule_id}", json={"description": None}, headers=headers
    )
    assert cleared.status_code == status.HTTP_200_OK
    assert cleared.json()["description"] is None

    deleted = await async_client.delete(f"{BASE}/{rule_id}", headers=headers)
    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    gone = await async_client.get(f"{BASE}/{rule_id}", headers=headers)
    assert gone.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_event_types_catalog(async_client, make_auth_headers, sessionmaker, data_factory):
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.get(f"{BASE}/event-types", headers=headers)
    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert body["total"] == len(body["items"]) > 0
    incident = next(i for i in body["items"] if i["event_type"] == "IncidentCreated")
    assert any(f["name"] == "severity" for f in incident["fields"])
    assert all(i["event_type"] != "rule.triggered" for i in body["items"])


@pytest.mark.asyncio
async def test_роли_получателей_словами_из_единого_словаря(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    """Срез-148: форма берёт роли-получатели с сервера — все роли RoleEnum без
    псевдонимов, словами; те, кому шлёт сама библиотека правил, в списке есть."""
    from app.core.role_labels import ROLE_ALIASES, ROLE_LABELS

    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.get(f"{BASE}/recipient-roles", headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    codes = [item["code"] for item in body["items"]]
    assert body["total"] == len(codes) == len(set(codes))
    # До среза форма знала пять ролей; библиотека шлёт экологу и инженеру ПБ.
    assert {"ecologist", "pb_engineer", "ot_specialist", "hr", "admin"} <= set(codes)
    assert set(codes) == {role.value for role in RoleEnum} - set(ROLE_ALIASES)
    assert all(item["label"] == ROLE_LABELS[item["code"]] for item in body["items"])

    # Правило с ролями из этого списка исполнитель принимает.
    created = await async_client.post(
        BASE,
        json={
            **RULE,
            "name": f"Экологу и инженеру ПБ {uuid4().hex[:6]}",
            "actions_json": [{**RULE["actions_json"][0], "roles": ["ecologist", "pb_engineer"]}],
        },
        headers=headers,
    )
    assert created.status_code == status.HTTP_201_CREATED, created.text
    assert created.json()["actions_json"][0]["roles"] == ["ecologist", "pb_engineer"]

    # Ручка — для тех, кто правит правила: остальным 403, как всему движку.
    specialist = await make_auth_headers(RoleEnum.OT_SPECIALIST)
    forbidden = await async_client.get(f"{BASE}/recipient-roles", headers=specialist)
    assert forbidden.status_code == status.HTTP_403_FORBIDDEN, forbidden.text


@pytest.mark.asyncio
async def test_dry_run(async_client, make_auth_headers, sessionmaker, data_factory):
    tenant_id = await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    matched = await async_client.post(
        f"{BASE}/dry-run",
        json={
            "rule": RULE,
            "event": {
                "event_type": "IncidentCreated",
                "payload": _incident_payload(tenant_id, severity="critical"),
            },
        },
        headers=headers,
    )
    assert matched.status_code == status.HTTP_200_OK, matched.text
    body = matched.json()
    assert body["matched"] is True
    assert body["condition_results"][0]["matched"] is True
    assert body["condition_results"][0]["field"] == "severity"
    assert body["condition_results"][0]["actual"] == "critical"
    assert body["would_actions"]

    no_match = await async_client.post(
        f"{BASE}/dry-run",
        json={
            "rule": RULE,
            "event": {
                "event_type": "IncidentCreated",
                "payload": _incident_payload(tenant_id, severity="low"),
            },
        },
        headers=headers,
    )
    assert no_match.status_code == status.HTTP_200_OK
    assert no_match.json()["matched"] is False
    assert no_match.json()["would_actions"] == []


@pytest.mark.asyncio
async def test_dry_run_invalid_config_422(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    tenant_id = await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.post(
        f"{BASE}/dry-run",
        json={
            "rule": {
                **RULE,
                "conditions_json": {
                    "match": "all",
                    "conditions": [{"field": "severity", "op": "bogus", "value": "x"}],
                },
            },
            "event": {
                "event_type": "IncidentCreated",
                "payload": _incident_payload(tenant_id),
            },
        },
        headers=headers,
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "invalid_condition_op" in resp.text


@pytest.mark.asyncio
async def test_rule_test_by_history(async_client, make_auth_headers, sessionmaker, data_factory):
    tenant_id = await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    created = await async_client.post(BASE, json=RULE, headers=headers)
    assert created.status_code == status.HTTP_201_CREATED, created.text
    rule_id = created.json()["id"]

    # Живой enqueue также запустит движок (флаг включён, правило существует) —
    # это ок: /test считает историю независимо от журнала срабатываний.
    await _enqueue_incidents(sessionmaker, tenant_id, ["critical", "critical", "low"])

    resp = await async_client.post(f"{BASE}/{rule_id}/test", json={}, headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    assert body["events_checked"] == 3
    assert body["matched_count"] == 2
    assert len(body["results"]) == 3
    assert all(r["event_key"] for r in body["results"])


@pytest.mark.asyncio
async def test_triggers_journal(async_client, make_auth_headers, sessionmaker, data_factory):
    tenant_id = await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    created = await async_client.post(BASE, json=RULE, headers=headers)
    assert created.status_code == status.HTTP_201_CREATED, created.text
    rule_id = created.json()["id"]

    await _enqueue_incidents(sessionmaker, tenant_id, ["critical"])

    resp = await async_client.get(f"{BASE}/triggers", headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    assert body["total"] >= 1
    assert all(t["rule_id"] == rule_id for t in body["items"])
    assert body["items"][0]["status"] == "success"

    filtered = await async_client.get(f"{BASE}/triggers?rule_id={rule_id}", headers=headers)
    assert filtered.status_code == status.HTTP_200_OK
    assert filtered.json()["total"] == body["total"]

    empty = await async_client.get(f"{BASE}/triggers?rule_id={uuid4()}", headers=headers)
    assert empty.status_code == status.HTTP_200_OK
    assert empty.json()["total"] == 0


@pytest.mark.asyncio
async def test_person_recipient_mode_gated_by_event(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    """Срез-118: получатель «работник из события» доступен только там, где работник есть."""
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    person_action = {
        "type": "notify",
        "recipient_mode": "person",
        "title_template": "Замена СИЗ",
        "body_template": "Срок по {item_name}",
    }

    denied = await async_client.post(
        BASE,
        json={**RULE, "name": "Работник из инцидента", "actions_json": [person_action]},
        headers=headers,
    )
    assert denied.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, denied.text
    assert "person_not_in_event" in denied.text

    allowed = await async_client.post(
        BASE,
        json={
            **RULE,
            "name": "Работник из события СИЗ",
            "event_type": "PPEReplacementDue",
            "conditions_json": {"match": "all", "conditions": []},
            "actions_json": [person_action],
        },
        headers=headers,
    )
    assert allowed.status_code == status.HTTP_201_CREATED, allowed.text
