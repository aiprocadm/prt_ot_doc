# Наряд-допуск на высоте (782н) — Ф3a «журнал эксплуатации» — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать наряду в статусе `issued` операционный журнал: ежедневный допуск к работе (таблица), структурный журнал продлений (было→стало) и журналируемую смену состава бригады — всё поверх существующих `WorkPermitEvent`/`WorkPermitMember`, без изменения FSM.

**Architecture:** Full-stack, аддитивно. Backend: миграция `wp04` добавляет таблицу `work_permit_daily_admission` И колонку `meta`(JSON) у `work_permit_event`; сервис журналирует продления/смену состава через обогащённый `_log(meta=...)` и даёт CRUD ежедневного допуска (гейт `issued`); 3 новых типа событий. Frontend: панель допуска + рендер `meta` в ленте + редактирование бригады в `issued`.

**Tech Stack:** Python/FastAPI/SQLAlchemy/Alembic (backend); React/Vite/TypeScript, axios (`apiClient`), vitest (frontend).

**Spec:** `docs/superpowers/specs/2026-06-18-work-permit-782n-ops-journal-design.md`

**Branch:** `feat/work-permits-782n-ops-journal` (стек поверх Ф2 `feat/work-permits-782n-signatures`, HEAD `9ab3b35`).

**Тесты (среда):** venv **Py3.13.7** локально (`.venv`); фикстуры БД — `sessionmaker` + `data_factory` (`data_factory.create_person()`); API-тесты — `async_client` + `make_auth_headers(RoleEnum.ADMIN)`, пути с префиксом `/api/v1`. Канон CI = Py3.12.12. Не запускать `make cs:test`. Миграция-guard — source-level (как wp02/wp03). Frontend: `npm --prefix frontend run test -- <file>`, `npm --prefix frontend run build`.

**Реестр имён (сквозь план):**
- Новые типы событий: `admitted`, `member_added`, `member_removed`.
- `meta`(JSON): `extended`→`{"old_end": iso|None, "new_end": iso|None}`; `member_added`/`member_removed`→`{"person_id": str, "role": str}`.
- Ежедневный допуск доступен только когда наряд `issued`.

---

## Часть A — Backend

### Task 1: Новые типы событий (lifecycle)

**Files:**
- Modify: `backend/app/domains/work_permits/lifecycle.py:29-31`
- Test: `backend/tests/test_work_permit_lifecycle.py`

- [ ] **Step 1: Написать падающий тест**

Добавить в `backend/tests/test_work_permit_lifecycle.py`:

```python
def test_event_types_include_ops_journal():
    from app.domains.work_permits import lifecycle as lc

    assert {"admitted", "member_added", "member_removed"}.issubset(lc.EVENT_TYPES)
    # существующие сохранены
    assert {"issued", "suspended", "resumed", "closed", "cancelled", "extended"}.issubset(lc.EVENT_TYPES)
```

- [ ] **Step 2: Прогнать тест — должен упасть**

Run: `python -m pytest backend/tests/test_work_permit_lifecycle.py::test_event_types_include_ops_journal -v`
Expected: FAIL (новых типов нет).

- [ ] **Step 3: Реализовать**

В `backend/app/domains/work_permits/lifecycle.py` заменить блок `EVENT_TYPES` (строки 29-31):

```python
EVENT_TYPES = frozenset({
    "issued", "suspended", "resumed", "closed", "cancelled", "extended",
    "admitted", "member_added", "member_removed",
})
```

- [ ] **Step 4: Прогнать тест — должен пройти**

Run: `python -m pytest backend/tests/test_work_permit_lifecycle.py::test_event_types_include_ops_journal -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/work_permits/lifecycle.py backend/tests/test_work_permit_lifecycle.py
git commit -m "feat(work-permits): ops-journal event types (admitted/member_added/member_removed)"
```

---

### Task 2: Миграция wp04 — таблица допуска + колонка meta

**Files:**
- Create: `backend/app/migrations/versions/20260618_wp04_work_permit_ops_journal.py`
- Test: `backend/tests/test_wp04_work_permit_ops_journal_migration.py`

- [ ] **Step 1: Подтвердить head**

Истинный head ветки наряда — `20260618_wp03_work_permit_briefing` (детей нет). `down_revision` = именно эта ревизия.

- [ ] **Step 2: Написать падающий тест (guard, source-level)**

Create `backend/tests/test_wp04_work_permit_ops_journal_migration.py`:

```python
"""Guard: wp04 chains from wp03, creates daily_admission table + adds event.meta."""
import importlib.util
from pathlib import Path

MIG = (
    Path(__file__).resolve().parents[1]
    / "app/migrations/versions/20260618_wp04_work_permit_ops_journal.py"
)

ADMISSION_COLUMNS = {
    "work_permit_id", "admission_date", "start_at", "end_at",
    "admitted_by_person_id", "note",
}


def _load():
    spec = importlib.util.spec_from_file_location("wp04_mig", MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_wp04_chain_and_revision():
    mod = _load()
    assert mod.revision == "20260618_wp04_work_permit_ops_journal"
    assert mod.down_revision == "20260618_wp03_work_permit_briefing"


def test_wp04_source_table_and_meta_column():
    src = MIG.read_text(encoding="utf-8")
    assert 'create_table(\n        "work_permit_daily_admission"' in src or 'create_table("work_permit_daily_admission"' in src
    for col in ADMISSION_COLUMNS:
        assert f'"{col}"' in src, f"missing admission column literal: {col}"
    assert 'add_column("work_permit_event"' in src and '"meta"' in src, "must add event.meta"
    # honest downgrade: both drop_column(meta) and drop_table(admission)
    assert 'drop_column("work_permit_event", "meta")' in src
    assert 'drop_table("work_permit_daily_admission")' in src
```

- [ ] **Step 3: Прогнать тест — должен упасть**

Run: `python -m pytest backend/tests/test_wp04_work_permit_ops_journal_migration.py -v`
Expected: FAIL (файла нет).

- [ ] **Step 4: Написать миграцию**

Create `backend/app/migrations/versions/20260618_wp04_work_permit_ops_journal.py`:

