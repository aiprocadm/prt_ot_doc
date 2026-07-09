# P10-03 Психиатрическое освидетельствование (342н) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the one true functional gap in медосмотры — build обязательное психиатрическое освидетельствование (342н / ПП РФ 695) as a *second contingent derivation axis* parallel to the 29н hazard→factor one, reusing the existing referral/suspension/допуск-block machinery.

**Architecture:** New tenant-scoped catalog `PsychiatricActivityType` (виды деятельности 695) + mapping `PsychiatricPositionActivity` (должность→вид) drive a new `PSYCHIATRIC` branch in `compute_contingent`. The освидетельствование is a `MedicalExam(kind=PSYCHIATRIC)` with 2 extra nullable columns; recording an `UNFIT` one already opens a suspension → blocks допуск (zero new code there). One additive migration `med03` from the `wh01` head. 5-year periodicity overridable per activity. Backend + thin `MedicalPage` section. Standard 695 list is one code constant, seeded for demo + via an on-demand endpoint.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy (async) / Alembic / Pydantic v2 / pytest-asyncio · React 18 / Vite / TypeScript / vitest.

**Spec:** `docs/superpowers/specs/2026-07-09-p10-03-psychiatric-assessment-342n-design.md`

**Invariant anchor:** existing contingent/referral/suspension tests stay green — psychiatry is added as a union term, not a rewrite. All new exam columns are nullable/defaulted (records without psychiatry unaffected).

---

## File structure

**Backend (create):**
- `backend/app/domains/medical/psychiatric_defaults.py` — `PSYCHIATRIC_ACTIVITY_DEFAULTS` constant (ПП-695 list).
- `backend/app/api/routes/medical/psychiatric.py` — new route module (catalog CRUD + seed-defaults + position mapping).
- `backend/app/migrations/versions/20260709_med03_psychiatric_342n.py` — additive migration.

**Backend (modify):**
- `backend/app/models/medical.py` — +`PsychiatricActivityType`, +`PsychiatricPositionActivity`, +2 columns on `MedicalExam`.
- `backend/app/models/models.py` — re-export the 2 new model classes.
- `backend/app/domains/medical/lifecycle.py` — +`ActivityTuple`, `psychiatric_required`, `psychiatric_interval`.
- `backend/app/domains/medical/service.py` — catalog/map loaders, `compute_contingent` union, `record_exam` periodicity + new fields, `seed_default_activity_types`.
- `backend/app/schemas/medical.py` — psychiatric schemas + 2 fields on `MedicalExamCreate`/`MedicalExamRead`.
- `backend/app/api/routes/medical/_common.py` — `_get_activity_type` getter.
- `backend/app/api/routes/medical/__init__.py` — register the psychiatric module.
- `backend/app/api/routes/medical/exams.py` — thread the 2 new fields in `create_medical_exam`.
- `backend/app/services/demo_bootstrap.py` — `_seed_psychiatric_activities_demo` + wire-in.

**Frontend (modify):**
- `frontend/src/api/operations.ts` — psychiatric snapshot + mutations.
- `frontend/src/pages/medical/MedicalPage.tsx` — thin «Психиатрическое освидетельствование (342н)» section.

**Tests (create):**
- `tests/unit/test_medical_psychiatric_lifecycle.py` — pure-logic units.
- `backend/tests/test_medical_psychiatric_migration.py` — migration source assertions.
- `tests/test_medical_psychiatric_contingent.py` — contingent/service integration.
- `tests/api/test_medical_psychiatric_api.py` — catalog/mapping/seed API.
- `tests/test_medical_psychiatric_seed.py` — `seed_default_activity_types`.
- `frontend/src/pages/medical/MedicalPage.test.tsx` — thin-section vitest (create if absent).

---

## Operational notes (from prior slices — READ before running gates)

- **Backend tests:** run via **PowerShell** tool (Git-Bash segfaults on pytest), global Python: `& "C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe" -m pytest ... -q`. Cold app import is **2-3 min** → **timeout 600000 ms, ONE run, no retry loop**. Run in **batches ≤4-5 files**. Local Py3.13 vs canon 3.12.12 — note the mismatch, don't abort.
- **conftest builds schema from ORM `metadata.create_all`**, not migrations → tests see the new tables as soon as the models exist (Task 1). The migration is validated separately (source test + PG16 gate).
- **black may reformat migration/test source** and break substring asserts → normalize whitespace (`"".join(src.split())`) or re-run the test after black.
- **OpenAPI baseline** re-snap requires `$env:PYTHONPATH="backend"`.
- **PG16 gate** (`scripts/ci/local_gate.py --db-only`) needs Docker; validates alembic round-trip + ARCH-3 boundaries.
- **Frontend:** worktree has no `node_modules` → `npm ci --prefer-offline` once; run gates via Bash `npx vitest run <file>` from `frontend/`. Don't run full `vitest run` in parallel with backend pytest (CPU contention → false flakes).

---

## Task 1: ORM models + exam columns + re-exports

**Files:**
- Modify: `backend/app/models/medical.py`
- Modify: `backend/app/models/models.py`
- Test: `backend/tests/test_medical_psychiatric_model.py` (create)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_medical_psychiatric_model.py`:

```python
"""ORM models for 342н psychiatric assessment exist and persist."""

from __future__ import annotations


def test_psychiatric_models_and_exam_columns_importable():
    from app.models.models import (
        MedicalExam,
        PsychiatricActivityType,
        PsychiatricPositionActivity,
    )

    # tables registered under canonical names
    assert PsychiatricActivityType.__tablename__ == "psychiatric_activity_type"
    assert PsychiatricPositionActivity.__tablename__ == "psychiatric_position_activity"
    # additive exam columns present
    cols = set(MedicalExam.__table__.columns.keys())
    assert {"psychiatric_protocol_no", "psychiatric_activity_codes"} <= cols
    # catalog defaults 5y periodicity
    assert PsychiatricActivityType.__table__.c.interval_days.default.arg == 1825
```

- [ ] **Step 2: Run test to verify it fails**

Run (PowerShell): `& "C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe" -m pytest backend/tests/test_medical_psychiatric_model.py -q`
Expected: FAIL — `ImportError: cannot import name 'PsychiatricActivityType'`.

- [ ] **Step 3: Add the models to `backend/app/models/medical.py`**

Append after `MedicalSuspension` (end of file):

```python
class PsychiatricActivityType(TenantBaseModel):
    """342н reference catalog: вид деятельности (перечень ПП РФ № 695) mandating обязательное
    психиатрическое освидетельствование. Tenant-scoped; unique by code. interval_days overrides
    the 1825-day (5y) default periodicity per activity. VARCHAR-only, no cross-base FK."""

    __tablename__ = "psychiatric_activity_type"

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1825)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_psychiatric_activity_type_tenant_code"),
    )


class PsychiatricPositionActivity(TenantBaseModel):
    """Mapping должность → вид деятельности 695 — the psychiatry contingent axis, parallel to
    RiskHazard.medical_factor_code for 29н. A position subject to ОПО has ≥1 mapped activity."""

    __tablename__ = "psychiatric_position_activity"

    position_id: Mapped[str] = mapped_column(
        ForeignKey("position.id"), nullable=False, index=True
    )
    activity_code: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "position_id",
            "activity_code",
            name="uq_psychiatric_position_activity",
        ),
    )
```

Add the 2 columns inside `class MedicalExam(...)`, right after the `medical_org_name` column (line ~105):

```python
    # --- additive (342н psychiatric assessment) ---
    psychiatric_protocol_no: Mapped[str | None] = mapped_column(String(128))
    psychiatric_activity_codes: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
```

- [ ] **Step 4: Re-export from `backend/app/models/models.py`**

In the `from app.models.medical import (...)` block (line ~157) add the 2 class names (keep alphabetical-ish with the others):

```python
    MedicalSuspensionReason,
    MedicalSuspensionStatus,
    PsychiatricActivityType,
    PsychiatricPositionActivity,
)
```

In the `__all__` list, after `"MedicalSuspension",` (both occurrences at line ~333 and ~578 — add to the one that is the module `__all__`; if two lists exist, add to both) add:

```python
    "PsychiatricActivityType",
    "PsychiatricPositionActivity",
