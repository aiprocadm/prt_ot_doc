# СИЗ Срез-1: нормы + личная карточка 766н + жизненный цикл выдачи — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Превратить «schema theater» PPE-контура в рабочий поток: CRUD норм выдачи, вычисляемая личная карточка по 766н (с хранимыми реквизитами), явный FSM-цикл выдачи (return/writeoff/replace), beat-скан истекающих СИЗ, удаление орфанного семейства B из ORM.

**Architecture:** Эволюция живого семейства A (`models.py`: PPENorm/PPEItem/PPEIssue) + домен по паттерну medical/contractors: чистый `domains/ppe/lifecycle.py` (FSM + статусы строк карточки) и I/O в `domains/ppe/service.py`. Конверсия `ppeissue.status` native enum → VARCHAR(32). Спек: `docs/superpowers/specs/2026-06-10-ppe-norms-personal-card-design.md`.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Alembic + Celery beat + outbox; pytest (фикстуры `async_client`/`make_auth_headers`/`sessionmaker`/`data_factory` из корневого `tests/conftest.py`).

**Прогон тестов (Win/Py3.13.7/.venv):** все pytest-команды запускать из корня репо через PowerShell с редиректом в файл (НЕ git-bash→tail), например:
`.venv\Scripts\python.exe -m pytest <paths> -p no:xdist --timeout=120 -q > test_out.txt 2>&1; Get-Content test_out.txt -Tail 30`
Канон Py3.12 = CI (выключен) — расхождение версии указывать в отчёте, не абортить.

**Контекст-якоря (прочитать перед задачей, если что-то неясно):**
- Паттерн чистого lifecycle: `backend/app/domains/contractors/lifecycle.py`, `backend/app/domains/shared.py`
- Паттерн notify+tick: `backend/app/services/contractor_documents.py`, `backend/app/tasks/_core.py:2004-2032`
- Паттерн CRUD с 409/ETag/ABAC: `backend/app/api/routes/ppe.py` (существующие items/issues), `backend/app/api/routes/contractors.py`
- Миграция-шаблон: `backend/app/migrations/versions/20260610_con02_contractor_document_requirements.py`

---

### Task 1: Чистый lifecycle-модуль (FSM + статусы строк карточки)

**Files:**
- Create: `backend/app/domains/ppe/lifecycle.py`
- Test: `backend/tests/test_ppe_lifecycle.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_ppe_lifecycle.py
"""Pure-logic tests for the PPE issue FSM and personal-card line statuses.

Hermetic: no DB, no route imports (Windows libmagic pitfall).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domains.ppe.lifecycle import (
    ISSUE_STATUS_ISSUED,
    ISSUE_STATUS_LOST,
    ISSUE_STATUS_REPLACED,
    ISSUE_STATUS_RETURNED,
    ISSUE_STATUS_WRITTEN_OFF,
    IssueView,
    PPETransitionError,
    card_line_status,
    fold_card_status,
    validate_transition,
)

TODAY = date(2026, 6, 10)


# --- FSM -------------------------------------------------------------------

@pytest.mark.parametrize("target", [
    ISSUE_STATUS_RETURNED, ISSUE_STATUS_WRITTEN_OFF, ISSUE_STATUS_REPLACED, ISSUE_STATUS_LOST,
])
def test_issued_can_transition_to_each_terminal(target):
    validate_transition(ISSUE_STATUS_ISSUED, target)  # must not raise


@pytest.mark.parametrize("current", [
    ISSUE_STATUS_RETURNED, ISSUE_STATUS_WRITTEN_OFF, ISSUE_STATUS_REPLACED, ISSUE_STATUS_LOST,
])
def test_terminal_statuses_are_frozen(current):
    with pytest.raises(PPETransitionError):
        validate_transition(current, ISSUE_STATUS_RETURNED)


def test_unknown_status_rejected():
    with pytest.raises(PPETransitionError):
        validate_transition(ISSUE_STATUS_ISSUED, "evaporated")
    with pytest.raises(PPETransitionError):
        validate_transition("bogus", ISSUE_STATUS_RETURNED)


def test_noop_same_status_rejected():
    with pytest.raises(PPETransitionError):
        validate_transition(ISSUE_STATUS_ISSUED, ISSUE_STATUS_ISSUED)


# --- card_line_status ------------------------------------------------------

def _issue(qty=1, expires_in_days: int | None = 100, status=ISSUE_STATUS_ISSUED):
    expires = TODAY + timedelta(days=expires_in_days) if expires_in_days is not None else None
    return IssueView(quantity=qty, expires_at=expires, status=status)


def test_no_active_issues_is_missing():
    assert card_line_status(1, [], TODAY) == "missing"
    # returned-only is not active
    assert card_line_status(1, [_issue(status=ISSUE_STATUS_RETURNED)], TODAY) == "missing"


def test_partial_quantity_is_missing():
    assert card_line_status(2, [_issue(qty=1)], TODAY) == "missing"


def test_expired_active_issue_is_overdue():
    assert card_line_status(1, [_issue(expires_in_days=-1)], TODAY) == "overdue"


def test_due_soon_within_default_30_days():
    assert card_line_status(1, [_issue(expires_in_days=10)], TODAY) == "due_soon"


def test_ok_when_far_from_expiry():
    assert card_line_status(1, [_issue(expires_in_days=200)], TODAY) == "ok"


def test_termless_issue_is_ok():
    # expires_at IS NULL → бессрочно
    assert card_line_status(1, [_issue(expires_in_days=None)], TODAY) == "ok"


def test_overdue_beats_due_soon_within_line():
    issues = [_issue(expires_in_days=10), _issue(expires_in_days=-5)]
    assert card_line_status(1, issues, TODAY) == "overdue"


# --- fold_card_status ------------------------------------------------------

def test_fold_empty_is_ok():
    assert fold_card_status([]) == "ok"


def test_fold_worst_of():
    assert fold_card_status(["ok", "due_soon"]) == "due_soon"
    assert fold_card_status(["ok", "overdue", "due_soon"]) == "overdue"
    assert fold_card_status(["missing", "overdue"]) == "missing"
    assert fold_card_status(["ok", "ok"]) == "ok"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_ppe_lifecycle.py -p no:xdist --timeout=120 -q > test_out.txt 2>&1; Get-Content test_out.txt -Tail 15`
Expected: FAIL — `ImportError: cannot import name ... from 'app.domains.ppe.lifecycle'` (модуля нет)

- [ ] **Step 3: Write the implementation**

```python
# backend/app/domains/ppe/lifecycle.py
"""Pure PPE lifecycle rules: issue FSM + personal-card line statuses.

No I/O and no sqlalchemy imports — mirrors ``domains/medical/lifecycle.py``
and ``domains/contractors/lifecycle.py``. Status values are the canonical
VARCHAR values stored in ``ppeissue.status`` (lowercase, see migration sz01).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from app.domains.shared import ContingentItemStatus, classify

ISSUE_STATUS_ISSUED = "issued"
ISSUE_STATUS_RETURNED = "returned"
ISSUE_STATUS_WRITTEN_OFF = "written_off"
ISSUE_STATUS_REPLACED = "replaced"
ISSUE_STATUS_LOST = "lost"

TERMINAL_STATUSES = frozenset({
    ISSUE_STATUS_RETURNED,
    ISSUE_STATUS_WRITTEN_OFF,
    ISSUE_STATUS_REPLACED,
    ISSUE_STATUS_LOST,
})
ISSUE_STATUSES = frozenset({ISSUE_STATUS_ISSUED}) | TERMINAL_STATUSES

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    ISSUE_STATUS_ISSUED: TERMINAL_STATUSES,
    ISSUE_STATUS_RETURNED: frozenset(),
    ISSUE_STATUS_WRITTEN_OFF: frozenset(),
    ISSUE_STATUS_REPLACED: frozenset(),
    ISSUE_STATUS_LOST: frozenset(),
}


class PPETransitionError(ValueError):
    """Invalid PPE issue status transition (maps to HTTP 409 at the API layer)."""

    def __init__(self, current: str, target: str) -> None:
        self.current = current
        self.target = target
        super().__init__(f"invalid PPE issue transition: {current!r} -> {target!r}")


def validate_transition(current: str, target: str) -> None:
    """Raise PPETransitionError unless current -> target is allowed."""
    allowed = ALLOWED_TRANSITIONS.get(current)
    if allowed is None or target not in allowed:
        raise PPETransitionError(current, target)


@dataclass(slots=True)
class IssueView:
    """ORM-free projection of a PPE issue for card computations."""

    quantity: int
    expires_at: date | None
    status: str


# Worst-first severity order for folding line statuses into a card verdict.
_SEVERITY = (
    ContingentItemStatus.MISSING.value,
    ContingentItemStatus.OVERDUE.value,
    ContingentItemStatus.DUE_SOON.value,
    ContingentItemStatus.OK.value,
)


def card_line_status(
    required_qty: int,
    issues: Iterable[IssueView],
    today: date,
    due_soon_days: int = 30,
) -> str:
    """Status of one «положено» card line vs the person's issues.

    missing  — no active issues, or active quantity below the norm (partial)
    overdue  — some active issue is past its wear term
    due_soon — some active issue expires within ``due_soon_days``
    ok       — otherwise; issues without expires_at are termless (never expire)
    """
    active = [i for i in issues if i.status == ISSUE_STATUS_ISSUED]
    if not active:
        return ContingentItemStatus.MISSING.value
    if sum(i.quantity for i in active) < required_qty:
        return ContingentItemStatus.MISSING.value

    statuses = {
        classify(i.expires_at, today, warning_days=due_soon_days).value
        for i in active
        if i.expires_at is not None
    }
    for severity in (_SEVERITY[1], _SEVERITY[2]):  # overdue, then due_soon
        if severity in statuses:
            return severity
    return ContingentItemStatus.OK.value


def fold_card_status(line_statuses: Iterable[str]) -> str:
    """Worst-of fold of line statuses; an empty card (no norms) is ok."""
    seen = set(line_statuses)
    for severity in _SEVERITY:
        if severity in seen:
            return severity
    return ContingentItemStatus.OK.value
```

Замечание: `classify(expires_at_date, today)` принимает `date`; `IssueView.expires_at` — `date`. При построении из ORM (Task 5) `PPEIssue.expires_at` (datetime) приводится через `.date()`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_ppe_lifecycle.py -p no:xdist --timeout=120 -q > test_out.txt 2>&1; Get-Content test_out.txt -Tail 5`
Expected: `18 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/ppe/lifecycle.py backend/tests/test_ppe_lifecycle.py
git commit -m "feat(ppe): pure lifecycle - issue FSM + card line statuses"
```

---

### Task 2: Модели + миграция sz01 + конверсия статуса в VARCHAR

**Files:**
- Modify: `backend/app/models/models.py` (PPENorm ~1400, PPEIssueStatus ~1447, PPEIssue ~1453, Person ~743)
- Create: `backend/app/migrations/versions/20260610_sz01_ppe_norms_card_766n.py`
- Modify: `backend/app/api/routes/ppe.py` (строки 314, 348, 352, 366 — `.value`/enum-сравнения)
- Modify: `backend/app/domains/ppe/service.py` (issue_ppe_item, list_expiring_issues)
- Test: `backend/tests/test_sz01_ppe_766n_migration.py`

- [ ] **Step 1: Write the failing tests (hermetic — модели и текст миграции, без route-импортов)**

```python
# backend/tests/test_sz01_ppe_766n_migration.py
"""sz01 migration + model shape: 766н fields, item_id on norms, VARCHAR status."""
from __future__ import annotations

