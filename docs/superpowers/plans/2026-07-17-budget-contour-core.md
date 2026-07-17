# Бюджет безопасности §12.4 срез-1 (ядро) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Кросс-доменный контур «Бюджет безопасности»: бюджеты обучения/медосмотров/мероприятий,
справочник статей расходов, журнал фактических расходов, план↔факт (включая СИЗ read-only) и
breakdown-аналитика по статьям/доменам/компаниям/филиалам/объектам.

**Architecture:** Новый модуль `backend/app/modules/budget/` + модели `backend/app/models/budget.py`
(3 таблицы, миграция `bg01` от head `re01`, без PG-enum). План персистентен, факт ВСЕГДА вычисляется
из журнала `budget_expense`; СИЗ-домен в сводке читается read-only из `ppe_safety_budget` +
`compute_budget_actual` (склад). Фронт — страница `/budget` с 4 вкладками за флагом `budget`
(default-off). Spec: `docs/superpowers/specs/2026-07-17-budget-contour-core-design.md`.

**Tech Stack:** FastAPI / SQLAlchemy async / Alembic / Pydantic v2 / React 18 + Radix + vitest.

**Рабочая среда:** изолированный worktree `tz-continuation-d43adc`, ветка
`claude/tz-continuation-d43adc` от `main`@`bbf8e628`. Коммиты атомарные `git commit -- <paths>`.

**Запуск backend-тестов (память проекта):** PowerShell, `$env:PYTHONPATH="backend"`, батчи ≤5
файлов, timeout 600000 мс ОДИН раз (холодный импорт минуты, НЕ перезапускать), вывод в лог-файл +
`EXIT=$LASTEXITCODE`; при зависании на импорте — добавить `-p magic_stub` (памятка
windows-pytest-magic-import-hang). Python: `.venv` главного дерева (Py3.12.10) либо `py -3.12`;
если только 3.13 — допустимый fallback (CLAUDE.md). Пример:

```powershell
$env:PYTHONPATH="backend"
python -m pytest tests/api/test_budget_service.py -p no:schemathesis -q 2>&1 | Tee-Object buildlog.txt; "EXIT=$LASTEXITCODE"
```

**Эталонные файлы (читать перед соответствующей задачей):**
- Модель/миграция/сервис/тесты бюджета-эталона: `backend/app/models/ppe.py:119`,
  `backend/app/migrations/versions/20260705_wa09_ppe_safety_budget.py`,
  `backend/app/modules/ppe/budget.py`, `tests/api/test_ppe_budget_*.py` (5 файлов).
- API-конвенции (FeatureGate/_audit/ETag/статические-пути-до-`{id}`):
  `backend/app/modules/rules_engine/api.py`.
- Регистрация роутера: `backend/app/api/v1/route_groups.py:85,188`.
- Demo-сид: `backend/app/services/demo_bootstrap.py` (`_seed_committees_demo` ~610 — флаг;
  `_seed_report_builder_demo` ~823 — идемпотентность).
- Breakdown-конвенции: `backend/app/modules/analytics/breakdown.py`.
- Фронт-регистрация: `frontend/src/router/pageRegistry.tsx:73`,
  `frontend/src/router/routeGroups.tsx:244`, `frontend/src/router/navigationConfig.ts:133`,
  `frontend/src/router/navVisibility.ts`, `frontend/src/permissions/permissions.ts`.
- Фронт-страница/диалоги/api: `frontend/src/pages/rules/RulesPage.tsx`,
  `frontend/src/api/rules.ts`, `frontend/src/api/warehouse.ts` (budget-методы).

---

### Task 1: Модели + миграция `bg01`

**Files:**
- Create: `backend/app/models/budget.py`
- Modify: `backend/app/models/models.py` (re-export блок в конце, зеркало блока `# P10-10 re01`)
- Create: `backend/app/migrations/versions/20260717_bg01_safety_budget_core.py`
- Test: `tests/api/test_budget_model.py`

- [ ] **Step 1: Написать падающий тест** (обвязка/фикстуры — скопировать из
  `tests/api/test_ppe_budget_model.py`; там же посмотреть, как создаётся session/tenant через
  `metadata.create_all`):

```python
import pytest
from sqlalchemy import select

from app.models.budget import (
    BUDGET_DOMAINS,
    EXPENSE_ENTITY_TYPES,
    BudgetExpense,
    BudgetExpenseArticle,
    SafetyBudget,
)


def test_domain_whitelist_constants():
    assert BUDGET_DOMAINS == ("training", "medical", "events")
    assert EXPENSE_ENTITY_TYPES == {
        "training": "training_session",
        "medical": "medical_exam",
        "events": "corrective_action",
    }


@pytest.mark.asyncio
async def test_budget_roundtrip(session, tenant_id):  # имена фикстур — как в test_ppe_budget_model
    budget = SafetyBudget(
        tenant_id=tenant_id, name="Бюджет обучения 2026", domain="training",
        period_start=date(2026, 1, 1), period_end=date(2026, 12, 31),
        planned_amount=500000, notes=None,
    )
    session.add(budget)
    await session.flush()
    row = (await session.execute(select(SafetyBudget))).scalar_one()
    assert row.domain == "training" and float(row.planned_amount) == 500000.0


@pytest.mark.asyncio
async def test_article_unique_code_per_tenant(session, tenant_id):
    session.add(BudgetExpenseArticle(tenant_id=tenant_id, code="other", name="Прочее"))
    await session.flush()
    session.add(BudgetExpenseArticle(tenant_id=tenant_id, code="other", name="Дубль"))
    with pytest.raises(IntegrityError):
        await session.flush()


@pytest.mark.asyncio
async def test_expense_roundtrip_with_nullable_dims(session, tenant_id):
    exp = BudgetExpense(
        tenant_id=tenant_id, domain="events", title="Ремонт вентиляции",
        occurred_on=date(2026, 3, 10), amount=120000,
    )
    session.add(exp)
    await session.flush()
    row = (await session.execute(select(BudgetExpense))).scalar_one()
    assert row.article_id is None and row.site_id is None and row.entity_type is None
```

- [ ] **Step 2: Прогнать — убедиться, что падает** (`ImportError: app.models.budget`).

- [ ] **Step 3: Реализовать `backend/app/models/budget.py`** (полный файл):

```python
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
    "training": "training_session",     # app.models.training.TrainingSession
    "medical": "medical_exam",          # app.models.medical.MedicalExam
    "events": "corrective_action",      # app.models.safety_ops.CorrectiveAction
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
```

В конец `backend/app/models/models.py` (после блока `# P10-10 re01`) добавить re-export
(регистрирует таблицы в metadata для `metadata.create_all` в тестах):

```python
# §12.4 bg01: re-export budget models from app.models.budget.
from app.models.budget import (  # noqa: E402
    BudgetExpense,
    BudgetExpenseArticle,
    SafetyBudget,
)
```

и дописать три имени в `__all__`, если он есть в файле (проверить).