```

- [ ] **Step 5: Run test to verify it passes**

Run: `& "...python.exe" -m pytest backend/tests/test_medical_psychiatric_model.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/medical.py backend/app/models/models.py backend/tests/test_medical_psychiatric_model.py
git commit -m "feat(p10-03): PsychiatricActivityType + PositionActivity models + exam fields"
```

---

## Task 2: Additive migration `med03`

**Files:**
- Create: `backend/app/migrations/versions/20260709_med03_psychiatric_342n.py`
- Test: `backend/tests/test_medical_psychiatric_migration.py` (create)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_medical_psychiatric_migration.py`:

```python
"""med03 migration is additive, round-trip-safe, chains from the wh01 head."""

from __future__ import annotations

from pathlib import Path

MIG = (
    Path(__file__).resolve().parents[2]
    / "backend/app/migrations/versions/20260709_med03_psychiatric_342n.py"
)


def _norm(text: str) -> str:
    return "".join(text.split())


def test_med03_chains_and_is_additive():
    src = MIG.read_text(encoding="utf-8")
    n = _norm(src)
    assert 'revision="20260709_med03_psychiatric_342n"' in n
    assert 'down_revision="20260709_wh01_webhook_delivery_outbox_id"' in n
    # creates both tables + adds both exam columns
    assert 'create_table("psychiatric_activity_type"' in n
    assert 'create_table("psychiatric_position_activity"' in n
    assert 'add_column("medical_exam"' in n
    assert n.count('add_column("medical_exam"') == 2
    # downgrade drops columns before tables (round-trip safe)
    assert 'drop_table("psychiatric_position_activity")' in n
    assert 'drop_table("psychiatric_activity_type")' in n
    assert 'drop_column("medical_exam","psychiatric_activity_codes")' in n
    assert 'drop_column("medical_exam","psychiatric_protocol_no")' in n
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& "...python.exe" -m pytest backend/tests/test_medical_psychiatric_migration.py -q`
Expected: FAIL — file does not exist (`FileNotFoundError`).

- [ ] **Step 3: Write the migration**

Create `backend/app/migrations/versions/20260709_med03_psychiatric_342n.py`:

```python
"""med03: 342н psychiatric assessment — activity-type catalog + position mapping + exam fields.

Additive. Two new tenant-scoped tables + two columns on medical_exam. VARCHAR-only, one FK to
position, JSON default '[]'. Round-trip-safe: downgrade drops columns then tables.
Table/column names are LITERAL (AST-audit blindspot).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260709_med03_psychiatric_342n"
down_revision = "20260709_wh01_webhook_delivery_outbox_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "psychiatric_activity_type",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False, server_default="1825"),
        sa.UniqueConstraint(
            "tenant_id", "code", name="uq_psychiatric_activity_type_tenant_code"
        ),
    )
    op.create_table(
        "psychiatric_position_activity",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("position_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("activity_code", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["position_id"], ["position.id"]),
        sa.UniqueConstraint(
            "tenant_id",
            "position_id",
            "activity_code",
            name="uq_psychiatric_position_activity",
        ),
    )
    op.add_column(
        "medical_exam",
        sa.Column("psychiatric_protocol_no", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "medical_exam",
        sa.Column(
            "psychiatric_activity_codes",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("medical_exam", "psychiatric_activity_codes")
    op.drop_column("medical_exam", "psychiatric_protocol_no")
    op.drop_table("psychiatric_position_activity")
    op.drop_table("psychiatric_activity_type")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `& "...python.exe" -m pytest backend/tests/test_medical_psychiatric_migration.py -q`
Expected: PASS. (If black reformatted the migration and split an `add_column("medical_exam", ...)` across lines, the `_norm` whitespace-collapse still matches — good.)

- [ ] **Step 5: Verify single alembic head**

Run: `$env:PYTHONPATH="backend"; & "...python.exe" -m alembic -c backend/app/migrations/alembic.ini heads`
Expected: single head `20260709_med03_psychiatric_342n`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/migrations/versions/20260709_med03_psychiatric_342n.py backend/tests/test_medical_psychiatric_migration.py
git commit -m "feat(p10-03): med03 migration — psychiatric catalog/mapping/exam fields"
```

---

## Task 3: Pure logic — defaults constant + lifecycle functions

**Files:**
- Create: `backend/app/domains/medical/psychiatric_defaults.py`
- Modify: `backend/app/domains/medical/lifecycle.py`
- Test: `tests/unit/test_medical_psychiatric_lifecycle.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_medical_psychiatric_lifecycle.py`:

```python
from __future__ import annotations

from app.domains.medical import lifecycle as lc
from app.domains.medical.psychiatric_defaults import PSYCHIATRIC_ACTIVITY_DEFAULTS

# catalog: (code, name, interval_days)
CAT = [("height", "Работы на высоте", 1825), ("transport", "Транспорт", 1095)]


def test_psychiatric_required():
    assert lc.psychiatric_required({"height"}, CAT) is True
    assert lc.psychiatric_required({"height", "unknown"}, CAT) is True
    assert lc.psychiatric_required(set(), CAT) is False
    assert lc.psychiatric_required({"unknown"}, CAT) is False  # code not in catalog
    assert lc.psychiatric_required({"height"}, []) is False  # empty catalog


def test_psychiatric_interval():
    # strictest (min) among mapped activities
    assert lc.psychiatric_interval({"height", "transport"}, CAT) == 1095
    assert lc.psychiatric_interval({"height"}, CAT) == 1825
    # fallback to 5y default when nothing matches
    assert lc.psychiatric_interval(set(), CAT) == 1825
    assert lc.psychiatric_interval({"unknown"}, CAT) == 1825


def test_defaults_constant_shape():
    assert len(PSYCHIATRIC_ACTIVITY_DEFAULTS) >= 8
    for code, name, days in PSYCHIATRIC_ACTIVITY_DEFAULTS:
        assert isinstance(code, str) and code
        assert isinstance(name, str) and name
        assert days == 1825
    # codes unique
    codes = [c for c, _, _ in PSYCHIATRIC_ACTIVITY_DEFAULTS]
    assert len(codes) == len(set(codes))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& "...python.exe" -m pytest tests/unit/test_medical_psychiatric_lifecycle.py -q`
Expected: FAIL — `ModuleNotFoundError: app.domains.medical.psychiatric_defaults`.

- [ ] **Step 3: Create the defaults constant**

Create `backend/app/domains/medical/psychiatric_defaults.py`:

```python
"""Standard ПП РФ № 695 виды деятельности requiring обязательное психиатрическое
освидетельствование (приказ Минздрава № 342н). Single source for the demo seed and the
POST /medical/psychiatric/activity-types/seed-defaults endpoint.

Formulations are conservative paraphrases of the ПП-695 приложение — verify exact wording
against the primary source before any print/legal use. Periodicity 1825 days = 5 лет.
"""

from __future__ import annotations

# (code, name, interval_days)
PSYCHIATRIC_ACTIVITY_DEFAULTS: tuple[tuple[str, str, int], ...] = (
    ("transport", "Управление транспортными средствами", 1825),
    ("height", "Работы на высоте", 1825),
    ("electrical", "Обслуживание и ремонт действующих электроустановок", 1825),
    ("forestry", "Работы в лесной охране, валка и транспортировка леса", 1825),
    ("weapons", "Работы, связанные с оборотом и ношением оружия", 1825),
    ("pressure_vessels", "Обслуживание сосудов, работающих под давлением", 1825),
    ("rescue_fire", "Аварийно-спасательные работы и тушение пожаров", 1825),
    ("underground", "Подземные работы", 1825),
    ("railway", "Работы, связанные с движением поездов и маневровой работой", 1825),
)
```

- [ ] **Step 4: Add lifecycle functions**

In `backend/app/domains/medical/lifecycle.py`, after the 29н factor block (after `required_exams_from_factors`, ~line 162), add:

```python
# ---------------------------------------------------------------------------
# 2.6b — 342н psychiatric resolution (695 activity types → subject / periodicity)
# ---------------------------------------------------------------------------

# (code, name, interval_days) — ORM-free вид деятельности 695.
ActivityTuple = tuple[str, str, int]


def psychiatric_required(activity_codes: set[str], catalog: Iterable[ActivityTuple]) -> bool:
    """True when a position is subject to ОПО: it has ≥1 mapped activity code that exists in the
    tenant's activity-type catalog (695). Unknown/stale mapping codes are ignored."""
    catalog_codes = {a[0] for a in catalog}
    return bool(activity_codes & catalog_codes)


def psychiatric_interval(activity_codes: set[str], catalog: Iterable[ActivityTuple]) -> int:
    """Strictest (min) interval_days among the position's mapped activity types; falls back to
    the 5-year PSYCHIATRIC default when none of the codes match the catalog."""
    intervals = [days for code, _name, days in catalog if code in activity_codes]
    if not intervals:
        return DEFAULT_INTERVAL_DAYS[MedicalExamKind.PSYCHIATRIC]
    return min(intervals)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `& "...python.exe" -m pytest tests/unit/test_medical_psychiatric_lifecycle.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/domains/medical/psychiatric_defaults.py backend/app/domains/medical/lifecycle.py tests/unit/test_medical_psychiatric_lifecycle.py
