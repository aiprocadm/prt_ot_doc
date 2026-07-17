"""Service pins for the budget expense journal (§12.4 срез-1, Task 4).

Covers CRUD + tenant-scoped reference validation (article/company/branch/site/
polymorphic entity) and the explicit-null PATCH guard. Budgets/articles CRUD is
pinned in tests/api/test_budget_service.py; aggregation (fact/overview/breakdown)
is out of scope here (Task 5).
"""

from __future__ import annotations

from datetime import date

import pytest

from app.models.models import Branch, Company, Site
from app.models.safety_ops import CorrectiveAction
from app.modules.budget.service import (
    BudgetService,
    BudgetValidationError,
    ExpenseNotFound,
)
from app.schemas.budget import (
    BudgetArticleCreate,
    BudgetArticleUpdate,
    BudgetExpenseCreate,
    BudgetExpenseUpdate,
)
from tests.utils.factories import TestDataFactory


async def _make_company(session, tenant_id: str, name: str = "ООО Ромашка") -> Company:
    company = Company(tenant_id=tenant_id, name=name)
    session.add(company)
    await session.flush()
    await session.refresh(company)
    return company


async def _make_branch(session, tenant_id: str, company_id: str, name: str = "Филиал") -> Branch:
    branch = Branch(tenant_id=tenant_id, company_id=company_id, name=name)
    session.add(branch)
    await session.flush()
    await session.refresh(branch)
    return branch


async def _make_site(session, tenant_id: str, company_id: str, name: str = "Площадка") -> Site:
    site = Site(tenant_id=tenant_id, company_id=company_id, name=name)
    session.add(site)
    await session.flush()
    await session.refresh(site)
    return site


async def _make_corrective_action(
    session, tenant_id: str, title: str = "Устранить"
) -> CorrectiveAction:
    action = CorrectiveAction(
        tenant_id=tenant_id,
        source_type="incident",
        source_id="s1",
        title=title,
        action_type="corrective",
    )
    session.add(action)
    await session.flush()
    await session.refresh(action)
    return action


# ---------------------------------------------------------------------------
# create / list happy-path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expense_create_list_filters_and_join(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = BudgetService(session, tenant.id)

        article = await svc.create_article(
            BudgetArticleCreate(code="training_external", name="Обучение", domain="training")
        )

        e1 = await svc.create_expense(
            BudgetExpenseCreate(
                domain="training",
                article_id=article.id,
                title="Курс А",
                occurred_on=date(2026, 1, 5),
                amount=1000,
            )
        )
        e2 = await svc.create_expense(
            BudgetExpenseCreate(
                domain="training",
                article_id=article.id,
                title="Курс Б",
                occurred_on=date(2026, 1, 10),
                amount=2000,
            )
        )
        e3 = await svc.create_expense(
            BudgetExpenseCreate(
                domain="medical",
                title="Медосмотр без статьи",
                occurred_on=date(2026, 1, 15),
                amount=3000,
            )
        )

        # domain filter
        items, total = await svc.list_expenses(domain="training")
        assert total == 2
        assert [row[0].id for row in items] == [e2.id, e1.id]  # order_by occurred_on desc

        # article filter
        items, total = await svc.list_expenses(article_id=article.id)
        assert total == 2
        assert {row[0].id for row in items} == {e1.id, e2.id}

        # date window inclusive on both bounds
        items, total = await svc.list_expenses(date_from=date(2026, 1, 5), date_to=date(2026, 1, 10))
        assert total == 2
        assert {row[0].id for row in items} == {e1.id, e2.id}

        items, total = await svc.list_expenses(date_from=date(2026, 1, 5), date_to=date(2026, 1, 5))
        assert total == 1
        assert items[0][0].id == e1.id

        # article_name via outerjoin: present for e1/e2, None for e3
        all_items, all_total = await svc.list_expenses()
        assert all_total == 3
        by_id = {row[0].id: row[1] for row in all_items}
        assert by_id[e1.id] == "Обучение"
        assert by_id[e2.id] == "Обучение"
        assert by_id[e3.id] is None


