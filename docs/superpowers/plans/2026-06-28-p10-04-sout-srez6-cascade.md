# P10-04 СОУТ срез-6 «Авто-каскад класса в нормы медосмотров» Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** При смене класса РМ admin открывает preview каскада → применяет → мед-нормы должности обновляются (штамп класса СОУТ + добор видов осмотров по 29н); СИЗ остаётся advisory в preview.

**Architecture:** 3-слойное зеркало срезов 4-5: чистый домен `cascade.py` (датаклассы + `build_cascade_plan` + `months_to_interval_days`, без I/O) → сервис `sout_cascade.py` (preview/apply, re-derive из БД, all-or-nothing) → 2 эндпоинта в `routes/sout.py` (preview + apply) → тонкий фронт. Apply пишет ТОЛЬКО в существующие `medical_norm` (колонка `working_conditions_class` уже есть) → **миграции нет**.

**Tech Stack:** Python 3.12 (CI; локально Win + Py3.13.7, venv в КОРНЕ репо `.venv`), FastAPI, SQLAlchemy async, pytest; React/Vite/TS, vitest.

**Спека:** `docs/superpowers/specs/2026-06-28-p10-04-sout-srez6-cascade-design.md`

**Среда запуска тестов (Win):** summary-строка может теряться в PowerShell-буфере — судить по EXIT-коду. Backend: из `backend/` через `../.venv/Scripts/python.exe -m pytest tests/test_X.py -q`. Канон Py3.12 PG CI = финальный гейт.

**Инвариант:** после среза `git diff origin/main...HEAD -- backend/app/migrations/versions/` должен быть ПУСТ.

---

## File Structure

- **Modify** `backend/app/schemas/sout.py` — `CascadeMedicalAction`, `CascadePreview`, `CascadeResult` (`Literal` уже импортирован).
- **Create** `backend/app/domains/sout/cascade.py` — чистый домен: датаклассы плана + `build_cascade_plan` + `months_to_interval_days`.
- **Create** `backend/app/services/sout_cascade.py` — `preview_cascade`/`apply_cascade` + loader общих мед-норм; `to_preview_schema`.
- **Modify** `backend/app/api/routes/sout.py` — эндпоинты `GET /workplaces/{wid}/cascade/preview` + `POST /workplaces/{wid}/cascade/apply`.
- **Modify** `frontend/src/api/sout.ts` — интерфейсы + `previewCascade`/`applyCascade`.
- **Modify** `frontend/src/pages/sout/SoutPage.tsx` — компонент `CascadeSection` рядом с `NormSuggestionsSection`.
- **Create** tests: `backend/tests/test_sout_cascade_domain.py`, `backend/tests/test_sout_cascade_service.py`, `backend/tests/test_sout_cascade_api.py`, `frontend/src/__tests__/SoutCascade.test.tsx`.

---

## Task 1: Схемы каскада

**Files:**
- Modify: `backend/app/schemas/sout.py` (после `NormSuggestions`, строка ~181)
- Test: `backend/tests/test_sout_cascade_domain.py` (только schema-roundtrip часть в этой задаче)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_sout_cascade_domain.py
"""Юниты чистого домена каскада СОУТ (без БД, без async) + схемы."""
from app.schemas.sout import CascadeMedicalAction, CascadePreview, CascadeResult


def test_cascade_schema_roundtrip():
    action = CascadeMedicalAction(
        exam_kind="periodic", op="create", periodicity_months=12,
        interval_days=365, target_class="harmful_3_1", current_class=None,
        factor_codes=["4.1"], reason="x",
    )
    preview = CascadePreview(
        assessed_class="harmful_3_1", can_apply=True, medical=[action], ppe_advisory=[],
    )
    assert preview.medical[0].op == "create"
    assert preview.can_apply is True
    result = CascadeResult(created=1, reclassified=0, conflicts=0, ppe_advisory_count=2)
    assert result.created == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `backend/`): `../.venv/Scripts/python.exe -m pytest tests/test_sout_cascade_domain.py::test_cascade_schema_roundtrip -q`
Expected: FAIL — `ImportError: cannot import name 'CascadeMedicalAction'`.

- [ ] **Step 3: Add the schemas**

In `backend/app/schemas/sout.py`, after the `NormSuggestions` class (~line 181), add:

```python
# --- Class cascade (срез-6) ---
class CascadeMedicalAction(BaseSchema):
    exam_kind: str
    op: Literal["create", "reclass", "conflict"]
    periodicity_months: int
    interval_days: int
    target_class: str
    current_class: str | None = None
    factor_codes: list[str] = []
    reason: str


class CascadePreview(BaseSchema):
    assessed_class: str | None
    can_apply: bool
    medical: list[CascadeMedicalAction] = []
    ppe_advisory: list[PpeNormSuggestion] = []


class CascadeResult(BaseSchema):
    created: int
    reclassified: int
    conflicts: int
    ppe_advisory_count: int
```