git commit -m "feat(p10-03): psychiatric pure logic — 695 defaults + required/interval"
```

---

## Task 4: Service — contingent integration (second derivation axis)

**Files:**
- Modify: `backend/app/domains/medical/service.py`
- Test: `tests/test_medical_psychiatric_contingent.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_medical_psychiatric_contingent.py`:

```python
"""compute_contingent adds PSYCHIATRIC for positions mapped to a 695 activity."""

from datetime import date

import pytest

from app.domains.medical.service import compute_contingent
from app.models.models import (
    Position,
    PsychiatricActivityType,
    PsychiatricPositionActivity,
)


@pytest.mark.asyncio
async def test_contingent_includes_psychiatric_for_mapped_position(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        pos = Position(tenant_id=tenant.id, company_id=company.id, name="Крановщик")
        session.add(pos)
        await session.flush()
        session.add(
            PsychiatricActivityType(
                tenant_id=tenant.id, code="height", name="Работы на высоте", interval_days=1825
            )
        )
        session.add(
            PsychiatricPositionActivity(
                tenant_id=tenant.id, position_id=pos.id, activity_code="height"
            )
        )
        person = await data_factory.create_person(
            tenant=tenant, company=company, session=session,
            position_id=pos.id, first_name="Иван", last_name="Петров",
        )
        await session.commit()
        items = await compute_contingent(session, tenant_id=str(tenant.id), today=date(2026, 7, 9))

    assert any(
        it["person_id"] == person.id
        and it["exam_kind"] == "psychiatric"
        and it["status"] == "missing"
        for it in items
    )


@pytest.mark.asyncio
async def test_contingent_no_psychiatric_when_activity_not_in_catalog(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        pos = Position(tenant_id=tenant.id, company_id=company.id, name="Бухгалтер")
        session.add(pos)
        await session.flush()
        # mapping references a code with NO catalog row → not subject
        session.add(
            PsychiatricPositionActivity(
                tenant_id=tenant.id, position_id=pos.id, activity_code="ghost"
            )
        )
        person = await data_factory.create_person(
            tenant=tenant, company=company, session=session,
            position_id=pos.id, first_name="Пётр", last_name="Сидоров",
        )
        await session.commit()
        items = await compute_contingent(session, tenant_id=str(tenant.id), today=date(2026, 7, 9))

    assert not any(
        it["person_id"] == person.id and it["exam_kind"] == "psychiatric" for it in items
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& "...python.exe" -m pytest tests/test_medical_psychiatric_contingent.py -q`
Expected: FAIL — PSYCHIATRIC not in contingent (assertion fails), because `compute_contingent` doesn't yet consider the psychiatric axis.

- [ ] **Step 3: Add loaders + wire into `compute_contingent`**

In `backend/app/domains/medical/service.py`:

Add to the model import block (line ~12) — `PsychiatricActivityType, PsychiatricPositionActivity`:

```python
    Person,
    Position,
    PsychiatricActivityType,
    PsychiatricPositionActivity,
)
```

Add loaders right after `_load_factor_catalog` (line ~282):

```python
async def _load_activity_catalog(
    session: AsyncSession, *, tenant_id: str
) -> list[lc.ActivityTuple]:
    """695 activity-type catalog as ORM-free ActivityTuples for the pure engine."""
    stmt = select(
        PsychiatricActivityType.code,
        PsychiatricActivityType.name,
        PsychiatricActivityType.interval_days,
    ).where(PsychiatricActivityType.tenant_id == tenant_id)
    return [(code, name, int(days)) for code, name, days in (await session.execute(stmt)).all()]


async def _load_position_activity_map(
    session: AsyncSession, *, tenant_id: str
) -> dict[str, set[str]]:
    """position_id -> set of mapped 695 activity codes (batched, no N+1)."""
    stmt = select(
        PsychiatricPositionActivity.position_id,
        PsychiatricPositionActivity.activity_code,
    ).where(PsychiatricPositionActivity.tenant_id == tenant_id)
    out: dict[str, set[str]] = {}
    for pos_id, code in (await session.execute(stmt)).all():
        out.setdefault(pos_id, set()).add(code)
    return out
```

In `compute_contingent` — load the psychiatric data and widen the early-return guard. Replace:

```python
    catalog = await _load_factor_catalog(session, tenant_id=tenant_id)
    if not norms and not catalog:
        return []
```

with:

```python
    catalog = await _load_factor_catalog(session, tenant_id=tenant_id)
    psych_catalog = await _load_activity_catalog(session, tenant_id=tenant_id)
    psych_map = await _load_position_activity_map(session, tenant_id=tenant_id)
    if not norms and not catalog and not psych_catalog:
        return []
```

In the per-person loop, after the factor-driven union line (`required |= set(...)`, ~line 357) add:

```python
        if person.position_id and lc.psychiatric_required(
            psych_map.get(person.position_id, set()), psych_catalog
        ):
            required.add(MedicalExamKind.PSYCHIATRIC)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `& "...python.exe" -m pytest tests/test_medical_psychiatric_contingent.py -q`
Expected: PASS.

- [ ] **Step 5: Run the existing contingent tests (invariant anchor)**

Run: `& "...python.exe" -m pytest tests/test_medical_contingent_factor.py tests/test_medical_service.py -q`
Expected: PASS (29н branch unchanged).

- [ ] **Step 6: Commit**

```bash
git add backend/app/domains/medical/service.py tests/test_medical_psychiatric_contingent.py
git commit -m "feat(p10-03): compute_contingent — psychiatric derivation axis (695)"
```

---

## Task 5: Service — record_exam periodicity + fields + seed helper

**Files:**
- Modify: `backend/app/domains/medical/service.py`
- Test: `tests/test_medical_psychiatric_seed.py` (create) + add cases to `tests/test_medical_psychiatric_contingent.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_medical_psychiatric_contingent.py`:

```python
@pytest.mark.asyncio
async def test_record_psychiatric_exam_uses_activity_interval_and_fields(sessionmaker, data_factory):
    from datetime import date

    from app.domains.medical.service import record_exam
    from app.models.models import MedicalExamKind, MedicalFitness

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        pos = Position(tenant_id=tenant.id, company_id=company.id, name="Водитель")
        session.add(pos)
        await session.flush()
        session.add(
            PsychiatricActivityType(
                tenant_id=tenant.id, code="transport", name="Транспорт", interval_days=1095
            )
        )
        session.add(
            PsychiatricPositionActivity(
                tenant_id=tenant.id, position_id=pos.id, activity_code="transport"
            )
        )
        person = await data_factory.create_person(
            tenant=tenant, company=company, session=session,
            position_id=pos.id, first_name="Глеб", last_name="Смирнов",
        )
        await session.flush()
        exam = await record_exam(
            session,
            tenant_id=str(tenant.id),
            actor_id=None,
            person_id=person.id,
            exam_kind=MedicalExamKind.PSYCHIATRIC,
            exam_date=date(2026, 1, 1),
            fitness=MedicalFitness.FIT,
            contraindications=[],
            conclusion=None,
            restrictions=None,
            valid_until=None,  # derive from activity interval
            medical_org_name="ВК № 3",
            referral_id=None,
            exam_type=None,
            psychiatric_protocol_no="ПРО-42",
            psychiatric_activity_codes=["transport"],
        )
        await session.commit()

    # 1095-day interval from the activity, not the 1825 default
    assert exam.valid_until == date(2029, 1, 1)  # 2026-01-01 + 1095d
    assert exam.psychiatric_protocol_no == "ПРО-42"
    assert exam.psychiatric_activity_codes == ["transport"]


@pytest.mark.asyncio
async def test_unfit_psychiatric_exam_opens_suspension(sessionmaker, data_factory):
    from datetime import date

    from app.domains.medical.service import list_active_suspensions, record_exam
    from app.models.models import MedicalExamKind, MedicalFitness

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(
            tenant=tenant, company=company, session=session,
            first_name="Анна", last_name="Кот",
        )
        await session.flush()
        await record_exam(
            session, tenant_id=str(tenant.id), actor_id=None, person_id=person.id,
            exam_kind=MedicalExamKind.PSYCHIATRIC, exam_date=date(2026, 1, 1),
            fitness=MedicalFitness.UNFIT, contraindications=["transport"],
            conclusion=None, restrictions=None, valid_until=None,
            medical_org_name=None, referral_id=None, exam_type=None,
        )
        await session.commit()
        actives = await list_active_suspensions(
            session, tenant_id=str(tenant.id), person_ids=[person.id]
        )
    assert len(actives) == 1  # UNFIT psychiatric verdict blocks допуск via existing machinery
```

Create `tests/test_medical_psychiatric_seed.py`:

```python
"""seed_default_activity_types is idempotent and loads the standard 695 set."""

import pytest

from app.domains.medical.psychiatric_defaults import PSYCHIATRIC_ACTIVITY_DEFAULTS
from app.domains.medical.service import seed_default_activity_types
from app.models.models import PsychiatricActivityType
from sqlalchemy import func, select


@pytest.mark.asyncio
async def test_seed_defaults_idempotent(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        n1 = await seed_default_activity_types(session, tenant_id=str(tenant.id))
        await session.commit()
        n2 = await seed_default_activity_types(session, tenant_id=str(tenant.id))
        await session.commit()
        total = await session.scalar(
            select(func.count()).select_from(PsychiatricActivityType).where(
                PsychiatricActivityType.tenant_id == tenant.id
            )
        )
    assert n1 == len(PSYCHIATRIC_ACTIVITY_DEFAULTS)
    assert n2 == 0  # second run inserts nothing
    assert int(total) == len(PSYCHIATRIC_ACTIVITY_DEFAULTS)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `& "...python.exe" -m pytest tests/test_medical_psychiatric_seed.py "tests/test_medical_psychiatric_contingent.py::test_record_psychiatric_exam_uses_activity_interval_and_fields" -q`
Expected: FAIL — `record_exam() got an unexpected keyword argument 'psychiatric_protocol_no'` and `ImportError: seed_default_activity_types`.

- [ ] **Step 3: Extend `record_exam` + add `_psychiatric_interval_days` + `seed_default_activity_types`**

In `record_exam` signature (after `exam_type: str | None,`, line ~79) add two keyword params:

```python
    exam_type: str | None,
    psychiatric_protocol_no: str | None = None,
    psychiatric_activity_codes: list[str] | None = None,
) -> MedicalExam:
```

Replace the `valid_until` computation block (lines ~92-96):

```python
    if valid_until is None:
        interval = await _norm_interval(
            session, tenant_id=tenant_id, person=person, exam_kind=exam_kind
        )
        valid_until = lc.compute_valid_until(exam_date, interval)
```

with:

```python
    if valid_until is None:
        if exam_kind is MedicalExamKind.PSYCHIATRIC:
            interval = await _psychiatric_interval_days(
                session, tenant_id=tenant_id, person=person
            )
        else:
            interval = await _norm_interval(
                session, tenant_id=tenant_id, person=person, exam_kind=exam_kind
            )
        valid_until = lc.compute_valid_until(exam_date, interval)
```

Add the two new columns to the `MedicalExam(...)` constructor (after `referral_id=referral_id,`, line ~110):

```python
        referral_id=referral_id,
        psychiatric_protocol_no=psychiatric_protocol_no,
        psychiatric_activity_codes=list(psychiatric_activity_codes or []),
    )
