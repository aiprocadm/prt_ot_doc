"""CRUD бюджетов/статей/расходов. Факт здесь НЕ считается (см. aggregation.py).

Паттерн mirror'ит app/modules/ppe/budget.py (flush-only CRUD, effective-period merge
на update) и app/modules/rules_engine/service.py (класс-сервис с tenant_id, конфликт
уникальности статьи по коду через pre-check + IntegrityError race-guard). Сервис
НИЧЕГО не коммитит — коммит делает роутер (Task 6), здесь только flush/refresh.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.budget import BudgetExpenseArticle, SafetyBudget
from app.schemas.budget import (
    BudgetArticleCreate,
    BudgetArticleUpdate,
    SafetyBudgetCreate,
    SafetyBudgetUpdate,
)

__all__ = [
    "DEFAULT_ARTICLES",
    "BudgetNotFound",
    "ArticleNotFound",
    "ExpenseNotFound",
    "ArticleCodeConflict",
    "BudgetValidationError",
    "BudgetService",
]

# code, name, domain (None = универсальная статья, не привязана к домену)
DEFAULT_ARTICLES: tuple[tuple[str, str, str | None], ...] = (
    ("training_external", "Обучение в учебном центре", "training"),
    ("training_internal", "Внутреннее обучение", "training"),
    ("medical_periodic", "Периодические медосмотры", "medical"),
    ("medical_psychiatric", "Психиатрические освидетельствования", "medical"),
    ("events_capa", "Мероприятия по улучшению условий труда", "events"),
    ("sout", "Спецоценка условий труда", None),
    ("ppe_purchase", "Закупка СИЗ", None),
    ("services_external", "Услуги сторонних организаций", None),
    ("other", "Прочее", None),
)


class BudgetNotFound(Exception):
    def __init__(self, budget_id: str) -> None:
        super().__init__(f"safety budget not found: {budget_id}")
        self.budget_id = budget_id


class ArticleNotFound(Exception):
    def __init__(self, article_id: str) -> None:
        super().__init__(f"budget expense article not found: {article_id}")
        self.article_id = article_id


class ExpenseNotFound(Exception):
    def __init__(self, expense_id: str) -> None:
        super().__init__(f"budget expense not found: {expense_id}")
        self.expense_id = expense_id


class ArticleCodeConflict(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(f"budget expense article code already exists: {code}")
        self.code = code


class BudgetValidationError(Exception):
    def __init__(self, code: str, message: str = ""):
        self.code, self.message = code, message
        super().__init__(message or code)


class BudgetService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    # ------------------------------------------------------------------
    # budgets
    # ------------------------------------------------------------------

    def _budget_base(self):
        return select(SafetyBudget).where(
            SafetyBudget.tenant_id == self.tenant_id,
            SafetyBudget.deleted_at.is_(None),
        )

    async def _load_budget(self, budget_id: str) -> SafetyBudget:
        row = await self.session.scalar(self._budget_base().where(SafetyBudget.id == budget_id))
        if row is None:
            raise BudgetNotFound(budget_id)
        return row

    async def create_budget(self, payload: SafetyBudgetCreate) -> SafetyBudget:
        budget = SafetyBudget(tenant_id=self.tenant_id, **payload.model_dump())
        self.session.add(budget)
        await self.session.flush()
        await self.session.refresh(budget)
        return budget

    async def list_budgets(
        self, *, domain: str | None = None, limit: int = 100, offset: int = 0
    ) -> tuple[list[SafetyBudget], int]:
        stmt = self._budget_base()
        if domain is not None:
            stmt = stmt.where(SafetyBudget.domain == domain)
        total = int(
            await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        )
        rows = list(
            (
                await self.session.execute(
                    stmt.order_by(SafetyBudget.period_start.desc(), SafetyBudget.id)
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return rows, total

    async def get_budget(self, budget_id: str) -> SafetyBudget:
        return await self._load_budget(budget_id)

    async def update_budget(self, budget_id: str, payload: SafetyBudgetUpdate) -> SafetyBudget:
        """Partial PATCH; re-validates the merged period against stored+incoming values.

        A partial body carrying only one period bound has nothing to compare against
        on its own (Pydantic validates the request in isolation), so the effective
        range is re-checked here before applying the mutation — mirrors
        app/modules/ppe/budget.py::update_budget.
        """
        budget = await self._load_budget(budget_id)
        fields = payload.model_dump(exclude_unset=True)
        effective_start = fields.get("period_start", budget.period_start)
        effective_end = fields.get("period_end", budget.period_end)
        if effective_end < effective_start:
            raise BudgetValidationError("period_invalid", "period_end must be >= period_start")
        for key, value in fields.items():
            setattr(budget, key, value)
        await self.session.flush()
        await self.session.refresh(budget)
        return budget

    async def delete_budget(self, budget_id: str) -> None:
        budget = await self._load_budget(budget_id)
        budget.deleted_at = datetime.now(timezone.utc)
        await self.session.flush()

    # ------------------------------------------------------------------
    # articles
    # ------------------------------------------------------------------

    def _article_base(self):
        return select(BudgetExpenseArticle).where(
            BudgetExpenseArticle.tenant_id == self.tenant_id,
            BudgetExpenseArticle.deleted_at.is_(None),
        )

    async def _load_article(self, article_id: str) -> BudgetExpenseArticle:
        row = await self.session.scalar(
            self._article_base().where(BudgetExpenseArticle.id == article_id)
        )
        if row is None:
            raise ArticleNotFound(article_id)
        return row

    async def _ensure_code_free(self, code: str) -> None:
        # Осознанно БЕЗ фильтра deleted_at: soft-deleted тёзка блокирует создание
        # (unique-constraint uq_budget_expense_article_tenant_code тоже её видит).
        existing = await self.session.scalar(
            select(BudgetExpenseArticle.id)
            .where(
                BudgetExpenseArticle.tenant_id == self.tenant_id,
                BudgetExpenseArticle.code == code,
            )
            .limit(1)
        )
        if existing is not None:
            raise ArticleCodeConflict(code)

    async def create_article(self, payload: BudgetArticleCreate) -> BudgetExpenseArticle:
        await self._ensure_code_free(payload.code)
        article = BudgetExpenseArticle(tenant_id=self.tenant_id, **payload.model_dump())
        self.session.add(article)
        try:
            await self.session.flush()
        except IntegrityError as exc:  # гонка параллельных create — паттерн rules_engine
            await self.session.rollback()
            raise ArticleCodeConflict(payload.code) from exc
        await self.session.refresh(article)
        return article

    async def list_articles(
        self, *, limit: int = 200, offset: int = 0
    ) -> tuple[list[BudgetExpenseArticle], int]:
        # is_active НЕ фильтруется здесь — неактивные статьи видны в справочнике,
        # чтобы старые расходы могли на них ссылаться; UI решает, что показывать.
        stmt = self._article_base()
        total = int(
            await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        )
        rows = list(
            (
                await self.session.execute(
                    stmt.order_by(BudgetExpenseArticle.code).limit(limit).offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return rows, total

    async def update_article(
        self, article_id: str, payload: BudgetArticleUpdate
    ) -> BudgetExpenseArticle:
        article = await self._load_article(article_id)
        fields = payload.model_dump(exclude_unset=True)
        for key, value in fields.items():
            setattr(article, key, value)
        await self.session.flush()
        await self.session.refresh(article)
        return article

    async def delete_article(self, article_id: str) -> None:
        article = await self._load_article(article_id)
        article.deleted_at = datetime.now(timezone.utc)
        await self.session.flush()

    async def seed_default_articles(self) -> tuple[int, int]:
        """Insert the DEFAULT_ARTICLES catalog for this tenant; existing codes are kept as-is.

        A single membership query (no ``deleted_at`` filter — a soft-deleted default
        counts as "already seeded", it is not silently resurrected) decides what is
        missing; a pre-existing custom article sharing a default code is never
        overwritten.
        """
        existing_codes = set(
            (
                await self.session.execute(
                    select(BudgetExpenseArticle.code).where(
                        BudgetExpenseArticle.tenant_id == self.tenant_id
                    )
                )
            )
            .scalars()
            .all()
        )
        created = 0
        for code, name, domain in DEFAULT_ARTICLES:
            if code in existing_codes:
                continue
            self.session.add(
                BudgetExpenseArticle(
                    tenant_id=self.tenant_id, code=code, name=name, domain=domain
                )
            )
            created += 1
        await self.session.flush()
        skipped = len(DEFAULT_ARTICLES) - created
        return created, skipped