- [ ] **Step 4: Написать миграцию** `backend/app/migrations/versions/20260717_bg01_safety_budget_core.py`
  (полный файл; колоночный шаблон — точное зеркало wa09):

```python
"""safety budget core §12.4 срез-1: budgets + expense articles + expense journal.

Additive: 3 new tables (safety_budget, budget_expense_article, budget_expense).
No data backfill, no enum (domains are VARCHAR + code whitelist). Chains off re01.
Honest downgrade: drops in FK-safe order (expense -> budget -> article).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260717_bg01_safety_budget_core"
down_revision = "20260715_re01_automation_rules"
branch_labels = None
depends_on = None


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "budget_expense_article",
        *_base_columns(),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=32), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_budget_expense_article_tenant_code"),
    )
    op.create_index(
        op.f("ix_budget_expense_article_tenant_id"), "budget_expense_article", ["tenant_id"]
    )

    op.create_table(
        "safety_budget",
        *_base_columns(),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=32), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("planned_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_safety_budget_tenant_id"), "safety_budget", ["tenant_id"])
    op.create_index("ix_safety_budget_tenant_domain", "safety_budget", ["tenant_id", "domain"])

    op.create_table(
        "budget_expense",
        *_base_columns(),
        sa.Column("domain", sa.String(length=32), nullable=False),
        sa.Column("article_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=True),
        sa.Column("branch_id", sa.String(length=36), nullable=True),
        sa.Column("site_id", sa.String(length=36), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.String(length=36), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(
            ["article_id"], ["budget_expense_article.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["branch_id"], ["branch.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_budget_expense_tenant_id"), "budget_expense", ["tenant_id"])
    op.create_index(
        "ix_budget_expense_tenant_domain_occurred",
        "budget_expense",
        ["tenant_id", "domain", "occurred_on"],
    )


def downgrade() -> None:
    op.drop_index("ix_budget_expense_tenant_domain_occurred", table_name="budget_expense")
    op.drop_index(op.f("ix_budget_expense_tenant_id"), table_name="budget_expense")
    op.drop_table("budget_expense")
    op.drop_index("ix_safety_budget_tenant_domain", table_name="safety_budget")
    op.drop_index(op.f("ix_safety_budget_tenant_id"), table_name="safety_budget")
    op.drop_table("safety_budget")
    op.drop_index(op.f("ix_budget_expense_article_tenant_id"), table_name="budget_expense_article")
    op.drop_table("budget_expense_article")
```

Перед сохранением сверить: (a) единственный alembic head — `20260715_re01_automation_rules`
(`grep down_revision` по versions/ не должен найти ссылок на bg01-конкурентов); (b) точные
`__tablename__` FK-целей: `company`/`branch`/`site` (в `master_data.py`: Company — авто-имя
`company`, Branch:212 `branch`, Site:233 `site`).

- [ ] **Step 5: Прогнать тест — зелёный**; также smoke-импорт:
  `python -c "from app.models.budget import SafetyBudget"` (с `PYTHONPATH=backend`).

- [ ] **Step 6: Commit:**
  `git add backend/app/models/budget.py backend/app/models/models.py backend/app/migrations/versions/20260717_bg01_safety_budget_core.py tests/api/test_budget_model.py && git commit -m "feat(budget): models + bg01 migration (safety_budget, articles, expenses)"`

---

### Task 2: Pydantic-схемы

**Files:**
- Create: `backend/app/schemas/budget.py`
- Test: `tests/api/test_budget_schema.py`

- [ ] **Step 1: Падающий тест** (обвязка — зеркало `tests/api/test_ppe_budget_schema.py`):

```python
import pytest
from pydantic import ValidationError

from app.schemas.budget import (
    BudgetExpenseCreate,
    SafetyBudgetCreate,
    SafetyBudgetUpdate,
)


def test_budget_period_inversion_rejected():
    with pytest.raises(ValidationError):
        SafetyBudgetCreate(name="x", domain="training",
                           period_start=date(2026, 5, 1), period_end=date(2026, 4, 1),
                           planned_amount=1)


def test_budget_domain_whitelist():
    with pytest.raises(ValidationError):
        SafetyBudgetCreate(name="x", domain="ppe",  # СИЗ ведётся на складе, не здесь
                           period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
                           planned_amount=1)


def test_expense_amount_must_be_positive():
    with pytest.raises(ValidationError):
        BudgetExpenseCreate(domain="events", title="x", occurred_on=date(2026, 1, 1), amount=0)


def test_update_partial_keeps_unset():
    upd = SafetyBudgetUpdate(planned_amount=10)
    assert "name" not in upd.model_dump(exclude_unset=True)
```

- [ ] **Step 2: Прогнать — ImportError.**

- [ ] **Step 3: Реализовать `backend/app/schemas/budget.py`.** База — `BaseSchema` из
  `app.schemas.base` (ORM-mode; посмотреть, как её используют `PPESafetyBudget*`-схемы в
  `backend/app/schemas/ppe.py:98-157`, включая `model_validator` периода — скопировать стиль):

