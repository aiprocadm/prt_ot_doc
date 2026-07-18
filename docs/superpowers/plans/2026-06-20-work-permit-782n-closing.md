# Наряд-допуск 782н Ф3b «закрытие с подписями» — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сделать закрытие наряда-допуска 782н юридически значимым: акт окончания работ + две подписи ПЭП («сдал» производитель работ / «принял» ответственный руководитель или допускающий), гейтящие переход `issued→closed`.

**Architecture:** Подход A (эпитаксия на Ф2). Акт закрытия — 1:1 с нарядом, поэтому два поля на `work_permit` (без новой таблицы). Подписи — полиморфно в `signature_requests` через переиспользуемый Ф2-модуль `domains/work_permits/signing.py` (новый `object_type="work_permit_closing"`). Гейт — чистый предикат `closing_readiness` в `lifecycle.py` (тестируется изолированно), врезанный в `service.close()` через ленивое чтение подписанных видов (как `issue` врезает `enforce_brigade_readiness`). Гейт распространяется ТОЛЬКО на `close`; `cancel` не затронут.

**Tech Stack:** Python 3.12 (канон CI; локально допустим доступный Python с отметкой версии — CLAUDE.md), FastAPI, SQLAlchemy async, Alembic, pytest; фронт — React/Vite/TS, vitest.

**Среда выполнения:** Win + локальный Python через `.venv\Scripts\python.exe`; pytest запускать PowerShell→файл, итог по EXIT-коду (summary-строка теряется блочной буферизацией — [[py313_win_pytest_invocation]]). Frontend: `npm --prefix frontend run test -- <file>` и `npm --prefix frontend run build`.

**Ветка:** `feat/work-permits-782n-closing` (уже создана, спека закоммичена `a973212`).

**NB по объёму слома контракта `close`:** demo-seed для нарядов в репозитории НЕТ (проверено: `grep -rln "WorkPermit" backend/app | grep -i seed` пусто). Единственные не-тестовые вызовы `close()` — эндпоинт `/close`. Слом затрагивает ровно два существующих теста (Task 7). Поэтому §8 спеки в части «demo-seed» — неприменим; обновляем только тесты.

---

## File Structure

**Backend (создать/изменить):**
- Modify: `backend/app/models/work_permit.py` — +2 поля на `WorkPermit`.
- Create: `backend/app/migrations/versions/20260620_wp05_work_permit_closing.py` — аддитивная миграция.
- Modify: `backend/app/domains/work_permits/lifecycle.py` — чистый `closing_readiness` + `ClosingReadiness` + `WorkPermitClosingIncomplete` + ролевые множества.
- Modify: `backend/app/domains/signing/pep.py` — `PEP_PURPOSES` += `work_permit_closing`.
- Modify: `backend/app/services/pep_signing.py` — ветка `_build_content` для `work_permit_closing`.
- Modify: `backend/app/domains/work_permits/signing.py` — `sign_closing` + `CLOSING_SIGNER_ROLES`.
- Modify: `backend/app/domains/work_permits/service.py` — `record_completion`, `_signed_closing_kinds`, гейт в `close()`.
- Modify: `backend/app/schemas/work_permit.py` — `WorkPermitClosingRecordCreate`, `WorkPermitClosingSummary`.
- Modify: `backend/app/api/routes/work_permits.py` — эндпоинты `closing` (record/summary/signatures) + 409-маппинг в `close_endpoint`.

**Backend (тесты):**
- Create: `tests/test_work_permit_closing_migration.py` — guard миграции wp05.
- Create: `tests/test_work_permit_closing_domain.py` — `PEP_PURPOSES`, снимок хэша, `closing_readiness`.
- Create: `tests/test_work_permit_closing_service.py` — `record_completion`, `sign_closing`, гейт `close`.
- Create: `tests/api/test_work_permit_closing_api.py` — closing CRUD + signatures + close-гейт + tenant-isolation.
- Modify: `tests/test_work_permit_service.py` — обновить `test_create_add_member_issue_suspend_resume_close` под гейт.
- Modify: `tests/api/test_work_permits_api.py` — обновить close-успех (строка ~110) под гейт.

**Frontend (создать/изменить):**
- Modify: `frontend/src/api/workPermits.ts` — `getClosing`, `recordCompletion`, `createClosingSignature`.
- Modify: `frontend/src/types/dto/workPermits.ts` — `WorkPermitClosingSummaryDto`.
- Modify: `frontend/src/lib/workPermitVocab.ts` — подписи «сдал/принял» + недостающих пунктов.
- Create: `frontend/src/features/work-permits/ClosingPanel.tsx` — панель закрытия.
- Modify: `frontend/src/pages/work-permits/WorkPermitDetailPage.tsx` — монтаж `ClosingPanel`.
- Create: `frontend/src/features/work-permits/ClosingPanel.test.tsx` — тест панели.

---

## Task 1: Миграция wp05 + поля акта на модели

**Files:**
- Create: `backend/app/migrations/versions/20260620_wp05_work_permit_closing.py`
- Modify: `backend/app/models/work_permit.py` (класс `WorkPermit`, после `closed_at`/`suspended_at`, ~строка 40)
- Test: `tests/test_work_permit_closing_migration.py`

- [ ] **Step 1: Подтвердить истинный single-head перед цепочкой**

Run:
```
.venv\Scripts\python.exe -m alembic -c backend/alembic.ini heads
```
Expected: ровно один head. Если это `20260618_wp04_work_permit_ops_journal` — `down_revision` ниже верен. Если head иной (миграция бланка позже) — поставить `down_revision` на фактический head и отметить это в коммите. (Файл `alembic.ini` может быть в `backend/`; при ошибке пути — `backend/app/alembic.ini` или `python -m alembic` из `backend/`.)

- [ ] **Step 2: Написать guard-тест миграции (failing)**

Create `tests/test_work_permit_closing_migration.py`:
```python
"""wp05 guard: цепочка от истинного head, состав колонок, honest downgrade."""
from __future__ import annotations

import importlib.util
from pathlib import Path

MIG = (
    Path(__file__).resolve().parents[1]
    / "backend/app/migrations/versions/20260620_wp05_work_permit_closing.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("wp05_mig", MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_wp05_chain_and_revision():
    mod = _load()
    assert mod.revision == "20260620_wp05_work_permit_closing"
    assert mod.down_revision == "20260618_wp04_work_permit_ops_journal"


def test_wp05_adds_completion_columns():
    src = MIG.read_text(encoding="utf-8")
    # table name LITERAL (AST-audit blindspot)
    assert '"work_permit"' in src
    assert "completion_text" in src
    assert "completion_recorded_at" in src


def test_wp05_downgrade_drops_added_columns():
    src = MIG.read_text(encoding="utf-8")
    assert 'op.drop_column("work_permit", "completion_text")' in src
    assert 'op.drop_column("work_permit", "completion_recorded_at")' in src
```

- [ ] **Step 3: Запустить — убедиться, что падает**

Run (PowerShell→file, читать EXIT):
```
.venv\Scripts\python.exe -m pytest tests/test_work_permit_closing_migration.py -p no:cacheprovider 2>&1 | Tee-Object test_wp05_guard.txt; echo "EXIT=$LASTEXITCODE"
```
Expected: FAIL (файл миграции ещё не создан → ImportError/FileNotFound).

- [ ] **Step 4: Создать миграцию**

