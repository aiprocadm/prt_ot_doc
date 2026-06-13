# Медосмотры §9.2 — авто-контингент из штатки + документы 29н — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать формальные документы приказа 29н (контингент + поименный список), авто-формируемые из штатного расписания (Position+Person × вредные факторы), и factor-driven путь в `compute_contingent` (сотрудник в контингенте без ручной нормы).

**Architecture:** Три слоя поверх медицинского домена Среза-1 (`backend/app/domains/medical/`): (1) данные — каталог `MedicalFactor` (29н) + строковая привязка `RiskHazard.medical_factor_code`; (2) чистый движок — `factors_for_hazards` / `required_exams_from_factors` + расширение `compute_contingent` (норм-путь ∪ factor-путь); (3) документы — `build_contingent_register` / `build_named_list` (live-compute) + API.

**Tech Stack:** Python 3.12 (локально Py3.13.7/.venv), FastAPI, SQLAlchemy async, Alembic, pytest. Спек: `docs/superpowers/specs/2026-06-13-medical-contingent-staffing-design.md`.

**Среда тестов:** локально `python -m pytest` через PowerShell→file (канон Py3.12 = CI, выключен). Команды ниже — канонические; на этой машине запускать через `.venv` ([[py313_win_pytest_invocation]]).

**Базовая ветка:** `feat/medical-contingent-staffing` (уже создана; спек закоммичен).

---

## File Structure

- **Modify** `backend/app/models/models.py` — новый класс `MedicalFactor` (после `MedicalNorm`, ~стр.900).
- **Modify** `backend/app/models/risk.py` — колонка `RiskHazard.medical_factor_code` (~стр.76).
- **Create** `backend/app/migrations/versions/20260613_med02_medical_factor_catalog.py` — таблица + колонка.
- **Modify** `backend/app/domains/medical/lifecycle.py` — `FactorTuple`, `factors_for_hazards`, `required_exams_from_factors`, `worst_status`.
- **Modify** `backend/app/domains/medical/service.py` — `_load_factor_catalog`, расширение `compute_contingent`, `build_contingent_register`, `build_named_list`.
- **Modify** `backend/app/schemas/medical.py` — `MedicalFactor{Create,Read,Update,Page}`, `ContingentRegisterRow/Page`, `NamedListRow/Page`.
- **Modify** `backend/app/api/routes/medical.py` — CRUD `/medical/factors`, `GET /medical/contingent/register`, `GET /medical/named-list`.
- **Modify** `backend/app/services/demo_bootstrap.py` — seed факторов 29н + привязка demo-hazard + position_hazard.
- **Create** tests: `backend/tests/test_medical_factor_model.py`, `backend/tests/test_medical_factor_migration.py`, `backend/tests/test_medical_factor_engine.py`, `tests/api/test_medical_documents.py`, `tests/api/test_medical_factors_api.py`.

---

## Task 1: Модель `MedicalFactor` + колонка `RiskHazard.medical_factor_code`

**Files:**
- Modify: `backend/app/models/models.py` (после класса `MedicalNorm`, ~стр.900)
- Modify: `backend/app/models/risk.py` (класс `RiskHazard`, ~стр.76)
- Test: `backend/tests/test_medical_factor_model.py`

- [ ] **Step 1: Написать падающий тест**

Create `backend/tests/test_medical_factor_model.py`:

```python
"""Model-shape guards for the 29н factor catalog (§9.2)."""
from app.models.models import MedicalFactor
from app.models.risk import RiskHazard


def test_medical_factor_table_and_columns():
    cols = MedicalFactor.__table__.columns
    assert MedicalFactor.__tablename__ == "medical_factor"
    for name in ("id", "tenant_id", "code", "name", "category",
                 "exam_kinds", "periodicity_months", "participants", "lab_tests"):
        assert name in cols, f"missing column {name}"
    uniques = {tuple(c.name for c in con.columns)
               for con in MedicalFactor.__table__.constraints
               if con.__class__.__name__ == "UniqueConstraint"}
    assert ("tenant_id", "code") in uniques


def test_risk_hazard_has_medical_factor_code():
    assert "medical_factor_code" in RiskHazard.__table__.columns
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `python -m pytest backend/tests/test_medical_factor_model.py -v`
Expected: FAIL — `ImportError: cannot import name 'MedicalFactor'`.

- [ ] **Step 3: Добавить модель `MedicalFactor`**

В `backend/app/models/models.py`, сразу после класса `MedicalNorm` (после его `__table_args__`, ~стр.900):

```python
class MedicalFactor(TenantBaseModel):
    """29н reference catalog: harmful factor / kind of work mandating periodic exams.

    VARCHAR ``category`` (no PG enum — enum-label-parity anti-pattern). Linked from
    ``RiskHazard.medical_factor_code`` (string, no cross-base FK). Optional norm overrides.
    """
    __tablename__ = "medical_factor"

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False, default="factor")
    exam_kinds: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    periodicity_months: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    participants: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    lab_tests: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_medical_factor_tenant_code"),
    )
```

- [ ] **Step 4: Добавить колонку в `RiskHazard`**

В `backend/app/models/risk.py`, в классе `RiskHazard`, сразу после `document_file_id` (~стр.76, перед `document_file` relationship):

```python
    # §9.2: maps this tenant hazard to a 29н factor code (MedicalFactor.code).
    # Plain string — RiskHazard is on TenantBase, MedicalFactor on TenantBaseModel;
    # a cross-base FK breaks metadata wiring (wa02 lesson). No FK by design.
    medical_factor_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
```

- [ ] **Step 5: Запустить тест — убедиться, что проходит**

Run: `python -m pytest backend/tests/test_medical_factor_model.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Прогнать mapper-guard (регрессия маппинга)**

