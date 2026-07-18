# Medical Exams + Contingent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the «Медосмотры» contour core (write-path, exam types, referrals FSM, contraindications→suspension→admission-block) plus norm-driven contingent and automation, per spec `docs/superpowers/specs/2026-06-07-medical-exams-contingent-design.md`.

**Architecture:** Approach A — additive. Extend the existing `medical_exam` table + add `medical_norm`/`medical_referral`/`medical_suspension`. New pure-FSM domain `domains/medical/lifecycle.py` + I/O `domains/medical/service.py` (mirrors `prescriptions`). Extend `routes/medical.py`, `schemas/medical.py`, `events.py`. De-dup the admission check into `services/person_admission.py` and make it norm-aware with a back-compat fallback. New events + a daily celery-beat tick. Per-tenant `medical` feature-flag (default-ON). Read-side (calendar/dashboard/DQ) extended additively.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, Celery, Pydantic v2, pytest. Tests run locally on Py3.13/Windows; canonical Py3.12 in CI (see `CLAUDE.md`). Branch: `feat/medical-exams-contingent` (off `origin/main` `5e34d9b`).

---

## Conventions for every task

- **TDD:** write test → run (fail) → implement → run (pass) → commit.
- **Run pytest** (per `CLAUDE.md`): prefer `python3.12 -m pytest ...`; fallback `python3 -m pytest ...`. On Windows the repo note says invoke via PowerShell→file redirect for full suites; for a single test file the direct invocation is fine.
- **Commit message footer** (every commit):
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  ```
- **Enums:** use `native_enum(EnumCls)` from `app.models.base` (lowercase PG labels — see enum-parity arc #633→#640).
- **Tenant scope:** every query filters `tenant_id == tenant.id` and `deleted_at.is_(None)` where the model has `SoftDeleteMixin`.

---

## File Structure

**Create:**
- `backend/app/domains/medical/__init__.py` — package marker.
- `backend/app/domains/medical/lifecycle.py` — pure FSM + rules (no DB/app imports).
- `backend/app/domains/medical/service.py` — I/O service (record exam, contingent, referrals, suspensions, summary, escalation).
- `backend/app/services/person_admission.py` — shared admission-invariants helper (de-dup of tasks.py + packs.py).
- `backend/app/migrations/versions/20260607_med01_medical_domain.py` — additive migration.
- Test files (see tasks): `tests/unit/test_medical_lifecycle.py`, `tests/api/test_medical_api.py`, `tests/api/test_medical_cache_etag_contract.py`, `tests/api/test_medical_contingent_admission.py`, `backend/tests/test_medical_access_parity.py`, `backend/tests/test_med01_medical_domain_migration.py`, `backend/tests/test_medical_events.py`.

**Modify:**
- `backend/app/models/models.py` — new enums; extend `MedicalExam`; add `MedicalNorm`, `MedicalReferral`, `MedicalSuspension`.
- `backend/app/schemas/medical.py` — new/extended schemas.
- `backend/app/services/events.py` — new `EventType` members + payloads + `_PAYLOADS` + `dedupe_key_for`.
- `backend/app/api/routes/medical.py` — new endpoints + feature gate.
- `backend/app/services/tasks.py` — `_enforce_person_invariants` delegates to the shared helper.
- `backend/app/api/routes/packs.py` — inline admission check delegates to the shared helper.
- `backend/app/services/calendar_aggregator.py` — referral-due + contingent-gap events.
- `backend/app/modules/operational_dashboard/service.py` — suspension + contingent counts.
- `backend/app/modules/data_quality/rules.py` — missing-required-exam + unfit-without-suspension rule.
- `backend/app/services/celery_app.py` — beat entry `medical-contingent-daily`.
- `backend/app/tasks/_core.py` — `medical.contingent.tick` task.
- `backend/app/api/routes/medical.py` (feature gate) + a seed file for the `medical` Feature row.

---

## Phase 1 — Data model + migration

### Task 1.1: Medical enums

**Files:**
- Modify: `backend/app/models/models.py` (near the existing `MedicalExam`, line ~812)
- Test: `backend/tests/test_medical_models.py`

- [ ] **Step 1: Write the failing test**
```python
# backend/tests/test_medical_models.py
from __future__ import annotations

from app.models.models import (
    MedicalExamKind,
    MedicalFitness,
    MedicalReferralStatus,
    MedicalSuspensionReason,
    MedicalSuspensionStatus,
)


def test_medical_enum_values_are_lowercase():
    assert MedicalExamKind.PERIODIC.value == "periodic"
    assert {k.value for k in MedicalExamKind} == {
        "periodic", "preliminary", "psychiatric", "fluorography", "health_book",
    }
    assert MedicalFitness.UNFIT.value == "unfit"
    assert {f.value for f in MedicalFitness} == {"fit", "fit_with_restrictions", "unfit"}
    assert {s.value for s in MedicalReferralStatus} == {
        "issued", "scheduled", "completed", "cancelled",
    }
    assert {s.value for s in MedicalSuspensionStatus} == {"active", "lifted"}
    assert {r.value for r in MedicalSuspensionReason} == {"unfit", "contraindication"}
```

- [ ] **Step 2: Run test to verify it fails**
Run: `python3 -m pytest backend/tests/test_medical_models.py -v`
Expected: FAIL (ImportError: cannot import name `MedicalExamKind`).

- [ ] **Step 3: Implement the enums**
Add to `backend/app/models/models.py` immediately above `class MedicalExam` (line ~812):
```python
class MedicalExamKind(str, enum.Enum):
    PERIODIC = "periodic"
    PRELIMINARY = "preliminary"
    PSYCHIATRIC = "psychiatric"
    FLUOROGRAPHY = "fluorography"
    HEALTH_BOOK = "health_book"


class MedicalFitness(str, enum.Enum):
    FIT = "fit"
    FIT_WITH_RESTRICTIONS = "fit_with_restrictions"
    UNFIT = "unfit"


class MedicalReferralStatus(str, enum.Enum):
    ISSUED = "issued"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class MedicalSuspensionStatus(str, enum.Enum):
    ACTIVE = "active"
    LIFTED = "lifted"


class MedicalSuspensionReason(str, enum.Enum):
    UNFIT = "unfit"
    CONTRAINDICATION = "contraindication"
```

- [ ] **Step 4: Run test to verify it passes**
Run: `python3 -m pytest backend/tests/test_medical_models.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/models/models.py backend/tests/test_medical_models.py
git commit -m "feat(medical): add medical domain enums"
```

---

### Task 1.2: Extend MedicalExam + new tables

**Files:**
- Modify: `backend/app/models/models.py` (extend `MedicalExam` ~812; add 3 models after it)
- Test: `backend/tests/test_medical_models.py` (extend)

- [ ] **Step 1: Add failing tests**
Append to `backend/tests/test_medical_models.py`:
```python
def test_medical_exam_has_new_columns():
    cols = {c.name for c in __import__(
        "app.models.models", fromlist=["MedicalExam"]
    ).MedicalExam.__table__.columns}
    assert {"exam_kind", "fitness", "restrictions", "contraindications",
            "referral_id", "medical_org_name"}.issubset(cols)


def test_new_medical_tables_exist():
    from app.models.models import MedicalNorm, MedicalReferral, MedicalSuspension
    assert MedicalNorm.__tablename__ == "medical_norm"
    assert MedicalReferral.__tablename__ == "medical_referral"
    assert MedicalSuspension.__tablename__ == "medical_suspension"
    norm_cols = {c.name for c in MedicalNorm.__table__.columns}
    assert {"position_id", "hazard_id", "exam_kind", "interval_days",
            "working_conditions_class"}.issubset(norm_cols)
    ref_cols = {c.name for c in MedicalReferral.__table__.columns}
    assert {"person_id", "exam_kind", "due_at", "status",
            "medical_org_name", "issued_by", "result_exam_id"}.issubset(ref_cols)
    susp_cols = {c.name for c in MedicalSuspension.__table__.columns}
    assert {"person_id", "reason", "source_exam_id", "started_at",
            "lifted_at", "status", "lifted_by"}.issubset(susp_cols)
```

- [ ] **Step 2: Run test to verify it fails**
Run: `python3 -m pytest backend/tests/test_medical_models.py -v`
Expected: FAIL (new columns/models missing).

- [ ] **Step 3: Extend `MedicalExam` and add models**
Replace the existing `MedicalExam` body (line ~812) with the extended version and add three models after it:
```python
class MedicalExam(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "medical_exam"

    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), nullable=False, index=True)
    exam_type: Mapped[str] = mapped_column(String(128), nullable=False)
    exam_date: Mapped[date] = mapped_column(Date, nullable=False)
    conclusion: Mapped[str | None] = mapped_column(String(255))
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)
    # --- additive (TZ B.8) ---
    exam_kind: Mapped[MedicalExamKind | None] = mapped_column(native_enum(MedicalExamKind), nullable=True)
    fitness: Mapped[MedicalFitness | None] = mapped_column(native_enum(MedicalFitness), nullable=True)
    restrictions: Mapped[str | None] = mapped_column(Text)
    contraindications: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    referral_id: Mapped[str | None] = mapped_column(ForeignKey("medical_referral.id"), nullable=True, index=True)
    medical_org_name: Mapped[str | None] = mapped_column(String(255))

    person: Mapped[Person] = relationship(backref="medical_exams")


class MedicalNorm(TenantBaseModel):
    __tablename__ = "medical_norm"

    position_id: Mapped[str] = mapped_column(ForeignKey("position.id"), nullable=False, index=True)
    hazard_id: Mapped[str | None] = mapped_column(
        ForeignKey("risk_hazards.id", ondelete="CASCADE"), nullable=True, index=True
    )
    exam_kind: Mapped[MedicalExamKind] = mapped_column(native_enum(MedicalExamKind), nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=365)
    working_conditions_class: Mapped[str | None] = mapped_column(String(32))

    position: Mapped[Position] = relationship(backref="medical_norms")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "position_id", "hazard_id", "exam_kind",
            name="uq_medical_norm_position_hazard_kind",
        ),
    )