```python
"""Схемы бюджетного контура §12.4 (срез-1)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field, model_validator

from app.models.budget import BUDGET_DOMAINS
from app.schemas.base import BaseSchema


def _check_period(values):
    if values.period_end < values.period_start:
        raise ValueError("period_end must be >= period_start")
    return values


class SafetyBudgetCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=255)
    domain: str
    period_start: date
    period_end: date
    planned_amount: float = Field(ge=0)
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _validate(self):
        if self.domain not in BUDGET_DOMAINS:
            raise ValueError(f"unknown domain: {self.domain}")
        return _check_period(self)


class SafetyBudgetUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    period_start: date | None = None
    period_end: date | None = None
    planned_amount: float | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=1000)
    # domain намеренно НЕ обновляется (перенос бюджета между доменами = удалить+создать)


class SafetyBudgetRead(BaseSchema):
    id: str
    name: str
    domain: str
    period_start: date
    period_end: date
    planned_amount: float
    notes: str | None


class SafetyBudgetPage(BaseSchema):
    items: list[SafetyBudgetRead]
    total: int
    limit: int
    offset: int


class BudgetArticleActualRead(BaseSchema):
    article_id: str | None
    article_name: str          # "— без статьи" для NULL
    amount: float


class SafetyBudgetDetail(SafetyBudgetRead):
    actual_total: float
    remaining: float           # planned - actual; отрицательный = перерасход
    expense_count: int
    by_article: list[BudgetArticleActualRead]


class BudgetArticleCreate(BaseSchema):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    domain: str | None = None      # NULL = универсальная
    is_active: bool = True

    @model_validator(mode="after")
    def _validate(self):
        if self.domain is not None and self.domain not in BUDGET_DOMAINS:
            raise ValueError(f"unknown domain: {self.domain}")
        return self


class BudgetArticleUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    domain: str | None = None
    is_active: bool | None = None
    # code иммутабелен (ключ уникальности/сида)


class BudgetArticleRead(BaseSchema):
    id: str
    code: str
    name: str
    domain: str | None
    is_active: bool


class BudgetArticlePage(BaseSchema):
    items: list[BudgetArticleRead]
    total: int
    limit: int
    offset: int


class BudgetSeedResult(BaseSchema):
    created: int
    skipped: int


class BudgetExpenseCreate(BaseSchema):
    domain: str
    article_id: str | None = None
    title: str = Field(min_length=1, max_length=255)
    occurred_on: date
    amount: float = Field(gt=0)
    company_id: str | None = None
    branch_id: str | None = None
    site_id: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _validate(self):
        if self.domain not in BUDGET_DOMAINS:
            raise ValueError(f"unknown domain: {self.domain}")
        if (self.entity_id is None) != (self.entity_type is None):
            raise ValueError("entity_type and entity_id must be provided together")
        return self


class BudgetExpenseUpdate(BaseSchema):
    article_id: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    occurred_on: date | None = None
    amount: float | None = Field(default=None, gt=0)
    company_id: str | None = None
    branch_id: str | None = None
    site_id: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    notes: str | None = Field(default=None, max_length=1000)
    # domain иммутабелен (перенос расхода между доменами = удалить+создать)


class BudgetExpenseRead(BaseSchema):
    id: str
    domain: str
    article_id: str | None
    article_name: str | None       # outerjoin в сервисе
    title: str
    occurred_on: date
    amount: float
    company_id: str | None
    branch_id: str | None
    site_id: str | None
    entity_type: str | None
    entity_id: str | None
    notes: str | None


class BudgetExpensePage(BaseSchema):
    items: list[BudgetExpenseRead]
    total: int
    limit: int
    offset: int


class BudgetOverviewBudgetRow(BaseSchema):
    id: str
    name: str
    period_start: date
    period_end: date
    planned_amount: float
    actual_own_period: float
    remaining: float


class BudgetOverviewDomain(BaseSchema):
    domain: str                    # training|medical|events|ppe
    read_only: bool                # True только для ppe
    planned: float
    actual: float
    remaining: float
    warning_unpriced_receipts: int | None = None   # только ppe
    budgets: list[BudgetOverviewBudgetRow]


class BudgetOverviewResponse(BaseSchema):
    generated_at: datetime
    date_from: date
    date_to: date
    domains: list[BudgetOverviewDomain]


class BudgetBreakdownItem(BaseSchema):
    id: str                        # "" = None-bucket «— без привязки»/«— без статьи»
    name: str
    amount: float


class BudgetBreakdownResponse(BaseSchema):
    dimension: str
    date_from: date
    date_to: date
    total: int                     # строк ДО cap 200
    items: list[BudgetBreakdownItem]
```

- [ ] **Step 4: Прогнать тест — зелёный.**

- [ ] **Step 5: Commit:** `git add backend/app/schemas/budget.py tests/api/test_budget_schema.py && git commit -m "feat(budget): pydantic schemas"`

---

### Task 3: Сервис — бюджеты + статьи + seed-defaults

**Files:**
- Create: `backend/app/modules/budget/__init__.py` (пустой)
- Create: `backend/app/modules/budget/service.py`
- Test: `tests/api/test_budget_service.py`

- [ ] **Step 1: Падающие тесты** (обвязка — зеркало `tests/api/test_ppe_budget_service.py`).
  Покрыть (полные тест-функции писать по этим спецификациям, каждая — отдельный тест):
  - create/get/list бюджетов: list фильтрует по `domain`, сортировка `period_start desc`,
    пагинация limit/offset + total; tenant-изоляция (чужой tenant_id → `BudgetNotFound`).
  - update: allowlist (name/period_start/period_end/planned_amount/notes), partial PATCH с
    повторной валидацией периода на merged stored+incoming (передать только `period_end` раньше
    stored `period_start` → `BudgetValidationError("period_invalid")`).
  - soft-delete: строка исчезает из list/get, `deleted_at` проставлен.
  - Статьи: create (дубль кода → `ArticleCodeConflict`, В Т.Ч. если тёзка soft-deleted — пин-тест);
    update не меняет code; list с `include_inactive=True` по умолчанию.
  - `seed_default_articles()`: первый вызов `created=9, skipped=0`; второй — `created=0, skipped=9`;
    существующая кастомная статья не перезаписывается.

Пример двух ключевых тестов:

```python
@pytest.mark.asyncio
async def test_seed_default_articles_idempotent(session, tenant_id):
    svc = BudgetService(session, tenant_id)
    created, skipped = await svc.seed_default_articles()
    assert (created, skipped) == (9, 0)
    created2, skipped2 = await svc.seed_default_articles()
    assert (created2, skipped2) == (0, 9)


@pytest.mark.asyncio
async def test_article_code_conflict_includes_soft_deleted(session, tenant_id):
    svc = BudgetService(session, tenant_id)
    art = await svc.create_article(BudgetArticleCreate(code="x1", name="Статья"))
    await svc.delete_article(art.id)
    with pytest.raises(ArticleCodeConflict):
        await svc.create_article(BudgetArticleCreate(code="x1", name="Тёзка"))
```

- [ ] **Step 2: Прогнать — ImportError.**

- [ ] **Step 3: Реализовать `service.py`.** Контракты:

```python
"""CRUD бюджетов/статей/расходов. Факт здесь НЕ считается (см. aggregation.py)."""

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


class BudgetNotFound(Exception): ...
class ArticleNotFound(Exception): ...
class ExpenseNotFound(Exception): ...
class ArticleCodeConflict(Exception): ...


class BudgetValidationError(Exception):
    def __init__(self, code: str, message: str = ""):
        self.code, self.message = code, message
        super().__init__(message or code)


class BudgetService:
    def __init__(self, session: AsyncSession, tenant_id: str): ...

    # budgets
    async def create_budget(self, payload: SafetyBudgetCreate) -> SafetyBudget
    async def list_budgets(self, *, domain: str | None = None, limit: int, offset: int) -> tuple[list[SafetyBudget], int]
    async def get_budget(self, budget_id: str) -> SafetyBudget          # not found/cross-tenant/deleted -> BudgetNotFound
    async def update_budget(self, budget_id: str, payload: SafetyBudgetUpdate) -> SafetyBudget
    async def delete_budget(self, budget_id: str) -> None               # soft
    # articles
    async def create_article(self, payload: BudgetArticleCreate) -> BudgetExpenseArticle
    async def list_articles(self, *, limit: int, offset: int) -> tuple[list[BudgetExpenseArticle], int]
    async def update_article(self, article_id: str, payload: BudgetArticleUpdate) -> BudgetExpenseArticle
    async def delete_article(self, article_id: str) -> None             # soft
    async def seed_default_articles(self) -> tuple[int, int]            # (created, skipped)
```

Детали реализации:
- Все запросы `where(Model.tenant_id == self.tenant_id)`; для list/get дополнительно
  `deleted_at.is_(None)`.
- `update_budget`: применять только `payload.model_dump(exclude_unset=True)`; после merge
  проверить `period_end >= period_start` (stored+incoming) → иначе
  `BudgetValidationError("period_invalid")`.
