# Наряд-допуск на высоте (782н) — Ф2 «целевой инструктаж + подписи ПЭП» — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать наряду-допуску юридическую значимость: целевой инструктаж бригады (новая сущность) + подписи ПЭП двух потоков (ответственные → наряд; бригада → инструктаж) в двух режимах (attested + code-flow), с отображением на карточке. FSM Ф1 не меняется.

**Architecture:** Full-stack, аддитивно, **Подход A** (без промежуточной таблицы подписей). Backend: миграция `wp03` добавляет одну таблицу `work_permit_briefing`; подписи живут в существующем `signature_requests` через 2 новых `object_type`/`purpose` + 2 ветки `_build_content`; тонкий сервис `domains/work_permits/signing.py` валидирует членство и блокирует повторную подпись поверх готового `PepSigningService`; confirm/decline — через существующий `/sign/pep/...`. Frontend: api-модуль + две панели на карточке (по образцу Ф1, без стора).

**Tech Stack:** Python/FastAPI/SQLAlchemy/Alembic (backend); React/Vite/TypeScript, axios (`apiClient`), vitest + @testing-library/react (frontend).

**Spec:** `docs/superpowers/specs/2026-06-18-work-permit-782n-signatures-design.md`

**Branch:** `feat/work-permits-782n-signatures` (уже создана от `origin/main` b269116, где Ф1 есть).

**Тесты (среда):** канон Py3.12.12 = CI. Локально может быть другая версия (на этой машине Py3.14) — прогонять доступным Python, отметить расхождение (CLAUDE.md). Не запускать `make cs:test`. Точечные вызовы pytest. Frontend: `npm --prefix frontend run test -- <file>` и `npm --prefix frontend run build`.

**Реестр имён (используются сквозь план):**
- `object_type`: `"work_permit"` (подпись наряда), `"work_permit_briefing"` (ознакомление с инструктажом).
- `purpose`: `"work_permit"`, `"work_permit_briefing"`.
- Классы ролей: ответственные `{issuer, supervisor, admitter, foreman}` → наряд; бригада `{member, observer, foreman}` → инструктаж.
- `mode`: `"attested"` | `"code"`.

---

## Часть A — Backend

### Task 1: Новые purpose'ы ПЭП (домен)

**Files:**
- Modify: `backend/app/domains/signing/pep.py:14`
- Test: `backend/tests/test_pep_signing_domain.py`

- [ ] **Step 1: Написать падающий тест**

Добавить в `backend/tests/test_pep_signing_domain.py`:

```python
def test_pep_purposes_include_work_permit_streams():
    from app.domains.signing.pep import PEP_PURPOSES

    assert "work_permit" in PEP_PURPOSES
    assert "work_permit_briefing" in PEP_PURPOSES
```

- [ ] **Step 2: Прогнать тест — должен упасть**

Run: `python -m pytest backend/tests/test_pep_signing_domain.py::test_pep_purposes_include_work_permit_streams -v`
Expected: FAIL (значений нет в frozenset).

- [ ] **Step 3: Реализовать**

В `backend/app/domains/signing/pep.py` заменить строку 14:

```python
PEP_PURPOSES = frozenset(
    {"document", "acknowledgement", "ppe_issue", "briefing", "work_permit", "work_permit_briefing"}
)
```

- [ ] **Step 4: Прогнать тест — должен пройти**

Run: `python -m pytest backend/tests/test_pep_signing_domain.py::test_pep_purposes_include_work_permit_streams -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/signing/pep.py backend/tests/test_pep_signing_domain.py
git commit -m "feat(work-permits): PEP purposes for permit + briefing signing (782н Ф2)"
```

---

### Task 2: Миграция wp03 — таблица work_permit_briefing

**Files:**
- Create: `backend/app/migrations/versions/20260618_wp03_work_permit_briefing.py`
- Test: `backend/tests/test_wp03_work_permit_briefing_migration.py`

- [ ] **Step 1: Подтвердить head**

Истинный head ветки наряда — `20260617_wp02_work_permit_782n_fields` (детей нет; репо многоголовое — это норма). `down_revision` миграции = именно эта ревизия. Если кто-то нарастил цепочку наряда — взять актуального потомка wp02 и отразить в guard-тесте.

- [ ] **Step 2: Написать падающий тест (guard, source-level — как wp02)**

Create `backend/tests/test_wp03_work_permit_briefing_migration.py`:

```python
"""Guard: wp03 chains from wp02 and creates work_permit_briefing (additive)."""
import importlib.util
from pathlib import Path

MIG = (
    Path(__file__).resolve().parents[1]
    / "app/migrations/versions/20260618_wp03_work_permit_briefing.py"
)

NEW_COLUMNS = {"work_permit_id", "conducted_by_person_id", "conducted_at", "topics_text"}


def _load():
    spec = importlib.util.spec_from_file_location("wp03_mig", MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_wp03_chain_and_revision():
    mod = _load()
    assert mod.revision == "20260618_wp03_work_permit_briefing"
    assert mod.down_revision == "20260617_wp02_work_permit_782n_fields"


def test_wp03_source_creates_and_drops_table():
    src = MIG.read_text(encoding="utf-8")
    assert 'create_table(\n        "work_permit_briefing"' in src or 'create_table("work_permit_briefing"' in src
    for col in NEW_COLUMNS:
        assert f'"{col}"' in src, f"missing column literal: {col}"
    assert 'drop_table("work_permit_briefing")' in src, "downgrade must drop the table"
```

- [ ] **Step 3: Прогнать тест — должен упасть**

Run: `python -m pytest backend/tests/test_wp03_work_permit_briefing_migration.py -v`
Expected: FAIL (файла миграции нет → ошибка загрузки).

- [ ] **Step 4: Написать миграцию**

Create `backend/app/migrations/versions/20260618_wp03_work_permit_briefing.py`:

```python
"""wp03: целевой инструктаж наряда-допуска (Ф2) — таблица work_permit_briefing.

Additive: одна новая таблица. FK→work_permit (CASCADE), FK→person (SET NULL).
Имена таблиц LITERAL (AST-audit blindspot). Honest downgrade drops the table.
Подписи отдельной таблицы НЕ получают — живут в signature_requests (Подход A).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260618_wp03_work_permit_briefing"
down_revision = "20260617_wp02_work_permit_782n_fields"
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
        "work_permit_briefing",
        *_base_columns(),
        sa.Column("work_permit_id", sa.String(length=36), nullable=False),
        sa.Column("conducted_by_person_id", sa.String(length=36), nullable=True),
        sa.Column("conducted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("topics_text", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["work_permit_id"], ["work_permit.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conducted_by_person_id"], ["person.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_work_permit_briefing_permit", "work_permit_briefing", ["work_permit_id"]
    )


def downgrade() -> None:
    op.drop_table("work_permit_briefing")
```

- [ ] **Step 5: Прогнать тест — должен пройти**

Run: `python -m pytest backend/tests/test_wp03_work_permit_briefing_migration.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/migrations/versions/20260618_wp03_work_permit_briefing.py backend/tests/test_wp03_work_permit_briefing_migration.py
git commit -m "feat(work-permits): wp03 migration — work_permit_briefing table"
```

---

### Task 3: Модель WorkPermitBriefing

**Files:**
- Modify: `backend/app/models/work_permit.py`
- Test: `backend/tests/test_wp03_work_permit_briefing_migration.py` (добавить shape-тест модели)

- [ ] **Step 1: Написать падающий тест**

Добавить в `backend/tests/test_wp03_work_permit_briefing_migration.py`:

```python
def test_model_has_briefing_columns():
    from app.models.work_permit import WorkPermitBriefing

    cols = set(WorkPermitBriefing.__table__.columns.keys())
    assert NEW_COLUMNS.issubset(cols)
    assert WorkPermitBriefing.__tablename__ == "work_permit_briefing"
```

- [ ] **Step 2: Прогнать тест — должен упасть**

Run: `python -m pytest backend/tests/test_wp03_work_permit_briefing_migration.py::test_model_has_briefing_columns -v`
Expected: FAIL (`ImportError: cannot import name 'WorkPermitBriefing'`).