import re
from pathlib import Path

from app.models.models import Person, PPEIssue, PPEIssueStatus, PPENorm

MIGRATION = Path(__file__).resolve().parents[1] / "app" / "migrations" / "versions" / "20260610_sz01_ppe_norms_card_766n.py"


def test_ppenorm_has_item_id():
    cols = PPENorm.__table__.c
    assert "item_id" in cols
    assert cols["item_id"].nullable is True


def test_person_has_ppe_sizes_json():
    assert "ppe_sizes" in Person.__table__.c
    assert Person.__table__.c["ppe_sizes"].nullable is True


def test_ppeissue_766n_columns():
    cols = PPEIssue.__table__.c
    for name in (
        "certificate_no", "wear_percent", "return_wear_percent",
        "signature_doc_ref", "writeoff_reason", "replaces_issue_id",
    ):
        assert name in cols, name
        assert cols[name].nullable is True, name


def test_ppeissue_status_is_varchar_not_native_enum():
    col = PPEIssue.__table__.c["status"]
    # String(32), NOT sqlalchemy Enum
    assert type(col.type).__name__ == "String"
    assert col.type.length == 32


def test_status_enum_has_all_five_values():
    assert {m.value for m in PPEIssueStatus} == {
        "issued", "returned", "written_off", "replaced", "lost",
    }


def test_migration_revision_chain():
    src = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260610_sz01_ppe_norms_card_766n"' in src
    assert 'down_revision = "20260610_con02_contractor_document_requirements"' in src


def test_migration_converts_status_and_drops_enum_type():
    src = MIGRATION.read_text(encoding="utf-8")
    # PG branch: USING lower(...), then drop the orphan enum type
    assert re.search(r"USING\s+lower\(status::text\)", src)
    assert "DROP TYPE IF EXISTS ppeissuestatus" in src
    # additive columns present
    for name in (
        "item_id", "ppe_sizes", "certificate_no", "wear_percent",
        "return_wear_percent", "signature_doc_ref", "writeoff_reason",
        "replaces_issue_id",
    ):
        assert name in src, name


def test_migration_downgrade_guards_new_values():
    src = MIGRATION.read_text(encoding="utf-8")
    # honest asymmetry: downgrade must refuse if written_off/replaced rows exist
    assert "written_off" in src and "replaced" in src
    assert "RuntimeError" in src
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_sz01_ppe_766n_migration.py -p no:xdist --timeout=120 -q > test_out.txt 2>&1; Get-Content test_out.txt -Tail 15`
Expected: FAIL — отсутствуют колонки/файл миграции

- [ ] **Step 3: Update models**

В `backend/app/models/models.py`:

(a) `PPENorm` — добавить после `interval_days` (строка ~1407):

```python
    item_id: Mapped[str | None] = mapped_column(
        ForeignKey("ppeitem.id", ondelete="SET NULL"), nullable=True, index=True
    )
```
и relationship после `hazard` (строка ~1410):
```python
    item: Mapped["PPEItem | None"] = relationship("PPEItem")
```

(b) `PPEIssueStatus` (строка ~1447) — добавить члены:

```python
class PPEIssueStatus(str, enum.Enum):
    ISSUED = "issued"
    RETURNED = "returned"
    WRITTEN_OFF = "written_off"
    REPLACED = "replaced"
    LOST = "lost"
```

(c) `PPEIssue` (строка ~1453) — заменить колонку `status` и добавить поля 766н:

```python
    # VARCHAR, not a native PG enum (sz01 converted the column; values are
    # the lowercase PPEIssueStatus .value strings — анти-грабли after the
    # PG enum incidents, same convention as medical/contractors).
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PPEIssueStatus.ISSUED.value
    )
    certificate_no: Mapped[str | None] = mapped_column(String(255), nullable=True)
    wear_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    return_wear_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    signature_doc_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    writeoff_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    replaces_issue_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
```

(d) `Person` — после `current_ppe` (строка ~743):

```python
    # 766н: рост и размеры СИЗ работника (одежда/обувь/головной убор/СИЗОД/
    # перчатки/рукавицы). JSON: состав ключей зависит от выдаваемых СИЗ.
    ppe_sizes: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