```python
"""wp04: ops-journal (Ф3a) — daily-admission table + event.meta column (additive).

New table work_permit_daily_admission (FK→work_permit CASCADE, FK→person SET NULL)
and a nullable JSON `meta` column on work_permit_event for structured extend /
crew-change details. Table names LITERAL (AST-audit blindspot). Honest downgrade
drops the column then the table.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260618_wp04_work_permit_ops_journal"
down_revision = "20260618_wp03_work_permit_briefing"
branch_labels = None
depends_on = None


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    ]


def upgrade() -> None:
    op.create_table(
        "work_permit_daily_admission",
        *_base_columns(),
        sa.Column("work_permit_id", sa.String(length=36), nullable=False),
        sa.Column("admission_date", sa.Date(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("admitted_by_person_id", sa.String(length=36), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["work_permit_id"], ["work_permit.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["admitted_by_person_id"], ["person.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_work_permit_daily_admission_permit",
        "work_permit_daily_admission", ["work_permit_id"],
    )
    op.add_column("work_permit_event", sa.Column("meta", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("work_permit_event", "meta")
    op.drop_table("work_permit_daily_admission")
```

- [ ] **Step 5: Прогнать тест — должен пройти**

Run: `python -m pytest backend/tests/test_wp04_work_permit_ops_journal_migration.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/migrations/versions/20260618_wp04_work_permit_ops_journal.py backend/tests/test_wp04_work_permit_ops_journal_migration.py
git commit -m "feat(work-permits): wp04 migration — daily_admission table + event.meta"
```

---

### Task 3: Модели — meta у события + WorkPermitDailyAdmission

**Files:**
- Modify: `backend/app/models/work_permit.py`
- Test: `backend/tests/test_wp04_work_permit_ops_journal_migration.py` (добавить shape-тесты)

- [ ] **Step 1: Написать падающий тест**

Добавить в `backend/tests/test_wp04_work_permit_ops_journal_migration.py`:

```python
def test_event_model_has_meta():
    from app.models.work_permit import WorkPermitEvent

    assert "meta" in WorkPermitEvent.__table__.columns.keys()


def test_daily_admission_model_columns():
    from app.models.work_permit import WorkPermitDailyAdmission

    cols = set(WorkPermitDailyAdmission.__table__.columns.keys())
    assert ADMISSION_COLUMNS.issubset(cols)
    assert WorkPermitDailyAdmission.__tablename__ == "work_permit_daily_admission"
```

- [ ] **Step 2: Прогнать тест — должен упасть**

Run: `python -m pytest backend/tests/test_wp04_work_permit_ops_journal_migration.py::test_daily_admission_model_columns -v`
Expected: FAIL (`ImportError: cannot import name 'WorkPermitDailyAdmission'`).

- [ ] **Step 3: Реализовать**

В `backend/app/models/work_permit.py`:

1) Расширить импорты:
- строка `from datetime import datetime` → `from datetime import date, datetime`;
- строка sqlalchemy-импорта (добавить `Date`): `from sqlalchemy import Date, DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint, func`.

2) В классе `WorkPermitEvent` после `note`-колонки добавить:

```python
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

3) В конец файла добавить:

```python
class WorkPermitDailyAdmission(TenantBaseModel):
    __tablename__ = "work_permit_daily_admission"

    work_permit_id: Mapped[str] = mapped_column(
        ForeignKey("work_permit.id", ondelete="CASCADE"), nullable=False, index=True
    )
    admission_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    admitted_by_person_id: Mapped[str | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 4: Прогнать тест — должен пройти**

Run: `python -m pytest backend/tests/test_wp04_work_permit_ops_journal_migration.py -v`
Expected: PASS (все тесты файла).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/work_permit.py backend/tests/test_wp04_work_permit_ops_journal_migration.py
git commit -m "feat(work-permits): event.meta + WorkPermitDailyAdmission models"
```

---

### Task 4: Журналирование продлений и смены состава (сервис)

**Files:**
- Modify: `backend/app/domains/work_permits/service.py`
- Test: `tests/test_work_permit_service.py`

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/test_work_permit_service.py` (фикстуры `sessionmaker`/`data_factory` — как в соседних тестах файла):

```python
@pytest.mark.asyncio
async def test_extend_logs_old_and_new_end(sessionmaker, data_factory):
    from datetime import datetime, timezone
    from app.domains.work_permits import create_work_permit, issue, extend, list_events

    async with sessionmaker() as session:
        tenant = await data_factory.create_tenant()
        wp = await create_work_permit(session, tenant_id=tenant.id, work_type="height", zone_text="z",
                                      planned_end=datetime(2026, 6, 18, tzinfo=timezone.utc))
        await issue(session, tenant_id=tenant.id, work_permit_id=wp.id, actor_user_id="u1")
        new_end = datetime(2026, 6, 20, tzinfo=timezone.utc)
        await extend(session, tenant_id=tenant.id, work_permit_id=wp.id, planned_end=new_end, actor_user_id="u1")
        events = await list_events(session, tenant_id=tenant.id, work_permit_id=wp.id)
        ext = [e for e in events if e.event_type == "extended"][-1]
        assert ext.meta["new_end"].startswith("2026-06-20")
        assert ext.meta["old_end"].startswith("2026-06-18")


@pytest.mark.asyncio
async def test_member_changes_are_logged(sessionmaker, data_factory):
    from app.domains.work_permits import add_member, remove_member, create_work_permit, list_events

    async with sessionmaker() as session:
        tenant = await data_factory.create_tenant()
        person = await data_factory.create_person(tenant_id=tenant.id)
        wp = await create_work_permit(session, tenant_id=tenant.id, work_type="height", zone_text="z")
        m = await add_member(session, tenant_id=tenant.id, work_permit_id=wp.id,
                             person_id=person.id, role="member", actor_user_id="u1")
        await remove_member(session, tenant_id=tenant.id, work_permit_id=wp.id,
                            member_id=m.id, actor_user_id="u1")
        events = await list_events(session, tenant_id=tenant.id, work_permit_id=wp.id)
        types = [e.event_type for e in events]
        assert "member_added" in types and "member_removed" in types
        added = [e for e in events if e.event_type == "member_added"][0]
        assert added.meta == {"person_id": person.id, "role": "member"}
```

> NB: имена/сигнатуры фикстур (`sessionmaker`, `data_factory.create_tenant`, `data_factory.create_person`) — взять точно как в соседних тестах `tests/test_work_permit_service.py`; если `create_tenant`/`create_person` называются/вызываются иначе, выровнять.

- [ ] **Step 2: Прогнать тест — должен упасть**

Run: `python -m pytest tests/test_work_permit_service.py::test_extend_logs_old_and_new_end tests/test_work_permit_service.py::test_member_changes_are_logged -v`
Expected: FAIL (`add_member` не принимает `actor_user_id`; `meta` пустой).

- [ ] **Step 3: Реализовать**

В `backend/app/domains/work_permits/service.py`:

1) Расширить `_log` параметром `meta`:

```python
async def _log(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str, event_type: str,
    actor_user_id: str | None, photo_file_id: str | None = None, note: str | None = None,
    meta: dict | None = None,
) -> WorkPermitEvent:
    event = WorkPermitEvent(
        tenant_id=tenant_id, work_permit_id=work_permit_id, event_type=event_type,
        at=_now(), actor_user_id=actor_user_id, photo_file_id=photo_file_id, note=note,
        meta=meta,
    )
    session.add(event)
    await session.flush()
    return event
```

2) `add_member` — принять `actor_user_id` и залогировать:

```python
async def add_member(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str, person_id: str, role: str,
    actor_user_id: str | None = None,
) -> WorkPermitMember | None:
    wp = await _get(session, tenant_id, work_permit_id)
    if wp is None:
        return None
    if wp.status in _TERMINAL:
        raise lc.WorkPermitTransitionError(str(wp.status), "add_member")
    member = WorkPermitMember(
        tenant_id=tenant_id, work_permit_id=work_permit_id, person_id=person_id, role=role,
    )
    session.add(member)
    await session.flush()
    await session.refresh(member)
    await _log(
        session, tenant_id=tenant_id, work_permit_id=work_permit_id,
        event_type="member_added", actor_user_id=actor_user_id,
        meta={"person_id": person_id, "role": role},
    )
    return member
```

3) `remove_member` — принять `actor_user_id`, добавить терминальный гейт, залогировать с данными ДО удаления:

```python
async def remove_member(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str, member_id: str,
    actor_user_id: str | None = None,
) -> bool:
    stmt = select(WorkPermitMember).where(
        WorkPermitMember.id == member_id,
        WorkPermitMember.work_permit_id == work_permit_id,
        WorkPermitMember.tenant_id == tenant_id,
    )
    member = (await session.execute(stmt)).scalar_one_or_none()
    if member is None:
        return False
    wp = await _get(session, tenant_id, work_permit_id)
    if wp is not None and wp.status in _TERMINAL:
        raise lc.WorkPermitTransitionError(str(wp.status), "remove_member")
    person_id, role = member.person_id, member.role
    await session.delete(member)
    await session.flush()
    await _log(
        session, tenant_id=tenant_id, work_permit_id=work_permit_id,
        event_type="member_removed", actor_user_id=actor_user_id,
        meta={"person_id": person_id, "role": role},
    )
    return True
```

4) `extend` — записать old/new в meta:

```python
async def extend(session, *, tenant_id, work_permit_id, planned_end, actor_user_id, note=None):
    wp = await _get(session, tenant_id, work_permit_id)
    if wp is None:
        return None
    if wp.status not in (lc.STATUS_ISSUED, lc.STATUS_SUSPENDED):
        raise lc.WorkPermitTransitionError(str(wp.status), "extend")
    old_end = wp.planned_end
    wp.planned_end = planned_end
    await _log(
        session, tenant_id=tenant_id, work_permit_id=work_permit_id,
        event_type="extended", actor_user_id=actor_user_id, note=note,
        meta={
            "old_end": old_end.isoformat() if old_end else None,
            "new_end": planned_end.isoformat() if planned_end else None,
        },
    )
    await session.flush()
    await session.refresh(wp)
    return wp
```

- [ ] **Step 4: Прогнать тест — должен пройти**

Run: `python -m pytest tests/test_work_permit_service.py::test_extend_logs_old_and_new_end tests/test_work_permit_service.py::test_member_changes_are_logged -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/work_permits/service.py tests/test_work_permit_service.py
git commit -m "feat(work-permits): journal extend (old/new) + crew changes (events + meta)"
```

---

### Task 5: Ежедневный допуск — сервис

**Files:**
- Modify: `backend/app/domains/work_permits/service.py`
- Modify: `backend/app/domains/work_permits/__init__.py`
- Test: `tests/test_work_permit_service.py`

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/test_work_permit_service.py`:

```python
@pytest.mark.asyncio
async def test_daily_admission_requires_issued(sessionmaker, data_factory):
    from datetime import date
    from app.domains.work_permits import create_admission, create_work_permit, issue
    from app.domains.work_permits.lifecycle import WorkPermitTransitionError

    async with sessionmaker() as session:
        tenant = await data_factory.create_tenant()
        wp = await create_work_permit(session, tenant_id=tenant.id, work_type="height", zone_text="z")
        # draft → нельзя
        with pytest.raises(WorkPermitTransitionError):
            await create_admission(session, tenant_id=tenant.id, work_permit_id=wp.id,
                                   admission_date=date(2026, 6, 18))
        await issue(session, tenant_id=tenant.id, work_permit_id=wp.id, actor_user_id="u1")
        adm = await create_admission(session, tenant_id=tenant.id, work_permit_id=wp.id,
                                     admission_date=date(2026, 6, 18), note="смена 1")
        assert adm.admission_date == date(2026, 6, 18)
        assert adm.note == "смена 1"


@pytest.mark.asyncio
async def test_daily_admission_list_and_update(sessionmaker, data_factory):
    from datetime import date, datetime, timezone
    from app.domains.work_permits import (
        create_admission, create_work_permit, issue, list_admissions, update_admission,
    )

    async with sessionmaker() as session:
        tenant = await data_factory.create_tenant()
        wp = await create_work_permit(session, tenant_id=tenant.id, work_type="height", zone_text="z")
        await issue(session, tenant_id=tenant.id, work_permit_id=wp.id, actor_user_id="u1")
        adm = await create_admission(session, tenant_id=tenant.id, work_permit_id=wp.id,
                                     admission_date=date(2026, 6, 18))
        rows = await list_admissions(session, tenant_id=tenant.id, work_permit_id=wp.id)
        assert [a.id for a in rows] == [adm.id]
        end = datetime(2026, 6, 18, 17, tzinfo=timezone.utc)
        upd = await update_admission(session, tenant_id=tenant.id, admission_id=adm.id, end_at=end)
        assert upd.end_at == end