Run: `python -m pytest backend/tests/test_orm_mapper_configuration.py -q`
Expected: PASS — `configure_mappers()` зелёный с новой моделью.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/models.py backend/app/models/risk.py backend/tests/test_medical_factor_model.py
git commit -m "feat(medical): MedicalFactor 29н catalog model + RiskHazard.medical_factor_code"
```

---

## Task 2: Миграция `med02`

**Files:**
- Create: `backend/app/migrations/versions/20260613_med02_medical_factor_catalog.py`
- Test: `backend/tests/test_medical_factor_migration.py`

- [ ] **Step 1: Написать падающий тест**

Create `backend/tests/test_medical_factor_migration.py`:

```python
"""Chain + shape guard for med02 (medical_factor catalog)."""
import importlib

MOD = "app.migrations.versions.20260613_med02_medical_factor_catalog"


def test_med02_chains_to_ed03():
    mod = importlib.import_module(MOD)
    assert mod.revision == "20260613_med02_medical_factor_catalog"
    assert mod.down_revision == "20260612_ed03_briefing_signature_unique"


def test_med02_has_upgrade_and_downgrade():
    mod = importlib.import_module(MOD)
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)
```

> NB: модуль импортируется по точечному пути с цифрами — `importlib.import_module` это допускает (в отличие от `import` statement).

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `python -m pytest backend/tests/test_medical_factor_migration.py -v`
Expected: FAIL — `ModuleNotFoundError` (файла миграции нет).

- [ ] **Step 3: Написать миграцию**

Create `backend/app/migrations/versions/20260613_med02_medical_factor_catalog.py`:

```python
"""med02: 29н factor catalog (medical_factor) + RiskHazard.medical_factor_code (TZ B.8 §9.2).

Additive. New table + one nullable column on risk_hazards. VARCHAR category (no enum
types), no cross-base FK. Round-trip-safe: downgrade drops the column then the table.
Table/column names are LITERAL (AST-audit blindspot — [[audit_static_analysis_blindspots]]).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260613_med02_medical_factor_catalog"
down_revision = "20260612_ed03_briefing_signature_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "medical_factor",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False, server_default="factor"),
        sa.Column("exam_kinds", sa.JSON(), nullable=False),
        sa.Column("periodicity_months", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("participants", sa.JSON(), nullable=True),
        sa.Column("lab_tests", sa.JSON(), nullable=True),
        sa.UniqueConstraint("tenant_id", "code", name="uq_medical_factor_tenant_code"),
    )
    op.add_column(
        "risk_hazards",
        sa.Column("medical_factor_code", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("risk_hazards", "medical_factor_code")
    op.drop_table("medical_factor")
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `python -m pytest backend/tests/test_medical_factor_migration.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Применить миграцию к свежей SQLite-БД (smoke)**

Run (из `backend/`): `python -m pytest backend/tests/test_medical_factor_model.py -q`
> Если в репо есть общий guard прогона миграций (`test_migrations_comprehensive_safety.py`), прогнать его:
Run: `python -m pytest backend/tests/test_migrations_comprehensive_safety.py -q`
Expected: PASS — цепочка `…→ed03→med02` одна голова, без сирот.

- [ ] **Step 6: Commit**

```bash
git add backend/app/migrations/versions/20260613_med02_medical_factor_catalog.py backend/tests/test_medical_factor_migration.py
git commit -m "feat(medical): med02 migration — medical_factor table + risk_hazards.medical_factor_code"
```

---

## Task 3: Чистый движок — `factors_for_hazards` / `required_exams_from_factors` / `worst_status`

**Files:**
- Modify: `backend/app/domains/medical/lifecycle.py` (после `resolve_required_kinds`, ~стр.128)
- Test: `backend/tests/test_medical_factor_engine.py`

- [ ] **Step 1: Написать падающие тесты**

Create `backend/tests/test_medical_factor_engine.py`:

```python
"""Pure-function tests for the §9.2 factor-driven engine."""
from app.domains.medical.lifecycle import (
    FactorTuple, factors_for_hazards, required_exams_from_factors, worst_status,
)
from app.models.models import MedicalExamKind as K

NOISE: FactorTuple = ("4.4", "Шум", (K.PERIODIC,), 12)
CHEM: FactorTuple = ("1.1", "Химические", (K.PERIODIC, K.FLUOROGRAPHY), 24)
HEIGHT: FactorTuple = ("6.1", "Работы на высоте", (K.PERIODIC,), 12)
CATALOG = [NOISE, CHEM, HEIGHT]


def test_factors_for_hazards_selects_mapped_codes():
    assert factors_for_hazards({"4.4", "1.1"}, CATALOG) == {NOISE, CHEM}


def test_factors_for_hazards_ignores_unmapped():
    assert factors_for_hazards({"zzz"}, CATALOG) == set()
    assert factors_for_hazards(set(), CATALOG) == set()


def test_required_exams_union_with_strictest_periodicity():
    # PERIODIC appears in NOISE(12) and CHEM(24) → strictest 12; FLUOROGRAPHY from CHEM(24).
    result = required_exams_from_factors({NOISE, CHEM})
    assert result == {K.PERIODIC: 12, K.FLUOROGRAPHY: 24}


def test_worst_status_priority():
    assert worst_status(["ok", "due_soon", "overdue"]) == "overdue"
    assert worst_status(["ok", "missing", "due_soon"]) == "missing"
    assert worst_status(["ok"]) == "ok"
    assert worst_status([]) == "ok"
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `python -m pytest backend/tests/test_medical_factor_engine.py -v`
Expected: FAIL — `ImportError` (функций нет).

- [ ] **Step 3: Реализовать функции**

В `backend/app/domains/medical/lifecycle.py`, после `resolve_required_kinds` (~стр.128), добавить:

```python
# ---------------------------------------------------------------------------
# 2.6 — §9.2 factor-driven resolution (29н catalog → required kinds)
# ---------------------------------------------------------------------------

# (code, name, exam_kinds, periodicity_months) — ORM-free 29н factor tuple.
FactorTuple = tuple[str, str, tuple["MedicalExamKind", ...], int]

# Worst-first priority of contingent statuses (for per-person rollup).
_STATUS_PRIORITY: dict[str, int] = {"missing": 3, "overdue": 2, "due_soon": 1, "ok": 0}


def factors_for_hazards(
    hazard_factor_codes: set[str], catalog: Iterable[FactorTuple]
) -> set[FactorTuple]:
    """29н factors whose code is mapped by one of the position's hazards."""
    return {f for f in catalog if f[0] in hazard_factor_codes}