- `create_article`: пре-чек `select(...).where(tenant_id, code)` **БЕЗ** deleted_at-фильтра →
  `ArticleCodeConflict`; плюс перехват `IntegrityError` на flush → тоже `ArticleCodeConflict`
  (гонка).
- `seed_default_articles`: `select` существующих code одним запросом (без deleted_at-фильтра),
  добавлять недостающие из `DEFAULT_ARTICLES`; вернуть `(created, skipped)`.

- [ ] **Step 4: Прогнать — зелёный.**

- [ ] **Step 5: Commit:** `git add backend/app/modules/budget/ tests/api/test_budget_service.py && git commit -m "feat(budget): service — budgets + articles CRUD + seed-defaults"`

---

### Task 4: Сервис — расходы + tenant-валидация FK/entity

**Files:**
- Modify: `backend/app/modules/budget/service.py`
- Test: `tests/api/test_budget_expense_service.py`

- [ ] **Step 1: Падающие тесты.** Обвязка — как в Task 3; для company/branch/site использовать
  фабрики/ORM master-data (посмотреть, как соседние тесты создают `Company`/`Site`;
  `Branch(tenant_id, company_id, name)` — `app.models.master_data`). Покрыть:
  - create/list/update/delete расхода happy-path; list-фильтры: `domain`, `article_id`,
    `date_from/date_to` (обе границы включительно по `occurred_on`), `company_id`, `branch_id`,
    `site_id`; сортировка `occurred_on desc`; `article_name` в Read через outerjoin.
  - Каждый client-supplied FK чужого tenant'а или несуществующий → `BudgetValidationError` с
    кодом: `unknown_article` / `unknown_company` / `unknown_branch` / `unknown_site`.
  - `article_domain_mismatch`: статья `domain="training"` в расходе `domain="events"` → ошибка;
    универсальная статья (`domain=None`) — проходит в любом домене.
  - `article_inactive`: `is_active=False` → ошибка при create (при update, если article_id не
    меняется — не проверять повторно).
  - entity-ссылка: `invalid_entity_type` (тип не соответствует `EXPENSE_ENTITY_TYPES[domain]`);
    `unknown_entity` (нет строки в tenant); валидная ссылка на `CorrectiveAction` того же
    tenant'а — проходит. Для теста создать минимальный
    `CorrectiveAction(tenant_id=..., source_type="incident", source_id="s1", title="t",
    action_type="corrective")`.
  - update: смена `article_id`/`site_id`/`entity_id` перевалидируется; `domain` в Update
    отсутствует (схема).

Пример ключевого теста:

```python
@pytest.mark.asyncio
async def test_expense_rejects_foreign_tenant_site(session, tenant_id, other_tenant_id):
    foreign_site = Site(tenant_id=other_tenant_id, company_id=..., name="Чужой цех")
    session.add(foreign_site)
    await session.flush()
    svc = BudgetService(session, tenant_id)
    with pytest.raises(BudgetValidationError) as e:
        await svc.create_expense(BudgetExpenseCreate(
            domain="events", title="x", occurred_on=date(2026, 1, 10), amount=100,
            site_id=foreign_site.id,
        ))
    assert e.value.code == "unknown_site"
```

- [ ] **Step 2: Прогнать — AttributeError (нет create_expense).**

- [ ] **Step 3: Реализовать в `service.py`:**

```python
    # expenses
    async def create_expense(self, payload: BudgetExpenseCreate) -> BudgetExpense
    async def list_expenses(self, *, domain=None, article_id=None, date_from=None, date_to=None,
                            company_id=None, branch_id=None, site_id=None,
                            limit: int, offset: int) -> tuple[list[tuple[BudgetExpense, str | None]], int]
    async def update_expense(self, expense_id: str, payload: BudgetExpenseUpdate) -> BudgetExpense
    async def delete_expense(self, expense_id: str) -> None

    async def _validate_expense_refs(self, *, article_id, company_id, branch_id, site_id,
                                     entity_type, entity_id, domain) -> None
```

`_validate_expense_refs` — по одному `select(Model.id)` на заданное поле (пропускать None):
- article: `BudgetExpenseArticle` where tenant, id, `deleted_at IS NULL` → нет → `unknown_article`;
  затем `is_active` → нет → `article_inactive`; затем `domain in (None, expense.domain)` →
  иначе `article_domain_mismatch`.
- company/branch/site: `Company`/`Branch`/`Site` (`app.models.master_data`) where tenant, id,
  `deleted_at IS NULL` → `unknown_company`/`unknown_branch`/`unknown_site`.
- entity: тип должен равняться `EXPENSE_ENTITY_TYPES[domain]` → иначе `invalid_entity_type`;
  модель по мапе `{"training_session": TrainingSession, "medical_exam": MedicalExam,
  "corrective_action": CorrectiveAction}` (импорты: `app.models.training`, `app.models.medical`,
  `app.models.safety_ops`; ВНИМАНИЕ: у `TrainingSession` НЕТ SoftDeleteMixin — deleted_at-фильтр
  только там, где атрибут есть: `hasattr(Model, "deleted_at")`) where tenant, id → нет →
  `unknown_entity`.
- В `update_expense`: собрать merged-значения (stored + `exclude_unset`) и звать
  `_validate_expense_refs` только если менялись соответствующие поля (достаточно: звать всегда
  с merged-значениями — идемпотентно и проще; для article_inactive пропускать проверку, если
  `article_id` не менялся).

`list_expenses`: `select(BudgetExpense, BudgetExpenseArticle.name).outerjoin(...)`, фильтры,
`order_by(occurred_on.desc(), BudgetExpense.id)`, отдельный `func.count` для total.

- [ ] **Step 4: Прогнать оба сервисных файла — зелёные.**

- [ ] **Step 5: Commit:** `git add backend/app/modules/budget/service.py tests/api/test_budget_expense_service.py && git commit -m "feat(budget): expense journal + tenant-scoped FK/entity validation"`

---

### Task 5: Агрегация — факт / overview (вкл. СИЗ read-only) / breakdown

**Files:**
- Create: `backend/app/modules/budget/aggregation.py`
- Test: `tests/api/test_budget_aggregation.py`