- [ ] **Step 4: Run test to verify it passes**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_sout_cascade_domain.py::test_cascade_schema_roundtrip -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/sout.py backend/tests/test_sout_cascade_domain.py
git commit -m "feat(sout): cascade preview/result schemas (срез-6)"
```

---

## Task 2: Чистый домен — build_cascade_plan + months_to_interval_days

**Files:**
- Create: `backend/app/domains/sout/cascade.py`
- Test: `backend/tests/test_sout_cascade_domain.py` (дополняем)

**Контекст для реализатора:**
- `factors` — это `SoutFactor` rows (атрибуты `hazard_id`, `name`, `code`, `measured_class`); в тестах заменяются `SimpleNamespace`.
- `hazard_meta` — `{hazard_id: (title, medical_factor_code)}` (как возвращает `_load_hazard_meta` в `routes/sout.py`).
- `factor_catalog` — итерируемое `FactorTuple = (code, name, exam_kinds: tuple[MedicalExamKind,...], periodicity_months: int)` (29н каталог из `app.domains.medical.service._load_factor_catalog`).
- `existing_med_norms` — `dict[str, str | None]`: `{exam_kind_value: working_conditions_class}` ТОЛЬКО для общих (`hazard_id IS NULL`) норм должности.
- `existing_ppe_pairs` — `set[(position_id, hazard_id)]`.
- Переиспользуем `med_lc.factors_for_hazards` + `med_lc.required_exams_from_factors` (как `build_medical_exam_suggestions`, но БЕЗ skip существующих — каскаду нужны все требуемые kinds для классификации) и `build_ppe_norm_suggestions` (advisory как есть).

- [ ] **Step 1: Write the failing tests**

First, add these imports to the **top** of `backend/tests/test_sout_cascade_domain.py` (below the existing schema imports — keep all imports at file top to avoid E402):

```python
from types import SimpleNamespace

from app.models.models import MedicalExamKind
from app.models.sout import SoutClass
from app.domains.sout.cascade import build_cascade_plan, months_to_interval_days
```

Then append these tests to the file:

```python
def test_months_to_interval_days():
    assert months_to_interval_days(12) == 365   # совпадает с DEFAULT_INTERVAL_DAYS[PERIODIC]
    assert months_to_interval_days(60) == 1825  # PSYCHIATRIC


# Каталог 29н: фактор "4.1" требует periodic каждые 12 мес.
_CATALOG = [("4.1", "Шум", (MedicalExamKind.PERIODIC,), 12)]


def _factor(hid="h1"):
    return SimpleNamespace(hazard_id=hid, name="Шум", code="4.1", measured_class=SoutClass.HARMFUL_3_1)


def test_plan_create_when_no_norm():
    plan = build_cascade_plan(
        assessed_class="harmful_3_1", position_id="p1",
        factors=[_factor()], hazard_meta={"h1": ("Шум", "4.1")},
        factor_catalog=_CATALOG, existing_med_norms={}, existing_ppe_pairs=set(),
    )
    assert [a.op for a in plan.medical] == ["create"]
    assert plan.medical[0].exam_kind == "periodic"
    assert plan.medical[0].interval_days == 365
    assert plan.medical[0].target_class == "harmful_3_1"


def test_plan_reclass_when_class_empty():
    plan = build_cascade_plan(
        assessed_class="harmful_3_1", position_id="p1",
        factors=[_factor()], hazard_meta={"h1": ("Шум", "4.1")},
        factor_catalog=_CATALOG, existing_med_norms={"periodic": None}, existing_ppe_pairs=set(),
    )
    assert [a.op for a in plan.medical] == ["reclass"]


def test_plan_conflict_when_class_differs_nonempty():
    plan = build_cascade_plan(
        assessed_class="harmful_3_1", position_id="p1",
        factors=[_factor()], hazard_meta={"h1": ("Шум", "4.1")},
        factor_catalog=_CATALOG, existing_med_norms={"periodic": "acceptable"}, existing_ppe_pairs=set(),
    )
    assert [a.op for a in plan.medical] == ["conflict"]
    assert plan.medical[0].current_class == "acceptable"


def test_plan_idempotent_when_class_matches():
    plan = build_cascade_plan(
        assessed_class="harmful_3_1", position_id="p1",
        factors=[_factor()], hazard_meta={"h1": ("Шум", "4.1")},
        factor_catalog=_CATALOG, existing_med_norms={"periodic": "harmful_3_1"}, existing_ppe_pairs=set(),
    )
    assert plan.medical == []


def test_plan_empty_when_class_none():
    plan = build_cascade_plan(
        assessed_class=None, position_id="p1",
        factors=[_factor()], hazard_meta={"h1": ("Шум", "4.1")},
        factor_catalog=_CATALOG, existing_med_norms={}, existing_ppe_pairs=set(),
    )
    assert plan.medical == []