```

- [ ] **Step 2: Прогнать тест — должен упасть**

Run: `python -m pytest tests/test_work_permit_service.py::test_daily_admission_requires_issued -v`
Expected: FAIL (`ImportError: cannot import name 'create_admission'`).

- [ ] **Step 3: Реализовать**

1) В `backend/app/domains/work_permits/service.py` заменить строку импорта моделей на:

```python
from app.models.work_permit import (
    WorkPermit, WorkPermitBriefing, WorkPermitDailyAdmission, WorkPermitEvent, WorkPermitMember,
)
```

> NB: если в текущем файле модели импортируются другой строкой (после Ф2 там уже есть `WorkPermitBriefing`) — просто добавить `WorkPermitDailyAdmission` в существующий импорт.

2) В конец `service.py` добавить (после briefing-функций Ф2):

```python
# --- ежедневный допуск (Ф3a) -----------------------------------------------

async def create_admission(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str, admission_date,
    start_at: datetime | None = None, end_at: datetime | None = None,
    admitted_by_person_id: str | None = None, note: str | None = None,
    actor_user_id: str | None = None,
) -> WorkPermitDailyAdmission | None:
    wp = await _get(session, tenant_id, work_permit_id)
    if wp is None:
        return None
    if wp.status != lc.STATUS_ISSUED:
        raise lc.WorkPermitTransitionError(str(wp.status), "daily_admission")
    adm = WorkPermitDailyAdmission(
        tenant_id=tenant_id, work_permit_id=work_permit_id, admission_date=admission_date,
        start_at=start_at, end_at=end_at, admitted_by_person_id=admitted_by_person_id, note=note,
    )
    session.add(adm)
    await session.flush()
    await session.refresh(adm)
    await _log(
        session, tenant_id=tenant_id, work_permit_id=work_permit_id,
        event_type="admitted", actor_user_id=actor_user_id,
        meta={"admission_id": adm.id, "admission_date": admission_date.isoformat()},
    )
    return adm


async def list_admissions(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str,
) -> list[WorkPermitDailyAdmission]:
    stmt = select(WorkPermitDailyAdmission).where(
        WorkPermitDailyAdmission.tenant_id == tenant_id,
        WorkPermitDailyAdmission.work_permit_id == work_permit_id,
    ).order_by(WorkPermitDailyAdmission.admission_date.asc(),
               WorkPermitDailyAdmission.created_at.asc())
    return list((await session.execute(stmt)).scalars().all())