Create `backend/app/migrations/versions/20260620_wp05_work_permit_closing.py`:
```python
"""wp05: closing (Ф3b) — completion-act columns on work_permit (additive).

Закрытие 1:1 с нарядом → поля на work_permit, без новой таблицы. Подписи
закрытия живут в signature_requests (object_type="work_permit_closing").
Имена таблиц ЛИТЕРАЛОМ (AST-audit blindspot). Honest downgrade удаляет колонки.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260620_wp05_work_permit_closing"
down_revision = "20260618_wp04_work_permit_ops_journal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("work_permit", sa.Column("completion_text", sa.Text(), nullable=True))
    op.add_column(
        "work_permit",
        sa.Column("completion_recorded_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("work_permit", "completion_recorded_at")
    op.drop_column("work_permit", "completion_text")
```

- [ ] **Step 5: Добавить поля в ORM-модель**

In `backend/app/models/work_permit.py`, в классе `WorkPermit` после `suspended_at` (строка ~40) добавить:
```python
    completion_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    completion_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```
(`Text`, `DateTime`, `datetime` уже импортированы — используются выше в файле.)

- [ ] **Step 6: Запустить guard + проверить применимость миграции**

Run:
```
.venv\Scripts\python.exe -m pytest tests/test_work_permit_closing_migration.py -p no:cacheprovider 2>&1 | Tee-Object test_wp05_guard.txt; echo "EXIT=$LASTEXITCODE"
```
Expected: EXIT=0 (3 passed).

- [ ] **Step 7: Коммит**

```bash
git add backend/app/migrations/versions/20260620_wp05_work_permit_closing.py backend/app/models/work_permit.py tests/test_work_permit_closing_migration.py
git commit -m "feat(work-permits): wp05 — поля акта закрытия на work_permit (Ф3b)"
```

---

## Task 2: ПЭП-purpose + канонический снимок `work_permit_closing`

**Files:**
- Modify: `backend/app/domains/signing/pep.py:15` (`PEP_PURPOSES`)
- Modify: `backend/app/services/pep_signing.py` (`_build_content`, после ветки `work_permit_briefing`, ~строка 133)
- Test: `tests/test_work_permit_closing_domain.py`

- [ ] **Step 1: Написать тест (failing)**

Create `tests/test_work_permit_closing_domain.py`:
```python
"""Ф3b домен: PEP_PURPOSES + детерминированный снимок closing + closing_readiness."""
from __future__ import annotations

import pytest

from app.domains.signing.pep import PEP_PURPOSES


def test_pep_purposes_has_closing():
    assert "work_permit_closing" in PEP_PURPOSES


@pytest.mark.asyncio
async def test_closing_snapshot_is_deterministic(sessionmaker, data_factory):
    from app.services.pep_signing import PepSigningService
    from app.domains.work_permits import service as svc

    async with sessionmaker() as session:
        person = await data_factory.create_person(session)
        wp = await svc.create_work_permit(
            session, tenant_id=person.tenant_id, work_type="height", zone_text="z",
            number="НД-1",
        )
        await svc.record_completion(
            session, tenant_id=person.tenant_id, work_permit_id=wp.id,
            completion_text="работы окончены, место сдано", actor_user_id="u1",
        )
        ps = PepSigningService(session, person.tenant_id)
        a = await ps._build_content("work_permit_closing", wp.id)
        b = await ps._build_content("work_permit_closing", wp.id)
        assert a == b
        assert a["work_permit_id"] == wp.id
        assert a["completion_text"] == "работы окончены, место сдано"
```
(Тест на `record_completion` — определена в Task 4; этот тест запускаем зелёным после Task 4. Сейчас проверяем только первый кейс `test_pep_purposes_has_closing` — он падает до Step 2.)

- [ ] **Step 2: Запустить первый кейс — убедиться, что падает**

Run:
```
.venv\Scripts\python.exe -m pytest "tests/test_work_permit_closing_domain.py::test_pep_purposes_has_closing" -p no:cacheprovider 2>&1 | Tee-Object test_dom1.txt; echo "EXIT=$LASTEXITCODE"
```
Expected: FAIL (`work_permit_closing` ещё не в `PEP_PURPOSES`).

- [ ] **Step 3: Расширить PEP_PURPOSES**

In `backend/app/domains/signing/pep.py`, строка 15 — добавить элемент во frozenset:
```python
PEP_PURPOSES = frozenset(
    {"document", "acknowledgement", "ppe_issue", "briefing", "work_permit", "work_permit_briefing", "work_permit_closing"}
```
(сохранить закрывающую `)` как в оригинале).

- [ ] **Step 4: Добавить ветку `_build_content`**

In `backend/app/services/pep_signing.py`, сразу после блока `if object_type == "work_permit_briefing":` (заканчивается ~строкой 133, перед `raise PepConflict(f"unsupported object_type...")`) добавить:
```python
        if object_type == "work_permit_closing":
            wp = await self.session.get(WorkPermit, object_id)
            if wp is None or str(wp.tenant_id) != str(self.tenant_id):
                raise PepNotFound("work_permit")
            return {
                "work_permit_closing_id": wp.id,
                "work_permit_id": wp.id,
                "number": wp.number,
                "completion_text": wp.completion_text,
                "completion_recorded_at": (
                    wp.completion_recorded_at.isoformat() if wp.completion_recorded_at else None
                ),
                "status": wp.status,
            }
```
(`WorkPermit` уже импортирован — строка 31.)

- [ ] **Step 5: Запустить первый кейс — убедиться, что прошёл**

Run:
```
.venv\Scripts\python.exe -m pytest "tests/test_work_permit_closing_domain.py::test_pep_purposes_has_closing" -p no:cacheprovider 2>&1 | Tee-Object test_dom1.txt; echo "EXIT=$LASTEXITCODE"
```
Expected: EXIT=0 (1 passed). (Снимок-тест станет зелёным после Task 4 — ок.)

- [ ] **Step 6: Коммит**

```bash
git add backend/app/domains/signing/pep.py backend/app/services/pep_signing.py tests/test_work_permit_closing_domain.py
git commit -m "feat(work-permits): ПЭП purpose + снимок work_permit_closing (Ф3b)"
```

---

## Task 3: Чистый предикат `closing_readiness` в lifecycle

**Files:**
- Modify: `backend/app/domains/work_permits/lifecycle.py` (в конец файла)
- Test: `tests/test_work_permit_closing_domain.py` (дополнить)

- [ ] **Step 1: Дописать unit-тесты предиката (failing)**

Append to `tests/test_work_permit_closing_domain.py`:
```python
from app.domains.work_permits.lifecycle import closing_readiness


def test_readiness_all_present():
    r = closing_readiness(completion_text="готово", signed_kinds={"handover", "acceptance"})
    assert r.can_close is True
    assert r.missing == []


def test_readiness_missing_act():
    r = closing_readiness(completion_text=None, signed_kinds={"handover", "acceptance"})
    assert r.can_close is False
    assert "completion_act" in r.missing


def test_readiness_missing_handover():
    r = closing_readiness(completion_text="готово", signed_kinds={"acceptance"})
    assert r.can_close is False
    assert "handover_signature" in r.missing


def test_readiness_missing_acceptance():
    r = closing_readiness(completion_text="готово", signed_kinds={"handover"})
    assert r.can_close is False
    assert "acceptance_signature" in r.missing


def test_readiness_empty_text_is_missing_act():
    r = closing_readiness(completion_text="   ", signed_kinds={"handover", "acceptance"})
    assert r.can_close is False
    assert "completion_act" in r.missing
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run:
```
.venv\Scripts\python.exe -m pytest tests/test_work_permit_closing_domain.py -k readiness -p no:cacheprovider 2>&1 | Tee-Object test_dom_rd.txt; echo "EXIT=$LASTEXITCODE"
```
Expected: FAIL (`closing_readiness` не определён).

- [ ] **Step 3: Реализовать предикат + исключение + роли**

Append to `backend/app/domains/work_permits/lifecycle.py`:
```python
from dataclasses import dataclass, field

