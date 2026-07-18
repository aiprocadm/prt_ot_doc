"""Model pins for automation rules engine (P10-10 срез-1, vNext §25.2)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_name_unique_per_tenant(sessionmaker, data_factory: TestDataFactory) -> None:
    from app.models.models import AutomationRule

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tenant_id = str(tenant.id)

        first = AutomationRule(
            tenant_id=tenant_id,
            name="Правило Альфа",
            event_type="incident.created",
            conditions_json={},
            actions_json=[],
        )
        session.add(first)
        await session.commit()

        session.add(
            AutomationRule(
                tenant_id=tenant_id,
                name="Правило Альфа",
                event_type="incident.created",
                conditions_json={},
                actions_json=[],
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_name_unique_includes_soft_deleted(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    """uq_automation_rule_tenant_name действует БЕЗ фильтра deleted_at (паттерн
    ReportDefinition): soft-deleted тёзка не освобождает слот."""
    from app.models.models import AutomationRule

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tenant_id = str(tenant.id)

        first = AutomationRule(
            tenant_id=tenant_id,
            name="Правило Бета",
            event_type="incident.created",
            conditions_json={},
            actions_json=[],
        )
        session.add(first)
        await session.commit()

        first.deleted_at = datetime.now(tz=timezone.utc)
        session.add(first)
        await session.commit()

        session.add(
            AutomationRule(
                tenant_id=tenant_id,
                name="Правило Бета",
                event_type="incident.created",
                conditions_json={},
                actions_json=[],
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_trigger_row_roundtrip(sessionmaker, data_factory: TestDataFactory) -> None:
    from app.models.models import AutomationRule, AutomationRuleTrigger, RuleTriggerStatus

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tenant_id = str(tenant.id)

        rule = AutomationRule(
            tenant_id=tenant_id,
            name="Правило Гамма",
            event_type="incident.created",
            conditions_json={"field": "severity", "op": "eq", "value": "high"},
            actions_json=[{"type": "notify", "template": "incident_high"}],
        )
        session.add(rule)
        await session.commit()

        trigger = AutomationRuleTrigger(
            tenant_id=tenant_id,
            rule_id=rule.id,
            event_type="incident.created",
            event_key="incident:123",
            correlation_id="corr-1",
            event_payload={"incident_id": "123"},
            status=RuleTriggerStatus.SUCCESS,
            actions_result=[{"type": "notify", "ok": True}],
        )
        session.add(trigger)
        await session.commit()

        assert trigger.id is not None
        assert trigger.status == RuleTriggerStatus.SUCCESS
