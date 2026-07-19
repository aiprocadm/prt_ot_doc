"""Tests for the budget demo seed in bootstrap_demo_tenant.

Verifies that running bootstrap_demo_tenant:
- creates the "budget" Feature catalogue row and enables it for the demo tenant,
- seeds the default expense-article catalog + 3 domain budgets + 5 demo expenses,
- seeds 3 СФР reimbursement claims (draft/submitted/approved) with their composition,
- is idempotent (re-run does not duplicate budgets/expenses/articles/claims).
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.core.config import Settings
from app.core.feature_flags import is_feature_enabled
from app.models.budget import (
    BudgetExpense,
    BudgetExpenseArticle,
    BudgetReimbursement,
    BudgetReimbursementItem,
    SafetyBudget,
)
from app.models.feature import Feature
from app.models.models import Tenant
from app.services.demo_bootstrap import bootstrap_demo_tenant

_DEMO_TENANT_SLUG = "budget-bootstrap-demo"
_DEMO_COMPANY = "Budget Bootstrap Co"
_DEMO_SITE = "Budget Bootstrap Site"


def _make_settings() -> Settings:
    return Settings.model_validate(
        {
            "APP_ENV": "test",
            "DEMO_BOOTSTRAP": True,
            "DEMO_TENANT_ID": _DEMO_TENANT_SLUG,
            "DEMO_COMPANY_NAME": _DEMO_COMPANY,
            "DEMO_SITE_NAME": _DEMO_SITE,
            "LIBREOFFICE_BIN": "python",
        }
    )


async def _fake_ensure_default_packs(session, *, tenant_slug: str) -> None:
    return None


@pytest.mark.anyio
async def test_budget_feature_seeded_and_enabled(
    sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """bootstrap_demo_tenant seeds the 'budget' Feature and enables it for the demo tenant."""

    monkeypatch.setattr(
        "app.services.demo_bootstrap.ensure_default_packs", _fake_ensure_default_packs
    )

    await bootstrap_demo_tenant(_make_settings())

    async with sessionmaker() as session:
        feature = (
            await session.execute(select(Feature).where(Feature.code == "budget"))
        ).scalar_one_or_none()
        assert feature is not None, "Feature(code='budget') must exist after bootstrap"
        assert feature.title == "Бюджет безопасности"

        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == _DEMO_TENANT_SLUG))
        ).scalar_one()
        tenant_id = str(tenant.id)

        enabled = await is_feature_enabled(session, tenant_id, "budget")
        assert enabled is True


@pytest.mark.anyio
async def test_budget_demo_data_seeded(
    sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """bootstrap_demo_tenant seeds default articles + 3 budgets + 5 expenses."""

    monkeypatch.setattr(
        "app.services.demo_bootstrap.ensure_default_packs", _fake_ensure_default_packs
    )

    await bootstrap_demo_tenant(_make_settings())

    async with sessionmaker() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == _DEMO_TENANT_SLUG))
        ).scalar_one()
        tenant_id = str(tenant.id)

        article_count = (
            await session.execute(
                select(func.count()).where(BudgetExpenseArticle.tenant_id == tenant_id)
            )
        ).scalar_one()
        assert article_count == 9, f"Expected 9 default articles, got {article_count}"

        budget_names = set(
            (
                await session.execute(
                    select(SafetyBudget.name).where(SafetyBudget.tenant_id == tenant_id)
                )
            )
            .scalars()
            .all()
        )
        assert budget_names == {
            "Бюджет обучения 2026",
            "Бюджет медосмотров 2026",
            "Бюджет мероприятий 2026",
        }

        expense_titles = set(
            (
                await session.execute(
                    select(BudgetExpense.title).where(BudgetExpense.tenant_id == tenant_id)
                )
            )
            .scalars()
            .all()
        )
        assert expense_titles == {
            "Обучение по охране труда (группа 1)",
            "Внутренний семинар по ОТ",
            "Периодический медосмотр цеха №1",
            "Ремонт вентиляции сварочного поста",
            "Закупка знаков безопасности",
        }


@pytest.mark.anyio
async def test_budget_reimbursements_seeded(
    sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """bootstrap_demo_tenant seeds 3 СФР claims (draft/submitted/approved) with composition."""

    monkeypatch.setattr(
        "app.services.demo_bootstrap.ensure_default_packs", _fake_ensure_default_packs
    )

    await bootstrap_demo_tenant(_make_settings())

    async with sessionmaker() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == _DEMO_TENANT_SLUG))
        ).scalar_one()
        tenant_id = str(tenant.id)

        claims = {
            row.title: row
            for row in (
                await session.execute(
                    select(BudgetReimbursement).where(BudgetReimbursement.tenant_id == tenant_id)
                )
            )
            .scalars()
            .all()
        }
        assert set(claims) == {
            "Возмещение СФР — I полугодие 2026 (черновик)",
            "Возмещение СФР — медосмотры 2026 (подана)",
            "Возмещение СФР — мероприятия 2026 (одобрена)",
        }
        assert {claim.status for claim in claims.values()} == {"draft", "submitted", "approved"}

        draft = claims["Возмещение СФР — I полугодие 2026 (черновик)"]
        assert draft.submitted_at is None and draft.approved_amount is None

        submitted = claims["Возмещение СФР — медосмотры 2026 (подана)"]
        assert submitted.submitted_at is not None and submitted.decided_at is None

        approved = claims["Возмещение СФР — мероприятия 2026 (одобрена)"]
        assert float(approved.approved_amount) == 180000.0
        assert approved.decided_at is not None
        assert approved.paid_at is None

        # Состав: 2 + 1 + 2 строки, каждая ссылается на demo-расход.
        item_counts = {
            claim.title: (
                await session.execute(
                    select(func.count()).where(BudgetReimbursementItem.reimbursement_id == claim.id)
                )
            ).scalar_one()
            for claim in claims.values()
        }
        assert sorted(item_counts.values()) == [1, 2, 2]


@pytest.mark.anyio
async def test_budget_bootstrap_is_idempotent(
    sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-running bootstrap does not duplicate budgets, expenses, or articles."""

    monkeypatch.setattr(
        "app.services.demo_bootstrap.ensure_default_packs", _fake_ensure_default_packs
    )

    settings = _make_settings()

    await bootstrap_demo_tenant(settings)
    await bootstrap_demo_tenant(settings)

    async with sessionmaker() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == _DEMO_TENANT_SLUG))
        ).scalar_one()
        tenant_id = str(tenant.id)

        article_count = (
            await session.execute(
                select(func.count()).where(BudgetExpenseArticle.tenant_id == tenant_id)
            )
        ).scalar_one()
        assert (
            article_count == 9
        ), f"Expected exactly 9 articles after double-bootstrap, got {article_count}"

        budget_count = (
            await session.execute(select(func.count()).where(SafetyBudget.tenant_id == tenant_id))
        ).scalar_one()
        assert (
            budget_count == 3
        ), f"Expected exactly 3 budgets after double-bootstrap, got {budget_count}"

        expense_count = (
            await session.execute(select(func.count()).where(BudgetExpense.tenant_id == tenant_id))
        ).scalar_one()
        assert (
            expense_count == 5
        ), f"Expected exactly 5 expenses after double-bootstrap, got {expense_count}"

        claim_count = (
            await session.execute(
                select(func.count()).where(BudgetReimbursement.tenant_id == tenant_id)
            )
        ).scalar_one()
        assert (
            claim_count == 3
        ), f"Expected exactly 3 reimbursement claims after double-bootstrap, got {claim_count}"

        item_count = (
            await session.execute(
                select(func.count()).where(BudgetReimbursementItem.tenant_id == tenant_id)
            )
        ).scalar_one()
        assert (
            item_count == 5
        ), f"Expected exactly 5 claim items after double-bootstrap, got {item_count}"

        feature_count = (
            await session.execute(select(func.count()).where(Feature.code == "budget"))
        ).scalar_one()
        assert feature_count == 1, f"Expected exactly 1 Feature(code='budget'), got {feature_count}"