- [ ] **Step 1: Падающие тесты.** Покрыть:
  - `compute_domain_actual`: суммирует только свой домен/окно (границы включительно), soft-deleted
    расходы не считает; `by_article` группирует c именами + bucket «— без статьи»
    (article_id=None); `expense_count` точный.
  - `compute_overview`: (a) планы — overlap-семантика: бюджет `[2026-01-01..2026-06-30]` попадает
    в окно `[2026-06-01..2026-12-31]` полной суммой; бюджет вне окна — не попадает; (b) у каждого
    budget-row `actual_own_period` считается по СОБСТВЕННОМУ периоду бюджета, а не окну;
    (c) **СИЗ-домен**: создать `PPESafetyBudget` + склад-данные (позиция/партия с `unit_cost` +
    receipt-движение — скопировать сетап из `tests/api/test_ppe_budget_actual_service.py`) →
    в overview домен `ppe` имеет `read_only=True`, plan из ppe_safety_budget, actual > 0,
    `warning_unpriced_receipts` прокинут; (d) домены без бюджетов и расходов присутствуют в ответе
    с нулями (детерминированный UI).
  - `compute_breakdown`: по каждому dimension (`article`/`domain`/`company`/`branch`/`site`) —
    группировка, имена из справочников, None-bucket `id=""` только при ненулевой сумме,
    сортировка `amount desc, name asc`, cap 200 (создать 2 строки, проверить порядок; cap —
    юнитом на константу), `total` = строк до капа; unknown dimension →
    `BudgetValidationError("breakdown_dimension_unknown")`; `date_from > date_to` →
    `BudgetValidationError("breakdown_window_invalid")`. СИЗ-расходы в breakdown НЕ входят
    (тест: склад-receipt есть, breakdown по domain не содержит `ppe`).

- [ ] **Step 2: Прогнать — ImportError.**

- [ ] **Step 3: Реализовать `aggregation.py`:**

```python
"""Вычисляемый факт бюджетного контура. НИКОГДА не персистится (инвариант §12.4/§35.5)."""

BREAKDOWN_ROW_CAP = 200
BREAKDOWN_DIMENSIONS = ("article", "domain", "company", "branch", "site")
NO_BUCKET_ID = ""

@dataclass(slots=True, frozen=True)
class ArticleActual:
    article_id: str | None
    article_name: str
    amount: float

@dataclass(slots=True, frozen=True)
class DomainActual:
    actual_total: float
    by_article: list[ArticleActual]
    expense_count: int

async def compute_domain_actual(session, tenant_id, domain, period_start, period_end) -> DomainActual
async def compute_overview(session, tenant_id, date_from, date_to) -> BudgetOverviewResponse
async def compute_breakdown(session, tenant_id, dimension, date_from, date_to) -> BudgetBreakdownResponse
```

- `compute_domain_actual`: один `select(BudgetExpense.article_id, BudgetExpenseArticle.name,
  func.sum(amount), func.count()).outerjoin(...).where(tenant, domain, occurred_on BETWEEN,
  deleted_at IS NULL).group_by(article_id, name)`; None-имя → «— без статьи»; totals — суммой
  по группам.
- `compute_overview`: для 3 доменов — бюджеты
  `where(period_start <= date_to, period_end >= date_from, deleted_at IS NULL)` (overlap);
  на каждый бюджет — `compute_domain_actual` по его периоду; per-domain `actual` — одним
  вызовом `compute_domain_actual(domain, date_from, date_to)`. Для `ppe`:
  `select(PPESafetyBudget)` (тот же overlap; `app.models.ppe`) + `compute_budget_actual` из
  `app.modules.ppe.budget` (для окна — раз, и для каждого ppe-бюджета — по его периоду);
  `warning_unpriced_receipts = actual.unpriced_receipt_count` окна. Возвращать pydantic-объекты
  схем из Task 2 (импорт `app.schemas.budget`), `generated_at = datetime.now(timezone.utc)`.
  Дефолты окна разруливает РОУТЕР (см. Task 6), сюда приходят готовые даты.
- `compute_breakdown`: dimension→колонка: article → join имени; domain → сам столбец
  (имена RU отдаёт фронт-vocab, тут — код домена как name); company/branch/site → outerjoin
  `Company`/`Branch`/`Site` по FK. Один `GROUP BY` + сшивка имён; NULL-группа → `id=""`,
  name «— без привязки» (для article — «— без статьи»); сортировка/cap/total как в спеке.

- [ ] **Step 4: Прогнать — зелёный.** Также регресс эталона:
  `python -m pytest tests/api/test_ppe_budget_actual_service.py -p no:schemathesis -q`
  (мы его импортируем, не меняем — должен остаться зелёным).

- [ ] **Step 5: Commit:** `git add backend/app/modules/budget/aggregation.py tests/api/test_budget_aggregation.py && git commit -m "feat(budget): computed actuals — domain fact, overview incl. PPE read-only, breakdown"`

---

### Task 6: API-роутер + регистрация

**Files:**
- Create: `backend/app/modules/budget/api.py`
- Modify: `backend/app/api/v1/route_groups.py` (import + кортеж регистрации)
- Test: `tests/api/test_budget_api.py`

- [ ] **Step 1: Падающие тесты.** Обвязка — зеркало `tests/api/test_ppe_budget_api.py`
  (auth-заголовки/клиент оттуда) + фича-флаг: как включается флаг в тестах — посмотреть
  тесты rules_engine (grep `rules_engine` по tests/, взять хелпер включения Feature/
  FeatureEnablement). Покрыть:
  - flag-off → 404 на `GET /api/v1/budget/budgets` (и body содержит «is not enabled»).
  - CRUD бюджета end-to-end (201 → list → detail c `actual_total`/`remaining`/`by_article` после
    двух созданных расходов → PATCH → DELETE 204).
  - `POST /budget/articles/seed-defaults` дважды → `{created:9,skipped:0}` затем
    `{created:0,skipped:9}`; дубль кода статьи → 409 `ARTICLE_CODE_EXISTS`.
  - Расход с чужим `site_id` → 422 (код `unknown_site` в detail).
  - `GET /budget/overview` → 4 домена, `ppe.read_only == true`.
  - `GET /budget/breakdown?dimension=nope` → 422; `?dimension=article` → 200.
  - RBAC: `accountant` и `ot_pb_lead` — 200 на чтение; `worker` (или `student`) — 403.
  - ETag: второй `GET /budget/budgets` с `If-None-Match` → 304.

- [ ] **Step 2: Прогнать — 404 (роут не зарегистрирован).**

