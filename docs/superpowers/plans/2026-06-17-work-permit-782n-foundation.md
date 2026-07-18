# Наряд-допуск на высоте (782н) — Ф1 «модель + экран» — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Расширить модель наряда-допуска описательными полями официальной формы 782н и дать admin-экран (список + карточка) для ведения наряда по форме.

**Architecture:** Full-stack, аддитивно. Backend: миграция `wp02` добавляет 8 колонок в `work_permit`; словарь систем безопасности — чистый хелпер в `lifecycle.py`; схемы/сервис/роуты прокидывают новые поля (контракт действий/гейта не меняется). Frontend: api-модуль + `useAsyncResource` (без стора, как экран личных допусков Л1); список `/work-permits` и карточка `/work-permits/:id` на готовых компонентах (`RegistryTable`, `Dialog`, `Can`).

**Tech Stack:** Python/FastAPI/SQLAlchemy/Alembic (backend); React/Vite/TypeScript, react-hook-form + zod, axios (`apiClient`), vitest + @testing-library/react (frontend).

**Spec:** `docs/superpowers/specs/2026-06-17-work-permit-782n-foundation-design.md`

**Branch:** `feat/work-permits-782n` (уже создана от `main`).

**Тесты (среда):** канон Py3.12.12 = CI. Локально может быть другая версия — прогонять доступным Python, отметить расхождение (CLAUDE.md). Не запускать `make cs:test`. Точечные вызовы pytest. Frontend: `npm --prefix frontend run test -- <file>` и `tsc`/`build`.

---

## Часть A — Backend

### Task 1: Словарь систем безопасности (lifecycle)

**Files:**
- Modify: `backend/app/domains/work_permits/lifecycle.py`
- Test: `backend/tests/test_work_permit_lifecycle.py`

- [ ] **Step 1: Написать падающий тест**

Добавить в `backend/tests/test_work_permit_lifecycle.py`:

```python
def test_safety_system_vocabulary():
    from app.domains.work_permits import lifecycle as lc

    assert lc.is_safety_system("fall_arrest") is True
    assert lc.is_safety_system("restraint") is True
    assert lc.is_safety_system("nonsense") is False
    assert lc.SAFETY_SYSTEMS == frozenset(
        {"restraint", "positioning", "fall_arrest", "rescue_evacuation", "access"}
    )
```

- [ ] **Step 2: Прогнать тест — должен упасть**

Run: `python -m pytest backend/tests/test_work_permit_lifecycle.py::test_safety_system_vocabulary -v`
Expected: FAIL (`AttributeError: module ... has no attribute 'SAFETY_SYSTEMS'`).

- [ ] **Step 3: Реализовать**

В `backend/app/domains/work_permits/lifecycle.py` после блока `EVENT_TYPES` добавить:

```python
# системы обеспечения безопасности работ на высоте (782н):
# удерживающие / позиционирования / страховочные / для эвакуации и спасения /
# для подъёма и спуска (доступа)
SAFETY_SYSTEMS = frozenset({
    "restraint", "positioning", "fall_arrest", "rescue_evacuation", "access",
})
```

И рядом с `is_work_type` / `is_member_role` добавить:

```python
def is_safety_system(value: str) -> bool:
    return value in SAFETY_SYSTEMS
```

- [ ] **Step 4: Прогнать тест — должен пройти**

Run: `python -m pytest backend/tests/test_work_permit_lifecycle.py::test_safety_system_vocabulary -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/work_permits/lifecycle.py backend/tests/test_work_permit_lifecycle.py
git commit -m "feat(work-permits): safety-systems vocabulary (782н)"
```

---

### Task 2: Миграция wp02 — 8 колонок 782н

**Files:**
- Create: `backend/app/migrations/versions/20260617_wp02_work_permit_782n_fields.py`
- Test: `backend/tests/test_wp02_work_permit_782n_migration.py`

- [ ] **Step 1: Подтвердить head перед написанием**

Run: `python -m alembic -c backend/alembic.ini heads`
Ожидание: среди heads есть `20260616_wp01_work_permit_tables`. `down_revision` миграции = именно эта ревизия. Если wp01 уже не head (кто-то нарастил цепочку) — взять актуальный потомок wp01 как `down_revision` и отразить в guard-тесте.

- [ ] **Step 2: Написать падающий тест (guard)**

Create `backend/tests/test_wp02_work_permit_782n_migration.py`:

```python
"""Guard: wp02 chains from wp01 and adds exactly the 782н columns (additive)."""
import importlib.util
from pathlib import Path

MIG = (
    Path(__file__).resolve().parents[1]
    / "app/migrations/versions/20260617_wp02_work_permit_782n_fields.py"
)

NEW_COLUMNS = {
    "subdivision_text", "content_text", "conditions_text", "safety_systems",
    "measures_before_text", "measures_during_text", "special_conditions_text", "ppe_text",
}


def _load():
    spec = importlib.util.spec_from_file_location("wp02_mig", MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_wp02_chain_and_revision():
    mod = _load()
    assert mod.revision == "20260617_wp02_work_permit_782n_fields"
    assert mod.down_revision == "20260616_wp01_work_permit_tables"


def test_wp02_source_adds_and_drops_all_columns():
    src = MIG.read_text(encoding="utf-8")
    for col in NEW_COLUMNS:
        assert f'add_column("work_permit"' in src or "add_column(\n" in src  # additive present
        assert f'"{col}"' in src, f"missing column literal: {col}"
        assert f'drop_column("work_permit", "{col}")' in src, f"downgrade missing: {col}"
```

- [ ] **Step 3: Прогнать тест — должен упасть**

Run: `python -m pytest backend/tests/test_wp02_work_permit_782n_migration.py -v`
Expected: FAIL (файла миграции ещё нет → ошибка загрузки).

- [ ] **Step 4: Написать миграцию**

Create `backend/app/migrations/versions/20260617_wp02_work_permit_782n_fields.py`:

```python
"""wp02: descriptive 782н fields on work_permit (additive).

8 nullable columns for the official «работа на высоте» form sections.
VARCHAR/TEXT/JSON, no native enums. Table name LITERAL (AST-audit blindspot).
Honest downgrade drops exactly the added columns.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260617_wp02_work_permit_782n_fields"
down_revision = "20260616_wp01_work_permit_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("work_permit", sa.Column("subdivision_text", sa.String(length=255), nullable=True))
    op.add_column("work_permit", sa.Column("content_text", sa.Text(), nullable=True))
    op.add_column("work_permit", sa.Column("conditions_text", sa.Text(), nullable=True))
    op.add_column("work_permit", sa.Column("safety_systems", sa.JSON(), nullable=True))
    op.add_column("work_permit", sa.Column("measures_before_text", sa.Text(), nullable=True))
    op.add_column("work_permit", sa.Column("measures_during_text", sa.Text(), nullable=True))
    op.add_column("work_permit", sa.Column("special_conditions_text", sa.Text(), nullable=True))
    op.add_column("work_permit", sa.Column("ppe_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("work_permit", "ppe_text")
    op.drop_column("work_permit", "special_conditions_text")
    op.drop_column("work_permit", "measures_during_text")
    op.drop_column("work_permit", "measures_before_text")
    op.drop_column("work_permit", "safety_systems")
    op.drop_column("work_permit", "conditions_text")
    op.drop_column("work_permit", "content_text")
    op.drop_column("work_permit", "subdivision_text")
```

- [ ] **Step 5: Прогнать тест — должен пройти**

Run: `python -m pytest backend/tests/test_wp02_work_permit_782n_migration.py -v`
Expected: PASS.

- [ ] **Step 6: Применить миграцию на тестовой БД (round-trip)**