```

Add the interval helper right after `_norm_interval` (line ~61):

```python
async def _psychiatric_interval_days(
    session: AsyncSession, *, tenant_id: str, person: Person
) -> int:
    """Periodicity in days for a psychiatric exam: strictest interval among the person's
    position's mapped 695 activities, else the 5-year default."""
    catalog = await _load_activity_catalog(session, tenant_id=tenant_id)
    codes: set[str] = set()
    if person.position_id:
        rows = (
            await session.execute(
                select(PsychiatricPositionActivity.activity_code).where(
                    PsychiatricPositionActivity.tenant_id == tenant_id,
                    PsychiatricPositionActivity.position_id == person.position_id,
                )
            )
        ).all()
        codes = {c for (c,) in rows}
    return lc.psychiatric_interval(codes, catalog)
```

> Note: `_psychiatric_interval_days` references `_load_activity_catalog` (added in Task 4) — Task 4 must land first.

Add the seed helper near the other catalog helpers (e.g. after `_load_position_activity_map`):

```python
async def seed_default_activity_types(session: AsyncSession, *, tenant_id: str) -> int:
    """Insert the standard ПП-695 activity-type set for codes not already present. Idempotent.
    Does not commit. Returns the count inserted."""
    from app.domains.medical.psychiatric_defaults import PSYCHIATRIC_ACTIVITY_DEFAULTS

    existing = {
        c
        for (c,) in (
            await session.execute(
                select(PsychiatricActivityType.code).where(
                    PsychiatricActivityType.tenant_id == tenant_id
                )
            )
        ).all()
    }
    created = 0
    for code, name, interval_days in PSYCHIATRIC_ACTIVITY_DEFAULTS:
        if code in existing:
            continue
        session.add(
            PsychiatricActivityType(
                tenant_id=tenant_id, code=code, name=name, interval_days=interval_days
            )
        )
        created += 1
    await session.flush()
    return created
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `& "...python.exe" -m pytest tests/test_medical_psychiatric_seed.py tests/test_medical_psychiatric_contingent.py -q`
Expected: PASS (all cases).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/medical/service.py tests/test_medical_psychiatric_seed.py tests/test_medical_psychiatric_contingent.py
git commit -m "feat(p10-03): record_exam psychiatric periodicity/fields + seed_default_activity_types"
```

---

## Task 6: Schemas — psychiatric schemas + exam extension

**Files:**
- Modify: `backend/app/schemas/medical.py`
- Test: `backend/tests/test_medical_psychiatric_schemas.py` (create)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_medical_psychiatric_schemas.py`:

```python
from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_activity_type_schema_bounds():
    from app.schemas.medical import PsychiatricActivityTypeCreate

    ok = PsychiatricActivityTypeCreate(code="height", name="Высота")
    assert ok.interval_days == 1825  # 5y default
    with pytest.raises(ValidationError):
        PsychiatricActivityTypeCreate(code="", name="x")  # empty code
    with pytest.raises(ValidationError):
        PsychiatricActivityTypeCreate(code="h", name="x", interval_days=0)  # < 1


def test_exam_schema_carries_psychiatric_fields():
    from datetime import date

    from app.models.models import MedicalExamKind
    from app.schemas.medical import MedicalExamCreate, MedicalExamRead

    c = MedicalExamCreate(
        person_id="p1",
        exam_kind=MedicalExamKind.PSYCHIATRIC,
        exam_date=date(2026, 1, 1),
        psychiatric_protocol_no="ПРО-1",
        psychiatric_activity_codes=["height"],
    )
    assert c.psychiatric_activity_codes == ["height"]
    # Read defaults are safe for non-psychiatric records
    assert "psychiatric_protocol_no" in MedicalExamRead.model_fields
    assert "psychiatric_activity_codes" in MedicalExamRead.model_fields


def test_position_activities_in_schema():
    from app.schemas.medical import PositionActivitiesIn

    body = PositionActivitiesIn(activity_codes=["height", "transport"])
    assert body.activity_codes == ["height", "transport"]
    assert PositionActivitiesIn().activity_codes == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& "...python.exe" -m pytest backend/tests/test_medical_psychiatric_schemas.py -q`
Expected: FAIL — `ImportError: PsychiatricActivityTypeCreate`.

- [ ] **Step 3: Add schemas + extend exam schemas**

In `backend/app/schemas/medical.py`:

Add the 2 fields to `MedicalExamRead` (after `medical_org_name`, line ~41):

```python
    medical_org_name: str | None = None
    psychiatric_protocol_no: str | None = None
    psychiatric_activity_codes: list[str] = Field(default_factory=list)
```

Add the 2 fields to `MedicalExamCreate` (after `referral_id`, line ~61):

```python
    referral_id: str | None = None
    psychiatric_protocol_no: str | None = None
    psychiatric_activity_codes: list[str] = Field(default_factory=list)
```