- [ ] **Step 3: Реализовать `api.py`.** Полное зеркало структуры
  `backend/app/modules/rules_engine/api.py` (скопировать и адаптировать):
  - `router = APIRouter(prefix="/budget", tags=["budget"])`.
  - `_ROLES = ["admin", "owner", "accountant", "ot_pb_lead"]` — сверить слаги по
    `backend/app/core/rbac_abac.py` (оба подтверждены грепом) и `Access`-деп через `abac(...,
    required_roles=_ROLES, action="manage safety budget")`. Один Access на чтение и запись
    (спека: наборы совпадают).
  - `_FEATURE_CODE = "budget"`; `_require_feature` → 404
    `api_problem_detail(code="BUDGET_DISABLED", message="Budget feature is not enabled for this
    tenant", error_type="budget")`; `FeatureGate = Depends(_require_feature)`.
  - `_audit` хелпер с `object_type="safety_budget"` (создание/изменение бюджета),
    `"budget_expense_article"`, `"budget_expense"` — object_type передавать параметром.
  - Порядок роутов (СТАТИЧЕСКИЕ ДО `{id}`): `GET /overview`, `GET /breakdown`,
    `POST/GET /articles`, `POST /articles/seed-defaults`, `PATCH/DELETE /articles/{article_id}`,
    `POST/GET /expenses`, `PATCH/DELETE /expenses/{expense_id}`, `POST/GET /budgets`,
    `GET/PATCH/DELETE /budgets/{budget_id}`.
  - `GET /overview`: `date_from: date | None = Query(None)`, `date_to: date | None = Query(None)`;
    дефолт — текущий календарный год (`date(today.year,1,1)`/`date(today.year,12,31)`,
    `today = datetime.now(timezone.utc).date()`); `date_from > date_to` → 422
    `breakdown_window_invalid` (тот же код — единая семантика окна).
  - `GET /breakdown`: те же query + `dimension: str = Query(...)`;
    `BudgetValidationError` → 422 c `detail=api_problem_detail(code=exc.code, ...)`.
  - Маппинг исключений: `BudgetNotFound`/`ArticleNotFound`/`ExpenseNotFound` → 404;
    `ArticleCodeConflict` → 409 `ARTICLE_CODE_EXISTS`; `BudgetValidationError` → 422 (code из
    исключения).
  - ETag на `GET /budgets`, `GET /articles`, `GET /expenses` — точный паттерн `list_rules`
    (`compute_list_etag` + `build_not_modified_headers` + `apply_etag_response_headers`).
  - Write-роуты: `_audit(...)` ПЕРЕД `session.commit()`; после — `refresh` + Read-схема
    (см. `create_rule`).

  В `route_groups.py`: `from app.modules.budget.api import router as budget_router` (строка к
  блоку импортов ~85) и `(budget_router, {"tags": ["budget"]}),` в конец
  `DOCUMENT_CORE_ROUTER_REGISTRATIONS` (рядом с rules_engine ~188).

- [ ] **Step 4: Прогнать api-тесты + быстрый смок всех budget-тестов** (5 файлов одним батчем) —
  зелёные.

- [ ] **Step 5: Commit:** `git add backend/app/modules/budget/api.py backend/app/api/v1/route_groups.py tests/api/test_budget_api.py && git commit -m "feat(budget): /budget API — 16 routes behind budget flag"`

---

### Task 7: Demo-сид + OpenAPI baseline

**Files:**
- Modify: `backend/app/services/demo_bootstrap.py`
- Modify: `docs/stabilization/openapi_routes_baseline.json` (реген скриптом)

- [ ] **Step 1: Реализовать `_seed_budget_demo(session, tenant_db_id)`** по образцу
  `_seed_committees_demo` (флаг) + `_seed_report_builder_demo` (идемпотентность):
  - Feature `code="budget", title="Бюджет безопасности"` + FeatureEnablement(on=True) —
    find-or-create.
  - `BudgetService(session, tenant_db_id).seed_default_articles()`.
  - 3 бюджета (natural key — name; создавать только если нет): «Бюджет обучения 2026» (training,
    2026-01-01..2026-12-31, 500000), «Бюджет медосмотров 2026» (medical, тот же период, 350000),
    «Бюджет мероприятий 2026» (events, тот же период, 250000).
  - ~5 расходов (natural key — title; только если нет): 2 training (одна со статьёй
    training_external), 1 medical (medical_periodic), 2 events (events_capa; один с `site_id`
    первого demo-`Site` и `branch_id` первого demo-`Branch`, если они есть в demo-сиде — если
    Branch в demo нет, создать один `Branch(name="Головной филиал")` для company demo-tenant'а;
    один расход со ссылкой `entity_type="corrective_action"` на существующее demo-CAPA, если
    есть — иначе без ссылки).
  - Вызвать `_seed_budget_demo` в конце `bootstrap_demo_tenant()` рядом с соседними сидами.
- [ ] **Step 2: Прогнать существующий тест сидов** (grep: `bootstrap_demo` в tests/ — найти и
  запустить соответствующий файл; если такого нет — smoke: `python -c` с вызовом функции не
  требуется, достаточно, что Task 12 живой dev_lite прогон это проверит).
- [ ] **Step 3: Переснять OpenAPI baseline:**

```powershell
$env:PYTHONPATH="backend"; $env:SECRET_KEY="x"; $env:S3_ACCESS_KEY="x"; $env:S3_SECRET_KEY="x"; $env:S3_BUCKET="x"
python scripts/ci/check_openapi_snapshot.py --snapshot
python scripts/ci/check_openapi_snapshot.py --compare   # ожидание: ARCH-4 unchanged, exit 0
```

  Зафиксировать в выводе счётчики операций/схем (до/после, ожидание +16 операций) — счётчики
  пойдут в handoff.
- [ ] **Step 4: Commit:** `git add backend/app/services/demo_bootstrap.py docs/stabilization/openapi_routes_baseline.json && git commit -m "feat(budget): demo seed + openapi baseline (+16 /budget routes)"`

---

### Task 8: Фронт — api-клиент, DTO, vocab, права, маршрут, навигация

**Files:**
- Create: `frontend/src/api/budget.ts`
- Create: `frontend/src/types/dto/budget.ts`
- Create: `frontend/src/pages/budget/budgetVocab.ts`
- Create: `frontend/src/pages/budget/BudgetPage.tsx` (минимальный каркас — вкладки наполняются в
  Tasks 9-10)
- Modify: `frontend/src/permissions/permissions.ts`, `frontend/src/router/pageRegistry.tsx`,
  `frontend/src/router/routeGroups.tsx`, `frontend/src/router/navigationConfig.ts`,
  `frontend/src/router/navVisibility.ts`
- Test: `frontend/src/api/budget.test.ts` (контрактный, зеркало `src/api/rules.test.ts`, если
  есть; иначе — зеркало ближайшего api-теста)

- [ ] **Step 1: DTO `types/dto/budget.ts`** — точное зеркало схем Task 2 (`BudgetDomain =
  "training" | "medical" | "events"`; `SafetyBudgetDto`, `SafetyBudgetDetailDto`,
  `BudgetArticleDto`, `BudgetExpenseDto`, `BudgetOverviewDto`, `BudgetBreakdownDto`,
  `*CreateInput`/`*UpdateInput`, `Page<T>`-формы `{items,total,limit,offset}`).
- [ ] **Step 2: `api/budget.ts`** — зеркало `api/rules.ts`: `const BASE = "/budget"`; методы
  (16): `getOverview(params)`, `getBreakdown(params)`, `listBudgets/createBudget/getBudget/
  updateBudget/deleteBudget`, `listArticles/createArticle/updateArticle/deleteArticle/
  seedDefaultArticles`, `listExpenses/createExpense/updateExpense/deleteExpense`; копия
  `isFeatureDisabledError` (status 404 + `/feature is not enabled/i`).
- [ ] **Step 3: `budgetVocab.ts`:** `BUDGET_DOMAIN_LABELS = {training: "Обучение", medical:
  "Медосмотры", events: "Мероприятия", ppe: "СИЗ (склад)"}`; `BREAKDOWN_DIMENSION_LABELS =
  {article: "По статьям", domain: "По доменам", company: "По компаниям", branch: "По филиалам",
  site: "По объектам"}`.
