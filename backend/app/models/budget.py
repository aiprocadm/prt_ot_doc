"""Бюджет безопасности §12.4: бюджеты доменов, статьи расходов, журнал расходов (срез-1)
и заявки на возмещение СФР со связью с расходами (срез-2).

Инвариант (зеркало PPESafetyBudget): план персистентен, факт ВСЕГДА вычисляется из журнала
budget_expense (см. app/modules/budget/aggregation.py) и никогда не денормализуется.
Домены/типы/статусы — VARCHAR + whitelist в коде (НЕ PG-enum — конвенция ppe.py/medical.py).
СИЗ-домен здесь НЕ живёт: он остаётся в ppe_safety_budget (склад) и читается сводкой read-only.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
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


class BudgetReimbursement(TenantBaseModel, SoftDeleteMixin):
    """Заявка на возмещение расходов из бюджета СФР (§12.4 срез-2).

    Статус — VARCHAR + FSM в app/modules/budget/reimbursement_lifecycle.py (НЕ PG-enum).
    Сумма заявки (requested_amount) вводится вручную и НЕ выводится из привязанных расходов:
    состав заявки может быть неполным на момент подачи, а СФР возмещает не весь чек.
    Фактически одобренная сумма — approved_amount (NULL до решения).
    """

    __tablename__ = "budget_reimbursement"
    __table_args__ = (Index("ix_budget_reimbursement_tenant_status", "tenant_id", "status"),)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    requested_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    approved_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(64), nullable=True)  # номер в СФР
    company_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("company.id", ondelete="SET NULL"), nullable=True
    )
    decision_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class BudgetReimbursementItem(TenantBaseModel, SoftDeleteMixin):
    """Строка состава заявки: ссылка на расход из журнала budget_expense.

    Сумма строки НЕ дублируется — она всегда читается из связанного расхода
    (инвариант «факт не денормализуется»). Unique БЕЗ фильтра deleted_at: снятый
    из заявки расход блокирует повторную привязку до жёсткой очистки (прецедент
    uq_budget_expense_article_tenant_code) — сервис снимает строку жёстким delete.
    """

    __tablename__ = "budget_reimbursement_item"
    __table_args__ = (
        UniqueConstraint(
            "reimbursement_id", "expense_id", name="uq_budget_reimbursement_item_pair"
        ),
        Index("ix_budget_reimbursement_item_tenant_claim", "tenant_id", "reimbursement_id"),
    )

    reimbursement_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("budget_reimbursement.id", ondelete="CASCADE"), nullable=False
    )
    expense_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("budget_expense.id", ondelete="CASCADE"), nullable=False
    )