Run: `python -m alembic -c backend/alembic.ini upgrade head && python -m alembic -c backend/alembic.ini downgrade -1 && python -m alembic -c backend/alembic.ini upgrade head`
Expected: без ошибок (upgrade → downgrade на один шаг → upgrade снова).

- [ ] **Step 7: Commit**

```bash
git add backend/app/migrations/versions/20260617_wp02_work_permit_782n_fields.py backend/tests/test_wp02_work_permit_782n_migration.py
git commit -m "feat(work-permits): wp02 migration — 782н descriptive fields"
```

---

### Task 3: Колонки модели WorkPermit

**Files:**
- Modify: `backend/app/models/work_permit.py`
- Test: `backend/tests/test_wp02_work_permit_782n_migration.py` (добавить shape-тест модели)

- [ ] **Step 1: Написать падающий тест**

Добавить в `backend/tests/test_wp02_work_permit_782n_migration.py`:

```python
def test_model_has_782n_columns():
    from app.models.work_permit import WorkPermit

    cols = set(WorkPermit.__table__.columns.keys())
    assert NEW_COLUMNS.issubset(cols)
```

- [ ] **Step 2: Прогнать тест — должен упасть**

Run: `python -m pytest backend/tests/test_wp02_work_permit_782n_migration.py::test_model_has_782n_columns -v`
Expected: FAIL (колонок в модели нет).

- [ ] **Step 3: Реализовать**

В `backend/app/models/work_permit.py` заменить строку импорта sqlalchemy на (добавлен `JSON`):

```python
from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint, func
```

И в классе `WorkPermit` после `measures_text` добавить:

```python
    # секции официальной формы 782н (Ф1)
    subdivision_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    conditions_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    safety_systems: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    measures_before_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    measures_during_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    special_conditions_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ppe_text: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 4: Прогнать тест — должен пройти**

Run: `python -m pytest backend/tests/test_wp02_work_permit_782n_migration.py -v`
Expected: PASS (все тесты файла).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/work_permit.py backend/tests/test_wp02_work_permit_782n_migration.py
git commit -m "feat(work-permits): WorkPermit model — 782н columns"
```

---

### Task 4: Схемы + валидатор safety_systems

**Files:**
- Modify: `backend/app/schemas/work_permit.py`
- Test: `backend/tests/test_work_permit_schemas_782n.py`

- [ ] **Step 1: Написать падающий тест**

Create `backend/tests/test_work_permit_schemas_782n.py`:

```python
import pytest
from pydantic import ValidationError

from app.schemas.work_permit import WorkPermitCreate


def test_create_accepts_782n_fields():
    payload = WorkPermitCreate(
        work_type="height", zone_text="фасад, ось 3-5",
        subdivision_text="Цех №2", content_text="монтаж ограждения",
        conditions_text="высота 8 м", safety_systems=["fall_arrest", "rescue_evacuation"],
        measures_before_text="установить ограждение", measures_during_text="контроль привязи",
        special_conditions_text="ветер до 10 м/с", ppe_text="каска, привязь",
    )
    assert payload.safety_systems == ["fall_arrest", "rescue_evacuation"]
    assert payload.subdivision_text == "Цех №2"


def test_create_rejects_unknown_safety_system():
    with pytest.raises(ValidationError):
        WorkPermitCreate(work_type="height", zone_text="z", safety_systems=["bogus"])
```

- [ ] **Step 2: Прогнать тест — должен упасть**

Run: `python -m pytest backend/tests/test_work_permit_schemas_782n.py -v`
Expected: FAIL (поля/валидатора нет).

- [ ] **Step 3: Реализовать**

В `backend/app/schemas/work_permit.py`:

1) В `WorkPermitCreate` после `measures_text`-блока добавить поля и валидатор `safety_systems`:

```python
    subdivision_text: str | None = None
    content_text: str | None = None
    conditions_text: str | None = None
    safety_systems: list[str] | None = None
    measures_before_text: str | None = None
    measures_during_text: str | None = None
    special_conditions_text: str | None = None
    ppe_text: str | None = None

    @field_validator("safety_systems")
    @classmethod
    def _safety_systems(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        for code in v:
            if not lc.is_safety_system(code):
                raise ValueError(f"invalid safety_system: {code!r}")
        return v
```

2) В `WorkPermitUpdate` добавить те же 8 полей (все `| None = None`) и такой же валидатор `safety_systems`.

3) В `WorkPermitRead` добавить те же 8 полей с типами:

```python
    subdivision_text: str | None
    content_text: str | None
    conditions_text: str | None
    safety_systems: list[str] | None
    measures_before_text: str | None
    measures_during_text: str | None
    special_conditions_text: str | None
    ppe_text: str | None
```

- [ ] **Step 4: Прогнать тест — должен пройти**

Run: `python -m pytest backend/tests/test_work_permit_schemas_782n.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/work_permit.py backend/tests/test_work_permit_schemas_782n.py
git commit -m "feat(work-permits): schemas — 782н fields + safety_systems validator"
```

---

### Task 5: Сервис create/update прокидывает новые поля

**Files:**
- Modify: `backend/app/domains/work_permits/service.py`
- Test: `tests/test_work_permit_service.py`

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/test_work_permit_service.py` (использует существующие фикстуры файла — `session`/`tenant`; если их имена иные, взять как в соседних тестах файла):

```python
@pytest.mark.asyncio
async def test_create_persists_782n_fields(session, tenant):
    from app.domains.work_permits import create_work_permit, update_work_permit

    wp = await create_work_permit(
        session, tenant_id=tenant.id, work_type="height", zone_text="z",
        content_text="монтаж", safety_systems=["fall_arrest"], ppe_text="каска",
    )
    assert wp.content_text == "монтаж"
    assert wp.safety_systems == ["fall_arrest"]

    updated = await update_work_permit(
        session, tenant_id=tenant.id, work_permit_id=wp.id,
        conditions_text="высота 8м", safety_systems=["restraint", "access"],
    )
    assert updated.conditions_text == "высота 8м"
    assert updated.safety_systems == ["restraint", "access"]
```

- [ ] **Step 2: Прогнать тест — должен упасть**

Run: `python -m pytest tests/test_work_permit_service.py::test_create_persists_782n_fields -v`
Expected: FAIL (`create_work_permit` не принимает `content_text`).

- [ ] **Step 3: Реализовать**

В `backend/app/domains/work_permits/service.py`:

1) Расширить сигнатуру и тело `create_work_permit` — добавить kwargs и передать их в конструктор `WorkPermit`:

```python
async def create_work_permit(
    session: AsyncSession, *, tenant_id: str, work_type: str, zone_text: str,
    number: str | None = None, site_id: str | None = None, equipment_text: str | None = None,
    hazards_text: str | None = None, measures_text: str | None = None,
    planned_start: datetime | None = None, planned_end: datetime | None = None,
    subdivision_text: str | None = None, content_text: str | None = None,
    conditions_text: str | None = None, safety_systems: list[str] | None = None,
    measures_before_text: str | None = None, measures_during_text: str | None = None,
    special_conditions_text: str | None = None, ppe_text: str | None = None,
) -> WorkPermit:
    wp = WorkPermit(
        tenant_id=tenant_id, work_type=work_type, zone_text=zone_text, number=number,
        site_id=site_id, equipment_text=equipment_text, hazards_text=hazards_text,
        measures_text=measures_text, planned_start=planned_start, planned_end=planned_end,
        subdivision_text=subdivision_text, content_text=content_text,
        conditions_text=conditions_text, safety_systems=safety_systems,
        measures_before_text=measures_before_text, measures_during_text=measures_during_text,
        special_conditions_text=special_conditions_text, ppe_text=ppe_text,
        status=lc.STATUS_DRAFT,
    )
    session.add(wp)
    await session.flush()
    await session.refresh(wp)
    return wp
