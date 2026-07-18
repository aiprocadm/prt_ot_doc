"""Service pins for safety budget CRUD (§12.4 срез-1): budgets + articles + seed-defaults.

Факт/агрегация здесь не тестируются (см. Task 5, aggregation.py); expense CRUD — Task 4.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.models.budget import SafetyBudget
from app.modules.budget.service import (
    DEFAULT_ARTICLES,
    ArticleCodeConflict,
    BudgetNotFound,
    BudgetService,
    BudgetValidationError,
)
from app.schemas.budget import (
    BudgetArticleCreate,
    BudgetArticleUpdate,
    SafetyBudgetCreate,
    SafetyBudgetUpdate,
)
from tests.utils.factories import TestDataFactory

# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_budget_create_get_list(sessionmaker, data_factory: TestDataFactory) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = BudgetService(session, tenant.id)

        b1 = await svc.create_budget(
            SafetyBudgetCreate(
                name="Обучение Q1",
                domain="training",
                period_start=date(2026, 1, 1),
                period_end=date(2026, 3, 31),
                planned_amount=100000,
                notes="заметка",
            )
        )
        b2 = await svc.create_budget(
            SafetyBudgetCreate(
                name="Обучение Q2",
                domain="training",
                period_start=date(2026, 4, 1),
                period_end=date(2026, 6, 30),
                planned_amount=50000,
            )
        )
        await svc.create_budget(
            SafetyBudgetCreate(
                name="Медосмотры",
                domain="medical",
                period_start=date(2026, 1, 1),
                period_end=date(2026, 12, 31),
                planned_amount=200000,
            )
        )

        got = await svc.get_budget(b1.id)
        assert got.name == "Обучение Q1"
        assert got.domain == "training"
        assert got.period_start == date(2026, 1, 1)
        assert got.period_end == date(2026, 3, 31)
        assert float(got.planned_amount) == 100000.0
        assert got.notes == "заметка"

        # domain filter + order_by period_start desc
        items, total = await svc.list_budgets(domain="training")
        assert total == 2
        assert [i.id for i in items] == [b2.id, b1.id]

        # pagination: exact total regardless of the page window
        page, page_total = await svc.list_budgets(domain="training", limit=1, offset=1)
        assert page_total == 2
        assert [i.id for i in page] == [b1.id]

        all_items, all_total = await svc.list_budgets()
        assert all_total == 3


@pytest.mark.asyncio
async def test_budget_tenant_isolation(sessionmaker, data_factory: TestDataFactory) -> None:
    async with sessionmaker() as session:
        t1 = await data_factory.ensure_tenant(session=session)
        t2 = await data_factory.ensure_tenant(session=session, slug="other")
        svc1 = BudgetService(session, t1.id)
        svc2 = BudgetService(session, t2.id)

        b = await svc1.create_budget(
            SafetyBudgetCreate(
                name="T1 budget",
                domain="training",
                period_start=date(2026, 1, 1),
                period_end=date(2026, 12, 31),
                planned_amount=1,
            )
        )

        with pytest.raises(BudgetNotFound):
            await svc2.get_budget(b.id)


@pytest.mark.asyncio
async def test_budget_update_partial_and_period_validation(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = BudgetService(session, tenant.id)
        b = await svc.create_budget(
            SafetyBudgetCreate(
                name="Бюджет",
                domain="training",
                period_start=date(2026, 1, 1),
                period_end=date(2026, 3, 31),
                planned_amount=100000,
                notes="n",
            )
        )

        # partial patch touches only planned_amount
        updated = await svc.update_budget(b.id, SafetyBudgetUpdate(planned_amount=150000))
        assert float(updated.planned_amount) == 150000.0
        assert updated.name == "Бюджет"
        assert updated.period_start == date(2026, 1, 1)
        assert updated.period_end == date(2026, 3, 31)
        assert updated.notes == "n"

        # merged period validation: only period_end supplied, checked against stored period_start
        with pytest.raises(BudgetValidationError) as exc_info:
            await svc.update_budget(b.id, SafetyBudgetUpdate(period_end=date(2025, 12, 1)))
        assert exc_info.value.code == "period_invalid"


@pytest.mark.asyncio
async def test_budget_update_explicit_null_rejected(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = BudgetService(session, tenant.id)
        b = await svc.create_budget(
            SafetyBudgetCreate(
                name="Бюджет",
                domain="training",
                period_start=date(2026, 1, 1),
                period_end=date(2026, 3, 31),
                planned_amount=100000,
            )
        )

        # explicit null on a non-nullable field is a validation error, NOT a
        # TypeError/500 from comparing None with a date at the period-merge check
        upd = SafetyBudgetUpdate(period_end=None)
        assert "period_end" in upd.model_dump(exclude_unset=True)
        with pytest.raises(BudgetValidationError) as exc_info:
            await svc.update_budget(b.id, upd)
        assert exc_info.value.code == "invalid_field_null"


@pytest.mark.asyncio
async def test_budget_soft_delete(sessionmaker, data_factory: TestDataFactory) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = BudgetService(session, tenant.id)
        b = await svc.create_budget(
            SafetyBudgetCreate(
                name="Удаляемый",
                domain="events",
                period_start=date(2026, 1, 1),
                period_end=date(2026, 12, 31),
                planned_amount=1,
            )
        )

        await svc.delete_budget(b.id)

        row = await session.get(SafetyBudget, b.id)
        assert row is not None
        assert row.deleted_at is not None

        items, total = await svc.list_budgets()
        assert total == 0
        assert items == []

        with pytest.raises(BudgetNotFound):
            await svc.get_budget(b.id)


# ---------------------------------------------------------------------------
# Articles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_article_create_list_and_code_conflict(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        t1 = await data_factory.ensure_tenant(session=session)
        t2 = await data_factory.ensure_tenant(session=session, slug="other")
        svc1 = BudgetService(session, t1.id)

        await svc1.create_article(BudgetArticleCreate(code="training_external", name="Обучение"))
        await svc1.create_article(BudgetArticleCreate(code="sout", name="СОУТ"))

        items, total = await svc1.list_articles()
        assert total == 2
        assert [i.code for i in items] == ["sout", "training_external"]

        with pytest.raises(ArticleCodeConflict):
            await svc1.create_article(BudgetArticleCreate(code="sout", name="Дубль"))

        # cross-tenant reuse of the same code is allowed
        svc2 = BudgetService(session, t2.id)
        reused = await svc2.create_article(BudgetArticleCreate(code="sout", name="СОУТ (T2)"))
        assert reused.code == "sout"
        assert reused.tenant_id == t2.id


@pytest.mark.asyncio
async def test_article_code_conflict_includes_soft_deleted(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = BudgetService(session, tenant.id)
        art = await svc.create_article(BudgetArticleCreate(code="x1", name="Статья"))
        await svc.delete_article(art.id)

        with pytest.raises(ArticleCodeConflict):
            await svc.create_article(BudgetArticleCreate(code="x1", name="Тёзка"))


@pytest.mark.asyncio
async def test_article_update(sessionmaker, data_factory: TestDataFactory) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = BudgetService(session, tenant.id)
        art = await svc.create_article(BudgetArticleCreate(code="ppe_purchase", name="Закупка СИЗ"))

        updated = await svc.update_article(
            art.id, BudgetArticleUpdate(name="Закупка СИЗ (обновлено)", is_active=False)
        )
        assert updated.name == "Закупка СИЗ (обновлено)"
        assert updated.is_active is False
        assert updated.code == "ppe_purchase"


@pytest.mark.asyncio
async def test_article_update_explicit_null_rejected(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = BudgetService(session, tenant.id)
        art = await svc.create_article(
            BudgetArticleCreate(code="training_external", name="Обучение", domain="training")
        )

        with pytest.raises(BudgetValidationError) as exc_info:
            await svc.update_article(art.id, BudgetArticleUpdate(name=None))
        assert exc_info.value.code == "invalid_field_null"

        # domain: null stays ALLOWED — legitimate "сделать универсальной"
        updated = await svc.update_article(art.id, BudgetArticleUpdate(domain=None))
        assert updated.domain is None
        assert updated.name == "Обучение"


@pytest.mark.asyncio
async def test_list_articles_includes_inactive(sessionmaker, data_factory: TestDataFactory) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = BudgetService(session, tenant.id)
        art = await svc.create_article(BudgetArticleCreate(code="other", name="Прочее"))

        await svc.update_article(art.id, BudgetArticleUpdate(is_active=False))

        items, total = await svc.list_articles()
        assert total == 1
        assert items[0].id == art.id
        assert items[0].is_active is False


@pytest.mark.asyncio
async def test_seed_treats_soft_deleted_default_as_seeded(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = BudgetService(session, tenant.id)

        created, skipped = await svc.seed_default_articles()
        assert (created, skipped) == (len(DEFAULT_ARTICLES), 0)

        items, _ = await svc.list_articles()
        one_default = next(i for i in items if i.code == DEFAULT_ARTICLES[0][0])
        await svc.delete_article(one_default.id)

        created2, skipped2 = await svc.seed_default_articles()
        assert (created2, skipped2) == (0, len(DEFAULT_ARTICLES))

        remaining, remaining_total = await svc.list_articles()
        assert remaining_total == len(DEFAULT_ARTICLES) - 1
        assert one_default.code not in {i.code for i in remaining}


@pytest.mark.asyncio
async def test_seed_default_articles_idempotent(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = BudgetService(session, tenant.id)

        created, skipped = await svc.seed_default_articles()
        assert (created, skipped) == (len(DEFAULT_ARTICLES), 0)

        items, total = await svc.list_articles()
        assert total == len(DEFAULT_ARTICLES)

        created2, skipped2 = await svc.seed_default_articles()
        assert (created2, skipped2) == (0, len(DEFAULT_ARTICLES))


@pytest.mark.asyncio
async def test_seed_default_articles_skips_existing_custom_code(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = BudgetService(session, tenant.id)

        await svc.create_article(BudgetArticleCreate(code="other", name="Своя"))

        created, skipped = await svc.seed_default_articles()
        assert (created, skipped) == (len(DEFAULT_ARTICLES) - 1, 1)

        items, _ = await svc.list_articles()
        other = next(i for i in items if i.code == "other")
        assert other.name == "Своя"