async def get_admission(
    session: AsyncSession, *, tenant_id: str, admission_id: str,
) -> WorkPermitDailyAdmission | None:
    stmt = select(WorkPermitDailyAdmission).where(
        WorkPermitDailyAdmission.id == admission_id,
        WorkPermitDailyAdmission.tenant_id == tenant_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


_ADMISSION_EDITABLE = ("start_at", "end_at", "admitted_by_person_id", "note")


async def update_admission(
    session: AsyncSession, *, tenant_id: str, admission_id: str, **fields,
) -> WorkPermitDailyAdmission | None:
    adm = await get_admission(session, tenant_id=tenant_id, admission_id=admission_id)
    if adm is None:
        return None
    for key, value in fields.items():
        if key in _ADMISSION_EDITABLE:
            setattr(adm, key, value)
    await session.flush()
    await session.refresh(adm)
    return adm
```

3) В `backend/app/domains/work_permits/__init__.py` добавить в импорт из `service` и в `__all__`: `create_admission`, `get_admission`, `list_admissions`, `update_admission`.

- [ ] **Step 4: Прогнать тест — должен пройти**

Run: `python -m pytest tests/test_work_permit_service.py::test_daily_admission_requires_issued tests/test_work_permit_service.py::test_daily_admission_list_and_update -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/work_permits/service.py backend/app/domains/work_permits/__init__.py tests/test_work_permit_service.py
git commit -m "feat(work-permits): daily-admission CRUD service (issued-gated)"
```

---

### Task 6: Схемы — допуск + meta у события

**Files:**
- Modify: `backend/app/schemas/work_permit.py`
- Test: `backend/tests/test_work_permit_admission_schemas.py`

- [ ] **Step 1: Написать падающий тест**

Create `backend/tests/test_work_permit_admission_schemas.py`:

```python
from datetime import date

from app.schemas.work_permit import WorkPermitDailyAdmissionCreate, WorkPermitEventRead


def test_admission_create_minimal():
    a = WorkPermitDailyAdmissionCreate(admission_date=date(2026, 6, 18))
    assert a.admission_date == date(2026, 6, 18)
    assert a.note is None


def test_event_read_has_meta_field():
    assert "meta" in WorkPermitEventRead.model_fields
```

- [ ] **Step 2: Прогнать тест — должен упасть**

Run: `python -m pytest backend/tests/test_work_permit_admission_schemas.py -v`
Expected: FAIL (`ImportError: cannot import name 'WorkPermitDailyAdmissionCreate'`).

- [ ] **Step 3: Реализовать**

В `backend/app/schemas/work_permit.py`:

1) В `WorkPermitEventRead` (после `note`) добавить:

```python
    meta: dict | None = None
```

2) Расширить импорт `datetime` сверху файла: `from datetime import date, datetime`.

3) В конец файла добавить:

```python
class WorkPermitDailyAdmissionCreate(BaseSchema):
    admission_date: date
    start_at: datetime | None = None
    end_at: datetime | None = None
    admitted_by_person_id: str | None = None
    note: str | None = None


class WorkPermitDailyAdmissionUpdate(BaseSchema):
    start_at: datetime | None = None
    end_at: datetime | None = None
    admitted_by_person_id: str | None = None
    note: str | None = None


class WorkPermitDailyAdmissionRead(BaseSchema):
    id: str
    work_permit_id: str
    admission_date: date
    start_at: datetime | None
    end_at: datetime | None
    admitted_by_person_id: str | None
    note: str | None
    created_at: datetime
    updated_at: datetime
```

- [ ] **Step 4: Прогнать тест — должен пройти**

Run: `python -m pytest backend/tests/test_work_permit_admission_schemas.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/work_permit.py backend/tests/test_work_permit_admission_schemas.py
git commit -m "feat(work-permits): daily-admission schemas + event.meta read field"
```

---

### Task 7: API — допуск + meta в событиях + actor смены состава

**Files:**
- Modify: `backend/app/api/routes/work_permits.py`
- Test: `tests/api/test_work_permit_admission_api.py`

- [ ] **Step 1: Написать падающий тест**

Create `tests/api/test_work_permit_admission_api.py`:

```python
from __future__ import annotations

import pytest
from app.models.models import RoleEnum

BASE = "/api/v1/work-permits"


async def _issued_permit(async_client, headers) -> str:
    r = await async_client.post(BASE, headers=headers, json={"work_type": "height", "zone_text": "z"})
    wp_id = r.json()["id"]
    iss = await async_client.post(f"{BASE}/{wp_id}/issue", headers=headers, json={})
    assert iss.status_code == 200, iss.text
    return wp_id


@pytest.mark.asyncio
async def test_admission_create_list_patch(async_client, make_auth_headers, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    wp_id = await _issued_permit(async_client, headers)

    r = await async_client.post(
        f"{BASE}/{wp_id}/admissions", headers=headers,
        json={"admission_date": "2026-06-18", "note": "смена 1"},
    )
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    assert r.json()["work_permit_id"] == wp_id

    lst = await async_client.get(f"{BASE}/{wp_id}/admissions", headers=headers)
    assert lst.status_code == 200
    assert [a["id"] for a in lst.json()] == [aid]

    upd = await async_client.patch(
        f"{BASE}/{wp_id}/admissions/{aid}", headers=headers,
        json={"end_at": "2026-06-18T17:00:00+00:00"},
    )
    assert upd.status_code == 200
    assert upd.json()["end_at"].startswith("2026-06-18T17:00")


@pytest.mark.asyncio
async def test_admission_rejected_when_not_issued(async_client, make_auth_headers, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    r = await async_client.post(BASE, headers=headers, json={"work_type": "height", "zone_text": "z"})
    wp_id = r.json()["id"]  # draft
    a = await async_client.post(
        f"{BASE}/{wp_id}/admissions", headers=headers, json={"admission_date": "2026-06-18"}
    )
    assert a.status_code == 409, a.text


@pytest.mark.asyncio
async def test_member_add_emits_event_with_meta(async_client, make_auth_headers, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    wp_id = await _issued_permit(async_client, headers)
    person = await data_factory.create_person()
    add = await async_client.post(
        f"{BASE}/{wp_id}/members", headers=headers, json={"person_id": person.id, "role": "member"}
    )
    assert add.status_code == 201, add.text
    evs = await async_client.get(f"{BASE}/{wp_id}/events", headers=headers)
    added = [e for e in evs.json() if e["event_type"] == "member_added"]
    assert added and added[0]["meta"]["person_id"] == person.id
```

> NB: `data_factory.create_person()` — как в `tests/api/test_work_permit_signatures_api.py`; если требует tenant-аргумент или иной вызов, выровнять.

- [ ] **Step 2: Прогнать тест — должен упасть**

Run: `python -m pytest tests/api/test_work_permit_admission_api.py -v`
Expected: FAIL (admissions-эндпоинтов нет; в `member_added`-события нет, т.к. роут не передаёт actor / событие может писаться, но эндпоинта admissions нет).

- [ ] **Step 3: Реализовать**

В `backend/app/api/routes/work_permits.py`:

1) Дополнить доменный импорт именами допуска:

```python
from app.domains.work_permits import (
    add_member, cancel, close, create_admission, create_briefing, create_work_permit,
    delete_draft, extend, get_briefing, issue, list_admissions, list_briefings, list_events,
    list_members, remove_member, resume, suspend, update_admission, update_briefing,
    update_work_permit,
)
```

2) Дополнить импорт схем: добавить `WorkPermitDailyAdmissionCreate, WorkPermitDailyAdmissionRead, WorkPermitDailyAdmissionUpdate`.

3) В `events`-эндпоинте добавить `meta` в конструктор `WorkPermitEventRead` (там, где собираются события):

```python
    return [WorkPermitEventRead(
        id=str(e.id), event_type=e.event_type, at=e.at, actor_user_id=e.actor_user_id,
        photo_file_id=e.photo_file_id, note=e.note, meta=e.meta,
    ) for e in rows]
```

4) Передать `actor_user_id` в `add_member`/`remove_member` из роутов:
- в `add_member_endpoint` вызов `add_member(...)` дополнить `actor_user_id=access.user.id if access else None`;
- в `remove_member_endpoint` вызов `remove_member(...)` дополнить `actor_user_id=access.user.id if access else None`; и обернуть в try/except `lc.WorkPermitTransitionError` → `_transition_conflict` (теперь remove может бросить терминальный гейт):

```python
    try:
        ok = await remove_member(
            session, tenant_id=tenant.id, work_permit_id=wp_id, member_id=member_id,
            actor_user_id=access.user.id if access else None,
        )
    except lc.WorkPermitTransitionError as exc:
        raise _transition_conflict(exc) from exc
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "member not found")
```

5) После briefing-хелперов добавить admission read-хелпер:

```python
def _admission_read(a) -> WorkPermitDailyAdmissionRead:
    return WorkPermitDailyAdmissionRead(
        id=str(a.id), work_permit_id=str(a.work_permit_id), admission_date=a.admission_date,
        start_at=a.start_at, end_at=a.end_at,
        admitted_by_person_id=str(a.admitted_by_person_id) if a.admitted_by_person_id else None,
        note=a.note, created_at=a.created_at, updated_at=a.updated_at,
    )
```

6) В конец файла добавить эндпоинты допуска:

```python
@router.post("/{wp_id}/admissions", response_model=WorkPermitDailyAdmissionRead, status_code=status.HTTP_201_CREATED)
@audit_operation("update", "work_permit")
async def create_admission_endpoint(
    wp_id: str, payload: WorkPermitDailyAdmissionCreate, tenant: TenantDep, session: SessionDep, access: WriterAccess
) -> WorkPermitDailyAdmissionRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    if payload.admitted_by_person_id:
        await _ensure_person(session, tenant, payload.admitted_by_person_id)
    try:
        adm = await create_admission(
            session, tenant_id=tenant.id, work_permit_id=wp_id,
            admission_date=payload.admission_date, start_at=payload.start_at, end_at=payload.end_at,
            admitted_by_person_id=payload.admitted_by_person_id, note=payload.note,
            actor_user_id=access.user.id if access else None,
        )
    except lc.WorkPermitTransitionError as exc:
        raise _transition_conflict(exc) from exc
    if adm is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "work permit not found")
    return _admission_read(adm)


@router.get("/{wp_id}/admissions", response_model=list[WorkPermitDailyAdmissionRead])
async def list_admissions_endpoint(
    wp_id: str, tenant: TenantDep, session: SessionDep, access: ReaderAccess
) -> list[WorkPermitDailyAdmissionRead]:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    rows = await list_admissions(session, tenant_id=tenant.id, work_permit_id=wp_id)
    return [_admission_read(a) for a in rows]


@router.patch("/{wp_id}/admissions/{admission_id}", response_model=WorkPermitDailyAdmissionRead)
@audit_operation("update", "work_permit")
async def update_admission_endpoint(
    wp_id: str, admission_id: str, payload: WorkPermitDailyAdmissionUpdate,
    tenant: TenantDep, session: SessionDep, access: WriterAccess,
) -> WorkPermitDailyAdmissionRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    fields = payload.model_dump(exclude_unset=True)
    if fields.get("admitted_by_person_id"):
        await _ensure_person(session, tenant, fields["admitted_by_person_id"])
    # admission must belong to THIS permit (not just the same tenant)
    from app.domains.work_permits import get_admission
    existing = await get_admission(session, tenant_id=tenant.id, admission_id=admission_id)
    if existing is None or str(existing.work_permit_id) != wp_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "admission not found")
    adm = await update_admission(session, tenant_id=tenant.id, admission_id=admission_id, **fields)
    return _admission_read(adm)
```

> NB: импорт схем `WorkPermitDailyAdmission*` добавить в существующую строку `from app.schemas.work_permit import (...)`. `get_admission` можно импортировать сверху вместе с остальными доменными функциями вместо локального импорта — выбрать единый стиль файла.

- [ ] **Step 4: Прогнать тест — должен пройти**

Run: `python -m pytest tests/api/test_work_permit_admission_api.py -v`
Expected: PASS.

- [ ] **Step 5: Прогон backend-контура Ф3a**

Run: `python -m pytest backend/tests/test_work_permit_lifecycle.py backend/tests/test_wp04_work_permit_ops_journal_migration.py backend/tests/test_work_permit_admission_schemas.py tests/test_work_permit_service.py tests/api/test_work_permit_admission_api.py tests/api/test_work_permits_api.py -v`
Expected: PASS (контур + регрессия Ф1; отметить версию Python).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/work_permits.py tests/api/test_work_permit_admission_api.py
git commit -m "feat(work-permits): daily-admission API + event.meta + crew-change actor"
```

---

## Часть B — Frontend

### Task 8: DTO + словарь типов событий

**Files:**
- Modify: `frontend/src/types/dto/workPermits.ts`
- Modify: `frontend/src/lib/workPermitVocab.ts`

- [ ] **Step 1: Реализовать DTO**

В `frontend/src/types/dto/workPermits.ts`:

1) В `WorkPermitEventDto` добавить поле `meta`:

```ts
  meta: Record<string, string | null> | null;
```

2) В конец файла добавить:

```ts
export interface WorkPermitDailyAdmissionDto {
  id: string;
  work_permit_id: string;
  admission_date: string;
  start_at: string | null;
  end_at: string | null;
  admitted_by_person_id: string | null;
  note: string | null;
  created_at: string;
  updated_at: string;
}
```

- [ ] **Step 2: Реализовать словарь**

В `frontend/src/lib/workPermitVocab.ts` в объект `EVENT_TYPE_LABELS` добавить:

```ts
  admitted: "Ежедневный допуск",
  member_added: "Добавлен участник",
  member_removed: "Удалён участник",
```

- [ ] **Step 3: Проверить типы**

Run: `npm --prefix frontend run build`
Expected: проходит.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/dto/workPermits.ts frontend/src/lib/workPermitVocab.ts
git commit -m "feat(work-permits): daily-admission DTO + event.meta + event labels"
```

---

### Task 9: API-модуль — допуск

**Files:**
- Modify: `frontend/src/api/workPermits.ts`

- [ ] **Step 1: Реализовать**

В `frontend/src/api/workPermits.ts`:

1) Дополнить импорт DTO именем `WorkPermitDailyAdmissionDto`.

2) В объект `workPermitsApi` добавить методы:

```ts
  async listAdmissions(id: string): Promise<WorkPermitDailyAdmissionDto[]> {
    return (await apiClient.get<WorkPermitDailyAdmissionDto[]>(`${base}/${id}/admissions`)).data;
  },
  async createAdmission(id: string, body: Record<string, unknown>): Promise<WorkPermitDailyAdmissionDto> {
    return (await apiClient.post<WorkPermitDailyAdmissionDto>(`${base}/${id}/admissions`, body)).data;
  },
  async updateAdmission(
    id: string, admissionId: string, body: Record<string, unknown>,
  ): Promise<WorkPermitDailyAdmissionDto> {
    return (await apiClient.patch<WorkPermitDailyAdmissionDto>(`${base}/${id}/admissions/${admissionId}`, body)).data;
  },
```

- [ ] **Step 2: Проверить типы**

Run: `npm --prefix frontend run build`
Expected: проходит.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/workPermits.ts
git commit -m "feat(work-permits): api — daily admissions"
```

---

### Task 10: Лента событий — рендер meta