Append the psychiatric schemas at the end of the file:

```python
class PsychiatricActivityTypeCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=255)
    interval_days: int = Field(default=1825, ge=1, le=3650)
    model_config = ConfigDict(extra="forbid")


class PsychiatricActivityTypeRead(BaseModel):
    id: str
    code: str
    name: str
    interval_days: int
    model_config = ConfigDict(from_attributes=True)


class PsychiatricActivityTypeUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    interval_days: int | None = Field(default=None, ge=1, le=3650)
    model_config = ConfigDict(extra="forbid")


class PsychiatricActivityTypePage(BaseModel):
    items: list[PsychiatricActivityTypeRead]
    total: int


class PositionActivitiesIn(BaseModel):
    """Full replacement of a position's mapped 695 activity codes."""

    activity_codes: list[str] = Field(default_factory=list)
    model_config = ConfigDict(extra="forbid")


class PositionActivitiesRead(BaseModel):
    position_id: str
    activity_codes: list[str]


class PositionActivitiesPage(BaseModel):
    items: list[PositionActivitiesRead]
    total: int
```

- [ ] **Step 4: Run test to verify it passes**

Run: `& "...python.exe" -m pytest backend/tests/test_medical_psychiatric_schemas.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/medical.py backend/tests/test_medical_psychiatric_schemas.py
git commit -m "feat(p10-03): psychiatric schemas + exam create/read fields"
```

---

## Task 7: Routes — psychiatric.py (catalog CRUD + seed-defaults + mapping)

**Files:**
- Create: `backend/app/api/routes/medical/psychiatric.py`
- Modify: `backend/app/api/routes/medical/_common.py`
- Modify: `backend/app/api/routes/medical/__init__.py`
- Test: `tests/api/test_medical_psychiatric_api.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_medical_psychiatric_api.py`:

```python
from __future__ import annotations

import pytest
from fastapi import status

from app.models.models import RoleEnum


@pytest.mark.asyncio
async def test_activity_type_crud_and_duplicate(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    body = {"code": "height", "name": "Работы на высоте", "interval_days": 1825}
    r = await async_client.post(
        "/api/v1/medical/psychiatric/activity-types", headers=headers, json=body
    )
    assert r.status_code == status.HTTP_201_CREATED, r.text
    aid = r.json()["id"]

    dup = await async_client.post(
        "/api/v1/medical/psychiatric/activity-types", headers=headers, json=body
    )
    assert dup.status_code == status.HTTP_409_CONFLICT

    lst = await async_client.get("/api/v1/medical/psychiatric/activity-types", headers=headers)
    assert lst.status_code == status.HTTP_200_OK
    assert any(a["code"] == "height" for a in lst.json()["items"])

    patched = await async_client.patch(
        f"/api/v1/medical/psychiatric/activity-types/{aid}",
        headers=headers, json={"interval_days": 1095},
    )
    assert patched.status_code == status.HTTP_200_OK and patched.json()["interval_days"] == 1095

    deleted = await async_client.delete(
        f"/api/v1/medical/psychiatric/activity-types/{aid}", headers=headers
    )
    assert deleted.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_seed_defaults_idempotent_endpoint(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    r1 = await async_client.post(
        "/api/v1/medical/psychiatric/activity-types/seed-defaults", headers=headers
    )
    assert r1.status_code == status.HTTP_200_OK and r1.json()["count"] >= 8
    r2 = await async_client.post(
        "/api/v1/medical/psychiatric/activity-types/seed-defaults", headers=headers
    )
    assert r2.status_code == status.HTTP_200_OK and r2.json()["count"] == 0


@pytest.mark.asyncio
async def test_set_position_activities_and_validation(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    from app.models.models import Position

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        pos = Position(tenant_id=tenant.id, company_id=company.id, name="Крановщик")
        session.add(pos)
        await session.commit()
        pos_id = pos.id
    headers = await make_auth_headers(RoleEnum.ADMIN)
    await async_client.post(
        "/api/v1/medical/psychiatric/activity-types/seed-defaults", headers=headers
    )
    # unknown code → 422
    bad = await async_client.put(
        f"/api/v1/medical/psychiatric/positions/{pos_id}/activities",
        headers=headers, json={"activity_codes": ["ghost"]},
    )
    assert bad.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    # valid set → 200, and read reflects it
    ok = await async_client.put(
        f"/api/v1/medical/psychiatric/positions/{pos_id}/activities",
        headers=headers, json={"activity_codes": ["height", "transport"]},
    )
    assert ok.status_code == status.HTTP_200_OK
    assert set(ok.json()["activity_codes"]) == {"height", "transport"}
    # replace semantics: setting a smaller set removes the rest
    ok2 = await async_client.put(
        f"/api/v1/medical/psychiatric/positions/{pos_id}/activities",
        headers=headers, json={"activity_codes": ["height"]},
    )
    assert set(ok2.json()["activity_codes"]) == {"height"}


@pytest.mark.asyncio
async def test_activity_types_require_write_role(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)
    r = await async_client.post(
        "/api/v1/medical/psychiatric/activity-types",
        headers=headers, json={"code": "x", "name": "y"},
    )
    assert r.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& "...python.exe" -m pytest tests/api/test_medical_psychiatric_api.py -q`
Expected: FAIL — 404 for every route (module not registered).

- [ ] **Step 3: Add `_get_activity_type` to `_common.py`**

In `backend/app/api/routes/medical/_common.py`, add `PsychiatricActivityType` to the model import (line ~20) and append a getter after `_get_referral`:

```python
async def _get_activity_type(
    session: AsyncSession, tenant_id: str, activity_id: str
) -> "PsychiatricActivityType":
    from app.models.models import PsychiatricActivityType as _AT

    rec = (
        await session.execute(
            select(_AT).where(_AT.id == activity_id, _AT.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if rec is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=_error("activity_type_not_found", "Psychiatric activity type not found"),
        )
    return rec
```

- [ ] **Step 4: Create the route module**

Create `backend/app/api/routes/medical/psychiatric.py`:

```python
"""Medical endpoints — 342н psychiatric assessment: 695 activity-type catalog + seed-defaults
+ должность→вид mapping. Behind the medical feature flag; same RBAC as the rest of /medical."""

from __future__ import annotations

from fastapi import HTTPException, Query, Request, Response, status
from sqlalchemy import delete, func, select

from app.api.routes.medical._common import (
    MedicalAccess,
    MedicalFeatureGate,
    MedicalReadAccess,
    SessionDep,
    TenantDep,
    _error,
    _get_activity_type,
    router,
)
from app.core.tenant_validation import TenantContextValidator
from app.domains.medical import service as medsvc
from app.models.models import (
    Position,
    PsychiatricActivityType,
    PsychiatricPositionActivity,
)
from app.schemas.medical import (
    PositionActivitiesIn,
    PositionActivitiesPage,
    PositionActivitiesRead,
    PsychiatricActivityTypeCreate,
    PsychiatricActivityTypePage,
    PsychiatricActivityTypeRead,
    PsychiatricActivityTypeUpdate,
)
from app.services.audit import AuditService


def _audit_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# --- activity-type catalog CRUD ---


@router.get(
    "/medical/psychiatric/activity-types",
    response_model=PsychiatricActivityTypePage,
    dependencies=[MedicalFeatureGate],
)
async def list_activity_types(
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PsychiatricActivityTypePage:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    stmt = select(PsychiatricActivityType).where(
        PsychiatricActivityType.tenant_id == tenant.id
    )
    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = list(
        (
            await session.execute(
                stmt.order_by(PsychiatricActivityType.code.asc()).offset(offset).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return PsychiatricActivityTypePage(
        items=[PsychiatricActivityTypeRead.model_validate(r) for r in rows],
        total=int(total or 0),
    )


@router.post(
    "/medical/psychiatric/activity-types",
    response_model=PsychiatricActivityTypeRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[MedicalFeatureGate],
)
async def create_activity_type(
    request: Request,
    payload: PsychiatricActivityTypeCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalAccess,
) -> PsychiatricActivityTypeRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    dup = await session.scalar(
        select(PsychiatricActivityType).where(
            PsychiatricActivityType.tenant_id == tenant.id,
            PsychiatricActivityType.code == payload.code,
        )
    )
    if dup is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=_error(
                "activity_type_duplicate", f"Activity code already exists: {payload.code}"
            ),
        )
    record = PsychiatricActivityType(tenant_id=str(tenant.id), **payload.model_dump())
    session.add(record)
    await session.flush()
    audit = AuditService(session)
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="psychiatric_activity_type",
        object_id=record.id,
        user_id=getattr(access.user, "id", None),
        ip=_audit_ip(request),
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    await session.refresh(record)
    return PsychiatricActivityTypeRead.model_validate(record)


@router.post(
    "/medical/psychiatric/activity-types/seed-defaults",
    dependencies=[MedicalFeatureGate],
)
async def seed_activity_type_defaults(
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalAccess,
) -> dict[str, int]:
    TenantContextValidator.ensure_tenant_context(tenant)
    count = await medsvc.seed_default_activity_types(session, tenant_id=str(tenant.id))
    audit = AuditService(session)
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="seed",
        object_type="psychiatric_activity_type",
        object_id="defaults",
        user_id=getattr(access.user, "id", None),
        ip=_audit_ip(request),
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={"count": count},
    )
    await session.commit()
    return {"count": count}


@router.get(
    "/medical/psychiatric/activity-types/{activity_id}",
    response_model=PsychiatricActivityTypeRead,
    dependencies=[MedicalFeatureGate],
)
async def get_activity_type(
    activity_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
) -> PsychiatricActivityTypeRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    return PsychiatricActivityTypeRead.model_validate(
        await _get_activity_type(session, str(tenant.id), activity_id)
    )


@router.patch(
    "/medical/psychiatric/activity-types/{activity_id}",
    response_model=PsychiatricActivityTypeRead,
    dependencies=[MedicalFeatureGate],
)
async def update_activity_type(
    request: Request,
    activity_id: str,
    payload: PsychiatricActivityTypeUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalAccess,
) -> PsychiatricActivityTypeRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    record = await _get_activity_type(session, str(tenant.id), activity_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(record, k, v)
    audit = AuditService(session)
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="psychiatric_activity_type",
        object_id=record.id,
        user_id=getattr(access.user, "id", None),
        ip=_audit_ip(request),
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    await session.refresh(record)
    return PsychiatricActivityTypeRead.model_validate(record)


@router.delete(
    "/medical/psychiatric/activity-types/{activity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[MedicalFeatureGate],
)
async def delete_activity_type(
    request: Request,
    activity_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalAccess,
) -> Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    record = await _get_activity_type(session, str(tenant.id), activity_id)
    audit = AuditService(session)
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="delete",
        object_type="psychiatric_activity_type",
        object_id=record.id,
        user_id=getattr(access.user, "id", None),
        ip=_audit_ip(request),
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
    )
    await session.delete(record)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- position → activity mapping ---


async def _position_codes(session, tenant_id: str, position_id: str) -> list[str]:
    rows = (
        await session.execute(
            select(PsychiatricPositionActivity.activity_code).where(
                PsychiatricPositionActivity.tenant_id == tenant_id,
                PsychiatricPositionActivity.position_id == position_id,
            )
        )
    ).all()
    return sorted(c for (c,) in rows)


@router.get(
    "/medical/psychiatric/position-activities",
    response_model=PositionActivitiesPage,
    dependencies=[MedicalFeatureGate],
)
async def list_position_activities(
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
) -> PositionActivitiesPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    rows = (
        await session.execute(
            select(
                PsychiatricPositionActivity.position_id,
                PsychiatricPositionActivity.activity_code,
            ).where(PsychiatricPositionActivity.tenant_id == tenant.id)
        )
    ).all()
    grouped: dict[str, list[str]] = {}
    for pos_id, code in rows:
        grouped.setdefault(pos_id, []).append(code)
    items = [
        PositionActivitiesRead(position_id=pid, activity_codes=sorted(codes))
        for pid, codes in grouped.items()
    ]
    return PositionActivitiesPage(items=items, total=len(items))


@router.put(
    "/medical/psychiatric/positions/{position_id}/activities",
    response_model=PositionActivitiesRead,
    dependencies=[MedicalFeatureGate],
)
async def set_position_activities(
    request: Request,
    position_id: str,
    payload: PositionActivitiesIn,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalAccess,
) -> PositionActivitiesRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    tid = str(tenant.id)
    # position must exist in tenant
    pos = await session.scalar(
        select(Position).where(Position.id == position_id, Position.tenant_id == tid)
    )
    if pos is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=_error("position_not_found", "Position not found")
        )
    codes = list(dict.fromkeys(payload.activity_codes))  # dedupe, preserve order
    if codes:
        known = {
            c
            for (c,) in (
                await session.execute(
                    select(PsychiatricActivityType.code).where(
                        PsychiatricActivityType.tenant_id == tid,
                        PsychiatricActivityType.code.in_(tuple(codes)),
                    )
                )
            ).all()
        }
        unknown = [c for c in codes if c not in known]
        if unknown:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=_error(
                    "activity_code_unknown", f"Unknown activity codes: {', '.join(unknown)}"
                ),
            )
    # replace semantics: clear then insert
    await session.execute(
        delete(PsychiatricPositionActivity).where(
            PsychiatricPositionActivity.tenant_id == tid,
            PsychiatricPositionActivity.position_id == position_id,
        )
    )
    for code in codes:
        session.add(
            PsychiatricPositionActivity(
                tenant_id=tid, position_id=position_id, activity_code=code
            )
        )
    audit = AuditService(session)
    await audit.log_event(
        tenant_id=tid,
        action="update",
        object_type="psychiatric_position_activity",
        object_id=position_id,
        user_id=getattr(access.user, "id", None),
        ip=_audit_ip(request),
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={"activity_codes": codes},
    )
    await session.commit()
    return PositionActivitiesRead(
        position_id=position_id, activity_codes=await _position_codes(session, tid, position_id)
    )
```

- [ ] **Step 5: Register the module in `__init__.py`**

In `backend/app/api/routes/medical/__init__.py`, add the import in registration order (after `contingent`):

```python
from app.api.routes.medical import contingent  # noqa: F401  (mappings/contingent/summary)
from app.api.routes.medical import psychiatric  # noqa: F401  (342н activity catalog/mapping)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `& "...python.exe" -m pytest tests/api/test_medical_psychiatric_api.py -q`
Expected: PASS (all 4 tests).

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/routes/medical/psychiatric.py backend/app/api/routes/medical/_common.py backend/app/api/routes/medical/__init__.py tests/api/test_medical_psychiatric_api.py
git commit -m "feat(p10-03): psychiatric routes — activity catalog + seed-defaults + mapping"
```

---

## Task 8: Exams route — thread the 2 new fields

