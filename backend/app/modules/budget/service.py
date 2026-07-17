"""CRUD бюджетов/статей/расходов. Факт здесь НЕ считается (см. aggregation.py).

Паттерн mirror'ит app/modules/ppe/budget.py (flush-only CRUD, effective-period merge
на update) и app/modules/rules_engine/service.py (класс-сервис с tenant_id, конфликт
уникальности статьи по коду через pre-check + IntegrityError race-guard). Сервис
НИЧЕГО не коммитит — коммит делает роутер (Task 6), здесь только flush/refresh.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.budget import (
    BudgetExpense,
    BudgetExpenseArticle,
    EXPENSE_ENTITY_TYPES,
    SafetyBudget,
)
from app.models.master_data import Branch, Company, Site
from app.models.medical import MedicalExam
from app.models.safety_ops import CorrectiveAction
from app.models.training import TrainingSession
from app.schemas.budget import (
    BudgetArticleCreate,
    BudgetArticleUpdate,
    BudgetExpenseCreate,
    BudgetExpenseUpdate,
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

# entity_type -> polymorphic target model for BudgetExpense.entity_id (see
# app.models.budget.EXPENSE_ENTITY_TYPES for the domain -> entity_type mapping).
# TrainingSession has NO SoftDeleteMixin — the deleted_at filter below is applied
# conditionally via hasattr, not unconditionally.
_ENTITY_MODELS: dict[str, type] = {
    "training_session": TrainingSession,
    "medical_exam": MedicalExam,
    "corrective_action": CorrectiveAction,
}
# Map-parity pin: every entity_type reachable via EXPENSE_ENTITY_TYPES must have a
# model here (and vice versa) — a new domain added in models without wiring the
# validator would otherwise KeyError at request time instead of failing at import.
assert set(EXPENSE_ENTITY_TYPES.values()) == set(_ENTITY_MODELS)

# Fields that must never be explicitly nulled via PATCH (rules_engine convention:
# a client-supplied `null` on a non-nullable business field is a validation error,
# not a silent no-op / TypeError at flush time). Keyed per update schema.
_BUDGET_NON_NULLABLE = frozenset({"name", "period_start", "period_end", "planned_amount"})
_ARTICLE_NON_NULLABLE = frozenset({"name", "is_active"})
_EXPENSE_NON_NULLABLE = frozenset({"title", "occurred_on", "amount"})


def _reject_explicit_nulls(fields: dict, non_nullable: frozenset[str]) -> None:
    for key in non_nullable & fields.keys():
        if fields[key] is None:
            raise BudgetValidationError("invalid_field_null", f"Field '{key}' cannot be null")


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
        _reject_explicit_nulls(fields, _BUDGET_NON_NULLABLE)
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
            # rollback() откатывает ВСЮ транзакцию запроса, а не только этот flush —
            # вызывающий код не может продолжить работу с session в той же транзакции
            # после этого except (никаких доп. операций catch-and-continue здесь и выше).
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
        _reject_explicit_nulls(fields, _ARTICLE_NON_NULLABLE)
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

    # ------------------------------------------------------------------
    # expenses
    # ------------------------------------------------------------------

    def _expense_base(self):
        return select(BudgetExpense).where(
            BudgetExpense.tenant_id == self.tenant_id,
            BudgetExpense.deleted_at.is_(None),
        )

    async def _load_expense(self, expense_id: str) -> BudgetExpense:
        row = await self.session.scalar(
            self._expense_base().where(BudgetExpense.id == expense_id)
        )
        if row is None:
            raise ExpenseNotFound(expense_id)
        return row

    async def _validate_expense_refs(
        self,
        *,
        article_id: str | None,
        company_id: str | None,
        branch_id: str | None,
        site_id: str | None,
        entity_type: str | None,
        entity_id: str | None,
        domain: str,
        check_article_active: bool,
    ) -> None:
        """Tenant-scoped existence/consistency checks for every non-None reference.

        Each ref is checked with its own ``select`` (no join fan-out); callers pass
        the values that will actually be persisted (either the create payload as-is,
        or the update's merged stored+incoming values — see update_expense).
        """
        if article_id is not None:
            row = (
                await self.session.execute(
                    select(BudgetExpenseArticle.is_active, BudgetExpenseArticle.domain).where(
                        BudgetExpenseArticle.tenant_id == self.tenant_id,
                        BudgetExpenseArticle.id == article_id,
                        BudgetExpenseArticle.deleted_at.is_(None),
                    )
                )
            ).first()
            if row is None:
                raise BudgetValidationError("unknown_article", f"unknown article: {article_id}")
            is_active, article_domain = row
            if check_article_active and not is_active:
                raise BudgetValidationError(
                    "article_inactive", f"article is inactive: {article_id}"
                )
            if article_domain not in (None, domain):
                raise BudgetValidationError(
                    "article_domain_mismatch",
                    f"article domain {article_domain!r} does not match expense domain "
                    f"{domain!r}",
                )

        if company_id is not None:
            exists = await self.session.scalar(
                select(Company.id).where(
                    Company.tenant_id == self.tenant_id,
                    Company.id == company_id,
                    Company.deleted_at.is_(None),
                )
            )
            if exists is None:
                raise BudgetValidationError("unknown_company", f"unknown company: {company_id}")

        if branch_id is not None:
            exists = await self.session.scalar(
                select(Branch.id).where(
                    Branch.tenant_id == self.tenant_id,
                    Branch.id == branch_id,
                    Branch.deleted_at.is_(None),
                )
            )
            if exists is None:
                raise BudgetValidationError("unknown_branch", f"unknown branch: {branch_id}")

        if site_id is not None:
            exists = await self.session.scalar(
                select(Site.id).where(
                    Site.tenant_id == self.tenant_id,
                    Site.id == site_id,
                    Site.deleted_at.is_(None),
                )
            )
            if exists is None:
                raise BudgetValidationError("unknown_site", f"unknown site: {site_id}")

        if entity_type is not None:
            expected_type = EXPENSE_ENTITY_TYPES.get(domain)
            if entity_type != expected_type:
                raise BudgetValidationError(
                    "invalid_entity_type",
                    f"entity_type {entity_type!r} is not valid for domain {domain!r}",
                )
            model = _ENTITY_MODELS[entity_type]
            stmt = select(model.id).where(
                model.tenant_id == self.tenant_id, model.id == entity_id
            )
            if hasattr(model, "deleted_at"):
                stmt = stmt.where(model.deleted_at.is_(None))
            exists = await self.session.scalar(stmt)
            if exists is None:
                raise BudgetValidationError(
                    "unknown_entity", f"unknown entity: {entity_type}:{entity_id}"
                )

    async def create_expense(self, payload: BudgetExpenseCreate) -> BudgetExpense:
        await self._validate_expense_refs(
            article_id=payload.article_id,
            company_id=payload.company_id,
            branch_id=payload.branch_id,
            site_id=payload.site_id,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            domain=payload.domain,
            check_article_active=True,
        )
        expense = BudgetExpense(tenant_id=self.tenant_id, **payload.model_dump())
        self.session.add(expense)
        await self.session.flush()
        await self.session.refresh(expense)
        return expense

    async def list_expenses(
        self,
        *,
        domain: str | None = None,
        article_id: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        company_id: str | None = None,
        branch_id: str | None = None,
        site_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[tuple[BudgetExpense, str | None]], int]:
        filters = [
            BudgetExpense.tenant_id == self.tenant_id,
            BudgetExpense.deleted_at.is_(None),
        ]
        if domain is not None:
            filters.append(BudgetExpense.domain == domain)
        if article_id is not None:
            filters.append(BudgetExpense.article_id == article_id)
        if date_from is not None:
            filters.append(BudgetExpense.occurred_on >= date_from)
        if date_to is not None:
            filters.append(BudgetExpense.occurred_on <= date_to)
        if company_id is not None:
            filters.append(BudgetExpense.company_id == company_id)
        if branch_id is not None:
            filters.append(BudgetExpense.branch_id == branch_id)
        if site_id is not None:
            filters.append(BudgetExpense.site_id == site_id)

        total = int(
            await self.session.scalar(
                select(func.count()).select_from(BudgetExpense).where(*filters)
            )
            or 0
        )
        rows = (
            await self.session.execute(
                # outerjoin WITHOUT a deleted_at filter on the article: historical
                # expenses deliberately keep showing the name of a soft-deleted article.
                select(BudgetExpense, BudgetExpenseArticle.name)
                .outerjoin(
                    BudgetExpenseArticle, BudgetExpenseArticle.id == BudgetExpense.article_id
                )
                .where(*filters)
                .order_by(BudgetExpense.occurred_on.desc(), BudgetExpense.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return [(row[0], row[1]) for row in rows], total

    async def update_expense(
        self, expense_id: str, payload: BudgetExpenseUpdate
    ) -> BudgetExpense:
        expense = await self._load_expense(expense_id)
        fields = payload.model_dump(exclude_unset=True)
        _reject_explicit_nulls(fields, _EXPENSE_NON_NULLABLE)

        merged_entity_type = fields.get("entity_type", expense.entity_type)
        merged_entity_id = fields.get("entity_id", expense.entity_id)

        # A PATCH may clear only one side of the entity_type/entity_id pair (e.g.
        # {"entity_type": null} alone) — the schema validates each request in
        # isolation and cannot see the stored counterpart, so the merged pairing is
        # re-checked here before touching refs/row (mirrors update_budget's merged
        # period re-check). Always on merged values, regardless of which side was sent.
        if (merged_entity_type is None) != (merged_entity_id is None):
            raise BudgetValidationError(
                "invalid_entity_link", "entity_type and entity_id must be set together"
            )

        # Revalidate ONLY the refs this PATCH touches: a stored ref whose target was
        # later soft-deleted (or whose article domain drifted) must not make the
        # expense uneditable via an unrelated update (e.g. title/amount-only PATCH).
        # The entity pair participates if EITHER side is in fields — then the MERGED
        # pair is validated as a whole.
        # fields.get(key) is None both for an untouched key and for an explicit
        # null (= clearing the ref) — neither needs validation.
        touch_entity = "entity_type" in fields or "entity_id" in fields
        await self._validate_expense_refs(
            article_id=fields.get("article_id"),
            company_id=fields.get("company_id"),
            branch_id=fields.get("branch_id"),
            site_id=fields.get("site_id"),
            entity_type=merged_entity_type if touch_entity else None,
            entity_id=merged_entity_id if touch_entity else None,
            domain=expense.domain,
            check_article_active=True,
        )

        for key, value in fields.items():
            setattr(expense, key, value)
        await self.session.flush()
        await self.session.refresh(expense)
        return expense

    async def delete_expense(self, expense_id: str) -> None:
        expense = await self._load_expense(expense_id)
        expense.deleted_at = datetime.now(timezone.utc)
        await self.session.flush()