def test_plan_ppe_advisory_from_factors():
    plan = build_cascade_plan(
        assessed_class="harmful_3_1", position_id="p1",
        factors=[_factor()], hazard_meta={"h1": ("Шум", "4.1")},
        factor_catalog=_CATALOG, existing_med_norms={}, existing_ppe_pairs=set(),
    )
    assert [a.hazard_id for a in plan.ppe_advisory] == ["h1"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_sout_cascade_domain.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.domains.sout.cascade'`.

- [ ] **Step 3: Implement the domain**

Create `backend/app/domains/sout/cascade.py`:

```python
"""Чистый домен авто-каскада класса СОУТ → план изменений мед-норм (+ совет СИЗ).

Без БД/FastAPI. Caller передаёт уже загруженные строки. Медицинская часть
переиспользует 29н-движок (factors_for_hazards / required_exams_from_factors),
но НЕ пропускает существующие нормы — каскаду нужны все требуемые виды осмотров,
чтобы классифицировать каждое действие как create/reclass/conflict.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal

from app.domains.medical import lifecycle as med_lc
from app.domains.sout.suggestions import build_ppe_norm_suggestions
from app.schemas.sout import PpeNormSuggestion

CascadeOp = Literal["create", "reclass", "conflict"]


@dataclass
class MedicalCascadeAction:
    exam_kind: str
    op: CascadeOp
    periodicity_months: int
    interval_days: int
    target_class: str
    current_class: str | None
    factor_codes: list[str]
    reason: str


@dataclass
class CascadePlan:
    assessed_class: str | None
    medical: list[MedicalCascadeAction] = field(default_factory=list)
    ppe_advisory: list[PpeNormSuggestion] = field(default_factory=list)


def months_to_interval_days(months: int) -> int:
    """29н периодичность (мес) → interval_days. 12→365, 60→1825 (как DEFAULT_INTERVAL_DAYS)."""
    return months * 365 // 12


def build_cascade_plan(
    *,
    assessed_class: str | None,
    position_id: str | None,
    factors: Iterable,
    hazard_meta: dict[str, tuple[str, str | None]],
    factor_catalog: Iterable,
    existing_med_norms: dict[str, str | None],
    existing_ppe_pairs: set[tuple[str, str]],
) -> CascadePlan:
    """Построить план каскада. ``existing_med_norms`` — {exam_kind_value: class|None}
    только для общих (hazard_id IS NULL) норм должности."""
    plan = CascadePlan(assessed_class=assessed_class)
    if assessed_class is None or position_id is None:
        return plan

    hazard_factor_codes = {meta[1] for meta in hazard_meta.values() if meta[1]}
    matched = med_lc.factors_for_hazards(hazard_factor_codes, factor_catalog)
    required = med_lc.required_exams_from_factors(matched)  # {MedicalExamKind: months}

    for kind, months in sorted(required.items(), key=lambda kv: kv[0].value):
        kv = kind.value
        codes = sorted(code for (code, _n, kinds, _m) in matched if kind in kinds)
        interval = months_to_interval_days(int(months))
        if kv not in existing_med_norms:
            op: CascadeOp = "create"
            current: str | None = None
            reason = f"СОУТ класс {assessed_class}: добавить норму осмотра «{kv}» ({int(months)} мес.)"
        else:
            current = existing_med_norms[kv]
            if current in (None, ""):
                op = "reclass"
                reason = f"СОУТ класс {assessed_class}: проставить класс в норме осмотра «{kv}»"
            elif current != assessed_class:
                op = "conflict"
                reason = (
                    f"Норма осмотра «{kv}» имеет класс {current} ≠ СОУТ {assessed_class} "
                    f"— проверьте вручную (apply не перезапишет)"
                )
            else:
                continue  # класс уже совпадает — действие не нужно
        plan.medical.append(
            MedicalCascadeAction(
                exam_kind=kv, op=op, periodicity_months=int(months),
                interval_days=interval, target_class=assessed_class,
                current_class=current, factor_codes=codes, reason=reason,
            )
        )

    hazard_titles = {hid: meta[0] for hid, meta in hazard_meta.items()}
    plan.ppe_advisory = build_ppe_norm_suggestions(
        position_id=position_id, factors=factors,
        hazard_titles=hazard_titles, existing_norm_pairs=existing_ppe_pairs,
    )
    return plan
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_sout_cascade_domain.py -q`
Expected: PASS (all 8 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/sout/cascade.py backend/tests/test_sout_cascade_domain.py
git commit -m "feat(sout): cascade pure domain — plan create/reclass/conflict (срез-6)"
```

---

## Task 3: Сервис — preview_cascade + apply_cascade

**Files:**
- Create: `backend/app/services/sout_cascade.py`
- Test: `backend/tests/test_sout_cascade_service.py`

**Контекст для реализатора:**
- `MedicalNorm` / `MedicalExamKind` / `PPENorm` / `Position` — в `app.models.models`.
- `RiskHazard` — в `app.models.risk`; `SoutWorkplace`/`SoutFactor`/`SoutCampaign` — в `app.models.sout`.
- Каталог 29н: `from app.domains.medical.service import _load_factor_catalog` → `await _load_factor_catalog(session, tenant_id=str(tenant.id))`.
- Кампания открыта: `from app.domains.sout.lifecycle import ensure_campaign_open, CampaignTransitionError`; вызывать `ensure_campaign_open(campaign.status)` (бросает `CampaignTransitionError` → роут вернёт 409).
- Apply пишет общие нормы: create → `hazard_id=None`; reclass → UPDATE строки с `hazard_id IS NULL` для kind.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_sout_cascade_service.py
"""Тесты сервиса каскада СОУТ (in-memory SQLite)."""
import pytest
from sqlalchemy import Column, String, Table, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models.models  # noqa: F401 — регистрирует medical/ppe/position
import app.models.risk  # noqa: F401 — регистрирует risk_hazards
import app.models.sout  # noqa: F401 — регистрирует sout-таблицы
from app.db.session import TenantBase
from app.models.models import Company, MedicalExamKind, MedicalFactor, MedicalNorm, Position
from app.models.risk import RiskHazard
from app.models.sout import SoutCampaign, SoutClass, SoutFactor, SoutWorkplace
from app.services.sout_cascade import apply_cascade, preview_cascade


@pytest.fixture()
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    if "tenant" not in TenantBase.metadata.tables:
        Table("tenant", TenantBase.metadata, Column("id", String(36), primary_key=True))
    async with engine.begin() as conn:
        await conn.run_sync(TenantBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


class _Tenant:
    def __init__(self, tid="tenant-1"):
        self.id = tid


@pytest.fixture()
async def seeded(db_session):
    """Кампания (PLANNED=open) с РМ класса 3.1, должностью, hazard→29н фактор periodic/12мес."""
    t = _Tenant()
    company = Company(tenant_id=t.id, name="ООО Ромашка")
    db_session.add(company)
    await db_session.flush()
    pos = Position(tenant_id=t.id, company_id=company.id, name="Слесарь")
    db_session.add(pos)
    await db_session.flush()
    db_session.add(MedicalFactor(
        tenant_id=t.id, code="4.1", name="Шум", category="factor",
        exam_kinds=["periodic"], periodicity_months=12,
    ))
    haz = RiskHazard(tenant_id=t.id, code="H-4.1", title="Шум", medical_factor_code="4.1")
    db_session.add(haz)
    await db_session.flush()
    c = SoutCampaign(tenant_id=t.id, name="СОУТ 2026")  # default status PLANNED ∈ _OPEN_STATUSES
    db_session.add(c)
    await db_session.flush()
    wp = SoutWorkplace(
        tenant_id=t.id, campaign_id=c.id, workplace_code="РМ-01",
        position_name="Слесарь", position_id=pos.id, assessed_class=SoutClass.HARMFUL_3_1,
    )
    db_session.add(wp)
    await db_session.flush()
    db_session.add(SoutFactor(
        tenant_id=t.id, workplace_id=wp.id, name="Шум", code="4.1",
        hazard_id=haz.id, measured_class=SoutClass.HARMFUL_3_1,
    ))
    await db_session.flush()
    return t, c, wp, pos


@pytest.mark.asyncio
async def test_preview_proposes_create(db_session, seeded):
    t, c, wp, pos = seeded
    preview = await preview_cascade(db_session, _Tenant(), wp.id)
    assert preview is not None
    assert preview.assessed_class == "harmful_3_1"
    assert [a.op for a in preview.medical] == ["create"]
    assert preview.can_apply is True


@pytest.mark.asyncio
async def test_preview_none_when_workplace_missing(db_session, seeded):
    preview = await preview_cascade(db_session, _Tenant(), "no-such-id")
    assert preview is None


@pytest.mark.asyncio
async def test_apply_creates_medical_norm_with_class(db_session, seeded):
    t, c, wp, pos = seeded
    result = await apply_cascade(db_session, _Tenant(), wp.id)
    assert result is not None
    assert result.created == 1
    norms = list((await db_session.execute(
        select(MedicalNorm).where(MedicalNorm.position_id == pos.id)
    )).scalars().all())
    assert len(norms) == 1
    assert norms[0].exam_kind == MedicalExamKind.PERIODIC
    assert norms[0].working_conditions_class == "harmful_3_1"
    assert norms[0].hazard_id is None
    assert norms[0].interval_days == 365


@pytest.mark.asyncio
async def test_apply_is_idempotent(db_session, seeded):
    t, c, wp, pos = seeded
    await apply_cascade(db_session, _Tenant(), wp.id)
    second = await apply_cascade(db_session, _Tenant(), wp.id)
    assert second.created == 0 and second.reclassified == 0


@pytest.mark.asyncio
async def test_apply_reclass_only_when_empty(db_session, seeded):
    t, c, wp, pos = seeded
    db_session.add(MedicalNorm(
        tenant_id=t.id, position_id=pos.id, exam_kind=MedicalExamKind.PERIODIC,
        hazard_id=None, interval_days=365, working_conditions_class=None,
    ))
    await db_session.flush()
    result = await apply_cascade(db_session, _Tenant(), wp.id)
    assert result.reclassified == 1 and result.created == 0
    norm = (await db_session.execute(
        select(MedicalNorm).where(MedicalNorm.position_id == pos.id)
    )).scalar_one()
    assert norm.working_conditions_class == "harmful_3_1"


@pytest.mark.asyncio
async def test_apply_conflict_not_overwritten(db_session, seeded):
    t, c, wp, pos = seeded
    db_session.add(MedicalNorm(
        tenant_id=t.id, position_id=pos.id, exam_kind=MedicalExamKind.PERIODIC,
        hazard_id=None, interval_days=365, working_conditions_class="acceptable",
    ))
    await db_session.flush()
    result = await apply_cascade(db_session, _Tenant(), wp.id)
    assert result.conflicts == 1 and result.created == 0 and result.reclassified == 0
    norm = (await db_session.execute(
        select(MedicalNorm).where(MedicalNorm.position_id == pos.id)
    )).scalar_one()
    assert norm.working_conditions_class == "acceptable"  # не перезаписан
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_sout_cascade_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.sout_cascade'`.

- [ ] **Step 3: Implement the service**

Create `backend/app/services/sout_cascade.py`:

```python
"""Сервис авто-каскада класса СОУТ → запись мед-норм (preview/apply).

Пишет ТОЛЬКО в существующую medical_norm (колонка working_conditions_class уже
есть) → миграции нет. apply повторно выводит план из БД (не доверяет клиенту) →
идемпотентность. Работает только с общими (hazard_id IS NULL) нормами должности.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.medical.service import _load_factor_catalog
from app.domains.sout import cascade as casc
from app.domains.sout.lifecycle import CampaignTransitionError, ensure_campaign_open
from app.models.models import MedicalExamKind, MedicalNorm, PPENorm, Position  # noqa: F401
from app.models.risk import RiskHazard
from app.models.sout import SoutCampaign, SoutFactor, SoutWorkplace
from app.models.tenanting import Tenant
from app.schemas.sout import CascadeMedicalAction, CascadePreview, CascadeResult


def _raw_class(value) -> str | None:
    return value.value if value is not None else None


async def _load_workplace(session: AsyncSession, tenant: Tenant, wid: str) -> SoutWorkplace | None:
    return (
        await session.execute(
            select(SoutWorkplace).where(
                SoutWorkplace.id == wid,
                SoutWorkplace.tenant_id == tenant.id,
                SoutWorkplace.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def _load_factors(session: AsyncSession, tenant: Tenant, wid: str):
    return list(
        (
            await session.execute(
                select(SoutFactor).where(
                    SoutFactor.workplace_id == wid, SoutFactor.tenant_id == tenant.id
                )
            )
        ).scalars().all()
    )


async def _load_hazard_meta(session: AsyncSession, tenant: Tenant, hazard_ids):
    if not hazard_ids:
        return {}
    rows = (
        await session.execute(
            select(RiskHazard.id, RiskHazard.title, RiskHazard.medical_factor_code).where(
                RiskHazard.id.in_(hazard_ids), RiskHazard.tenant_id == tenant.id
            )
        )
    ).all()
    return {r[0]: (r[1], r[2]) for r in rows}


async def _load_general_med_norms(session: AsyncSession, tenant: Tenant, position_id: str):
    """{exam_kind_value: working_conditions_class} для общих (hazard_id IS NULL) норм."""
    rows = (
        await session.execute(
            select(MedicalNorm.exam_kind, MedicalNorm.working_conditions_class).where(
                MedicalNorm.tenant_id == tenant.id,
                MedicalNorm.position_id == position_id,
                MedicalNorm.hazard_id.is_(None),
            )
        )
    ).all()
    return {r[0].value: r[1] for r in rows}


async def _load_ppe_pairs(session: AsyncSession, tenant: Tenant, position_id: str):
    rows = (
        await session.execute(
            select(PPENorm.position_id, PPENorm.hazard_id).where(
                PPENorm.tenant_id == tenant.id, PPENorm.position_id == position_id
            )
        )
    ).all()
    return {(r[0], r[1]) for r in rows}


async def _build_plan(session: AsyncSession, tenant: Tenant, wp: SoutWorkplace) -> casc.CascadePlan:
    assessed = _raw_class(wp.assessed_class)
    if wp.position_id is None:
        return casc.CascadePlan(assessed_class=assessed)
    factors = await _load_factors(session, tenant, wp.id)
    hazard_ids = {f.hazard_id for f in factors if f.hazard_id is not None}
    hazard_meta = await _load_hazard_meta(session, tenant, hazard_ids)
    catalog = await _load_factor_catalog(session, tenant_id=str(tenant.id))
    existing_med = await _load_general_med_norms(session, tenant, wp.position_id)
    ppe_pairs = await _load_ppe_pairs(session, tenant, wp.position_id)
    return casc.build_cascade_plan(
        assessed_class=assessed, position_id=wp.position_id, factors=factors,
        hazard_meta=hazard_meta, factor_catalog=catalog,
        existing_med_norms=existing_med, existing_ppe_pairs=ppe_pairs,
    )


def _to_preview(plan: casc.CascadePlan) -> CascadePreview:
    medical = [
        CascadeMedicalAction(
            exam_kind=a.exam_kind, op=a.op, periodicity_months=a.periodicity_months,
            interval_days=a.interval_days, target_class=a.target_class,
            current_class=a.current_class, factor_codes=a.factor_codes, reason=a.reason,
        )
        for a in plan.medical
    ]
    can_apply = any(a.op in ("create", "reclass") for a in plan.medical)
    # plan.ppe_advisory items are already PpeNormSuggestion (pydantic) instances —
    # build_ppe_norm_suggestions returns the schema directly.
    return CascadePreview(
        assessed_class=plan.assessed_class, can_apply=can_apply,
        medical=medical, ppe_advisory=list(plan.ppe_advisory),
    )


async def preview_cascade(
    session: AsyncSession, tenant: Tenant, wid: str
) -> CascadePreview | None:
    wp = await _load_workplace(session, tenant, wid)
    if wp is None:
        return None
    plan = await _build_plan(session, tenant, wp)
    return _to_preview(plan)


async def apply_cascade(
    session: AsyncSession, tenant: Tenant, wid: str
) -> CascadeResult | None:
    """Применить каскад. Бросает CampaignTransitionError если кампания закрыта."""
    wp = await _load_workplace(session, tenant, wid)
    if wp is None:
        return None
    campaign = (
        await session.execute(
            select(SoutCampaign).where(
                SoutCampaign.id == wp.campaign_id, SoutCampaign.tenant_id == tenant.id
            )
        )
    ).scalar_one_or_none()
    if campaign is None:
        return None
    ensure_campaign_open(campaign.status)  # CampaignTransitionError → 409 в роуте

    plan = await _build_plan(session, tenant, wp)
    created = reclassified = conflicts = 0
    for action in plan.medical:
        if action.op == "create":
            session.add(
                MedicalNorm(
                    tenant_id=tenant.id, position_id=wp.position_id,
                    exam_kind=MedicalExamKind(action.exam_kind), hazard_id=None,
                    interval_days=action.interval_days,
                    working_conditions_class=action.target_class,
                )
            )
            created += 1
        elif action.op == "reclass":
            norm = (
                await session.execute(
                    select(MedicalNorm).where(
                        MedicalNorm.tenant_id == tenant.id,
                        MedicalNorm.position_id == wp.position_id,
                        MedicalNorm.hazard_id.is_(None),
                        MedicalNorm.exam_kind == MedicalExamKind(action.exam_kind),
                    )
                )
            ).scalar_one_or_none()
            if norm is not None and norm.working_conditions_class in (None, ""):
                norm.working_conditions_class = action.target_class
                reclassified += 1
        elif action.op == "conflict":
            conflicts += 1
    await session.flush()
    return CascadeResult(
        created=created, reclassified=reclassified, conflicts=conflicts,
        ppe_advisory_count=len(plan.ppe_advisory),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_sout_cascade_service.py -q`
Expected: PASS (all 6 tests). Default `SoutCampaignStatus.PLANNED` is in `_OPEN_STATUSES`, so `ensure_campaign_open` passes for the seeded campaign.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/sout_cascade.py backend/tests/test_sout_cascade_service.py
git commit -m "feat(sout): cascade service — preview/apply medical norms (срез-6)"
```

---

## Task 4: Эндпоинты preview + apply

**Files:**
- Modify: `backend/app/api/routes/sout.py` (импорты ~строки 28-67; новый блок после `get_norm_suggestions`, ~строка 567)
- Test: `backend/tests/test_sout_cascade_api.py`

**Контекст для реализатора:** API-тесты СОУТ в этом репо **не** используют httpx-клиент —
они вызывают route-функции напрямую и monkeypatch'ат зависимости (см. донор
`backend/tests/test_sout_import_api.py`). `_require_sout_enabled` патчится `AsyncMock()`,
сервис-функции (`preview_cascade`/`apply_cascade`) патчатся на модуле `routes`, `access=None`.
HTTPException достаётся как `getattr(exc.value, "status_code", None)`. Существующие хелперы в
`routes/sout.py`: `_require_sout_enabled`, `_get_workplace`, `_conflict(exc)`, `_not_found`,
`TenantContextValidator`. `CampaignTransitionError` уже импортирован (строка 23). Audit-декоратор:
найдите существующий `@audit_operation(...)` в файле и повторите его форму для apply.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_sout_cascade_api.py
"""API-контракт каскада СОУТ (monkeypatch + прямой вызов route-функций, как test_sout_import_api.py)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.api.routes.sout as routes
from app.domains.sout.lifecycle import CampaignTransitionError
from app.schemas.sout import CascadePreview, CascadeResult


def _tenant():
    return SimpleNamespace(id="tenant-1", is_active=True, slug="t1", name="ООО Ромашка")


@pytest.mark.asyncio
async def test_preview_ok(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "preview_cascade", AsyncMock(return_value=CascadePreview(
        assessed_class="harmful_3_1", can_apply=True, medical=[], ppe_advisory=[],
    )))
    out = await routes.cascade_preview(wid="w1", tenant=_tenant(), session=AsyncMock(), access=None)
    assert out.assessed_class == "harmful_3_1"


@pytest.mark.asyncio
async def test_preview_404_when_workplace_missing(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "preview_cascade", AsyncMock(return_value=None))
    with pytest.raises(Exception) as exc:
        await routes.cascade_preview(wid="nope", tenant=_tenant(), session=AsyncMock(), access=None)
    assert getattr(exc.value, "status_code", None) == 404


@pytest.mark.asyncio
async def test_apply_ok(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "apply_cascade", AsyncMock(return_value=CascadeResult(
        created=1, reclassified=0, conflicts=0, ppe_advisory_count=2,
    )))
    out = await routes.cascade_apply(wid="w1", tenant=_tenant(), session=AsyncMock(), access=None)
    assert out.created == 1 and out.ppe_advisory_count == 2


@pytest.mark.asyncio
async def test_apply_404_when_workplace_missing(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "apply_cascade", AsyncMock(return_value=None))
    with pytest.raises(Exception) as exc:
        await routes.cascade_apply(wid="nope", tenant=_tenant(), session=AsyncMock(), access=None)
    assert getattr(exc.value, "status_code", None) == 404


@pytest.mark.asyncio
async def test_apply_409_when_campaign_closed(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "apply_cascade", AsyncMock(
        side_effect=CampaignTransitionError("Campaign roster is editable only while planned/in_progress")
    ))
    with pytest.raises(Exception) as exc:
        await routes.cascade_apply(wid="w1", tenant=_tenant(), session=AsyncMock(), access=None)
    assert getattr(exc.value, "status_code", None) == 409
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_sout_cascade_api.py -q`
Expected: FAIL — `AttributeError: module 'app.api.routes.sout' has no attribute 'cascade_preview'`.

- [ ] **Step 3: Add imports**

In `backend/app/api/routes/sout.py`, extend the existing service-import block (near the `sout_import` import, ~line 49) with:

```python
from app.services.sout_cascade import apply_cascade, preview_cascade
```

And extend the schema import block (where `NormSuggestions` is imported, ~line 81) with:

```python
    CascadePreview,
    CascadeResult,
```

- [ ] **Step 4: Add the endpoints**

In `backend/app/api/routes/sout.py`, after `get_norm_suggestions` (ends ~line 567), add:

```python
@router.get("/workplaces/{wid}/cascade/preview", response_model=CascadePreview)
async def cascade_preview(
    wid: str, tenant: TenantDep, session: SessionDep, access: Access
) -> CascadePreview:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    preview = await preview_cascade(session, tenant, wid)
    if preview is None:
        raise _not_found("Workplace")
    return preview


@router.post("/workplaces/{wid}/cascade/apply", response_model=CascadeResult)
async def cascade_apply(
    wid: str, tenant: TenantDep, session: SessionDep, access: Access
) -> CascadeResult:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    try:
        result = await apply_cascade(session, tenant, wid)
    except CampaignTransitionError as exc:
        raise _conflict(exc)
    if result is None:
        raise _not_found("Workplace")
    return result
```

> **Реализатор:** если соседние мутационные роуты в этом файле помечены `@audit_operation(...)`, добавьте такой же декоратор к `cascade_apply` по образцу (имя операции — `"update"`, сущность — `"sout_cascade"` или ближайший существующий паттерн).

- [ ] **Step 5: Run tests to verify they pass**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_sout_cascade_api.py -q`
Expected: PASS (all 5).

- [ ] **Step 6: Run the full СОУТ backend cohort**

Run: `../.venv/Scripts/python.exe -m pytest tests/ -q -k sout`
Expected: EXIT 0 (no regressions across sout domain/service/api/import/declaration/print).

- [ ] **Step 7: Verify migration invariant**

Run: `git diff origin/main...HEAD -- backend/app/migrations/versions/`
Expected: EMPTY output.

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/routes/sout.py backend/tests/test_sout_cascade_api.py
git commit -m "feat(sout): cascade preview/apply endpoints (срез-6)"
```

---

## Task 5: Фронт API — интерфейсы + методы

**Files:**
- Modify: `frontend/src/api/sout.ts` (интерфейсы после `NormSuggestions` ~строка 105; методы в `soutApi` после `getNormSuggestions` ~строка 201)

- [ ] **Step 1: Add interfaces**

In `frontend/src/api/sout.ts`, after the `NormSuggestions` interface (~line 105), add:

```typescript
export interface CascadeMedicalAction {
  exam_kind: string;
  op: "create" | "reclass" | "conflict";
  periodicity_months: number;
  interval_days: number;
  target_class: string;
  current_class: string | null;
  factor_codes: string[];
  reason: string;
}

export interface CascadePreview {
  assessed_class: string | null;
  can_apply: boolean;
  medical: CascadeMedicalAction[];
  ppe_advisory: PpeNormSuggestion[];
}

export interface CascadeResult {
  created: number;
  reclassified: number;
  conflicts: number;
  ppe_advisory_count: number;
}
```

- [ ] **Step 2: Add methods**

In the `soutApi` object, after `getNormSuggestions` (~line 201), add:

```typescript
  async previewCascade(workplaceId: string): Promise<CascadePreview> {
    return (await apiClient.get<CascadePreview>(`${base}/workplaces/${workplaceId}/cascade/preview`)).data;
  },

  async applyCascade(workplaceId: string): Promise<CascadeResult> {
    return (await apiClient.post<CascadeResult>(`${base}/workplaces/${workplaceId}/cascade/apply`)).data;
  },
```

- [ ] **Step 3: Typecheck**

Run: `npm --prefix frontend run typecheck`
Expected: EXIT 0.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/sout.ts
git commit -m "feat(sout): cascade api client methods (срез-6)"
```

---

## Task 6: Фронт UI — CascadeSection + vitest

**Files:**
- Modify: `frontend/src/pages/sout/SoutPage.tsx` (новый компонент после `NormSuggestionsSection` ~строка 269; рендер в строке РМ рядом с `<NormSuggestionsSection ... />` ~строка 605)
- Test: `frontend/src/__tests__/SoutCascade.test.tsx`

**Контекст для реализатора:** компонент-донор — `NormSuggestionsSection` (строки 189-269): тот же стиль toggle/loading/error, импорты `ApiError`, `ErrorState`, `LoadingScreen`, `soutApi`, `useState` уже в файле.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/SoutCascade.test.tsx
import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { CascadeSection } from "../pages/sout/SoutPage";
import { soutApi } from "../api/sout";

vi.mock("../api/sout", async (orig) => {
  const actual = await orig<typeof import("../api/sout")>();
  return { ...actual, soutApi: { ...actual.soutApi, previewCascade: vi.fn(), applyCascade: vi.fn() } };
});

describe("CascadeSection", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads preview and applies", async () => {
    (soutApi.previewCascade as ReturnType<typeof vi.fn>).mockResolvedValue({
      assessed_class: "harmful_3_1", can_apply: true,
      medical: [{ exam_kind: "periodic", op: "create", periodicity_months: 12, interval_days: 365,
        target_class: "harmful_3_1", current_class: null, factor_codes: ["4.1"], reason: "r" }],
      ppe_advisory: [],
    });
    (soutApi.applyCascade as ReturnType<typeof vi.fn>).mockResolvedValue({
      created: 1, reclassified: 0, conflicts: 0, ppe_advisory_count: 0 });

    render(<CascadeSection workplaceId="w1" />);
    fireEvent.click(screen.getByRole("button", { name: /каскад/i }));
    await waitFor(() => expect(soutApi.previewCascade).toHaveBeenCalledWith("w1"));
    await screen.findByText(/periodic/i);

    fireEvent.click(screen.getByRole("button", { name: /применить/i }));
    await waitFor(() => expect(soutApi.applyCascade).toHaveBeenCalledWith("w1"));
  });

  it("disables apply when plan is empty", async () => {
    (soutApi.previewCascade as ReturnType<typeof vi.fn>).mockResolvedValue({
      assessed_class: "acceptable", can_apply: false, medical: [], ppe_advisory: [] });
    render(<CascadeSection workplaceId="w2" />);
    fireEvent.click(screen.getByRole("button", { name: /каскад/i }));
    await waitFor(() => expect(soutApi.previewCascade).toHaveBeenCalled());
    const applyBtn = await screen.findByRole("button", { name: /применить/i });
    expect(applyBtn).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- SoutCascade`
Expected: FAIL — `CascadeSection` is not exported.

- [ ] **Step 3: Implement and export CascadeSection**

In `frontend/src/pages/sout/SoutPage.tsx`, after `NormSuggestionsSection` (~line 269), add (and ensure the `import` line for `soutApi` types includes the new `CascadePreview` type — extend the existing `import { ... type NormSuggestions as NormSuggestionsData } from "../../api/sout"` block):

```tsx
interface CascadeSectionProps {
  workplaceId: string;
}

export const CascadeSection = ({ workplaceId }: CascadeSectionProps) => {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [data, setData] = useState<CascadePreviewData | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const loadPreview = async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await soutApi.previewCascade(workplaceId));
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось загрузить каскад" });
    } finally {
      setLoading(false);
    }
  };

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && data === null && !loading) await loadPreview();
  };

  const apply = async () => {
    if (applying) return;
    setApplying(true);
    setError(null);
    try {
      const res = await soutApi.applyCascade(workplaceId);
      setDone(`Создано: ${res.created}, переклассифицировано: ${res.reclassified}, конфликтов: ${res.conflicts}`);
      await loadPreview();
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось применить каскад" });
    } finally {
      setApplying(false);
    }
  };

  const opLabel = (op: string) =>
    op === "create" ? "создать" : op === "reclass" ? "проставить класс" : "конфликт";

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => void toggle()}
        className="text-xs text-muted-foreground underline-offset-2 hover:underline"
      >
        {open ? "Скрыть каскад в нормы" : "Каскад в нормы"}
      </button>
      {open ? (
        <div className="space-y-2">
          <ErrorState error={error ?? undefined} onRetry={() => void loadPreview()} />
          {loading ? <LoadingScreen label="Загрузка каскада" /> : null}
          {!loading && !error && data !== null ? (
            <div className="space-y-2">
              <p className="text-xs text-muted-foreground">
                Класс СОУТ: <span className="font-medium">{data.assessed_class ?? "—"}</span>
              </p>
              {data.medical.length > 0 ? (
                <ul className="space-y-1 text-xs">
                  {data.medical.map((m) => (
                    <li key={`casc-${m.exam_kind}`} className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{m.exam_kind}</span>
                      <span className="rounded bg-muted px-1">{opLabel(m.op)}</span>
                      <span className="text-muted-foreground">{m.reason}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-muted-foreground">Изменений мед-норм нет.</p>
              )}
              {data.ppe_advisory.length > 0 ? (
                <p className="text-xs italic text-muted-foreground">
                  СИЗ: {data.ppe_advisory.length} вредных фактор(ов) без норм — заведите вручную.
                </p>
              ) : null}
              <button
                type="button"
                onClick={() => void apply()}
                disabled={!data.can_apply || applying}
                className="rounded border px-2 py-1 text-xs disabled:opacity-50"
              >
                {applying ? "Применение…" : "Применить"}
              </button>
              {done ? <p className="text-xs text-emerald-600">{done}</p> : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
};
```

Add the type import to the existing `../../api/sout` import block at the top of the file:

```tsx
  type CascadePreview as CascadePreviewData,
```

- [ ] **Step 4: Render CascadeSection in the workplace row**

Near `<NormSuggestionsSection workplaceId={workplace.id} />` (~line 605), add directly after it:

```tsx
                <CascadeSection workplaceId={workplace.id} />
```

- [ ] **Step 5: Run test to verify it passes**

Run: `npm --prefix frontend run test -- SoutCascade`
Expected: PASS (2 tests).

- [ ] **Step 6: Frontend gates**

Run:
```bash
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
```
Expected: all EXIT 0 (1 pre-existing exhaustive-deps lint warning on report-load effect is acceptable; no new errors).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/sout/SoutPage.tsx frontend/src/__tests__/SoutCascade.test.tsx
git commit -m "feat(sout): cascade UI section per workplace (срез-6)"
```

---

## Final verification

- [ ] **Backend СОУТ cohort green:** `cd backend && ../.venv/Scripts/python.exe -m pytest tests/ -q -k sout` → EXIT 0.
- [ ] **Migration invariant:** `git diff origin/main...HEAD -- backend/app/migrations/versions/` → EMPTY.
- [ ] **Frontend gates:** typecheck + test + build all EXIT 0.
- [ ] **Handoff:** prepend a new block to `AI_IMPLEMENTATION_REPORT.md` (mirror prior срез handoffs: branch, что построено, дивиденд-без-миграции доказан, тесты, осознанно отклонено, Next). Commit `docs: handoff for СОУТ срез-6 авто-каскад`.
- [ ] Branch `feat/sout-srez6-cascade-p10-04` ready; merge/PR is the user's call (base = main).

---

## Notes / gotchas

- **Campaign open status:** `ensure_campaign_open` accepts only the "open"/draft status(es) defined in `app/domains/sout/lifecycle.py`. In the service seed fixture, confirm the campaign's default status passes `ensure_campaign_open`; for the closed-campaign API test, set the campaign to a completed/closed status.
- **`_load_factor_catalog` is private** but already imported and used in `routes/sout.py` (line 27) — reusing it in the service is consistent with the срез-3 precedent.
- **PPENorm advisory only:** apply NEVER writes PPENorm — it only counts `len(plan.ppe_advisory)`.
- **General norms only:** cascade reads/writes `MedicalNorm` rows with `hazard_id IS NULL`. Hazard-specific norms are out of scope (and untouched).
- **Idempotency:** apply re-derives the plan from the DB; a second apply yields `created=0, reclassified=0` because created/reclassed kinds now match.
