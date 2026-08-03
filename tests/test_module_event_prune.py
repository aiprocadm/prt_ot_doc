"""SEC-63 (разд. 63.3), риск «осиротевшие доступы»: вебхуки при отключении модуля.

ТЗ: «После отключения модуля остаются активные API-ключи/вебхуки/задачи этого
модуля → Отключение модуля деактивирует связанные интеграции». Порядок закрытия
из docs/security/MODULE_ENTITLEMENTS.md:

1. модуль в каталоге объявляет типы событий, которые он порождает
   (``MODULE_EVENT_TYPES`` — полное покрытие каталога, пустой набор допустим);
2. отключение модуля (``apply_plan`` с тарифом без него) убирает эти типы из
   ``subscribed_events`` эндпоинтов арендатора и гасит эндпоинты, у которых не
   осталось событий (пустой список у диспетчера значит «ВСЕ события», поэтому
   оставить опустевший эндпоинт включённым = расширить доставку, а не сузить);
   подписки ``WebhookSubscription`` на события модуля выключаются.

Обратного автоматического включения при апгрейде НЕТ: платформа не помнит, чьи
события убирала, и «вернуть» интеграции должен сам арендатор осознанно.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.models.approval_runtime import WebhookEndpoint
from app.models.models import RoleEnum, Tenant
from app.models.tenant_billing import WebhookSubscription
from app.modules.subscription.plans import (
    FEATURE_CATALOG,
    MODULE_EVENT_TYPES,
    PLANS,
    SubscriptionPlan,
)
from app.services.events import EventType
from app.services.tenants.subscription import apply_plan

BASE = "/api/v1/platform/tenants"


@pytest.fixture(autouse=True)
def _managing_tenant(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PLATFORM_TENANT_SLUG", "test")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


async def _provision(async_client: AsyncClient, headers, slug: str) -> str:
    response = await async_client.post(
        BASE,
        json={
            "slug": slug,
            "name": f"Компания {slug}",
            "owner_email": f"owner@{slug}.ru",
            "owner_password": "OwnerPass123",
            "kind": "customer",
            "demo_data": False,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["tenant"]["id"]


def test_module_event_registry_covers_the_whole_catalog() -> None:
    """Каждый модуль каталога обязан объявить свои события (хотя бы пустым набором).

    Иначе девятый модуль появится без записи, и «деактивация связанных
    интеграций» для него молча не сработает — ровно тот класс дыр, который
    ратчет-гарды SEC-63 существуют ловить.
    """

    assert set(MODULE_EVENT_TYPES) == set(FEATURE_CATALOG)


def test_module_event_registry_uses_only_real_event_types() -> None:
    known = {event.value for event in EventType}
    for code, events in MODULE_EVENT_TYPES.items():
        unknown = set(events) - known
        assert not unknown, f"модуль {code} объявляет несуществующие события: {unknown}"


def test_cross_cutting_events_are_not_claimed_by_any_module() -> None:
    """Сквозные события (DocumentGenerated, PPEIssued, …) не принадлежат модулям.

    Если два модуля или модуль+ядро начнут «владеть» одним типом, отключение
    одного модуля оборвёт доставку событий, которые продолжают происходить.
    Событие может числиться максимум за одним модулем.
    """

    seen: dict[str, str] = {}
    for code, events in MODULE_EVENT_TYPES.items():
        for event in events:
            assert event not in seen, f"{event} объявлен и у {seen[event]}, и у {code}"
            seen[event] = code
    for cross_cutting in ("DocumentGenerated", "PPEIssued", "TrainingCompleted"):
        assert cross_cutting not in seen


@pytest.mark.anyio
async def test_downgrade_prunes_module_events_and_darkens_empty_endpoints(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    tenant_id = await _provision(async_client, headers, "prunerules")

    response = await async_client.patch(
        f"{BASE}/{tenant_id}/plan", json={"plan": "enterprise"}, headers=headers
    )
    assert response.status_code == 200, response.text

    async with sessionmaker() as session:
        mixed = WebhookEndpoint(
            tenant_id=tenant_id,
            name="mixed",
            url="https://client.example/hooks/mixed",
            is_enabled=True,
            subscribed_events=["rule.triggered", "DocumentGenerated"],
        )
        rules_only = WebhookEndpoint(
            tenant_id=tenant_id,
            name="rules-only",
            url="https://client.example/hooks/rules",
            is_enabled=True,
            subscribed_events=["rule.triggered"],
        )
        session.add_all([mixed, rules_only])
        session.add(
            WebhookSubscription(
                tenant_id=tenant_id,
                event_type="rule.triggered",
                url="https://client.example/subs/rules",
                enabled=True,
            )
        )
        session.add(
            WebhookSubscription(
                tenant_id=tenant_id,
                event_type="DocumentGenerated",
                url="https://client.example/subs/docs",
                enabled=True,
            )
        )
        await session.commit()
        mixed_id, rules_only_id = mixed.id, rules_only.id

    # Даунгрейд: тариф pro не содержит rules_engine.
    response = await async_client.patch(
        f"{BASE}/{tenant_id}/plan", json={"plan": "pro"}, headers=headers
    )
    assert response.status_code == 200, response.text

    async with sessionmaker() as session:
        mixed = (
            await session.execute(select(WebhookEndpoint).where(WebhookEndpoint.id == mixed_id))
        ).scalar_one()
        rules_only = (
            await session.execute(
                select(WebhookEndpoint).where(WebhookEndpoint.id == rules_only_id)
            )
        ).scalar_one()
        # Смешанный эндпоинт: событие модуля убрано, сквозное осталось, он жив.
        assert mixed.subscribed_events == ["DocumentGenerated"]
        assert mixed.is_enabled is True
        # Эндпоинт только на события модуля: опустел и погашен (пустой список =
        # «все события», оставить его включённым значило бы расширить доставку).
        assert rules_only.subscribed_events == []
        assert rules_only.is_enabled is False

        subs = (
            (
                await session.execute(
                    select(WebhookSubscription).where(WebhookSubscription.tenant_id == tenant_id)
                )
            )
            .scalars()
            .all()
        )
        by_event = {sub.event_type: sub for sub in subs}
        assert by_event["rule.triggered"].enabled is False
        assert by_event["DocumentGenerated"].enabled is True

    # Апгрейд обратно НЕ воскрешает интеграции сам.
    response = await async_client.patch(
        f"{BASE}/{tenant_id}/plan", json={"plan": "enterprise"}, headers=headers
    )
    assert response.status_code == 200, response.text
    async with sessionmaker() as session:
        rules_only = (
            await session.execute(
                select(WebhookEndpoint).where(WebhookEndpoint.id == rules_only_id)
            )
        ).scalar_one()
        assert rules_only.is_enabled is False
        rules_sub = (
            await session.execute(
                select(WebhookSubscription).where(
                    WebhookSubscription.tenant_id == tenant_id,
                    WebhookSubscription.event_type == "rule.triggered",
                )
            )
        ).scalar_one()
        assert rules_sub.enabled is False


@pytest.mark.anyio
async def test_service_level_prune_covers_medical_module(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    """Medical есть во всех штатных тарифах, поэтому его отключение проверяется
    на уровне сервиса кастомным планом — механика та же, что и в API-тесте."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    tenant_id = await _provision(async_client, headers, "prunemed")

    async with sessionmaker() as session:
        session.add(
            WebhookEndpoint(
                tenant_id=tenant_id,
                name="medical",
                url="https://client.example/hooks/medical",
                is_enabled=True,
                subscribed_events=["MedicalExamRecorded", "PersonSuspended"],
            )
        )
        await session.commit()

    no_medical = SubscriptionPlan(
        code="custom",
        title="Без медосмотров",
        features=PLANS["enterprise"].features - {"medical"},
        quotas=dict(PLANS["enterprise"].quotas),
    )
    async with sessionmaker() as session:
        target = (await session.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()
        await apply_plan(session, target, no_medical)
        await session.commit()

    async with sessionmaker() as session:
        endpoint = (
            await session.execute(
                select(WebhookEndpoint).where(WebhookEndpoint.tenant_id == tenant_id)
            )
        ).scalar_one()
        assert endpoint.subscribed_events == []
        assert endpoint.is_enabled is False
