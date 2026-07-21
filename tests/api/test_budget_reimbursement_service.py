"""Service pins for СФР reimbursement claims (§12.4 срез-2, bg02).

Covers CRUD + claim composition + the FSM side effects that live in the service
(the transition table itself is pinned I/O-free in
tests/api/test_budget_reimbursement_lifecycle.py). Budgets/articles CRUD is
pinned in tests/api/test_budget_service.py, the expense journal in
tests/api/test_budget_expense_service.py.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.models.models import Company
from app.modules.budget import reimbursement_lifecycle as lc
from app.modules.budget.reimbursement_service import (
    ExpenseAlreadyLinked,
    ReimbursementNotFound,
    ReimbursementService,
)
from app.modules.budget.service import BudgetService, BudgetValidationError
from app.schemas.budget import (
    BudgetExpenseCreate,
    ReimbursementCreate,
    ReimbursementDecision,
    ReimbursementUpdate,
)
from tests.utils.factories import TestDataFactory

NO_DECISION = ReimbursementDecision()


def _claim_payload(**overrides) -> ReimbursementCreate:
    fields = {
        "title": "Возмещение за I квартал",
        "period_start": date(2026, 1, 1),
        "period_end": date(2026, 3, 31),
        "requested_amount": 100000,
    }
    fields.update(overrides)
    return ReimbursementCreate(**fields)


async def _make_expense(
    session,
    tenant_id: str,
    amount: float,
    title: str = "Обучение",
    occurred_on: date = date(2026, 2, 1),
):
    """Расход в журнале — единственный источник items_amount заявки."""
    return await BudgetService(session, tenant_id).create_expense(
        BudgetExpenseCreate(
            domain="training",
            title=title,
            occurred_on=occurred_on,
            amount=amount,
        )
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_is_created_as_draft_and_listed(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = ReimbursementService(session, tenant.id)

        claim = await svc.create_claim(_claim_payload(reference="СФР-1"))

        # статус не принимается из payload — заявка всегда рождается черновиком
        assert claim.status == lc.STATUS_DRAFT
        assert claim.reference == "СФР-1"
        assert claim.approved_amount is None
        assert claim.submitted_at is None

        got = await svc.get_claim(claim.id)
        assert got.id == claim.id

        items, total = await svc.list_claims()
        assert total == 1
        assert [i.id for i in items] == [claim.id]


@pytest.mark.asyncio
async def test_list_claims_filters_by_status_and_rejects_unknown_one(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = ReimbursementService(session, tenant.id)

        draft = await svc.create_claim(_claim_payload(title="Черновик"))
        submitted = await svc.create_claim(_claim_payload(title="Поданная"))
        expense = await _make_expense(session, tenant.id, 5000)
        await svc.add_item(submitted.id, expense.id)
        await svc.run_action(submitted.id, "submit", NO_DECISION)

        drafts, drafts_total = await svc.list_claims(status=lc.STATUS_DRAFT)
        assert drafts_total == 1
        assert [i.id for i in drafts] == [draft.id]

        with pytest.raises(BudgetValidationError) as exc:
            await svc.list_claims(status="bogus")
        assert exc.value.code == "unknown_status"


@pytest.mark.asyncio
async def test_claims_are_tenant_scoped(sessionmaker, data_factory: TestDataFactory) -> None:
    async with sessionmaker() as session:
        t1 = await data_factory.ensure_tenant(session=session)
        t2 = await data_factory.ensure_tenant(session=session, slug="other")

        claim = await ReimbursementService(session, t1.id).create_claim(_claim_payload())

        other = ReimbursementService(session, t2.id)
        _, total = await other.list_claims()
        assert total == 0
        with pytest.raises(ReimbursementNotFound):
            await other.get_claim(claim.id)


@pytest.mark.asyncio
async def test_update_rejects_explicit_nulls_and_inverted_period(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = ReimbursementService(session, tenant.id)
        claim = await svc.create_claim(_claim_payload())

        with pytest.raises(BudgetValidationError) as null_exc:
            await svc.update_claim(claim.id, ReimbursementUpdate(title=None))
        assert null_exc.value.code == "invalid_field_null"

        # период проверяется на СЛИТЫХ значениях: приходит только начало, конец — хранимый
        with pytest.raises(BudgetValidationError) as period_exc:
            await svc.update_claim(claim.id, ReimbursementUpdate(period_start=date(2026, 12, 31)))
        assert period_exc.value.code == "period_invalid"

        updated = await svc.update_claim(claim.id, ReimbursementUpdate(requested_amount=7000))
        assert float(updated.requested_amount) == 7000.0
        assert updated.title == "Возмещение за I квартал"  # не затёрто


@pytest.mark.asyncio
async def test_update_rejects_company_from_another_tenant(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        t1 = await data_factory.ensure_tenant(session=session)
        t2 = await data_factory.ensure_tenant(session=session, slug="other")
        foreign = Company(tenant_id=t2.id, name="Чужая компания")
        session.add(foreign)
        await session.flush()

        svc = ReimbursementService(session, t1.id)
        claim = await svc.create_claim(_claim_payload())

        with pytest.raises(BudgetValidationError) as exc:
            await svc.update_claim(claim.id, ReimbursementUpdate(company_id=foreign.id))
        assert exc.value.code == "unknown_company"


@pytest.mark.asyncio
async def test_deleted_claim_disappears_from_reads(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = ReimbursementService(session, tenant.id)
        claim = await svc.create_claim(_claim_payload())

        await svc.delete_claim(claim.id)

        _, total = await svc.list_claims()
        assert total == 0
        with pytest.raises(ReimbursementNotFound):
            await svc.get_claim(claim.id)


# ---------------------------------------------------------------------------
# состав заявки
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_items_amount_sums_linked_expenses_only(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = ReimbursementService(session, tenant.id)
        claim = await svc.create_claim(_claim_payload())

        older = await _make_expense(session, tenant.id, 1500, "Каски", date(2026, 2, 1))
        newer = await _make_expense(session, tenant.id, 2500, "Перчатки", date(2026, 3, 1))
        await _make_expense(session, tenant.id, 9999, "Не в заявке")

        await svc.add_item(claim.id, older.id)
        await svc.add_item(claim.id, newer.id)

        assert await svc.aggregate_items([claim.id]) == {claim.id: (2, 4000.0)}
        # состав отдаётся свежими расходами вперёд (occurred_on desc)
        assert [e.id for e in await svc.list_items(claim.id)] == [newer.id, older.id]


@pytest.mark.asyncio
async def test_aggregate_items_drops_soft_deleted_expenses(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    """Расход, снятый после привязки, уходит из суммы — строка состава остаётся."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = ReimbursementService(session, tenant.id)
        claim = await svc.create_claim(_claim_payload())

        kept = await _make_expense(session, tenant.id, 1000, "Осталось")
        dropped = await _make_expense(session, tenant.id, 4000, "Снято")
        await svc.add_item(claim.id, kept.id)
        await svc.add_item(claim.id, dropped.id)

        dropped.deleted_at = datetime.now(timezone.utc)
        await session.flush()

        assert await svc.aggregate_items([claim.id]) == {claim.id: (1, 1000.0)}
        assert [e.id for e in await svc.list_items(claim.id)] == [kept.id]


