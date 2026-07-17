"""Model pins for safety budget core (§12.4 срез-1, bg01)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from tests.utils.factories import TestDataFactory


def test_domain_whitelist_constants() -> None:
    from app.models.budget import BUDGET_DOMAINS, EXPENSE_ENTITY_TYPES

    assert BUDGET_DOMAINS == ("training", "medical", "events")
    assert EXPENSE_ENTITY_TYPES == {
        "training": "training_session",
        "medical": "medical_exam",
        "events": "corrective_action",
    }


@pytest.mark.asyncio
async def test_budget_roundtrip(sessionmaker, data_factory: TestDataFactory) -> None:
    from app.models.budget import SafetyBudget

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        budget = SafetyBudget(
            tenant_id=tenant.id,
            name="Бюджет обучения 2026",
            domain="training",
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
            planned_amount=500000,
            notes=None,
        )
        session.add(budget)
        await session.flush()
        row = (await session.execute(select(SafetyBudget))).scalar_one()
        assert row.domain == "training"
        assert float(row.planned_amount) == 500000.0
        assert row.deleted_at is None


@pytest.mark.asyncio
async def test_article_unique_code_per_tenant(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    from app.models.budget import BudgetExpenseArticle

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tenant_id = str(tenant.id)

        session.add(BudgetExpenseArticle(tenant_id=tenant_id, code="other", name="Прочее"))
        await session.commit()

        session.add(BudgetExpenseArticle(tenant_id=tenant_id, code="other", name="Дубль"))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_expense_roundtrip_with_nullable_dims(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    from app.models.budget import BudgetExpense

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        exp = BudgetExpense(
            tenant_id=tenant.id,
            domain="events",
            title="Ремонт вентиляции",
            occurred_on=date(2026, 3, 10),
            amount=120000,
        )
        session.add(exp)
        await session.flush()
        row = (await session.execute(select(BudgetExpense))).scalar_one()
        assert row.article_id is None
        assert row.site_id is None
        assert row.entity_type is None
        assert float(row.amount) == 120000.0
