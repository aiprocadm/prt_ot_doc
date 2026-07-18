"""Pins for computed budget actuals (§12.4 срез-1, Task 5).

Covers compute_domain_actual (window/domain/soft-delete filters, by-article
grouping incl. the «— без статьи» bucket), compute_overview (planned overlap
semantics, per-budget own-period actuals, PPE read-only domain fed by the stock
ledger, deterministic zero-domains) and compute_breakdown (article/domain/
company/branch/site dimensions, None-buckets, tenant isolation, validation
codes, row cap wiring). Journal CRUD is pinned in test_budget_expense_service.py.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.models.budget import BudgetExpense, BudgetExpenseArticle, SafetyBudget
from app.models.models import Branch, Company, PPEItem, PPEItemCategory, Site
from app.models.ppe_registry import PPESafetyBudget, PPEStockBatch, PPEStockMovement
from app.modules.budget import aggregation
from app.modules.budget.aggregation import (
    BREAKDOWN_DIMENSIONS,
    BREAKDOWN_ROW_CAP,
    NO_BUCKET_ID,
    compute_breakdown,
    compute_domain_actual,
    compute_overview,
)
from app.modules.budget.service import BudgetValidationError
from tests.utils.factories import TestDataFactory

WIN_FROM, WIN_TO = date(2026, 1, 1), date(2026, 1, 31)


async def _article(session, tenant_id, *, code, name, domain=None):
    article = BudgetExpenseArticle(tenant_id=tenant_id, code=code, name=name, domain=domain)
    session.add(article)
    await session.flush()
    return article


async def _budget(session, tenant_id, *, domain, start, end, planned, name="Бюджет"):
    budget = SafetyBudget(
        tenant_id=tenant_id,
        name=name,
        domain=domain,
        period_start=start,
        period_end=end,
        planned_amount=planned,
    )
    session.add(budget)
    await session.flush()
    return budget


async def _expense(
    session,
    tenant_id,
    *,
    domain,
    amount,
    occurred_on,
    article_id=None,
    company_id=None,
    branch_id=None,
    site_id=None,
    deleted_at=None,
    title="Расход",
):
    expense = BudgetExpense(
        tenant_id=tenant_id,
        domain=domain,
        title=title,
        occurred_on=occurred_on,
        amount=amount,
        article_id=article_id,
        company_id=company_id,
        branch_id=branch_id,
        site_id=site_id,
        deleted_at=deleted_at,
    )
    session.add(expense)
    await session.flush()
    return expense


# --- PPE warehouse setup (mirrors tests/api/test_ppe_budget_actual_service.py) ---


async def _ppe_item(session, tenant_id, *, name, category=PPEItemCategory.HEAD):
    item = PPEItem(tenant_id=tenant_id, name=name, category=category)
    session.add(item)
    await session.flush()
    return item


async def _ppe_batch(session, tenant_id, item_id, *, unit_cost, no="B"):
    batch = PPEStockBatch(
        tenant_id=tenant_id, item_id=item_id, batch_no=no, quantity=0, unit_cost=unit_cost
    )
    session.add(batch)
    await session.flush()
    return batch


async def _ppe_receipt(session, tenant_id, item_id, batch_id, *, delta, when):
    movement = PPEStockMovement(
        tenant_id=tenant_id,
        item_id=item_id,
        batch_id=batch_id,
        kind="receipt",
        quantity_delta=delta,
        occurred_at=when,
    )
    session.add(movement)
    await session.flush()
    return movement


# ---------------------------------------------------------------------------
# compute_domain_actual
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_domain_actual_window_grouping_and_filters(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        art_a = await _article(session, tenant.id, code="a", name="Статья А")
        art_b = await _article(session, tenant.id, code="b", name="Статья Б")

        # in window: boundary dates ON start and ON end are included
        await _expense(
            session,
            tenant.id,
            domain="training",
            amount=100.50,
            occurred_on=WIN_FROM,
            article_id=art_a.id,
        )
        await _expense(
            session,
            tenant.id,
            domain="training",
            amount=200.25,
            occurred_on=WIN_TO,
            article_id=art_a.id,
        )
        await _expense(
            session,
            tenant.id,
            domain="training",
            amount=50,
            occurred_on=date(2026, 1, 15),
            article_id=art_b.id,
        )
        await _expense(
            session, tenant.id, domain="training", amount=10, occurred_on=date(2026, 1, 10)
        )  # article-less -> «— без статьи»
        # out of window (both sides)
        await _expense(
            session,
            tenant.id,
            domain="training",
            amount=999,
            occurred_on=date(2025, 12, 31),
            article_id=art_a.id,
        )
        await _expense(
            session,
            tenant.id,
            domain="training",
            amount=999,
            occurred_on=date(2026, 2, 1),
            article_id=art_a.id,
        )
        # other domain
        await _expense(
            session, tenant.id, domain="medical", amount=777, occurred_on=date(2026, 1, 15)
        )
        # soft-deleted
        await _expense(
            session,
            tenant.id,
            domain="training",
            amount=555,
            occurred_on=date(2026, 1, 15),
            deleted_at=datetime.now(timezone.utc),
        )

        fact = await compute_domain_actual(session, tenant.id, "training", WIN_FROM, WIN_TO)

        assert fact.actual_total == 360.75  # 100.50 + 200.25 + 50 + 10
        assert fact.expense_count == 4
        assert [(a.article_id, a.article_name, a.amount) for a in fact.by_article] == [
            (art_a.id, "Статья А", 300.75),
            (art_b.id, "Статья Б", 50.0),
            (None, "— без статьи", 10.0),
        ]


# ---------------------------------------------------------------------------
# compute_overview
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overview_planned_overlap_and_own_period_actual(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        win_from, win_to = date(2026, 2, 1), date(2026, 2, 28)

        inside = await _budget(
            session,
            tenant.id,
            domain="training",
            start=date(2026, 2, 5),
            end=date(2026, 2, 20),
            planned=1000,
            name="Внутри окна",
        )
        straddle = await _budget(
            session,
            tenant.id,
            domain="training",
            start=date(2026, 1, 15),
            end=date(2026, 2, 10),
            planned=500,
            name="Через край",
        )
        await _budget(
            session,
            tenant.id,
            domain="training",
            start=date(2026, 3, 1),
            end=date(2026, 3, 31),
            planned=9999,
            name="Вне окна",
        )

        # inside straddle's own period but OUTSIDE the overview window
        await _expense(
            session, tenant.id, domain="training", amount=100, occurred_on=date(2026, 1, 20)
        )
        # inside the window and inside both overlapping budget periods
        await _expense(
            session, tenant.id, domain="training", amount=40, occurred_on=date(2026, 2, 7)
        )

        overview = await compute_overview(session, tenant.id, win_from, win_to)

        training = next(d for d in overview.domains if d.domain == "training")
        assert training.read_only is False
        assert training.warning_unpriced_receipts is None
        assert training.planned == 1500.0  # inside + straddle, FULL amounts (no proration)
        assert training.actual == 40.0  # window-scoped
        assert training.remaining == 1460.0

        # ordered period_start desc
        assert [r.id for r in training.budgets] == [inside.id, straddle.id]
        rows = {r.id: r for r in training.budgets}
        assert rows[inside.id].actual_own_period == 40.0
        assert rows[inside.id].remaining == 960.0
        # own-period actual counts the Jan expense the window actual does not
        assert rows[straddle.id].actual_own_period == 140.0
        assert rows[straddle.id].remaining == 360.0
        assert rows[straddle.id].actual_own_period != training.actual


@pytest.mark.asyncio
async def test_overview_ppe_read_only_from_stock_ledger(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        win_from, win_to = date(2026, 1, 1), date(2026, 12, 31)

        item = await _ppe_item(session, tenant.id, name="Каска")
        priced = await _ppe_batch(session, tenant.id, item.id, unit_cost=100, no="P")
        unpriced = await _ppe_batch(session, tenant.id, item.id, unit_cost=None, no="U")
        when = datetime(2026, 6, 1, tzinfo=timezone.utc)
        await _ppe_receipt(session, tenant.id, item.id, priced.id, delta=3, when=when)
        await _ppe_receipt(session, tenant.id, item.id, unpriced.id, delta=2, when=when)

        ppe_budget = PPESafetyBudget(
            tenant_id=tenant.id,
            name="СИЗ бюджет",
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
            planned_amount=5000,
        )
        session.add(ppe_budget)
        await session.flush()

        overview = await compute_overview(session, tenant.id, win_from, win_to)

        ppe = next(d for d in overview.domains if d.domain == "ppe")
        assert ppe.read_only is True
        assert ppe.planned == 5000.0
        assert ppe.actual == 300.0  # 3 x 100, unpriced receipt excluded
        assert ppe.remaining == 4700.0
        assert ppe.warning_unpriced_receipts == 1

        assert len(ppe.budgets) == 1
        row = ppe.budgets[0]
        assert row.id == ppe_budget.id
        assert row.planned_amount == 5000.0
        assert row.actual_own_period == 300.0
        assert row.remaining == 4700.0


@pytest.mark.asyncio
async def test_overview_empty_tenant_all_domains_zero(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)

        overview = await compute_overview(session, tenant.id, WIN_FROM, WIN_TO)

        assert [d.domain for d in overview.domains] == ["training", "medical", "events", "ppe"]
        assert [d.read_only for d in overview.domains] == [False, False, False, True]
        for domain in overview.domains:
            assert domain.planned == 0.0
            assert domain.actual == 0.0
            assert domain.remaining == 0.0
            assert domain.budgets == []
        assert overview.domains[3].warning_unpriced_receipts == 0
        assert overview.date_from == WIN_FROM
        assert overview.date_to == WIN_TO
        assert overview.generated_at.tzinfo is not None


@pytest.mark.asyncio
async def test_overview_window_inversion_rejected(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)

        with pytest.raises(BudgetValidationError) as exc_info:
            await compute_overview(session, tenant.id, date(2026, 2, 1), date(2026, 1, 1))
        assert exc_info.value.code == "window_invalid"


# ---------------------------------------------------------------------------
# compute_breakdown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_breakdown_by_article_with_none_bucket(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        art_a = await _article(session, tenant.id, code="a", name="А-статья")
        art_b = await _article(session, tenant.id, code="b", name="Б-статья")

        await _expense(
            session,
            tenant.id,
            domain="training",
            amount=300,
            occurred_on=date(2026, 1, 5),
            article_id=art_a.id,
        )
        await _expense(
            session,
            tenant.id,
            domain="medical",
            amount=200,
            occurred_on=date(2026, 1, 10),
            article_id=art_b.id,
        )
        await _expense(
            session, tenant.id, domain="events", amount=100, occurred_on=date(2026, 1, 15)
        )

        result = await compute_breakdown(session, tenant.id, "article", WIN_FROM, WIN_TO)

        assert result.dimension == "article"
        assert result.total == 3
        assert [(i.id, i.name, i.amount) for i in result.items] == [
            (art_a.id, "А-статья", 300.0),
            (art_b.id, "Б-статья", 200.0),
            (NO_BUCKET_ID, "— без статьи", 100.0),
        ]


@pytest.mark.asyncio
async def test_breakdown_by_domain_codes_and_name_tiebreak(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)

        # equal amounts -> sorted by name asc (domain code; RU labels are frontend vocab)
        await _expense(
            session, tenant.id, domain="training", amount=100, occurred_on=date(2026, 1, 5)
        )
        await _expense(
            session, tenant.id, domain="medical", amount=100, occurred_on=date(2026, 1, 10)
        )

        result = await compute_breakdown(session, tenant.id, "domain", WIN_FROM, WIN_TO)

        assert result.total == 2
        assert [(i.id, i.name, i.amount) for i in result.items] == [
            ("medical", "medical", 100.0),
            ("training", "training", 100.0),
        ]


@pytest.mark.asyncio
async def test_breakdown_company_branch_site_with_tenant_isolation(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        t1 = await data_factory.ensure_tenant(session=session)
        t2 = await data_factory.ensure_tenant(session=session, slug="other")

        company = Company(tenant_id=t1.id, name="ООО Ромашка")
        session.add(company)
        await session.flush()
        branch = Branch(tenant_id=t1.id, company_id=company.id, name="Филиал-1")
        site = Site(tenant_id=t1.id, company_id=company.id, name="Площадка-1")
        session.add_all([branch, site])
        await session.flush()

        # foreign tenant: same-named site + an expense referencing it
        company2 = Company(tenant_id=t2.id, name="ООО Чужая")
        session.add(company2)
        await session.flush()
        foreign_site = Site(tenant_id=t2.id, company_id=company2.id, name="Площадка-1")
        session.add(foreign_site)
        await session.flush()
        await _expense(
            session,
            t2.id,
            domain="training",
            amount=999,
            occurred_on=date(2026, 1, 10),
            site_id=foreign_site.id,
        )

        await _expense(
            session,
            t1.id,
            domain="training",
            amount=500,
            occurred_on=date(2026, 1, 10),
            company_id=company.id,
            branch_id=branch.id,
            site_id=site.id,
        )
        await _expense(
            session, t1.id, domain="training", amount=120, occurred_on=date(2026, 1, 12)
        )  # no bindings -> «— без привязки» in every dimension

        for dimension, dim_id, dim_name in (
            ("company", company.id, "ООО Ромашка"),
            ("branch", branch.id, "Филиал-1"),
            ("site", site.id, "Площадка-1"),
        ):
            result = await compute_breakdown(session, t1.id, dimension, WIN_FROM, WIN_TO)
            assert result.total == 2, dimension
            assert [(i.id, i.name, i.amount) for i in result.items] == [
                (dim_id, dim_name, 500.0),
                (NO_BUCKET_ID, "— без привязки", 120.0),
            ], dimension


@pytest.mark.asyncio
async def test_breakdown_validation_codes(sessionmaker, data_factory: TestDataFactory) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)

        with pytest.raises(BudgetValidationError) as exc_info:
            await compute_breakdown(session, tenant.id, "nope", WIN_FROM, WIN_TO)
        assert exc_info.value.code == "breakdown_dimension_unknown"

        with pytest.raises(BudgetValidationError) as exc_info:
            await compute_breakdown(
                session, tenant.id, "article", date(2026, 2, 1), date(2026, 1, 1)
            )
        assert exc_info.value.code == "window_invalid"


@pytest.mark.asyncio
async def test_breakdown_excludes_ppe_stock_ledger(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)

        item = await _ppe_item(session, tenant.id, name="Каска")
        batch = await _ppe_batch(session, tenant.id, item.id, unit_cost=100)
        await _ppe_receipt(
            session,
            tenant.id,
            item.id,
            batch.id,
            delta=3,
            when=datetime(2026, 1, 15, tzinfo=timezone.utc),
        )
        await _expense(
            session, tenant.id, domain="training", amount=100, occurred_on=date(2026, 1, 10)
        )

        result = await compute_breakdown(session, tenant.id, "domain", WIN_FROM, WIN_TO)

        assert [i.id for i in result.items] == ["training"]  # no "ppe" row


@pytest.mark.asyncio
async def test_breakdown_cap_wiring(sessionmaker, data_factory: TestDataFactory) -> None:
    assert BREAKDOWN_ROW_CAP == 200  # pin
    assert BREAKDOWN_DIMENSIONS == ("article", "domain", "company", "branch", "site")
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        for domain, amount in (("training", 30), ("medical", 20), ("events", 10)):
            await _expense(
                session, tenant.id, domain=domain, amount=amount, occurred_on=date(2026, 1, 5)
            )

        result = await compute_breakdown(session, tenant.id, "domain", WIN_FROM, WIN_TO)

        assert result.total == 3
        assert len(result.items) == 3  # under the cap nothing is truncated


@pytest.mark.asyncio
async def test_breakdown_cap_truncation(
    sessionmaker, data_factory: TestDataFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """total counts ALL groups; items are the top-N by amount after the cap."""
    monkeypatch.setattr(aggregation, "BREAKDOWN_ROW_CAP", 2)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        art_a = await _article(session, tenant.id, code="a", name="А-статья")
        art_b = await _article(session, tenant.id, code="b", name="Б-статья")
        art_c = await _article(session, tenant.id, code="c", name="В-статья")
        for article, amount in ((art_a, 300), (art_b, 200), (art_c, 100)):
            await _expense(
                session,
                tenant.id,
                domain="training",
                amount=amount,
                occurred_on=date(2026, 1, 5),
                article_id=article.id,
            )

        result = await compute_breakdown(session, tenant.id, "article", WIN_FROM, WIN_TO)

        assert result.total == 3
        assert len(result.items) == 2
        assert [(i.id, i.amount) for i in result.items] == [
            (art_a.id, 300.0),
            (art_b.id, 200.0),
        ]  # top-2 by amount; В-статья truncated