- [ ] **Step 4: Права/маршрут/нав (строго парой — guard-тест):**
  - `permissions.ts`: `BUDGET_VIEW: "budget.view"`, `BUDGET_MANAGE: "budget.manage"`; в
    `ROLE_PERMISSIONS.accountant` добавить оба; если в Role-union есть `ot_pb_lead` — добавить
    оба и ему (admin/owner — через isAdminUser-байпас, ot_pb_head — через ALL-механику; проверить
    grep'ом, как ot_pb_head получает список).
  - `pageRegistry.tsx`: `export const BudgetPage = lazy(() => import("@/pages/budget/BudgetPage"));`
  - `routeGroups.tsx`: `{ permission: PERMISSIONS.BUDGET_VIEW, routes: [<Route key="/budget"
    path="/budget" element={<BudgetPage />} />] }` (рядом с RULES_VIEW-группой, строка ~244).
  - `navigationConfig.ts`: в группу «Бизнес и аналитика» —
    `{ label: "Бюджет безопасности", to: "/budget", icon: Wallet, permission:
    PERMISSIONS.BUDGET_VIEW }` (icon `Wallet` из lucide-react — как импортированы соседние).
  - `navVisibility.ts`: `if (item.to === "/budget" && featureFlags.budget === false) return false;`
- [ ] **Step 5: Каркас `BudgetPage.tsx`** — default-export; `useAsyncResource` с
  useCallback-loader (`Promise.all([getOverview(), listBudgets(), listArticles(),
  listExpenses()])`); `isFeatureDisabledError` по всем ошибкам → EmptyState «Функция недоступна»
  (паттерн `RulesPage.tsx`); Radix Tabs со вкладками «Сводка / Бюджеты / Расходы / Статьи»
  (контент — заглушки `<div>` до Tasks 9-10, БЕЗ отдельного коммита заглушек — Task 8 коммитится
  целиком, тесты страницы приходят в Tasks 9-10).
- [ ] **Step 6: Прогнать:** `npx vitest run src/__tests__/navigationConfigRoutes.test.tsx
  src/api/budget.test.ts` → PASS; `npm --prefix frontend run typecheck` → 0.
- [ ] **Step 7: Commit:** `git add frontend/src/api/budget.ts frontend/src/types/dto/budget.ts frontend/src/pages/budget/ frontend/src/permissions/permissions.ts frontend/src/router/ && git commit -m "feat(budget): typed api client + route/nav/permissions wiring"`

---

### Task 9: Фронт — вкладки «Сводка» и «Бюджеты»

**Files:**
- Create: `frontend/src/features/budget/OverviewTab.tsx`, `frontend/src/features/budget/BudgetsTab.tsx`,
  `frontend/src/features/budget/BudgetFormDialog.tsx`
- Modify: `frontend/src/pages/budget/BudgetPage.tsx`
- Test: `frontend/src/pages/budget/BudgetPage.test.tsx`

- [ ] **Step 1: Падающие тесты** (vi.mock `@/api/budget` через importOriginal-подмену; vi.mock
  `Can` → «всегда можно»; MemoryRouter; образец — `frontend/src/pages/rules/*.test.tsx` или
  contractors-тесты):
  - рендер «Сводки»: 4 домена с RU-лейблами, у `ppe` бейдж «ведётся на складе» и ссылка на
    `/warehouse`; строки план/факт/остаток из мока overview.
  - breakdown-таблица: toggle dimension → вызов `getBreakdown({dimension})`; строка None-bucket
    (`id:""`) рендерится и не кликабельна; подпись «СИЗ-закупки в разрезе не участвуют».
  - «Бюджеты»: таблица из мока; открытие `BudgetFormDialog`, submit → `createBudget` вызван с
    введёнными значениями; строка → detail-блок с `by_article`.
  - feature-off: все ресурсы реджектят 404 «feature is not enabled» → EmptyState.
- [ ] **Step 2: Прогнать — FAIL (компонентов нет).**
- [ ] **Step 3: Реализовать.**
  - `OverviewTab`: props `{overview: BudgetOverviewDto, onReload: () => void}`; период-фильтр
    (два date-input + кнопка «Применить» → `getOverview({date_from, date_to})` через колбэк
    страницы); карточки доменов (Card): лейбл из vocab, план/факт/остаток
    (`Intl.NumberFormat("ru-RU")`), для ppe — Badge «ведётся на складе» + `<Link to="/warehouse">`
    + предупреждение «Приходов без цены: N» при `warning_unpriced_receipts > 0`; разрез: toggle
    из `BREAKDOWN_DIMENSION_LABELS`, простая HTML-таблица `имя | сумма | CSS-бар
    width=amount/max*100%` (образец — breakdown-таблица `ManagementDashboardPage`).
  - `BudgetsTab`: фильтр по домену (select из vocab), таблица (название/домен/период/план),
    `BudgetFormDialog` (`{trigger, initialData?, onSubmitted?}` — контракт contractors-диалогов):
    поля name/domain(select; disabled при edit)/period_start/period_end/planned_amount/notes;
    write-контролы под `<Can permission={PERMISSIONS.BUDGET_MANAGE}>`; клик по строке →
    `getBudget(id)` → detail-блок (план/факт/остаток + таблица by_article + expense_count).
  - Подключить оба в `BudgetPage` (передавая данные/reload из loader'а страницы).
- [ ] **Step 4: Прогнать тесты страницы + typecheck** → PASS.
- [ ] **Step 5: Commit:** `git add frontend/src/features/budget/ frontend/src/pages/budget/ && git commit -m "feat(budget): overview + budgets tabs"`

---

### Task 10: Фронт — вкладки «Расходы» и «Статьи»

**Files:**
- Create: `frontend/src/features/budget/ExpensesTab.tsx`, `frontend/src/features/budget/ExpenseFormDialog.tsx`,
  `frontend/src/features/budget/ArticlesTab.tsx`, `frontend/src/features/budget/ArticleFormDialog.tsx`
- Modify: `frontend/src/pages/budget/BudgetPage.tsx`
- Test: `frontend/src/pages/budget/BudgetPage.test.tsx` (дополнить)

- [ ] **Step 1: Падающие тесты:**
  - «Расходы»: таблица из мока (`article_name` рендерится, «— без статьи» для null); фильтры
    домен+статья вызывают `listExpenses` с параметрами; `ExpenseFormDialog` submit →
    `createExpense` с датой/суммой/доменом; выбор домена фильтрует селект статей (universal +
    доменные); блок «Связать с записью» появляется по чекбоксу и шлёт `entity_type`
    (фиксированный по домену) + введённый `entity_id`.
  - «Статьи»: таблица; `seedDefaultArticles` по кнопке «Заполнить стандартными» → reload;
    create-диалог → `createArticle`; деактивация (Switch is_active) → `updateArticle`.
- [ ] **Step 2: Прогнать — FAIL.**
- [ ] **Step 3: Реализовать.** `ExpenseFormDialog`: селекты компаний/филиалов/объектов — грузить
  справочники через существующие api-клиенты (grep `frontend/src/api` на `companies`/`sites`/
  `branches`; чего нет — простой `apiClient.get("/branches", {params:{limit:200}})` внутри
  `api/budget.ts` как `listBranchesRef()`); тихая деградация: 403/ошибка справочника → селект не
  рендерится (паттерн ManagementDashboardPage). Сумма — input type=number, отправлять `Number`,
  пустая строка → поле не отправляется (грабля rules-формы). `ArticlesTab`: колонки
  код/название/домен («Универсальная» для null)/активность; write под `<Can
  permission={PERMISSIONS.BUDGET_MANAGE}>`.
- [ ] **Step 4: Прогнать тесты страницы + typecheck.**
- [ ] **Step 5: Commit:** `git add frontend/src/features/budget/ frontend/src/pages/budget/ && git commit -m "feat(budget): expenses + articles tabs"`

---

### Task 11: Полные гейты

**Files:** только фиксы, если гейты красные.

- [ ] **Step 1 (backend):** батчи PowerShell (тайм-аут 600000, ОДИН прогон на батч, лог в файл):
  (a) `tests/api/test_budget_model.py tests/api/test_budget_schema.py
  tests/api/test_budget_service.py tests/api/test_budget_expense_service.py`;
  (b) `tests/api/test_budget_aggregation.py tests/api/test_budget_api.py`;
  (c) регресс смежного: `tests/api/test_ppe_budget_api.py tests/api/test_ppe_budget_actual_service.py`
  (+ если есть тесты route_groups/openapi в tests/unit — включить). Все EXIT=0.
- [ ] **Step 2 (стиль):** `python -m ruff check backend/app/modules/budget backend/app/models/budget.py backend/app/schemas/budget.py backend/app/migrations/versions/20260717_bg01_safety_budget_core.py tests/api/test_budget_*.py` и `python -m black --check <те же>` → clean (при фиксах перепрогнать затронутые тесты).
- [ ] **Step 3 (PG16):** `python scripts/ci/local_gate.py --db-only` (требует Docker; round-trip
  `bg01` upgrade→downgrade→upgrade). Если Docker недоступен — зафиксировать «PG16 отложен на CI»
  в handoff (прецедент committees) — но ПОПЫТАТЬСЯ обязательно.
- [ ] **Step 4 (frontend):** `npm --prefix frontend run typecheck` → 0; полный
  `npm --prefix frontend run test` (не параллелить с другим; красное — перепроверить файл
  изолированно `npx vitest run <file>`); `npm --prefix frontend run build` → 0 (lazy-чанк
  BudgetPage в precache).
- [ ] **Step 5: Commit** (если были фиксы): `git commit -m "fix(budget): gate fixes"` с точечными путями.

---

### Task 12: Живая верификация + docs + handoff

**Files:**
- Modify: `CHANGELOG.md`, `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md` (строка P10-06
  «Остаётся» — вычеркнуть кросс-доменный §12.4-кусок, вписать сделанное; Summary-строка),
  `AI_IMPLEMENTATION_REPORT.md` (новый handoff-блок сверху)

- [ ] **Step 1: dev_lite из worktree** (`python scripts/dev_lite.py --auto-kill-ports`; помнить:
  он сам ставит `DEMO_BOOTSTRAP=0` → прогнать
  `$env:DATABASE_URL="sqlite+aiosqlite:///./dev.db"; $env:SECRET_KEY="x"; $env:S3_ACCESS_KEY="x";
  $env:S3_SECRET_KEY="x"; $env:S3_BUCKET="x"; python scripts/bootstrap_demo_tenant.py --force`).
- [ ] **Step 2: Живой API-прогон** (авторизоваться demo/admin@example.com/admin123; браузер-пейн
  или httpx): `GET /api/v1/budget/overview` → 200, 4 домена, ppe.read_only=true;
  `POST /api/v1/budget/expenses` (novый расход events) → 201 → overview изменился;
  `GET /api/v1/budget/breakdown?dimension=site` → 200 (demo-расход с site_id виден);
  `dimension=nope` → 422.
- [ ] **Step 3: UI-прогон** (browser pane): логин → `/budget` в меню «Бизнес и аналитика» →
  4 вкладки рендерятся: Сводка (домены+разрез), Бюджеты (3 demo), Расходы (demo-журнал),
  Статьи (9). Скриншот; если screenshot таймаутит (известная деградация) — read_page/DOM-пруф.
- [ ] **Step 4: Docs:** CHANGELOG-запись волны; roadmap-правка; handoff-блок в
  `AI_IMPLEMENTATION_REPORT.md` (шаблон раздела H ТЗ: Studied Docs / Selected Plan Item /
  Implemented / Decisions / Known Problems / Validation / Next: срез-2 = заявки на возмещение
  СФР + СИЗ-в-breakdown + автосбор факта).
- [ ] **Step 5: Commit + push:**
  `git add CHANGELOG.md docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md AI_IMPLEMENTATION_REPORT.md && git commit -m "docs(budget): wave handoff + changelog + roadmap (§12.4 срез-1)" && git push -u origin claude/tz-continuation-d43adc`.
  PR-body минимальный (политика публичного репо). PR открывать только по решению пользователя.

---

## Self-Review

- **Spec coverage:** модели/миграция (Task 1) ✓; схемы (2) ✓; CRUD бюджеты+статьи+seed (3) ✓;
  расходы+tenant-валидация (4) ✓; факт/overview-с-СИЗ/breakdown (5) ✓; 16 роутов+флаг+RBAC+ETag+
  audit (6) ✓; demo-сид+OpenAPI (7) ✓; фронт-провод (8) ✓; вкладки (9-10) ✓; гейты (11) ✓;
  живая верификация+docs (12) ✓. Все 8 требований среза из спеки покрыты; возмещения — вне
  объёма (спека).
- **Placeholder scan:** код всех новых backend-файлов дан полностью (модели, миграция, схемы) или
  сигнатурами+точными правилами (service/aggregation/api — с указанием эталонного файла для
  копирования обвязки); тесты — полные функции для ключевых кейсов + перечисленные спецификации
  для остальных с точными кодами ошибок. Фикстурные имена намеренно берутся из эталонных
  test_ppe_budget_* (имплементер обязан открыть их первым шагом).
- **Type consistency:** `BudgetService`/`BudgetValidationError(code)`/`compute_domain_actual`/
  `compute_overview`/`compute_breakdown`/`EXPENSE_ENTITY_TYPES` — имена совпадают в Tasks 1-6;
  DTO фронта зеркалят схемы Task 2; коды ошибок (`unknown_*`, `article_domain_mismatch`,
  `article_inactive`, `invalid_entity_type`, `unknown_entity`, `ARTICLE_CODE_EXISTS`,
  `breakdown_dimension_unknown`, `breakdown_window_invalid`, `BUDGET_DISABLED`) — единый список
  в Tasks 4-6 и тестах.