**Files:**
- Modify: `frontend/src/features/work-permits/WorkPermitEventsTimeline.tsx`
- Modify: `frontend/src/pages/work-permits/WorkPermitDetailPage.tsx` (передать `nameOf`)

- [ ] **Step 1: Реализовать рендер meta**

Заменить содержимое `frontend/src/features/work-permits/WorkPermitEventsTimeline.tsx`:

```tsx
import type { WorkPermitEventDto } from "@/types/dto/workPermits";
import { EVENT_TYPE_LABELS, MEMBER_ROLE_LABELS, labelOf } from "@/lib/workPermitVocab";

const fmt = (d: string | null | undefined): string =>
  d ? new Date(d).toLocaleString("ru-RU") : "—";

function metaText(
  e: WorkPermitEventDto,
  nameOf: (id: string) => string,
): string | null {
  const m = e.meta;
  if (!m) return null;
  if (e.event_type === "extended" && (m.old_end || m.new_end)) {
    return `с ${fmt(m.old_end)} до ${fmt(m.new_end)}`;
  }
  if ((e.event_type === "member_added" || e.event_type === "member_removed") && m.person_id) {
    const role = m.role ? ` (${labelOf(MEMBER_ROLE_LABELS, m.role)})` : "";
    return `${nameOf(m.person_id)}${role}`;
  }
  return null;
}

interface Props {
  events: WorkPermitEventDto[];
  nameOf?: (id: string) => string;
}

export const WorkPermitEventsTimeline = ({ events, nameOf }: Props) => {
  if (events.length === 0)
    return <p className="text-sm text-muted-foreground">Событий нет</p>;
  const resolve = nameOf ?? ((id: string) => id);
  return (
    <ul className="space-y-1 text-sm">
      {events.map((e) => {
        const detail = e.note ?? metaText(e, resolve);
        return (
          <li key={e.id} className="flex gap-3">
            <span className="w-36 shrink-0 text-muted-foreground">
              {new Date(e.at).toLocaleString("ru-RU")}
            </span>
            <span>{labelOf(EVENT_TYPE_LABELS, e.event_type)}</span>
            {detail ? <span className="text-muted-foreground">— {detail}</span> : null}
          </li>
        );
      })}
    </ul>
  );
};
```

- [ ] **Step 2: Передать nameOf из карточки**

В `frontend/src/pages/work-permits/WorkPermitDetailPage.tsx` найти использование `<WorkPermitEventsTimeline events={events} />` и заменить на:

```tsx
            <WorkPermitEventsTimeline events={events} nameOf={nameOf} />
```

(`nameOf` уже определён в компоненте карточки — резолвер `person_id → ФИО`.)

- [ ] **Step 3: Проверить типы**

Run: `npm --prefix frontend run build`
Expected: проходит.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/work-permits/WorkPermitEventsTimeline.tsx frontend/src/pages/work-permits/WorkPermitDetailPage.tsx
git commit -m "feat(work-permits): timeline renders event meta (extend/crew)"
```

---

### Task 11: Панель ежедневного допуска

**Files:**
- Create: `frontend/src/features/work-permits/DailyAdmissionPanel.tsx`

- [ ] **Step 1: Реализовать** (паттерн `BriefingPanel.tsx`: загрузка через api + форма + `Can`)

Create `frontend/src/features/work-permits/DailyAdmissionPanel.tsx`:

```tsx
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { workPermitsApi } from "@/api/workPermits";
import { Button } from "@/components/ui/button";
import { Can } from "@/components/permissions/Can";
import { Input } from "@/components/ui/input";
import { PERMISSIONS } from "@/permissions/permissions";
import type { WorkPermitDailyAdmissionDto, WorkPermitDto } from "@/types/dto/workPermits";

interface Props {
  wp: WorkPermitDto;
  onRefresh: () => void;
}

export const DailyAdmissionPanel = ({ wp, onRefresh }: Props) => {
  const [rows, setRows] = useState<WorkPermitDailyAdmissionDto[]>([]);
  const [day, setDay] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    workPermitsApi.listAdmissions(wp.id).then(setRows).catch(() => undefined);
  }, [wp.id]);

  useEffect(() => { load(); }, [load]);

  const canAdmit = wp.status === "issued";

  const handleAdd = async () => {
    if (!day) {
      toast.error("Укажите дату смены");
      return;
    }
    setSaving(true);
    try {
      await workPermitsApi.createAdmission(wp.id, {
        admission_date: day,
        start_at: new Date().toISOString(),
      });
      toast.success("Допуск на смену оформлен");
      setDay("");
      load();
      onRefresh();
    } catch {
      toast.error("Не удалось оформить допуск (наряд должен быть выдан)");
    } finally {
      setSaving(false);
    }
  };

  const handleClose = async (a: WorkPermitDailyAdmissionDto) => {
    try {
      await workPermitsApi.updateAdmission(wp.id, a.id, { end_at: new Date().toISOString() });
      toast.success("Смена закрыта");
      load();
    } catch {
      toast.error("Не удалось закрыть смену");
    }
  };

  return (
    <div className="space-y-2">
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">Допусков на смену нет</p>
      ) : (
        <ul className="space-y-1 text-sm">
          {rows.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 border-b pb-1">
              <span>
                {new Date(a.admission_date).toLocaleDateString("ru-RU")}
                {a.start_at ? ` · с ${new Date(a.start_at).toLocaleTimeString("ru-RU")}` : ""}
                {a.end_at ? ` · по ${new Date(a.end_at).toLocaleTimeString("ru-RU")}` : ""}
              </span>
              {!a.end_at && (
                <Can permission={PERMISSIONS.WORK_PERMIT_MANAGE}>
                  <Button size="sm" variant="ghost" onClick={() => void handleClose(a)}>
                    Закрыть смену
                  </Button>
                </Can>
              )}
            </li>
          ))}
        </ul>
      )}

      {canAdmit && (
        <Can permission={PERMISSIONS.WORK_PERMIT_MANAGE}>
          <div className="flex flex-wrap items-end gap-2 pt-1">
            <Input type="date" className="w-44" value={day} onChange={(e) => setDay(e.target.value)} />
            <Button size="sm" disabled={saving || !day} onClick={() => void handleAdd()}>
              {saving ? "..." : "Допустить на смену"}
            </Button>
          </div>
        </Can>
      )}
    </div>
  );
};
```

- [ ] **Step 2: Проверить типы**

Run: `npm --prefix frontend run build`
Expected: проходит.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/work-permits/DailyAdmissionPanel.tsx
git commit -m "feat(work-permits): DailyAdmissionPanel"
```