# ---------------------------------------------------------------------------
# update / delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expense_update_and_soft_delete(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = BudgetService(session, tenant.id)

        expense = await svc.create_expense(
            BudgetExpenseCreate(
                domain="events",
                title="Мероприятие",
                occurred_on=date(2026, 2, 1),
                amount=500,
            )
        )

        updated = await svc.update_expense(expense.id, BudgetExpenseUpdate(amount=750))
        assert float(updated.amount) == 750.0
        assert updated.title == "Мероприятие"

        await svc.delete_expense(expense.id)
        items, total = await svc.list_expenses()
        assert total == 0
        assert items == []

        with pytest.raises(ExpenseNotFound):
            await svc.update_expense(expense.id, BudgetExpenseUpdate(amount=1))


# ---------------------------------------------------------------------------
# reference validation: unknown_* / tenant isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expense_unknown_article(sessionmaker, data_factory: TestDataFactory) -> None:
    async with sessionmaker() as session:
        t1 = await data_factory.ensure_tenant(session=session)
        t2 = await data_factory.ensure_tenant(session=session, slug="other")
        svc1 = BudgetService(session, t1.id)
        svc2 = BudgetService(session, t2.id)

        foreign_article = await svc2.create_article(
            BudgetArticleCreate(code="foreign", name="Чужая статья")
        )

        with pytest.raises(BudgetValidationError) as exc_info:
            await svc1.create_expense(
                BudgetExpenseCreate(
                    domain="training",
                    article_id="does-not-exist",
                    title="X",
                    occurred_on=date(2026, 1, 1),
                    amount=1,
                )
            )
        assert exc_info.value.code == "unknown_article"

        with pytest.raises(BudgetValidationError) as exc_info:
            await svc1.create_expense(
                BudgetExpenseCreate(
                    domain="training",
                    article_id=foreign_article.id,
                    title="X",
                    occurred_on=date(2026, 1, 1),
                    amount=1,
                )
            )
        assert exc_info.value.code == "unknown_article"


@pytest.mark.asyncio
async def test_expense_unknown_company(sessionmaker, data_factory: TestDataFactory) -> None:
    async with sessionmaker() as session:
        t1 = await data_factory.ensure_tenant(session=session)
        t2 = await data_factory.ensure_tenant(session=session, slug="other")
        svc1 = BudgetService(session, t1.id)

        foreign_company = await _make_company(session, t2.id)

        for company_id in ("does-not-exist", foreign_company.id):
            with pytest.raises(BudgetValidationError) as exc_info:
                await svc1.create_expense(
                    BudgetExpenseCreate(
                        domain="training",
                        title="X",
                        occurred_on=date(2026, 1, 1),
                        amount=1,
                        company_id=company_id,
                    )
                )
            assert exc_info.value.code == "unknown_company"


@pytest.mark.asyncio
async def test_expense_unknown_branch(sessionmaker, data_factory: TestDataFactory) -> None:
    async with sessionmaker() as session:
        t1 = await data_factory.ensure_tenant(session=session)
        t2 = await data_factory.ensure_tenant(session=session, slug="other")
        svc1 = BudgetService(session, t1.id)

        company2 = await _make_company(session, t2.id)
        foreign_branch = await _make_branch(session, t2.id, company2.id)

        for branch_id in ("does-not-exist", foreign_branch.id):
            with pytest.raises(BudgetValidationError) as exc_info:
                await svc1.create_expense(
                    BudgetExpenseCreate(
                        domain="training",
                        title="X",
                        occurred_on=date(2026, 1, 1),
                        amount=1,
                        branch_id=branch_id,
                    )
                )
            assert exc_info.value.code == "unknown_branch"


@pytest.mark.asyncio
async def test_expense_unknown_site(sessionmaker, data_factory: TestDataFactory) -> None:
    async with sessionmaker() as session:
        t1 = await data_factory.ensure_tenant(session=session)
        t2 = await data_factory.ensure_tenant(session=session, slug="other")
        svc1 = BudgetService(session, t1.id)

        company2 = await _make_company(session, t2.id)
        foreign_site = await _make_site(session, t2.id, company2.id)

        for site_id in ("does-not-exist", foreign_site.id):
            with pytest.raises(BudgetValidationError) as exc_info:
                await svc1.create_expense(
                    BudgetExpenseCreate(
                        domain="training",
                        title="X",
                        occurred_on=date(2026, 1, 1),
                        amount=1,
                        site_id=site_id,
                    )
                )
            assert exc_info.value.code == "unknown_site"