def required_exams_from_factors(
    factors: Iterable[FactorTuple],
) -> dict[MedicalExamKind, int]:
    """Union of mandated exam kinds → strictest (min) periodicity in months."""
    result: dict[MedicalExamKind, int] = {}
    for _code, _name, kinds, months in factors:
        for kind in kinds:
            if kind not in result or months < result[kind]:
                result[kind] = months
    return result


def worst_status(statuses: Iterable[str]) -> str:
    """Roll up per-kind contingent statuses to the most severe; 'ok' when empty."""
    worst = "ok"
    for st in statuses:
        if _STATUS_PRIORITY.get(st, 0) > _STATUS_PRIORITY[worst]:
            worst = st
    return worst
```

> `MedicalExamKind` уже импортирован в начале `lifecycle.py`. `Iterable` уже импортирован (`from collections.abc import Iterable`).

- [ ] **Step 4: Запустить тесты — убедиться, что проходят**

Run: `python -m pytest backend/tests/test_medical_factor_engine.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/medical/lifecycle.py backend/tests/test_medical_factor_engine.py
git commit -m "feat(medical): pure factor-driven engine — factors_for_hazards/required_exams_from_factors/worst_status"
```

---

## Task 4: Расширить `compute_contingent` factor-driven путём

**Files:**
- Modify: `backend/app/domains/medical/service.py` (импорты, новый `_load_factor_catalog`, тело `compute_contingent` ~стр.173-225)
- Test: `backend/tests/test_medical_contingent_factor.py`

- [ ] **Step 1: Написать падающий тест**

Create `backend/tests/test_medical_contingent_factor.py`:

```python
"""compute_contingent must include factor-driven persons with NO manual norm."""
import pytest
from datetime import date

from app.domains.medical.service import compute_contingent
from app.models.models import (
    Company, MedicalFactor, Person, Position,
)
from app.models.risk import RiskHazard


@pytest.mark.asyncio
async def test_contingent_includes_factor_driven_person_without_norm(
    sessionmaker, data_factory,
):
    # Engine fixture conventions mirror tests/conftest.py (sessionmaker + data_factory).
    async with sessionmaker() as session:
        tenant_id = await data_factory.tenant(session)
        company = Company(tenant_id=tenant_id, name="ООО Демо")
        session.add(company); await session.flush()
        hazard = RiskHazard(tenant_id=tenant_id, code="noise", title="Шум",
                            medical_factor_code="4.4")
        session.add(hazard); await session.flush()
        pos = Position(tenant_id=tenant_id, company_id=company.id, name="Сварщик")
        pos.hazards.append(hazard)
        session.add(pos); await session.flush()
        person = Person(tenant_id=tenant_id, company_id=company.id, position_id=pos.id,
                        first_name="Иван", last_name="Петров")
        session.add(person)
        session.add(MedicalFactor(tenant_id=tenant_id, code="4.4", name="Шум",
                                  exam_kinds=["periodic"], periodicity_months=12))
        await session.commit()

        items = await compute_contingent(session, tenant_id=tenant_id, today=date(2026, 6, 13))

    # No MedicalNorm was created — the person enters the contingent factor-driven.
    assert any(it["person_id"] == person.id and it["exam_kind"] == "periodic"
               and it["status"] == "missing" for it in items)
```

> **NB:** точные имена фикстур (`sessionmaker`/`data_factory`) и helper'ы `data_factory.tenant(...)` — сверить с `tests/conftest.py` репо; если API фабрики иной, адаптировать создание tenant/company. Суть теста — фактор без нормы даёт строку контингента.

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `python -m pytest backend/tests/test_medical_contingent_factor.py -v`
Expected: FAIL — текущий `compute_contingent` возвращает `[]` при отсутствии норм.

- [ ] **Step 3: Добавить загрузчик каталога + расширить `compute_contingent`**

В `backend/app/domains/medical/service.py`:

(a) Импорты — добавить `MedicalFactor` в существующий блок `from app.models.models import (...)` (стр.11-15):

```python
from app.models.models import (
    MedicalExam, MedicalExamKind, MedicalFactor, MedicalFitness, MedicalNorm,
    MedicalReferral, MedicalReferralStatus, MedicalSuspension,
    MedicalSuspensionStatus, Person, Position,
)
```

(b) Добавить загрузчик перед `compute_contingent` (~стр.171):

```python
async def _load_factor_catalog(
    session: AsyncSession, *, tenant_id: str
) -> list[lc.FactorTuple]:
    """29н factor catalog as ORM-free FactorTuples for the pure engine."""
    stmt = select(
        MedicalFactor.code, MedicalFactor.name,
        MedicalFactor.exam_kinds, MedicalFactor.periodicity_months,
    ).where(MedicalFactor.tenant_id == tenant_id)
    out: list[lc.FactorTuple] = []
    for code, name, kinds, months in (await session.execute(stmt)).all():
        out.append((code, name, tuple(MedicalExamKind(k) for k in (kinds or [])), int(months)))
    return out