@pytest.mark.asyncio
async def test_aggregate_items_on_empty_input_and_empty_claim(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = ReimbursementService(session, tenant.id)
        claim = await svc.create_claim(_claim_payload())

        assert await svc.aggregate_items([]) == {}
        # у пустой заявки ключа нет вовсе — читатели обязаны использовать .get(..., (0, 0.0))
        assert await svc.aggregate_items([claim.id]) == {}


@pytest.mark.asyncio
async def test_add_item_rejects_unknown_expense(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = ReimbursementService(session, tenant.id)
        claim = await svc.create_claim(_claim_payload())

        with pytest.raises(BudgetValidationError) as exc:
            await svc.add_item(claim.id, "no-such-expense")
        assert exc.value.code == "unknown_expense"


@pytest.mark.asyncio
async def test_add_item_twice_raises_already_linked(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    """Повтор ловится unique-парой; сервис откатывает транзакцию — сессия дальше не используется."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = ReimbursementService(session, tenant.id)
        claim = await svc.create_claim(_claim_payload())
        expense = await _make_expense(session, tenant.id, 1000)
        # id запоминаем до повторного add_item: его rollback истекает ORM-объекты,
        # и обращение к expense.id после отката ушло бы в БД по мёртвой сессии.
        expense_id = expense.id
        claim_id = claim.id
        await svc.add_item(claim_id, expense_id)
        await session.commit()

        with pytest.raises(ExpenseAlreadyLinked) as exc:
            await svc.add_item(claim_id, expense_id)
        assert exc.value.expense_id == expense_id


@pytest.mark.asyncio
async def test_remove_item_unlinks_and_allows_relinking(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    """Строка состава удаляется жёстко — иначе unique-пара заблокировала бы повторную привязку."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = ReimbursementService(session, tenant.id)
        claim = await svc.create_claim(_claim_payload())
        expense = await _make_expense(session, tenant.id, 1000)

        await svc.add_item(claim.id, expense.id)
        await svc.remove_item(claim.id, expense.id)
        assert await svc.aggregate_items([claim.id]) == {}

        await svc.add_item(claim.id, expense.id)
        assert await svc.aggregate_items([claim.id]) == {claim.id: (1, 1000.0)}


@pytest.mark.asyncio
async def test_remove_item_that_is_not_linked(sessionmaker, data_factory: TestDataFactory) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = ReimbursementService(session, tenant.id)
        claim = await svc.create_claim(_claim_payload())
        expense = await _make_expense(session, tenant.id, 1000)

        with pytest.raises(BudgetValidationError) as exc:
            await svc.remove_item(claim.id, expense.id)
        assert exc.value.code == "expense_not_linked"


# ---------------------------------------------------------------------------
# FSM
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_claim_cannot_be_submitted(sessionmaker, data_factory: TestDataFactory) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = ReimbursementService(session, tenant.id)
        claim = await svc.create_claim(_claim_payload())

        with pytest.raises(BudgetValidationError) as exc:
            await svc.run_action(claim.id, "submit", NO_DECISION)
        assert exc.value.code == "reimbursement_empty"
        assert claim.status == lc.STATUS_DRAFT


@pytest.mark.asyncio
async def test_happy_path_submit_approve_pay_stamps_timestamps(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = ReimbursementService(session, tenant.id)
        claim = await svc.create_claim(_claim_payload())
        expense = await _make_expense(session, tenant.id, 30000)
        await svc.add_item(claim.id, expense.id)

        submitted = await svc.run_action(claim.id, "submit", NO_DECISION)
        assert submitted.status == lc.STATUS_SUBMITTED
        assert submitted.submitted_at is not None

        approved = await svc.run_action(
            claim.id, "approve", ReimbursementDecision(approved_amount=80000)
        )
        assert approved.status == lc.STATUS_APPROVED
        assert float(approved.approved_amount) == 80000.0
        assert approved.decided_at is not None

        paid = await svc.run_action(claim.id, "pay", NO_DECISION)
        assert paid.status == lc.STATUS_PAID
        assert paid.paid_at is not None


@pytest.mark.asyncio
async def test_approve_defaults_to_requested_amount_and_caps_at_it(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = ReimbursementService(session, tenant.id)

        over = await svc.create_claim(_claim_payload(requested_amount=100000))
        expense = await _make_expense(session, tenant.id, 100000)
        await svc.add_item(over.id, expense.id)
        await svc.run_action(over.id, "submit", NO_DECISION)

        with pytest.raises(BudgetValidationError) as exc:
            await svc.run_action(over.id, "approve", ReimbursementDecision(approved_amount=100001))
        assert exc.value.code == "approved_amount_invalid"

        # без approved_amount одобряется вся запрошенная сумма
        approved = await svc.run_action(over.id, "approve", NO_DECISION)
        assert float(approved.approved_amount) == 100000.0


@pytest.mark.asyncio
async def test_reject_requires_a_reason(sessionmaker, data_factory: TestDataFactory) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = ReimbursementService(session, tenant.id)
        claim = await svc.create_claim(_claim_payload())
        expense = await _make_expense(session, tenant.id, 1000)
        await svc.add_item(claim.id, expense.id)
        await svc.run_action(claim.id, "submit", NO_DECISION)

        with pytest.raises(BudgetValidationError) as exc:
            await svc.run_action(claim.id, "reject", NO_DECISION)
        assert exc.value.code == "decision_reason_required"

        rejected = await svc.run_action(
            claim.id, "reject", ReimbursementDecision(decision_reason="Нет подтверждающих")
        )
        assert rejected.status == lc.STATUS_REJECTED
        assert rejected.decision_reason == "Нет подтверждающих"
        assert rejected.decided_at is not None


@pytest.mark.asyncio
async def test_unknown_action_is_a_validation_error(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = ReimbursementService(session, tenant.id)
        claim = await svc.create_claim(_claim_payload())

        with pytest.raises(BudgetValidationError) as exc:
            await svc.run_action(claim.id, "unsubmit", NO_DECISION)
        assert exc.value.code == "unknown_action"


@pytest.mark.asyncio
async def test_invalid_transition_raises_transition_error(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = ReimbursementService(session, tenant.id)
        claim = await svc.create_claim(_claim_payload())

        # черновик нельзя одобрить, минуя подачу (роутер маппит это в 409)
        with pytest.raises(lc.ReimbursementTransitionError):
            await svc.run_action(claim.id, "approve", NO_DECISION)


@pytest.mark.asyncio
async def test_submitted_claim_is_frozen_for_edits(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    """После подачи заявка — документ во внешнем органе: ни правки, ни состава, ни удаления."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = ReimbursementService(session, tenant.id)
        claim = await svc.create_claim(_claim_payload())
        linked = await _make_expense(session, tenant.id, 1000, "В заявке")
        other = await _make_expense(session, tenant.id, 2000, "Ещё один")
        await svc.add_item(claim.id, linked.id)
        await svc.run_action(claim.id, "submit", NO_DECISION)

        with pytest.raises(lc.ReimbursementTransitionError):
            await svc.update_claim(claim.id, ReimbursementUpdate(title="Правка"))
        with pytest.raises(lc.ReimbursementTransitionError):
            await svc.add_item(claim.id, other.id)
        with pytest.raises(lc.ReimbursementTransitionError):
            await svc.remove_item(claim.id, linked.id)
        with pytest.raises(lc.ReimbursementTransitionError):
            await svc.delete_claim(claim.id)