```

2) Расширить `_DRAFT_EDITABLE` (update идёт через него):

```python
_DRAFT_EDITABLE = ("number", "work_type", "zone_text", "site_id", "equipment_text",
                   "hazards_text", "measures_text", "planned_start", "planned_end",
                   "subdivision_text", "content_text", "conditions_text", "safety_systems",
                   "measures_before_text", "measures_during_text", "special_conditions_text",
                   "ppe_text")
```

- [ ] **Step 4: Прогнать тест — должен пройти**

Run: `python -m pytest tests/test_work_permit_service.py::test_create_persists_782n_fields -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/work_permits/service.py tests/test_work_permit_service.py
git commit -m "feat(work-permits): service create/update passthrough 782н fields"
```

---

### Task 6: Роуты — create/read прокидывают новые поля

**Files:**
- Modify: `backend/app/api/routes/work_permits.py`
- Test: `tests/api/test_work_permit_782n_fields.py`

- [ ] **Step 1: Написать падающий тест**

Create `tests/api/test_work_permit_782n_fields.py` (паттерн запроса — как в `tests/api/test_work_permits_api.py`: тот же клиент/заголовки/админ-контекст; скопировать фикстуры/хелперы оттуда):

```python
import pytest


@pytest.mark.asyncio
async def test_create_roundtrips_782n_fields(admin_client):
    body = {
        "work_type": "height", "zone_text": "фасад",
        "subdivision_text": "Цех №2", "content_text": "монтаж ограждения",
        "safety_systems": ["fall_arrest", "rescue_evacuation"], "ppe_text": "каска, привязь",
    }
    r = await admin_client.post("/api/v1/work-permits", json=body)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["subdivision_text"] == "Цех №2"
    assert data["safety_systems"] == ["fall_arrest", "rescue_evacuation"]

    got = await admin_client.get(f"/api/v1/work-permits/{data['id']}")
    assert got.json()["content_text"] == "монтаж ограждения"


@pytest.mark.asyncio
async def test_create_rejects_bad_safety_system(admin_client):
    r = await admin_client.post(
        "/api/v1/work-permits",
        json={"work_type": "height", "zone_text": "z", "safety_systems": ["bogus"]},
    )
    assert r.status_code == 422
```

> NB: имя фикстуры клиента (`admin_client`) и префикс пути (`/api/v1`) взять точно как в существующем `tests/api/test_work_permits_api.py`.

- [ ] **Step 2: Прогнать тест — должен упасть**

Run: `python -m pytest tests/api/test_work_permit_782n_fields.py -v`
Expected: FAIL (ответ не содержит новых полей).

- [ ] **Step 3: Реализовать**

В `backend/app/api/routes/work_permits.py`:

1) В `_permit_read` добавить новые поля в конструктор `WorkPermitRead`:

```python
        subdivision_text=wp.subdivision_text, content_text=wp.content_text,
        conditions_text=wp.conditions_text, safety_systems=wp.safety_systems,
        measures_before_text=wp.measures_before_text, measures_during_text=wp.measures_during_text,
        special_conditions_text=wp.special_conditions_text, ppe_text=wp.ppe_text,
```

2) В `create_work_permit_endpoint` дополнить вызов `create_work_permit(...)` новыми аргументами из `payload`:

```python
        subdivision_text=payload.subdivision_text, content_text=payload.content_text,
        conditions_text=payload.conditions_text, safety_systems=payload.safety_systems,
        measures_before_text=payload.measures_before_text,
        measures_during_text=payload.measures_during_text,
        special_conditions_text=payload.special_conditions_text, ppe_text=payload.ppe_text,
```

(PATCH уже работает: `update_work_permit_endpoint` передаёт `**fields` из `model_dump(exclude_unset=True)`, а Task 5 добавил поля в `_DRAFT_EDITABLE`.)

- [ ] **Step 4: Прогнать тест — должен пройти**

Run: `python -m pytest tests/api/test_work_permit_782n_fields.py -v`
Expected: PASS.

- [ ] **Step 5: Прогон контурной регрессии backend**

Run: `python -m pytest backend/tests/test_work_permit_lifecycle.py backend/tests/test_wp02_work_permit_782n_migration.py backend/tests/test_work_permit_schemas_782n.py tests/test_work_permit_service.py tests/api/test_work_permits_api.py tests/api/test_work_permit_782n_fields.py -v`
Expected: PASS (весь контур + новые поля).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/work_permits.py tests/api/test_work_permit_782n_fields.py
git commit -m "feat(work-permits): routes create/read passthrough 782н fields"
```

---

## Часть B — Frontend

> Конвенции — как у `frontend/src/pages/persons/PersonsPage.tsx` + `frontend/src/features/persons/PersonFormDialog.tsx` + `frontend/src/pages/prescriptions/PrescriptionsPage.tsx`. Клиент — `frontend/src/api/client.ts` (`apiClient`, auth + X-Tenant авто). Команды: `npm --prefix frontend run test -- <file>`, `npm --prefix frontend run build`.

### Task 7: Коды прав work_permit.view / work_permit.manage

**Files:**
- Modify: `frontend/src/permissions/permissions.ts`

- [ ] **Step 1: Реализовать**

В объект `PERMISSIONS` добавить (рядом с другими доменными кодами):

```ts
  WORK_PERMIT_VIEW: "work_permit.view",
  WORK_PERMIT_MANAGE: "work_permit.manage",
```

(Роль `admin` = `ALL_PERMISSIONS` → коды получит только admin; другим ролям не добавляем.)

- [ ] **Step 2: Проверить типы**

Run: `npm --prefix frontend run build`
Expected: сборка проходит (нет ошибок типов от нового кода прав).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/permissions/permissions.ts
git commit -m "feat(work-permits): frontend permission codes (admin-only)"
```

---

### Task 8: Словарь подписей (RU)

**Files:**
- Create: `frontend/src/lib/workPermitVocab.ts`

- [ ] **Step 1: Реализовать**

Create `frontend/src/lib/workPermitVocab.ts`:

```ts
export const WORK_TYPE_LABELS: Record<string, string> = {
  hot_work: "Огневые работы",
  gas_hazardous: "Газоопасные работы",
  height: "Работа на высоте",
  confined_space: "Замкнутые пространства",
  excavation: "Земляные работы",
  electrical: "Электроустановки",
};

export const MEMBER_ROLE_LABELS: Record<string, string> = {
  issuer: "Выдающий наряд",
  supervisor: "Ответственный руководитель",
  admitter: "Допускающий",
  foreman: "Производитель работ",
  observer: "Наблюдающий",
  member: "Член бригады",
};

export const STATUS_LABELS: Record<string, string> = {
  draft: "Черновик",
  issued: "Выдан",
  suspended: "Приостановлен",
  closed: "Закрыт",
  cancelled: "Отменён",
};

export const EVENT_TYPE_LABELS: Record<string, string> = {
  issued: "Выдан",
  suspended: "Приостановлен",
  resumed: "Возобновлён",
  closed: "Закрыт",
  cancelled: "Отменён",
  extended: "Продлён",
};

export const SAFETY_SYSTEM_LABELS: Record<string, string> = {
  restraint: "Удерживающие системы",
  positioning: "Системы позиционирования",
  fall_arrest: "Страховочные системы",
  rescue_evacuation: "Системы для эвакуации и спасения",
  access: "Системы для подъёма и спуска",
};

export const labelOf = (map: Record<string, string>, code: string): string =>
  map[code] ?? code;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/workPermitVocab.ts
git commit -m "feat(work-permits): RU vocab labels"
```

---

### Task 9: DTO + zod-форма

**Files:**
- Create: `frontend/src/types/dto/workPermits.ts`
- Create: `frontend/src/types/forms/workPermits.ts`

- [ ] **Step 1: Реализовать DTO**

Create `frontend/src/types/dto/workPermits.ts`:

```ts
export interface WorkPermitMemberDto {
  id: string;
  person_id: string;
  role: string;
  created_at: string;
}