```

(c) Заменить тело `compute_contingent` (стр.177-225) на версию с factor-путём:

```python
    """Per (active person, required exam-kind) contingent rows with status (ok/due_soon/overdue/missing).

    Required kinds = norm-driven (resolve_required_kinds) ∪ factor-driven (29н factors mapped
    via Position hazards' medical_factor_code). A person enters the contingent even without a
    manual MedicalNorm when their position's hazards map to 29н factors.
    """
    norm_stmt = select(
        MedicalNorm.position_id, MedicalNorm.hazard_id,
        MedicalNorm.working_conditions_class, MedicalNorm.exam_kind,
    ).where(MedicalNorm.tenant_id == tenant_id)
    norms = [(r[0], r[1], r[2], r[3]) for r in (await session.execute(norm_stmt)).all()]
    catalog = await _load_factor_catalog(session, tenant_id=tenant_id)
    if not norms and not catalog:
        return []

    p_stmt = (
        select(Person)
        .where(
            Person.tenant_id == tenant_id, Person.deleted_at.is_(None),
            Person.position_id.is_not(None),
        )
        .options(selectinload(Person.position).selectinload(Position.hazards))
    )
    if position_id:
        p_stmt = p_stmt.where(Person.position_id == position_id)
    people = list((await session.execute(p_stmt)).scalars().all())
    if not people:
        return []

    person_ids = [p.id for p in people]
    ex_stmt = select(
        MedicalExam.person_id, MedicalExam.exam_kind, func.max(MedicalExam.valid_until),
    ).where(
        MedicalExam.tenant_id == tenant_id, MedicalExam.deleted_at.is_(None),
        MedicalExam.person_id.in_(person_ids), MedicalExam.exam_kind.is_not(None),
    ).group_by(MedicalExam.person_id, MedicalExam.exam_kind)
    latest: dict[tuple[str, MedicalExamKind], date] = {
        (pid, kind): vu for pid, kind, vu in (await session.execute(ex_stmt)).all()
    }

    items: list[dict] = []
    for person in people:
        hazards = person.position.hazards if person.position else []
        hazard_ids = {h.id for h in hazards}
        factor_codes = {h.medical_factor_code for h in hazards if h.medical_factor_code}
        required = lc.resolve_required_kinds(
            person.position_id, person.working_conditions_class, hazard_ids, norms,
        )
        required |= set(
            lc.required_exams_from_factors(
                lc.factors_for_hazards(factor_codes, catalog)
            ).keys()
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
```

- [ ] **Step 4: Запустить новый тест + parity Среза-1**

Run: `python -m pytest backend/tests/test_medical_contingent_factor.py -v`
Expected: PASS.

Run: `python -m pytest backend/tests/ -k "contingent or medical" -q`
Expected: PASS — норм-путь и summary не сломаны (back-compat).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/medical/service.py backend/tests/test_medical_contingent_factor.py
git commit -m "feat(medical): factor-driven path in compute_contingent (29н staffing, no manual norm)"
```

---

## Task 5: Сервисы документов — `build_contingent_register` / `build_named_list`

**Files:**
- Modify: `backend/app/domains/medical/service.py` (новые функции после `status_summary`, ~стр.247; импорт `EmploymentStatus`)
- Test: `backend/tests/test_medical_documents_service.py`

- [ ] **Step 1: Написать падающие тесты**

Create `backend/tests/test_medical_documents_service.py`:

```python
"""Document builders: контингент (position-level) + поименный список (person-level)."""
import pytest
from datetime import date

from app.domains.medical.service import build_contingent_register, build_named_list
from app.models.models import Company, MedicalFactor, Person, Position
from app.models.risk import RiskHazard


async def _seed(session, data_factory):
    tenant_id = await data_factory.tenant(session)
    company = Company(tenant_id=tenant_id, name="ООО Демо")
    session.add(company); await session.flush()
    hazard = RiskHazard(tenant_id=tenant_id, code="noise", title="Шум", medical_factor_code="4.4")
    session.add(hazard); await session.flush()
    pos = Position(tenant_id=tenant_id, company_id=company.id, name="Сварщик")
    pos.hazards.append(hazard)
    session.add(pos); await session.flush()
    session.add(Person(tenant_id=tenant_id, company_id=company.id, position_id=pos.id,
                       first_name="Иван", last_name="Петров"))
    session.add(MedicalFactor(tenant_id=tenant_id, code="4.4", name="Шум",
                              exam_kinds=["periodic"], periodicity_months=12))
    await session.commit()
    return tenant_id, pos.id


@pytest.mark.asyncio
async def test_contingent_register_groups_by_position_with_headcount(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant_id, pos_id = await _seed(session, data_factory)
        rows = await build_contingent_register(session, tenant_id=tenant_id, today=date(2026, 6, 13))
    assert len(rows) == 1
    row = rows[0]
    assert row["position_id"] == pos_id
    assert row["headcount"] == 1
    assert {"code": "4.4", "name": "Шум"} in row["factors"]
    assert "periodic" in row["exam_kinds"]


@pytest.mark.asyncio
async def test_named_list_lists_person_with_factors_and_status(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant_id, _pos = await _seed(session, data_factory)
        rows = await build_named_list(session, tenant_id=tenant_id, today=date(2026, 6, 13))
    assert len(rows) == 1
    row = rows[0]
    assert row["full_name"] == "Петров Иван"
    assert row["position_name"] == "Сварщик"
    assert {"code": "4.4", "name": "Шум"} in row["factors"]
    assert row["status"] == "missing"  # no exam yet
    assert row["next_due_date"] == date(2026, 6, 13)  # missing → today


@pytest.mark.asyncio
async def test_documents_empty_without_factor_mapping(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant_id = await data_factory.tenant(session)
        # no factors / no mapped hazards → both documents empty
        reg = await build_contingent_register(session, tenant_id=tenant_id, today=date(2026, 6, 13))
        named = await build_named_list(session, tenant_id=tenant_id, today=date(2026, 6, 13))
    assert reg == [] and named == []
```

> **NB:** сверить фикстуры с `tests/conftest.py`; `full_name` формат — «Фамилия Имя» (см. реализацию ниже).

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `python -m pytest backend/tests/test_medical_documents_service.py -v`
Expected: FAIL — `ImportError` (функций нет).

- [ ] **Step 3: Реализовать сервисы документов**

В `backend/app/domains/medical/service.py`:

(a) Импорт `EmploymentStatus` — добавить в блок `from app.models.models import (...)`:

```python
    MedicalSuspensionStatus, Person, Position, EmploymentStatus,
```

(b) После `status_summary` (~стр.247) добавить общий загрузчик штатки факторов + два построителя:

```python
# ---------------------------------------------------------------------------
# 5.2b — §9.2 formal 29н documents (live-compute, no snapshot table)
# ---------------------------------------------------------------------------


def _months_to_days(months: int) -> int:
    """Documented approximation: reuse Срез-1 day-based machinery."""
    return months * 30


async def _active_headcount_by_position(
    session: AsyncSession, *, tenant_id: str
) -> dict[str, int]:
    """Count of active (non-deleted, employment_status=active) persons per position."""
    stmt = select(Person.position_id, func.count()).where(
        Person.tenant_id == tenant_id, Person.deleted_at.is_(None),
        Person.position_id.is_not(None),
        Person.employment_status == EmploymentStatus.ACTIVE,
    ).group_by(Person.position_id)
    return {pid: int(n) for pid, n in (await session.execute(stmt)).all()}


async def build_contingent_register(
    session: AsyncSession, *, tenant_id: str, today: date
) -> list[dict]:
    """29н «контингент»: position-level rows of factors + headcount (factor-driven only)."""
    catalog = await _load_factor_catalog(session, tenant_id=tenant_id)
    if not catalog:
        return []
    headcount = await _active_headcount_by_position(session, tenant_id=tenant_id)
    pos_stmt = (
        select(Position)
        .where(Position.tenant_id == tenant_id, Position.deleted_at.is_(None))
        .options(selectinload(Position.hazards))
    )
    positions = list((await session.execute(pos_stmt)).scalars().all())
    rows: list[dict] = []
    for pos in positions:
        codes = {h.medical_factor_code for h in pos.hazards if h.medical_factor_code}
        factors = lc.factors_for_hazards(codes, catalog)
        hc = headcount.get(pos.id, 0)
        if not factors or hc == 0:
            continue
        exams = lc.required_exams_from_factors(factors)
        rows.append({
            "position_id": pos.id,
            "position_name": pos.name,
            "factors": [{"code": f[0], "name": f[1]} for f in sorted(factors)],
            "headcount": hc,
            "exam_kinds": sorted(k.value for k in exams),
            "periodicity_months": min(exams.values()) if exams else None,
        })
    return rows


async def build_named_list(
    session: AsyncSession, *, tenant_id: str, today: date, warning_days: int = 30
) -> list[dict]:
    """29н «поименный список»: person-level rows with factors, last/next exam, status (factor-driven)."""
    catalog = await _load_factor_catalog(session, tenant_id=tenant_id)
    if not catalog:
        return []
    p_stmt = (
        select(Person)
        .where(
            Person.tenant_id == tenant_id, Person.deleted_at.is_(None),
            Person.position_id.is_not(None),
            Person.employment_status == EmploymentStatus.ACTIVE,
        )
        .options(
            selectinload(Person.position).selectinload(Position.hazards),
            selectinload(Person.workplace),
        )
    )
    people = list((await session.execute(p_stmt)).scalars().all())
    if not people:
        return []

    person_ids = [p.id for p in people]
    vu_stmt = select(
        MedicalExam.person_id, MedicalExam.exam_kind, func.max(MedicalExam.valid_until),
    ).where(
        MedicalExam.tenant_id == tenant_id, MedicalExam.deleted_at.is_(None),
        MedicalExam.person_id.in_(person_ids), MedicalExam.exam_kind.is_not(None),
    ).group_by(MedicalExam.person_id, MedicalExam.exam_kind)
    latest_vu: dict[tuple[str, MedicalExamKind], date] = {
        (pid, kind): vu for pid, kind, vu in (await session.execute(vu_stmt)).all()
    }
    ld_stmt = select(MedicalExam.person_id, func.max(MedicalExam.exam_date)).where(
        MedicalExam.tenant_id == tenant_id, MedicalExam.deleted_at.is_(None),
        MedicalExam.person_id.in_(person_ids),
    ).group_by(MedicalExam.person_id)
    last_exam: dict[str, date] = {
        pid: d for pid, d in (await session.execute(ld_stmt)).all()
    }

    rows: list[dict] = []
    for person in people:
        hazards = person.position.hazards if person.position else []
        codes = {h.medical_factor_code for h in hazards if h.medical_factor_code}
        factors = lc.factors_for_hazards(codes, catalog)
        if not factors:
            continue
        required = lc.required_exams_from_factors(factors)
        statuses: list[str] = []
        dues: list[date] = []
        for kind in required:
            vu = latest_vu.get((person.id, kind))
            statuses.append(lc.classify(vu, today, warning_days).value)
            dues.append(vu if vu is not None else today)
        full_name = f"{person.last_name} {person.first_name}".strip()
        rows.append({
            "person_id": person.id,
            "full_name": full_name,
            "position_name": person.position.name if person.position else None,
            "department": person.workplace.name if person.workplace else None,
            "factors": [{"code": f[0], "name": f[1]} for f in sorted(factors)],
            "required_kinds": sorted(k.value for k in required),
            "last_exam_date": last_exam.get(person.id),
            "next_due_date": min(dues) if dues else today,
            "status": lc.worst_status(statuses),
        })
    return rows
```

- [ ] **Step 4: Запустить тесты — убедиться, что проходят**

Run: `python -m pytest backend/tests/test_medical_documents_service.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/medical/service.py backend/tests/test_medical_documents_service.py
git commit -m "feat(medical): 29н document builders — build_contingent_register/build_named_list"
```

---

## Task 6: Схемы + API — CRUD факторов + документы

**Files:**
- Modify: `backend/app/schemas/medical.py` (новые схемы в конце файла)
- Modify: `backend/app/api/routes/medical.py` (импорты схем + эндпоинты)
- Test: `tests/api/test_medical_factors_api.py`, `tests/api/test_medical_documents.py`

- [ ] **Step 1: Написать падающие API-тесты**

Create `tests/api/test_medical_factors_api.py`:

```python
"""CRUD /medical/factors + 29н documents over HTTP."""
import pytest


@pytest.mark.asyncio
async def test_factor_crud_and_duplicate_code(medical_client):
    # medical_client: authenticated client for a tenant with `medical` feature ON.
    body = {"code": "4.4", "name": "Шум", "category": "factor",
            "exam_kinds": ["periodic"], "periodicity_months": 12}
    r = await medical_client.post("/medical/factors", json=body)
    assert r.status_code == 201, r.text
    fid = r.json()["id"]

    r2 = await medical_client.post("/medical/factors", json=body)
    assert r2.status_code == 409  # duplicate code

    r3 = await medical_client.get("/medical/factors")
    assert r3.status_code == 200
    assert any(f["code"] == "4.4" for f in r3.json()["items"])

    r4 = await medical_client.patch(f"/medical/factors/{fid}", json={"periodicity_months": 24})
    assert r4.status_code == 200 and r4.json()["periodicity_months"] == 24

    r5 = await medical_client.delete(f"/medical/factors/{fid}")
    assert r5.status_code == 204


@pytest.mark.asyncio
async def test_factors_require_write_role(medical_readonly_client):
    r = await medical_readonly_client.post(
        "/medical/factors",
        json={"code": "x", "name": "y", "exam_kinds": ["periodic"]},
    )
    assert r.status_code in (401, 403)
```

Create `tests/api/test_medical_documents.py`:

```python
"""GET /medical/contingent/register + /medical/named-list over HTTP."""
import pytest


@pytest.mark.asyncio
async def test_register_and_named_list_endpoints(medical_client_with_staffing):
    # Fixture seeds: factor 4.4, a hazard mapped to it, a position with that hazard,
    # one active person in the position, no manual norm.
    r1 = await medical_client_with_staffing.get("/medical/contingent/register")
    assert r1.status_code == 200, r1.text
    reg = r1.json()["items"]
    assert any(row["headcount"] >= 1 and any(f["code"] == "4.4" for f in row["factors"])
               for row in reg)

    r2 = await medical_client_with_staffing.get("/medical/named-list")
    assert r2.status_code == 200, r2.text
    named = r2.json()["items"]
    assert any(any(f["code"] == "4.4" for f in row["factors"]) for row in named)
```

> **NB фикстуры:** имена `medical_client` / `medical_readonly_client` / `medical_client_with_staffing` — выровнять по существующим фикстурам api-тестов (см. `tests/api/conftest.py` и существующий `tests/api/test_medical*` если есть). Если staffing-фикстуры нет — построить инлайн в тесте через сервисный seed (как в Task 5), затем дернуть эндпоинт.

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `python -m pytest tests/api/test_medical_factors_api.py tests/api/test_medical_documents.py -v`
Expected: FAIL — 404 на новых маршрутах.

- [ ] **Step 3: Добавить схемы**

В конец `backend/app/schemas/medical.py`:

```python
class MedicalFactorCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=255)
    category: Literal["factor", "work"] = "factor"
    exam_kinds: list[MedicalExamKind] = Field(..., min_length=1)
    periodicity_months: int = Field(default=12, ge=1, le=120)
    participants: list[str] | None = None
    lab_tests: list[str] | None = None
    model_config = ConfigDict(extra="forbid")


class MedicalFactorRead(BaseModel):
    id: str
    code: str
    name: str
    category: str
    exam_kinds: list[str]
    periodicity_months: int
    participants: list[str] | None = None
    lab_tests: list[str] | None = None
    model_config = ConfigDict(from_attributes=True)


class MedicalFactorUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    category: Literal["factor", "work"] | None = None
    exam_kinds: list[MedicalExamKind] | None = None
    periodicity_months: int | None = Field(default=None, ge=1, le=120)
    participants: list[str] | None = None
    lab_tests: list[str] | None = None
    model_config = ConfigDict(extra="forbid")


class MedicalFactorPage(BaseModel):
    items: list[MedicalFactorRead]
    total: int


class FactorRef(BaseModel):
    code: str
    name: str


class ContingentRegisterRow(BaseModel):
    position_id: str
    position_name: str
    factors: list[FactorRef]
    headcount: int
    exam_kinds: list[str]
    periodicity_months: int | None = None


class ContingentRegisterPage(BaseModel):
    items: list[ContingentRegisterRow]
    total: int


class NamedListRow(BaseModel):
    person_id: str
    full_name: str
    position_name: str | None = None
    department: str | None = None
    factors: list[FactorRef]
    required_kinds: list[str]
    last_exam_date: date | None = None
    next_due_date: date | None = None
    status: str


class NamedListPage(BaseModel):
    items: list[NamedListRow]
    total: int
```

Добавить `Literal` в импорты `schemas/medical.py` (строка `from typing import ...` — если её нет, добавить `from typing import Literal`). Проверить, что `date` импортирован (да, `from datetime import date, datetime`).

- [ ] **Step 4: Добавить эндпоинты + хелпер `_get_factor`**

В `backend/app/api/routes/medical.py`:

(a) Импорты — добавить `MedicalFactor` в блок `from app.models.models import (...)` и новые схемы в блок `from app.schemas.medical import (...)`:

```python
from app.models.models import (
    MedicalExam, MedicalFactor, MedicalNorm, MedicalReferral, MedicalReferralStatus,
    MedicalSuspension, MedicalSuspensionStatus, Person, Tenant,
)
```
```python
from app.schemas.medical import (
    ContingentItem, ContingentPage,
    ContingentRegisterPage, ContingentRegisterRow,
    MedicalExamCreate, MedicalExamPage, MedicalExamRead, MedicalExamUpdate, MedicalRequirementCreate,
    MedicalFactorCreate, MedicalFactorPage, MedicalFactorRead, MedicalFactorUpdate,
    MedicalNormCreate, MedicalNormPage, MedicalNormRead, MedicalNormUpdate,
    MedicalReferralCreate, MedicalReferralPage, MedicalReferralRead, MedicalReferralTransition,
    MedicalSummary,
    MedicalSuspensionPage, MedicalSuspensionRead,
    NamedListPage, NamedListRow,
)
```

(b) Хелпер `_get_factor` — рядом с `_get_norm` (~стр.97):

```python
async def _get_factor(session: AsyncSession, tenant_id: str, factor_id: str) -> MedicalFactor:
    rec = (await session.execute(select(MedicalFactor).where(
        MedicalFactor.id == factor_id, MedicalFactor.tenant_id == tenant_id,
    ))).scalar_one_or_none()
    if rec is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=_error("medical_factor_not_found", "Medical factor not found"),
        )
    return rec
```

(c) Эндпоинты — добавить перед `@router.get("/medical/contingent" ...)` (~стр.673):

```python
@router.get("/medical/factors", response_model=MedicalFactorPage, dependencies=[MedicalFeatureGate])
async def list_medical_factors(
    tenant: TenantDep, session: SessionDep, access: MedicalReadAccess,
    category: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> MedicalFactorPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    stmt = select(MedicalFactor).where(MedicalFactor.tenant_id == tenant.id)
    if category:
        stmt = stmt.where(MedicalFactor.category == category)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = list((await session.execute(
        stmt.order_by(MedicalFactor.code.asc()).offset(offset).limit(limit)
    )).scalars().all())
    return MedicalFactorPage(
        items=[MedicalFactorRead.model_validate(r) for r in rows], total=int(total or 0),
    )


@router.post("/medical/factors", response_model=MedicalFactorRead,
             status_code=status.HTTP_201_CREATED, dependencies=[MedicalFeatureGate])
async def create_medical_factor(
    payload: MedicalFactorCreate, tenant: TenantDep, session: SessionDep, access: MedicalAccess,
) -> MedicalFactorRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    dup = await session.scalar(select(MedicalFactor).where(
        MedicalFactor.tenant_id == tenant.id, MedicalFactor.code == payload.code,
    ))
    if dup is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=_error("medical_factor_duplicate", f"Factor code already exists: {payload.code}"),
        )
    data = payload.model_dump()
    data["exam_kinds"] = [k.value for k in payload.exam_kinds]
    record = MedicalFactor(tenant_id=str(tenant.id), **data)
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return MedicalFactorRead.model_validate(record)


@router.get("/medical/factors/{factor_id}", response_model=MedicalFactorRead,
            dependencies=[MedicalFeatureGate])
async def get_medical_factor(
    factor_id: str, tenant: TenantDep, session: SessionDep, access: MedicalReadAccess,
) -> MedicalFactorRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    return MedicalFactorRead.model_validate(await _get_factor(session, str(tenant.id), factor_id))


@router.patch("/medical/factors/{factor_id}", response_model=MedicalFactorRead,
              dependencies=[MedicalFeatureGate])
async def update_medical_factor(
    factor_id: str, payload: MedicalFactorUpdate, tenant: TenantDep,
    session: SessionDep, access: MedicalAccess,
) -> MedicalFactorRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    record = await _get_factor(session, str(tenant.id), factor_id)
    data = payload.model_dump(exclude_unset=True)
    if "exam_kinds" in data and data["exam_kinds"] is not None:
        data["exam_kinds"] = [k.value if hasattr(k, "value") else k for k in data["exam_kinds"]]
    for k, v in data.items():
        setattr(record, k, v)
    await session.commit()
    await session.refresh(record)
    return MedicalFactorRead.model_validate(record)


@router.delete("/medical/factors/{factor_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[MedicalFeatureGate])
async def delete_medical_factor(
    factor_id: str, tenant: TenantDep, session: SessionDep, access: MedicalAccess,
) -> Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    record = await _get_factor(session, str(tenant.id), factor_id)
    await session.delete(record)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/medical/contingent/register", response_model=ContingentRegisterPage,
            dependencies=[MedicalFeatureGate])
async def get_contingent_register(
    tenant: TenantDep, session: SessionDep, access: MedicalReadAccess,
) -> ContingentRegisterPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    today = datetime.now(timezone.utc).date()
    rows = await medsvc.build_contingent_register(session, tenant_id=str(tenant.id), today=today)
    return ContingentRegisterPage(
        items=[ContingentRegisterRow(**r) for r in rows], total=len(rows),
    )


@router.get("/medical/named-list", response_model=NamedListPage,
            dependencies=[MedicalFeatureGate])
async def get_named_list(
    tenant: TenantDep, session: SessionDep, access: MedicalReadAccess,
) -> NamedListPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    today = datetime.now(timezone.utc).date()
    rows = await medsvc.build_named_list(session, tenant_id=str(tenant.id), today=today)
    return NamedListPage(items=[NamedListRow(**r) for r in rows], total=len(rows))
```

> **NB маршрутизация:** `/medical/contingent/register` зарегистрировать ДО существующего `/medical/contingent` не обязательно (пути не конфликтуют — разные суффиксы), но разместить рядом для читаемости.

- [ ] **Step 5: Запустить API-тесты — убедиться, что проходят**

Run: `python -m pytest tests/api/test_medical_factors_api.py tests/api/test_medical_documents.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/medical.py backend/app/api/routes/medical.py tests/api/test_medical_factors_api.py tests/api/test_medical_documents.py
git commit -m "feat(medical): API — /medical/factors CRUD + /contingent/register + /named-list"
```

---

## Task 7: Demo-seed 29н + parity/регрессия

**Files:**
- Modify: `backend/app/services/demo_bootstrap.py` (seed факторов + привязка demo-hazard + position_hazard)
- Test: расширить `backend/tests/` существующий demo/seed-тест либо `backend/tests/test_medical_factor_seed.py`

- [ ] **Step 1: Написать падающий seed-тест**

Create `backend/tests/test_medical_factor_seed.py`:

```python
"""After demo bootstrap, the named list is non-empty factor-driven."""
import pytest
from datetime import datetime, timezone

from app.domains.medical.service import build_named_list


@pytest.mark.asyncio
async def test_demo_seed_populates_named_list(bootstrapped_tenant_session):
    # bootstrapped_tenant_session: session for a tenant after demo_bootstrap ran.
    session, tenant_id = bootstrapped_tenant_session
    today = datetime.now(timezone.utc).date()
    rows = await build_named_list(session, tenant_id=tenant_id, today=today)
    assert any(any(f["code"] for f in row["factors"]) for row in rows)
```

> **NB:** сверить фикстуру bootstrap с репо (как тестируется `demo_bootstrap` сейчас). Если прямой фикстуры нет — вызвать `seed_demo_data`/эквивалент инлайн в тесте на чистом tenant, затем `build_named_list`.

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `python -m pytest backend/tests/test_medical_factor_seed.py -v`
Expected: FAIL — demo-hazard `demo_general` не имеет `medical_factor_code`, фактора 29н нет → named list пуст.

- [ ] **Step 3: Расширить demo-seed**

В `backend/app/services/demo_bootstrap.py`:

(a) Импорты — добавить `MedicalFactor` в блок `from ... import (Company, MedicalExamKind, MedicalNorm, ...)` и `PositionHazardLink`:

```python
    Company, MedicalExamKind, MedicalFactor, MedicalNorm, Person, Position,
    PositionHazardLink, PPEIssue, PPEItem,
```

(b) В функции, где сидится demo-`Position` и `_seed_ppe_demo` создаёт `hazard` (`demo_general`), после блока медицинской нормы (~стр.262) добавить factor-seed (идемпотентно):

```python
        # §9.2: seed a 29н factor and map the demo hazard to it, so the demo
        # tenant shows a non-empty контингент/поименный список factor-driven
        # (no manual norm needed for this path).
        if position is not None:
            factor = (await session.execute(select(MedicalFactor).where(
                MedicalFactor.tenant_id == tenant_db_id, MedicalFactor.code == "4.4",
            ))).scalar_one_or_none()
            if factor is None:
                session.add(MedicalFactor(
                    tenant_id=tenant_db_id, code="4.4", name="Шум",
                    category="factor", exam_kinds=[MedicalExamKind.PERIODIC.value],
                    periodicity_months=12,
                ))
            demo_hazard = (await session.execute(select(RiskHazard).where(
                RiskHazard.tenant_id == tenant_db_id, RiskHazard.code == "demo_general",
            ))).scalar_one_or_none()
            if demo_hazard is not None:
                if not demo_hazard.medical_factor_code:
                    demo_hazard.medical_factor_code = "4.4"
                link = (await session.execute(select(PositionHazardLink).where(
                    PositionHazardLink.tenant_id == tenant_db_id,
                    PositionHazardLink.position_id == position.id,
                    PositionHazardLink.hazard_id == demo_hazard.id,
                ))).scalar_one_or_none()
                if link is None:
                    session.add(PositionHazardLink(
                        tenant_id=tenant_db_id, position_id=position.id,
                        hazard_id=demo_hazard.id,
                    ))
```

> **NB порядок:** `_seed_ppe_demo` создаёт `demo_general` hazard. Этот блок должен идти ПОСЛЕ него (hazard уже существует). Если порядок вызовов иной — продублировать lookup-or-create hazard здесь (идемпотентно).

- [ ] **Step 4: Запустить seed-тест + полную медицинскую регрессию**

Run: `python -m pytest backend/tests/test_medical_factor_seed.py -v`
Expected: PASS.

Run: `python -m pytest backend/tests/ tests/api/ -k "medical or contingent or factor" -q`
Expected: PASS — весь медицинский когорт зелёный (Срез-1 parity + §9.2).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/demo_bootstrap.py backend/tests/test_medical_factor_seed.py
git commit -m "feat(medical): demo-seed 29н factor + hazard mapping (factor-driven named list)"
```

---

## Финальная верификация (после всех задач)

- [ ] **Контурный когорт §9.2 + parity Среза-1**

Run: `python -m pytest backend/tests/ tests/api/ -k "medical or contingent or factor" -q`
Expected: PASS, EXIT=0.

- [ ] **Смежная регрессия (mapper, миграции, person_admission)**

Run: `python -m pytest backend/tests/ -k "migration or downgrade or mapper or person_admission or dq_medical or calendar_medical" -q`
Expected: PASS, EXIT=0. (На этой машине — через `.venv`, PowerShell→file; финальные summary добирать EXIT-кодом, [[py313_win_pytest_invocation]].)

- [ ] **Holistic-review** через `superpowers:requesting-code-review` — спек-соответствие секция-в-секцию, 0 Critical/Important.

---

## Self-Review (выполнено автором плана)

**Spec coverage:** §2.1 каталог → Task 1+2; §2.2 движок → Task 3+4; §2.3 документы → Task 5; §3 миграция → Task 2; §4 API → Task 6; §5 seed → Task 7; §6 тесты → распределены по задачам (TDD). Все секции спека покрыты.

**Placeholder scan:** код полный во всех шагах; «NB»-пометки касаются только сверки имён фикстур с репо (`tests/conftest.py`) — это явная инструкция, не placeholder-логика.

**Type consistency:** `FactorTuple=(code,name,exam_kinds,periodicity_months)` единообразен в Task 3/4/5; `_load_factor_catalog` реконструирует enum из JSON-строк; API `create_medical_factor` пишет `exam_kinds` как `.value`-строки (совпадает с `JSON list[str]` модели и `_load_factor_catalog`). Документы возвращают dict-ключи, совпадающие с pydantic-полями `ContingentRegisterRow`/`NamedListRow`.

**Известный риск:** имена тест-фикстур (`sessionmaker`/`data_factory`/`medical_client`/bootstrap) — псевдонимны; исполнитель выравнивает их по `tests/conftest.py` и `tests/api/conftest.py` на Task 4/6/7 (суть тестов от этого не меняется).
