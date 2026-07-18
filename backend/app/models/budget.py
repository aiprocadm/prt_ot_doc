"""Бюджет безопасности §12.4 (срез-1): бюджеты доменов, статьи расходов, журнал расходов.

Инвариант (зеркало PPESafetyBudget): план персистентен, факт ВСЕГДА вычисляется из журнала
budget_expense (см. app/modules/budget/aggregation.py) и никогда не денормализуется.
Домены/типы — VARCHAR + whitelist в коде (НЕ PG-enum — конвенция ppe.py/medical.py).
СИЗ-домен здесь НЕ живёт: он остаётся в ppe_safety_budget (склад) и читается сводкой read-only.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import SoftDeleteMixin, TenantBaseModel

BUDGET_DOMAINS: tuple[str, ...] = ("training", "medical", "events")

# domain -> допустимый entity_type опциональной ссылки расхода на доменную запись
EXPENSE_ENTITY_TYPES: dict[str, str] = {
    "training": "training_session",  # app.models.training.TrainingSession
    "medical": "medical_exam",  # app.models.medical.MedicalExam
    "events": "corrective_action",  # app.models.safety_ops.CorrectiveAction
}


class SafetyBudget(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "safety_budget"
    __table_args__ = (Index("ix_safety_budget_tenant_domain", "tenant_id", "domain"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    planned_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class BudgetExpenseArticle(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "budget_expense_article"
    # unique БЕЗ deleted_at-фильтра: soft-deleted тёзка блокирует создание (прецедент rules_engine)
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_budget_expense_article_tenant_code"),
    )

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(32), nullable=True)  # NULL = универсальная
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class BudgetExpense(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "budget_expense"
    __table_args__ = (
        Index("ix_budget_expense_tenant_domain_occurred", "tenant_id", "domain", "occurred_on"),
    )

    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    article_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("budget_expense_article.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    company_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("company.id", ondelete="SET NULL"), nullable=True
    )
    branch_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("branch.id", ondelete="SET NULL"), nullable=True
    )
    site_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("site.id", ondelete="SET NULL"), nullable=True
    )
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # полиморфная, без FK
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