**Files:**
- Modify: `backend/app/api/routes/medical/exams.py`
- Test: `tests/api/test_medical_psychiatric_api.py` (add a case)

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_medical_psychiatric_api.py`:

```python
@pytest.mark.asyncio
async def test_create_psychiatric_exam_persists_new_fields(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(
            tenant=tenant, company=company, session=session,
            first_name="Марк", last_name="Лев",
        )
        await session.commit()
        pid = person.id
    headers = await make_auth_headers(RoleEnum.ADMIN)
    body = {
        "person_id": pid,
        "exam_kind": "psychiatric",
        "exam_date": "2026-01-01",
        "fitness": "fit",
        "medical_org_name": "ВК № 7",
        "psychiatric_protocol_no": "ПРО-99",
        "psychiatric_activity_codes": ["height"],
    }
    r = await async_client.post("/api/v1/medical/exams", headers=headers, json=body)
    assert r.status_code == status.HTTP_201_CREATED, r.text
    data = r.json()
    assert data["psychiatric_protocol_no"] == "ПРО-99"
    assert data["psychiatric_activity_codes"] == ["height"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& "...python.exe" -m pytest "tests/api/test_medical_psychiatric_api.py::test_create_psychiatric_exam_persists_new_fields" -q`
Expected: FAIL — response `psychiatric_protocol_no` is `None` (route drops the fields).

- [ ] **Step 3: Pass the fields in `create_medical_exam`**

In `backend/app/api/routes/medical/exams.py`, in the `medsvc.record_exam(...)` call (line ~161), add after `exam_type=payload.exam_type,`:

```python
            exam_type=payload.exam_type,
            psychiatric_protocol_no=payload.psychiatric_protocol_no,
            psychiatric_activity_codes=payload.psychiatric_activity_codes,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `& "...python.exe" -m pytest "tests/api/test_medical_psychiatric_api.py::test_create_psychiatric_exam_persists_new_fields" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/medical/exams.py tests/api/test_medical_psychiatric_api.py
git commit -m "feat(p10-03): thread psychiatric exam fields through create_medical_exam"
```

---

## Task 9: Demo seed — psychiatric activities + position mapping

**Files:**
- Modify: `backend/app/services/demo_bootstrap.py`
- Test: `tests/test_medical_psychiatric_seed.py` (add a case)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_medical_psychiatric_seed.py`:

```python
@pytest.mark.asyncio
async def test_demo_seed_maps_position_to_activity(sessionmaker, data_factory):
    from app.models.models import Position, PsychiatricPositionActivity
    from app.services.demo_bootstrap import _seed_psychiatric_activities_demo

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        pos = Position(tenant_id=tenant.id, company_id=company.id, name="Демо-должность")
        session.add(pos)
        await session.flush()
        await _seed_psychiatric_activities_demo(session, str(tenant.id), str(pos.id))
        await session.commit()
        rows = (
            await session.execute(
                select(PsychiatricPositionActivity.activity_code).where(
                    PsychiatricPositionActivity.tenant_id == tenant.id,
                    PsychiatricPositionActivity.position_id == pos.id,
                )
            )
        ).all()
    assert ("height",) in rows
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& "...python.exe" -m pytest "tests/test_medical_psychiatric_seed.py::test_demo_seed_maps_position_to_activity" -q`
Expected: FAIL — `ImportError: _seed_psychiatric_activities_demo`.

- [ ] **Step 3: Add the demo seeder + wire it in**

In `backend/app/services/demo_bootstrap.py`, add `PsychiatricPositionActivity` to the models import block (line ~20, alphabetical with the other medical imports) and add the function after `_seed_medical_factor_demo` (line ~226):

```python
async def _seed_psychiatric_activities_demo(
    session, tenant_db_id: str, position_id: str
) -> None:
    """342н: seed the standard 695 activity-type set and map the demo position to «height»,
    so the demo психиатрический контингент is non-empty out of the box. Idempotent."""
    from app.domains.medical.service import seed_default_activity_types

    await seed_default_activity_types(session, tenant_id=tenant_db_id)
    existing = (
        await session.execute(
            select(PsychiatricPositionActivity).where(
                PsychiatricPositionActivity.tenant_id == tenant_db_id,
                PsychiatricPositionActivity.position_id == position_id,
                PsychiatricPositionActivity.activity_code == "height",
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            PsychiatricPositionActivity(
                tenant_id=tenant_db_id, position_id=position_id, activity_code="height"
            )
        )
        await session.flush()
```

Wire it into the demo block next to the factor seed (line ~1021):

```python
            await _seed_medical_factor_demo(session, tenant_db_id, str(position.id))
            await _seed_psychiatric_activities_demo(session, tenant_db_id, str(position.id))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `& "...python.exe" -m pytest "tests/test_medical_psychiatric_seed.py::test_demo_seed_maps_position_to_activity" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/demo_bootstrap.py tests/test_medical_psychiatric_seed.py
git commit -m "feat(p10-03): demo-seed 695 activities + map demo position"
```

---

## Task 10: Frontend — api methods + thin MedicalPage section

**Files:**
- Modify: `frontend/src/api/operations.ts`
- Modify: `frontend/src/pages/medical/MedicalPage.tsx`
- Test: `frontend/src/pages/medical/MedicalPage.test.tsx` (create)

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/medical/MedicalPage.test.tsx`:

```tsx
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import MedicalPage from "./MedicalPage";
import { operationsApi } from "@/api/operations";

vi.mock("@/api/operations", () => ({
  operationsApi: {
    getMedicalSnapshot: vi.fn(),
    getPsychiatricSnapshot: vi.fn(),
    seedPsychiatricDefaults: vi.fn(),
  },
}));

beforeEach(() => {
  (operationsApi.getMedicalSnapshot as any).mockResolvedValue({ exams: [], persons: [], tasks: [] });
  (operationsApi.getPsychiatricSnapshot as any).mockResolvedValue({
    activityTypes: [{ id: "a1", code: "height", name: "Работы на высоте", interval_days: 1825 }],
    contingent: [],
  });
  (operationsApi.seedPsychiatricDefaults as any).mockResolvedValue({ count: 9 });
});

describe("MedicalPage psychiatric section", () => {
  it("renders the 342н section with activity types", async () => {
    render(<MedicalPage />);
    await waitFor(() =>
      expect(screen.getByText(/Психиатрическое освидетельствование/i)).toBeInTheDocument()
    );
    expect(await screen.findByText(/Работы на высоте/)).toBeInTheDocument();
  });

  it("calls seedPsychiatricDefaults when the seed button is clicked", async () => {
    (operationsApi.getPsychiatricSnapshot as any).mockResolvedValue({ activityTypes: [], contingent: [] });
    render(<MedicalPage />);
    const btn = await screen.findByRole("button", { name: /Загрузить стандартный список 695/i });
    fireEvent.click(btn);
    await waitFor(() => expect(operationsApi.seedPsychiatricDefaults).toHaveBeenCalled());
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (Bash, from `frontend/`): `npx vitest run src/pages/medical/MedicalPage.test.tsx`
Expected: FAIL — `getPsychiatricSnapshot` not exported / section not rendered.

- [ ] **Step 3: Add the api methods**

In `frontend/src/api/operations.ts`, add inside the `operationsApi` object (near `getMedicalSnapshot`, line ~295):

```ts
  getPsychiatricSnapshot: async () => {
    const [typesResponse, contingentResponse] = await Promise.all([
      apiClient.get<{ items: { id: string; code: string; name: string; interval_days: number }[]; total: number }>(
        "/medical/psychiatric/activity-types",
        { params: { limit: 200, offset: 0 } }
      ),
      apiClient.get<{ items: { person_id: string; exam_kind: string; status: string; due_at: string | null }[]; total: number }>(
        "/medical/contingent",
        { params: {} }
      ),
    ]);
    return {
      activityTypes: typesResponse.data.items ?? [],
      contingent: (contingentResponse.data.items ?? []).filter((i) => i.exam_kind === "psychiatric"),
    };
  },

  seedPsychiatricDefaults: async () => {
    const response = await apiClient.post<{ count: number }>(
      "/medical/psychiatric/activity-types/seed-defaults"
    );
    return response.data;
  },

  setPositionActivities: async (positionId: string, activityCodes: string[]) => {
    const response = await apiClient.put<{ position_id: string; activity_codes: string[] }>(
      `/medical/psychiatric/positions/${positionId}/activities`,
      { activity_codes: activityCodes }
    );
    return response.data;
  },
```

- [ ] **Step 4: Add the thin section to `MedicalPage.tsx`**

Replace the whole `MedicalPage.tsx` body with the version below (adds a second `useAsyncResource` for the psychiatric snapshot and renders a section under the existing table):

```tsx
import { useCallback, useMemo, useState } from "react";

import { operationsApi } from "@/api/operations";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { formatDate } from "@/utils/datetime";

const MedicalPage = () => {
  const { data, loading, error, reload } = useAsyncResource({
    loader: useCallback(() => operationsApi.getMedicalSnapshot(), []),
    initialData: { exams: [], persons: [], tasks: [] },
    errorMessage: "Не удалось загрузить медосмотры"
  });

  const psych = useAsyncResource({
    loader: useCallback(() => operationsApi.getPsychiatricSnapshot(), []),
    initialData: { activityTypes: [], contingent: [] },
    errorMessage: "Не удалось загрузить психиатрическое освидетельствование"
  });
  const [seeding, setSeeding] = useState(false);

  const onSeed = useCallback(async () => {
    setSeeding(true);
    try {
      await operationsApi.seedPsychiatricDefaults();
      await psych.reload();
    } finally {
      setSeeding(false);
    }
  }, [psych]);

  const items = useMemo(
    () => data.exams.map((exam) => ({ ...exam, person: data.persons.find((person) => person.id === exam.person_id) })),
    [data]
  );
  const registry = useLocalRegistry({
    items,
    match: (item, query) => [item.person?.full_name, item.exam_type, item.conclusion].filter(Boolean).join(" ").toLowerCase().includes(query)
  });

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Медосмотры и допуски"
        description="Реестр использует эндпоинт `/medical/exams` и связывает его с людьми и обязательствами."
        stats={[
          { label: "Медосмотров", value: data.exams.length },
          { label: "Просрочено", value: data.exams.filter((item) => new Date(item.valid_until) < new Date()).length },
          { label: "Задач по медосмотрам", value: data.tasks.length }
        ]}
      />
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка медосмотров" /> : null}
      {!loading && !error && registry.total === 0 ? <EmptyState title="Медосмотры не найдены" description="Добавьте записи медосмотров или создайте требования." /> : null}
      {!loading && !error && registry.total > 0 ? (
        <RegistryTable
          columns={[
            { id: "person", header: "Сотрудник", cell: ({ row }) => row.original.person?.full_name || row.original.person_id },
            { accessorKey: "exam_type", header: "Тип" },
            { accessorKey: "exam_date", header: "Дата", cell: ({ row }) => formatDate(row.original.exam_date) },
            { accessorKey: "valid_until", header: "Действует до", cell: ({ row }) => formatDate(row.original.valid_until) },
            { id: "state", header: "Состояние", cell: ({ row }) => <StatusBadge status={new Date(row.original.valid_until) < new Date() ? "overdue" : "ready"} /> },
            { accessorKey: "conclusion", header: "Заключение", cell: ({ row }) => row.original.conclusion || "—" }
          ]}
          data={registry.pagedItems}
          pageIndex={registry.pageIndex}
          pageSize={registry.pageSize}
          total={registry.total}
          onPageChange={registry.onPageChange}
          onPageSizeChange={registry.onPageSizeChange}
          onSearchChange={registry.onSearchChange}
          searchPlaceholder="Поиск по сотруднику, типу, заключению"
          caption="Реестр медицинских осмотров"
        />
      ) : null}

      <section className="rounded-lg border border-border p-4 space-y-3">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold">Психиатрическое освидетельствование (342н)</h2>
            <p className="text-sm text-muted-foreground">Виды деятельности по перечню ПП РФ № 695 и подлежащий контингент.</p>
          </div>
          {psych.data.activityTypes.length === 0 ? (
            <button
              type="button"
              className="rounded-md border border-border px-3 py-1.5 text-sm"
              onClick={() => void onSeed()}
              disabled={seeding}
            >
              {seeding ? "Загрузка…" : "Загрузить стандартный список 695"}
            </button>
          ) : null}
        </div>
        <ErrorState error={psych.error ?? undefined} onRetry={() => void psych.reload()} />
        {psych.data.activityTypes.length > 0 ? (
          <ul className="grid gap-1 text-sm sm:grid-cols-2">
            {psych.data.activityTypes.map((a) => (
              <li key={a.id} className="flex justify-between gap-2 border-b border-border/50 py-1">
                <span>{a.name}</span>
                <span className="text-muted-foreground">{Math.round(a.interval_days / 365)} лет</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">Каталог видов деятельности пуст.</p>
        )}
        <div className="text-sm">
          Подлежит освидетельствованию (контингент): <strong>{psych.data.contingent.length}</strong>
        </div>
      </section>
    </div>
  );
};

export default MedicalPage;
```

- [ ] **Step 5: Run test to verify it passes**

Run (Bash, from `frontend/`): `npx vitest run src/pages/medical/MedicalPage.test.tsx`
Expected: PASS (both cases).

- [ ] **Step 6: Typecheck + build**

Run (Bash, from `frontend/`): `npx tsc --noEmit && npx vite build`
Expected: exit 0.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/operations.ts frontend/src/pages/medical/MedicalPage.tsx frontend/src/pages/medical/MedicalPage.test.tsx
git commit -m "feat(p10-03): MedicalPage 342н section + psychiatric api methods"
```

---

## Task 11: Gates + docs (OpenAPI baseline, lint/format, PG16, roadmap/changelog/handoff)

**Files:**
- Modify: `docs/stabilization/openapi_routes_baseline.json` (OpenAPI baseline, additive re-snap)
- Modify: `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md` (P10-03 row)
- Modify: `CHANGELOG.md`
- Modify: `AI_IMPLEMENTATION_REPORT.md` (new handoff block at top)

- [ ] **Step 1: Full backend regression (batched)**

Run (PowerShell, timeout 600000, ONE run) in ≤4-file batches:
```
& "...python.exe" -m pytest backend/tests/test_medical_psychiatric_model.py backend/tests/test_medical_psychiatric_migration.py backend/tests/test_medical_psychiatric_schemas.py tests/unit/test_medical_psychiatric_lifecycle.py -q
& "...python.exe" -m pytest tests/test_medical_psychiatric_contingent.py tests/test_medical_psychiatric_seed.py tests/api/test_medical_psychiatric_api.py -q
& "...python.exe" -m pytest tests/test_medical_contingent_factor.py tests/test_medical_service.py tests/api/test_medical_api.py tests/api/test_medical_factors_api.py -q
```
Expected: all exit 0 (last batch = invariant anchor: existing medical tests unaffected).

- [ ] **Step 2: Lint + format**

Run: `& "...python.exe" -m ruff check backend/app tests backend/tests` → All checks passed.
Run: `& "...python.exe" -m black backend/app tests backend/tests` then **re-run** `test_medical_psychiatric_migration.py` (black may reformat the migration; the `_norm` test tolerates it, but confirm).

- [ ] **Step 3: OpenAPI baseline re-snap (additive only)**

First confirm the drift is additive: `$env:PYTHONPATH="backend"; & "...python.exe" scripts/ci/check_openapi_snapshot.py` (no flag = compare; will report the new routes as drift, exit 1 — expected). Then re-snap: `$env:PYTHONPATH="backend"; & "...python.exe" scripts/ci/check_openapi_snapshot.py --snapshot` (writes `docs/stabilization/openapi_routes_baseline.json`).
Then `git diff docs/stabilization/openapi_routes_baseline.json`: expect only **added** routes (`/medical/psychiatric/*`) + schemas (`Psychiatric*`, `PositionActivities*`, +2 fields on `MedicalExam*`), **0 deletions** (ARCH-4). Re-run compare (no flag) → EXIT 0.

- [ ] **Step 4: PG16 migration gate**

Run: `& "...python.exe" scripts/ci/local_gate.py --db-only` (needs Docker).
Expected: alembic upgrade heads (incl. `med03`) + downgrade round-trip + enum guards green; ARCH-3 boundaries clean (0 new).

- [ ] **Step 5: Update docs**

- `PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md` P10-03 row (line ~655): add shipped prose (психиатрическое освидетельствование 342н — каталог видов деятельности 695 + маппинг должность→вид + вторая ось контингента + расширенный exam + demo/seed-defaults), and trim «психиатрия» from the «Остаётся» clause (leaving контингент-UI/направления-UI/отстранение-UI).
- `CHANGELOG.md`: new entry dated 2026-07-09.
- `AI_IMPLEMENTATION_REPORT.md`: prepend a new «Last Agent Handoff (2026-07-09, P10-03 МЕДОСМОТРЫ — ПСИХИАТРИЯ 342н …)» block following the house format (decisions, architecture, verification, deferred, next step).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "docs(p10-03): roadmap + changelog + handoff + OpenAPI baseline for psychiatric 342n"
```

---

## Self-review notes (author)

- **Spec coverage:** model (§1)→T1/T2; pure logic (§2)→T3; contingent (§3)→T4; referral/suspension/block (§4)→T4/T5 (reused, asserted in T5); routes (§5)→T7/T8; seed 695 (§6)→T5/T9; frontend (§7)→T10; tests/gates (§8)→every task + T11. All spec sections have tasks.
- **Type consistency:** `record_exam(..., psychiatric_protocol_no, psychiatric_activity_codes)` defined in T5, consumed in T8 route. `seed_default_activity_types` defined T5, used in T7 endpoint + T9 demo. `_load_activity_catalog` defined T4, used by `_psychiatric_interval_days` in T5 (ordering noted). `ActivityTuple`/`psychiatric_required`/`psychiatric_interval` defined T3, used T4/T5. Schema names (`PsychiatricActivityType*`, `PositionActivities*`) defined T6, used T7. Route paths in T7 tests match T7 handlers and T10 api-client (`/medical/psychiatric/activity-types`, `/seed-defaults`, `/positions/{id}/activities`).
- **No placeholders:** every code step shows full code; every run step shows command + expected result.
- **Deferred (unchanged from spec):** per-activity partial restriction, printable направление/решение form, psychiatric-specific register prints, commission-member modeling, on-indication repeat logic, mapping-editor UI beyond the read/seed section (mapping is set via API/tests this slice; a full per-position editor is a follow-up).