# ---------------------------------------------------------------------------
# article domain mismatch / universal article
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expense_article_domain_mismatch_and_universal(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = BudgetService(session, tenant.id)

        training_article = await svc.create_article(
            BudgetArticleCreate(code="training_external", name="Обучение", domain="training")
        )
        universal_article = await svc.create_article(
            BudgetArticleCreate(code="other", name="Прочее")  # domain=None
        )

        with pytest.raises(BudgetValidationError) as exc_info:
            await svc.create_expense(
                BudgetExpenseCreate(
                    domain="events",
                    article_id=training_article.id,
                    title="X",
                    occurred_on=date(2026, 1, 1),
                    amount=1,
                )
            )
        assert exc_info.value.code == "article_domain_mismatch"

        # universal article (domain=None) passes in any domain
        expense = await svc.create_expense(
            BudgetExpenseCreate(
                domain="events",
                article_id=universal_article.id,
                title="X",
                occurred_on=date(2026, 1, 1),
                amount=1,
            )
        )
        assert expense.article_id == universal_article.id


# ---------------------------------------------------------------------------
# article_inactive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expense_article_inactive(sessionmaker, data_factory: TestDataFactory) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = BudgetService(session, tenant.id)

        article = await svc.create_article(BudgetArticleCreate(code="other", name="Прочее"))
        await svc.update_article(article.id, BudgetArticleUpdate(is_active=False))

        with pytest.raises(BudgetValidationError) as exc_info:
            await svc.create_expense(
                BudgetExpenseCreate(
                    domain="training",
                    article_id=article.id,
                    title="X",
                    occurred_on=date(2026, 1, 1),
                    amount=1,
                )
            )
        assert exc_info.value.code == "article_inactive"

        # existing expense on an inactive article: update WITHOUT touching article_id
        # must NOT re-check the article at all (only touched refs are revalidated)
        active_article = await svc.create_article(
            BudgetArticleCreate(code="active_one", name="Активная")
        )
        expense = await svc.create_expense(
            BudgetExpenseCreate(
                domain="training",
                article_id=active_article.id,
                title="X",
                occurred_on=date(2026, 1, 1),
                amount=1,
            )
        )
        await svc.update_article(active_article.id, BudgetArticleUpdate(is_active=False))
        updated = await svc.update_expense(expense.id, BudgetExpenseUpdate(amount=2))
        assert float(updated.amount) == 2.0


# ---------------------------------------------------------------------------
# entity link validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expense_entity_link(sessionmaker, data_factory: TestDataFactory) -> None:
    async with sessionmaker() as session:
        t1 = await data_factory.ensure_tenant(session=session)
        t2 = await data_factory.ensure_tenant(session=session, slug="other")
        svc1 = BudgetService(session, t1.id)

        # invalid_entity_type: medical_exam is not valid for domain=events
        with pytest.raises(BudgetValidationError) as exc_info:
            await svc1.create_expense(
                BudgetExpenseCreate(
                    domain="events",
                    title="X",
                    occurred_on=date(2026, 1, 1),
                    amount=1,
                    entity_type="medical_exam",
                    entity_id="whatever",
                )
            )
        assert exc_info.value.code == "invalid_entity_type"

        # unknown_entity: nonexistent id
        with pytest.raises(BudgetValidationError) as exc_info:
            await svc1.create_expense(
                BudgetExpenseCreate(
                    domain="events",
                    title="X",
                    occurred_on=date(2026, 1, 1),
                    amount=1,
                    entity_type="corrective_action",
                    entity_id="does-not-exist",
                )
            )
        assert exc_info.value.code == "unknown_entity"

        # unknown_entity: foreign-tenant CorrectiveAction id
        foreign_action = await _make_corrective_action(session, t2.id)
        with pytest.raises(BudgetValidationError) as exc_info:
            await svc1.create_expense(
                BudgetExpenseCreate(
                    domain="events",
                    title="X",
                    occurred_on=date(2026, 1, 1),
                    amount=1,
                    entity_type="corrective_action",
                    entity_id=foreign_action.id,
                )
            )
        assert exc_info.value.code == "unknown_entity"

        # valid link to same-tenant CorrectiveAction
        own_action = await _make_corrective_action(session, t1.id)
        expense = await svc1.create_expense(
            BudgetExpenseCreate(
                domain="events",
                title="X",
                occurred_on=date(2026, 1, 1),
                amount=1,
                entity_type="corrective_action",
                entity_id=own_action.id,
            )
        )
        assert expense.entity_id == own_action.id
        assert expense.entity_type == "corrective_action"


@pytest.mark.asyncio
async def test_expense_update_validates_touched_ref(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    """A ref supplied in the PATCH body is validated tenant-scoped on update."""
    async with sessionmaker() as session:
        t1 = await data_factory.ensure_tenant(session=session)
        t2 = await data_factory.ensure_tenant(session=session, slug="other")
        svc1 = BudgetService(session, t1.id)

        company1 = await _make_company(session, t1.id)
        own_site = await _make_site(session, t1.id, company1.id)
        company2 = await _make_company(session, t2.id, name="ООО Чужая")
        foreign_site = await _make_site(session, t2.id, company2.id, name="Чужая площадка")

        expense = await svc1.create_expense(
            BudgetExpenseCreate(
                domain="training",
                title="X",
                occurred_on=date(2026, 1, 1),
                amount=1,
                site_id=own_site.id,
            )
        )

        with pytest.raises(BudgetValidationError) as exc_info:
            await svc1.update_expense(
                expense.id, BudgetExpenseUpdate(site_id=foreign_site.id)
            )
        assert exc_info.value.code == "unknown_site"


@pytest.mark.asyncio
async def test_expense_update_skips_untouched_stale_refs(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    """A stored ref whose target was later soft-deleted must not block unrelated PATCHes."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = BudgetService(session, tenant.id)

        article = await svc.create_article(BudgetArticleCreate(code="other", name="Прочее"))
        expense = await svc.create_expense(
            BudgetExpenseCreate(
                domain="training",
                article_id=article.id,
                title="X",
                occurred_on=date(2026, 1, 1),
                amount=1,
            )
        )

        await svc.delete_article(article.id)

        # amount-only PATCH does not revalidate the (now soft-deleted) stored article
        updated = await svc.update_expense(expense.id, BudgetExpenseUpdate(amount=5))
        assert float(updated.amount) == 5.0
        assert updated.article_id == article.id


# ---------------------------------------------------------------------------
# merged pairing check on update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expense_update_merged_entity_pairing(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = BudgetService(session, tenant.id)
        action = await _make_corrective_action(session, tenant.id)

        expense = await svc.create_expense(
            BudgetExpenseCreate(
                domain="events",
                title="X",
                occurred_on=date(2026, 1, 1),
                amount=1,
                entity_type="corrective_action",
                entity_id=action.id,
            )
        )

        # clearing only one side of the pair -> invalid_entity_link
        with pytest.raises(BudgetValidationError) as exc_info:
            await svc.update_expense(expense.id, BudgetExpenseUpdate(entity_type=None))
        assert exc_info.value.code == "invalid_entity_link"

        # clearing BOTH sides succeeds
        updated = await svc.update_expense(
            expense.id, BudgetExpenseUpdate(entity_type=None, entity_id=None)
        )
        assert updated.entity_type is None
        assert updated.entity_id is None


# ---------------------------------------------------------------------------
# explicit-null guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expense_explicit_null_rejected(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = BudgetService(session, tenant.id)
        expense = await svc.create_expense(
            BudgetExpenseCreate(
                domain="events",
                title="X",
                occurred_on=date(2026, 1, 1),
                amount=1,
            )
        )

        with pytest.raises(BudgetValidationError) as exc_info:
            await svc.update_expense(expense.id, BudgetExpenseUpdate(title=None))
        assert exc_info.value.code == "invalid_field_null"
