"""Idempotent demo seed: rules_engine flag + 2 sample automation rules."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_seed_idempotent(sessionmaker, data_factory: TestDataFactory):
    from app.models.feature import Feature, FeatureEnablement
    from app.models.rules_engine import AutomationRule
    from app.services.demo_bootstrap import _seed_rules_engine_demo

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        await _seed_rules_engine_demo(session, tid)
        await session.commit()
        await _seed_rules_engine_demo(session, tid)  # второй прогон — без дублей
        await session.commit()

        features = (
            (await session.execute(select(Feature).where(Feature.code == "rules_engine")))
            .scalars()
            .all()
        )
        assert len(features) == 1
        feature = features[0]
        assert feature.title == "Правила автоматизации"

        enablements = (
            await session.execute(
                select(func.count())
                .select_from(FeatureEnablement)
                .where(
                    FeatureEnablement.tenant_id == tid,
                    FeatureEnablement.feature_id == feature.id,
                )
            )
        ).scalar_one()
        assert enablements == 1
        enablement = (
            await session.execute(
                select(FeatureEnablement).where(
                    FeatureEnablement.tenant_id == tid,
                    FeatureEnablement.feature_id == feature.id,
                )
            )
        ).scalar_one()
        assert enablement.on is True

        rules = (
            (await session.execute(select(AutomationRule).where(AutomationRule.tenant_id == tid)))
            .scalars()
            .all()
        )
        assert len(rules) == 2
        assert {r.name for r in rules} == {
            "Критичный инцидент — задача и уведомление",
            "Истекающий документ подрядчика — уведомление",
        }

        # configs валидны для API (rules_engine validators)
        from app.modules.rules_engine.actions import validate_actions
        from app.modules.rules_engine.conditions import validate_conditions

        for rule in rules:
            validate_conditions(rule.conditions_json)
            validate_actions(rule.actions_json)
