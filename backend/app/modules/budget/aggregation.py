"""Вычисляемый факт бюджетного контура. НИКОГДА не персистится (инвариант §12.4/§35.5).

Три чистых read-функции поверх журнала budget_expense:

- ``compute_domain_actual`` — факт одного домена за период с разрезом по статьям;
- ``compute_overview`` — сводка план/факт по всем доменам за окно, включая СИЗ
  read-only: план — ``ppe_safety_budget`` (склад), факт — складской леджер через
  ``app.modules.ppe.budget.compute_budget_actual``;
- ``compute_breakdown`` — факт журнала в разрезе article/domain/company/branch/site.

PPE/складские данные в breakdown НЕ участвуют: СИЗ-факт живёт в складском леджере
(``PPEStockMovement``) без бюджетных измерений (статья/company/branch/site) и виден
только в overview отдельным read-only доменом. Семантика плана в overview —
overlap: бюджет попадает в окно, если его период пересекается с окном, и
учитывается ПОЛНОЙ суммой (без пропорции). Деньги суммируются в Decimal
(``Numeric(14,2)`` -> ``decimal.Decimal``); float — только на границе
датаклассов/pydantic-схем.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.budget import (
    BUDGET_DOMAINS,
    BudgetExpense,
    BudgetExpenseArticle,
    SafetyBudget,
)
from app.models.master_data import Branch, Company, Site
from app.models.ppe_registry import PPESafetyBudget
from app.modules.ppe.budget import compute_budget_actual
from app.schemas.budget import (
    BudgetBreakdownItem,
    BudgetBreakdownResponse,
    BudgetOverviewBudgetRow,
    BudgetOverviewDomain,
    BudgetOverviewResponse,
)

from .service import BudgetValidationError

__all__ = [
    "BREAKDOWN_ROW_CAP",
    "BREAKDOWN_DIMENSIONS",
    "NO_BUCKET_ID",
    "ArticleActual",
    "DomainActual",
    "compute_domain_actual",
    "compute_overview",
    "compute_breakdown",
]

BREAKDOWN_ROW_CAP = 200
BREAKDOWN_DIMENSIONS = ("article", "domain", "company", "branch", "site")
NO_BUCKET_ID = ""
NO_ARTICLE_NAME = "— без статьи"
NO_REF_NAME = "— без привязки"

_DIMENSION_COLUMNS = {
    "company": BudgetExpense.company_id,
    "branch": BudgetExpense.branch_id,
    "site": BudgetExpense.site_id,
}
_DIMENSION_MODELS = {"company": Company, "branch": Branch, "site": Site}


@dataclass(slots=True, frozen=True)
class ArticleActual:
    article_id: str | None
    article_name: str  # "— без статьи" for NULL
    amount: float


@dataclass(slots=True, frozen=True)
class DomainActual:
    actual_total: float
    by_article: list[ArticleActual]
    expense_count: int


def _as_decimal(value) -> Decimal:
    """SQL aggregates return Decimal | None (and floats on some dialects) — normalize."""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _check_window(date_from: date, date_to: date) -> None:
    if date_to < date_from:
        raise BudgetValidationError(
            "breakdown_window_invalid", "date_to must be >= date_from"
        )


async def _domain_fact(
    session: AsyncSession,
    tenant_id: str,
    domain: str,
    period_start: date,
    period_end: date,
) -> tuple[Decimal, list[ArticleActual], int]:
    """Decimal total + by-article rows + expense count for one journal domain.

    Single GROUP BY query; the article outerjoin deliberately has NO deleted_at
    filter — historical expenses keep showing a soft-deleted article's name
    (mirrors BudgetService.list_expenses).
    """
    stmt = (
        select(
            BudgetExpense.article_id,
            BudgetExpenseArticle.name,
            func.sum(BudgetExpense.amount),
            func.count(),
        )
        .outerjoin(
            BudgetExpenseArticle, BudgetExpenseArticle.id == BudgetExpense.article_id
        )
        .where(
            BudgetExpense.tenant_id == tenant_id,
            BudgetExpense.domain == domain,
            BudgetExpense.occurred_on >= period_start,
            BudgetExpense.occurred_on <= period_end,
            BudgetExpense.deleted_at.is_(None),
        )
        .group_by(BudgetExpense.article_id, BudgetExpenseArticle.name)
    )
    total = Decimal("0")
    expense_count = 0
    by_article: list[ArticleActual] = []
    for article_id, article_name, amount_sum, row_count in (
        await session.execute(stmt)
    ).all():
        amount = _as_decimal(amount_sum)
        total += amount
        expense_count += int(row_count or 0)
        if article_id is None:
            display_name = NO_ARTICLE_NAME
        else:
            # FK is ondelete=SET NULL, so a dangling id is not expected; raw-id
            # fallback keeps the money visible if it ever happens anyway.
            display_name = article_name if article_name is not None else str(article_id)
        by_article.append(
            ArticleActual(
                article_id=article_id, article_name=display_name, amount=float(amount)
            )
        )
    by_article.sort(key=lambda row: (-row.amount, row.article_name))
    return total, by_article, expense_count


async def compute_domain_actual(
    session: AsyncSession,
    tenant_id: str,
    domain: str,
    period_start: date,
    period_end: date,
) -> DomainActual:
    total, by_article, expense_count = await _domain_fact(
        session, tenant_id, domain, period_start, period_end
    )
    return DomainActual(
        actual_total=float(total), by_article=by_article, expense_count=expense_count
    )


async def compute_overview(
    session: AsyncSession, tenant_id: str, date_from: date, date_to: date
) -> BudgetOverviewResponse:
    """План/факт по всем доменам за окно; домены без данных отдаются нулями.

    Journal-домены: план = Σ planned_amount бюджетов, пересекающихся с окном
    (полные суммы), факт окна — из журнала; actual_own_period каждого бюджета
    считается за ЕГО период, не за окно. PPE-домен read-only: план из
    ppe_safety_budget, факт из складского леджера (одна доп. query на ppe-бюджет —
    список мал).
    """
    _check_window(date_from, date_to)
    domains: list[BudgetOverviewDomain] = []

    for domain in BUDGET_DOMAINS:
        budgets = (
            (
                await session.execute(
                    select(SafetyBudget)
                    .where(
                        SafetyBudget.tenant_id == tenant_id,
                        SafetyBudget.domain == domain,
                        SafetyBudget.period_start <= date_to,
                        SafetyBudget.period_end >= date_from,
                        SafetyBudget.deleted_at.is_(None),
                    )
                    .order_by(SafetyBudget.period_start.desc(), SafetyBudget.id)
                )
            )
            .scalars()
            .all()
        )
        planned = sum((_as_decimal(b.planned_amount) for b in budgets), Decimal("0"))
        window_total, _, _ = await _domain_fact(
            session, tenant_id, domain, date_from, date_to
        )
        rows: list[BudgetOverviewBudgetRow] = []
        for budget in budgets:
            own_total, _, _ = await _domain_fact(
                session, tenant_id, domain, budget.period_start, budget.period_end
            )
            budget_planned = _as_decimal(budget.planned_amount)
            rows.append(
                BudgetOverviewBudgetRow(
                    id=budget.id,
                    name=budget.name,
                    period_start=budget.period_start,
                    period_end=budget.period_end,
                    planned_amount=float(budget_planned),
                    actual_own_period=float(own_total),
                    remaining=float(budget_planned - own_total),
                )
            )
        domains.append(
            BudgetOverviewDomain(
                domain=domain,
                read_only=False,
                planned=float(planned),
                actual=float(window_total),
                remaining=float(planned - window_total),
                warning_unpriced_receipts=None,
                budgets=rows,
            )
        )

    ppe_budgets = (
        (
            await session.execute(
                select(PPESafetyBudget)
                .where(
                    PPESafetyBudget.tenant_id == tenant_id,
                    PPESafetyBudget.period_start <= date_to,
                    PPESafetyBudget.period_end >= date_from,
                    PPESafetyBudget.deleted_at.is_(None),
                )
                .order_by(PPESafetyBudget.period_start.desc(), PPESafetyBudget.id)
            )
        )
        .scalars()
        .all()
    )
    ppe_planned = sum((_as_decimal(b.planned_amount) for b in ppe_budgets), Decimal("0"))
    ppe_window = await compute_budget_actual(session, tenant_id, date_from, date_to)
    ppe_actual = _as_decimal(ppe_window.actual_total)
    ppe_rows: list[BudgetOverviewBudgetRow] = []
    for budget in ppe_budgets:
        own = await compute_budget_actual(
            session, tenant_id, budget.period_start, budget.period_end
        )
        own_total = _as_decimal(own.actual_total)
        budget_planned = _as_decimal(budget.planned_amount)
        ppe_rows.append(
            BudgetOverviewBudgetRow(
                id=budget.id,
                name=budget.name,
                period_start=budget.period_start,
                period_end=budget.period_end,
                planned_amount=float(budget_planned),
                actual_own_period=float(own_total),
                remaining=float(budget_planned - own_total),
            )
        )
    domains.append(
        BudgetOverviewDomain(
            domain="ppe",
            read_only=True,
            planned=float(ppe_planned),
            actual=float(ppe_actual),
            remaining=float(ppe_planned - ppe_actual),
            warning_unpriced_receipts=ppe_window.unpriced_receipt_count,
            budgets=ppe_rows,
        )
    )

    return BudgetOverviewResponse(
        generated_at=datetime.now(timezone.utc),
        date_from=date_from,
        date_to=date_to,
        domains=domains,
    )


async def compute_breakdown(
    session: AsyncSession, tenant_id: str, dimension: str, date_from: date, date_to: date
) -> BudgetBreakdownResponse:
    """Факт журнала за окно в одном разрезе; один GROUP BY на вызов.

    NULL-измерение собирается в None-bucket (id="" / «— без статьи»/«— без
    привязки»); bucket появляется только когда его сумма > 0 (amount > 0 по
    схеме — существующая группа всегда ненулевая). Живой FK на отсутствующую/
    soft-deleted master-строку не теряет денег: имя падает на сырой id.
    """
    if dimension not in BREAKDOWN_DIMENSIONS:
        raise BudgetValidationError(
            "breakdown_dimension_unknown", f"unknown breakdown dimension: {dimension}"
        )
    _check_window(date_from, date_to)

    filters = (
        BudgetExpense.tenant_id == tenant_id,
        BudgetExpense.occurred_on >= date_from,
        BudgetExpense.occurred_on <= date_to,
        BudgetExpense.deleted_at.is_(None),
    )
    entries: list[tuple[str, str, Decimal]] = []

    if dimension == "article":
        stmt = (
            select(
                BudgetExpense.article_id,
                BudgetExpenseArticle.name,
                func.sum(BudgetExpense.amount),
            )
            .outerjoin(
                BudgetExpenseArticle, BudgetExpenseArticle.id == BudgetExpense.article_id
            )
            .where(*filters)
            .group_by(BudgetExpense.article_id, BudgetExpenseArticle.name)
        )
        for article_id, name, amount_sum in (await session.execute(stmt)).all():
            amount = _as_decimal(amount_sum)
            if article_id is None:
                if amount > 0:
                    entries.append((NO_BUCKET_ID, NO_ARTICLE_NAME, amount))
            else:
                entries.append(
                    (article_id, name if name is not None else str(article_id), amount)
                )
    elif dimension == "domain":
        stmt = (
            select(BudgetExpense.domain, func.sum(BudgetExpense.amount))
            .where(*filters)
            .group_by(BudgetExpense.domain)
        )
        for domain_code, amount_sum in (await session.execute(stmt)).all():
            # id = name = domain code; RU-подписи — словарь фронтенда
            entries.append((domain_code, domain_code, _as_decimal(amount_sum)))
    else:  # company | branch | site
        dim_col = _DIMENSION_COLUMNS[dimension]
        ref_model = _DIMENSION_MODELS[dimension]
        stmt = (
            select(dim_col, ref_model.name, func.sum(BudgetExpense.amount))
            .outerjoin(
                ref_model,
                and_(
                    ref_model.id == dim_col,
                    ref_model.tenant_id == tenant_id,
                    ref_model.deleted_at.is_(None),
                ),
            )
            .where(*filters)
            .group_by(dim_col, ref_model.name)
        )
        for ref_id, name, amount_sum in (await session.execute(stmt)).all():
            amount = _as_decimal(amount_sum)
            if ref_id is None:
                if amount > 0:
                    entries.append((NO_BUCKET_ID, NO_REF_NAME, amount))
            else:
                entries.append((ref_id, name if name is not None else str(ref_id), amount))

    entries.sort(key=lambda row: (-row[2], row[1]))
    return BudgetBreakdownResponse(
        dimension=dimension,
        date_from=date_from,
        date_to=date_to,
        total=len(entries),
        items=[
            BudgetBreakdownItem(id=entry_id, name=name, amount=float(amount))
            for entry_id, name, amount in entries[:BREAKDOWN_ROW_CAP]
        ],
    )