- [ ] **Step 3: Реализовать**

В `backend/app/models/work_permit.py` в конец файла (после `WorkPermitEvent`) добавить (импорты `DateTime, ForeignKey, Text` уже есть в строке 6):

```python
class WorkPermitBriefing(TenantBaseModel):
    __tablename__ = "work_permit_briefing"

    work_permit_id: Mapped[str] = mapped_column(
        ForeignKey("work_permit.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conducted_by_person_id: Mapped[str | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), nullable=True
    )
    conducted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    topics_text: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 4: Прогнать тест — должен пройти**

Run: `python -m pytest backend/tests/test_wp03_work_permit_briefing_migration.py -v`
Expected: PASS (все тесты файла).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/work_permit.py backend/tests/test_wp03_work_permit_briefing_migration.py
git commit -m "feat(work-permits): WorkPermitBriefing model"
```

---

### Task 4: Ветки _build_content для наряда и инструктажа (ПЭП-сервис)

**Files:**
- Modify: `backend/app/services/pep_signing.py`
- Test: `tests/test_work_permit_signing.py` (новый файл контура подписи наряда)

- [ ] **Step 1: Написать падающий тест**

Create `tests/test_work_permit_signing.py` (фикстуры `session`/`tenant` — как в `tests/test_work_permit_service.py`; если имена иные, выровнять):

```python
import pytest

from app.domains.work_permits import create_work_permit
from app.services.pep_signing import PepNotFound, PepSigningService


@pytest.mark.asyncio
async def test_build_content_work_permit(session, tenant):
    wp = await create_work_permit(
        session, tenant_id=tenant.id, work_type="height", zone_text="фасад",
        number="НД-7", content_text="монтаж",
    )
    svc = PepSigningService(session, str(tenant.id))
    content = await svc._build_content("work_permit", wp.id)
    assert content["work_permit_id"] == wp.id
    assert content["number"] == "НД-7"
    assert content["work_type"] == "height"
    assert content["members"] == []


@pytest.mark.asyncio
async def test_build_content_unknown_permit_raises(session, tenant):
    svc = PepSigningService(session, str(tenant.id))
    with pytest.raises(PepNotFound):
        await svc._build_content("work_permit", "missing-id")
```

- [ ] **Step 2: Прогнать тест — должен упасть**

Run: `python -m pytest tests/test_work_permit_signing.py -v`
Expected: FAIL (`PepConflict: unsupported object_type: work_permit`).

- [ ] **Step 3: Реализовать**

В `backend/app/services/pep_signing.py`:

1) После строки импорта моделей (`from app.models.models import ApprovalInstance, BriefingEntry, Person, PPEIssue, SignatureRequest`) добавить:

```python
from app.models.work_permit import WorkPermit, WorkPermitBriefing, WorkPermitMember
```

2) В методе `_build_content`, перед финальной строкой `raise PepConflict(f"unsupported object_type: {object_type}")`, добавить две ветки:

```python
        if object_type == "work_permit":
            wp = await self.session.get(WorkPermit, object_id)
            if wp is None or str(wp.tenant_id) != str(self.tenant_id):
                raise PepNotFound("work_permit")
            members = (
                await self.session.execute(
                    select(WorkPermitMember)
                    .where(
                        WorkPermitMember.tenant_id == self.tenant_id,
                        WorkPermitMember.work_permit_id == wp.id,
                    )
                    .order_by(WorkPermitMember.created_at.asc())
                )
            ).scalars().all()
            return {
                "work_permit_id": wp.id,
                "number": wp.number,
                "work_type": wp.work_type,
                "zone_text": wp.zone_text,
                "status": wp.status,
                "members": [{"person_id": m.person_id, "role": m.role} for m in members],
            }
        if object_type == "work_permit_briefing":
            br = await self.session.get(WorkPermitBriefing, object_id)
            if br is None or str(br.tenant_id) != str(self.tenant_id):
                raise PepNotFound("work_permit_briefing")
            return {
                "work_permit_briefing_id": br.id,
                "work_permit_id": br.work_permit_id,
                "conducted_by_person_id": br.conducted_by_person_id,
                "conducted_at": br.conducted_at.isoformat() if br.conducted_at else None,
                "topics_text": br.topics_text,
            }
```

- [ ] **Step 4: Прогнать тест — должен пройти**

Run: `python -m pytest tests/test_work_permit_signing.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/pep_signing.py tests/test_work_permit_signing.py
git commit -m "feat(work-permits): _build_content branches for permit + briefing"
```

---

### Task 5: CRUD целевого инструктажа (сервис)

**Files:**
- Modify: `backend/app/domains/work_permits/service.py`
- Modify: `backend/app/domains/work_permits/__init__.py`
- Test: `tests/test_work_permit_service.py`

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/test_work_permit_service.py`:

```python
@pytest.mark.asyncio
async def test_briefing_crud(session, tenant):
    from app.domains.work_permits import (
        create_briefing, create_work_permit, get_briefing, list_briefings, update_briefing,
    )

    wp = await create_work_permit(session, tenant_id=tenant.id, work_type="height", zone_text="z")
    br = await create_briefing(
        session, tenant_id=tenant.id, work_permit_id=wp.id, topics_text="страховка",
    )
    assert br.work_permit_id == wp.id
    assert br.topics_text == "страховка"

    rows = await list_briefings(session, tenant_id=tenant.id, work_permit_id=wp.id)
    assert [b.id for b in rows] == [br.id]

    updated = await update_briefing(
        session, tenant_id=tenant.id, briefing_id=br.id, topics_text="страховка + СИЗ",
    )
    assert updated.topics_text == "страховка + СИЗ"

    again = await get_briefing(session, tenant_id=tenant.id, briefing_id=br.id)
    assert again.topics_text == "страховка + СИЗ"


@pytest.mark.asyncio
async def test_create_briefing_unknown_permit_returns_none(session, tenant):
    from app.domains.work_permits import create_briefing

    assert await create_briefing(session, tenant_id=tenant.id, work_permit_id="missing") is None
```

- [ ] **Step 2: Прогнать тест — должен упасть**

Run: `python -m pytest tests/test_work_permit_service.py::test_briefing_crud -v`
Expected: FAIL (`ImportError: cannot import name 'create_briefing'`).

- [ ] **Step 3: Реализовать**

1) В `backend/app/domains/work_permits/service.py` заменить строку импорта моделей:

```python
from app.models.work_permit import WorkPermit, WorkPermitBriefing, WorkPermitEvent, WorkPermitMember
```

2) В конец `service.py` добавить:

```python
# --- целевой инструктаж (Ф2) ------------------------------------------------

async def create_briefing(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str,
    conducted_by_person_id: str | None = None, conducted_at: datetime | None = None,
    topics_text: str | None = None,
) -> WorkPermitBriefing | None:
    wp = await _get(session, tenant_id, work_permit_id)
    if wp is None:
        return None
    br = WorkPermitBriefing(
        tenant_id=tenant_id, work_permit_id=work_permit_id,
        conducted_by_person_id=conducted_by_person_id, conducted_at=conducted_at,
        topics_text=topics_text,
    )
    session.add(br)
    await session.flush()
    await session.refresh(br)
    return br


async def list_briefings(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str,
) -> list[WorkPermitBriefing]:
    stmt = select(WorkPermitBriefing).where(
        WorkPermitBriefing.tenant_id == tenant_id,
        WorkPermitBriefing.work_permit_id == work_permit_id,
    ).order_by(WorkPermitBriefing.created_at.asc())
    return list((await session.execute(stmt)).scalars().all())