```

- [ ] **Step 4: Write the migration**

```python
# backend/app/migrations/versions/20260610_sz01_ppe_norms_card_766n.py
"""sz01: СИЗ Срез-1 — norms→catalog link, 766н card requisites, VARCHAR status.

Additive columns + one in-place type conversion:
  * ppenorm.item_id            (nullable FK-like ref to ppeitem; legacy rows keep item_name only)
  * person.ppe_sizes           (JSON, 766н sizes/anthropometry)
  * ppeissue: certificate_no / wear_percent / return_wear_percent /
              signature_doc_ref / writeoff_reason / replaces_issue_id
  * ppeissue.status: native enum ppeissuestatus -> VARCHAR(32), data lowercased,
    orphan PG type dropped (анти-грабли: VARCHAR convention, see con01/med01).

Downgrade is honest about asymmetry: it refuses when written_off/replaced rows
exist (those values are unrepresentable in the old 3-value enum).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260610_sz01_ppe_norms_card_766n"
down_revision = "20260610_con02_contractor_document_requirements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # --- additive columns ----------------------------------------------
    op.add_column("ppenorm", sa.Column("item_id", sa.String(length=36), nullable=True))
    op.create_index("ix_ppenorm_item_id", "ppenorm", ["item_id"])

    op.add_column("person", sa.Column("ppe_sizes", sa.JSON(), nullable=True))

    op.add_column("ppeissue", sa.Column("certificate_no", sa.String(length=255), nullable=True))
    op.add_column("ppeissue", sa.Column("wear_percent", sa.Integer(), nullable=True))
    op.add_column("ppeissue", sa.Column("return_wear_percent", sa.Integer(), nullable=True))
    op.add_column("ppeissue", sa.Column("signature_doc_ref", sa.String(length=255), nullable=True))
    op.add_column("ppeissue", sa.Column("writeoff_reason", sa.String(length=255), nullable=True))
    op.add_column("ppeissue", sa.Column("replaces_issue_id", sa.String(length=36), nullable=True))
    op.create_index("ix_ppeissue_replaces_issue_id", "ppeissue", ["replaces_issue_id"])

    # --- status: native enum -> VARCHAR(32), lowercase ------------------
    if dialect == "postgresql":
        op.execute(
            "ALTER TABLE ppeissue ALTER COLUMN status TYPE VARCHAR(32) "
            "USING lower(status::text)"
        )
        op.execute("ALTER TABLE ppeissue ALTER COLUMN status SET DEFAULT 'issued'")
        op.execute("DROP TYPE IF EXISTS ppeissuestatus")
    else:
        # SQLite: Enum is already stored as VARCHAR; just normalise case.
        with op.batch_alter_table("ppeissue") as batch:
            batch.alter_column(
                "status",
                existing_type=sa.String(length=32),
                type_=sa.String(length=32),
                existing_nullable=False,
            )
        op.execute("UPDATE ppeissue SET status = lower(status)")


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # written_off / replaced are unrepresentable in the legacy 3-value enum.
    blockers = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM ppeissue WHERE status IN ('written_off', 'replaced')"
        )
    ).scalar()
    if blockers:
        raise RuntimeError(
            "cannot downgrade sz01: ppeissue contains written_off/replaced rows "
            f"({blockers}); resolve them before downgrading"
        )

    if dialect == "postgresql":
        op.execute("ALTER TABLE ppeissue ALTER COLUMN status DROP DEFAULT")
        op.execute("CREATE TYPE ppeissuestatus AS ENUM ('ISSUED', 'RETURNED', 'LOST')")
        op.execute(
            "ALTER TABLE ppeissue ALTER COLUMN status TYPE ppeissuestatus "
            "USING upper(status)::ppeissuestatus"
        )
    else:
        op.execute("UPDATE ppeissue SET status = upper(status)")

    op.drop_index("ix_ppeissue_replaces_issue_id", table_name="ppeissue")
    op.drop_column("ppeissue", "replaces_issue_id")
    op.drop_column("ppeissue", "writeoff_reason")
    op.drop_column("ppeissue", "signature_doc_ref")
    op.drop_column("ppeissue", "return_wear_percent")
    op.drop_column("ppeissue", "wear_percent")
    op.drop_column("ppeissue", "certificate_no")
    op.drop_column("person", "ppe_sizes")
    op.drop_index("ix_ppenorm_item_id", table_name="ppenorm")
    op.drop_column("ppenorm", "item_id")
```

- [ ] **Step 5: Fix status readers/writers (`.value`-доступы ломаются на str-колонке)**

В `backend/app/api/routes/ppe.py`:
- строка ~314 (`create_issue` payload): `"status": issue.status.value` → `"status": issue.status`
- строка ~366 (`update_issue` payload): `"status": issue.status.value` → `"status": issue.status`
- в `update_issue` (строка ~345) нормализовать enum из схемы в строку ПЕРЕД setattr:

```python
    updates = payload.model_dump(exclude_unset=True)
    if isinstance(updates.get("status"), PPEIssueStatus):
        updates["status"] = updates["status"].value
```
- сравнения вида `issue.status == PPEIssueStatus.RETURNED` и `PPEIssue.status == PPEIssueStatus.ISSUED` (строки ~232, 242, 348, 352) продолжают работать (str-enum равен своей строке) — НЕ трогать, но заменить присваивание `issue.status = ...` нет (его нет, идёт через setattr).

В `backend/app/domains/ppe/service.py`:
- `issue_ppe_item` (строка ~88): `status=PPEIssueStatus.ISSUED` → `status=PPEIssueStatus.ISSUED.value`
- `list_expiring_issues` (строка ~110): сравнение `PPEIssue.status == PPEIssueStatus.ISSUED` оставить (работает), но для единообразия можно `.value` — на усмотрение.

Читатели в `modules/analytics/services.py:130`, `modules/data_quality/rules.py:410`, `modules/operational_dashboard/service.py:133` сравнивают `== PPEIssueStatus.ISSUED` — str-enum, работает с VARCHAR-колонкой, изменений НЕ требуется (проверяется регрессией в Task 9).

- [ ] **Step 6: Run tests**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_sz01_ppe_766n_migration.py backend/tests/test_ppe_lifecycle.py backend/tests/test_ppeitem_table_exists.py -p no:xdist --timeout=120 -q > test_out.txt 2>&1; Get-Content test_out.txt -Tail 10`
Expected: PASS (все)

- [ ] **Step 7: Smoke — существующий PPE API-контур не сломан**

Run: `.venv\Scripts\python.exe -m pytest tests -k "ppe" -p no:xdist --timeout=240 -q > test_out.txt 2>&1; Get-Content test_out.txt -Tail 15`
Expected: PASS (текущие ppe-тесты в корневом tests/, если есть; иначе «no tests ran» — это ок)

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/models.py backend/app/migrations/versions/20260610_sz01_ppe_norms_card_766n.py backend/app/api/routes/ppe.py backend/app/domains/ppe/service.py backend/tests/test_sz01_ppe_766n_migration.py
git commit -m "feat(ppe): sz01 migration - norm item_id, 766n requisites, VARCHAR status"
```

---

### Task 3: CRUD `/ppe/norms`

**Files:**
- Modify: `backend/app/schemas/ppe.py` (добавить норм-схемы)
- Modify: `backend/app/api/routes/ppe.py` (добавить норм-эндпоинты)
- Test: `tests/api/test_ppe_norms_api.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/test_ppe_norms_api.py
"""PPE norms CRUD: create/list/patch/delete, 409 duplicate, tenant isolation."""
from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import Position, PPEItem, RoleEnum
from app.models.risk import RiskHazard

BASE = "/api/v1/ppe/norms"


async def _seed_refs(sessionmaker, data_factory, slug="test"):
    """Position + hazard + ppe item for the default test tenant."""
    tenant = await data_factory.ensure_tenant(slug=slug)
    company = await data_factory.create_company(tenant=tenant, name=f"PPE Co {slug}")
    async with sessionmaker() as session:
        position = Position(tenant_id=tenant.id, company_id=company.id, title="Сварщик")
        hazard = RiskHazard(tenant_id=tenant.id, code=f"weld-{slug}", title="Сварочные аэрозоли")
        item = PPEItem(tenant_id=tenant.id, name=f"Щиток сварщика {slug}", default_wear_days=365)
        session.add_all([position, hazard, item])
        await session.commit()
        return str(position.id), str(hazard.id), str(item.id)


@pytest.mark.asyncio
async def test_norm_crud_roundtrip(async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    position_id, hazard_id, item_id = await _seed_refs(sessionmaker, data_factory)

    resp = await async_client.post(BASE, headers=headers, json={
        "position_id": position_id, "hazard_id": hazard_id,
        "item_id": item_id, "quantity": 2, "interval_days": 180,
    })
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    body = resp.json()
    norm_id = body["id"]
    assert body["item_id"] == item_id
    assert body["item_name"]  # денормализовано из PPEItem.name
    assert body["quantity"] == 2

    listed = await async_client.get(BASE, headers=headers, params={"position_id": position_id})
    assert listed.status_code == status.HTTP_200_OK
    assert any(n["id"] == norm_id for n in listed.json()["items"])

    patched = await async_client.patch(f"{BASE}/{norm_id}", headers=headers, json={"quantity": 3})
    assert patched.status_code == status.HTTP_200_OK
    assert patched.json()["quantity"] == 3

    deleted = await async_client.delete(f"{BASE}/{norm_id}", headers=headers)
    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    listed2 = await async_client.get(BASE, headers=headers)
    assert all(n["id"] != norm_id for n in listed2.json()["items"])


@pytest.mark.asyncio
async def test_duplicate_norm_409(async_client, make_auth_headers, sessionmaker, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    position_id, hazard_id, item_id = await _seed_refs(sessionmaker, data_factory, slug="test")
    payload = {"position_id": position_id, "hazard_id": hazard_id, "item_id": item_id}
    first = await async_client.post(BASE, headers=headers, json=payload)
    assert first.status_code == status.HTTP_201_CREATED, first.text
    dup = await async_client.post(BASE, headers=headers, json=payload)
    assert dup.status_code == status.HTTP_409_CONFLICT, dup.text


@pytest.mark.asyncio
async def test_norm_foreign_refs_must_exist_in_tenant(async_client, make_auth_headers, sessionmaker, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    position_id, hazard_id, _ = await _seed_refs(sessionmaker, data_factory)
    resp = await async_client.post(BASE, headers=headers, json={
        "position_id": position_id, "hazard_id": hazard_id, "item_id": "missing-item-id",
    })
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.text
```

Примечание для исполнителя: проверь сигнатуру `Position` (обязательные поля) в `backend/app/models/models.py` и подправь сидинг при расхождении (`title` vs `name`); схема теста от этого не меняется.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/api/test_ppe_norms_api.py -p no:xdist --timeout=240 -q > test_out.txt 2>&1; Get-Content test_out.txt -Tail 15`
Expected: FAIL — 404/405 на `/ppe/norms` (роута нет)

- [ ] **Step 3: Add schemas (`backend/app/schemas/ppe.py`, после PPEItemPage)**

```python
class PPENormCreate(BaseSchema):
    position_id: str
    hazard_id: str
    item_id: str
    quantity: int = Field(default=1, ge=1)
    interval_days: int = Field(default=365, ge=1)


class PPENormUpdate(BaseSchema):
    item_id: str | None = None
    quantity: int | None = Field(default=None, ge=1)
    interval_days: int | None = Field(default=None, ge=1)


class PPENormRead(BaseSchema):
    id: str
    position_id: str
    hazard_id: str
    item_id: str | None
    item_name: str
    quantity: int
    interval_days: int
    created_at: datetime
    updated_at: datetime


class PPENormPage(BaseSchema):
    items: list[PPENormRead]
    total: int
```

- [ ] **Step 4: Add endpoints (`backend/app/api/routes/ppe.py`)**

Импорты: добавить `PPENorm` в импорт из `app.models.ppe_registry`? — НЕТ: `PPENorm` не реэкспортирован в ppe_registry; импортировать из `app.models.models`:
```python
from app.models.models import Position, PPENorm
from app.models.risk import RiskHazard
```
Схемы — добавить `PPENormCreate, PPENormPage, PPENormRead, PPENormUpdate` в импорт из `app.schemas.ppe`.

Код эндпоинтов (вставить после блока items, перед issues):

```python
def _norm_schema(norm: PPENorm) -> PPENormRead:
    return PPENormRead.model_validate(norm)


async def _get_norm(session: AsyncSession, tenant: Tenant, norm_id: str) -> PPENorm:
    stmt = select(PPENorm).where(PPENorm.id == norm_id, PPENorm.tenant_id == tenant.id)
    norm = (await session.execute(stmt)).scalar_one_or_none()
    if norm is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PPE norm not found")
    return norm


async def _check_norm_refs(
    session: AsyncSession, tenant: Tenant, *, position_id: str, hazard_id: str, item_id: str
) -> PPEItem:
    position = (await session.execute(select(Position).where(
        Position.id == position_id, Position.tenant_id == tenant.id, Position.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if position is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Position not found")
    hazard = (await session.execute(select(RiskHazard).where(
        RiskHazard.id == hazard_id, RiskHazard.tenant_id == tenant.id,
    ))).scalar_one_or_none()
    if hazard is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hazard not found")
    return await _get_item(session, tenant, item_id)


def _norm_duplicate_conflict() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=api_problem_detail(
            code="PPE_NORM_DUPLICATE",
            message="A norm for this position/hazard/item already exists",
            error_type="ppe",
        ),
    )


@router.get("/norms", response_model=PPENormPage)
async def list_norms(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
    position_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PPENormPage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)

    stmt = select(PPENorm).where(PPENorm.tenant_id == tenant.id)
    count_stmt = select(func.count()).where(PPENorm.tenant_id == tenant.id)
    if position_id:
        stmt = stmt.where(PPENorm.position_id == position_id)
        count_stmt = count_stmt.where(PPENorm.position_id == position_id)
    stmt = stmt.order_by(PPENorm.item_name.asc()).limit(limit).offset(offset)
    norms = list((await session.execute(stmt)).scalars().all())
    total = (await session.execute(count_stmt)).scalar_one()
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=norms,
        scalars=[
            ("total", int(total or 0)), ("limit", limit), ("offset", offset),
            ("position", position_id or ""),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    return PPENormPage(items=[_norm_schema(n) for n in norms], total=total)


@router.post("/norms", response_model=PPENormRead, status_code=status.HTTP_201_CREATED)
@audit_operation("create", "ppe_norm")
async def create_norm(
    payload: PPENormCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> PPENormRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    item = await _check_norm_refs(
        session, tenant,
        position_id=payload.position_id, hazard_id=payload.hazard_id, item_id=payload.item_id,
    )
    existing = (await session.execute(select(PPENorm).where(
        PPENorm.tenant_id == tenant.id,
        PPENorm.position_id == payload.position_id,
        PPENorm.hazard_id == payload.hazard_id,
        PPENorm.item_name == item.name,
    ))).scalar_one_or_none()
    if existing is not None:
        raise _norm_duplicate_conflict()

    norm = PPENorm(
        tenant_id=tenant.id,
        position_id=payload.position_id,
        hazard_id=payload.hazard_id,
        item_id=item.id,
        item_name=item.name,  # денормализация: ключ сопоставления для legacy-строк
        quantity=payload.quantity,
        interval_days=payload.interval_days,
    )
    session.add(norm)
    await session.flush()
    await session.refresh(norm)
    return _norm_schema(norm)


@router.get("/norms/{norm_id}", response_model=PPENormRead)
async def get_norm(
    norm_id: str, tenant: TenantDep, session: SessionDep, access: ManagerAccess
) -> PPENormRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    return _norm_schema(await _get_norm(session, tenant, norm_id))


@router.patch("/norms/{norm_id}", response_model=PPENormRead)
@audit_operation("update", "ppe_norm")
async def update_norm(
    norm_id: str,
    payload: PPENormUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> PPENormRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    norm = await _get_norm(session, tenant, norm_id)
    updates = payload.model_dump(exclude_unset=True)
    new_item_id = updates.pop("item_id", None)
    if new_item_id is not None:
        item = await _get_item(session, tenant, new_item_id)
        dup = (await session.execute(select(PPENorm).where(
            PPENorm.tenant_id == tenant.id,
            PPENorm.position_id == norm.position_id,
            PPENorm.hazard_id == norm.hazard_id,
            PPENorm.item_name == item.name,
            PPENorm.id != norm.id,
        ))).scalar_one_or_none()
        if dup is not None:
            raise _norm_duplicate_conflict()
        norm.item_id = item.id
        norm.item_name = item.name
    for field, value in updates.items():
        setattr(norm, field, value)
    await session.flush()
    await session.refresh(norm)
    return _norm_schema(norm)


@router.delete("/norms/{norm_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
@audit_operation("delete", "ppe_norm")
async def delete_norm(
    norm_id: str, tenant: TenantDep, session: SessionDep, access: EditorAccess
) -> None:
    TenantContextValidator.ensure_tenant_context(tenant)
    norm = await _get_norm(session, tenant, norm_id)
    await session.delete(norm)  # PPENorm has no SoftDeleteMixin — hard delete
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

ВАЖНО (FastAPI route ordering): `/norms` — отдельный префикс, с `/items`/`/issues` не конфликтует; порядок внутри файла не критичен, но статические пути (`/issues/expiring`) должны оставаться ДО `/issues/{issue_id}` — не переставлять существующие.

- [ ] **Step 5: Run tests**

Run: `.venv\Scripts\python.exe -m pytest tests/api/test_ppe_norms_api.py -p no:xdist --timeout=240 -q > test_out.txt 2>&1; Get-Content test_out.txt -Tail 10`
Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/ppe.py backend/app/api/routes/ppe.py tests/api/test_ppe_norms_api.py
git commit -m "feat(ppe): norms CRUD with catalog link + 409 duplicate guard"
```

---

### Task 4: Операции выдачи return / writeoff / replace + FSM в legacy PATCH

**Files:**
- Modify: `backend/app/services/events.py` (EventType + payload)
- Modify: `backend/app/domains/ppe/service.py` (операции)
- Modify: `backend/app/domains/ppe/__init__.py` (реэкспорт — проверь текущее содержимое и добавь новые имена)
- Modify: `backend/app/schemas/ppe.py` (схемы операций; расширить PPEIssueRead/Create)
- Modify: `backend/app/api/routes/ppe.py` (3 эндпоинта + FSM в PATCH)
- Test: `tests/api/test_ppe_issue_operations_api.py`, `backend/tests/test_ppe_events.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_ppe_events.py
"""Payload schemas for the new PPE event types (hermetic)."""
from __future__ import annotations

from datetime import datetime, timezone

from app.services.events import (
    EventType,
    PPEReplacementDuePayload,
    PPEWrittenOffPayload,
)


def test_event_types_registered():
    assert EventType.PPE_WRITTEN_OFF.value == "PPEWrittenOff"
    assert EventType.PPE_REPLACEMENT_DUE.value == "PPEReplacementDue"


def test_written_off_payload_roundtrip():
    payload = PPEWrittenOffPayload(
        tenant_id="t1", ppe_issue_id="i1", person_id="p1", item_id=None,
        quantity=1, reason="износ", status="written_off",
    )
    assert payload.model_dump()["reason"] == "износ"


def test_replacement_due_payload_roundtrip():
    payload = PPEReplacementDuePayload(
        tenant_id="t1", ppe_issue_id="i1", person_id="p1", item_id="it1",
        item_name="Каска", expires_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        status="due_soon",
    )
    assert payload.model_dump()["item_name"] == "Каска"
```

```python
# tests/api/test_ppe_issue_operations_api.py
"""Issue lifecycle operations: return/writeoff/replace + FSM 409 + outbox."""
from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.models.models import Outbox, PPEItem, RoleEnum

ISSUES = "/api/v1/ppe/issues"


async def _seed_issue(async_client, headers, sessionmaker, data_factory) -> tuple[str, str]:
    """Create item + person + issue via API; return (issue_id, person_id)."""
    tenant = await data_factory.ensure_tenant(slug="test")
    person = await data_factory.create_person(tenant=tenant)
    async with sessionmaker() as session:
        item = PPEItem(tenant_id=tenant.id, name=f"Перчатки-{person.id[:8]}", default_wear_days=90)
        session.add(item)
        await session.commit()
        item_id = str(item.id)
    resp = await async_client.post(ISSUES, headers=headers, json={
        "person_id": str(person.id), "item_id": item_id, "quantity": 1,
        "certificate_no": "ЕАЭС RU С-RU.АБ12.В.00001/26",
    })
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    assert resp.json()["certificate_no"] == "ЕАЭС RU С-RU.АБ12.В.00001/26"
    return resp.json()["id"], str(person.id)


@pytest.mark.asyncio
async def test_return_operation(async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    issue_id, _ = await _seed_issue(async_client, headers, sessionmaker, data_factory)

    resp = await async_client.post(f"{ISSUES}/{issue_id}/return", headers=headers, json={
        "return_wear_percent": 50, "signature_doc_ref": "ведомость МБ-7 №12",
    })
    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    assert body["status"] == "returned"
    assert body["return_wear_percent"] == 50
    assert body["returned_at"] is not None

    # terminal: second operation must 409
    again = await async_client.post(f"{ISSUES}/{issue_id}/return", headers=headers, json={})
    assert again.status_code == status.HTTP_409_CONFLICT, again.text


@pytest.mark.asyncio
async def test_writeoff_operation_emits_event(async_client, make_auth_headers, sessionmaker, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    issue_id, _ = await _seed_issue(async_client, headers, sessionmaker, data_factory)

    resp = await async_client.post(f"{ISSUES}/{issue_id}/writeoff", headers=headers, json={
        "writeoff_reason": "механическое повреждение",
    })
    assert resp.status_code == status.HTTP_200_OK, resp.text
    assert resp.json()["status"] == "written_off"
    assert resp.json()["writeoff_reason"] == "механическое повреждение"

    async with sessionmaker() as session:
        rows = (await session.execute(
            select(Outbox).where(Outbox.event_type == "PPEWrittenOff")
        )).scalars().all()
        assert any(issue_id in str(r.payload) for r in rows)


@pytest.mark.asyncio
async def test_replace_operation_links_new_issue(async_client, make_auth_headers, sessionmaker, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    issue_id, person_id = await _seed_issue(async_client, headers, sessionmaker, data_factory)

    resp = await async_client.post(f"{ISSUES}/{issue_id}/replace", headers=headers, json={
        "quantity": 1, "certificate_no": "ЕАЭС RU С-RU.АБ12.В.00002/26",
    })
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    new_issue = resp.json()
    assert new_issue["replaces_issue_id"] == issue_id
    assert new_issue["status"] == "issued"
    assert new_issue["person_id"] == person_id

    old = await async_client.get(f"{ISSUES}/{issue_id}", headers=headers)
    assert old.json()["status"] == "replaced"


@pytest.mark.asyncio
async def test_legacy_patch_respects_fsm(async_client, make_auth_headers, sessionmaker, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    issue_id, _ = await _seed_issue(async_client, headers, sessionmaker, data_factory)

    ok = await async_client.patch(f"{ISSUES}/{issue_id}", headers=headers, json={"status": "returned"})
    assert ok.status_code == status.HTTP_200_OK, ok.text

    bad = await async_client.patch(f"{ISSUES}/{issue_id}", headers=headers, json={"status": "lost"})
    assert bad.status_code == status.HTTP_409_CONFLICT, bad.text
```

Примечание: имя модели Outbox/поля payload проверь по `app/models/models.py` (используется в `services/contractor_documents.py:16` — `from app.models.models import Outbox`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_ppe_events.py tests/api/test_ppe_issue_operations_api.py -p no:xdist --timeout=240 -q > test_out.txt 2>&1; Get-Content test_out.txt -Tail 15`
Expected: FAIL — нет EventType/эндпоинтов

- [ ] **Step 3: EventType + payloads (`backend/app/services/events.py`)**

После `CONTRACTOR_DOCUMENT_EXPIRED` (строка ~38):
```python
    PPE_WRITTEN_OFF = "PPEWrittenOff"
    PPE_REPLACEMENT_DUE = "PPEReplacementDue"
```
После `PPEReturnedPayload` (строка ~123):
```python
class PPEWrittenOffPayload(BaseEventPayload):
    ppe_issue_id: str
    person_id: str
    item_id: str | None
    quantity: int
    reason: str | None = None
    status: str


class PPEReplacementDuePayload(BaseEventPayload):
    ppe_issue_id: str
    person_id: str
    item_id: str | None
    item_name: str
    expires_at: datetime
    status: str
```

- [ ] **Step 4: Service operations (`backend/app/domains/ppe/service.py`)**

Импорты: добавить
```python
from app.domains.ppe import lifecycle as lc
```
и функции (после `list_expiring_issues`):

```python
async def _get_issue_record(session: AsyncSession, tenant_id: str, issue_id: str) -> PPEIssue | None:
    stmt = select(PPEIssue).where(
        PPEIssue.id == issue_id,
        PPEIssue.tenant_id == tenant_id,
        PPEIssue.deleted_at.is_(None),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def return_issue(
    session: AsyncSession,
    *,
    tenant_id: str,
    issue_id: str,
    returned_at: datetime | None = None,
    return_wear_percent: int | None = None,
    signature_doc_ref: str | None = None,
) -> PPEIssue | None:
    """Mark an issue as returned. None when not found; PPETransitionError on FSM violation."""
    issue = await _get_issue_record(session, tenant_id, issue_id)
    if issue is None:
        return None
    lc.validate_transition(str(issue.status), lc.ISSUE_STATUS_RETURNED)
    issue.status = lc.ISSUE_STATUS_RETURNED
    issue.returned_at = returned_at or datetime.now(tz=timezone.utc)
    if return_wear_percent is not None:
        issue.return_wear_percent = return_wear_percent
    if signature_doc_ref is not None:
        issue.signature_doc_ref = signature_doc_ref
    await session.flush()
    await session.refresh(issue)
    return issue


async def writeoff_issue(
    session: AsyncSession,
    *,
    tenant_id: str,
    issue_id: str,
    reason: str,
) -> PPEIssue | None:
    """Write an issue off. None when not found; PPETransitionError on FSM violation."""
    issue = await _get_issue_record(session, tenant_id, issue_id)
    if issue is None:
        return None
    lc.validate_transition(str(issue.status), lc.ISSUE_STATUS_WRITTEN_OFF)
    issue.status = lc.ISSUE_STATUS_WRITTEN_OFF
    issue.writeoff_reason = reason
    await session.flush()
    await session.refresh(issue)
    return issue


async def replace_issue(
    session: AsyncSession,
    *,
    tenant_id: str,
    issue_id: str,
    item_id: str | None = None,
    quantity: int | None = None,
    wear_days: int | None = None,
    expires_at: datetime | None = None,
    certificate_no: str | None = None,
    wear_percent: int | None = None,
    signature_doc_ref: str | None = None,
) -> tuple[PPEIssue, PPEIssue] | None:
    """Close the old issue as replaced and create a linked new one.

    Returns (old, new) or None when the old issue is not found.
    Raises PPETransitionError when the old issue is not active.
    """
    old = await _get_issue_record(session, tenant_id, issue_id)
    if old is None:
        return None
    lc.validate_transition(str(old.status), lc.ISSUE_STATUS_REPLACED)

    new_item_id = item_id or old.item_id
    if new_item_id is None:
        raise ValueError("cannot replace an issue without item_id: specify item_id")

    new = await issue_ppe_item(
        session,
        tenant_id=tenant_id,
        person_id=old.person_id,
        item_id=new_item_id,
        quantity=quantity or old.quantity,
        wear_days=wear_days,
        expires_at=expires_at,
    )
    new.replaces_issue_id = old.id
    if certificate_no is not None:
        new.certificate_no = certificate_no
    if wear_percent is not None:
        new.wear_percent = wear_percent
    if signature_doc_ref is not None:
        new.signature_doc_ref = signature_doc_ref

    old.status = lc.ISSUE_STATUS_REPLACED
    await session.flush()
    await session.refresh(new)
    await session.refresh(old)
    return old, new
```

Также в `issue_ppe_item` добавить опциональные параметры реквизитов (для POST /issues):
```python
    certificate_no: str | None = None,
    wear_percent: int | None = None,
    signature_doc_ref: str | None = None,
```
и пробросить их в конструктор `PPEIssue(...)`:
```python
        certificate_no=certificate_no,
        wear_percent=wear_percent,
        signature_doc_ref=signature_doc_ref,
```

Проверь `backend/app/domains/ppe/__init__.py` и добавь в реэкспорт: `return_issue, writeoff_issue, replace_issue`.

- [ ] **Step 5: Schemas (`backend/app/schemas/ppe.py`)**

`PPEIssueCreate` — добавить поля:
```python
    certificate_no: str | None = Field(default=None, max_length=255)
    wear_percent: int | None = Field(default=None, ge=0, le=100)
    signature_doc_ref: str | None = Field(default=None, max_length=255)
```
`PPEIssueRead` — добавить поля:
```python
    certificate_no: str | None
    wear_percent: int | None
    return_wear_percent: int | None
    signature_doc_ref: str | None
    writeoff_reason: str | None
    replaces_issue_id: str | None
```
Новые схемы операций:
```python
class PPEIssueReturnRequest(BaseSchema):
    returned_at: datetime | None = None
    return_wear_percent: int | None = Field(default=None, ge=0, le=100)
    signature_doc_ref: str | None = Field(default=None, max_length=255)


class PPEIssueWriteoffRequest(BaseSchema):
    writeoff_reason: str = Field(min_length=1, max_length=255)


class PPEIssueReplaceRequest(BaseSchema):
    item_id: str | None = None  # default: тот же item, что у заменяемой выдачи
    quantity: int | None = Field(default=None, ge=1)
    wear_days: int | None = Field(default=None, ge=1)
    expires_at: datetime | None = None
    certificate_no: str | None = Field(default=None, max_length=255)
    wear_percent: int | None = Field(default=None, ge=0, le=100)
    signature_doc_ref: str | None = Field(default=None, max_length=255)
```

- [ ] **Step 6: Routes (`backend/app/api/routes/ppe.py`)**

Импорты: `return_issue, writeoff_issue, replace_issue` из `app.domains.ppe`; `PPETransitionError` из `app.domains.ppe.lifecycle`; новые схемы. Пробросить реквизиты в `create_issue` (передать `certificate_no=payload.certificate_no, wear_percent=payload.wear_percent, signature_doc_ref=payload.signature_doc_ref` в `issue_ppe_item`).

Хелпер 409:
```python
def _transition_conflict(exc: PPETransitionError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=api_problem_detail(
            code="PPE_TRANSITION_INVALID",
            message=str(exc),
            error_type="ppe",
        ),
    )
```

Эндпоинты — вставить ПЕРЕД `@router.get("/issues/{issue_id}")` (FastAPI матчит по порядку; `/issues/{issue_id}/return` содержит фикс-сегмент после параметра, конфликта нет, но держим операции рядом с PATCH):

```python
@router.post("/issues/{issue_id}/return", response_model=PPEIssueRead)
@audit_operation("update", "ppe_issue")
async def return_issue_endpoint(
    issue_id: str,
    payload: PPEIssueReturnRequest,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> PPEIssueRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        issue = await return_issue(
            session, tenant_id=tenant.id, issue_id=issue_id,
            returned_at=payload.returned_at,
            return_wear_percent=payload.return_wear_percent,
            signature_doc_ref=payload.signature_doc_ref,
        )
    except PPETransitionError as exc:
        raise _transition_conflict(exc) from exc
    if issue is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PPE issue not found")
    outbox = OutboxService(session)
    await outbox.enqueue(
        tenant_id=str(tenant.id),
        event_type=EventType.PPE_RETURNED.value,
        payload={
            "tenant_id": str(tenant.id),
            "actor_id": access.user.id if access else None,
            "occurred_at": issue.returned_at,
            "ppe_issue_id": issue.id,
            "person_id": issue.person_id,
            "item_id": issue.item_id,
            "quantity": issue.quantity,
            "returned_at": issue.returned_at,
            "status": issue.status,
        },
    )
    return _issue_schema(issue)


@router.post("/issues/{issue_id}/writeoff", response_model=PPEIssueRead)
@audit_operation("update", "ppe_issue")
async def writeoff_issue_endpoint(
    issue_id: str,
    payload: PPEIssueWriteoffRequest,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> PPEIssueRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        issue = await writeoff_issue(
            session, tenant_id=tenant.id, issue_id=issue_id, reason=payload.writeoff_reason,
        )
    except PPETransitionError as exc:
        raise _transition_conflict(exc) from exc
    if issue is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PPE issue not found")
    outbox = OutboxService(session)
    await outbox.enqueue(
        tenant_id=str(tenant.id),
        event_type=EventType.PPE_WRITTEN_OFF.value,
        payload={
            "tenant_id": str(tenant.id),
            "actor_id": access.user.id if access else None,
            "occurred_at": datetime.now(timezone.utc),
            "ppe_issue_id": issue.id,
            "person_id": issue.person_id,
            "item_id": issue.item_id,
            "quantity": issue.quantity,
            "reason": issue.writeoff_reason,
            "status": issue.status,
        },
    )
    return _issue_schema(issue)


@router.post(
    "/issues/{issue_id}/replace",
    response_model=PPEIssueRead,
    status_code=status.HTTP_201_CREATED,
)
@audit_operation("update", "ppe_issue")
async def replace_issue_endpoint(
    issue_id: str,
    payload: PPEIssueReplaceRequest,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> PPEIssueRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        result = await replace_issue(
            session, tenant_id=tenant.id, issue_id=issue_id,
            item_id=payload.item_id, quantity=payload.quantity,
            wear_days=payload.wear_days, expires_at=payload.expires_at,
            certificate_no=payload.certificate_no, wear_percent=payload.wear_percent,
            signature_doc_ref=payload.signature_doc_ref,
        )
    except PPETransitionError as exc:
        raise _transition_conflict(exc) from exc
    except ValueError as exc:
        raise _ppe_bad_request(str(exc)) from exc
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PPE issue not found")
    _old, new_issue = result
    outbox = OutboxService(session)
    await outbox.enqueue(
        tenant_id=str(tenant.id),
        event_type=EventType.PPE_ISSUED.value,
        payload={
            "tenant_id": str(tenant.id),
            "actor_id": access.user.id if access else None,
            "occurred_at": new_issue.issued_at,
            "ppe_issue_id": new_issue.id,
            "person_id": new_issue.person_id,
            "item_id": new_issue.item_id,
            "quantity": new_issue.quantity,
            "issued_at": new_issue.issued_at,
            "expires_at": new_issue.expires_at,
            "status": new_issue.status,
        },
    )
    return _issue_schema(new_issue)
```

FSM в legacy PATCH `update_issue` (после `updates = payload.model_dump(exclude_unset=True)` и нормализации enum→str из Task 2):
```python
    new_status = updates.get("status")
    if new_status is not None and new_status != issue.status:
        try:
            validate_transition(str(issue.status), str(new_status))
        except PPETransitionError as exc:
            raise _transition_conflict(exc) from exc
```
(импортировать `validate_transition` из `app.domains.ppe.lifecycle`).

- [ ] **Step 7: Run tests**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_ppe_events.py tests/api/test_ppe_issue_operations_api.py -p no:xdist --timeout=240 -q > test_out.txt 2>&1; Get-Content test_out.txt -Tail 10`
Expected: `8 passed` (3 + 5)

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/events.py backend/app/domains/ppe/ backend/app/schemas/ppe.py backend/app/api/routes/ppe.py backend/tests/test_ppe_events.py tests/api/test_ppe_issue_operations_api.py
git commit -m "feat(ppe): explicit issue lifecycle - return/writeoff/replace + FSM-guarded PATCH"
```

---

### Task 5: Размеры работника + личная карточка 766н

**Files:**
- Modify: `backend/app/domains/ppe/service.py` (`build_personal_card_766n`)
- Modify: `backend/app/schemas/ppe.py` (карточка + sizes)
- Modify: `backend/app/api/routes/ppe.py` (2 эндпоинта)
- Test: `tests/test_ppe_personal_card_766n.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ppe_personal_card_766n.py
"""766н personal card: header+sizes, required-vs-issued, line statuses, timeline."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import status
from sqlalchemy import select