# Роли подписи закрытия (782н): "сдал" — производитель работ; "принял" —
# ответственный руководитель ИЛИ допускающий.
HANDOVER_ROLES = frozenset({"foreman"})
ACCEPTANCE_ROLES = frozenset({"supervisor", "admitter"})
CLOSING_SIGNER_ROLES = HANDOVER_ROLES | ACCEPTANCE_ROLES


def role_to_closing_kind(role: str) -> str | None:
    """Вид подписи закрытия по роли члена бригады, либо None если роль не подписывает закрытие."""
    if role in HANDOVER_ROLES:
        return "handover"
    if role in ACCEPTANCE_ROLES:
        return "acceptance"
    return None


@dataclass(frozen=True)
class ClosingReadiness:
    can_close: bool
    missing: list[str] = field(default_factory=list)


def closing_readiness(*, completion_text: str | None, signed_kinds: set[str]) -> ClosingReadiness:
    """Готовность наряда к закрытию: акт оформлен + есть SIGNED «сдал» и «принял».

    Чистая функция (без I/O). ``signed_kinds`` — множество видов закрытия
    ({"handover","acceptance"}), у которых есть SIGNED-подпись.
    """
    missing: list[str] = []
    if not (completion_text and completion_text.strip()):
        missing.append("completion_act")
    if "handover" not in signed_kinds:
        missing.append("handover_signature")
    if "acceptance" not in signed_kinds:
        missing.append("acceptance_signature")
    return ClosingReadiness(can_close=not missing, missing=missing)