async def get_briefing(
    session: AsyncSession, *, tenant_id: str, briefing_id: str,
) -> WorkPermitBriefing | None:
    stmt = select(WorkPermitBriefing).where(
        WorkPermitBriefing.id == briefing_id, WorkPermitBriefing.tenant_id == tenant_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


_BRIEFING_EDITABLE = ("conducted_by_person_id", "conducted_at", "topics_text")


async def update_briefing(
    session: AsyncSession, *, tenant_id: str, briefing_id: str, **fields,
) -> WorkPermitBriefing | None:
    br = await get_briefing(session, tenant_id=tenant_id, briefing_id=briefing_id)
    if br is None:
        return None
    for key, value in fields.items():
        if key in _BRIEFING_EDITABLE:
            setattr(br, key, value)
    await session.flush()
    await session.refresh(br)
    return br
```

3) В `backend/app/domains/work_permits/__init__.py` дополнить импорт из `service` и `__all__`:

```python
from app.domains.work_permits.service import (
    add_member, cancel, close, create_briefing, create_work_permit, delete_draft, extend,
    get_briefing, issue, list_briefings, list_events, list_members, remove_member, resume,
    suspend, update_briefing, update_work_permit,
)
```

и добавить в список `__all__` строки: `"create_briefing", "get_briefing", "list_briefings", "update_briefing"`.

- [ ] **Step 4: Прогнать тест — должен пройти**

Run: `python -m pytest tests/test_work_permit_service.py::test_briefing_crud tests/test_work_permit_service.py::test_create_briefing_unknown_permit_returns_none -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/work_permits/service.py backend/app/domains/work_permits/__init__.py tests/test_work_permit_service.py
git commit -m "feat(work-permits): briefing CRUD service"
```

---

### Task 6: Сервис подписи наряда (signing.py)

**Files:**
- Create: `backend/app/domains/work_permits/signing.py`
- Test: `tests/test_work_permit_signing.py`

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/test_work_permit_signing.py`:

```python
from app.domains.work_permits import add_member, create_briefing
from app.domains.work_permits.signing import (
    WorkPermitSignerError, sign_briefing, sign_permit,
)
from app.services.pep_signing import PepConflict


async def _person(session, tenant, last="Иванов"):
    from app.models.models import Person
    p = Person(tenant_id=tenant.id, first_name="И", last_name=last)
    session.add(p)
    await session.flush()
    return p


@pytest.mark.asyncio
async def test_sign_permit_attested_marks_signed(session, tenant):
    wp = await create_work_permit(session, tenant_id=tenant.id, work_type="height", zone_text="z")
    p = await _person(session, tenant)
    await add_member(session, tenant_id=tenant.id, work_permit_id=wp.id, person_id=p.id, role="foreman")
    req, code = await sign_permit(
        session, tenant_id=str(tenant.id), work_permit_id=wp.id,
        person_id=p.id, mode="attested", requested_by="u1",
    )
    assert code is None
    assert req.status == "signed"
    assert req.object_type == "work_permit"


@pytest.mark.asyncio
async def test_sign_permit_code_mode_returns_code(session, tenant):
    wp = await create_work_permit(session, tenant_id=tenant.id, work_type="height", zone_text="z")
    p = await _person(session, tenant)
    await add_member(session, tenant_id=tenant.id, work_permit_id=wp.id, person_id=p.id, role="supervisor")
    req, code = await sign_permit(
        session, tenant_id=str(tenant.id), work_permit_id=wp.id,
        person_id=p.id, mode="code", requested_by="u1",
    )
    assert code is not None and len(code) == 6
    assert req.status == "awaiting_code"


@pytest.mark.asyncio
async def test_sign_permit_rejects_non_responsible(session, tenant):
    wp = await create_work_permit(session, tenant_id=tenant.id, work_type="height", zone_text="z")
    p = await _person(session, tenant)
    # роль member НЕ входит в класс ответственных
    await add_member(session, tenant_id=tenant.id, work_permit_id=wp.id, person_id=p.id, role="member")
    with pytest.raises(WorkPermitSignerError):
        await sign_permit(
            session, tenant_id=str(tenant.id), work_permit_id=wp.id,
            person_id=p.id, mode="attested", requested_by="u1",
        )


@pytest.mark.asyncio
async def test_sign_permit_blocks_double_sign(session, tenant):
    wp = await create_work_permit(session, tenant_id=tenant.id, work_type="height", zone_text="z")
    p = await _person(session, tenant)
    await add_member(session, tenant_id=tenant.id, work_permit_id=wp.id, person_id=p.id, role="issuer")
    await sign_permit(session, tenant_id=str(tenant.id), work_permit_id=wp.id,
                      person_id=p.id, mode="attested", requested_by="u1")
    with pytest.raises(PepConflict):
        await sign_permit(session, tenant_id=str(tenant.id), work_permit_id=wp.id,
                          person_id=p.id, mode="attested", requested_by="u1")


@pytest.mark.asyncio
async def test_sign_briefing_attested(session, tenant):
    wp = await create_work_permit(session, tenant_id=tenant.id, work_type="height", zone_text="z")
    p = await _person(session, tenant)
    await add_member(session, tenant_id=tenant.id, work_permit_id=wp.id, person_id=p.id, role="member")
    br = await create_briefing(session, tenant_id=tenant.id, work_permit_id=wp.id, topics_text="t")
    req, code = await sign_briefing(
        session, tenant_id=str(tenant.id), briefing_id=br.id,
        person_id=p.id, mode="attested", requested_by="u1",
    )
    assert code is None and req.status == "signed"
    assert req.object_type == "work_permit_briefing"
```

> NB: модель `Person` и обязательные её поля взять как в соседних тестах (`tests/test_work_permit_service.py` / `tests/api/test_work_permits_api.py`) — выше показан минимум; если конструктор `Person` требует иные обязательные поля, скопировать их оттуда.

- [ ] **Step 2: Прогнать тест — должен упасть**

Run: `python -m pytest tests/test_work_permit_signing.py -v`
Expected: FAIL (`ModuleNotFoundError: app.domains.work_permits.signing`).

- [ ] **Step 3: Реализовать**

Create `backend/app/domains/work_permits/signing.py`:

```python
"""Подписи ПЭП наряда-допуска (Ф2): тонкая обёртка над PepSigningService.

Подход A — без промежуточной таблицы: подписи живут в signature_requests.
Два потока: наряд (ответственные роли) и целевой инструктаж (бригада).
Валидирует членство и блокирует повторную подпись (create_attested сам этого
не делает; create_request блокирует только активные дубли, не SIGNED).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.work_permits.service import get_briefing
from app.models.models import SignatureRequest
from app.models.work_permit import WorkPermitMember
from app.services.pep_signing import PepConflict, PepNotFound, PepSigningService

PERMIT_SIGNER_ROLES = frozenset({"issuer", "supervisor", "admitter", "foreman"})
BRIEFING_SIGNER_ROLES = frozenset({"member", "observer", "foreman"})
_SIGN_MODES = frozenset({"attested", "code"})
_SIGNED = "signed"


class WorkPermitSignerError(PepConflict):
    """Подписант не входит в нужный класс ролей наряда (маппится в 409)."""


async def _member_role(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str,
    person_id: str, allowed_roles: frozenset[str],
) -> str | None:
    stmt = select(WorkPermitMember.role).where(
        WorkPermitMember.tenant_id == tenant_id,
        WorkPermitMember.work_permit_id == work_permit_id,
        WorkPermitMember.person_id == person_id,
        WorkPermitMember.role.in_(tuple(allowed_roles)),
    )
    return (await session.execute(stmt)).scalars().first()


async def _reject_if_signed(
    session: AsyncSession, *, tenant_id: str, object_type: str,
    object_id: str, signer_person_id: str,
) -> None:
    stmt = select(SignatureRequest.id).where(
        SignatureRequest.tenant_id == tenant_id,
        SignatureRequest.object_type == object_type,
        SignatureRequest.object_id == object_id,
        SignatureRequest.signer_person_id == signer_person_id,
        SignatureRequest.status == _SIGNED,
    )
    if (await session.execute(stmt)).scalars().first() is not None:
        raise PepConflict("already signed by this person")


async def _dispatch(
    session: AsyncSession, *, tenant_id: str, object_type: str, object_id: str,
    purpose: str, person_id: str, mode: str, requested_by: str,
) -> tuple[SignatureRequest, str | None]:
    if mode not in _SIGN_MODES:
        raise PepConflict(f"unsupported mode: {mode}")
    await _reject_if_signed(
        session, tenant_id=tenant_id, object_type=object_type,
        object_id=object_id, signer_person_id=person_id,
    )
    svc = PepSigningService(session, tenant_id)
    if mode == "attested":
        req = await svc.create_attested(
            object_type=object_type, object_id=object_id, purpose=purpose,
            requested_by=requested_by, signer_person_id=person_id,
        )
        return req, None
    return await svc.create_request(
        object_type=object_type, object_id=object_id, purpose=purpose,
        requested_by=requested_by, signer_person_id=person_id,
    )


async def sign_permit(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str,
    person_id: str, mode: str, requested_by: str,
) -> tuple[SignatureRequest, str | None]:
    role = await _member_role(
        session, tenant_id=tenant_id, work_permit_id=work_permit_id,
        person_id=person_id, allowed_roles=PERMIT_SIGNER_ROLES,
    )
    if role is None:
        raise WorkPermitSignerError("person is not a responsible member of this permit")
    return await _dispatch(
        session, tenant_id=tenant_id, object_type="work_permit", object_id=work_permit_id,
        purpose="work_permit", person_id=person_id, mode=mode, requested_by=requested_by,
    )


async def sign_briefing(
    session: AsyncSession, *, tenant_id: str, briefing_id: str,
    person_id: str, mode: str, requested_by: str,
) -> tuple[SignatureRequest, str | None]:
    br = await get_briefing(session, tenant_id=tenant_id, briefing_id=briefing_id)
    if br is None:
        raise PepNotFound("work_permit_briefing")
    role = await _member_role(
        session, tenant_id=tenant_id, work_permit_id=br.work_permit_id,
        person_id=person_id, allowed_roles=BRIEFING_SIGNER_ROLES,
    )
    if role is None:
        raise WorkPermitSignerError("person is not a brigade member of this permit")
    return await _dispatch(
        session, tenant_id=tenant_id, object_type="work_permit_briefing", object_id=briefing_id,
        purpose="work_permit_briefing", person_id=person_id, mode=mode, requested_by=requested_by,
    )
```

- [ ] **Step 4: Прогнать тест — должен пройти**

Run: `python -m pytest tests/test_work_permit_signing.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/work_permits/signing.py tests/test_work_permit_signing.py
git commit -m "feat(work-permits): signing service — permit + briefing, membership + dup guard"
```

---

### Task 7: Схемы (инструктаж + подпись)

**Files:**
- Modify: `backend/app/schemas/work_permit.py`
- Test: `backend/tests/test_work_permit_signature_schemas.py`

- [ ] **Step 1: Написать падающий тест**

Create `backend/tests/test_work_permit_signature_schemas.py`:

```python
import pytest
from pydantic import ValidationError

from app.schemas.work_permit import WorkPermitSignatureCreate


def test_signature_create_defaults_attested():
    s = WorkPermitSignatureCreate(person_id="p1")
    assert s.mode == "attested"


def test_signature_create_accepts_code():
    assert WorkPermitSignatureCreate(person_id="p1", mode="code").mode == "code"


def test_signature_create_rejects_unknown_mode():
    with pytest.raises(ValidationError):
        WorkPermitSignatureCreate(person_id="p1", mode="bogus")
```

- [ ] **Step 2: Прогнать тест — должен упасть**

Run: `python -m pytest backend/tests/test_work_permit_signature_schemas.py -v`
Expected: FAIL (`ImportError: cannot import name 'WorkPermitSignatureCreate'`).

- [ ] **Step 3: Реализовать**

В конец `backend/app/schemas/work_permit.py` добавить:

```python
class WorkPermitBriefingCreate(BaseSchema):
    conducted_by_person_id: str | None = None
    conducted_at: datetime | None = None
    topics_text: str | None = None


class WorkPermitBriefingUpdate(BaseSchema):
    conducted_by_person_id: str | None = None
    conducted_at: datetime | None = None
    topics_text: str | None = None


class WorkPermitBriefingRead(BaseSchema):
    id: str
    work_permit_id: str
    conducted_by_person_id: str | None
    conducted_at: datetime | None
    topics_text: str | None
    created_at: datetime
    updated_at: datetime


class WorkPermitSignatureCreate(BaseSchema):
    person_id: str
    mode: str = "attested"

    @field_validator("mode")
    @classmethod
    def _mode(cls, v: str) -> str:
        if v not in ("attested", "code"):
            raise ValueError(f"invalid mode: {v!r}")
        return v


class WorkPermitSignatureRead(BaseSchema):
    id: str
    stream: str
    object_type: str
    object_id: str
    purpose: str
    status: str
    signer_person_id: str | None
    signer_name: str | None
    content_hash: str | None
    signed_at: datetime | None
    confirm_code: str | None = None
```

- [ ] **Step 4: Прогнать тест — должен пройти**

Run: `python -m pytest backend/tests/test_work_permit_signature_schemas.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/work_permit.py backend/tests/test_work_permit_signature_schemas.py
git commit -m "feat(work-permits): briefing + signature schemas"
```

---

### Task 8: API — эндпоинты инструктажа

**Files:**
- Modify: `backend/app/api/routes/work_permits.py`
- Test: `tests/api/test_work_permit_briefing_api.py`

- [ ] **Step 1: Написать падающий тест**

Create `tests/api/test_work_permit_briefing_api.py` (паттерн клиента/заголовков — как в `tests/api/test_work_permits_api.py`; имя фикстуры клиента и хелпер создания наряда взять оттуда):

```python
import pytest


async def _make_permit(admin_client) -> str:
    r = await admin_client.post("/api/v1/work-permits", json={"work_type": "height", "zone_text": "z"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_briefing_create_list_patch(admin_client):
    wp_id = await _make_permit(admin_client)

    r = await admin_client.post(
        f"/api/v1/work-permits/{wp_id}/briefing",
        json={"topics_text": "страховочные системы"},
    )
    assert r.status_code == 201, r.text
    bid = r.json()["id"]
    assert r.json()["work_permit_id"] == wp_id

    lst = await admin_client.get(f"/api/v1/work-permits/{wp_id}/briefing")
    assert lst.status_code == 200
    assert [b["id"] for b in lst.json()] == [bid]

    upd = await admin_client.patch(
        f"/api/v1/work-permits/{wp_id}/briefing/{bid}",
        json={"topics_text": "страховка + эвакуация"},
    )
    assert upd.status_code == 200
    assert upd.json()["topics_text"] == "страховка + эвакуация"
```

- [ ] **Step 2: Прогнать тест — должен упасть**

Run: `python -m pytest tests/api/test_work_permit_briefing_api.py -v`
Expected: FAIL (404 — эндпоинтов нет).

- [ ] **Step 3: Реализовать**

В `backend/app/api/routes/work_permits.py`:

1) Дополнить импорт доменных функций (строки 17-20) именами инструктажа:

```python
from app.domains.work_permits import (
    add_member, cancel, close, create_briefing, create_work_permit, delete_draft, extend,
    get_briefing, issue, list_briefings, list_events, list_members, remove_member, resume,
    suspend, update_briefing, update_work_permit,
)
```

2) Дополнить импорт схем (строки 24-28) новыми именами:

```python
from app.schemas.work_permit import (
    ReadinessReportRead, ViolationRead, WorkPermitActionRequest, WorkPermitBriefingCreate,
    WorkPermitBriefingRead, WorkPermitBriefingUpdate, WorkPermitCreate, WorkPermitEventRead,
    WorkPermitExtendRequest, WorkPermitMemberCreate, WorkPermitMemberRead, WorkPermitPage,
    WorkPermitRead, WorkPermitSignatureCreate, WorkPermitSignatureRead, WorkPermitUpdate,
)
```

3) После функции `_member_schema` (около строки 57) добавить хелпер:

```python
def _briefing_read(br) -> WorkPermitBriefingRead:
    return WorkPermitBriefingRead(
        id=str(br.id), work_permit_id=str(br.work_permit_id),
        conducted_by_person_id=str(br.conducted_by_person_id) if br.conducted_by_person_id else None,
        conducted_at=br.conducted_at, topics_text=br.topics_text,
        created_at=br.created_at, updated_at=br.updated_at,
    )
```

