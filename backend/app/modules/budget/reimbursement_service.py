"""CRUD + FSM-переходы заявок на возмещение СФР (§12.4 срез-2).

Паттерн зеркалит app/modules/budget/service.py (flush-only CRUD, tenant-scoped
_base()-хелперы, BudgetValidationError(code) для 422) и app/domains/work_permits
(чистый FSM в отдельном модуле, TransitionError -> 409). Сервис НИЧЕГО не коммитит —
коммит делает роутер.

Инвариант состава: сумма заявки (requested_amount) вводится вручную, а сумма
привязанных расходов (items_amount) ВСЕГДА считается из журнала budget_expense
и нигде не денормализуется — зеркало инварианта факта в aggregation.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.budget import BudgetExpense, BudgetReimbursement, BudgetReimbursementItem
from app.models.master_data import Company
from app.schemas.budget import (
    ReimbursementCreate,
    ReimbursementDecision,
    ReimbursementUpdate,
)

from . import reimbursement_lifecycle as lc
from .service import BudgetValidationError

__all__ = [
    "ReimbursementNotFound",
    "ExpenseAlreadyLinked",
    "ReimbursementService",
]

# Поля, которые нельзя обнулить явным null в PATCH (конвенция budget/service.py)
_REIMBURSEMENT_NON_NULLABLE = frozenset({"title", "period_start", "period_end", "requested_amount"})


class ReimbursementNotFound(Exception):
    def __init__(self, reimbursement_id: str) -> None:
        super().__init__(f"budget reimbursement not found: {reimbursement_id}")
        self.reimbursement_id = reimbursement_id


class ExpenseAlreadyLinked(Exception):
    def __init__(self, expense_id: str) -> None:
        super().__init__(f"expense already linked to this reimbursement: {expense_id}")
        self.expense_id = expense_id


def _reject_explicit_nulls(fields: dict) -> None:
    for key in _REIMBURSEMENT_NON_NULLABLE & fields.keys():
        if fields[key] is None:
            raise BudgetValidationError("invalid_field_null", f"Field '{key}' cannot be null")


class ReimbursementService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _claim_base(self):
        return select(BudgetReimbursement).where(
            BudgetReimbursement.tenant_id == self.tenant_id,
            BudgetReimbursement.deleted_at.is_(None),
        )

    async def _load_claim(self, reimbursement_id: str) -> BudgetReimbursement:
        row = await self.session.scalar(
            self._claim_base().where(BudgetReimbursement.id == reimbursement_id)
        )
        if row is None:
            raise ReimbursementNotFound(reimbursement_id)
        return row

    async def _validate_company(self, company_id: str | None) -> None:
        if company_id is None:
            return
        exists = await self.session.scalar(
            select(Company.id).where(
                Company.tenant_id == self.tenant_id,
                Company.id == company_id,
                Company.deleted_at.is_(None),
            )
        )
        if exists is None:
            raise BudgetValidationError("unknown_company", f"unknown company: {company_id}")

    async def aggregate_items(self, claim_ids: list[str]) -> dict[str, tuple[int, float]]:
        """claim_id -> (item_count, items_amount); мягко удалённые расходы не считаются.

        Расход, снятый (soft-delete) уже после привязки, исчезает из суммы, но строка
        состава остаётся — это осознанно: заявка помнит, что расход к ней относили.
        """
        if not claim_ids:
            return {}
        rows = (
            await self.session.execute(
                select(
                    BudgetReimbursementItem.reimbursement_id,
                    func.count(BudgetExpense.id),
                    func.coalesce(func.sum(BudgetExpense.amount), 0),
                )
                .join(BudgetExpense, BudgetExpense.id == BudgetReimbursementItem.expense_id)
                .where(
                    BudgetReimbursementItem.tenant_id == self.tenant_id,
                    BudgetReimbursementItem.reimbursement_id.in_(claim_ids),
                    BudgetReimbursementItem.deleted_at.is_(None),
                    BudgetExpense.deleted_at.is_(None),
                )
                .group_by(BudgetReimbursementItem.reimbursement_id)
            )
        ).all()
        return {row[0]: (int(row[1]), float(Decimal(str(row[2] or 0)))) for row in rows}

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create_claim(self, payload: ReimbursementCreate) -> BudgetReimbursement:
        await self._validate_company(payload.company_id)
        claim = BudgetReimbursement(
            tenant_id=self.tenant_id, status=lc.STATUS_DRAFT, **payload.model_dump()
        )
        self.session.add(claim)
        await self.session.flush()
        await self.session.refresh(claim)
        return claim

    async def list_claims(
        self, *, status: str | None = None, limit: int = 100, offset: int = 0
    ) -> tuple[list[BudgetReimbursement], int]:
        stmt = self._claim_base()
        if status is not None:
            if status not in lc.REIMBURSEMENT_STATUSES:
                raise BudgetValidationError("unknown_status", f"unknown status: {status}")
            stmt = stmt.where(BudgetReimbursement.status == status)
        total = int(
            await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        )
        rows = list(
            (
                await self.session.execute(
                    stmt.order_by(BudgetReimbursement.period_start.desc(), BudgetReimbursement.id)
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return rows, total

    async def get_claim(self, reimbursement_id: str) -> BudgetReimbursement:
        return await self._load_claim(reimbursement_id)

    async def list_items(self, reimbursement_id: str) -> list[BudgetExpense]:
        """Расходы состава заявки (мягко удалённые расходы исключены — как в сумме)."""
        await self._load_claim(reimbursement_id)
        rows = (
            await self.session.execute(
                select(BudgetExpense)
                .join(
                    BudgetReimbursementItem,
                    BudgetReimbursementItem.expense_id == BudgetExpense.id,
                )
                .where(
                    BudgetReimbursementItem.tenant_id == self.tenant_id,
                    BudgetReimbursementItem.reimbursement_id == reimbursement_id,
                    BudgetReimbursementItem.deleted_at.is_(None),
                    BudgetExpense.deleted_at.is_(None),
                )
                .order_by(BudgetExpense.occurred_on.desc(), BudgetExpense.id)
            )
        ).scalars()
        return list(rows.all())

    async def update_claim(
        self, reimbursement_id: str, payload: ReimbursementUpdate
    ) -> BudgetReimbursement:
        """Частичный PATCH; период перепроверяется на слитых (хранимое+входящее) значениях."""
        claim = await self._load_claim(reimbursement_id)
        lc.ensure_editable(str(claim.status))
        fields = payload.model_dump(exclude_unset=True)
        _reject_explicit_nulls(fields)
        effective_start = fields.get("period_start", claim.period_start)
        effective_end = fields.get("period_end", claim.period_end)
        if effective_end < effective_start:
            raise BudgetValidationError("period_invalid", "period_end must be >= period_start")
        if "company_id" in fields:
            await self._validate_company(fields["company_id"])
        for key, value in fields.items():
            setattr(claim, key, value)
        await self.session.flush()
        await self.session.refresh(claim)
        return claim

    async def delete_claim(self, reimbursement_id: str) -> None:
        """Мягкое удаление; поданную заявку удалить нельзя (документ уже во внешнем органе)."""
        claim = await self._load_claim(reimbursement_id)
        lc.ensure_editable(str(claim.status))
        claim.deleted_at = datetime.now(timezone.utc)
        await self.session.flush()

    # ------------------------------------------------------------------
    # состав заявки
    # ------------------------------------------------------------------

    async def add_item(self, reimbursement_id: str, expense_id: str) -> BudgetExpense:
        claim = await self._load_claim(reimbursement_id)
        lc.ensure_editable(str(claim.status))
        expense = await self.session.scalar(
            select(BudgetExpense).where(
                BudgetExpense.tenant_id == self.tenant_id,
                BudgetExpense.id == expense_id,
                BudgetExpense.deleted_at.is_(None),
            )
        )
        if expense is None:
            raise BudgetValidationError("unknown_expense", f"unknown expense: {expense_id}")
        self.session.add(
            BudgetReimbursementItem(
                tenant_id=self.tenant_id,
                reimbursement_id=reimbursement_id,
                expense_id=expense_id,
            )
        )
        try:
            await self.session.flush()
        except IntegrityError as exc:  # гонка/повтор — uq_budget_reimbursement_item_pair
            # rollback() откатывает ВСЮ транзакцию запроса: продолжать работу с session
            # в этом запросе после except нельзя (конвенция create_article).
            await self.session.rollback()
            raise ExpenseAlreadyLinked(expense_id) from exc
        return expense

    async def remove_item(self, reimbursement_id: str, expense_id: str) -> None:
        """Жёсткое удаление строки состава: unique-пара не должна блокировать повторную привязку."""
        claim = await self._load_claim(reimbursement_id)
        lc.ensure_editable(str(claim.status))
        result = await self.session.execute(
            sa_delete(BudgetReimbursementItem).where(
                BudgetReimbursementItem.tenant_id == self.tenant_id,
                BudgetReimbursementItem.reimbursement_id == reimbursement_id,
                BudgetReimbursementItem.expense_id == expense_id,
            )
        )
        if result.rowcount == 0:
            raise BudgetValidationError(
                "expense_not_linked", f"expense is not linked to this claim: {expense_id}"
            )
        await self.session.flush()

    # ------------------------------------------------------------------
    # FSM
    # ------------------------------------------------------------------

    async def run_action(
        self, reimbursement_id: str, action: str, payload: ReimbursementDecision
    ) -> BudgetReimbursement:
        claim = await self._load_claim(reimbursement_id)
        target = lc.ACTION_TARGETS.get(action)
        if target is None:
            raise BudgetValidationError("unknown_action", f"unknown action: {action}")
        lc.validate_transition(str(claim.status), target)
        now = datetime.now(timezone.utc)

        if target == lc.STATUS_SUBMITTED:
            counts = await self.aggregate_items([reimbursement_id])
            if counts.get(reimbursement_id, (0, 0.0))[0] == 0:
                raise BudgetValidationError(
                    "reimbursement_empty", "claim has no linked expenses to submit"
                )
            claim.submitted_at = now
        elif target == lc.STATUS_APPROVED:
            approved = (
                payload.approved_amount
                if payload.approved_amount is not None
                else float(claim.requested_amount)
            )
            if approved > float(claim.requested_amount):
                raise BudgetValidationError(
                    "approved_amount_invalid",
                    "approved_amount must be <= requested_amount",
                )
            claim.approved_amount = approved
            claim.decision_reason = payload.decision_reason
            claim.decided_at = now
        elif target == lc.STATUS_REJECTED:
            if payload.decision_reason is None:
                raise BudgetValidationError(
                    "decision_reason_required", "decision_reason is required to reject a claim"
                )
            claim.decision_reason = payload.decision_reason
            claim.decided_at = now
        elif target == lc.STATUS_PAID:
            claim.paid_at = now

        claim.status = target
        await self.session.flush()
        await self.session.refresh(claim)
        return claim