class WorkPermitClosingIncomplete(Exception):
    """close вызван до готовности гейта закрытия (maps to HTTP 409)."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__(f"closing requirements not met: {missing}")
```

- [ ] **Step 4: Запустить — убедиться, что прошло**

Run:
```
.venv\Scripts\python.exe -m pytest tests/test_work_permit_closing_domain.py -k readiness -p no:cacheprovider 2>&1 | Tee-Object test_dom_rd.txt; echo "EXIT=$LASTEXITCODE"
```
Expected: EXIT=0 (5 passed).

- [ ] **Step 5: Коммит**

```bash
git add backend/app/domains/work_permits/lifecycle.py tests/test_work_permit_closing_domain.py
git commit -m "feat(work-permits): чистый предикат closing_readiness + роли закрытия (Ф3b)"
```

---

## Task 4: Сервис — `record_completion`, чтение видов подписи, гейт в `close()`

**Files:**
- Modify: `backend/app/domains/work_permits/service.py` (добавить `record_completion`, `_signed_closing_kinds`; врезать гейт в `close`)
- Test: `tests/test_work_permit_closing_service.py`

- [ ] **Step 1: Написать сервис-тесты (failing)**

Create `tests/test_work_permit_closing_service.py`:
```python
"""Ф3b сервис: record_completion, гейт close (без подписей → ошибка; с актом+сдал+принял → ок)."""
from __future__ import annotations

import pytest

from app.domains.work_permits import lifecycle as lc
from app.domains.work_permits import service as svc
from app.domains.work_permits.signing import sign_closing


async def _issued_permit_with_brigade(session, data_factory):
    """Наряд в issued с foreman+supervisor; личные допуски не требуются (гейт issue не в фокусе)."""
    foreman = await data_factory.create_person(session)
    supervisor = await data_factory.create_person(session)
    tid = foreman.tenant_id
    wp = await svc.create_work_permit(session, tenant_id=tid, work_type="height", zone_text="z")
    await svc.add_member(session, tenant_id=tid, work_permit_id=wp.id, person_id=foreman.id, role="foreman")
    await svc.add_member(session, tenant_id=tid, work_permit_id=wp.id, person_id=supervisor.id, role="supervisor")
    # перевести в issued напрямую через _transition (минуя гейт бригады — не предмет теста)
    wp.status = lc.STATUS_ISSUED
    await session.flush()
    return wp, foreman, supervisor, tid


@pytest.mark.asyncio
async def test_record_completion_upsert(sessionmaker, data_factory):
    async with sessionmaker() as session:
        wp, *_ , tid = await _issued_permit_with_brigade(session, data_factory)
        out = await svc.record_completion(
            session, tenant_id=tid, work_permit_id=wp.id,
            completion_text="место сдано", actor_user_id="u1",
        )
        assert out.completion_text == "место сдано"
        assert out.completion_recorded_at is not None
        # идемпотентный upsert
        out2 = await svc.record_completion(
            session, tenant_id=tid, work_permit_id=wp.id,
            completion_text="место сдано-2", actor_user_id="u1",
        )
        assert out2.completion_text == "место сдано-2"


@pytest.mark.asyncio
async def test_record_completion_rejects_non_issued(sessionmaker, data_factory):
    async with sessionmaker() as session:
        person = await data_factory.create_person(session)
        wp = await svc.create_work_permit(session, tenant_id=person.tenant_id, work_type="height", zone_text="z")
        # статус draft
        with pytest.raises(lc.WorkPermitTransitionError):
            await svc.record_completion(
                session, tenant_id=person.tenant_id, work_permit_id=wp.id,
                completion_text="x", actor_user_id="u1",
            )


@pytest.mark.asyncio
async def test_close_gate_blocks_without_signatures(sessionmaker, data_factory):
    async with sessionmaker() as session:
        wp, foreman, supervisor, tid = await _issued_permit_with_brigade(session, data_factory)
        await svc.record_completion(
            session, tenant_id=tid, work_permit_id=wp.id, completion_text="готово", actor_user_id="u1",
        )
        with pytest.raises(lc.WorkPermitClosingIncomplete) as ei:
            await svc.close(session, tenant_id=tid, work_permit_id=wp.id, actor_user_id="u1")
        assert "handover_signature" in ei.value.missing
        assert "acceptance_signature" in ei.value.missing


@pytest.mark.asyncio
async def test_close_succeeds_with_act_and_both_signatures(sessionmaker, data_factory):
    async with sessionmaker() as session:
        wp, foreman, supervisor, tid = await _issued_permit_with_brigade(session, data_factory)
        await svc.record_completion(
            session, tenant_id=tid, work_permit_id=wp.id, completion_text="готово", actor_user_id="u1",
        )
        await sign_closing(session, tenant_id=tid, work_permit_id=wp.id,
                           person_id=foreman.id, mode="attested", requested_by="u1")
        await sign_closing(session, tenant_id=tid, work_permit_id=wp.id,
                           person_id=supervisor.id, mode="attested", requested_by="u1")
        closed = await svc.close(session, tenant_id=tid, work_permit_id=wp.id, actor_user_id="u1")
        assert closed.status == lc.STATUS_CLOSED


@pytest.mark.asyncio
async def test_cancel_not_gated(sessionmaker, data_factory):
    async with sessionmaker() as session:
        wp, *_ , tid = await _issued_permit_with_brigade(session, data_factory)
        cancelled = await svc.cancel(session, tenant_id=tid, work_permit_id=wp.id, actor_user_id="u1")
        assert cancelled.status == lc.STATUS_CANCELLED
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run:
```
.venv\Scripts\python.exe -m pytest tests/test_work_permit_closing_service.py -p no:cacheprovider 2>&1 | Tee-Object test_svc.txt; echo "EXIT=$LASTEXITCODE"
```
Expected: FAIL (`record_completion`/`sign_closing` не определены; гейта в `close` нет).

- [ ] **Step 3: Добавить `record_completion` и `_signed_closing_kinds` в сервис**

In `backend/app/domains/work_permits/service.py`, после `cancel` (~строка 240) добавить:
```python
async def record_completion(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str,
    completion_text: str, actor_user_id: str | None = None,
) -> WorkPermit | None:
    """Оформить/обновить акт окончания работ (idempotent upsert). Только в issued."""
    wp = await _get(session, tenant_id, work_permit_id)
    if wp is None:
        return None
    if wp.status != lc.STATUS_ISSUED:
        raise lc.WorkPermitTransitionError(str(wp.status), "record_completion")
    wp.completion_text = completion_text
    wp.completion_recorded_at = _now()
    await session.flush()
    await session.refresh(wp)
    return wp


async def _signed_closing_kinds(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str,
) -> set[str]:
    """Виды подписи закрытия ({"handover","acceptance"}) с хотя бы одной SIGNED-подписью.

    SIGNED closing-подпись валидна, только если её подписант — действующий член
    бригады наряда с подписывающей закрытие ролью (роль резолвится «на сейчас»).
    """
    from app.models.models import SignatureRequest

    rows = (await session.execute(
        select(SignatureRequest.signer_person_id).where(
            SignatureRequest.tenant_id == tenant_id,
            SignatureRequest.object_type == "work_permit_closing",
            SignatureRequest.object_id == work_permit_id,
            SignatureRequest.status == "signed",
        )
    )).scalars().all()
    signed_person_ids = {p for p in rows if p}
    if not signed_person_ids:
        return set()
    role_rows = (await session.execute(
        select(WorkPermitMember.person_id, WorkPermitMember.role).where(
            WorkPermitMember.tenant_id == tenant_id,
            WorkPermitMember.work_permit_id == work_permit_id,
            WorkPermitMember.person_id.in_(tuple(signed_person_ids)),
        )
    )).all()
    kinds: set[str] = set()
    for person_id, role in role_rows:
        kind = lc.role_to_closing_kind(role)
        if kind:
            kinds.add(kind)
    return kinds
```

- [ ] **Step 4: Врезать гейт в `close()`**

In `backend/app/domains/work_permits/service.py`, заменить тело `close` (строки 229-233) на:
```python
async def close(session, *, tenant_id, work_permit_id, actor_user_id, photo_file_id=None, note=None):
    wp = await _get(session, tenant_id, work_permit_id)
    if wp is None:
        return None
    signed = await _signed_closing_kinds(session, tenant_id=tenant_id, work_permit_id=work_permit_id)
    readiness = lc.closing_readiness(completion_text=wp.completion_text, signed_kinds=signed)
    if not readiness.can_close:
        raise lc.WorkPermitClosingIncomplete(readiness.missing)
    return await _transition(
        session, tenant_id=tenant_id, work_permit_id=work_permit_id, target=lc.STATUS_CLOSED,
        event_type="closed", actor_user_id=actor_user_id, photo_file_id=photo_file_id, note=note,
    )
```

- [ ] **Step 5: Запустить — убедиться, что прошло**

Run:
```
.venv\Scripts\python.exe -m pytest tests/test_work_permit_closing_service.py tests/test_work_permit_closing_domain.py -p no:cacheprovider 2>&1 | Tee-Object test_svc.txt; echo "EXIT=$LASTEXITCODE"
```
Expected: EXIT=0 (сервис 5 + домен 7+1 снимок). Снимок-тест из Task 2 теперь зелёный (есть `record_completion`).

- [ ] **Step 6: Коммит**

```bash
git add backend/app/domains/work_permits/service.py tests/test_work_permit_closing_service.py
git commit -m "feat(work-permits): record_completion + гейт close по подписям (Ф3b)"
```

---

## Task 5: `sign_closing` в модуле подписи

**Files:**
- Modify: `backend/app/domains/work_permits/signing.py` (добавить `CLOSING_SIGNER_ROLES`-импорт и `sign_closing`)
- Test: `tests/test_work_permit_closing_service.py` (дополнить — валидация членства и дубль-гард)

- [ ] **Step 1: Дописать тесты подписи (failing)**

Append to `tests/test_work_permit_closing_service.py`:
```python
from app.services.pep_signing import PepConflict
from app.domains.work_permits.signing import WorkPermitSignerError


@pytest.mark.asyncio
async def test_sign_closing_rejects_non_member(sessionmaker, data_factory):
    async with sessionmaker() as session:
        wp, foreman, supervisor, tid = await _issued_permit_with_brigade(session, data_factory)
        outsider = await data_factory.create_person(session)
        with pytest.raises(WorkPermitSignerError):
            await sign_closing(session, tenant_id=tid, work_permit_id=wp.id,
                               person_id=outsider.id, mode="attested", requested_by="u1")


@pytest.mark.asyncio
async def test_sign_closing_rejects_wrong_role(sessionmaker, data_factory):
    """Член бригады с ролью observer не подписывает закрытие."""
    async with sessionmaker() as session:
        wp, foreman, supervisor, tid = await _issued_permit_with_brigade(session, data_factory)
        observer = await data_factory.create_person(session)
        await svc.add_member(session, tenant_id=tid, work_permit_id=wp.id, person_id=observer.id, role="observer")
        with pytest.raises(WorkPermitSignerError):
            await sign_closing(session, tenant_id=tid, work_permit_id=wp.id,
                               person_id=observer.id, mode="attested", requested_by="u1")


@pytest.mark.asyncio
async def test_sign_closing_double_sign_blocked(sessionmaker, data_factory):
    async with sessionmaker() as session:
        wp, foreman, supervisor, tid = await _issued_permit_with_brigade(session, data_factory)
        await svc.record_completion(session, tenant_id=tid, work_permit_id=wp.id,
                                    completion_text="готово", actor_user_id="u1")
        await sign_closing(session, tenant_id=tid, work_permit_id=wp.id,
                           person_id=foreman.id, mode="attested", requested_by="u1")
        with pytest.raises(PepConflict):
            await sign_closing(session, tenant_id=tid, work_permit_id=wp.id,
                               person_id=foreman.id, mode="attested", requested_by="u1")
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run:
```
.venv\Scripts\python.exe -m pytest tests/test_work_permit_closing_service.py -k sign_closing -p no:cacheprovider 2>&1 | Tee-Object test_sign.txt; echo "EXIT=$LASTEXITCODE"
```
Expected: FAIL (`sign_closing` не определён).

- [ ] **Step 3: Реализовать `sign_closing`**

In `backend/app/domains/work_permits/signing.py`:
- В импортах модели добавить роли закрытия (после строки `from app.models.work_permit import WorkPermitMember`):
```python
from app.domains.work_permits.lifecycle import CLOSING_SIGNER_ROLES
```
- В конец файла добавить:
```python
async def sign_closing(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str,
    person_id: str, mode: str, requested_by: str,
) -> tuple[SignatureRequest, str | None]:
    """Подпись закрытия наряда: подписант — член бригады с ролью из CLOSING_SIGNER_ROLES.

    Вид «сдал/принял» НЕ хранится в запросе — резолвится из роли члена при чтении
    (см. service._signed_closing_kinds)."""
    role = await _member_role(
        session, tenant_id=tenant_id, work_permit_id=work_permit_id,
        person_id=person_id, allowed_roles=CLOSING_SIGNER_ROLES,
    )
    if role is None:
        raise WorkPermitSignerError("person is not a closing-signer member of this permit")
    return await _dispatch(
        session, tenant_id=tenant_id, object_type="work_permit_closing", object_id=work_permit_id,
        purpose="work_permit_closing", person_id=person_id, mode=mode, requested_by=requested_by,
    )
```

- [ ] **Step 4: Запустить — убедиться, что прошло**

Run:
```
.venv\Scripts\python.exe -m pytest tests/test_work_permit_closing_service.py -p no:cacheprovider 2>&1 | Tee-Object test_sign.txt; echo "EXIT=$LASTEXITCODE"
```
Expected: EXIT=0 (8 passed: 5 сервис + 3 подпись).

- [ ] **Step 5: Коммит**

```bash
git add backend/app/domains/work_permits/signing.py tests/test_work_permit_closing_service.py
git commit -m "feat(work-permits): sign_closing — подпись закрытия с валидацией членства (Ф3b)"
```

---

## Task 6: Схемы + API эндпоинты closing + 409-маппинг close

**Files:**
- Modify: `backend/app/schemas/work_permit.py` (после `WorkPermitSignatureRead`, ~строка 216)
- Modify: `backend/app/api/routes/work_permits.py` (новые эндпоинты + маппинг в `close_endpoint`)
- Test: `tests/api/test_work_permit_closing_api.py`

- [ ] **Step 1: Написать API-тесты (failing)**

Create `tests/api/test_work_permit_closing_api.py`:
```python
"""Ф3b API: акт закрытия + подписи + гейт close + tenant-isolation."""
from __future__ import annotations

import pytest

BASE = "/api/v1/work-permits"


async def _issued_permit(async_client, headers, persons):
    """Создаёт наряд, добавляет foreman+supervisor, переводит в issued.
    persons = (foreman_id, supervisor_id). Возвращает wp_id."""
    foreman_id, supervisor_id = persons
    wp_id = (await async_client.post(BASE, headers=headers, json={
        "work_type": "height", "zone_text": "z",
    })).json()["id"]
    for pid, role in ((foreman_id, "foreman"), (supervisor_id, "supervisor")):
        await async_client.post(f"{BASE}/{wp_id}/members", headers=headers,
                                json={"person_id": pid, "role": role})
    await async_client.post(f"{BASE}/{wp_id}/issue", headers=headers, json={})
    return wp_id


@pytest.mark.asyncio
async def test_closing_act_and_summary(async_client, admin_headers, two_brigade_persons):
    headers = admin_headers
    wp_id = await _issued_permit(async_client, headers, two_brigade_persons)
    # оформить акт
    r = await async_client.post(f"{BASE}/{wp_id}/closing", headers=headers,
                                json={"completion_text": "место сдано"})
    assert r.status_code == 200, r.text
    s = (await async_client.get(f"{BASE}/{wp_id}/closing", headers=headers)).json()
    assert s["completion_text"] == "место сдано"
    assert s["can_close"] is False
    assert "handover_signature" in s["missing"]


@pytest.mark.asyncio
async def test_close_gate_then_success(async_client, admin_headers, two_brigade_persons):
    headers = admin_headers
    foreman_id, supervisor_id = two_brigade_persons
    wp_id = await _issued_permit(async_client, headers, two_brigade_persons)
    await async_client.post(f"{BASE}/{wp_id}/closing", headers=headers,
                            json={"completion_text": "готово"})
    # close до подписей → 409
    blocked = await async_client.post(f"{BASE}/{wp_id}/close", headers=headers, json={})
    assert blocked.status_code == 409
    assert "missing" in str(blocked.json()).lower() or blocked.json().get("detail")
    # подписи сдал+принял (attested)
    for pid in (foreman_id, supervisor_id):
        rs = await async_client.post(f"{BASE}/{wp_id}/closing/signatures", headers=headers,
                                     json={"person_id": pid, "mode": "attested"})
        assert rs.status_code == 201, rs.text
    # теперь готов
    s = (await async_client.get(f"{BASE}/{wp_id}/closing", headers=headers)).json()
    assert s["can_close"] is True
    ok = await async_client.post(f"{BASE}/{wp_id}/close", headers=headers, json={})
    assert ok.status_code == 200
    assert ok.json()["status"] == "closed"


@pytest.mark.asyncio
async def test_closing_signature_non_member_4xx(async_client, admin_headers, two_brigade_persons, extra_person):
    headers = admin_headers
    wp_id = await _issued_permit(async_client, headers, two_brigade_persons)
    r = await async_client.post(f"{BASE}/{wp_id}/closing/signatures", headers=headers,
                                json={"person_id": extra_person, "mode": "attested"})
    assert r.status_code in (409, 422)
```

NB: фикстуры `admin_headers`, `two_brigade_persons` (кортеж id двух персон foreman/supervisor одного тенанта), `extra_person` (id персоны того же тенанта, не член бригады) — переиспользовать существующие или добавить в `tests/api/conftest.py` по образцу фикстур Ф2 (`tests/api/test_work_permits_api.py` — посмотреть, как там создаются persons и admin-заголовки; повторить тот же приём, не изобретая).

- [ ] **Step 2: Запустить — убедиться, что падает**

Run:
```
.venv\Scripts\python.exe -m pytest tests/api/test_work_permit_closing_api.py -p no:cacheprovider 2>&1 | Tee-Object test_api.txt; echo "EXIT=$LASTEXITCODE"
```
Expected: FAIL (эндпоинтов `/closing*` нет → 404).

- [ ] **Step 3: Добавить схемы**

In `backend/app/schemas/work_permit.py`, после `WorkPermitSignatureRead` (строка 214) добавить:
```python
class WorkPermitClosingRecordCreate(BaseSchema):
    completion_text: str


class WorkPermitClosingSummary(BaseSchema):
    completion_text: str | None
    completion_recorded_at: datetime | None
    signatures: list[WorkPermitSignatureRead]
    can_close: bool
    missing: list[str]
```
(`datetime` уже импортирован в файле — используется в существующих схемах.)

- [ ] **Step 4: Добавить эндпоинты closing**

In `backend/app/api/routes/work_permits.py`:
- В импортах подписи (строка 23) добавить `sign_closing`:
```python
from app.domains.work_permits.signing import sign_briefing, sign_closing, sign_permit
```
- В импортах сервиса добавить `record_completion` и `_signed_closing_kinds` (найти строку с `from app.domains.work_permits.service import ...` и дополнить список; если `close`/`cancel` импортируются там же — добавить рядом).
- В импортах lifecycle (`lc`) уже есть `closing_readiness` через модуль `lc`.
- В импортах схем добавить `WorkPermitClosingRecordCreate, WorkPermitClosingSummary`.
- После briefing/signatures-эндпоинтов (в конец файла, после `list_signatures_endpoint`, строка 564) добавить:
```python
# --- Closing endpoints (Ф3b) -----------------------------------------------

@router.post("/{wp_id}/closing", response_model=WorkPermitClosingSummary)
@audit_operation("update", "work_permit")
async def record_closing_endpoint(
    wp_id: str, payload: WorkPermitClosingRecordCreate, tenant: TenantDep,
    session: SessionDep, access: WriterAccess,
) -> WorkPermitClosingSummary:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    try:
        wp = await record_completion(
            session, tenant_id=tenant.id, work_permit_id=wp_id,
            completion_text=payload.completion_text,
            actor_user_id=access.user.id if access else None,
        )
    except lc.WorkPermitTransitionError as exc:
        raise _transition_conflict(exc) from exc
    if wp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "work permit not found")
    return await _closing_summary(session, tenant, wp)


@router.get("/{wp_id}/closing", response_model=WorkPermitClosingSummary)
async def get_closing_endpoint(
    wp_id: str, tenant: TenantDep, session: SessionDep, access: ReaderAccess,
) -> WorkPermitClosingSummary:
    TenantContextValidator.ensure_tenant_context(tenant)
    wp = await _get_or_404(session, tenant, wp_id)
    return await _closing_summary(session, tenant, wp)


@router.post(
    "/{wp_id}/closing/signatures",
    response_model=WorkPermitSignatureRead, status_code=status.HTTP_201_CREATED,
)
@audit_operation("update", "work_permit")
async def create_closing_signature_endpoint(
    wp_id: str, payload: WorkPermitSignatureCreate, tenant: TenantDep,
    session: SessionDep, access: WriterAccess,
) -> WorkPermitSignatureRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    await _ensure_person(session, tenant, payload.person_id)
    try:
        req, code = await sign_closing(
            session, tenant_id=str(tenant.id), work_permit_id=wp_id,
            person_id=payload.person_id, mode=payload.mode,
            requested_by=access.user.id if access else "system",
        )
    except (PepNotFound, PepConflict) as exc:
        raise _pep_to_http(exc) from exc
    return _signature_read(req, "closing", confirm_code=code)
```
- Добавить хелпер `_closing_summary` рядом с прочими хелперами (например, после `_signature_read`, строка ~96):
```python
async def _closing_summary(session: AsyncSession, tenant, wp: WorkPermit) -> WorkPermitClosingSummary:
    rows = (await session.execute(
        select(SignatureRequest).where(
            SignatureRequest.tenant_id == tenant.id,
            SignatureRequest.signature_type == "pep",
            SignatureRequest.object_type == "work_permit_closing",
            SignatureRequest.object_id == wp.id,
        ).order_by(SignatureRequest.created_at.asc())
    )).scalars().all()
    signed = await _signed_closing_kinds(session, tenant_id=tenant.id, work_permit_id=wp.id)
    readiness = lc.closing_readiness(completion_text=wp.completion_text, signed_kinds=signed)
    return WorkPermitClosingSummary(
        completion_text=wp.completion_text,
        completion_recorded_at=wp.completion_recorded_at,
        signatures=[_signature_read(r, "closing") for r in rows],
        can_close=readiness.can_close,
        missing=readiness.missing,
    )
```
(`select`, `SignatureRequest`, `WorkPermit` уже импортированы в роутере — используются в `list_signatures_endpoint`.)

- [ ] **Step 5: Замапить `WorkPermitClosingIncomplete` → 409 в `close_endpoint`**

In `backend/app/api/routes/work_permits.py`, `close_endpoint` (строки 341-351) — обернуть вызов в обработку гейта. Заменить тело на:
```python
async def close_endpoint(wp_id: str, payload: WorkPermitActionRequest, tenant: TenantDep, session: SessionDep, access: WriterAccess) -> WorkPermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    if payload.photo_file_id:
        await _ensure_file(session, tenant, payload.photo_file_id)
    try:
        return await _action(session, tenant, wp_id, lambda: close(
            session, tenant_id=tenant.id, work_permit_id=wp_id,
            actor_user_id=access.user.id if access else None,
            photo_file_id=payload.photo_file_id, note=payload.note,
        ))
    except lc.WorkPermitClosingIncomplete as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "WORK_PERMIT_CLOSING_INCOMPLETE", "missing": exc.missing},
        ) from exc
```
(Убедиться, что `_action` пробрасывает исключение наружу, а не глотает — если `_action` ловит общие Exception, врезать обработку гейта ВНУТРИ либо до `_action`. Прочитать `_action` (строка 274) и при необходимости поднять `WorkPermitClosingIncomplete` мимо его try.)

- [ ] **Step 6: Запустить API-тесты + предыдущие**

Run:
```
.venv\Scripts\python.exe -m pytest tests/api/test_work_permit_closing_api.py tests/test_work_permit_closing_service.py tests/test_work_permit_closing_domain.py tests/test_work_permit_closing_migration.py -p no:cacheprovider 2>&1 | Tee-Object test_api.txt; echo "EXIT=$LASTEXITCODE"
```
Expected: EXIT=0 (вся когорта Ф3b зелёная).

- [ ] **Step 7: Коммит**

```bash
git add backend/app/schemas/work_permit.py backend/app/api/routes/work_permits.py tests/api/test_work_permit_closing_api.py
git commit -m "feat(work-permits): API закрытия — акт/сводка/подписи + 409 гейт close (Ф3b)"
```

---

## Task 7: Обновить существующие тесты под новый контракт `close`

**Files:**
- Modify: `tests/test_work_permit_service.py` (`test_create_add_member_issue_suspend_resume_close`, строки ~15-50)
- Modify: `tests/api/test_work_permits_api.py` (close-успех, строка ~110)

- [ ] **Step 1: Прогнать существующие тесты — увидеть слом**

Run:
```
.venv\Scripts\python.exe -m pytest tests/test_work_permit_service.py tests/api/test_work_permits_api.py -p no:cacheprovider 2>&1 | Tee-Object test_existing.txt; echo "EXIT=$LASTEXITCODE"
```
Expected: FAIL ровно там, где `close` ожидался успешным без акта+подписей (service ~строка 45; api ~строка 110). Зафиксировать имена упавших тестов.

- [ ] **Step 2: Обновить сервис-тест**

In `tests/test_work_permit_service.py`, в `test_create_add_member_issue_suspend_resume_close` ПЕРЕД вызовом `svc.close(...)` (строка 45) добавить оформление акта и две attested-подписи. Член бригады в тесте — убедиться, что есть `foreman` и `supervisor`/`admitter` (если в тесте добавлялся член иной роли — добавить двоих нужных ролей). Вставка по образцу:
```python
        # Ф3b: закрытие гейтится актом + подписями «сдал/принял»
        from app.domains.work_permits.signing import sign_closing
        foreman = await data_factory.create_person(session)
        supervisor = await data_factory.create_person(session)
        await svc.add_member(session, tenant_id=person.tenant_id, work_permit_id=wp.id, person_id=foreman.id, role="foreman")
        await svc.add_member(session, tenant_id=person.tenant_id, work_permit_id=wp.id, person_id=supervisor.id, role="supervisor")
        await svc.record_completion(session, tenant_id=person.tenant_id, work_permit_id=wp.id, completion_text="готово", actor_user_id="u1")
        await sign_closing(session, tenant_id=person.tenant_id, work_permit_id=wp.id, person_id=foreman.id, mode="attested", requested_by="u1")
        await sign_closing(session, tenant_id=person.tenant_id, work_permit_id=wp.id, person_id=supervisor.id, mode="attested", requested_by="u1")
```
Также обновить ассерт списка событий (строка ~50): добавление членов добавит события `member_added`. Перечитать фактический ассерт и привести ожидаемый список событий к реальному (либо ослабить до проверки наличия `"closed"` последним: `assert events[-1].event_type == "closed"`).

- [ ] **Step 3: Обновить API-тест close-успеха**

In `tests/api/test_work_permits_api.py`, перед строкой 110 (`.../close` ожидает `"closed"`) — добавить шаги: убедиться, что у наряда есть члены `foreman`+`supervisor` (добавить через `POST /members`, если их нет), затем:
```python
    await async_client.post(f"{BASE}/{wp_id}/closing", headers=headers, json={"completion_text": "готово"})
    for pid, role in ((foreman_id, "foreman"), (supervisor_id, "supervisor")):
        # member может уже существовать — добавление идемпотентно не требуется, создаём при необходимости
        await async_client.post(f"{BASE}/{wp_id}/members", headers=headers, json={"person_id": pid, "role": role})
        await async_client.post(f"{BASE}/{wp_id}/closing/signatures", headers=headers, json={"person_id": pid, "mode": "attested"})
```
Подставить фактические переменные id персон, используемые в этом тесте (перечитать тело теста — там уже создаются persons/members; переиспользовать их id, не плодя новых, чтобы не нарушить дубль-гард членства). Строку 125 (`bad` close из неподходящего статуса) НЕ трогать — это другой кейс.

- [ ] **Step 4: Прогнать — зелено**

Run:
```
.venv\Scripts\python.exe -m pytest tests/test_work_permit_service.py tests/api/test_work_permits_api.py -p no:cacheprovider 2>&1 | Tee-Object test_existing.txt; echo "EXIT=$LASTEXITCODE"
```
Expected: EXIT=0.

- [ ] **Step 5: Коммит**

```bash
git add tests/test_work_permit_service.py tests/api/test_work_permits_api.py
git commit -m "test(work-permits): обновить close-тесты Ф1/Ф3a под гейт закрытия (Ф3b)"
```

---

## Task 8: Frontend — api/dto/vocab + ClosingPanel + монтаж + тест

**Files:**
- Modify: `frontend/src/api/workPermits.ts`
- Modify: `frontend/src/types/dto/workPermits.ts`
- Modify: `frontend/src/lib/workPermitVocab.ts`
- Create: `frontend/src/features/work-permits/ClosingPanel.tsx`
- Modify: `frontend/src/pages/work-permits/WorkPermitDetailPage.tsx`
- Test: `frontend/src/features/work-permits/ClosingPanel.test.tsx`

- [ ] **Step 1: Прочитать образец `SignaturesPanel` и api-модуль**

Read: `frontend/src/features/work-permits/SignaturesPanel.tsx`, `frontend/src/api/workPermits.ts` (методы `listSignatures`/`createPermitSignature`/`confirmSignatureCode`), `frontend/src/types/dto/workPermits.ts`, `frontend/src/lib/workPermitVocab.ts`. Скопировать их стиль (хедеры запроса, `Can`, `StatusBadge`, `Button`, `toast`, `useAsyncResource`) — НИЧЕГО не изобретать сверх паттерна.

- [ ] **Step 2: Добавить DTO**

In `frontend/src/types/dto/workPermits.ts` добавить (тип подписи `WorkPermitSignatureDto` уже есть — переиспользовать):
```typescript
export interface WorkPermitClosingSummaryDto {
  completion_text: string | null;
  completion_recorded_at: string | null;
  signatures: WorkPermitSignatureDto[];
  can_close: boolean;
  missing: string[];
}
```

- [ ] **Step 3: Добавить api-методы**

In `frontend/src/api/workPermits.ts`, внутрь объекта `workPermitsApi` (по образцу `createPermitSignature`/`listSignatures`) добавить:
```typescript
  async getClosing(id: string): Promise<WorkPermitClosingSummaryDto> {
    return http.get(`/work-permits/${id}/closing`);
  },
  async recordCompletion(id: string, completionText: string): Promise<WorkPermitClosingSummaryDto> {
    return http.post(`/work-permits/${id}/closing`, { completion_text: completionText });
  },
  async createClosingSignature(
    id: string, personId: string, mode: "attested" | "code",
  ): Promise<WorkPermitSignatureDto> {
    return http.post(`/work-permits/${id}/closing/signatures`, { person_id: personId, mode });
  },
```
(Подставить фактический http-клиент/синтаксис из соседних методов — `createPermitSignature` показывает точную форму; `confirmSignatureCode` уже есть и переиспользуется.) Импортировать `WorkPermitClosingSummaryDto` из dto.

- [ ] **Step 4: Добавить словарь**

In `frontend/src/lib/workPermitVocab.ts` добавить подписи видов и недостающих пунктов:
```typescript
export const CLOSING_KIND_LABELS: Record<string, string> = {
  handover: "Сдал (производитель работ)",
  acceptance: "Принял (ответственный/допускающий)",
};

export const CLOSING_MISSING_LABELS: Record<string, string> = {
  completion_act: "не оформлен акт окончания работ",
  handover_signature: "нет подписи «сдал»",
  acceptance_signature: "нет подписи «принял»",
};
```

- [ ] **Step 5: Написать тест панели (failing)**

Create `frontend/src/features/work-permits/ClosingPanel.test.tsx` (по образцу существующих `*.test.tsx` в features/work-permits — перечитать один такой тест для бойлерплейта render/mock). Минимальные кейсы:
```tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ClosingPanel } from "./ClosingPanel";

const baseSummary = {
  completion_text: null,
  completion_recorded_at: null,
  signatures: [],
  can_close: false,
  missing: ["completion_act", "handover_signature", "acceptance_signature"],
};

describe("ClosingPanel", () => {
  it("кнопка «Закрыть» disabled и показывает причину пока can_close=false", () => {
    render(<ClosingPanel summary={baseSummary} canManage onClose={vi.fn()} onRefresh={vi.fn()} nameOf={() => "ФИО"} />);
    const btn = screen.getByRole("button", { name: /закрыть/i });
    expect(btn).toBeDisabled();
    expect(screen.getByText(/не оформлен акт окончания работ/i)).toBeInTheDocument();
  });

  it("кнопка «Закрыть» активна при can_close=true", () => {
    render(<ClosingPanel summary={{ ...baseSummary, completion_text: "ok", can_close: true, missing: [] }} canManage onClose={vi.fn()} onRefresh={vi.fn()} nameOf={() => "ФИО"} />);
    expect(screen.getByRole("button", { name: /закрыть/i })).toBeEnabled();
  });
});
```
(Сигнатуру пропсов `ClosingPanel` согласовать с шагом 6; если в проекте принят паттерн «панель сама дёргает api и onRefresh», адаптировать тест под него по образцу `SignaturesPanel.test.tsx` — НО сохранить два проверяемых поведения: дизейбл по `can_close` и видимый список `missing`.)

- [ ] **Step 6: Реализовать `ClosingPanel.tsx`**

Create `frontend/src/features/work-permits/ClosingPanel.tsx` по образцу `SignaturesPanel.tsx`:
- Пропсы: `summary: WorkPermitClosingSummaryDto`, `canManage: boolean`, `onClose: () => void` (вызывает `/close`), `onRefresh: () => void`, `nameOf: (personId: string) => string`.
- Секция «Акт окончания»: textarea + кнопка «Оформить акт» (под `canManage`) → `workPermitsApi.recordCompletion(...)` → `onRefresh`.
- Секция «Подписи закрытия»: список `summary.signatures` со `StatusBadge`; действия «Зафиксировать подпись (attested)» / «Запросить код» → `createClosingSignature`; для кода — поле ввода + `confirmSignatureCode` (переиспользовать из api). ФИО — `nameOf(signer_person_id)`. Вид подписи — `CLOSING_KIND_LABELS` (резолв по роли недоступен на фронте напрямую → показывать по `purpose`/из summary как есть; видовую метку допускается опустить, если бэк не отдаёт kind — тогда показывать ФИО+статус).
- Кнопка «Закрыть наряд»: `disabled={!summary.can_close}`; при `!can_close` под кнопкой список причин из `summary.missing` через `CLOSING_MISSING_LABELS`. По клику — `onClose()`.
- Ошибки — `toast` (как в `SignaturesPanel`).

- [ ] **Step 7: Смонтировать панель в карточке**

In `frontend/src/pages/work-permits/WorkPermitDetailPage.tsx`:
- Импорт: `import { ClosingPanel } from "@/features/work-permits/ClosingPanel";`
- Загрузка сводки закрытия через `useAsyncResource(() => workPermitsApi.getClosing(id), [id, refreshKey])` (по образцу загрузки signatures).
- Смонтировать `<ClosingPanel ... />` рядом с `DailyAdmissionPanel` (строка ~366), показывать для статусов `issued`/`suspended`/`closed`. `onClose` — существующий обработчик закрытия (тот, что дёргает `/close`); при 409 показать `toast` с причинами (бэк отдаёт `detail.missing`).
- Существующую кнопку «Закрыть» (если она была в шапке экшенов) либо убрать, либо оставить — но логику закрытия завести через панель/общий обработчик, чтобы 409-гейт обрабатывался единообразно.

- [ ] **Step 8: Прогнать фронт-тест + сборку**

Run:
```
npm --prefix frontend run test -- src/features/work-permits/ClosingPanel.test.tsx
npm --prefix frontend run build
```
Expected: тест зелёный; build без ошибок типов/линта.

- [ ] **Step 9: Коммит**

```bash
git add frontend/src/api/workPermits.ts frontend/src/types/dto/workPermits.ts frontend/src/lib/workPermitVocab.ts frontend/src/features/work-permits/ClosingPanel.tsx frontend/src/features/work-permits/ClosingPanel.test.tsx frontend/src/pages/work-permits/WorkPermitDetailPage.tsx
git commit -m "feat(work-permits): экран закрытия наряда — ClosingPanel + гейт-кнопка (Ф3b)"
```

---

## Task 9: Регрессия контура + смежная + handoff

**Files:**
- Modify: `AI_IMPLEMENTATION_REPORT.md` (новый верхний handoff-раздел)

- [ ] **Step 1: Прогнать весь контурный когорт Ф3b + Ф2 (регрессия подписи)**

Run:
```
.venv\Scripts\python.exe -m pytest tests/test_work_permit_closing_migration.py tests/test_work_permit_closing_domain.py tests/test_work_permit_closing_service.py tests/api/test_work_permit_closing_api.py tests/test_work_permit_service.py tests/api/test_work_permits_api.py -p no:cacheprovider 2>&1 | Tee-Object test_contour.txt; echo "EXIT=$LASTEXITCODE"
```
Expected: EXIT=0.

- [ ] **Step 2: Прогнать смежную регрессию (ПЭП + миграции + наряды Ф2/Ф3a)**

Run:
```
.venv\Scripts\python.exe -m pytest -k "work_permit or pep or signing or migration or downgrade or mapper" -p no:cacheprovider 2>&1 | Tee-Object test_regression.txt; echo "EXIT=$LASTEXITCODE"
```
Expected: EXIT=0 (либо предсуществующие падения, воспроизводимые на main — зафиксировать как pre-existing с доказательством, [[receiving-code-review]]).

- [ ] **Step 3: Фронт — общий прогон тестов work-permits + build**

Run:
```
npm --prefix frontend run test -- src/features/work-permits
npm --prefix frontend run build
```
Expected: зелено; build чист.

- [ ] **Step 4: Дописать handoff в отчёт**

In `AI_IMPLEMENTATION_REPORT.md` добавить новый верхний раздел `## Last Agent Handoff (2026-06-20, КОНТУР «НАРЯДЫ-ДОПУСКИ» 782н Ф3b «закрытие с подписями» ПОСТРОЕН ...)`: что построено (поля акта wp05, sign_closing/object_type=work_permit_closing, чистый closing_readiness, гейт close, API closing, ClosingPanel), анти-грабли (VARCHAR/литералы имён таблиц, гейт только на close, cancel не тронут, слом контракта close → обновлены 2 теста, demo-seed нарядов отсутствует), результаты тестов (EXIT-коды), отложенное (Ф4 печатный бланк; тиражирование на др. виды работ), Next (ветка готова, merge — решение пользователя; канон Py3.12 CI = финальный гейт).

- [ ] **Step 5: Коммит**

```bash
git add AI_IMPLEMENTATION_REPORT.md
git commit -m "docs: handoff наряд-допуск 782н Ф3b «закрытие с подписями»"
```

---

## Self-Review (выполнено при написании плана)

**1. Покрытие спека:**
- §4 модель (поля акта) → Task 1. ✅
- §5 ПЭП-интеграция (PEP_PURPOSES + _build_content) → Task 2. ✅
- §6 сервис подписи (sign_closing, классы ролей, дубль-гард) → Task 5. ✅
- §7 гейт + record_completion → Task 3 (предикат) + Task 4 (сервис). ✅
- §8 API (closing record/summary/signatures, close 409) → Task 6. ✅
- §9 фронтенд (ClosingPanel, api, dto, vocab, монтаж) → Task 8. ✅
- §10 поток → покрыт API-тестом гейт→успех (Task 6) и фронт-логикой (Task 8). ✅
- §11 ошибки (не член/повтор/не-issued/гейт/код) → Task 5 (не член/роль/дубль), Task 4 (не-issued, гейт), Task 6 (409). ✅
- §12 тесты → каждая задача TDD. ✅
- §8-спека «слом demo-seed» → скорректировано: demo-seed нарядов нет, слом = 2 теста (Task 7). ✅
- §2 «cancel без гейта» → Task 4 тест `test_cancel_not_gated`. ✅

**2. Плейсхолдеры:** код приведён в каждом шаге. Места, требующие сверки с фактическим кодом (фикстуры API-тестов, http-клиент фронта, форма `_action`), помечены явной инструкцией «перечитать образец X и повторить», а не «TODO» — это чтение существующего паттерна, не пропуск.

**3. Консистентность типов/имён:** `closing_readiness(*, completion_text, signed_kinds)` → `ClosingReadiness(can_close, missing)`; `role_to_closing_kind` → {"handover","acceptance"}; `WorkPermitClosingIncomplete(missing)`; `sign_closing(..., work_permit_id, person_id, mode, requested_by)`; `object_type="work_permit_closing"`; `status=="signed"`; схемы `WorkPermitClosingRecordCreate`/`WorkPermitClosingSummary`; api `getClosing`/`recordCompletion`/`createClosingSignature`. Имена согласованы между задачами.

**Открытый риск для исполнителя:** точная форма `_action` (роутер, строка 274) — если он перехватывает широкий `Exception`, гейт-исключение надо поднять ДО/МИМО него (Task 6, Step 5 отмечает это). Сверить при реализации.