4) В конец файла добавить эндпоинты инструктажа:

```python
@router.post("/{wp_id}/briefing", response_model=WorkPermitBriefingRead, status_code=status.HTTP_201_CREATED)
@audit_operation("update", "work_permit")
async def create_briefing_endpoint(
    wp_id: str, payload: WorkPermitBriefingCreate, tenant: TenantDep, session: SessionDep, access: WriterAccess
) -> WorkPermitBriefingRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    if payload.conducted_by_person_id:
        await _ensure_person(session, tenant, payload.conducted_by_person_id)
    br = await create_briefing(
        session, tenant_id=tenant.id, work_permit_id=wp_id,
        conducted_by_person_id=payload.conducted_by_person_id,
        conducted_at=payload.conducted_at, topics_text=payload.topics_text,
    )
    return _briefing_read(br)


@router.get("/{wp_id}/briefing", response_model=list[WorkPermitBriefingRead])
async def list_briefings_endpoint(
    wp_id: str, tenant: TenantDep, session: SessionDep, access: ReaderAccess
) -> list[WorkPermitBriefingRead]:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    rows = await list_briefings(session, tenant_id=tenant.id, work_permit_id=wp_id)
    return [_briefing_read(b) for b in rows]


@router.patch("/{wp_id}/briefing/{briefing_id}", response_model=WorkPermitBriefingRead)
@audit_operation("update", "work_permit")
async def update_briefing_endpoint(
    wp_id: str, briefing_id: str, payload: WorkPermitBriefingUpdate,
    tenant: TenantDep, session: SessionDep, access: WriterAccess,
) -> WorkPermitBriefingRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    fields = payload.model_dump(exclude_unset=True)
    if fields.get("conducted_by_person_id"):
        await _ensure_person(session, tenant, fields["conducted_by_person_id"])
    br = await update_briefing(session, tenant_id=tenant.id, briefing_id=briefing_id, **fields)
    if br is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "briefing not found")
    return _briefing_read(br)
```

- [ ] **Step 4: Прогнать тест — должен пройти**

Run: `python -m pytest tests/api/test_work_permit_briefing_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/work_permits.py tests/api/test_work_permit_briefing_api.py
git commit -m "feat(work-permits): briefing API endpoints"
```

---

### Task 9: API — эндпоинты подписи + список

**Files:**
- Modify: `backend/app/api/routes/work_permits.py`
- Test: `tests/api/test_work_permit_signatures_api.py`

- [ ] **Step 1: Написать падающий тест**

Create `tests/api/test_work_permit_signatures_api.py` (фикстуры/хелперы — как в `tests/api/test_work_permits_api.py`; хелпер создания person/получения его id взять оттуда — обозначен `_make_person`):

```python
import pytest


async def _make_permit(admin_client) -> str:
    r = await admin_client.post("/api/v1/work-permits", json={"work_type": "height", "zone_text": "z"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _add_member(admin_client, wp_id, person_id, role) -> None:
    r = await admin_client.post(
        f"/api/v1/work-permits/{wp_id}/members", json={"person_id": person_id, "role": role}
    )
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_permit_signature_attested_then_listed(admin_client, _make_person):
    wp_id = await _make_permit(admin_client)
    pid = await _make_person(admin_client)
    await _add_member(admin_client, wp_id, pid, "foreman")

    r = await admin_client.post(
        f"/api/v1/work-permits/{wp_id}/signatures", json={"person_id": pid, "mode": "attested"}
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "signed"
    assert r.json()["stream"] == "permit"

    lst = await admin_client.get(f"/api/v1/work-permits/{wp_id}/signatures")
    assert lst.status_code == 200
    assert any(s["status"] == "signed" and s["signer_person_id"] == pid for s in lst.json())


@pytest.mark.asyncio
async def test_permit_signature_code_flow(admin_client, _make_person):
    wp_id = await _make_permit(admin_client)
    pid = await _make_person(admin_client)
    await _add_member(admin_client, wp_id, pid, "supervisor")

    r = await admin_client.post(
        f"/api/v1/work-permits/{wp_id}/signatures", json={"person_id": pid, "mode": "code"}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "awaiting_code"
    code = body["confirm_code"]
    assert code and len(code) == 6

    confirm = await admin_client.post(
        f"/api/v1/sign/pep/requests/{body['id']}/confirm", json={"code": code}
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["status"] == "signed"


@pytest.mark.asyncio
async def test_permit_signature_rejects_non_member(admin_client, _make_person):
    wp_id = await _make_permit(admin_client)
    pid = await _make_person(admin_client)
    # сотрудник не в бригаде
    r = await admin_client.post(
        f"/api/v1/work-permits/{wp_id}/signatures", json={"person_id": pid, "mode": "attested"}
    )
    assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_briefing_signature_attested(admin_client, _make_person):
    wp_id = await _make_permit(admin_client)
    pid = await _make_person(admin_client)
    await _add_member(admin_client, wp_id, pid, "member")
    br = await admin_client.post(
        f"/api/v1/work-permits/{wp_id}/briefing", json={"topics_text": "t"}
    )
    bid = br.json()["id"]
    r = await admin_client.post(
        f"/api/v1/work-permits/{wp_id}/briefing/{bid}/signatures",
        json={"person_id": pid, "mode": "attested"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "signed"
    assert r.json()["stream"] == "briefing"
```

> NB: фикстура `_make_person` — взять/повторить хелпер создания сотрудника из `tests/api/test_work_permits_api.py` (там бригаду уже собирают); если он называется иначе, подставить актуальное имя.

- [ ] **Step 2: Прогнать тест — должен упасть**

Run: `python -m pytest tests/api/test_work_permit_signatures_api.py -v`
Expected: FAIL (404 — эндпоинтов подписи нет).

- [ ] **Step 3: Реализовать**

В `backend/app/api/routes/work_permits.py`:

1) Дополнить импорты вверху файла (после существующих):

```python
from app.domains.work_permits.signing import sign_briefing, sign_permit
from app.models.models import Person, SignatureRequest
from app.services.pep_signing import PepConflict, PepNotFound
```

(строка `from app.models.models import Person` уже есть — заменить её на `from app.models.models import Person, SignatureRequest`.)

2) После хелпера `_briefing_read` добавить маппер ошибок и read-хелпер подписи:

```python
def _pep_to_http(exc: Exception) -> HTTPException:
    if isinstance(exc, PepNotFound):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(code="PEP_NOT_FOUND", message=str(exc), error_type="work_permit"),
        )
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=api_problem_detail(code="PEP_CONFLICT", message=str(exc), error_type="work_permit"),
    )


def _signature_read(row: SignatureRequest, stream: str, *, confirm_code: str | None = None) -> WorkPermitSignatureRead:
    return WorkPermitSignatureRead(
        id=str(row.id), stream=stream, object_type=row.object_type, object_id=str(row.object_id),
        purpose=row.purpose, status=row.status,
        signer_person_id=str(row.signer_person_id) if row.signer_person_id else None,
        signer_name=row.signer_name, content_hash=row.content_hash, signed_at=row.signed_at,
        confirm_code=confirm_code,
    )
```

3) В конец файла добавить эндпоинты подписи:

```python
@router.post("/{wp_id}/signatures", response_model=WorkPermitSignatureRead, status_code=status.HTTP_201_CREATED)
@audit_operation("update", "work_permit")
async def create_permit_signature_endpoint(
    wp_id: str, payload: WorkPermitSignatureCreate, tenant: TenantDep, session: SessionDep, access: WriterAccess
) -> WorkPermitSignatureRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    await _ensure_person(session, tenant, payload.person_id)
    try:
        req, code = await sign_permit(
            session, tenant_id=str(tenant.id), work_permit_id=wp_id,
            person_id=payload.person_id, mode=payload.mode,
            requested_by=access.user.id if access else "system",
        )
    except (PepNotFound, PepConflict) as exc:
        raise _pep_to_http(exc) from exc
    return _signature_read(req, "permit", confirm_code=code)


@router.post(
    "/{wp_id}/briefing/{briefing_id}/signatures",
    response_model=WorkPermitSignatureRead, status_code=status.HTTP_201_CREATED,
)
@audit_operation("update", "work_permit")
async def create_briefing_signature_endpoint(
    wp_id: str, briefing_id: str, payload: WorkPermitSignatureCreate,
    tenant: TenantDep, session: SessionDep, access: WriterAccess,
) -> WorkPermitSignatureRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    await _ensure_person(session, tenant, payload.person_id)
    try:
        req, code = await sign_briefing(
            session, tenant_id=str(tenant.id), briefing_id=briefing_id,
            person_id=payload.person_id, mode=payload.mode,
            requested_by=access.user.id if access else "system",
        )
    except (PepNotFound, PepConflict) as exc:
        raise _pep_to_http(exc) from exc
    return _signature_read(req, "briefing", confirm_code=code)


@router.get("/{wp_id}/signatures", response_model=list[WorkPermitSignatureRead])
async def list_signatures_endpoint(
    wp_id: str, tenant: TenantDep, session: SessionDep, access: ReaderAccess
) -> list[WorkPermitSignatureRead]:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    permit_rows = (await session.execute(
        select(SignatureRequest).where(
            SignatureRequest.tenant_id == tenant.id,
            SignatureRequest.signature_type == "pep",
            SignatureRequest.object_type == "work_permit",
            SignatureRequest.object_id == wp_id,
        ).order_by(SignatureRequest.created_at.asc())
    )).scalars().all()
    briefings = await list_briefings(session, tenant_id=tenant.id, work_permit_id=wp_id)
    briefing_ids = [b.id for b in briefings]
    briefing_rows = []
    if briefing_ids:
        briefing_rows = (await session.execute(
            select(SignatureRequest).where(
                SignatureRequest.tenant_id == tenant.id,
                SignatureRequest.signature_type == "pep",
                SignatureRequest.object_type == "work_permit_briefing",
                SignatureRequest.object_id.in_(briefing_ids),
            ).order_by(SignatureRequest.created_at.asc())
        )).scalars().all()
    return (
        [_signature_read(r, "permit") for r in permit_rows]
        + [_signature_read(r, "briefing") for r in briefing_rows]
    )
```

- [ ] **Step 4: Прогнать тест — должен пройти**

Run: `python -m pytest tests/api/test_work_permit_signatures_api.py -v`
Expected: PASS.

- [ ] **Step 5: Прогон backend-контура Ф2**

Run: `python -m pytest backend/tests/test_pep_signing_domain.py backend/tests/test_wp03_work_permit_briefing_migration.py backend/tests/test_work_permit_signature_schemas.py tests/test_work_permit_signing.py tests/test_work_permit_service.py tests/api/test_work_permit_briefing_api.py tests/api/test_work_permit_signatures_api.py tests/api/test_work_permits_api.py -v`
Expected: PASS (весь контур + регрессия Ф1; отметить версию Python, если не 3.12).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/work_permits.py tests/api/test_work_permit_signatures_api.py
git commit -m "feat(work-permits): signature API — permit + briefing + list"
```

---

## Часть B — Frontend

> Конвенции — как в Ф1: api-модуль + `useAsyncResource`, панели в `features/work-permits/`. Клиент `@/api/client` (`apiClient`, auth + X-Tenant авто). Команды: `npm --prefix frontend run test -- <file>`, `npm --prefix frontend run build`.

### Task 10: DTO + словарь статусов подписи

**Files:**
- Modify: `frontend/src/types/dto/workPermits.ts`
- Modify: `frontend/src/lib/workPermitVocab.ts`

- [ ] **Step 1: Реализовать DTO**

В конец `frontend/src/types/dto/workPermits.ts` добавить:

```ts
export interface WorkPermitBriefingDto {
  id: string;
  work_permit_id: string;
  conducted_by_person_id: string | null;
  conducted_at: string | null;
  topics_text: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkPermitSignatureDto {
  id: string;
  stream: string; // "permit" | "briefing"
  object_type: string;
  object_id: string;
  purpose: string;
  status: string;
  signer_person_id: string | null;
  signer_name: string | null;
  content_hash: string | null;
  signed_at: string | null;
  confirm_code?: string | null;
}
```

- [ ] **Step 2: Реализовать словарь**

В `frontend/src/lib/workPermitVocab.ts` перед строкой `export const labelOf` добавить:

```ts
export const SIGN_STATUS_LABELS: Record<string, string> = {
  created: "Создан",
  awaiting_code: "Ожидает код",
  signed: "Подписан",
  declined: "Отклонён",
  expired: "Код истёк",
};
```

- [ ] **Step 3: Проверить типы**

Run: `npm --prefix frontend run build`
Expected: проходит.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/dto/workPermits.ts frontend/src/lib/workPermitVocab.ts
git commit -m "feat(work-permits): briefing/signature DTO + sign-status labels"
```

---

### Task 11: API-модуль — инструктаж + подписи

**Files:**
- Modify: `frontend/src/api/workPermits.ts`

- [ ] **Step 1: Реализовать**

В `frontend/src/api/workPermits.ts`:

1) Дополнить импорт DTO (строки 2-4):

```ts
import type {
  ReadinessReportDto, WorkPermitBriefingDto, WorkPermitDto, WorkPermitEventDto,
  WorkPermitMemberDto, WorkPermitPage, WorkPermitSignatureDto,
} from "@/types/dto/workPermits";
```

2) Внутри объекта `workPermitsApi` (после метода `extend`, перед закрывающей `};`) добавить методы:

```ts
  async getBriefings(id: string): Promise<WorkPermitBriefingDto[]> {
    return (await apiClient.get<WorkPermitBriefingDto[]>(`${base}/${id}/briefing`)).data;
  },
  async createBriefing(id: string, body: Record<string, unknown>): Promise<WorkPermitBriefingDto> {
    return (await apiClient.post<WorkPermitBriefingDto>(`${base}/${id}/briefing`, body)).data;
  },
  async updateBriefing(
    id: string, briefingId: string, body: Record<string, unknown>,
  ): Promise<WorkPermitBriefingDto> {
    return (await apiClient.patch<WorkPermitBriefingDto>(`${base}/${id}/briefing/${briefingId}`, body)).data;
  },
  async listSignatures(id: string): Promise<WorkPermitSignatureDto[]> {
    return (await apiClient.get<WorkPermitSignatureDto[]>(`${base}/${id}/signatures`)).data;
  },
  async createPermitSignature(
    id: string, body: { person_id: string; mode: "attested" | "code" },
  ): Promise<WorkPermitSignatureDto> {
    return (await apiClient.post<WorkPermitSignatureDto>(`${base}/${id}/signatures`, body)).data;
  },
  async createBriefingSignature(
    id: string, briefingId: string, body: { person_id: string; mode: "attested" | "code" },
  ): Promise<WorkPermitSignatureDto> {
    return (await apiClient.post<WorkPermitSignatureDto>(
      `${base}/${id}/briefing/${briefingId}/signatures`, body,
    )).data;
  },
  async confirmSignatureCode(requestId: string, code: string): Promise<void> {
    await apiClient.post(`/sign/pep/requests/${requestId}/confirm`, { code });
  },
```

- [ ] **Step 2: Проверить типы**

Run: `npm --prefix frontend run build`
Expected: проходит.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/workPermits.ts
git commit -m "feat(work-permits): api — briefing + signatures + confirm code"
```

---

### Task 12: Панели инструктажа и подписей

**Files:**
- Create: `frontend/src/features/work-permits/BriefingPanel.tsx`
- Create: `frontend/src/features/work-permits/SignaturesPanel.tsx`

- [ ] **Step 1: Реализовать SignaturesPanel** (переиспользуется обоими потоками — показывает строки участников + статус + действия)

Create `frontend/src/features/work-permits/SignaturesPanel.tsx`:

```tsx
import { useState } from "react";
import { toast } from "sonner";