---

### Task 12: Редактирование бригады в issued

**Files:**
- Modify: `frontend/src/features/work-permits/BrigadeMembersPanel.tsx`

- [ ] **Step 1: Реализовать**

В `frontend/src/features/work-permits/BrigadeMembersPanel.tsx` заменить строку гейта:

```tsx
  const canEdit = wp.status === "draft";
```

на:

```tsx
  // Ф3a: состав бригады редактируется и в работе (issued/suspended), не только в черновике
  const canEdit = wp.status === "draft" || wp.status === "issued" || wp.status === "suspended";
```

- [ ] **Step 2: Проверить типы + существующий тест**

Run: `npm --prefix frontend run build` then `npm --prefix frontend run test -- WorkPermitDetailPage`
Expected: сборка и тесты проходят (draft-логика не сломана; issued теперь тоже редактируем).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/work-permits/BrigadeMembersPanel.tsx
git commit -m "feat(work-permits): allow brigade edits in issued/suspended (Ф3a)"
```

---

### Task 13: Монтаж панели допуска на карточке + тест

**Files:**
- Modify: `frontend/src/pages/work-permits/WorkPermitDetailPage.tsx`
- Modify: `frontend/src/__tests__/WorkPermitDetailPage.test.tsx`

- [ ] **Step 1: Обновить мок теста**

В `frontend/src/__tests__/WorkPermitDetailPage.test.tsx` в `vi.mock("@/api/workPermits", ...)` добавить стаб `listAdmissions: () => Promise.resolve([])` (страница теперь грузит допуски).

- [ ] **Step 2: Добавить тест-проверку панели допуска**

Добавить в `describe("WorkPermitDetailPage", ...)`:

```tsx
  it("показывает панель ежедневного допуска", async () => {
    setRole([PERMISSIONS.WORK_PERMIT_VIEW, PERMISSIONS.WORK_PERMIT_MANAGE]);
    renderAt();
    expect(await screen.findByText(/ежедневный допуск/i)).toBeInTheDocument();
  });
```

- [ ] **Step 3: Прогнать тест — должен упасть**

Run: `npm --prefix frontend run test -- WorkPermitDetailPage`
Expected: FAIL (нет заголовка «Ежедневный допуск»).

- [ ] **Step 4: Реализовать монтаж**

В `frontend/src/pages/work-permits/WorkPermitDetailPage.tsx`:

1) Импорт: `import { DailyAdmissionPanel } from "@/features/work-permits/DailyAdmissionPanel";`

2) Перед блоком «Events log» (`{/* Events log */}`) вставить:

```tsx
      {/* Ежедневный допуск */}
      <div className="rounded-md border p-3">
        <div className="text-sm font-medium mb-2">Ежедневный допуск</div>
        <DailyAdmissionPanel wp={wp} onRefresh={refreshSide} />
      </div>
```

- [ ] **Step 5: Прогнать тест — должен пройти**

Run: `npm --prefix frontend run test -- WorkPermitDetailPage`
Expected: PASS (все тесты файла).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/work-permits/WorkPermitDetailPage.tsx frontend/src/__tests__/WorkPermitDetailPage.test.tsx
git commit -m "feat(work-permits): mount DailyAdmissionPanel on detail card"
```

---

### Task 14: Полная верификация

- [ ] **Step 1: Backend-контур Ф3a**

Run: `python -m pytest backend/tests/test_work_permit_lifecycle.py backend/tests/test_wp04_work_permit_ops_journal_migration.py backend/tests/test_work_permit_admission_schemas.py tests/test_work_permit_service.py tests/api/test_work_permit_admission_api.py tests/api/test_work_permits_api.py -v`
Expected: всё PASS (отметить версию Python, если не 3.12).

- [ ] **Step 2: Frontend тесты + сборка**

Run: `npm --prefix frontend run test -- WorkPermit` then `npm --prefix frontend run build`
Expected: тесты PASS; сборка без ошибок типов.

- [ ] **Step 3: Ручная проверка (preview)**

Запустить dev-preview, войти под admin, открыть карточку issued-наряда: оформить ежедневный допуск + закрыть смену, изменить состав бригады, продлить — убедиться, что записи появляются в журнале с деталями (продление «с..до», участник + роль). Зафиксировать скриншот.

- [ ] **Step 4: Финальный commit (если остались правки)**

```bash
git add -A && git commit -m "chore(work-permits): Ф3a verification fixes" || echo "nothing to commit"
```

---

## Self-Review (выполнено автором плана)

- **Покрытие спеки:** §4 модель (таблица допуска + `meta`) → Task 2/3; §5 сервис (допуск issued-гейт, журналирование смены состава, extend было→стало) → Task 4/5; §6 API (admissions CRUD + cross-permit guard + meta в /events + actor смены состава) → Task 7; §7 фронт (панель допуска, рендер meta, бригада в issued) → Task 8-13; §8 логика/гейты → Task 4/5/7/12; §10 тесты → Task 1/2/4/5/6/7/13/14. Гэпов нет.
- **Плейсхолдеры:** полный код в каждом шаге; `NB`-пометки — точки сверки фикстур (`sessionmaker`/`data_factory`/`async_client`/`create_person`), не заглушки.
- **Согласованность типов:** `meta`-семантика (`old_end/new_end`, `person_id/role`) едина backend↔frontend; `admitted` событие пишется в `create_admission` (Task 5) и подписано в vocab (Task 8); `WorkPermitDailyAdmissionDto`/`*Read` поля совпадают; `nameOf` проп ленты (Task 10) согласован с карточкой; новые типы событий (Task 1) подписаны в `EVENT_TYPE_LABELS` (Task 8).
- **FSM:** ни одна задача не трогает `validate_transition`/`ALLOWED_TRANSITIONS` — переходы не меняются (только новые НЕ-переходные события и таблица допуска).