from app.models.models import Position, PPEIssue, PPEItem, PPENorm, RoleEnum
from app.models.risk import RiskHazard

CARD = "/api/v1/ppe/employees/{person_id}/card"
SIZES = "/api/v1/ppe/employees/{person_id}/sizes"

NOW = datetime.now(tz=timezone.utc)


async def _seed_card_world(sessionmaker, data_factory):
    """Person on a position with 2 norms; 1 active issue, 1 expired, 1 norm uncovered."""
    tenant = await data_factory.ensure_tenant(slug="test")
    company = await data_factory.create_company(tenant=tenant, name="Card Co")
    async with sessionmaker() as session:
        position = Position(tenant_id=tenant.id, company_id=company.id, title="Монтажник")
        hazard = RiskHazard(tenant_id=tenant.id, code="height", title="Работы на высоте")
        helmet = PPEItem(tenant_id=tenant.id, name="Каска защитная", default_wear_days=730)
        belt = PPEItem(tenant_id=tenant.id, name="Пояс страховочный", default_wear_days=365)
        session.add_all([position, hazard, helmet, belt])
        await session.flush()
        person = None  # created via factory below (needs company/tenant ids)
        norm_helmet = PPENorm(
            tenant_id=tenant.id, position_id=position.id, hazard_id=hazard.id,
            item_id=helmet.id, item_name=helmet.name, quantity=1, interval_days=730,
        )
        norm_belt = PPENorm(
            tenant_id=tenant.id, position_id=position.id, hazard_id=hazard.id,
            item_id=belt.id, item_name=belt.name, quantity=1, interval_days=365,
        )
        session.add_all([norm_helmet, norm_belt])
        await session.commit()
        position_id, helmet_id, belt_id = str(position.id), str(helmet.id), str(belt.id)

    person = await data_factory.create_person(
        tenant=tenant, company=company, position_id=position_id,
        ppe_sizes={"height": 180, "headgear_size": "58"},
    )
    async with sessionmaker() as session:
        # активная выдача каски (далеко до истечения)
        session.add(PPEIssue(
            tenant_id=tenant.id, person_id=person.id, item_id=helmet_id,
            item_name="Каска защитная", quantity=1, issued_at=NOW,
            expires_at=NOW + timedelta(days=400), status="issued",
            certificate_no="CERT-1",
        ))
        # просроченная выдача пояса не закрывает норму? нет: активная, но истекла → overdue
        session.add(PPEIssue(
            tenant_id=tenant.id, person_id=person.id, item_id=belt_id,
            item_name="Пояс страховочный", quantity=1,
            issued_at=NOW - timedelta(days=400),
            expires_at=NOW - timedelta(days=35), status="issued",
        ))
        await session.commit()
    return str(person.id)