import { workPermitsApi } from "@/api/workPermits";
import { Button } from "@/components/ui/button";
import { Can } from "@/components/permissions/Can";
import { SIGN_STATUS_LABELS, labelOf } from "@/lib/workPermitVocab";
import { PERMISSIONS } from "@/permissions/permissions";
import type { WorkPermitSignatureDto } from "@/types/dto/workPermits";

export interface SignerRow {
  personId: string;
  name: string;
  roleLabel: string;
}

interface Props {
  title: string;
  signers: SignerRow[];
  signatures: WorkPermitSignatureDto[];
  onSign: (personId: string, mode: "attested" | "code") => Promise<void>;
  onConfirm: (requestId: string, code: string) => Promise<void>;
}

export const SignaturesPanel = ({ title, signers, signatures, onSign, onConfirm }: Props) => {
  const [codeInput, setCodeInput] = useState<Record<string, string>>({});

  // latest signature per person
  const sigByPerson = new Map<string, WorkPermitSignatureDto>();
  for (const s of signatures) {
    if (s.signer_person_id) sigByPerson.set(s.signer_person_id, s);
  }

  const handleSign = async (personId: string, mode: "attested" | "code") => {
    try {
      await onSign(personId, mode);
    } catch {
      toast.error("Не удалось инициировать подпись");
    }
  };

  const handleConfirm = async (sig: WorkPermitSignatureDto) => {
    const code = (codeInput[sig.id] ?? "").trim();
    if (!code) {
      toast.error("Введите код");
      return;
    }
    try {
      await onConfirm(sig.id, code);
      setCodeInput((m) => ({ ...m, [sig.id]: "" }));
    } catch {
      toast.error("Код неверный или истёк");
    }
  };

  return (
    <div className="space-y-2">
      <div className="text-sm font-medium">{title}</div>
      {signers.length === 0 && <p className="text-sm text-muted-foreground">Подписанты не назначены</p>}
      <ul className="space-y-2 text-sm">
        {signers.map((row) => {
          const sig = sigByPerson.get(row.personId);
          const signed = sig?.status === "signed";
          const awaiting = sig?.status === "awaiting_code";
          return (
            <li key={row.personId} className="flex flex-wrap items-center justify-between gap-2 border-b pb-1">
              <span>
                {row.name} <span className="text-muted-foreground">· {row.roleLabel}</span>
              </span>
              <span className="flex items-center gap-2">
                <span className={signed ? "text-green-600" : "text-muted-foreground"}>
                  {sig ? labelOf(SIGN_STATUS_LABELS, sig.status) : "Не подписан"}
                </span>
                {!signed && (
                  <Can permission={PERMISSIONS.WORK_PERMIT_MANAGE}>
                    {awaiting && sig ? (
                      <>
                        <input
                          className="h-8 w-24 rounded-md border px-2 text-sm"
                          placeholder="код"
                          value={codeInput[sig.id] ?? ""}
                          onChange={(e) => setCodeInput((m) => ({ ...m, [sig.id]: e.target.value }))}
                        />
                        <Button size="sm" variant="outline" onClick={() => void handleConfirm(sig)}>
                          Подтвердить
                        </Button>
                      </>
                    ) : (
                      <>
                        <Button size="sm" variant="outline" onClick={() => void handleSign(row.personId, "attested")}>
                          Зафиксировать
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => void handleSign(row.personId, "code")}>
                          Запросить код
                        </Button>
                      </>
                    )}
                  </Can>
                )}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
};
```

- [ ] **Step 2: Реализовать BriefingPanel** (запись инструктажа + форма проведения + подписи бригады через SignaturesPanel)

Create `frontend/src/features/work-permits/BriefingPanel.tsx`:

```tsx
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { workPermitsApi } from "@/api/workPermits";
import { Button } from "@/components/ui/button";
import { Can } from "@/components/permissions/Can";
import { SignaturesPanel, type SignerRow } from "@/features/work-permits/SignaturesPanel";
import { MEMBER_ROLE_LABELS, labelOf } from "@/lib/workPermitVocab";
import { PERMISSIONS } from "@/permissions/permissions";
import type {
  WorkPermitBriefingDto, WorkPermitDto, WorkPermitSignatureDto,
} from "@/types/dto/workPermits";

const BRIEFING_ROLES = new Set(["member", "observer", "foreman"]);

interface Props {
  wp: WorkPermitDto;
  nameOf: (personId: string) => string;
  signatures: WorkPermitSignatureDto[];
  onRefresh: () => void;
}

export const BriefingPanel = ({ wp, nameOf, signatures, onRefresh }: Props) => {
  const [briefing, setBriefing] = useState<WorkPermitBriefingDto | null>(null);
  const [topics, setTopics] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    workPermitsApi.getBriefings(wp.id).then((rows) => setBriefing(rows[0] ?? null)).catch(() => undefined);
  }, [wp.id]);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    setSaving(true);
    try {
      await workPermitsApi.createBriefing(wp.id, {
        topics_text: topics || null,
        conducted_at: new Date().toISOString(),
      });
      toast.success("Инструктаж проведён");
      setTopics("");
      load();
    } catch {
      toast.error("Не удалось сохранить инструктаж");
    } finally {
      setSaving(false);
    }
  };

  const briefingSigners: SignerRow[] = wp.members
    .filter((m) => BRIEFING_ROLES.has(m.role))
    .map((m) => ({ personId: m.person_id, name: nameOf(m.person_id), roleLabel: labelOf(MEMBER_ROLE_LABELS, m.role) }));

  const briefingSignatures = signatures.filter((s) => s.stream === "briefing");

  const handleSign = async (personId: string, mode: "attested" | "code") => {
    if (!briefing) return;
    const res = await workPermitsApi.createBriefingSignature(wp.id, briefing.id, { person_id: personId, mode });
    if (mode === "code" && res.confirm_code) {
      toast.success(`Код для подписанта: ${res.confirm_code}`);
    }
    onRefresh();
  };

  const handleConfirm = async (requestId: string, code: string) => {
    await workPermitsApi.confirmSignatureCode(requestId, code);
    toast.success("Подпись подтверждена");
    onRefresh();
  };

  return (
    <div className="space-y-3">
      {briefing ? (
        <div className="text-sm">
          <div className="text-muted-foreground text-xs">Целевой инструктаж проведён</div>
          {briefing.conducted_at && (
            <div>{new Date(briefing.conducted_at).toLocaleString("ru-RU")}</div>
          )}
          {briefing.topics_text && <div className="whitespace-pre-wrap">{briefing.topics_text}</div>}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">Целевой инструктаж не проведён</p>
      )}

      {!briefing && (
        <Can permission={PERMISSIONS.WORK_PERMIT_MANAGE}>
          <div className="space-y-2">
            <textarea
              className="min-h-[60px] w-full rounded-md border px-3 py-2 text-sm"
              placeholder="Темы инструктажа"
              value={topics}
              onChange={(e) => setTopics(e.target.value)}
            />
            <Button size="sm" disabled={saving} onClick={() => void handleCreate()}>
              {saving ? "Сохранение..." : "Провести инструктаж"}
            </Button>
          </div>
        </Can>
      )}

      {briefing && (
        <SignaturesPanel
          title="Ознакомление бригады"
          signers={briefingSigners}
          signatures={briefingSignatures}
          onSign={handleSign}
          onConfirm={handleConfirm}
        />
      )}
    </div>
  );
};
```

- [ ] **Step 3: Проверить типы**

Run: `npm --prefix frontend run build`
Expected: проходит.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/work-permits/SignaturesPanel.tsx frontend/src/features/work-permits/BriefingPanel.tsx
git commit -m "feat(work-permits): BriefingPanel + SignaturesPanel"
```

---

### Task 13: Монтаж панелей на карточке + тест

**Files:**
- Modify: `frontend/src/pages/work-permits/WorkPermitDetailPage.tsx`
- Modify: `frontend/src/__tests__/WorkPermitDetailPage.test.tsx`

- [ ] **Step 1: Обновить мок в существующем тесте (иначе сломается)**

В `frontend/src/__tests__/WorkPermitDetailPage.test.tsx` заменить `vi.mock("@/api/workPermits", ...)` на расширенный (страница теперь дёргает подписи/инструктаж):

```tsx
vi.mock("@/api/workPermits", () => ({
  workPermitsApi: {
    get: (...a: unknown[]) => getMock(...a),
    readiness: () => Promise.resolve({ ok: true, violations: [] }),
    events: () => Promise.resolve([]),
    getBriefings: () => Promise.resolve([]),
    listSignatures: () => Promise.resolve([]),
  },
  fetchAllPersons: () => Promise.resolve([]),
}));
```

- [ ] **Step 2: Добавить тест-проверку панели подписей**

Добавить в `describe("WorkPermitDetailPage", ...)`:

```tsx
  it("показывает панель подписей ответственных", async () => {
    setRole([PERMISSIONS.WORK_PERMIT_VIEW, PERMISSIONS.WORK_PERMIT_MANAGE]);
    renderAt();
    expect(await screen.findByText(/подписи ответственных/i)).toBeInTheDocument();
  });
```

- [ ] **Step 3: Прогнать тест — должен упасть**

Run: `npm --prefix frontend run test -- WorkPermitDetailPage`
Expected: FAIL (нет текста «Подписи ответственных»).

- [ ] **Step 4: Реализовать монтаж панелей**

В `frontend/src/pages/work-permits/WorkPermitDetailPage.tsx`:

1) Добавить импорты (рядом с другими импортами панелей):