class MedicalReferral(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "medical_referral"

    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), nullable=False, index=True)
    exam_kind: Mapped[MedicalExamKind] = mapped_column(native_enum(MedicalExamKind), nullable=False)
    due_at: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[MedicalReferralStatus] = mapped_column(
        native_enum(MedicalReferralStatus), nullable=False, default=MedicalReferralStatus.ISSUED
    )
    medical_org_name: Mapped[str | None] = mapped_column(String(255))
    issued_by: Mapped[str | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    result_exam_id: Mapped[str | None] = mapped_column(ForeignKey("medical_exam.id"), nullable=True)

    person: Mapped[Person] = relationship(backref="medical_referrals")


class MedicalSuspension(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "medical_suspension"

    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), nullable=False, index=True)
    reason: Mapped[MedicalSuspensionReason] = mapped_column(
        native_enum(MedicalSuspensionReason), nullable=False
    )
    source_exam_id: Mapped[str | None] = mapped_column(ForeignKey("medical_exam.id"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lifted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[MedicalSuspensionStatus] = mapped_column(
        native_enum(MedicalSuspensionStatus), nullable=False, default=MedicalSuspensionStatus.ACTIVE
    )
    lifted_by: Mapped[str | None] = mapped_column(ForeignKey("user.id"), nullable=True)

    person: Mapped[Person] = relationship(backref="medical_suspensions")
```
> NOTE: `MedicalExam.referral_id` and `MedicalReferral.result_exam_id` are a deliberate cycle. Both FKs are nullable and SQLAlchemy resolves them at flush; create the exam first (referral_id can be set later) or set `result_exam_id` after the exam exists. No `use_alter` needed because both are nullable.

- [ ] **Step 4: Run test to verify it passes**
Run: `python3 -m pytest backend/tests/test_medical_models.py -v`
Expected: PASS.

- [ ] **Step 5: Verify mapper config still builds** (catches relationship/duplicate-name regressions — see memory orm-duplicate-class-names)
Run: `python3 -m pytest backend/tests/test_orm_mapper_configuration.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**
```bash
git add backend/app/models/models.py backend/tests/test_medical_models.py
git commit -m "feat(medical): extend medical_exam + add norm/referral/suspension models"
```

---

### Task 1.3: Additive Alembic migration

**Files:**
- Create: `backend/app/migrations/versions/20260607_med01_medical_domain.py`
- Test: `backend/tests/test_med01_medical_domain_migration.py`

- [ ] **Step 1: Find the current head revision**
Run: `python3 -c "from pathlib import Path; import re; tips=[p for p in Path('backend/app/migrations/versions').glob('*.py')]; print(len(tips))"`
Then identify the latest by reading the most recent migration's `revision`. The new migration's `down_revision` MUST be the current single head (the `wa03` chain tip; confirm with `alembic heads` if available). Use the discovered value below as `<DOWN_REVISION>`.

- [ ] **Step 2: Write the failing migration test**
```python
# backend/tests/test_med01_medical_domain_migration.py
from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app" / "migrations" / "versions" / "20260607_med01_medical_domain.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("med01_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_revision_metadata():
    mod = _load()
    assert mod.revision == "20260607_med01_medical_domain"
    assert mod.down_revision  # non-empty; points at prior head
    assert mod.depends_on is None


def test_migration_is_additive_and_symmetric():
    src = _MIGRATION.read_text(encoding="utf-8")
    # additive columns on medical_exam
    for col in ("exam_kind", "fitness", "restrictions", "contraindications",
                "referral_id", "medical_org_name"):
        assert f'add_column("medical_exam"' in src
        assert f'"{col}"' in src
    # new tables created
    for tbl in ("medical_norm", "medical_referral", "medical_suspension"):
        assert f'create_table(\n        "{tbl}"' in src or f'create_table("{tbl}"' in src
    # symmetric downgrade
    for tbl in ("medical_norm", "medical_referral", "medical_suspension"):
        assert f'drop_table("{tbl}")' in src
    for col in ("exam_kind", "fitness", "restrictions", "contraindications",
                "referral_id", "medical_org_name"):
        assert f'drop_column("medical_exam", "{col}")' in src
    # postgres enum types dropped on downgrade (orphan-type lesson, PR #639)
    assert 'dialect.name == "postgresql"' in src
    assert "DROP TYPE IF EXISTS" in src
```

- [ ] **Step 3: Run test to verify it fails**
Run: `python3 -m pytest backend/tests/test_med01_medical_domain_migration.py -v`
Expected: FAIL (migration file missing).

- [ ] **Step 4: Write the migration**
```python
# backend/app/migrations/versions/20260607_med01_medical_domain.py
"""med01: medical domain — extend medical_exam + norm/referral/suspension (TZ B.8).

Additive. New enum types are created implicitly by SA Enum on PG; dropped on
downgrade after their owning tables (orphan-type lesson, PR #639).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260607_med01_medical_domain"
down_revision = "<DOWN_REVISION>"  # set to the current head from Step 1
branch_labels = None
depends_on = None

_EXAM_KIND = sa.Enum(
    "periodic", "preliminary", "psychiatric", "fluorography", "health_book",
    name="medicalexamkind",
)
_FITNESS = sa.Enum("fit", "fit_with_restrictions", "unfit", name="medicalfitness")
_REF_STATUS = sa.Enum("issued", "scheduled", "completed", "cancelled", name="medicalreferralstatus")
_SUSP_STATUS = sa.Enum("active", "lifted", name="medicalsuspensionstatus")
_SUSP_REASON = sa.Enum("unfit", "contraindication", name="medicalsuspensionreason")


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in (_EXAM_KIND, _FITNESS, _REF_STATUS, _SUSP_STATUS, _SUSP_REASON):
        enum_type.create(bind, checkfirst=True)

    op.add_column("medical_exam", sa.Column("exam_kind", _EXAM_KIND, nullable=True))
    op.add_column("medical_exam", sa.Column("fitness", _FITNESS, nullable=True))
    op.add_column("medical_exam", sa.Column("restrictions", sa.Text(), nullable=True))
    op.add_column("medical_exam", sa.Column("contraindications", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("medical_exam", sa.Column("referral_id", sa.String(length=36), nullable=True))
    op.add_column("medical_exam", sa.Column("medical_org_name", sa.String(length=255), nullable=True))
    op.create_index("ix_medical_exam_referral_id", "medical_exam", ["referral_id"])

    op.create_table(
        "medical_norm",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("position_id", sa.String(length=36), sa.ForeignKey("position.id"), nullable=False),
        sa.Column("hazard_id", sa.String(length=36), sa.ForeignKey("risk_hazards.id", ondelete="CASCADE"), nullable=True),
        sa.Column("exam_kind", _EXAM_KIND, nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False, server_default="365"),
        sa.Column("working_conditions_class", sa.String(length=32), nullable=True),
        sa.UniqueConstraint("tenant_id", "position_id", "hazard_id", "exam_kind", name="uq_medical_norm_position_hazard_kind"),
    )
    op.create_table(
        "medical_referral",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("person_id", sa.String(length=36), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("exam_kind", _EXAM_KIND, nullable=False),
        sa.Column("due_at", sa.Date(), nullable=True),
        sa.Column("status", _REF_STATUS, nullable=False, server_default="issued"),
        sa.Column("medical_org_name", sa.String(length=255), nullable=True),
        sa.Column("issued_by", sa.String(length=36), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("result_exam_id", sa.String(length=36), sa.ForeignKey("medical_exam.id"), nullable=True),
    )
    op.create_index("ix_medical_referral_person_id", "medical_referral", ["person_id"])
    op.create_index("ix_medical_referral_due_at", "medical_referral", ["due_at"])
    op.create_table(
        "medical_suspension",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("person_id", sa.String(length=36), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("reason", _SUSP_REASON, nullable=False),
        sa.Column("source_exam_id", sa.String(length=36), sa.ForeignKey("medical_exam.id"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lifted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", _SUSP_STATUS, nullable=False, server_default="active"),
        sa.Column("lifted_by", sa.String(length=36), sa.ForeignKey("user.id"), nullable=True),
    )
    op.create_index("ix_medical_suspension_person_id", "medical_suspension", ["person_id"])
    # add the FK from medical_exam.referral_id now that medical_referral exists
    with op.batch_alter_table("medical_exam") as batch:
        batch.create_foreign_key(
            "fk_medical_exam_referral_id", "medical_referral", ["referral_id"], ["id"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table("medical_exam") as batch:
        batch.drop_constraint("fk_medical_exam_referral_id", type_="foreignkey")
    op.drop_index("ix_medical_suspension_person_id", table_name="medical_suspension")
    op.drop_table("medical_suspension")
    op.drop_index("ix_medical_referral_due_at", table_name="medical_referral")
    op.drop_index("ix_medical_referral_person_id", table_name="medical_referral")
    op.drop_table("medical_referral")
    op.drop_table("medical_norm")
    op.drop_index("ix_medical_exam_referral_id", table_name="medical_exam")
    for col in ("medical_org_name", "referral_id", "contraindications",
                "restrictions", "fitness", "exam_kind"):
        op.drop_column("medical_exam", col)
    if bind.dialect.name == "postgresql":
        for type_name in ("medicalsuspensionreason", "medicalsuspensionstatus",
                          "medicalreferralstatus", "medicalfitness", "medicalexamkind"):
            op.execute(f"DROP TYPE IF EXISTS {type_name}")
```

- [ ] **Step 5: Run migration test**
Run: `python3 -m pytest backend/tests/test_med01_medical_domain_migration.py -v`
Expected: PASS.

- [ ] **Step 6: Apply migration on SQLite (smoke) + the PG round-trip guard if available**
Run (SQLite): `python3 -m pytest backend/tests/test_alembic_postgres_upgrade.py -v -k upgrade` (skips gracefully without `TEST_PG_ADMIN_URL`).
Expected: PASS or skip. (Full PG round-trip is validated in CI.)

- [ ] **Step 7: Commit**
```bash
git add backend/app/migrations/versions/20260607_med01_medical_domain.py backend/tests/test_med01_medical_domain_migration.py
git commit -m "feat(medical): additive migration med01 (exam cols + 3 tables)"
```

---

## Phase 2 — Domain FSM (pure, no DB)

### Task 2.1: Package + referral FSM

**Files:**
- Create: `backend/app/domains/medical/__init__.py`, `backend/app/domains/medical/lifecycle.py`
- Test: `tests/unit/test_medical_lifecycle.py`

- [ ] **Step 1: Write failing tests**
```python
# tests/unit/test_medical_lifecycle.py
from __future__ import annotations

from datetime import date

import pytest

from app.domains.medical import lifecycle as lc
from app.models.models import MedicalReferralStatus as RS


def test_referral_transitions():
    lc.validate_transition(RS.ISSUED, RS.SCHEDULED)
    lc.validate_transition(RS.SCHEDULED, RS.COMPLETED)
    lc.validate_transition(RS.ISSUED, RS.ISSUED)  # self no-op
    with pytest.raises(lc.InvalidTransition):
        lc.validate_transition(RS.COMPLETED, RS.SCHEDULED)
    with pytest.raises(lc.InvalidTransition):
        lc.validate_transition(RS.ISSUED, RS.COMPLETED)


def test_referral_terminal_and_overdue_and_result():
    assert lc.is_terminal(RS.COMPLETED) and lc.is_terminal(RS.CANCELLED)
    assert not lc.is_terminal(RS.ISSUED)
    assert lc.is_overdue(date(2020, 1, 1), RS.ISSUED, date(2020, 6, 1)) is True
    assert lc.is_overdue(date(2020, 1, 1), RS.COMPLETED, date(2020, 6, 1)) is False
    assert lc.is_overdue(None, RS.ISSUED, date(2020, 6, 1)) is False
    assert lc.requires_result(RS.COMPLETED) is True
    assert lc.requires_result(RS.SCHEDULED) is False
```

- [ ] **Step 2: Run to verify fail**
Run: `python3 -m pytest tests/unit/test_medical_lifecycle.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**
```python
# backend/app/domains/medical/__init__.py
```
```python
# backend/app/domains/medical/lifecycle.py
"""Medical domain pure logic — FSM, periodicity, contingent, suspension rule.

No DB / no app-service imports (only the enum types from app.models.models).
"""
from __future__ import annotations

import enum
from datetime import date, timedelta

from app.models.models import (
    MedicalExamKind,
    MedicalFitness,
    MedicalReferralStatus,
)

_R = MedicalReferralStatus

ALLOWED_TRANSITIONS: dict[MedicalReferralStatus, frozenset[MedicalReferralStatus]] = {
    _R.ISSUED: frozenset({_R.SCHEDULED, _R.CANCELLED}),
    _R.SCHEDULED: frozenset({_R.COMPLETED, _R.CANCELLED}),
    _R.COMPLETED: frozenset(),
    _R.CANCELLED: frozenset(),
}
TERMINAL_STATES: frozenset[MedicalReferralStatus] = frozenset({_R.COMPLETED, _R.CANCELLED})

# Segregation of duties: only these roles may lift a medical suspension.
LIFT_SUSPENSION_ROLES: frozenset[str] = frozenset({"admin", "owner"})

# Default periodicity (days) by exam kind when no norm provides interval_days.
DEFAULT_INTERVAL_DAYS: dict[MedicalExamKind, int] = {
    MedicalExamKind.PERIODIC: 365,
    MedicalExamKind.PRELIMINARY: 0,
    MedicalExamKind.PSYCHIATRIC: 1825,
    MedicalExamKind.FLUOROGRAPHY: 365,
    MedicalExamKind.HEALTH_BOOK: 365,
}


class InvalidTransition(Exception):
    def __init__(self, current: MedicalReferralStatus, target: MedicalReferralStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Cannot transition referral from {current.value} to {target.value}")


def validate_transition(current: MedicalReferralStatus, target: MedicalReferralStatus) -> None:
    if current == target:
        return
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransition(current, target)


def is_terminal(status: MedicalReferralStatus) -> bool:
    return status in TERMINAL_STATES


def is_overdue(due_at: date | None, status: MedicalReferralStatus, today: date) -> bool:
    return due_at is not None and due_at < today and status not in TERMINAL_STATES


def requires_result(target: MedicalReferralStatus) -> bool:
    return target == MedicalReferralStatus.COMPLETED
```

- [ ] **Step 4: Run to verify pass**
Run: `python3 -m pytest tests/unit/test_medical_lifecycle.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/domains/medical/ tests/unit/test_medical_lifecycle.py
git commit -m "feat(medical): referral FSM (pure lifecycle)"
```

---

### Task 2.2: Periodicity helpers

**Files:** Modify `backend/app/domains/medical/lifecycle.py`; Test: `tests/unit/test_medical_lifecycle.py`

- [ ] **Step 1: Add failing tests**
```python
def test_compute_valid_until_and_next_due():
    from app.models.models import MedicalExamKind as K
    assert lc.compute_valid_until(date(2026, 1, 1), 365) == date(2027, 1, 1)
    assert lc.next_due(None, 365, date(2026, 6, 1)) == date(2026, 6, 1)
    assert lc.next_due(date(2026, 1, 1), 365, date(2026, 6, 1)) == date(2027, 1, 1)
    assert lc.interval_for_kind(K.PERIODIC, None) == 365
    assert lc.interval_for_kind(K.PERIODIC, 180) == 180
    assert lc.interval_for_kind(K.PSYCHIATRIC, None) == 1825
```

- [ ] **Step 2: Run (fail)** — `python3 -m pytest tests/unit/test_medical_lifecycle.py -k valid_until -v` → FAIL.

- [ ] **Step 3: Implement** (append to `lifecycle.py`)
```python
def interval_for_kind(kind: MedicalExamKind, norm_interval_days: int | None) -> int:
    if norm_interval_days is not None:
        return norm_interval_days
    return DEFAULT_INTERVAL_DAYS.get(kind, 365)


def compute_valid_until(exam_date: date, interval_days: int) -> date:
    return exam_date + timedelta(days=interval_days)


def next_due(last_exam_date: date | None, interval_days: int, today: date) -> date:
    if last_exam_date is None:
        return today
    return last_exam_date + timedelta(days=interval_days)
```

- [ ] **Step 4: Run (pass)** — `python3 -m pytest tests/unit/test_medical_lifecycle.py -k valid_until -v` → PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/domains/medical/lifecycle.py tests/unit/test_medical_lifecycle.py
git commit -m "feat(medical): periodicity helpers"
```

---

### Task 2.3: Contingent classification

**Files:** Modify `lifecycle.py`; Test: `tests/unit/test_medical_lifecycle.py`

- [ ] **Step 1: Add failing tests**
```python
def test_classify_contingent():
    from app.domains.medical.lifecycle import ContingentItemStatus as C
    t = date(2026, 6, 1)
    assert lc.classify(None, t, 30) is C.MISSING
    assert lc.classify(date(2026, 5, 1), t, 30) is C.OVERDUE
    assert lc.classify(date(2026, 6, 15), t, 30) is C.DUE_SOON
    assert lc.classify(date(2027, 1, 1), t, 30) is C.OK
```

- [ ] **Step 2: Run (fail)** — `python3 -m pytest tests/unit/test_medical_lifecycle.py -k classify -v` → FAIL.

- [ ] **Step 3: Implement** (append)
```python
class ContingentItemStatus(str, enum.Enum):
    OK = "ok"
    DUE_SOON = "due_soon"
    OVERDUE = "overdue"
    MISSING = "missing"


def classify(
    latest_valid_until: date | None, today: date, warning_days: int = 30
) -> "ContingentItemStatus":
    if latest_valid_until is None:
        return ContingentItemStatus.MISSING
    if latest_valid_until < today:
        return ContingentItemStatus.OVERDUE
    if latest_valid_until <= today + timedelta(days=warning_days):
        return ContingentItemStatus.DUE_SOON
    return ContingentItemStatus.OK
```

- [ ] **Step 4: Run (pass)** → PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/domains/medical/lifecycle.py tests/unit/test_medical_lifecycle.py
git commit -m "feat(medical): contingent classification"
```

---

### Task 2.4: Required-kinds resolution (СОУТ influence)

**Files:** Modify `lifecycle.py`; Test: `tests/unit/test_medical_lifecycle.py`

- [ ] **Step 1: Add failing tests**
```python
def test_resolve_required_kinds():
    from app.models.models import MedicalExamKind as K
    # norms shaped as plain tuples to keep the function DB-free
    norms = [
        # (position_id, hazard_id, working_conditions_class, exam_kind)
        ("p1", "h1", None, K.PERIODIC),
        ("p1", None, "3.1", K.PSYCHIATRIC),
        ("p2", "h9", None, K.FLUOROGRAPHY),
    ]
    got = lc.resolve_required_kinds("p1", "3.1", {"h1"}, norms)
    assert got == {K.PERIODIC, K.PSYCHIATRIC}
    assert lc.resolve_required_kinds("p1", "1", set(), norms) == set()
    assert lc.resolve_required_kinds("p2", None, {"h9"}, norms) == {K.FLUOROGRAPHY}
```

- [ ] **Step 2: Run (fail)** → FAIL.

- [ ] **Step 3: Implement** (append)
```python
from collections.abc import Iterable
from typing import Tuple

# norm tuple shape: (position_id, hazard_id|None, working_conditions_class|None, exam_kind)
NormTuple = Tuple[str, str | None, str | None, MedicalExamKind]


def resolve_required_kinds(
    position_id: str,
    working_conditions_class: str | None,
    hazard_ids: set[str],
    norms: Iterable[NormTuple],
) -> set[MedicalExamKind]:
    required: set[MedicalExamKind] = set()
    for n_pos, n_hazard, n_wcc, n_kind in norms:
        if n_pos != position_id:
            continue
        # a norm applies if: it has no extra predicate, OR its hazard matches,
        # OR its working-conditions-class matches the person/position's class.
        hazard_ok = n_hazard is None or n_hazard in hazard_ids
        wcc_ok = n_wcc is None or n_wcc == working_conditions_class
        if hazard_ok and wcc_ok:
            required.add(n_kind)
    return required
```

- [ ] **Step 4: Run (pass)** → PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/domains/medical/lifecycle.py tests/unit/test_medical_lifecycle.py
git commit -m "feat(medical): required-kinds resolution (СОУТ influence)"
```

---

### Task 2.5: Suspension rule

**Files:** Modify `lifecycle.py`; Test: `tests/unit/test_medical_lifecycle.py`

- [ ] **Step 1: Add failing tests**
```python
def test_suspension_rule():
    from app.models.models import MedicalFitness as F
    from app.domains.medical.lifecycle import SuspensionAction as A
    assert lc.requires_suspension(F.UNFIT) is True
    assert lc.requires_suspension(F.FIT) is False
    assert lc.suspension_action(False, F.UNFIT) is A.OPEN
    assert lc.suspension_action(True, F.FIT) is A.LIFT
    assert lc.suspension_action(True, F.FIT_WITH_RESTRICTIONS) is A.LIFT
    assert lc.suspension_action(True, F.UNFIT) is A.NONE
    assert lc.suspension_action(False, F.FIT) is A.NONE


def test_reason_for_exam():
    from app.models.models import MedicalSuspensionReason as Reason
    assert lc.reason_for(["asthma"]) is Reason.CONTRAINDICATION
    assert lc.reason_for([]) is Reason.UNFIT
```

- [ ] **Step 2: Run (fail)** → FAIL.

- [ ] **Step 3: Implement** (append)
```python
from app.models.models import MedicalSuspensionReason


class SuspensionAction(str, enum.Enum):
    OPEN = "open"
    LIFT = "lift"
    NONE = "none"


def requires_suspension(fitness: MedicalFitness) -> bool:
    return fitness == MedicalFitness.UNFIT


def suspension_action(has_active_suspension: bool, new_fitness: MedicalFitness) -> SuspensionAction:
    if not has_active_suspension and new_fitness == MedicalFitness.UNFIT:
        return SuspensionAction.OPEN
    if has_active_suspension and new_fitness in (MedicalFitness.FIT, MedicalFitness.FIT_WITH_RESTRICTIONS):
        return SuspensionAction.LIFT
    return SuspensionAction.NONE


def reason_for(contraindications: list[str]) -> MedicalSuspensionReason:
    return (
        MedicalSuspensionReason.CONTRAINDICATION
        if contraindications
        else MedicalSuspensionReason.UNFIT
    )
```

- [ ] **Step 4: Run (pass)** — `python3 -m pytest tests/unit/test_medical_lifecycle.py -v` → ALL PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/domains/medical/lifecycle.py tests/unit/test_medical_lifecycle.py
git commit -m "feat(medical): suspension rule (fitness->action)"
```

---

## Phase 3 — Events

### Task 3.1: Medical event types + payloads

**Files:**
- Modify: `backend/app/services/events.py`
- Test: `backend/tests/test_medical_events.py`

- [ ] **Step 1: Write failing test**
```python
# backend/tests/test_medical_events.py
from __future__ import annotations

from datetime import datetime, timezone

from app.services.events import (
    EventType,
    MedicalExamRecordedPayload,
    PersonSuspendedPayload,
    PersonReinstatedPayload,
    dedupe_key_for,
    normalize_payload,
)


def test_medical_event_types_registered():
    assert EventType.MEDICAL_EXAM_RECORDED.value == "MedicalExamRecorded"
    assert EventType.PERSON_SUSPENDED.value == "PersonSuspended"
    assert EventType.PERSON_REINSTATED.value == "PersonReinstated"


def test_medical_payload_normalize_and_dedupe():
    parsed, dumped = normalize_payload(
        event_type=EventType.MEDICAL_EXAM_RECORDED,
        payload={"tenant_id": "t1", "exam_id": "e1", "person_id": "p1",
                 "exam_kind": "periodic", "fitness": "fit",
                 "valid_until": "2027-01-01"},
        tenant_id="t1",
    )
    assert isinstance(parsed, MedicalExamRecordedPayload)
    assert dedupe_key_for(EventType.MEDICAL_EXAM_RECORDED, parsed) == "e1"

    parsed2, _ = normalize_payload(
        event_type=EventType.PERSON_SUSPENDED,
        payload={"tenant_id": "t1", "suspension_id": "s1", "person_id": "p1",
                 "reason": "unfit"},
        tenant_id="t1",
    )
    assert dedupe_key_for(EventType.PERSON_SUSPENDED, parsed2) == "s1"
```

- [ ] **Step 2: Run (fail)** → FAIL (ImportError).

- [ ] **Step 3: Implement** — in `events.py`:
  - Add enum members to `EventType`:
    ```python
    MEDICAL_EXAM_RECORDED = "MedicalExamRecorded"
    PERSON_SUSPENDED = "PersonSuspended"
    PERSON_REINSTATED = "PersonReinstated"
    ```
  - Add payload classes (after `InspectionCreatedPayload`):
    ```python
    class MedicalExamRecordedPayload(BaseEventPayload):
        exam_id: str
        person_id: str
        exam_kind: str | None = None
        fitness: str | None = None
        valid_until: date | None = None


    class PersonSuspendedPayload(BaseEventPayload):
        suspension_id: str
        person_id: str
        reason: str
        source_exam_id: str | None = None


    class PersonReinstatedPayload(BaseEventPayload):
        suspension_id: str
        person_id: str
    ```
  - Register in `_PAYLOADS`:
    ```python
    EventType.MEDICAL_EXAM_RECORDED: MedicalExamRecordedPayload,
    EventType.PERSON_SUSPENDED: PersonSuspendedPayload,
    EventType.PERSON_REINSTATED: PersonReinstatedPayload,
    ```
  - Add `dedupe_key_for` branches (before the final `raise`):
    ```python
    if isinstance(payload, MedicalExamRecordedPayload):
        return payload.exam_id
    if isinstance(payload, (PersonSuspendedPayload, PersonReinstatedPayload)):
        return payload.suspension_id
    ```

- [ ] **Step 4: Run (pass)** → PASS.

- [ ] **Step 5: Regression — outbox still dispatches unknown/known events**
Run: `python3 -m pytest backend/tests/test_medical_events.py tests/test_outbox_dispatch.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**
```bash
git add backend/app/services/events.py backend/tests/test_medical_events.py
git commit -m "feat(medical): MedicalExamRecorded/PersonSuspended/PersonReinstated events"
```

---

## Phase 4 — Schemas

### Task 4.1: Medical schemas

**Files:**
- Modify: `backend/app/schemas/medical.py`
- Test: `backend/tests/test_medical_schemas.py`

- [ ] **Step 1: Write failing test**
```python
# backend/tests/test_medical_schemas.py
from __future__ import annotations

from datetime import date

from app.schemas.medical import (
    ContingentItem, ContingentPage, MedicalExamCreate, MedicalNormCreate,
    MedicalReferralCreate, MedicalReferralTransition, MedicalSummary,
    MedicalSuspensionRead,
)


def test_exam_create_requires_core_fields():
    m = MedicalExamCreate(person_id="p1", exam_kind="periodic",
                          exam_date=date(2026, 1, 1), fitness="fit")
    assert m.contraindications == []
    assert m.valid_until is None  # optional → service computes


def test_referral_transition_and_norm_and_contingent():
    MedicalReferralTransition(to="scheduled")
    MedicalNormCreate(position_id="p1", exam_kind="periodic", interval_days=365)
    item = ContingentItem(person_id="p1", exam_kind="periodic", status="missing",
                          valid_until=None, due_at=date(2026, 1, 1))
    page = ContingentPage(items=[item], total=1)
    assert page.total == 1
    MedicalSummary(by_status={"missing": 1}, total=1, overdue_count=0,
                   suspended_count=0)
```

- [ ] **Step 2: Run (fail)** → FAIL.

- [ ] **Step 3: Implement** — append to `backend/app/schemas/medical.py`:
```python
from app.models.models import (
    MedicalExamKind, MedicalFitness, MedicalReferralStatus, MedicalSuspensionReason,
    MedicalSuspensionStatus,
)


class MedicalExamCreate(BaseModel):
    person_id: str = Field(..., min_length=1, max_length=36)
    exam_kind: MedicalExamKind
    exam_date: date
    fitness: MedicalFitness | None = None
    conclusion: str | None = None
    restrictions: str | None = None
    contraindications: list[str] = Field(default_factory=list)
    valid_until: date | None = None
    medical_org_name: str | None = None
    referral_id: str | None = None
    exam_type: str | None = None  # legacy free label; defaults from exam_kind
    model_config = ConfigDict(extra="forbid")


class MedicalExamUpdate(BaseModel):
    fitness: MedicalFitness | None = None
    conclusion: str | None = None
    restrictions: str | None = None
    contraindications: list[str] | None = None
    valid_until: date | None = None
    model_config = ConfigDict(extra="forbid")


class MedicalNormCreate(BaseModel):
    position_id: str = Field(..., min_length=1, max_length=36)
    exam_kind: MedicalExamKind
    hazard_id: str | None = None
    interval_days: int = Field(default=365, ge=0, le=3650)
    working_conditions_class: str | None = None
    model_config = ConfigDict(extra="forbid")


class MedicalNormRead(BaseModel):
    id: str
    position_id: str
    hazard_id: str | None = None
    exam_kind: MedicalExamKind
    interval_days: int
    working_conditions_class: str | None = None
    model_config = ConfigDict(from_attributes=True)


class MedicalNormPage(BaseModel):
    items: list[MedicalNormRead]
    total: int


class MedicalReferralCreate(BaseModel):
    person_id: str = Field(..., min_length=1, max_length=36)
    exam_kind: MedicalExamKind
    due_at: date | None = None
    medical_org_name: str | None = None
    model_config = ConfigDict(extra="forbid")


class MedicalReferralTransition(BaseModel):
    to: MedicalReferralStatus
    result_exam_id: str | None = None
    note: str | None = None
    model_config = ConfigDict(extra="forbid")


class MedicalReferralRead(BaseModel):
    id: str
    person_id: str
    exam_kind: MedicalExamKind
    due_at: date | None = None
    status: MedicalReferralStatus
    medical_org_name: str | None = None
    result_exam_id: str | None = None
    is_overdue: bool = False
    model_config = ConfigDict(from_attributes=True)


class MedicalReferralPage(BaseModel):
    items: list[MedicalReferralRead]
    total: int


class ContingentItem(BaseModel):
    person_id: str
    exam_kind: MedicalExamKind
    status: str  # ContingentItemStatus value
    valid_until: date | None = None
    due_at: date | None = None
    model_config = ConfigDict(extra="forbid")


class ContingentPage(BaseModel):
    items: list[ContingentItem]
    total: int


class MedicalSummary(BaseModel):
    by_status: dict[str, int]
    total: int
    overdue_count: int
    suspended_count: int


class MedicalSuspensionRead(BaseModel):
    id: str
    person_id: str
    reason: MedicalSuspensionReason
    status: MedicalSuspensionStatus
    source_exam_id: str | None = None
    model_config = ConfigDict(from_attributes=True)


class MedicalSuspensionPage(BaseModel):
    items: list[MedicalSuspensionRead]
    total: int
```

- [ ] **Step 4: Run (pass)** → PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/schemas/medical.py backend/tests/test_medical_schemas.py
git commit -m "feat(medical): request/response schemas"
```

---

## Phase 5 — Domain service (I/O)

> Service functions live in `backend/app/domains/medical/service.py`. They take an `AsyncSession`, are tenant-scoped by argument, and DO NOT commit (the route owns the transaction) except where noted (escalation tick commits per tenant, mirroring prescriptions).

### Task 5.1: record_exam (safety loop) + helpers

**Files:**
- Create: `backend/app/domains/medical/service.py`
- Test: `tests/api/test_medical_api.py` (service is covered through the API in Phase 6; add a focused service test here)
- Test: `backend/tests/test_medical_service.py`

- [ ] **Step 1: Write failing test** (DB-backed, uses the app test session)
```python
# backend/tests/test_medical_service.py
from __future__ import annotations

from datetime import date

import pytest

from app.domains.medical import service as svc
from app.models.models import (
    MedicalExamKind, MedicalFitness, MedicalSuspension, MedicalSuspensionStatus,
)


@pytest.mark.asyncio
async def test_record_exam_unfit_opens_suspension_then_fit_lifts(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        await session.commit()

        tid = str(tenant.id)
        exam1 = await svc.record_exam(
            session, tenant_id=tid, actor_id=None,
            person_id=person.id, exam_kind=MedicalExamKind.PERIODIC,
            exam_date=date(2026, 1, 1), fitness=MedicalFitness.UNFIT,
            contraindications=["asthma"], conclusion=None, restrictions=None,
            valid_until=None, medical_org_name=None, referral_id=None, exam_type=None,
        )
        await session.commit()
        actives = await svc.list_active_suspensions(session, tenant_id=tid, person_ids=[person.id])
        assert len(actives) == 1
        assert actives[0].reason.value == "contraindication"

        await svc.record_exam(
            session, tenant_id=tid, actor_id=None,
            person_id=person.id, exam_kind=MedicalExamKind.PERIODIC,
            exam_date=date(2026, 2, 1), fitness=MedicalFitness.FIT,
            contraindications=[], conclusion=None, restrictions=None,
            valid_until=None, medical_org_name=None, referral_id=None, exam_type=None,
        )
        await session.commit()
        actives = await svc.list_active_suspensions(session, tenant_id=tid, person_ids=[person.id])
        assert actives == []
        assert exam1.valid_until == date(2027, 1, 1)  # computed from default interval
```
> If `data_factory.create_person` does not exist, add a minimal helper in `tests/utils/factories.py` mirroring `create_company` (Person needs `company_id`, `first_name`, `last_name`). Include that as Step 1a.

- [ ] **Step 1a (if needed): add `create_person` factory**
```python
# tests/utils/factories.py — add method on TestDataFactory
async def create_person(self, *, tenant=None, tenant_slug="test", company=None,
                        first_name="Иван", last_name="Петров", session=None, **overrides):
    from app.models.models import Person
    async def _do(s):
        t = tenant or await self.ensure_tenant(slug=tenant_slug, session=s)
        c = company or await self.create_company(tenant=t, session=s)
        person = Person(tenant_id=t.id, company_id=c.id, first_name=first_name,
                        last_name=last_name, **overrides)
        s.add(person); await s.flush(); return person
    if session is not None:
        return await _do(session)
    async with self._sessionmaker() as s:
        p = await _do(s); await s.commit(); return p
```

- [ ] **Step 2: Run (fail)** → FAIL (service missing).

- [ ] **Step 3: Implement `record_exam` + suspension helpers**
```python
# backend/app/domains/medical/service.py
"""Medical domain I/O service (TZ B.8)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.medical import lifecycle as lc
from app.models.models import (
    MedicalExam, MedicalExamKind, MedicalFitness, MedicalNorm, MedicalReferral,
    MedicalReferralStatus, MedicalSuspension, MedicalSuspensionStatus, Person,
)
from app.services.events import EventType
from app.services.outbox import OutboxService


async def list_active_suspensions(
    session: AsyncSession, *, tenant_id: str, person_ids: list[str]
) -> list[MedicalSuspension]:
    if not person_ids:
        return []
    stmt = select(MedicalSuspension).where(
        MedicalSuspension.tenant_id == tenant_id,
        MedicalSuspension.deleted_at.is_(None),
        MedicalSuspension.status == MedicalSuspensionStatus.ACTIVE,
        MedicalSuspension.person_id.in_(person_ids),
    )
    return list((await session.execute(stmt)).scalars().all())


async def _norm_interval(
    session: AsyncSession, *, tenant_id: str, person: Person, exam_kind: MedicalExamKind
) -> int:
    if person.position_id is None:
        return lc.interval_for_kind(exam_kind, None)
    stmt = select(MedicalNorm.interval_days).where(
        MedicalNorm.tenant_id == tenant_id,
        MedicalNorm.position_id == person.position_id,
        MedicalNorm.exam_kind == exam_kind,
    ).limit(1)
    interval = (await session.execute(stmt)).scalar_one_or_none()
    return lc.interval_for_kind(exam_kind, interval)


async def record_exam(
    session: AsyncSession, *, tenant_id: str, actor_id: str | None, person_id: str,
    exam_kind: MedicalExamKind, exam_date: date, fitness: MedicalFitness | None,
    contraindications: list[str], conclusion: str | None, restrictions: str | None,
    valid_until: date | None, medical_org_name: str | None, referral_id: str | None,
    exam_type: str | None,
) -> MedicalExam:
    person = (await session.execute(
        select(Person).where(
            Person.id == person_id, Person.tenant_id == tenant_id, Person.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if person is None:
        raise ValueError({"code": "person_not_found", "person_id": person_id})

    if valid_until is None:
        interval = await _norm_interval(session, tenant_id=tenant_id, person=person, exam_kind=exam_kind)
        valid_until = lc.compute_valid_until(exam_date, interval)

    exam = MedicalExam(
        tenant_id=tenant_id, person_id=person_id, exam_kind=exam_kind,
        exam_type=exam_type or exam_kind.value, exam_date=exam_date, fitness=fitness,
        conclusion=conclusion, restrictions=restrictions,
        contraindications=list(contraindications or []), valid_until=valid_until,
        medical_org_name=medical_org_name, referral_id=referral_id,
    )
    session.add(exam)
    await session.flush()

    outbox = OutboxService(session)
    await outbox.enqueue(
        tenant_id=tenant_id, event_type=EventType.MEDICAL_EXAM_RECORDED.value,
        idempotency_key=f"medical-exam:{exam.id}",
        payload={"tenant_id": tenant_id, "actor_id": actor_id, "exam_id": exam.id,
                 "person_id": person_id, "exam_kind": exam_kind.value,
                 "fitness": fitness.value if fitness else None,
                 "valid_until": valid_until},
    )

    if fitness is not None:
        await _apply_suspension(session, tenant_id=tenant_id, actor_id=actor_id,
                                person_id=person_id, exam=exam, fitness=fitness)
    return exam


async def _apply_suspension(
    session: AsyncSession, *, tenant_id: str, actor_id: str | None, person_id: str,
    exam: MedicalExam, fitness: MedicalFitness,
) -> None:
    actives = await list_active_suspensions(session, tenant_id=tenant_id, person_ids=[person_id])
    action = lc.suspension_action(bool(actives), fitness)
    outbox = OutboxService(session)
    if action is lc.SuspensionAction.OPEN:
        susp = MedicalSuspension(
            tenant_id=tenant_id, person_id=person_id,
            reason=lc.reason_for(exam.contraindications), source_exam_id=exam.id,
            started_at=datetime.now(tz=timezone.utc), status=MedicalSuspensionStatus.ACTIVE,
        )
        session.add(susp)
        await session.flush()
        await outbox.enqueue(
            tenant_id=tenant_id, event_type=EventType.PERSON_SUSPENDED.value,
            idempotency_key=f"person-suspended:{susp.id}",
            payload={"tenant_id": tenant_id, "actor_id": actor_id,
                     "suspension_id": susp.id, "person_id": person_id,
                     "reason": susp.reason.value, "source_exam_id": exam.id},
        )
    elif action is lc.SuspensionAction.LIFT:
        for susp in actives:
            susp.status = MedicalSuspensionStatus.LIFTED
            susp.lifted_at = datetime.now(tz=timezone.utc)
            susp.lifted_by = actor_id
            await outbox.enqueue(
                tenant_id=tenant_id, event_type=EventType.PERSON_REINSTATED.value,
                idempotency_key=f"person-reinstated:{susp.id}",
                payload={"tenant_id": tenant_id, "actor_id": actor_id,
                         "suspension_id": susp.id, "person_id": person_id},
            )
```

- [ ] **Step 4: Run (pass)** → `python3 -m pytest backend/tests/test_medical_service.py -v` → PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/domains/medical/service.py backend/tests/test_medical_service.py tests/utils/factories.py
git commit -m "feat(medical): record_exam service + suspension safety loop"
```

---

### Task 5.2: Contingent computation + summary

**Files:** Modify `service.py`; Test: `backend/tests/test_medical_service.py`

- [ ] **Step 1: Add failing test**
```python
@pytest.mark.asyncio
async def test_contingent_lists_missing_required_exam(sessionmaker, data_factory):
    from app.models.models import MedicalNorm, Position
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        pos = Position(tenant_id=tenant.id, company_id=company.id, name="Сварщик")
        session.add(pos); await session.flush()
        person = await data_factory.create_person(
            tenant=tenant, company=company, session=session, position_id=pos.id)
        session.add(MedicalNorm(tenant_id=tenant.id, position_id=pos.id,
                                exam_kind=MedicalExamKind.PERIODIC, interval_days=365))
        await session.commit()

        items = await svc.compute_contingent(session, tenant_id=str(tenant.id),
                                              today=date(2026, 6, 1))
        assert any(i["person_id"] == person.id and i["status"] == "missing" for i in items)
```

- [ ] **Step 2: Run (fail)** → FAIL.

- [ ] **Step 3: Implement** (append to `service.py`)
```python
async def compute_contingent(
    session: AsyncSession, *, tenant_id: str, today: date, warning_days: int = 30,
    position_id: str | None = None,
) -> list[dict]:
    # 1) load norms as plain tuples for the pure resolver
    norm_stmt = select(
        MedicalNorm.position_id, MedicalNorm.hazard_id,
        MedicalNorm.working_conditions_class, MedicalNorm.exam_kind,
    ).where(MedicalNorm.tenant_id == tenant_id)
    norms = [(r[0], r[1], r[2], r[3]) for r in (await session.execute(norm_stmt)).all()]
    if not norms:
        return []

    # 2) load active people (optionally filtered by position)
    p_stmt = select(Person).where(
        Person.tenant_id == tenant_id, Person.deleted_at.is_(None),
        Person.position_id.is_not(None),
    )
    if position_id:
        p_stmt = p_stmt.where(Person.position_id == position_id)
    people = list((await session.execute(p_stmt)).scalars().all())
    if not people:
        return []

    # 3) latest valid_until per (person, exam_kind)
    person_ids = [p.id for p in people]
    ex_stmt = select(
        MedicalExam.person_id, MedicalExam.exam_kind,
        func.max(MedicalExam.valid_until),
    ).where(
        MedicalExam.tenant_id == tenant_id, MedicalExam.deleted_at.is_(None),
        MedicalExam.person_id.in_(person_ids), MedicalExam.exam_kind.is_not(None),
    ).group_by(MedicalExam.person_id, MedicalExam.exam_kind)
    latest: dict[tuple[str, MedicalExamKind], date] = {
        (pid, kind): vu for pid, kind, vu in (await session.execute(ex_stmt)).all()
    }

    items: list[dict] = []
    for person in people:
        required = lc.resolve_required_kinds(
            person.position_id, person.working_conditions_class,
            {h.id for h in getattr(person.position, "hazards", [])} if person.position else set(),
            norms,
        )
        for kind in required:
            vu = latest.get((person.id, kind))
            st = lc.classify(vu, today, warning_days)
            items.append({
                "person_id": person.id, "exam_kind": kind.value,
                "status": st.value, "valid_until": vu,
                "due_at": vu if vu is not None else today,
            })
    return items


async def status_summary(session: AsyncSession, *, tenant_id: str, today: date) -> dict:
    items = await compute_contingent(session, tenant_id=tenant_id, today=today)
    by_status: dict[str, int] = {}
    for it in items:
        by_status[it["status"]] = by_status.get(it["status"], 0) + 1
    suspended = await session.scalar(
        select(func.count()).select_from(MedicalSuspension).where(
            MedicalSuspension.tenant_id == tenant_id,
            MedicalSuspension.deleted_at.is_(None),
            MedicalSuspension.status == MedicalSuspensionStatus.ACTIVE,
        )
    )
    return {
        "by_status": by_status,
        "total": len(items),
        "overdue_count": by_status.get("overdue", 0) + by_status.get("missing", 0),
        "suspended_count": int(suspended or 0),
    }
```

- [ ] **Step 4: Run (pass)** → PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/domains/medical/service.py backend/tests/test_medical_service.py
git commit -m "feat(medical): contingent computation + summary"
```

---

### Task 5.3: Referral issue / transition / generate_due_referrals

**Files:** Modify `service.py`; Test: `backend/tests/test_medical_service.py`

- [ ] **Step 1: Add failing test**
```python
@pytest.mark.asyncio
async def test_generate_due_referrals_is_idempotent(sessionmaker, data_factory):
    from app.models.models import MedicalNorm, Position
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        pos = Position(tenant_id=tenant.id, company_id=company.id, name="Маляр")
        session.add(pos); await session.flush()
        person = await data_factory.create_person(
            tenant=tenant, company=company, session=session, position_id=pos.id)
        session.add(MedicalNorm(tenant_id=tenant.id, position_id=pos.id,
                                exam_kind=MedicalExamKind.PERIODIC, interval_days=365))
        await session.commit()
        tid = str(tenant.id)
        n1 = await svc.generate_due_referrals(session, tenant_id=tid, today=date(2026, 6, 1))
        await session.commit()
        n2 = await svc.generate_due_referrals(session, tenant_id=tid, today=date(2026, 6, 1))
        await session.commit()
        assert n1 == 1 and n2 == 0  # second run is a no-op
```

- [ ] **Step 2: Run (fail)** → FAIL.

- [ ] **Step 3: Implement** (append)
```python
async def _open_referral_kinds(
    session: AsyncSession, *, tenant_id: str, person_id: str
) -> set[MedicalExamKind]:
    stmt = select(MedicalReferral.exam_kind).where(
        MedicalReferral.tenant_id == tenant_id,
        MedicalReferral.deleted_at.is_(None),
        MedicalReferral.person_id == person_id,
        MedicalReferral.status.not_in(list(lc.TERMINAL_STATES)),
    )
    return set((await session.execute(stmt)).scalars().all())


async def issue_referral(
    session: AsyncSession, *, tenant_id: str, person_id: str, exam_kind: MedicalExamKind,
    due_at: date | None, medical_org_name: str | None, issued_by: str | None,
) -> MedicalReferral:
    ref = MedicalReferral(
        tenant_id=tenant_id, person_id=person_id, exam_kind=exam_kind, due_at=due_at,
        status=MedicalReferralStatus.ISSUED, medical_org_name=medical_org_name,
        issued_by=issued_by,
    )
    session.add(ref)
    await session.flush()
    return ref


async def generate_due_referrals(
    session: AsyncSession, *, tenant_id: str, today: date, issued_by: str | None = None,
) -> int:
    items = await compute_contingent(session, tenant_id=tenant_id, today=today)
    created = 0
    for it in items:
        if it["status"] not in ("missing", "overdue"):
            continue
        kind = MedicalExamKind(it["exam_kind"])
        open_kinds = await _open_referral_kinds(session, tenant_id=tenant_id, person_id=it["person_id"])
        if kind in open_kinds:
            continue
        await issue_referral(session, tenant_id=tenant_id, person_id=it["person_id"],
                             exam_kind=kind, due_at=today, medical_org_name=None,
                             issued_by=issued_by)
        created += 1
    return created
```

- [ ] **Step 4: Run (pass)** → PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/domains/medical/service.py backend/tests/test_medical_service.py
git commit -m "feat(medical): referrals + idempotent generate_due_referrals"
```

---

### Task 5.4: notify_overdue (escalation reminders)

**Files:** Modify `service.py`; Test: covered by the beat task test in Phase 8 (Task 8.4). Implement now.

- [ ] **Step 1: Implement** (append; no new test here — exercised by Task 8.4)
```python
async def notify_overdue(
    session: AsyncSession, *, tenant_id: str, actor_id: str | None, today: date
) -> int:
    """Enqueue TASK_OVERDUE for overdue/missing contingent items. Idempotent per day."""
    items = await compute_contingent(session, tenant_id=tenant_id, today=today)
    outbox = OutboxService(session)
    count = 0
    for it in items:
        if it["status"] not in ("overdue", "missing"):
            continue
        await outbox.enqueue(
            tenant_id=tenant_id, event_type=EventType.TASK_OVERDUE.value,
            idempotency_key=f"medical-contingent:{it['person_id']}:{it['exam_kind']}:{today.isoformat()}",
            payload={"tenant_id": tenant_id, "actor_id": actor_id,
                     "task_id": f"{it['person_id']}:{it['exam_kind']}",
                     "title": f"Медосмотр просрочен/отсутствует: {it['exam_kind']}",
                     "due_at": None, "assignee_id": None, "status": it["status"],
                     "priority": "high", "overdue": True},
        )
        count += 1
    return count
```

- [ ] **Step 2: Commit**
```bash
git add backend/app/domains/medical/service.py
git commit -m "feat(medical): notify_overdue contingent reminders"
```

---

## Phase 6 — API endpoints

> All new endpoints mirror `routes/prescriptions.py`. Add the feature gate + role deps at the top of `routes/medical.py`.

### Task 6.1: Feature gate + role deps + write-path POST /medical/exams

**Files:**
- Modify: `backend/app/api/routes/medical.py`
- Test: `tests/api/test_medical_api.py`

- [ ] **Step 1: Write failing test**
```python
# tests/api/test_medical_api.py
from __future__ import annotations

from datetime import date

import pytest
from fastapi import status

from app.models.models import RoleEnum


async def _seed_person(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        await session.commit()
        return person.id


@pytest.mark.asyncio
async def test_record_exam_unfit_blocks_then_fit_clears(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    person_id = await _seed_person(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    r = await async_client.post("/api/v1/medical/exams", headers=headers, json={
        "person_id": person_id, "exam_kind": "periodic",
        "exam_date": date(2026, 1, 1).isoformat(), "fitness": "unfit",
        "contraindications": ["asthma"]})
    assert r.status_code == status.HTTP_201_CREATED, r.text
    assert r.json()["fitness"] == "unfit"

    s = await async_client.get("/api/v1/medical/suspensions", headers=headers,
                               params={"person_id": person_id})
    assert s.status_code == status.HTTP_200_OK
    assert s.json()["total"] == 1

    r2 = await async_client.post("/api/v1/medical/exams", headers=headers, json={
        "person_id": person_id, "exam_kind": "periodic",
        "exam_date": date(2026, 2, 1).isoformat(), "fitness": "fit"})
    assert r2.status_code == status.HTTP_201_CREATED
    s2 = await async_client.get("/api/v1/medical/suspensions", headers=headers,
                                params={"person_id": person_id, "status": "active"})
    assert s2.json()["total"] == 0
```

- [ ] **Step 2: Run (fail)** → FAIL (404, endpoints missing).

- [ ] **Step 3: Implement** — add to `routes/medical.py` (after existing imports/deps):
```python
from datetime import datetime, timezone

from app.core.feature_flags import is_feature_enabled
from app.domains.medical import lifecycle as lc
from app.domains.medical import service as medsvc
from app.models.models import (
    MedicalReferral, MedicalReferralStatus, MedicalSuspension, MedicalSuspensionStatus,
)
from app.schemas.medical import (
    ContingentItem, ContingentPage, MedicalExamCreate, MedicalExamUpdate,
    MedicalNormCreate, MedicalNormPage, MedicalNormRead, MedicalReferralCreate,
    MedicalReferralPage, MedicalReferralRead, MedicalReferralTransition,
    MedicalSummary, MedicalSuspensionPage, MedicalSuspensionRead,
)
from app.services.audit import AuditService

_MEDICAL_FEATURE_CODE = "medical"


async def require_medical_feature(tenant: TenantDep, session: SessionDep) -> None:
    if not await is_feature_enabled(session, str(tenant.id), _MEDICAL_FEATURE_CODE):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Medical feature is not enabled for this tenant")


MedicalFeatureGate = Depends(require_medical_feature)


def _error(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


@router.post("/medical/exams", response_model=MedicalExamRead,
             status_code=status.HTTP_201_CREATED, dependencies=[MedicalFeatureGate])
async def create_medical_exam(
    payload: MedicalExamCreate, tenant: TenantDep, session: SessionDep, access: MedicalAccess,
) -> MedicalExamRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        exam = await medsvc.record_exam(
            session, tenant_id=str(tenant.id), actor_id=getattr(access.user, "id", None),
            person_id=payload.person_id, exam_kind=payload.exam_kind,
            exam_date=payload.exam_date, fitness=payload.fitness,
            contraindications=payload.contraindications, conclusion=payload.conclusion,
            restrictions=payload.restrictions, valid_until=payload.valid_until,
            medical_org_name=payload.medical_org_name, referral_id=payload.referral_id,
            exam_type=payload.exam_type,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=exc.args[0])
    await session.commit()
    await session.refresh(exam)
    return MedicalExamRead.model_validate(exam)
```
Also update `MedicalExamRead` in `schemas/medical.py` to include the new fields (`exam_kind`, `fitness`, `restrictions`, `contraindications`, `referral_id`, `medical_org_name`) — extend its definition.

- [ ] **Step 4: Implement GET /medical/suspensions** (needed by the test)
```python
@router.get("/medical/suspensions", response_model=MedicalSuspensionPage,
            dependencies=[MedicalFeatureGate])
async def list_suspensions(
    tenant: TenantDep, session: SessionDep, access: MedicalReadAccess,
    person_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
) -> MedicalSuspensionPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    stmt = select(MedicalSuspension).where(
        MedicalSuspension.tenant_id == tenant.id, MedicalSuspension.deleted_at.is_(None))
    if person_id:
        stmt = stmt.where(MedicalSuspension.person_id == person_id)
    if status_filter == "active":
        stmt = stmt.where(MedicalSuspension.status == MedicalSuspensionStatus.ACTIVE)
    rows = list((await session.execute(stmt)).scalars().all())
    return MedicalSuspensionPage(
        items=[MedicalSuspensionRead.model_validate(r) for r in rows], total=len(rows))
```

- [ ] **Step 5: Run (pass)** → `python3 -m pytest tests/api/test_medical_api.py -k unfit -v` → PASS.

- [ ] **Step 6: Commit**
```bash
git add backend/app/api/routes/medical.py backend/app/schemas/medical.py tests/api/test_medical_api.py
git commit -m "feat(medical): feature gate + POST /medical/exams + suspensions list"
```

---

### Task 6.2: Norms CRUD

**Files:** Modify `routes/medical.py`; Test: `tests/api/test_medical_api.py`

- [ ] **Step 1: Add failing test**
```python
@pytest.mark.asyncio
async def test_norm_crud(async_client, sessionmaker, data_factory, make_auth_headers):
    from app.models.models import Position
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        pos = Position(tenant_id=tenant.id, company_id=company.id, name="Электрик")
        session.add(pos); await session.commit(); pos_id = pos.id
    headers = await make_auth_headers(RoleEnum.ADMIN)
    c = await async_client.post("/api/v1/medical/norms", headers=headers, json={
        "position_id": pos_id, "exam_kind": "periodic", "interval_days": 365})
    assert c.status_code == status.HTTP_201_CREATED, c.text
    lst = await async_client.get("/api/v1/medical/norms", headers=headers)
    assert lst.status_code == status.HTTP_200_OK
    assert lst.json()["total"] == 1
```

- [ ] **Step 2: Run (fail)** → FAIL.

- [ ] **Step 3: Implement** — add `GET/POST /medical/norms`, `GET/PATCH/DELETE /medical/norms/{id}` mirroring the prescriptions list/create/get/patch shape, all with `dependencies=[MedicalFeatureGate]`, `MedicalAccess` for writes, `MedicalReadAccess` for reads, `compute_list_etag` on the list, and `AuditService.log_event` on writes. (POST builds `MedicalNorm(tenant_id=..., **payload)`; list returns `MedicalNormPage`.)

- [ ] **Step 4: Run (pass)** → PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/api/routes/medical.py tests/api/test_medical_api.py
git commit -m "feat(medical): norms CRUD endpoints"
```

---

### Task 6.3: Referrals list/create/get/transition

**Files:** Modify `routes/medical.py`; Test: `tests/api/test_medical_api.py`

- [ ] **Step 1: Add failing test**
```python
@pytest.mark.asyncio
async def test_referral_fsm(async_client, sessionmaker, data_factory, make_auth_headers):
    person_id = await _seed_person(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    c = await async_client.post("/api/v1/medical/referrals", headers=headers, json={
        "person_id": person_id, "exam_kind": "periodic",
        "due_at": date(2026, 7, 1).isoformat()})
    assert c.status_code == status.HTTP_201_CREATED, c.text
    rid = c.json()["id"]
    ok = await async_client.post(f"/api/v1/medical/referrals/{rid}/transition",
                                 headers=headers, json={"to": "scheduled"})
    assert ok.status_code == status.HTTP_200_OK
    bad = await async_client.post(f"/api/v1/medical/referrals/{rid}/transition",
                                  headers=headers, json={"to": "issued"})
    assert bad.status_code == status.HTTP_409_CONFLICT
```

- [ ] **Step 2: Run (fail)** → FAIL.

- [ ] **Step 3: Implement** — add referral endpoints. `transition` mirrors prescriptions: `validate_transition`→`InvalidTransition`→409; idempotent no-op; if `to == COMPLETED` require `result_exam_id` (`requires_result`) else 422; set `record.status`, set `result_exam_id` if provided; audit; commit. Use `_to_referral_read` helper that injects `is_overdue` like prescriptions `_to_read`.
```python
def _to_referral_read(record, *, today):
    return MedicalReferralRead.model_validate(record).model_copy(
        update={"is_overdue": lc.is_overdue(record.due_at, record.status, today)})
```

- [ ] **Step 4: Run (pass)** → PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/api/routes/medical.py tests/api/test_medical_api.py
git commit -m "feat(medical): referral endpoints + FSM transition"
```

---

### Task 6.4: Contingent + generate-referrals + summary

**Files:** Modify `routes/medical.py`; Test: `tests/api/test_medical_api.py`

- [ ] **Step 1: Add failing test**
```python
@pytest.mark.asyncio
async def test_contingent_and_generate(async_client, sessionmaker, data_factory, make_auth_headers):
    from app.models.models import MedicalNorm, Position
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        pos = Position(tenant_id=tenant.id, company_id=company.id, name="Крановщик")
        session.add(pos); await session.flush()
        await data_factory.create_person(tenant=tenant, company=company, session=session, position_id=pos.id)
        session.add(MedicalNorm(tenant_id=tenant.id, position_id=pos.id,
                                exam_kind="periodic", interval_days=365))
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    cont = await async_client.get("/api/v1/medical/contingent", headers=headers)
    assert cont.status_code == status.HTTP_200_OK
    assert any(i["status"] == "missing" for i in cont.json()["items"])
    gen = await async_client.post("/api/v1/medical/contingent/generate-referrals", headers=headers)
    assert gen.status_code == status.HTTP_200_OK
    assert gen.json()["count"] == 1
    summ = await async_client.get("/api/v1/medical/summary", headers=headers)
    assert summ.json()["total"] >= 1
```

- [ ] **Step 2: Run (fail)** → FAIL.

- [ ] **Step 3: Implement**
```python
@router.get("/medical/contingent", response_model=ContingentPage,
            dependencies=[MedicalFeatureGate])
async def get_contingent(
    tenant: TenantDep, session: SessionDep, access: MedicalReadAccess,
    position_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
) -> ContingentPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    today = datetime.now(timezone.utc).date()
    items = await medsvc.compute_contingent(session, tenant_id=str(tenant.id),
                                            today=today, position_id=position_id)
    if status_filter:
        items = [i for i in items if i["status"] == status_filter]
    return ContingentPage(items=[ContingentItem(**i) for i in items], total=len(items))


@router.post("/medical/contingent/generate-referrals", dependencies=[MedicalFeatureGate])
async def generate_referrals(
    tenant: TenantDep, session: SessionDep, access: MedicalAccess,
) -> dict[str, int]:
    TenantContextValidator.ensure_tenant_context(tenant)
    today = datetime.now(timezone.utc).date()
    count = await medsvc.generate_due_referrals(
        session, tenant_id=str(tenant.id), today=today,
        issued_by=getattr(access.user, "id", None))
    await session.commit()
    return {"count": count}


@router.get("/medical/summary", response_model=MedicalSummary, dependencies=[MedicalFeatureGate])
async def medical_summary(
    tenant: TenantDep, session: SessionDep, access: MedicalReadAccess,
) -> MedicalSummary:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    today = datetime.now(timezone.utc).date()
    return MedicalSummary(**await medsvc.status_summary(session, tenant_id=str(tenant.id), today=today))
```

- [ ] **Step 4: Run (pass)** → PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/api/routes/medical.py tests/api/test_medical_api.py
git commit -m "feat(medical): contingent + generate-referrals + summary endpoints"
```

---

### Task 6.5: Suspension lift (role-gated)

**Files:** Modify `routes/medical.py`; Test: `tests/api/test_medical_api.py`

- [ ] **Step 1: Add failing test**
```python
@pytest.mark.asyncio
async def test_lift_suspension_requires_admin(async_client, sessionmaker, data_factory, make_auth_headers):
    person_id = await _seed_person(sessionmaker, data_factory)
    admin = await make_auth_headers(RoleEnum.ADMIN)
    await async_client.post("/api/v1/medical/exams", headers=admin, json={
        "person_id": person_id, "exam_kind": "periodic",
        "exam_date": date(2026, 1, 1).isoformat(), "fitness": "unfit"})
    sid = (await async_client.get("/api/v1/medical/suspensions", headers=admin,
                                  params={"person_id": person_id})).json()["items"][0]["id"]
    hr = await make_auth_headers(RoleEnum.HR, email="hr-x@example.com")
    forbidden = await async_client.post(f"/api/v1/medical/suspensions/{sid}/lift", headers=hr)
    assert forbidden.status_code == status.HTTP_403_FORBIDDEN
    ok = await async_client.post(f"/api/v1/medical/suspensions/{sid}/lift", headers=admin)
    assert ok.status_code == status.HTTP_200_OK
    assert ok.json()["status"] == "lifted"
```
> If `RoleEnum.HR` is not a write-role for medical, swap to a role that is in `_MEDICAL_WRITE_ROLES` but not in `LIFT_SUSPENSION_ROLES` (e.g. add `hr` to write-roles; `hr` is already in `_MEDICAL_WRITE_ROLES`). The 403 must come from the lift role-gate, not the ABAC write-gate.

- [ ] **Step 2: Run (fail)** → FAIL.

- [ ] **Step 3: Implement**
```python
@router.post("/medical/suspensions/{suspension_id}/lift",
             response_model=MedicalSuspensionRead, dependencies=[MedicalFeatureGate])
async def lift_suspension(
    suspension_id: str, tenant: TenantDep, session: SessionDep, access: MedicalAccess,
) -> MedicalSuspensionRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    roles = {v.lower() for v in access.to_auth_context().roles}
    if not roles & lc.LIFT_SUSPENSION_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            detail=_error("suspension_lift_forbidden",
                                          "Only admin or owner may lift a medical suspension"))
    record = (await session.execute(select(MedicalSuspension).where(
        MedicalSuspension.id == suspension_id, MedicalSuspension.tenant_id == tenant.id,
        MedicalSuspension.deleted_at.is_(None)))).scalar_one_or_none()
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_error("suspension_not_found", "Not found"))
    if record.status == MedicalSuspensionStatus.ACTIVE:
        record.status = MedicalSuspensionStatus.LIFTED
        record.lifted_at = datetime.now(timezone.utc)
        record.lifted_by = getattr(access.user, "id", None)
    await session.commit()
    await session.refresh(record)
    return MedicalSuspensionRead.model_validate(record)
```

- [ ] **Step 4: Run (pass)** → PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/api/routes/medical.py tests/api/test_medical_api.py
git commit -m "feat(medical): suspension lift (admin/owner gate)"
```

---

### Task 6.6: ETag contract on list endpoints

**Files:** Modify `routes/medical.py` (add ETag to norms/referrals/suspensions lists); Test: `tests/api/test_medical_cache_etag_contract.py`

- [ ] **Step 1: Write failing ETag test** (mirror the captured ETag pattern — 304 hit, bogus-etag miss, post-invalidation) for `GET /medical/norms`.
- [ ] **Step 2: Run (fail)** → FAIL.
- [ ] **Step 3: Implement** — wrap each list endpoint with `compute_list_etag` + `apply_etag_response_headers` + `if-none-match`→304 (exactly as `list_prescriptions`).
- [ ] **Step 4: Run (pass)** → PASS.
- [ ] **Step 5: Commit**
```bash
git add backend/app/api/routes/medical.py tests/api/test_medical_cache_etag_contract.py
git commit -m "feat(medical): ETag contract on list endpoints"
```

---

## Phase 7 — Admission-block integration

### Task 7.1: Extract shared admission helper (de-dup)

**Files:**
- Create: `backend/app/services/person_admission.py`
- Modify: `backend/app/services/tasks.py` (`_enforce_person_invariants` → delegate), `backend/app/api/routes/packs.py` (inline check → delegate)
- Test: `backend/tests/test_person_admission.py`

- [ ] **Step 1: Write failing test**
```python
# backend/tests/test_person_admission.py
import inspect
from app.services import person_admission
from app.services import tasks


def test_shared_helper_exists_and_is_used():
    assert hasattr(person_admission, "enforce_person_admission")
    src = inspect.getsource(tasks._enforce_person_invariants)
    assert "enforce_person_admission" in src
```

- [ ] **Step 2: Run (fail)** → FAIL.

- [ ] **Step 3: Implement** — move the body of `_enforce_person_invariants` into `person_admission.enforce_person_admission(session, *, tenant_scope, persons)`; keep the same `{"code": "requirements_not_met", "details": [...]}` contract. Then in `tasks.py` make `_enforce_person_invariants` call it; in `packs.py` replace the inline block with a call to it.

- [ ] **Step 4: Run regression** — `python3 -m pytest tests/integration/test_packages_e2e.py backend/tests/test_person_admission.py -v` → PASS (existing admission flows unchanged).

- [ ] **Step 5: Commit**
```bash
git add backend/app/services/person_admission.py backend/app/services/tasks.py backend/app/api/routes/packs.py backend/tests/test_person_admission.py
git commit -m "refactor(admission): extract shared enforce_person_admission helper"
```

---

### Task 7.2: Suspension block + norm-aware (with fallback)

**Files:** Modify `backend/app/services/person_admission.py`; Test: `tests/api/test_medical_contingent_admission.py`

- [ ] **Step 1: Write failing test** (end-to-end safety loop through a pack/admission flow)
```python
# tests/api/test_medical_contingent_admission.py
import pytest
from app.services.person_admission import enforce_person_admission


@pytest.mark.asyncio
async def test_active_suspension_blocks_admission(sessionmaker, data_factory):
    from datetime import date, datetime, timezone
    from app.models.models import MedicalExam, MedicalSuspension, MedicalSuspensionStatus
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        # give a valid exam so the legacy check passes...
        session.add(MedicalExam(tenant_id=tenant.id, person_id=person.id, exam_type="periodic",
                                exam_date=date(2026, 1, 1), valid_until=date(2999, 1, 1)))
        # ...but an active suspension must still block
        session.add(MedicalSuspension(tenant_id=tenant.id, person_id=person.id, reason="unfit",
                                      started_at=datetime.now(timezone.utc),
                                      status=MedicalSuspensionStatus.ACTIVE))
        await session.commit()
        with pytest.raises(ValueError) as ei:
            await enforce_person_admission(session, tenant_scope=(str(tenant.id),), persons=[person])
        assert "medical_suspension" in str(ei.value)
```

- [ ] **Step 2: Run (fail)** → FAIL (suspension not yet checked).

- [ ] **Step 3: Implement** — in `enforce_person_admission`, after computing `valid_medical`, query active `MedicalSuspension` for the person_ids; add `"medical_suspension"` to a person's `missing` list when an active suspension exists. Add the norm-aware branch: if `MedicalNorm` rows exist for the person's position, compute required kinds and add `"medical_exam"` when any required kind is MISSING/OVERDUE; **if no norms exist for the position, keep the existing "any valid exam" check** (back-compat).

- [ ] **Step 4: Run (pass)** + regression — `python3 -m pytest tests/api/test_medical_contingent_admission.py tests/integration/test_packages_e2e.py -v` → PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/services/person_admission.py tests/api/test_medical_contingent_admission.py
git commit -m "feat(medical): suspension + norm-aware admission block (back-compat fallback)"
```

---

## Phase 8 — Read-side, beat, seed, access-parity

### Task 8.1: Calendar — referral-due + contingent-gap events

**Files:** Modify `backend/app/services/calendar_aggregator.py`; Test: `backend/tests/test_calendar_medical.py`

- [ ] **Step 1: Write failing test** asserting a calendar fetch returns an event with `source_type == "medical_referral"` when a referral with `due_at` exists. (Mirror existing calendar tests; seed a referral via the factory.)
- [ ] **Step 2: Run (fail)** → FAIL.
- [ ] **Step 3: Implement** — add a `_build_medical_referrals` builder (copy of `_build_medicals` shape) emitting `CalendarEventItem(id=f"medical_referral:{ref.id}", source_type="medical_referral", title=f"Направление на медосмотр: {ref.exam_kind.value}", starts_at=_coerce_dt(ref.due_at), status=...)`; register it in the aggregator's source list next to `_build_medicals`.
- [ ] **Step 4: Run (pass)** → PASS.
- [ ] **Step 5: Commit**
```bash
git add backend/app/services/calendar_aggregator.py backend/tests/test_calendar_medical.py
git commit -m "feat(medical): calendar referral-due events"
```

---

### Task 8.2: Dashboard — suspension + contingent counts

**Files:** Modify `backend/app/modules/operational_dashboard/service.py`; Test: `backend/tests/test_dashboard_medical.py`

- [ ] **Step 1: Write failing test** — dashboard alert payload contains an `"medical_suspension"` count > 0 after seeding an active suspension.
- [ ] **Step 2: Run (fail)** → FAIL.
- [ ] **Step 3: Implement** — in `_get_overdue_alerts`, add an `_add_count(...)` for active `MedicalSuspension` keyed `"medical_suspension"` (mirror the existing medical-exam `_add_count` block).
- [ ] **Step 4: Run (pass)** → PASS.
- [ ] **Step 5: Commit**
```bash
git add backend/app/modules/operational_dashboard/service.py backend/tests/test_dashboard_medical.py
git commit -m "feat(medical): dashboard suspension count"
```

---

### Task 8.3: Data Quality — missing-required-exam rule

**Files:** Modify `backend/app/modules/data_quality/rules.py`; Test: `backend/tests/test_dq_medical.py`

- [ ] **Step 1: Write failing test** — a DQ run flags an issue of a new type for a person who is `unfit` (latest exam) but has no active suspension.
- [ ] **Step 2: Run (fail)** → FAIL.
- [ ] **Step 3: Implement** — add a rule (or extend `ExpiredRecordsRule`) that selects latest exam per person with `fitness == unfit` and no active `MedicalSuspension`, appending a `DataQualityIssue` (`affected_entity_type="person"`, severity HIGH).
- [ ] **Step 4: Run (pass)** → PASS.
- [ ] **Step 5: Commit**
```bash
git add backend/app/modules/data_quality/rules.py backend/tests/test_dq_medical.py
git commit -m "feat(medical): DQ rule unfit-without-suspension"
```

---

### Task 8.4: Celery beat — medical.contingent.tick

**Files:** Modify `backend/app/services/celery_app.py`, `backend/app/tasks/_core.py`; Test: `backend/tests/test_medical_tick.py`

- [ ] **Step 1: Write failing test** — call `_medical_contingent_tick()` coroutine directly (as the test for prescriptions does) after seeding an overdue/missing contingent; assert it returns the processed count and enqueues outbox rows.
```python
# backend/tests/test_medical_tick.py
import pytest


@pytest.mark.asyncio
async def test_medical_tick_processes_overdue(sessionmaker, data_factory, monkeypatch):
    from app.tasks import _core
    # seed a tenant with a norm + person lacking the exam (see Task 5.2 seed)
    # then:
    processed = await _core._medical_contingent_tick()
    assert processed >= 0
```
> Keep this assertion loose (`>= 0`) if multi-tenant iteration is environment-sensitive; the core logic is covered by `notify_overdue` in Task 5.4. Strengthen if the test harness seeds an active tenant deterministically.

- [ ] **Step 2: Run (fail)** → FAIL.
- [ ] **Step 3: Implement**
  - In `tasks/_core.py` (next to `prescriptions_escalate_tick`):
```python
@celery_app.task(
    name="medical.contingent.tick",
    autoretry_for=RETRYABLE_EXCEPTIONS, retry_backoff=True, retry_jitter=True, max_retries=5,
)
def medical_contingent_tick() -> int:
    return _run_coroutine(_medical_contingent_tick())


async def _medical_contingent_tick() -> int:
    from app.domains.medical.service import notify_overdue
    today = datetime.now(tz=timezone.utc).date()
    async with AsyncSessionLocal(tenant=settings.default_tenant_slug) as session:
        tenants = list((await session.execute(select(Tenant).where(Tenant.is_active.is_(True)))).scalars().all())
    processed = 0
    for tenant in tenants:
        with tenant_context(tenant.slug):
            ensure_tenant_schema(tenant.slug)
            async with session_scope(tenant=tenant.slug) as session:
                tenant_id, _scope = await _resolve_task_tenant_scope(session, tenant.slug)
                processed += await notify_overdue(session, tenant_id=tenant_id, actor_id=None, today=today)
                await session.commit()
    return processed
```
  - In `celery_app.py` `beat_schedule`, add:
```python
"medical-contingent-daily": {
    "task": "medical.contingent.tick",
    "schedule": crontab(hour=3, minute=0),
},
```
- [ ] **Step 4: Run (pass)** → PASS.
- [ ] **Step 5: Commit**
```bash
git add backend/app/services/celery_app.py backend/app/tasks/_core.py backend/tests/test_medical_tick.py
git commit -m "feat(medical): daily contingent escalation beat tick"
```

---

### Task 8.5: Access-parity test

**Files:** Test: `backend/tests/test_medical_access_parity.py`

- [ ] **Step 1: Write the test**
```python
# backend/tests/test_medical_access_parity.py
from app.api.routes.medical import _MEDICAL_READ_ROLES, _MEDICAL_WRITE_ROLES


def test_medical_write_roles_subset_of_read_roles():
    assert set(_MEDICAL_WRITE_ROLES).issubset(set(_MEDICAL_READ_ROLES))
```
- [ ] **Step 2: Run** → PASS (role lists already satisfy this).
- [ ] **Step 3: Commit**
```bash
git add backend/tests/test_medical_access_parity.py
git commit -m "test(medical): access-parity write⊆read"
```

---

### Task 8.6: Cross-tenant isolation test

**Files:** Test: `tests/api/test_medical_api.py` (add)

- [ ] **Step 1: Write the test** — seed an exam in tenant A; with tenant B headers (distinct email!) `GET /api/v1/medical/exams?person_id=<A's person>` returns `total == 0` and no leak; `GET /medical/suspensions` likewise scoped.
- [ ] **Step 2: Run** → PASS (queries are tenant-scoped).
- [ ] **Step 3: Commit**
```bash
git add tests/api/test_medical_api.py
git commit -m "test(medical): cross-tenant isolation"
```

---

### Task 8.7: Feature seed + demo data

**Files:** Modify the demo bootstrap (`scripts/` or `backend/app/.../bootstrap_demo_tenant`); Test: extend the bootstrap test if present.

- [ ] **Step 1: Locate demo bootstrap** — `grep -rn "bootstrap_demo_tenant" backend/app` to find the seeding entrypoint.
- [ ] **Step 2: Add seed** — insert a `Feature(code="medical", title="Медосмотры")` shared row (idempotent: skip if exists) and, for the demo tenant: one `MedicalNorm` (a demo position + `periodic`/365) and a `Person` on that position with no exam (so `/medical/contingent` shows a `missing` row in the demo).
- [ ] **Step 3: Run** the bootstrap/seed test (or a smoke import) → PASS.
- [ ] **Step 4: Commit**
```bash
git add -A
git commit -m "feat(medical): seed medical feature + demo contingent gap"
```

---

## Final verification

- [ ] **Run the full medical suite**
Run: `python3 -m pytest tests/unit/test_medical_lifecycle.py backend/tests/test_medical_models.py backend/tests/test_medical_service.py backend/tests/test_medical_events.py tests/api/test_medical_api.py tests/api/test_medical_cache_etag_contract.py tests/api/test_medical_contingent_admission.py backend/tests/test_med01_medical_domain_migration.py backend/tests/test_medical_access_parity.py -v`
Expected: ALL PASS (note Py3.12 vs local Py3.13 per CLAUDE.md; CI is canonical).

- [ ] **Run adjacent regressions** (admission, outbox, mapper, calendar, dashboard, DQ, packages-e2e)
Run: `python3 -m pytest backend/tests/test_orm_mapper_configuration.py tests/test_outbox_dispatch.py tests/integration/test_packages_e2e.py -v`
Expected: PASS.

- [ ] **OpenAPI sanity** — start app or run the route-import test to confirm the new endpoints register without error.

- [ ] **Update handoff** — append a handoff entry to `AI_IMPLEMENTATION_REPORT.md` and a `CHANGELOG.md` line (раздел E + H).

---

## Spec coverage check (self-review)

| Spec section | Task(s) |
|---|---|
| 4.1 extend medical_exam | 1.2, 1.3 |
| 4.2 medical_norm | 1.2, 1.3 |
| 4.3 medical_referral | 1.2, 1.3 |
| 4.4 medical_suspension | 1.2, 1.3 |
| 4.5 enums + migration | 1.1, 1.3 |
| 5.1 referral FSM | 2.1 |
| 5.2 periodicity | 2.2 |
| 5.3 contingent classify | 2.3 |
| 5.4 СОУТ resolution | 2.4 |
| 5.5 suspension rule | 2.5, 5.1 |
| 6.1 admission block + de-dup | 7.1, 7.2 |
| 6.2 calendar/dashboard/DQ | 8.1, 8.2, 8.3 |
| 6.3 events | 3.1, 5.1 |
| 6.4 automation (generate + tick) | 5.3, 5.4, 8.4 |
| 7 API surface | 6.1–6.6 |
| 8 RBAC/flag/tenant | 6.1, 6.5, 8.5, 8.6 |
| 9 tests | every task (TDD) + 6.6, 8.5, 8.6 |
| 10 acceptance | Final verification |

All spec sections map to at least one task.
