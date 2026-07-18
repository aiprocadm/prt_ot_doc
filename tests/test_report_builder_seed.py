"""Idempotent demo seed: report_builder flag + 4 system templates."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_seed_idempotent(sessionmaker, data_factory: TestDataFactory):
    from app.models.feature import Feature, FeatureEnablement
    from app.models.report_builder import ReportDefinition
    from app.services.demo_bootstrap import _seed_report_builder_demo

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        await _seed_report_builder_demo(session, tid)
        await session.commit()
        await _seed_report_builder_demo(session, tid)  # второй прогон — без дублей
        await session.commit()

        feature = (
            await session.execute(select(Feature).where(Feature.code == "report_builder"))
        ).scalar_one()
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

        definitions = (
            (
                await session.execute(
                    select(ReportDefinition).where(
                        ReportDefinition.tenant_id == tid,
                        ReportDefinition.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(definitions) == 4
        assert all(d.is_system for d in definitions)
        assert {d.dataset_code for d in definitions} == {
            "employees_training",
            "incidents",
            "risks",
            "ppe_warehouse",
        }
        # configs валидны для engine
        from app.modules.report_builder.engine import validate_config

        for d in definitions:
            validate_config(d.dataset_code, d.config_json)