```tsx
import { BriefingPanel } from "@/features/work-permits/BriefingPanel";
import { SignaturesPanel, type SignerRow } from "@/features/work-permits/SignaturesPanel";
import { MEMBER_ROLE_LABELS, labelOf } from "@/lib/workPermitVocab";
import type { WorkPermitSignatureDto } from "@/types/dto/workPermits";
```

> NB: `MEMBER_ROLE_LABELS` и `labelOf` уже импортированы вверху — НЕ дублировать импорт, при необходимости просто дополнить существующую строку импорта из `@/lib/workPermitVocab`.

2) В тело компонента (рядом с `const [events, setEvents] = ...`) добавить состояние подписей:

```tsx
  const [signatures, setSignatures] = useState<WorkPermitSignatureDto[]>([]);
```

3) В `refreshSide` дополнить загрузку подписей:

```tsx
  const refreshSide = useCallback(() => {
    workPermitsApi.readiness(id).then(setReadiness).catch(() => undefined);
    workPermitsApi.events(id).then(setEvents).catch(() => undefined);
    workPermitsApi.listSignatures(id).then(setSignatures).catch(() => undefined);
  }, [id]);
```

4) Перед `return (` добавить расчёт ответственных подписантов и хендлеры:

```tsx
  const RESP_ROLES = new Set(["issuer", "supervisor", "admitter", "foreman"]);
  const responsibleSigners: SignerRow[] = wp.members
    .filter((m) => RESP_ROLES.has(m.role))
    .map((m) => ({ personId: m.person_id, name: nameOf(m.person_id), roleLabel: labelOf(MEMBER_ROLE_LABELS, m.role) }));
  const permitSignatures = signatures.filter((s) => s.stream === "permit");

  const signPermit = async (personId: string, mode: "attested" | "code") => {
    const res = await workPermitsApi.createPermitSignature(wp.id, { person_id: personId, mode });
    if (mode === "code" && res.confirm_code) toast.success(`Код для подписанта: ${res.confirm_code}`);
    refreshSide();
  };
  const confirmSign = async (requestId: string, code: string) => {
    await workPermitsApi.confirmSignatureCode(requestId, code);
    toast.success("Подпись подтверждена");
    refreshSide();
  };
```

5) Перед блоком «Events log» (`{/* Events log */}`) вставить две панели:

```tsx
      {/* Целевой инструктаж */}
      <div className="rounded-md border p-3">
        <div className="text-sm font-medium mb-2">Целевой инструктаж</div>
        <BriefingPanel wp={wp} nameOf={nameOf} signatures={signatures} onRefresh={refreshSide} />
      </div>

      {/* Подписи ответственных лиц */}
      <div className="rounded-md border p-3">
        <SignaturesPanel
          title="Подписи ответственных"
          signers={responsibleSigners}
          signatures={permitSignatures}
          onSign={signPermit}
          onConfirm={confirmSign}
        />
      </div>
```

- [ ] **Step 5: Прогнать тест — должен пройти**

Run: `npm --prefix frontend run test -- WorkPermitDetailPage`
Expected: PASS (3 теста).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/work-permits/WorkPermitDetailPage.tsx frontend/src/__tests__/WorkPermitDetailPage.test.tsx
git commit -m "feat(work-permits): mount briefing + signatures panels on detail card"
```

---

### Task 14: Полная верификация

- [ ] **Step 1: Backend-контур Ф2**

Run: `python -m pytest backend/tests/test_pep_signing_domain.py backend/tests/test_wp03_work_permit_briefing_migration.py backend/tests/test_work_permit_signature_schemas.py tests/test_work_permit_signing.py tests/test_work_permit_service.py tests/api/test_work_permit_briefing_api.py tests/api/test_work_permit_signatures_api.py tests/api/test_work_permits_api.py -v`
Expected: всё PASS (отметить версию Python, если не 3.12).

- [ ] **Step 2: Frontend тесты + типы + сборка**

Run: `npm --prefix frontend run test -- WorkPermitDetailPage` затем `npm --prefix frontend run build`
Expected: тесты PASS; сборка без ошибок типов/линта.

- [ ] **Step 3: Ручная проверка (preview)**

Запустить dev-preview, войти под admin, открыть карточку наряда: провести целевой инструктаж, зафиксировать подпись ответственного (attested) и проверить code-flow (запросить код → подтвердить), убедиться, что статусы и панели обновляются. Зафиксировать скриншот.

- [ ] **Step 4: Финальный commit (если остались незакоммиченные правки)**

```bash
git add -A && git commit -m "chore(work-permits): Ф2 verification fixes" || echo "nothing to commit"
```

---

## Self-Review (выполнено автором плана)

- **Покрытие спеки:** §4 модель `work_permit_briefing` → Task 2/3; §5 ПЭП purposes + `_build_content` → Task 1/4; §6 сервис подписи (membership + dup-guard, оба режима) → Task 6; §7 API (инструктаж + подписи + список, confirm через готовый ПЭП) → Task 8/9; §8 фронт-архитектура → Task 10-13; §9 поток подписи (attested + code) → Task 6/9/12/13; §10 ошибки (PepNotFound→404, PepConflict→409, code wrong→409) → Task 9/12; §11 тесты → Task 1/2/4/6/7/8/9/13/14; §3 права (переиспользование Ф1-кодов) → Task 12/13. Гэпов нет.
- **Уточнение спеки (сознательное):** тело создания подписи — `{person_id, mode}` без `role` (членство и его класс выводятся из `WorkPermitMember`; подпись — одна на person/объект, роль не хранится в `SignatureRequest`). Это снимает многоролевую неоднозначность и упрощает контракт.
- **Плейсхолдеры:** в шагах с кодом приведён полный код; `NB`-пометки указывают точки сверки имён фикстур (`session`/`tenant`/`admin_client`/`_make_person`/`Person`) с существующими тестами — не заглушки логики.
- **Согласованность типов:** `object_type`/`purpose`/`mode`/классы ролей едины сквозь backend↔frontend; `WorkPermitSignatureDto.stream` ∈ {`permit`,`briefing`} согласован между `_signature_read` (Task 9) и фильтрами панелей (Task 12/13); `confirm_code` присутствует только в ответе создания (code-режим), в списке — `None`; `SignerRow`/`SignaturesPanel` props идентичны в Task 12 и 13.