export interface WorkPermitDto {
  id: string;
  number: string | null;
  work_type: string;
  zone_text: string;
  site_id: string | null;
  equipment_text: string | null;
  hazards_text: string | null;
  measures_text: string | null;
  planned_start: string | null;
  planned_end: string | null;
  status: string;
  opened_at: string | null;
  closed_at: string | null;
  suspended_at: string | null;
  members: WorkPermitMemberDto[];
  subdivision_text: string | null;
  content_text: string | null;
  conditions_text: string | null;
  safety_systems: string[] | null;
  measures_before_text: string | null;
  measures_during_text: string | null;
  special_conditions_text: string | null;
  ppe_text: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkPermitPage {
  items: WorkPermitDto[];
  total: number;
}

export interface WorkPermitEventDto {
  id: string;
  event_type: string;
  at: string;
  actor_user_id: string | null;
  photo_file_id: string | null;
  note: string | null;
}

export interface ViolationDto {
  person_id: string;
  role: string;
  code: string;
  severity: string;
}

export interface ReadinessReportDto {
  ok: boolean;
  violations: ViolationDto[];
}
```

- [ ] **Step 2: Реализовать zod-форму**

Create `frontend/src/types/forms/workPermits.ts`:

```ts
import { z } from "zod";

export const SAFETY_SYSTEM_CODES = [
  "restraint", "positioning", "fall_arrest", "rescue_evacuation", "access",
] as const;

export const workPermitSchema = z.object({
  work_type: z.string().min(1, "Укажите вид работ"),
  number: z.string().optional(),
  subdivision_text: z.string().optional(),
  site_id: z.string().optional(),
  zone_text: z.string().min(1, "Укажите зону работ"),
  planned_start: z.string().optional(),
  planned_end: z.string().optional(),
  content_text: z.string().optional(),
  conditions_text: z.string().optional(),
  hazards_text: z.string().optional(),
  safety_systems: z.array(z.enum(SAFETY_SYSTEM_CODES)).optional(),
  measures_before_text: z.string().optional(),
  measures_during_text: z.string().optional(),
  special_conditions_text: z.string().optional(),
  ppe_text: z.string().optional(),
});

export type WorkPermitFormValues = z.infer<typeof workPermitSchema>;
```

- [ ] **Step 3: Проверить типы**

Run: `npm --prefix frontend run build`
Expected: проходит.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/dto/workPermits.ts frontend/src/types/forms/workPermits.ts
git commit -m "feat(work-permits): DTO + zod form types"
```

---

### Task 10: API-модуль workPermits.ts

**Files:**
- Create: `frontend/src/api/workPermits.ts`

- [ ] **Step 1: Реализовать**

Create `frontend/src/api/workPermits.ts`:

```ts
import { apiClient } from "@/api/client";
import type {
  ReadinessReportDto, WorkPermitDto, WorkPermitEventDto, WorkPermitMemberDto, WorkPermitPage,
} from "@/types/dto/workPermits";

export interface PersonOption { id: string; label: string; }

export interface WorkPermitListParams {
  status?: string; work_type?: string; site_id?: string; limit?: number; offset?: number;
}

const base = "/work-permits";

export const workPermitsApi = {
  async list(params: WorkPermitListParams = {}): Promise<WorkPermitPage> {
    const r = await apiClient.get<WorkPermitPage>(base, {
      params: { limit: 200, offset: 0, ...params },
    });
    return r.data;
  },
  async count(params: WorkPermitListParams = {}): Promise<number> {
    const r = await apiClient.get<WorkPermitPage>(base, { params: { ...params, limit: 1, offset: 0 } });
    return r.data.total ?? 0;
  },
  async get(id: string): Promise<WorkPermitDto> {
    return (await apiClient.get<WorkPermitDto>(`${base}/${id}`)).data;
  },
  async create(body: Record<string, unknown>): Promise<WorkPermitDto> {
    return (await apiClient.post<WorkPermitDto>(base, body)).data;
  },
  async update(id: string, body: Record<string, unknown>): Promise<WorkPermitDto> {
    return (await apiClient.patch<WorkPermitDto>(`${base}/${id}`, body)).data;
  },
  async remove(id: string): Promise<void> {
    await apiClient.delete(`${base}/${id}`);
  },
  async addMember(id: string, body: { person_id: string; role: string }): Promise<WorkPermitMemberDto> {
    return (await apiClient.post<WorkPermitMemberDto>(`${base}/${id}/members`, body)).data;
  },
  async removeMember(id: string, memberId: string): Promise<void> {
    await apiClient.delete(`${base}/${id}/members/${memberId}`);
  },
  async readiness(id: string): Promise<ReadinessReportDto> {
    return (await apiClient.get<ReadinessReportDto>(`${base}/${id}/readiness`)).data;
  },
  async events(id: string): Promise<WorkPermitEventDto[]> {
    return (await apiClient.get<WorkPermitEventDto[]>(`${base}/${id}/events`)).data;
  },
  async action(
    id: string, name: "issue" | "suspend" | "resume" | "close" | "cancel",
    body: { note?: string } = {},
  ): Promise<WorkPermitDto> {
    return (await apiClient.post<WorkPermitDto>(`${base}/${id}/${name}`, body)).data;
  },
  async extend(id: string, planned_end: string): Promise<WorkPermitDto> {
    return (await apiClient.post<WorkPermitDto>(`${base}/${id}/extend`, { planned_end })).data;
  },
};

export async function fetchAllPersons(): Promise<PersonOption[]> {
  const r = await apiClient.get<{ items: Array<Record<string, unknown>> }>("/persons", {
    params: { limit: 500, offset: 0 },
  });
  return (r.data.items ?? []).map((p) => {
    const last = (p.last_name as string) ?? "";
    const first = (p.first_name as string) ?? "";
    const middle = (p.middle_name as string) ?? "";
    const label = [last, first, middle].filter(Boolean).join(" ").trim() || (p.id as string);
    return { id: p.id as string, label };
  });
}
```

> NB: подтвердить форму ответа `/persons` (поля `items`, `first_name`/`last_name`/`middle_name`) по `frontend/src/api/` — если отличается, поправить маппинг здесь.

- [ ] **Step 2: Проверить типы**

Run: `npm --prefix frontend run build`
Expected: проходит.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/workPermits.ts
git commit -m "feat(work-permits): api module + fetchAllPersons"
```

---

### Task 11: Форма создания/редактирования (секции 782н)

**Files:**
- Create: `frontend/src/features/work-permits/WorkPermitFormDialog.tsx`

- [ ] **Step 1: Реализовать** (паттерн `PersonFormDialog.tsx`: react-hook-form + zodResolver + native select/textarea + `applyApiFieldErrorsToForm` + `toast`)

Create `frontend/src/features/work-permits/WorkPermitFormDialog.tsx`:

```tsx
import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { workPermitsApi, type PersonOption } from "@/api/workPermits";
import type { WorkPermitDto } from "@/types/dto/workPermits";
import {
  SAFETY_SYSTEM_CODES, workPermitSchema, type WorkPermitFormValues,
} from "@/types/forms/workPermits";
import { SAFETY_SYSTEM_LABELS, WORK_TYPE_LABELS } from "@/lib/workPermitVocab";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const EMPTY: WorkPermitFormValues = {
  work_type: "height", number: "", subdivision_text: "", site_id: "", zone_text: "",
  planned_start: "", planned_end: "", content_text: "", conditions_text: "", hazards_text: "",
  safety_systems: [], measures_before_text: "", measures_during_text: "",
  special_conditions_text: "", ppe_text: "",
};

interface Props {
  trigger: ReactNode;
  initialData?: WorkPermitDto;
  onSubmitted?: (wp: WorkPermitDto) => void;
}

const ta = "min-h-[64px] w-full rounded-md border px-3 py-2 text-sm";

export const WorkPermitFormDialog = ({ trigger, initialData, onSubmitted }: Props) => {
  const [open, setOpen] = useState(false);
  const form = useForm<WorkPermitFormValues>({
    resolver: zodResolver(workPermitSchema),
    defaultValues: EMPTY,
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        work_type: initialData.work_type, number: initialData.number ?? "",
        subdivision_text: initialData.subdivision_text ?? "", site_id: initialData.site_id ?? "",
        zone_text: initialData.zone_text,
        planned_start: initialData.planned_start?.slice(0, 16) ?? "",
        planned_end: initialData.planned_end?.slice(0, 16) ?? "",
        content_text: initialData.content_text ?? "", conditions_text: initialData.conditions_text ?? "",
        hazards_text: initialData.hazards_text ?? "",
        safety_systems: (initialData.safety_systems ?? []) as WorkPermitFormValues["safety_systems"],
        measures_before_text: initialData.measures_before_text ?? "",
        measures_during_text: initialData.measures_during_text ?? "",
        special_conditions_text: initialData.special_conditions_text ?? "",
        ppe_text: initialData.ppe_text ?? "",
      });
    } else {
      form.reset(EMPTY);
    }
  }, [open, initialData, form]);

  const toBody = (v: WorkPermitFormValues): Record<string, unknown> => ({
    work_type: v.work_type, zone_text: v.zone_text,
    number: v.number || null, subdivision_text: v.subdivision_text || null,
    site_id: v.site_id || null, content_text: v.content_text || null,
    conditions_text: v.conditions_text || null, hazards_text: v.hazards_text || null,
    safety_systems: v.safety_systems && v.safety_systems.length ? v.safety_systems : null,
    measures_before_text: v.measures_before_text || null,
    measures_during_text: v.measures_during_text || null,
    special_conditions_text: v.special_conditions_text || null, ppe_text: v.ppe_text || null,
    planned_start: v.planned_start ? new Date(v.planned_start).toISOString() : null,
    planned_end: v.planned_end ? new Date(v.planned_end).toISOString() : null,
  });

  const onSubmit = async (v: WorkPermitFormValues) => {
    try {
      const result = initialData
        ? await workPermitsApi.update(initialData.id, toBody(v))
        : await workPermitsApi.create(toBody(v));
      onSubmitted?.(result);
      toast.success(initialData ? "Наряд обновлён" : "Наряд создан");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) applyApiFieldErrorsToForm(form.setError, err, {});
      toast.error("Не удалось сохранить наряд");
    }
  };

  const selected = new Set(form.watch("safety_systems") ?? []);
  const toggleSystem = (code: (typeof SAFETY_SYSTEM_CODES)[number]) => {
    const next = new Set(selected);
    next.has(code) ? next.delete(code) : next.add(code);
    form.setValue("safety_systems", Array.from(next) as WorkPermitFormValues["safety_systems"]);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{initialData ? "Редактировать наряд" : "Новый наряд-допуск"}</DialogTitle>
          <DialogDescription>Работа на высоте (форма 782н)</DialogDescription>
        </DialogHeader>
        <form className="space-y-4" onSubmit={form.handleSubmit(onSubmit)}>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="work_type">Вид работ</Label>
              <select id="work_type" className="h-10 w-full rounded-md border px-3" {...form.register("work_type")}>
                {Object.entries(WORK_TYPE_LABELS).map(([code, label]) => (
                  <option key={code} value={code}>{label}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="number">Номер</Label>
              <Input id="number" {...form.register("number")} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="subdivision_text">Подразделение</Label>
              <Input id="subdivision_text" {...form.register("subdivision_text")} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="zone_text">Зона работ</Label>
              <Input id="zone_text" {...form.register("zone_text")} />
              {form.formState.errors.zone_text && (
                <p className="text-xs text-destructive">{form.formState.errors.zone_text.message}</p>
              )}
            </div>
            <div className="space-y-1">
              <Label htmlFor="planned_start">Начало</Label>
              <Input id="planned_start" type="datetime-local" {...form.register("planned_start")} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="planned_end">Окончание</Label>
              <Input id="planned_end" type="datetime-local" {...form.register("planned_end")} />
            </div>
          </div>

          <div className="space-y-1">
            <Label htmlFor="content_text">Содержание работ</Label>
            <textarea id="content_text" className={ta} {...form.register("content_text")} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="conditions_text">Условия проведения</Label>
            <textarea id="conditions_text" className={ta} {...form.register("conditions_text")} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="hazards_text">Опасные факторы</Label>
            <textarea id="hazards_text" className={ta} {...form.register("hazards_text")} />
          </div>

          <div className="space-y-1">
            <Label>Системы обеспечения безопасности</Label>
            <div className="flex flex-wrap gap-3">
              {SAFETY_SYSTEM_CODES.map((code) => (
                <label key={code} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={selected.has(code)} onChange={() => toggleSystem(code)} />
                  {SAFETY_SYSTEM_LABELS[code]}
                </label>
              ))}
            </div>
          </div>

          <div className="space-y-1">
            <Label htmlFor="measures_before_text">Мероприятия до начала работ</Label>
            <textarea id="measures_before_text" className={ta} {...form.register("measures_before_text")} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="measures_during_text">Мероприятия в процессе работ</Label>
            <textarea id="measures_during_text" className={ta} {...form.register("measures_during_text")} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="special_conditions_text">Особые условия</Label>
            <textarea id="special_conditions_text" className={ta} {...form.register("special_conditions_text")} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="ppe_text">Перечень СИЗ</Label>
            <textarea id="ppe_text" className={ta} {...form.register("ppe_text")} />
          </div>

          <DialogFooter>
            <Button type="submit" disabled={form.formState.isSubmitting}>
              {form.formState.isSubmitting ? "Сохранение..." : "Сохранить"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};
```

> NB: `site_id` в Ф1 — скрытое/необязательное (площадка-выбор можно добавить позже; backend принимает `site_id` опционально). `PersonOption` импортирован для будущего использования в панели бригады (Task 13).

- [ ] **Step 2: Проверить типы**

Run: `npm --prefix frontend run build`
Expected: проходит.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/work-permits/WorkPermitFormDialog.tsx
git commit -m "feat(work-permits): create/edit form dialog (782н sections)"
```

---

### Task 12: Страница списка + тест

**Files:**
- Create: `frontend/src/pages/work-permits/WorkPermitsPage.tsx`
- Test: `frontend/src/__tests__/WorkPermitsPage.test.tsx`

- [ ] **Step 1: Написать падающий тест** (паттерн `frontend/src/__tests__/PpePage.test.tsx`)

Create `frontend/src/__tests__/WorkPermitsPage.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PERMISSIONS } from "@/permissions/permissions";
import WorkPermitsPage from "@/pages/work-permits/WorkPermitsPage";
import { useAuthStore } from "@/stores/auth";

const listMock = vi.fn();
const countMock = vi.fn();
vi.mock("@/api/workPermits", () => ({
  workPermitsApi: { list: (...a: unknown[]) => listMock(...a), count: (...a: unknown[]) => countMock(...a) },
}));

const setRole = (perms: string[]) =>
  useAuthStore.setState({
    user: { id: "u1", roles: ["admin"], permissions: perms } as never,
    loading: false, error: null, isAuthenticated: true, initialized: true,
  });

describe("WorkPermitsPage", () => {
  beforeEach(() => {
    listMock.mockReset(); countMock.mockReset();
    listMock.mockResolvedValue({ items: [], total: 0 });
    countMock.mockResolvedValue(0);
  });

  it("показывает пустое состояние", async () => {
    setRole([PERMISSIONS.WORK_PERMIT_VIEW, PERMISSIONS.WORK_PERMIT_MANAGE]);
    render(<MemoryRouter><WorkPermitsPage /></MemoryRouter>);
    expect(await screen.findByText(/наряд/i)).toBeInTheDocument();
  });

  it("скрывает «Новый наряд» без права manage", async () => {
    setRole([PERMISSIONS.WORK_PERMIT_VIEW]);
    render(<MemoryRouter><WorkPermitsPage /></MemoryRouter>);
    await screen.findByText(/наряд/i);
    expect(screen.queryByRole("button", { name: /новый наряд/i })).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Прогнать тест — должен упасть**

Run: `npm --prefix frontend run test -- WorkPermitsPage`
Expected: FAIL (страницы нет).

- [ ] **Step 3: Реализовать страницу** (паттерн `PrescriptionsPage.tsx`: `useAsyncResource` + `RegistryTable`)

Create `frontend/src/pages/work-permits/WorkPermitsPage.tsx`:

```tsx
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Can } from "@/components/permissions/Can";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryTable } from "@/components/common/RegistryTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { workPermitsApi } from "@/api/workPermits";
import { PERMISSIONS } from "@/permissions/permissions";
import { STATUS_LABELS, WORK_TYPE_LABELS, labelOf } from "@/lib/workPermitVocab";
import type { WorkPermitDto } from "@/types/dto/workPermits";
import { WorkPermitFormDialog } from "@/features/work-permits/WorkPermitFormDialog";

const STATUS_FILTERS = ["", "draft", "issued", "suspended", "closed", "cancelled"];

export default function WorkPermitsPage() {
  const [status, setStatus] = useState("");
  const [counts, setCounts] = useState({ draft: 0, issued: 0, closed: 0 });

  const loader = useCallback(
    () => workPermitsApi.list(status ? { status } : {}).then((p) => p.items),
    [status],
  );
  const { data, loading, error, reload } = useAsyncResource({
    loader, initialData: [] as WorkPermitDto[], errorMessage: "Не удалось загрузить наряды",
  });

  useEffect(() => {
    Promise.all([
      workPermitsApi.count({ status: "draft" }),
      workPermitsApi.count({ status: "issued" }),
      workPermitsApi.count({ status: "closed" }),
    ]).then(([draft, issued, closed]) => setCounts({ draft, issued, closed })).catch(() => undefined);
  }, [data]);

  const registry = useLocalRegistry({
    items: data,
    match: (wp: WorkPermitDto, q: string) =>
      [wp.number ?? "", labelOf(WORK_TYPE_LABELS, wp.work_type), wp.zone_text]
        .join(" ").toLowerCase().includes(q),
  });

  if (loading) return <LoadingScreen label="Загрузка нарядов-допусков" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-medium">Наряды-допуски</h1>
          <p className="text-sm text-muted-foreground">
            Черновики: {counts.draft} · Выдан: {counts.issued} · Закрыто: {counts.closed}
          </p>
        </div>
        <Can permission={PERMISSIONS.WORK_PERMIT_MANAGE}>
          <WorkPermitFormDialog
            trigger={<Button>Новый наряд</Button>}
            onSubmitted={() => reload()}
          />
        </Can>
      </div>

      <div className="flex gap-2">
        <select className="h-9 rounded-md border px-3 text-sm" value={status}
          onChange={(e) => setStatus(e.target.value)}>
          {STATUS_FILTERS.map((s) => (
            <option key={s || "all"} value={s}>{s ? STATUS_LABELS[s] : "Все статусы"}</option>
          ))}
        </select>
      </div>

      {data.length === 0 ? (
        <EmptyState title="Нарядов нет" description="Создайте первый наряд-допуск." />
      ) : (
        <RegistryTable
          columns={[
            { key: "number", header: "№", render: (wp: WorkPermitDto) => wp.number ?? "—" },
            { key: "work_type", header: "Вид работ", render: (wp: WorkPermitDto) => labelOf(WORK_TYPE_LABELS, wp.work_type) },
            { key: "zone_text", header: "Зона", render: (wp: WorkPermitDto) => wp.zone_text },
            { key: "members", header: "Бригада", render: (wp: WorkPermitDto) => String(wp.members.length) },
            { key: "status", header: "Статус", render: (wp: WorkPermitDto) => <StatusBadge label={labelOf(STATUS_LABELS, wp.status)} /> },
            { key: "open", header: "", render: (wp: WorkPermitDto) => <Link className="text-sm underline" to={`/work-permits/${wp.id}`}>Открыть</Link> },
          ]}
          data={registry.pagedItems}
          pageIndex={registry.pageIndex}
          pageSize={registry.pageSize}
          total={registry.total}
          onPageChange={registry.onPageChange}
          onPageSizeChange={registry.onPageSizeChange}
          onSearchChange={registry.onSearchChange}
          searchPlaceholder="Поиск по №, виду, зоне"
          caption="Наряды-допуски"
        />
      )}
    </div>
  );
}
```

> NB: проверить точные пропсы `RegistryTable`/`StatusBadge`/`useLocalRegistry`/`useAsyncResource` по `PrescriptionsPage.tsx`/`PpePage.tsx` и при расхождении выровнять (имена колонок/`render`). Цель — повторить существующий паттерн.

- [ ] **Step 4: Прогнать тест — должен пройти**

Run: `npm --prefix frontend run test -- WorkPermitsPage`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/work-permits/WorkPermitsPage.tsx frontend/src/__tests__/WorkPermitsPage.test.tsx
git commit -m "feat(work-permits): list page + component test"
```

---

### Task 13: Карточка наряда — секции, бригада, готовность, действия, события

**Files:**
- Create: `frontend/src/pages/work-permits/WorkPermitDetailPage.tsx`
- Create: `frontend/src/features/work-permits/ReadinessPanel.tsx`
- Create: `frontend/src/features/work-permits/WorkPermitEventsTimeline.tsx`

- [ ] **Step 1: Реализовать ReadinessPanel**

Create `frontend/src/features/work-permits/ReadinessPanel.tsx`:

```tsx
import type { ReadinessReportDto } from "@/types/dto/workPermits";
import { MEMBER_ROLE_LABELS, labelOf } from "@/lib/workPermitVocab";

const VIOLATION_LABELS: Record<string, string> = {
  permit_missing: "нет личного допуска",
  permit_expired: "просрочен личный допуск",
  medical_missing: "нет медосмотра",
  medical_expired: "просрочен медосмотр",
  training_missing: "нет обучения",
  training_expired: "просрочено обучение",
};

export const ReadinessPanel = ({ report, nameOf }: {
  report: ReadinessReportDto | null;
  nameOf: (personId: string) => string;
}) => {
  if (!report) return <p className="text-sm text-muted-foreground">Готовность не загружена</p>;
  if (report.ok) return <p className="text-sm text-emerald-600">Бригада готова — все допуски действуют</p>;
  return (
    <ul className="space-y-1 text-sm text-destructive">
      {report.violations.map((v, i) => (
        <li key={i}>
          {nameOf(v.person_id)} ({labelOf(MEMBER_ROLE_LABELS, v.role)}) — {VIOLATION_LABELS[v.code] ?? v.code}
        </li>
      ))}
    </ul>
  );
};
```

> NB: коды нарушений (`permit_expired` и т.д.) — подтвердить по `backend/app/services/work_permit_admission.py`; неизвестные коды падают в fallback (сырой код), поэтому панель не сломается.

- [ ] **Step 2: Реализовать EventsTimeline**

Create `frontend/src/features/work-permits/WorkPermitEventsTimeline.tsx`:

```tsx
import type { WorkPermitEventDto } from "@/types/dto/workPermits";
import { EVENT_TYPE_LABELS, labelOf } from "@/lib/workPermitVocab";

export const WorkPermitEventsTimeline = ({ events }: { events: WorkPermitEventDto[] }) => {
  if (events.length === 0) return <p className="text-sm text-muted-foreground">Событий нет</p>;
  return (
    <ul className="space-y-1 text-sm">
      {events.map((e) => (
        <li key={e.id} className="flex gap-3">
          <span className="w-32 shrink-0 text-muted-foreground">{new Date(e.at).toLocaleString("ru-RU")}</span>
          <span>{labelOf(EVENT_TYPE_LABELS, e.event_type)}</span>
          {e.note ? <span className="text-muted-foreground">— {e.note}</span> : null}
        </li>
      ))}
    </ul>
  );
};
```

- [ ] **Step 3: Реализовать карточку** (загрузка наряда + persons + readiness + events; действия по статусу; бригада — add/remove в draft)

Create `frontend/src/pages/work-permits/WorkPermitDetailPage.tsx`:

```tsx
import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Can } from "@/components/permissions/Can";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { ErrorState } from "@/components/common/ErrorState";
import { StatusBadge } from "@/components/common/StatusBadge";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { workPermitsApi, fetchAllPersons, type PersonOption } from "@/api/workPermits";
import { PERMISSIONS } from "@/permissions/permissions";
import {
  MEMBER_ROLE_LABELS, SAFETY_SYSTEM_LABELS, STATUS_LABELS, WORK_TYPE_LABELS, labelOf,
} from "@/lib/workPermitVocab";
import type { ReadinessReportDto, WorkPermitDto, WorkPermitEventDto } from "@/types/dto/workPermits";
import { WorkPermitFormDialog } from "@/features/work-permits/WorkPermitFormDialog";
import { ReadinessPanel } from "@/features/work-permits/ReadinessPanel";
import { WorkPermitEventsTimeline } from "@/features/work-permits/WorkPermitEventsTimeline";

const ACTIONS_BY_STATUS: Record<string, Array<{ name: "issue" | "suspend" | "resume" | "close" | "cancel"; label: string }>> = {
  draft: [{ name: "issue", label: "Выдать" }, { name: "cancel", label: "Отменить" }],
  issued: [{ name: "suspend", label: "Приостановить" }, { name: "close", label: "Закрыть" }, { name: "cancel", label: "Отменить" }],
  suspended: [{ name: "resume", label: "Возобновить" }, { name: "close", label: "Закрыть" }, { name: "cancel", label: "Отменить" }],
};

export default function WorkPermitDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [persons, setPersons] = useState<PersonOption[]>([]);
  const [readiness, setReadiness] = useState<ReadinessReportDto | null>(null);
  const [events, setEvents] = useState<WorkPermitEventDto[]>([]);

  const loader = useCallback(() => workPermitsApi.get(id), [id]);
  const { data: wp, loading, error, reload } = useAsyncResource({
    loader, initialData: null as WorkPermitDto | null, errorMessage: "Не удалось загрузить наряд",
  });

  useEffect(() => { fetchAllPersons().then(setPersons).catch(() => undefined); }, []);
  const refreshSide = useCallback(() => {
    workPermitsApi.readiness(id).then(setReadiness).catch(() => undefined);
    workPermitsApi.events(id).then(setEvents).catch(() => undefined);
  }, [id]);
  useEffect(() => { if (wp) refreshSide(); }, [wp, refreshSide]);

  const nameOf = useMemo(() => {
    const m = new Map(persons.map((p) => [p.id, p.label]));
    return (pid: string) => m.get(pid) ?? pid;
  }, [persons]);

  if (loading) return <LoadingScreen label="Загрузка наряда" />;
  if (error || !wp) return <ErrorState error={error ?? new Error("not found")} onRetry={reload} />;

  const runAction = async (name: "issue" | "suspend" | "resume" | "close" | "cancel") => {
    try {
      await workPermitsApi.action(wp.id, name);
      toast.success("Готово");
      reload();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: { code?: string; details?: { violations?: unknown[] } } } } })?.response?.data?.detail;
      if (detail?.code === "WORK_PERMIT_BLOCKED") {
        toast.error("Бригада не готова — наряд нельзя выдать");
        refreshSide();
      } else {
        toast.error("Действие недоступно");
      }
      reload();
    }
  };

  const Section = ({ title, value }: { title: string; value: string | null | undefined }) =>
    value ? (
      <div><div className="text-xs text-muted-foreground">{title}</div><div className="text-sm whitespace-pre-wrap">{value}</div></div>
    ) : null;

  return (
    <div className="space-y-5">
      <Link to="/work-permits" className="text-sm text-muted-foreground">← Наряды-допуски</Link>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-medium">
            Наряд {wp.number ?? "(без номера)"} <StatusBadge label={labelOf(STATUS_LABELS, wp.status)} />
          </h1>
          <p className="text-sm text-muted-foreground">
            {labelOf(WORK_TYPE_LABELS, wp.work_type)} · {wp.zone_text}
            {wp.subdivision_text ? ` · ${wp.subdivision_text}` : ""}
          </p>
        </div>
        <Can permission={PERMISSIONS.WORK_PERMIT_MANAGE}>
          <div className="flex flex-wrap gap-2 justify-end">
            {wp.status === "draft" && (
              <WorkPermitFormDialog trigger={<Button variant="outline">Изменить</Button>} initialData={wp} onSubmitted={() => reload()} />
            )}
            {(ACTIONS_BY_STATUS[wp.status] ?? []).map((a) => (
              <Button key={a.name} variant="outline" onClick={() => runAction(a.name)}>{a.label}</Button>
            ))}
            {wp.status === "draft" && (
              <Button variant="outline" onClick={async () => {
                try { await workPermitsApi.remove(wp.id); toast.success("Удалено"); navigate("/work-permits"); }
                catch { toast.error("Не удалось удалить"); }
              }}>Удалить</Button>
            )}
          </div>
        </Can>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-md border p-3 space-y-2">
          <div className="text-sm font-medium">Сведения</div>
          <Section title="Содержание работ" value={wp.content_text} />
          <Section title="Условия проведения" value={wp.conditions_text} />
          <Section title="Опасные факторы" value={wp.hazards_text} />
          <Section title="Системы безопасности" value={(wp.safety_systems ?? []).map((c) => SAFETY_SYSTEM_LABELS[c] ?? c).join(", ") || null} />
          <Section title="Мероприятия до начала" value={wp.measures_before_text} />
          <Section title="Мероприятия в процессе" value={wp.measures_during_text} />
          <Section title="Особые условия" value={wp.special_conditions_text} />
          <Section title="СИЗ" value={wp.ppe_text} />
        </div>

        <div className="space-y-4">
          <div className="rounded-md border p-3">
            <div className="text-sm font-medium mb-2">Бригада</div>
            <ul className="space-y-1 text-sm">
              {wp.members.map((m) => (
                <li key={m.id} className="flex justify-between">
                  <span>{nameOf(m.person_id)}</span>
                  <span className="text-muted-foreground">{labelOf(MEMBER_ROLE_LABELS, m.role)}</span>
                </li>
              ))}
              {wp.members.length === 0 && <li className="text-muted-foreground">Пусто</li>}
            </ul>
          </div>
          <div className="rounded-md border p-3">
            <div className="text-sm font-medium mb-2">Готовность бригады</div>
            <ReadinessPanel report={readiness} nameOf={nameOf} />
          </div>
        </div>
      </div>

      <div className="rounded-md border p-3">
        <div className="text-sm font-medium mb-2">Журнал событий</div>
        <WorkPermitEventsTimeline events={events} />
      </div>
    </div>
  );
}
```

> NB: управление составом бригады (add/remove участника) — добавить отдельной панелью с выбором `persons` + роли, кнопки только при `wp.status === "draft"` и праве `WORK_PERMIT_MANAGE`; API `workPermitsApi.addMember/removeMember` уже готовы. Если объём шага велик — вынести `BrigadeMembersPanel` в отдельный коммит внутри этой задачи.

- [ ] **Step 4: Проверить типы/сборку**

Run: `npm --prefix frontend run build`
Expected: проходит.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/work-permits/WorkPermitDetailPage.tsx frontend/src/features/work-permits/ReadinessPanel.tsx frontend/src/features/work-permits/WorkPermitEventsTimeline.tsx
git commit -m "feat(work-permits): detail page — sections/brigade/readiness/actions/events"
```

---

### Task 14: Маршруты + меню + права

**Files:**
- Modify: `frontend/src/router/pageRegistry.tsx`
- Modify: `frontend/src/router/routeGroups.tsx`
- Modify: `frontend/src/router/navigationConfig.ts`

- [ ] **Step 1: Зарегистрировать страницы (pageRegistry)**

В `frontend/src/router/pageRegistry.tsx` добавить:

```tsx
export const WorkPermitsPage = lazy(() => import("@/pages/work-permits/WorkPermitsPage"));
export const WorkPermitDetailPage = lazy(() => import("@/pages/work-permits/WorkPermitDetailPage"));
```

- [ ] **Step 2: Добавить защищённые маршруты (routeGroups)**

В `frontend/src/router/routeGroups.tsx` (внутри сборки защищённых групп) добавить группу под `PERMISSIONS.WORK_PERMIT_VIEW`:

```tsx
{
  permission: PERMISSIONS.WORK_PERMIT_VIEW,
  routes: [
    <Route key="/work-permits" path="/work-permits" element={<WorkPermitsPage />} />,
    <Route key="/work-permits/:id" path="/work-permits/:id" element={<WorkPermitDetailPage />} />,
  ],
},
```

(импорты `WorkPermitsPage`, `WorkPermitDetailPage` из pageRegistry — добавить в существующий import.)

- [ ] **Step 3: Добавить пункт меню (navigationConfig)**

В `frontend/src/router/navigationConfig.ts`, в группе «ОТ и ПромБез» (`items`) добавить:

```ts
{ label: "Наряды-допуски", to: "/work-permits", icon: ClipboardCheck, permission: PERMISSIONS.WORK_PERMIT_VIEW },
```

(иконку `ClipboardCheck` импортировать из `lucide-react` рядом с другими; если имя занято — выбрать близкую по смыслу, напр. `FileCheck`.)

- [ ] **Step 4: Проверить сборку**

Run: `npm --prefix frontend run build`
Expected: проходит; маршруты `/work-permits` и `/work-permits/:id` зарегистрированы.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/router/pageRegistry.tsx frontend/src/router/routeGroups.tsx frontend/src/router/navigationConfig.ts
git commit -m "feat(work-permits): register routes + nav entry (admin-only)"
```

---

### Task 15: Тест карточки (действия по статусу + гейт прав)

**Files:**
- Create: `frontend/src/__tests__/WorkPermitDetailPage.test.tsx`

- [ ] **Step 1: Написать тест**

Create `frontend/src/__tests__/WorkPermitDetailPage.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PERMISSIONS } from "@/permissions/permissions";
import WorkPermitDetailPage from "@/pages/work-permits/WorkPermitDetailPage";
import { useAuthStore } from "@/stores/auth";

const getMock = vi.fn();
vi.mock("@/api/workPermits", () => ({
  workPermitsApi: {
    get: (...a: unknown[]) => getMock(...a),
    readiness: () => Promise.resolve({ ok: true, violations: [] }),
    events: () => Promise.resolve([]),
  },
  fetchAllPersons: () => Promise.resolve([]),
}));

const draft = {
  id: "wp1", number: "НД-1", work_type: "height", zone_text: "фасад", status: "draft",
  members: [], safety_systems: ["fall_arrest"], content_text: "монтаж",
  conditions_text: null, hazards_text: null, measures_before_text: null, measures_during_text: null,
  special_conditions_text: null, ppe_text: null, subdivision_text: null, site_id: null,
  equipment_text: null, measures_text: null, planned_start: null, planned_end: null,
  opened_at: null, closed_at: null, suspended_at: null, created_at: "", updated_at: "",
};

const renderAt = () =>
  render(
    <MemoryRouter initialEntries={["/work-permits/wp1"]}>
      <Routes><Route path="/work-permits/:id" element={<WorkPermitDetailPage />} /></Routes>
    </MemoryRouter>,
  );

const setRole = (perms: string[]) =>
  useAuthStore.setState({
    user: { id: "u1", roles: ["admin"], permissions: perms } as never,
    loading: false, error: null, isAuthenticated: true, initialized: true,
  });

describe("WorkPermitDetailPage", () => {
  beforeEach(() => { getMock.mockReset(); getMock.mockResolvedValue(draft); });

  it("показывает «Выдать» у черновика при праве manage", async () => {
    setRole([PERMISSIONS.WORK_PERMIT_VIEW, PERMISSIONS.WORK_PERMIT_MANAGE]);
    renderAt();
    expect(await screen.findByRole("button", { name: /выдать/i })).toBeInTheDocument();
  });

  it("скрывает действия без права manage", async () => {
    setRole([PERMISSIONS.WORK_PERMIT_VIEW]);
    renderAt();
    await screen.findByText(/монтаж/i);
    expect(screen.queryByRole("button", { name: /выдать/i })).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Прогнать тест**

Run: `npm --prefix frontend run test -- WorkPermitDetailPage`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/__tests__/WorkPermitDetailPage.test.tsx
git commit -m "test(work-permits): detail page actions + permission gate"
```

---

### Task 16: Полная верификация

- [ ] **Step 1: Backend контур**

Run: `python -m pytest backend/tests/test_work_permit_lifecycle.py backend/tests/test_wp02_work_permit_782n_migration.py backend/tests/test_work_permit_schemas_782n.py tests/test_work_permit_service.py tests/api/test_work_permits_api.py tests/api/test_work_permit_782n_fields.py -v`
Expected: всё PASS (отметить версию Python, если не 3.12).

- [ ] **Step 2: Frontend тесты + типы + сборка**

Run: `npm --prefix frontend run test -- WorkPermits WorkPermitDetailPage` then `npm --prefix frontend run build`
Expected: тесты PASS; сборка без ошибок типов.

- [ ] **Step 3: Ручная проверка (preview)**

Запустить dev-preview, войти под admin, открыть `/work-permits`: создать наряд по форме, открыть карточку, собрать бригаду, проверить «Выдать»/готовность/журнал. Зафиксировать скриншот.

- [ ] **Step 4: Финальный commit (если остались незакоммиченные правки)**

```bash
git add -A && git commit -m "chore(work-permits): Ф1 verification fixes" || echo "nothing to commit"
```

---

## Self-Review (выполнено автором плана)

- **Покрытие спеки:** §4 модель → Task 2/3; §5 схемы/сервис/роуты → Task 1/4/5/6; §6 фронт-архитектура → Task 7-14; §7 секции формы → Task 11; §8 действия/FSM → Task 13; §9 готовность/события → Task 13; §11 тесты → Task 6/12/15/16; §3 права → Task 7/14. Гэпов нет.
- **Плейсхолдеры:** в шагах с кодом приведён полный код; `NB`-пометки указывают точки сверки с существующими файлами (имена фикстур/пропсов), не заглушки логики.
- **Согласованность типов:** `WorkPermitDto`/`workPermitsApi`/`workPermitSchema`/коды прав/словари используются единообразно во всех задачах; `safety_systems` — `list[str]`/`string[]` сквозь backend↔frontend.