@pytest.mark.asyncio
async def test_card_full_shape(async_client, make_auth_headers, sessionmaker, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    person_id = await _seed_card_world(sessionmaker, data_factory)

    resp = await async_client.get(CARD.format(person_id=person_id), headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
    card = resp.json()

    assert card["person_id"] == person_id
    assert card["position_name"] == "Монтажник"
    assert card["sizes"] == {"height": 180, "headgear_size": "58"}

    lines = {line["item_name"]: line for line in card["required"]}
    assert lines["Каска защитная"]["status"] == "ok"
    assert lines["Пояс страховочный"]["status"] == "overdue"
    assert card["summary_status"] == "overdue"

    assert len(card["issues"]) == 2
    events = [e["event"] for e in card["timeline"]]
    assert events.count("issued") == 2


@pytest.mark.asyncio
async def test_card_missing_line_when_no_issue(async_client, make_auth_headers, sessionmaker, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    tenant = await data_factory.ensure_tenant(slug="test")
    company = await data_factory.create_company(tenant=tenant, name="Missing Co")
    async with sessionmaker() as session:
        position = Position(tenant_id=tenant.id, company_id=company.id, title="Лаборант")
        hazard = RiskHazard(tenant_id=tenant.id, code="chem", title="Химфактор")
        gloves = PPEItem(tenant_id=tenant.id, name="Перчатки КЩС", default_wear_days=30)
        session.add_all([position, hazard, gloves])
        await session.flush()
        session.add(PPENorm(
            tenant_id=tenant.id, position_id=position.id, hazard_id=hazard.id,
            item_id=gloves.id, item_name=gloves.name, quantity=2, interval_days=30,
        ))
        await session.commit()
        position_id = str(position.id)
    person = await data_factory.create_person(tenant=tenant, company=company, position_id=position_id)

    resp = await async_client.get(CARD.format(person_id=str(person.id)), headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
    card = resp.json()
    assert card["required"][0]["status"] == "missing"
    assert card["summary_status"] == "missing"


@pytest.mark.asyncio
async def test_card_404_for_unknown_person(async_client, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.get(CARD.format(person_id="nope"), headers=headers)
    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_put_sizes_validates_and_persists(async_client, make_auth_headers, sessionmaker, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    tenant = await data_factory.ensure_tenant(slug="test")
    person = await data_factory.create_person(tenant=tenant)

    resp = await async_client.put(SIZES.format(person_id=str(person.id)), headers=headers, json={
        "height": 175, "clothing_size": "52-54", "shoe_size": "43",
    })
    assert resp.status_code == status.HTTP_200_OK, resp.text
    assert resp.json()["sizes"]["clothing_size"] == "52-54"

    bad = await async_client.put(SIZES.format(person_id=str(person.id)), headers=headers, json={
        "height": 999,
    })
    assert bad.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
```

Примечание: `create_person(..., position_id=..., ppe_sizes=...)` идут через `**overrides` фабрики — это колонки Person, сработает.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ppe_personal_card_766n.py -p no:xdist --timeout=240 -q > test_out.txt 2>&1; Get-Content test_out.txt -Tail 15`
Expected: FAIL — 404 на новых путях

- [ ] **Step 3: Service (`backend/app/domains/ppe/service.py`)**

```python
@dataclass(slots=True)
class CardRequiredLine:
    item_id: str | None
    item_name: str
    required_quantity: int
    interval_days: int | None
    status: str


@dataclass(slots=True)
class CardTimelineEvent:
    occurred_at: datetime
    event: str
    issue_id: str
    item_name: str


@dataclass(slots=True)
class PersonalCard766n:
    person: Person
    position: Position | None
    required: list[CardRequiredLine]
    issues: list[PPEIssue]
    timeline: list[CardTimelineEvent]
    summary_status: str


def _issue_line_key(item_id: str | None, item_name: str) -> str:
    return item_id or f"name:{item_name}"


async def build_personal_card_766n(
    session: AsyncSession, *, tenant_id: str, person_id: str
) -> PersonalCard766n | None:
    """766н personal card: required-by-norms vs issued, with line statuses and timeline.

    Required quantities are the max per catalog item across the position's norms
    (union over hazards). Issues are matched by item_id, with an item_name
    fallback for legacy norms that predate the catalog link.
    """
    stmt = select(Person).where(
        Person.id == person_id,
        Person.tenant_id == tenant_id,
        Person.deleted_at.is_(None),
    )
    person = (await session.execute(stmt)).scalar_one_or_none()
    if person is None:
        return None

    position: Position | None = None
    norms: list[PPENorm] = []
    if person.position_id:
        position = await _get_position(session, tenant_id, person.position_id)
        norms = list((await session.execute(select(PPENorm).where(
            PPENorm.tenant_id == tenant_id,
            PPENorm.position_id == person.position_id,
        ))).scalars().all())

    issues = list((await session.execute(
        select(PPEIssue).where(
            PPEIssue.tenant_id == tenant_id,
            PPEIssue.person_id == person.id,
            PPEIssue.deleted_at.is_(None),
        ).order_by(PPEIssue.issued_at.asc())
    )).scalars().all())

    # «Положено»: max по позиции каталога через переиспользуемый required_union.
    norm_items = [
        NormItem(
            applies_to_type="position",
            applies_to_id=str(person.position_id),
            ppe_catalog_id=_issue_line_key(norm.item_id, norm.item_name),
            quantity=float(norm.quantity),
            period_months=None,
        )
        for norm in norms
    ]
    required_qty = PPENormService.required_union(
        position_id=str(person.position_id) if person.position_id else None,
        workplace_id=None,
        hazard_ids=set(),
        norm_items=norm_items,
    )
    # Метаданные строки (имя/интервал) — по «лучшей» норме того же ключа.
    line_meta: dict[str, PPENorm] = {}
    for norm in norms:
        key = _issue_line_key(norm.item_id, norm.item_name)
        kept = line_meta.get(key)
        if kept is None or norm.quantity > kept.quantity:
            line_meta[key] = norm

    issues_by_key: dict[str, list[lc.IssueView]] = {}
    for issue in issues:
        key = _issue_line_key(issue.item_id, issue.item_name)
        issues_by_key.setdefault(key, []).append(lc.IssueView(
            quantity=issue.quantity,
            expires_at=issue.expires_at.date() if issue.expires_at else None,
            status=str(issue.status),
        ))

    today = datetime.now(tz=timezone.utc).date()
    required: list[CardRequiredLine] = []
    for key, qty in required_qty.items():
        norm = line_meta[key]
        required.append(CardRequiredLine(
            item_id=norm.item_id,
            item_name=norm.item_name,
            required_quantity=int(qty),
            interval_days=norm.interval_days,
            status=lc.card_line_status(int(qty), issues_by_key.get(key, []), today),
        ))
    required.sort(key=lambda line: line.item_name)

    timeline: list[CardTimelineEvent] = []
    for issue in issues:
        timeline.append(CardTimelineEvent(
            occurred_at=issue.issued_at, event="issued",
            issue_id=issue.id, item_name=issue.item_name,
        ))
        current = str(issue.status)
        if current == lc.ISSUE_STATUS_RETURNED and issue.returned_at is not None:
            timeline.append(CardTimelineEvent(
                occurred_at=issue.returned_at, event="returned",
                issue_id=issue.id, item_name=issue.item_name,
            ))
        elif current in (lc.ISSUE_STATUS_WRITTEN_OFF, lc.ISSUE_STATUS_REPLACED, lc.ISSUE_STATUS_LOST):
            timeline.append(CardTimelineEvent(
                occurred_at=issue.updated_at, event=current,
                issue_id=issue.id, item_name=issue.item_name,
            ))
    timeline.sort(key=lambda e: e.occurred_at)

    return PersonalCard766n(
        person=person,
        position=position,
        required=required,
        issues=issues,
        timeline=timeline,
        summary_status=lc.fold_card_status(line.status for line in required),
    )
```

Импорты, которые нужно добавить в service.py:
```python
from app.domains.ppe import lifecycle as lc
from app.modules.ppe.services import NormItem, PPENormService
```
(NB: `_get_person` в существующем коде использует `.scalar_one()` — для карточки нужен `scalar_one_or_none`, поэтому отдельный запрос выше, `_get_person` не трогать.)

- [ ] **Step 4: Schemas (`backend/app/schemas/ppe.py`)**

```python
class PPECardRequiredLine(BaseSchema):
    item_id: str | None
    item_name: str
    required_quantity: int
    interval_days: int | None
    status: str


class PPECardTimelineEvent(BaseSchema):
    occurred_at: datetime
    event: str
    issue_id: str
    item_name: str


class PPECardRead(BaseSchema):
    person_id: str
    full_name: str
    personnel_number: str | None
    hired_at: date | None
    position_name: str | None
    sizes: dict[str, Any] | None
    required: list[PPECardRequiredLine]
    issues: list[PPEIssueRead]
    timeline: list[PPECardTimelineEvent]
    summary_status: str


class PPESizesUpdate(BaseSchema):
    height: int | None = Field(default=None, ge=100, le=250)
    clothing_size: str | None = Field(default=None, max_length=16)
    shoe_size: str | None = Field(default=None, max_length=16)
    headgear_size: str | None = Field(default=None, max_length=16)
    gas_mask_size: str | None = Field(default=None, max_length=16)
    respirator_size: str | None = Field(default=None, max_length=16)
    gloves_size: str | None = Field(default=None, max_length=16)
    mittens_size: str | None = Field(default=None, max_length=16)


class PPESizesRead(BaseSchema):
    person_id: str
    sizes: dict[str, Any] | None
```

- [ ] **Step 5: Routes (`backend/app/api/routes/ppe.py`)**

Импорты: `build_personal_card_766n` из `app.domains.ppe`; `Person` из `app.models.models`; схемы. Добавить в `app.domains.ppe.__init__` реэкспорт `build_personal_card_766n`.

```python
@router.get("/employees/{person_id}/card", response_model=PPECardRead)
async def get_personal_card(
    person_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
) -> PPECardRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    card = await build_personal_card_766n(session, tenant_id=tenant.id, person_id=person_id)
    if card is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Person not found")
    person = card.person
    full_name = " ".join(part for part in (person.last_name, person.first_name, person.middle_name) if part)
    return PPECardRead(
        person_id=person.id,
        full_name=full_name,
        personnel_number=person.personnel_number,
        hired_at=person.hired_at,
        position_name=card.position.title if card.position else None,
        sizes=person.ppe_sizes,
        required=[
            PPECardRequiredLine(
                item_id=line.item_id, item_name=line.item_name,
                required_quantity=line.required_quantity,
                interval_days=line.interval_days, status=line.status,
            )
            for line in card.required
        ],
        issues=[_issue_schema(issue) for issue in card.issues],
        timeline=[
            PPECardTimelineEvent(
                occurred_at=event.occurred_at, event=event.event,
                issue_id=event.issue_id, item_name=event.item_name,
            )
            for event in card.timeline
        ],
        summary_status=card.summary_status,
    )


@router.put("/employees/{person_id}/sizes", response_model=PPESizesRead)
@audit_operation("update", "person_ppe_sizes")
async def put_person_sizes(
    person_id: str,
    payload: PPESizesUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> PPESizesRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    person = (await session.execute(select(Person).where(
        Person.id == person_id,
        Person.tenant_id == tenant.id,
        Person.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Person not found")
    # PUT-семантика: полная замена; None-поля выбрасываются.
    person.ppe_sizes = {
        key: value
        for key, value in payload.model_dump().items()
        if value is not None
    } or None
    await session.flush()
    await session.refresh(person)
    return PPESizesRead(person_id=person.id, sizes=person.ppe_sizes)
```

NB: проверь имя поля названия должности в `Position` (`title` или `name`) — в `position.title if card.position else None` подставь фактическое (см. модель `Position` в models.py); тест выше сидит `title="Монтажник"` — поправь обе стороны согласованно по факту модели.

- [ ] **Step 6: Run tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ppe_personal_card_766n.py -p no:xdist --timeout=240 -q > test_out.txt 2>&1; Get-Content test_out.txt -Tail 10`
Expected: `4 passed`

- [ ] **Step 7: Commit**

```bash
git add backend/app/domains/ppe/ backend/app/schemas/ppe.py backend/app/api/routes/ppe.py tests/test_ppe_personal_card_766n.py
git commit -m "feat(ppe): 766n personal card endpoint + employee sizes PUT"
```

---

### Task 6: notify_replacement_due + beat `ppe.expiry.tick`

**Files:**
- Create: `backend/app/services/ppe_notifications.py`
- Modify: `backend/app/tasks/_core.py` (после `_contractors_documents_tick`, ~строка 2032)
- Modify: `backend/app/services/celery_app.py` (beat_schedule, ~строка 80)
- Test: `tests/test_ppe_replacement_due_tick.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ppe_replacement_due_tick.py
"""notify_replacement_due: horizon scan + same-day idempotency."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.models import Outbox, PPEIssue, PPEItem
from app.services.ppe_notifications import notify_replacement_due

NOW = datetime.now(tz=timezone.utc)


async def _seed_issues(sessionmaker, data_factory):
    tenant = await data_factory.ensure_tenant(slug="test")
    person = await data_factory.create_person(tenant=tenant)
    async with sessionmaker() as session:
        item = PPEItem(tenant_id=tenant.id, name=f"Очки-{person.id[:8]}", default_wear_days=180)
        session.add(item)
        await session.flush()
        session.add_all([
            PPEIssue(  # истекает через 10 дней → due_soon
                tenant_id=tenant.id, person_id=person.id, item_id=item.id,
                item_name=item.name, quantity=1, issued_at=NOW - timedelta(days=170),
                expires_at=NOW + timedelta(days=10), status="issued",
            ),
            PPEIssue(  # просрочена → overdue
                tenant_id=tenant.id, person_id=person.id, item_id=item.id,
                item_name=item.name, quantity=1, issued_at=NOW - timedelta(days=200),
                expires_at=NOW - timedelta(days=20), status="issued",
            ),
            PPEIssue(  # далеко → не событие
                tenant_id=tenant.id, person_id=person.id, item_id=item.id,
                item_name=item.name, quantity=1, issued_at=NOW,
                expires_at=NOW + timedelta(days=300), status="issued",
            ),
            PPEIssue(  # возвращена → не событие
                tenant_id=tenant.id, person_id=person.id, item_id=item.id,
                item_name=item.name, quantity=1, issued_at=NOW - timedelta(days=170),
                expires_at=NOW + timedelta(days=5), status="returned",
            ),
        ])
        await session.commit()
    return str(tenant.id)


@pytest.mark.asyncio
async def test_notify_replacement_due_scans_and_dedups(sessionmaker, data_factory):
    tenant_id = await _seed_issues(sessionmaker, data_factory)

    async with sessionmaker() as session:
        first = await notify_replacement_due(session, tenant_id=tenant_id)
        await session.commit()
    assert first == 2  # due_soon + overdue

    async with sessionmaker() as session:
        second = await notify_replacement_due(session, tenant_id=tenant_id)
        await session.commit()
    assert second == 0  # same-day idempotent

    async with sessionmaker() as session:
        rows = (await session.execute(
            select(Outbox).where(Outbox.event_type == "PPEReplacementDue")
        )).scalars().all()
        assert len(rows) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ppe_replacement_due_tick.py -p no:xdist --timeout=240 -q > test_out.txt 2>&1; Get-Content test_out.txt -Tail 10`
Expected: FAIL — `ModuleNotFoundError: app.services.ppe_notifications`

- [ ] **Step 3: Service**

```python
# backend/app/services/ppe_notifications.py
"""PPE replacement-due notifications.

Mirrors ``contractor_documents.notify_document_expiry``: scan the tenant's
active issues with an expiry date, classify, enqueue one outbox event per
(issue, status, UTC day). Idempotent via the idempotency key + a destination-
agnostic pre-check (see contractor_documents._outbox_key_exists for the why).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.ppe.lifecycle import ISSUE_STATUS_ISSUED
from app.domains.shared import ContingentItemStatus, classify
from app.models.models import Outbox, PPEIssue
from app.services.events import EventType
from app.services.outbox import OutboxService

_NOTIFY_STATUSES = {ContingentItemStatus.DUE_SOON, ContingentItemStatus.OVERDUE}


async def _outbox_key_exists(session: AsyncSession, *, tenant_id: str, key: str) -> bool:
    stmt = select(Outbox.id).where(
        Outbox.tenant_id == tenant_id,
        Outbox.idempotency_key == key,
    ).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def notify_replacement_due(
    session: AsyncSession, *, tenant_id: str, within_days: int = 30
) -> int:
    """Enqueue PPE_REPLACEMENT_DUE for due-soon/overdue active issues. Returns count."""
    stmt = select(PPEIssue).where(
        PPEIssue.tenant_id == tenant_id,
        PPEIssue.deleted_at.is_(None),
        PPEIssue.status == ISSUE_STATUS_ISSUED,
        PPEIssue.expires_at.is_not(None),
    )
    issues = list((await session.execute(stmt)).scalars().all())

    today = datetime.now(timezone.utc).date()
    outbox = OutboxService(session)
    count = 0
    for issue in issues:
        expiry = classify(issue.expires_at.date(), today, warning_days=within_days)
        if expiry not in _NOTIFY_STATUSES:
            continue
        idem_key = f"ppe-replacement-due:{issue.id}:{expiry.value}:{today.isoformat()}"
        if await _outbox_key_exists(session, tenant_id=tenant_id, key=idem_key):
            continue
        await outbox.enqueue(
            tenant_id=tenant_id,
            event_type=EventType.PPE_REPLACEMENT_DUE.value,
            idempotency_key=idem_key,
            payload={
                "tenant_id": tenant_id,
                "ppe_issue_id": issue.id,
                "person_id": issue.person_id,
                "item_id": issue.item_id,
                "item_name": issue.item_name,
                "expires_at": issue.expires_at.isoformat(),
                "status": expiry.value,
            },
        )
        count += 1
    return count
```

- [ ] **Step 4: Beat task (`backend/app/tasks/_core.py`, после `_contractors_documents_tick`)**

```python
@celery_app.task(
    name="ppe.expiry.tick",
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def ppe_expiry_tick() -> int:
    return _run_coroutine(_ppe_expiry_tick())


async def _ppe_expiry_tick() -> int:
    from app.services.ppe_notifications import notify_replacement_due

    async with AsyncSessionLocal(tenant=settings.default_tenant_slug) as session:
        tenants = list(
            (await session.execute(select(Tenant).where(Tenant.is_active.is_(True)))).scalars().all()
        )
    total = 0
    for tenant in tenants:
        with tenant_context(tenant.slug):
            ensure_tenant_schema(tenant.slug)
            async with session_scope(tenant=tenant.slug) as session:
                tenant_id, _scope = await _resolve_task_tenant_scope(session, tenant.slug)
                # Enqueue then commit — события атомарны с чтением; notify дедупит
                # по (issue, status, day), поэтому autoretry безопасен.
                total += await notify_replacement_due(session, tenant_id=tenant_id)
                await session.commit()
    return total
```

beat_schedule (`backend/app/services/celery_app.py`, после `contractors-documents-daily`):
```python
    "ppe-expiry-daily": {
        "task": "ppe.expiry.tick",
        "schedule": crontab(hour=4, minute=15),
    },
```

- [ ] **Step 5: Run tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ppe_replacement_due_tick.py backend/tests/test_ppe_events.py -p no:xdist --timeout=240 -q > test_out.txt 2>&1; Get-Content test_out.txt -Tail 10`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/ppe_notifications.py backend/app/tasks/_core.py backend/app/services/celery_app.py tests/test_ppe_replacement_due_tick.py
git commit -m "feat(ppe): replacement-due notifications + ppe.expiry.tick beat"
```

---

### Task 7: Чистка ORM-долга — семейство B + WarehousePPE

**Files:**
- Modify: `backend/app/models/safety_core.py` (удалить 6 PPE-классов, строки ~207–298)
- Modify: `backend/app/models/models.py` (удалить `WarehousePPE`, ~строка 2321)
- Modify: `backend/app/models/ppe_registry.py` (убрать WarehousePPE)
- Modify: `backend/app/models/__init__.py` (убрать реэкспорты удалённых классов, если есть)

- [ ] **Step 1: Inventory imports (обязателен ПЕРЕД удалением)**

Run: `rg -n "WarehousePPE|PPECatalog|PPENormItem|PPEPersonalCard|PPEPersonalCardItem" --type py backend tests frontend 2>$null` (через Grep-инструмент)
И отдельно для дублей имён (важно отличать models.py-класс от safety_core-класса):
`rg -n "from app.models.safety_core import" --type py`

Ожидаемое: упоминания только в `safety_core.py`, `models.py` (WarehousePPE), `ppe_registry.py`, `models/__init__.py`, миграции `20260401_next58_safety_core.py` (НЕ трогать) и, возможно, тестах. `domains/ppe/service.py` содержит СВОЙ dataclass `PPEPersonalCard` (строка ~24) — НЕ трогать; `PersonalCard766n` из Task 5 тоже не трогать. Любое НЕинвентаризованное живое использование — STOP, доложить в финальном отчёте, не удалять этот символ.

- [ ] **Step 2: Delete**

- `safety_core.py`: удалить классы `PPENorm`, `PPECatalog`, `PPENormItem`, `PPEIssue`, `PPEPersonalCard`, `PPEPersonalCardItem` (строки ~207–298). Оставить комментарий-надгробие:
```python
# PPE family-B ORM classes (PPENorm/PPECatalog/PPENormItem/PPEIssue/
# PPEPersonalCard/PPEPersonalCardItem) were removed in СИЗ Срез-1 (2026-06-10):
# they had no API and duplicated the live family in models.py (см.
# docs/superpowers/specs/2026-06-10-ppe-norms-personal-card-design.md §7).
# Их таблицы (ppe_norms, ppe_catalog, ...) остаются в БД (миграция next58);
# DROP — отдельная миграция вне среза.
```
- `models.py`: удалить класс `WarehousePPE` (строка ~2321).
- `ppe_registry.py`: убрать `WarehousePPE` из импорта и `__all__`.
- `models/__init__.py`: убрать ссылки на удалённые имена (проверить grep'ом).

- [ ] **Step 3: Verify mappers + existing tests still green**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_next58_safety_core_services.py backend/tests/test_ppe_lifecycle.py backend/tests/test_sz01_ppe_766n_migration.py -p no:xdist --timeout=120 -q > test_out.txt 2>&1; Get-Content test_out.txt -Tail 10`
Expected: PASS (`test_next58_safety_core_services` тестирует чистые сервисы `modules/ppe/services.py` — они не удалялись)

Также прогнать guard-тест мапперов (имя файла найти: `rg -ln "configure_mappers" backend/tests tests`):
Run: `.venv\Scripts\python.exe -m pytest <найденный файл> -p no:xdist --timeout=120 -q > test_out.txt 2>&1; Get-Content test_out.txt -Tail 5`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/safety_core.py backend/app/models/models.py backend/app/models/ppe_registry.py backend/app/models/__init__.py
git commit -m "refactor(ppe): drop orphan family-B ORM classes + WarehousePPE (tables kept)"
```

---

### Task 8: Demo-seed

**Files:**
- Modify: `backend/app/services/demo_bootstrap.py`
- Test: `tests/test_demo_bootstrap_ppe.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_demo_bootstrap_ppe.py
"""Demo bootstrap seeds PPE norms, sizes and issues covering all card statuses."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.services.demo_bootstrap import _seed_ppe_demo
from app.models.models import Person, Position, PPEIssue, PPEItem, PPENorm
from app.models.risk import RiskHazard


@pytest.mark.asyncio
async def test_seed_ppe_demo_idempotent(sessionmaker, data_factory):
    tenant = await data_factory.ensure_tenant(slug="test")
    company = await data_factory.create_company(tenant=tenant, name="Demo PPE Co")
    async with sessionmaker() as session:
        position = Position(tenant_id=tenant.id, company_id=company.id, title="Демо-должность")
        session.add(position)
        await session.commit()
        position_id = str(position.id)
    person = await data_factory.create_person(tenant=tenant, company=company, position_id=position_id)

    async with sessionmaker() as session:
        person_row = (await session.execute(select(Person).where(Person.id == person.id))).scalar_one()
        await _seed_ppe_demo(session, str(tenant.id), person_row, position_id)
        await session.commit()

    async with sessionmaker() as session:
        norms = (await session.execute(select(PPENorm).where(PPENorm.tenant_id == tenant.id))).scalars().all()
        items = (await session.execute(select(PPEItem).where(PPEItem.tenant_id == tenant.id))).scalars().all()
        issues = (await session.execute(select(PPEIssue).where(PPEIssue.tenant_id == tenant.id))).scalars().all()
        person_row = (await session.execute(select(Person).where(Person.id == person.id))).scalar_one()
    assert len(norms) >= 3
    assert all(n.item_id for n in norms)
    assert len(items) >= 3
    assert len(issues) >= 2  # активная + просроченная
    assert person_row.ppe_sizes and person_row.ppe_sizes.get("height")

    # идемпотентность: второй прогон не плодит дублей
    async with sessionmaker() as session:
        person_row = (await session.execute(select(Person).where(Person.id == person.id))).scalar_one()
        await _seed_ppe_demo(session, str(tenant.id), person_row, position_id)
        await session.commit()
    async with sessionmaker() as session:
        norms2 = (await session.execute(select(PPENorm).where(PPENorm.tenant_id == tenant.id))).scalars().all()
    assert len(norms2) == len(norms)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_demo_bootstrap_ppe.py -p no:xdist --timeout=240 -q > test_out.txt 2>&1; Get-Content test_out.txt -Tail 10`
Expected: FAIL — `_seed_ppe_demo` не существует

- [ ] **Step 3: Implement seed (`backend/app/services/demo_bootstrap.py`)**

Импорты: добавить `PPEIssue, PPEItem, PPENorm` в импорт из `app.models.models`; `from app.models.risk import RiskHazard`.

```python
async def _seed_ppe_demo(session, tenant_db_id: str, person, position_id: str) -> None:
    """Seed PPE norms/sizes/issues so the 766н card demos all line statuses.

    Idempotent: keyed lookups on (tenant, name/code) before each insert.
    Card outcome: каска=ok (активная выдача), перчатки=overdue (просрочена),
    очки=missing (нормы без выдачи).
    """
    hazard = (await session.execute(select(RiskHazard).where(
        RiskHazard.tenant_id == tenant_db_id, RiskHazard.code == "demo_general",
    ))).scalar_one_or_none()
    if hazard is None:
        hazard = RiskHazard(tenant_id=tenant_db_id, code="demo_general", title="Общие производственные факторы")
        session.add(hazard)
        await session.flush()

    async def _ensure_item(name: str, wear_days: int) -> PPEItem:
        item = (await session.execute(select(PPEItem).where(
            PPEItem.tenant_id == tenant_db_id, PPEItem.name == name, PPEItem.deleted_at.is_(None),
        ))).scalar_one_or_none()
        if item is None:
            item = PPEItem(tenant_id=tenant_db_id, name=name, default_wear_days=wear_days)
            session.add(item)
            await session.flush()
        return item

    helmet = await _ensure_item("Каска защитная (демо)", 730)
    gloves = await _ensure_item("Перчатки защитные (демо)", 90)
    glasses = await _ensure_item("Очки защитные (демо)", 365)

    for item, qty, interval in ((helmet, 1, 730), (gloves, 2, 90), (glasses, 1, 365)):
        existing = (await session.execute(select(PPENorm).where(
            PPENorm.tenant_id == tenant_db_id,
            PPENorm.position_id == position_id,
            PPENorm.hazard_id == hazard.id,
            PPENorm.item_name == item.name,
        ))).scalar_one_or_none()
        if existing is None:
            session.add(PPENorm(
                tenant_id=tenant_db_id, position_id=position_id, hazard_id=hazard.id,
                item_id=item.id, item_name=item.name, quantity=qty, interval_days=interval,
            ))

    if not person.ppe_sizes:
        person.ppe_sizes = {"height": 178, "clothing_size": "52-54", "shoe_size": "43", "headgear_size": "58"}

    now = datetime.now(timezone.utc)
    existing_issue = (await session.execute(select(PPEIssue).where(
        PPEIssue.tenant_id == tenant_db_id, PPEIssue.person_id == person.id,
        PPEIssue.deleted_at.is_(None),
    ))).scalars().first()
    if existing_issue is None:
        session.add(PPEIssue(  # активная, с сертификатом → строка ok
            tenant_id=tenant_db_id, person_id=person.id, item_id=helmet.id,
            item_name=helmet.name, quantity=1, issued_at=now,
            expires_at=now + timedelta(days=700), wear_days=730, status="issued",
            certificate_no="ЕАЭС RU С-RU.ДЕМО.В.00001/26",
        ))
        session.add(PPEIssue(  # просроченная → строка overdue
            tenant_id=tenant_db_id, person_id=person.id, item_id=gloves.id,
            item_name=gloves.name, quantity=2, issued_at=now - timedelta(days=120),
            expires_at=now - timedelta(days=30), wear_days=90, status="issued",
        ))
        # очки: нормы есть, выдачи нет → строка missing
```

Вызов в `bootstrap_demo_tenant`: рядом с `await _seed_contractor_requirements(session, tenant_db_id)` (строка ~243) — найти в той же функции переменные демо-person и position (прочитать окружение строки 120–243; там создаются position/persons) и добавить:
```python
            await _seed_ppe_demo(session, tenant_db_id, <demo_person>, <demo_position>.id)
```
где `<demo_person>`/`<demo_position>` — фактические имена локальных переменных в функции (проверить по коду; если person создаётся списком — взять первого).

- [ ] **Step 4: Run tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_demo_bootstrap_ppe.py tests/test_demo_bootstrap_contractor_requirements.py -p no:xdist --timeout=240 -q > test_out.txt 2>&1; Get-Content test_out.txt -Tail 10`
Expected: PASS (вкл. существующий contractor-seed тест — соседство не сломано)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/demo_bootstrap.py tests/test_demo_bootstrap_ppe.py
git commit -m "feat(ppe): demo-seed norms/sizes/issues covering all card statuses"
```

---

### Task 9: Access parity + полная контурная регрессия

**Files:**
- Modify (при необходимости): `backend/tests/test_ppe_access_parity.py`
- Никаких новых фич — только верификация.

- [ ] **Step 1: Access parity**

Прочитать `backend/tests/test_ppe_access_parity.py`. Он проверяет `write_roles ⊆ read_roles` на уровне констант `_PPE_READ_ROLES`/`_PPE_WRITE_ROLES` — новые эндпоинты используют те же константы, тест уже покрывает. Если тест перечисляет эндпоинты поимённо — добавить новые (`/ppe/norms*`, `/ppe/issues/{id}/return|writeoff|replace`, `/ppe/employees/{id}/card|sizes`).

- [ ] **Step 2: Контурный когорт**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_ppe_lifecycle.py backend/tests/test_sz01_ppe_766n_migration.py backend/tests/test_ppe_events.py backend/tests/test_ppe_access_parity.py backend/tests/test_ppe_error_contract.py backend/tests/test_ppeitem_table_exists.py backend/tests/test_wa01_ppe_stock_batch_migration.py backend/tests/test_next58_safety_core_services.py tests/api/test_ppe_norms_api.py tests/api/test_ppe_issue_operations_api.py tests/test_ppe_personal_card_766n.py tests/test_ppe_replacement_due_tick.py tests/test_demo_bootstrap_ppe.py -p no:xdist --timeout=240 -q > test_out.txt 2>&1; Get-Content test_out.txt -Tail 10`
Expected: все PASS

- [ ] **Step 3: Смежная регрессия (читатели статуса + соседние контуры)**

Run: `.venv\Scripts\python.exe -m pytest tests -k "analytics or data_quality or operational_dashboard or outbox" -p no:xdist --timeout=300 -q > test_out.txt 2>&1; Get-Content test_out.txt -Tail 15`
Expected: PASS (str-enum сравнения совместимы с VARCHAR-колонкой)

И когорт миграционных guard'ов:
Run: `.venv\Scripts\python.exe -m pytest backend/tests -k "migration or downgrade or mapper" -p no:xdist --timeout=300 -q > test_out.txt 2>&1; Get-Content test_out.txt -Tail 15`
Expected: PASS

- [ ] **Step 4: Commit (если были правки access-parity)**

```bash
git add backend/tests/test_ppe_access_parity.py
git commit -m "test(ppe): access parity covers new norm/card/operation endpoints"
```

---

## Self-Review (выполнен при написании)

1. **Spec coverage:** §3 данные/миграция → Task 2; §4.1 lifecycle → Task 1; §4.2 сервис (карточка/операции/notify) → Tasks 4, 5, 6; §5 API (norms CRUD / операции / card / sizes / legacy PATCH-FSM) → Tasks 3, 4, 5; §6 события+beat → Tasks 4, 6; §7 чистка → Task 7; §8 demo-seed → Task 8; §9 тесты → во всех задачах + Task 9; §10 ошибки → Tasks 3–5 (409/404/422). Пробелов нет.
2. **Placeholder scan:** код полный во всех задачах; в двух местах сознательные «verify-by-reading» инструкции (имя поля Position.title/name; имена локальных переменных в bootstrap_demo_tenant) — это проверка факта кода, не дыра дизайна.
3. **Type consistency:** статусы — строки `issued/returned/written_off/replaced/lost` везде (lifecycle, миграция, тесты, seed); ключ строки карточки `_issue_line_key` единый для норм и выдач; `PPETransitionError` импортируется из `app.domains.ppe.lifecycle` во всех местах.
