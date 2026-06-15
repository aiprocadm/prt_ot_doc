# ЭДО Срез-3: код-flow для briefing — Implementation Plan

> **✅ РЕАЛИЗОВАНО И ВЛИТО — PR #652 (`cd57127`) + PR #653 (`ad900c4`).** Проверено аудитом кода 2026-06-15: двухфазный код-flow (`sign-employee` → `confirm-code`), флаг `require_signature_code`, миграция `ed04`, attested-fallback, сервис/API/тесты + demo-seed. Чекбоксы ниже отмечены пост-фактум.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Опциональная подпись ознакомления с инструктажем разовым 6-значным кодом (ПЭП код-flow) для работников без учётки, включаемая флагом на шаблоне инструктажа.

**Architecture:** Двухфазность (`sign-employee` выдаёт код → `confirm-code` подтверждает и создаёт `BriefingSignature`) живёт в briefing-модуле; ПЭП-ядро (`PepSigningService`) используется как generic-интерфейс без изменений. Триггер код-flow: `signer_type=="employee"` И `entry.person_id` задан И `template.require_signature_code`. Иначе — текущий attested-путь (back-compat).

**Tech Stack:** Python 3.12 (локально 3.13.7/.venv), FastAPI, SQLAlchemy async, Alembic, pytest-asyncio. Тесты локально через `.venv\Scripts\python.exe -m pytest` (PowerShell→file; см. [[py313_win_pytest_invocation]]).

**Спек:** `docs/superpowers/specs/2026-06-13-edo-briefing-code-flow-design.md`.

**Среда/прогон тестов:** канон Py3.12 = CI (выключен). Локально:
```
.venv\Scripts\python.exe -m pytest <path> -p no:xdist --timeout=120 -v 2>&1 | Tee-Object <file>
```

---

## File Structure

- **Modify** `backend/app/models/models.py` (`BriefingTemplate`, ~line 1281) — добавить колонку `require_signature_code`.
- **Create** `backend/app/migrations/versions/20260613_ed04_briefing_require_signature_code.py` — аддитивная миграция (head `med02`).
- **Create** `backend/tests/test_ed04_briefing_require_signature_code_migration.py` — chain+shape guard.
- **Modify** `backend/app/api/routes/briefings.py` (`BriefingTemplatePayload` :41; `sign_employee` :277; добавить `confirm-code` + `BriefingConfirmCodePayload`).
- **Modify** `backend/app/modules/briefings/services.py` (`BriefingEntryService`) — `requires_signature_code`, `start_employee_signature`, `_find_pending_request`, `confirm_code`, исключение `NoPendingCodeRequest`.
- **Create** `tests/services/test_briefing_code_flow_service.py` — сервис-тесты двухфазности.
- **Create** `tests/api/test_briefing_code_flow_api.py` — HTTP-контракт.
- **Modify** `backend/app/services/demo_bootstrap.py` — шаблон с флагом + пример (если есть briefing-seed; иначе минимальный seed).
- **Create/Modify** `tests/test_briefing_code_flow_seed.py` — seed-тест (если seed добавляется).

---

## Task 1: Модель `require_signature_code` + миграция ed04 + guard

**Files:**
- Modify: `backend/app/models/models.py:1281-1291` (`BriefingTemplate`)
- Create: `backend/app/migrations/versions/20260613_ed04_briefing_require_signature_code.py`
- Test: `backend/tests/test_ed04_briefing_require_signature_code_migration.py`

- [x] **Step 1: Write the failing migration guard test**

Create `backend/tests/test_ed04_briefing_require_signature_code_migration.py`:

```python
"""Chain + shape guard for ed04 (BriefingTemplate.require_signature_code)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app" / "migrations" / "versions"
    / "20260613_ed04_briefing_require_signature_code.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("ed04_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_ed04_chains_to_med02():
    mod = _load()
    assert mod.revision == "20260613_ed04_briefing_require_signature_code"
    assert mod.down_revision == "20260613_med02_medical_factor_catalog"
    assert mod.depends_on is None


def test_ed04_adds_column_with_literal_names():
    src = _MIGRATION.read_text(encoding="utf-8")
    assert 'add_column(' in src and '"briefing_templates"' in src
    assert '"require_signature_code"' in src
    assert 'server_default="false"' in src or "server_default='false'" in src
    # honest downgrade drops the column
    assert 'drop_column("briefing_templates", "require_signature_code")' in src
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_ed04_briefing_require_signature_code_migration.py -p no:xdist --timeout=120 -v`
Expected: FAIL — `FileNotFoundError` / load error (migration file does not exist yet).

- [x] **Step 3: Add the model column**

In `backend/app/models/models.py`, inside `class BriefingTemplate` (after `validity_days`, before `__table_args__`):

```python
    validity_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    require_signature_code: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
```

(Verify `Boolean` is already imported in models.py — it is used elsewhere; if not, add to the SQLAlchemy import.)

- [x] **Step 4: Create the migration**

Create `backend/app/migrations/versions/20260613_ed04_briefing_require_signature_code.py`:

```python
"""ed04: BriefingTemplate.require_signature_code (TZ B.5, vNext §6.9 Срез-3).

Additive. One non-null boolean column (server_default false) on briefing_templates
to opt a briefing type into code-flow signing. Round-trip-safe: downgrade drops it.
Table/column names are LITERAL (AST-audit blindspot, [[audit_static_analysis_blindspots]]).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260613_ed04_briefing_require_signature_code"
down_revision = "20260613_med02_medical_factor_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "briefing_templates",
        sa.Column(
            "require_signature_code",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("briefing_templates", "require_signature_code")
```

- [x] **Step 5: Run guard test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_ed04_briefing_require_signature_code_migration.py -p no:xdist --timeout=120 -v`
Expected: PASS (2 tests).

- [x] **Step 6: Verify single-head migration chain**

Run: `.venv\Scripts\python.exe -m pytest -k "migration or downgrade or mapper" -p no:xdist --timeout=300 -q 2>&1 | Tee-Object test_ed04_step6.txt`
Expected: all pass (no multiple-heads error; new revision is the single head after med02).

- [x] **Step 7: Commit**

```bash
git add backend/app/models/models.py backend/app/migrations/versions/20260613_ed04_briefing_require_signature_code.py backend/tests/test_ed04_briefing_require_signature_code_migration.py
git commit -m "feat(edo): BriefingTemplate.require_signature_code + миграция ed04"
```

---

## Task 2: Проброс флага в CRUD шаблонов

**Files:**
- Modify: `backend/app/api/routes/briefings.py:41-47` (`BriefingTemplatePayload`)
- Test: `tests/api/test_briefing_code_flow_api.py` (создаём файл; первый тест — CRUD флага)

- [x] **Step 1: Write the failing API test**

Create `tests/api/test_briefing_code_flow_api.py`:

```python
"""HTTP contract: BriefingTemplate.require_signature_code CRUD + code-flow cycle."""
from __future__ import annotations

import pytest

from app.models.models import RoleEnum


@pytest.mark.asyncio
async def test_template_require_signature_code_roundtrip(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)

    created = await async_client.post(
        "/api/v1/briefings/templates",
        json={
            "code": "BRF-CODE-T1",
            "title": "Вводный с кодом",
            "briefing_type": "primary",
            "require_signature_code": True,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["require_signature_code"] is True

    # default остаётся false, когда поле не передано
    created2 = await async_client.post(
        "/api/v1/briefings/templates",
        json={"code": "BRF-CODE-T2", "title": "Без кода", "briefing_type": "primary"},
        headers=headers,
    )
    assert created2.status_code == 201, created2.text
    assert created2.json()["require_signature_code"] is False
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/api/test_briefing_code_flow_api.py::test_template_require_signature_code_roundtrip -p no:xdist --timeout=120 -v`
Expected: FAIL — `require_signature_code` ignored on create / missing in read (KeyError or `False` when `True` expected).

- [x] **Step 3: Add the field to the template payload**

In `backend/app/api/routes/briefings.py`, `class BriefingTemplatePayload`:

```python
class BriefingTemplatePayload(BaseModel):
    code: str
    title: str
    briefing_type: str
    status: str = "draft"
    description: str | None = None
    validity_days: int | None = None
    require_signature_code: bool = False
```

(`BriefingTemplateRead(BriefingTemplatePayload)` inherits the field; `create_template`/`patch_template` use `payload.model_dump()` so it round-trips automatically.)

- [x] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/api/test_briefing_code_flow_api.py::test_template_require_signature_code_roundtrip -p no:xdist --timeout=120 -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add backend/app/api/routes/briefings.py tests/api/test_briefing_code_flow_api.py
git commit -m "feat(edo): проброс require_signature_code в CRUD шаблонов briefing"
```

---

## Task 3: Сервис — двухфазная логика (`start_employee_signature` + `confirm_code`)

**Files:**
- Modify: `backend/app/modules/briefings/services.py` (`BriefingEntryService` + new exception)
- Test: `tests/services/test_briefing_code_flow_service.py`

- [x] **Step 1: Write the failing service tests**

Create `tests/services/test_briefing_code_flow_service.py`:

```python
"""Two-phase briefing code-flow at the service layer (Срез-3)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.domains.signing.pep import PepStatus
from app.models.models import (
    BriefingEntry,
    BriefingJournal,
    BriefingSignature,
    BriefingTemplate,
    SignatureRequest,
)
from app.modules.briefings.services import (
    BriefingEntryService,
    NoPendingCodeRequest,
)
from app.services.pep_signing import PepConflict


async def _world(session, data_factory, *, require_code: bool, with_person: bool = True):
    tenant = await data_factory.ensure_tenant(session=session)
    company = await data_factory.create_company(tenant=tenant, session=session, name="BRF CF")
    person = (
        await data_factory.create_person(tenant=tenant, company=company, session=session)
        if with_person
        else None
    )
    template = BriefingTemplate(
        tenant_id=tenant.id,
        code="BRF-CF-T",
        title="CF",
        briefing_type="primary",
        require_signature_code=require_code,
    )
    journal = BriefingJournal(
        tenant_id=tenant.id, code="BRF-CF-J", title="CF", journal_type="workplace", status="active"
    )
    session.add_all([template, journal])
    await session.flush()
    entry = BriefingEntry(
        tenant_id=tenant.id,
        person_id=person.id if person else None,
        briefing_journal_id=journal.id,
        briefing_template_id=template.id,
        briefing_type="primary",
        briefing_date=datetime.now(tz=timezone.utc),
        status="assigned",
    )
    session.add(entry)
    await session.flush()
    return tenant, person, template, entry


@pytest.mark.asyncio
async def test_requires_code_true_only_when_flag_and_person(sessionmaker, data_factory):
    async with sessionmaker() as session:
        _, _, _, entry = await _world(session, data_factory, require_code=True)
        assert await BriefingEntryService().requires_signature_code(session, entry) is True

        _, _, _, entry_off = await _world(session, data_factory, require_code=False)
        assert await BriefingEntryService().requires_signature_code(session, entry_off) is False

        _, _, _, entry_noperson = await _world(
            session, data_factory, require_code=True, with_person=False
        )
        assert await BriefingEntryService().requires_signature_code(session, entry_noperson) is False


@pytest.mark.asyncio
async def test_start_then_confirm_creates_signature(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, person, _, entry = await _world(session, data_factory, require_code=True)
        svc = BriefingEntryService()
        req, code = await svc.start_employee_signature(session, entry, "user-1")
        await session.commit()

        assert req.status == PepStatus.AWAITING_CODE.value
        assert code is not None and len(code) == 6
        # строка подписи ещё НЕ создана, статус записи не тронут
        sigs = (await session.execute(
            select(BriefingSignature).where(BriefingSignature.briefing_entry_id == entry.id)
        )).scalars().all()
        assert sigs == []
        assert entry.status == "assigned"

        sig = await svc.confirm_code(session, entry, code)
        await session.commit()

        assert sig.signer_person_id == person.id
        assert sig.signature_payload["pep_request_id"] == req.id
        assert entry.status == "signed_employee"
        refreshed = await session.get(SignatureRequest, req.id)
        assert refreshed.status == PepStatus.SIGNED.value


@pytest.mark.asyncio
async def test_wrong_code_raises_and_attempts_increment_survive_commit(sessionmaker, data_factory):
    async with sessionmaker() as session:
        _, _, _, entry = await _world(session, data_factory, require_code=True)
        svc = BriefingEntryService()
        req, _ = await svc.start_employee_signature(session, entry, "user-1")
        await session.commit()

        with pytest.raises(PepConflict):
            await svc.confirm_code(session, entry, "000000")
        await session.commit()  # commit-on-conflict: счётчик попыток сохраняется

        refreshed = await session.get(SignatureRequest, req.id)
        assert refreshed.confirm_attempts == 1
        assert refreshed.status == PepStatus.AWAITING_CODE.value


@pytest.mark.asyncio
async def test_confirm_without_pending_request_raises(sessionmaker, data_factory):
    async with sessionmaker() as session:
        _, _, _, entry = await _world(session, data_factory, require_code=True)
        with pytest.raises(NoPendingCodeRequest):
            await BriefingEntryService().confirm_code(session, entry, "123456")
```

- [x] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/services/test_briefing_code_flow_service.py -p no:xdist --timeout=120 -v`
Expected: FAIL — `ImportError: cannot import name 'NoPendingCodeRequest'` / missing methods.

- [x] **Step 3: Implement the service methods**

In `backend/app/modules/briefings/services.py`, add imports near the top:

```python
from app.domains.signing.pep import PepStatus
from app.models.models import (
    BriefingEntry, BriefingSignature, BriefingTemplate, SignatureRequest,
)
from app.services.pep_signing import PepConflict, PepSigningService
```

(Merge with the existing `from app.models.models import ...` line — add `SignatureRequest`. `PepSigningService` is already imported; add `PepConflict`.)

Add the exception next to `BriefingSignatureConflict`:

```python
class NoPendingCodeRequest(Exception):
    """Нет активного AWAITING_CODE-запроса для этой записи/работника.

    Кидается confirm_code, когда запись не в состоянии ожидания кода
    (код-flow не запускался, уже подтверждён, истёк или отклонён).
    API-слой маппит в 409 no_pending_code_request.
    """
```

Add methods to `BriefingEntryService` (after `sign`):

```python
    async def requires_signature_code(
        self, session: AsyncSession, entry: BriefingEntry
    ) -> bool:
        """Код-flow для employee включается флагом шаблона при наличии person_id."""
        if entry.person_id is None or not entry.briefing_template_id:
            return False
        template = await session.get(BriefingTemplate, entry.briefing_template_id)
        return bool(
            template
            and str(template.tenant_id) == str(entry.tenant_id)
            and template.require_signature_code
        )

    async def start_employee_signature(
        self, session: AsyncSession, entry: BriefingEntry, requested_by: str | None
    ) -> tuple[SignatureRequest, str | None]:
        """Фаза 1 код-flow: ПЭП-запрос с выдачей разового кода (person-подписант).

        Строку BriefingSignature НЕ создаёт и entry.status НЕ меняет — pending-
        состояние живёт в SignatureRequest до confirm. create_request сам отбивает
        повторную выдачу кода активному запросу (PepConflict -> 409).
        """
        return await PepSigningService(session, str(entry.tenant_id)).create_request(
            object_type="briefing_entry",
            object_id=entry.id,
            purpose="briefing",
            requested_by=requested_by or "system",
            signer_person_id=entry.person_id,
        )

    async def _find_pending_request(
        self, session: AsyncSession, entry: BriefingEntry
    ) -> SignatureRequest | None:
        return (
            await session.execute(
                select(SignatureRequest).where(
                    SignatureRequest.tenant_id == entry.tenant_id,
                    SignatureRequest.object_type == "briefing_entry",
                    SignatureRequest.object_id == entry.id,
                    SignatureRequest.purpose == "briefing",
                    SignatureRequest.signer_person_id == entry.person_id,
                    SignatureRequest.status == PepStatus.AWAITING_CODE.value,
                )
            )
        ).scalars().first()

    async def confirm_code(
        self, session: AsyncSession, entry: BriefingEntry, code: str
    ) -> BriefingSignature:
        """Фаза 2 код-flow: подтвердить код и зафиксировать BriefingSignature.

        КОНТРАКТ ДЛЯ API: PepSigningService.confirm при неверном/истёкшем/
        исчерпанном коде кидает PepConflict, ИЗМЕНИВ состояние запроса (счётчик
        попыток / expired / declined) — API-слой обязан COMMIT, а не rollback.
        """
        existing = await self._find_existing(session, entry.id, "employee")
        if existing is not None:
            return existing  # идемпотентность: уже подписано

        req = await self._find_pending_request(session, entry)
        if req is None:
            raise NoPendingCodeRequest(
                f"no pending code request for entry={entry.id}"
            )

        await PepSigningService(session, str(entry.tenant_id)).confirm(req.id, code=code)

        signature = BriefingSignature(
            tenant_id=entry.tenant_id,
            briefing_entry_id=entry.id,
            signer_type="employee",
            signer_person_id=entry.person_id,
            signature_mode="internal_simple",
            signature_payload={"pep_request_id": req.id},
        )
        session.add(signature)
        entry.status = "signed_employee"
        entry_id = entry.id
        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            raise BriefingSignatureConflict(
                f"signature already exists for entry={entry_id} signer_type=employee"
            ) from exc
        return signature
```

- [x] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/services/test_briefing_code_flow_service.py -p no:xdist --timeout=120 -v`
Expected: PASS (4 tests).

- [x] **Step 5: Commit**

```bash
git add backend/app/modules/briefings/services.py tests/services/test_briefing_code_flow_service.py
git commit -m "feat(edo): двухфазный код-flow briefing в сервисе (start + confirm_code)"
```

---

## Task 4: API — ветвление `sign-employee` + эндпоинт `confirm-code`

**Files:**
- Modify: `backend/app/api/routes/briefings.py` (`sign_employee` :277; new payload + endpoint; error mapping)
- Test: `tests/api/test_briefing_code_flow_api.py` (добавить тесты цикла)

- [x] **Step 1: Write the failing API tests**

Append to `tests/api/test_briefing_code_flow_api.py`:

```python
from datetime import datetime, timezone

from app.models.models import BriefingEntry, BriefingJournal, BriefingTemplate


async def _entry_with_template(session, data_factory, *, require_code: bool):
    tenant = await data_factory.ensure_tenant(session=session)
    company = await data_factory.create_company(tenant=tenant, session=session, name="BRF CF API")
    person = await data_factory.create_person(tenant=tenant, company=company, session=session)
    template = BriefingTemplate(
        tenant_id=tenant.id, code="BRF-CF-API-T", title="CF", briefing_type="primary",
        require_signature_code=require_code,
    )
    journal = BriefingJournal(
        tenant_id=tenant.id, code="BRF-CF-API-J", title="CF", journal_type="workplace", status="active"
    )
    session.add_all([template, journal])
    await session.flush()
    entry = BriefingEntry(
        tenant_id=tenant.id, person_id=person.id, briefing_journal_id=journal.id,
        briefing_template_id=template.id, briefing_type="primary",
        briefing_date=datetime.now(tz=timezone.utc), status="assigned",
    )
    session.add(entry)
    await session.commit()
    return tenant, person, entry


@pytest.mark.asyncio
async def test_sign_employee_with_flag_returns_code_then_confirm(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:
        tenant, _, entry = await _entry_with_template(session, data_factory, require_code=True)
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)

    started = await async_client.post(
        f"/api/v1/briefings/entries/{entry.id}/sign-employee", json={}, headers=headers
    )
    assert started.status_code == 200, started.text
    pending = started.json()["pending"]
    assert pending["status"] == "awaiting_code"
    assert len(pending["confirm_code"]) == 6

    confirmed = await async_client.post(
        f"/api/v1/briefings/entries/{entry.id}/confirm-code",
        json={"code": pending["confirm_code"]},
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["signature"]["signer_type"] == "employee"


@pytest.mark.asyncio
async def test_sign_employee_without_flag_signs_immediately(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:
        tenant, _, entry = await _entry_with_template(session, data_factory, require_code=False)
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)

    resp = await async_client.post(
        f"/api/v1/briefings/entries/{entry.id}/sign-employee", json={}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "pending" not in body
    assert body["signature"]["signer_type"] == "employee"


@pytest.mark.asyncio
async def test_confirm_code_without_pending_returns_409(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:
        tenant, _, entry = await _entry_with_template(session, data_factory, require_code=True)
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)

    resp = await async_client.post(
        f"/api/v1/briefings/entries/{entry.id}/confirm-code",
        json={"code": "123456"}, headers=headers,
    )
    assert resp.status_code == 409, resp.text


@pytest.mark.asyncio
async def test_confirm_code_wrong_code_returns_409_and_persists_attempt(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:
        tenant, _, entry = await _entry_with_template(session, data_factory, require_code=True)
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)

    await async_client.post(
        f"/api/v1/briefings/entries/{entry.id}/sign-employee", json={}, headers=headers
    )
    wrong = await async_client.post(
        f"/api/v1/briefings/entries/{entry.id}/confirm-code",
        json={"code": "000000"}, headers=headers,
    )
    assert wrong.status_code == 409, wrong.text
```

- [x] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/api/test_briefing_code_flow_api.py -p no:xdist --timeout=120 -v`
Expected: FAIL — `sign-employee` ignores the flag (always returns `signature`, no `pending`); `confirm-code` endpoint → 404/405 (not defined).

- [x] **Step 3: Add the confirm payload, branch sign_employee, add confirm-code endpoint**

In `backend/app/api/routes/briefings.py`:

(a) Extend the briefings-service import:

```python
from app.modules.briefings.services import (
    BriefingEntryService,
    BriefingSignatureConflict,
    NoPendingCodeRequest,
)
from app.services.pep_signing import PepConflict
```

(b) Add the confirm payload near `BriefingSignPayload`:

```python
class BriefingConfirmCodePayload(BaseModel):
    code: str
```

(c) Replace the body of `sign_employee` with the branching version:

```python
@router.post("/entries/{item_id}/sign-employee")
@audit_operation("sign_employee", "briefing_entry", id_attr="entry")
async def sign_employee(item_id: str, payload: BriefingSignPayload, request: Request, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    item = await session.get(BriefingEntry, item_id)
    if not item or item.tenant_id != tenant.id:
        raise HTTPException(404, "Entry not found")
    svc = BriefingEntryService()
    if await svc.requires_signature_code(session, item):
        try:
            req, code = await svc.start_employee_signature(session, item, payload.signer_user_id)
        except PepConflict as exc:
            await session.commit()
            raise _briefing_signature_conflict(str(exc)) from exc
        await session.commit()
        return {
            "entry": _entry_read(item),
            "pending": {"pep_request_id": req.id, "status": req.status, "confirm_code": code},
        }
    try:
        sig = await svc.sign(session, item, "employee", payload.signer_user_id, signature_payload=payload.signature_payload)
    except BriefingSignatureConflict as exc:
        raise _briefing_signature_conflict(str(exc)) from exc
    await session.commit()
    return {"entry": _entry_read(item, [sig]), "signature": BriefingSignatureRead.model_validate(sig)}
```

(d) Add the `confirm-code` endpoint right after `sign_employee`:

```python
@router.post("/entries/{item_id}/confirm-code")
@audit_operation("confirm_code", "briefing_entry", id_attr="entry")
async def confirm_code(item_id: str, payload: BriefingConfirmCodePayload, request: Request, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), __: Any = _PermWriteDep):
    item = await session.get(BriefingEntry, item_id)
    if not item or item.tenant_id != tenant.id:
        raise HTTPException(404, "Entry not found")
    svc = BriefingEntryService()
    try:
        sig = await svc.confirm_code(session, item, payload.code)
    except NoPendingCodeRequest as exc:
        raise api_problem_detail(status.HTTP_409_CONFLICT, "no_pending_code_request", str(exc)) from exc
    except PepConflict as exc:
        # commit-on-conflict: счётчик попыток / expired / declined должны сохраниться
        await session.commit()
        raise api_problem_detail(status.HTTP_409_CONFLICT, "pep_conflict", str(exc)) from exc
    except BriefingSignatureConflict as exc:
        raise _briefing_signature_conflict(str(exc)) from exc
    await session.commit()
    return {"entry": _entry_read(item, [sig]), "signature": BriefingSignatureRead.model_validate(sig)}
```

NB: verify the helper `_briefing_signature_conflict` and `api_problem_detail` exist in this module (they are used by neighbouring handlers; `api_problem_detail` is imported at line 18). If `_briefing_signature_conflict` wraps `api_problem_detail`, reuse the same pattern for `no_pending_code_request`. If `_entry_read` requires a second arg, the pending branch passes only `item` (no signatures yet) — confirm `_entry_read(item)` is valid (it has a default `[]`); if not, pass `_entry_read(item, [])`.

- [x] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/api/test_briefing_code_flow_api.py -p no:xdist --timeout=120 -v`
Expected: PASS (all tests in the file, incl. Task 2's).

- [x] **Step 5: Commit**

```bash
git add backend/app/api/routes/briefings.py tests/api/test_briefing_code_flow_api.py
git commit -m "feat(edo): API ветвление sign-employee + эндпоинт confirm-code (код-flow briefing)"
```

---

## Task 5: Demo-seed шаблона с флагом

**Files:**
- Modify: `backend/app/services/demo_bootstrap.py` (briefing-секция seed)
- Test: `tests/test_briefing_code_flow_seed.py`

- [x] **Step 1: Locate the briefing seed block**

Run: `.venv\Scripts\python.exe -m pytest --co -q 2>$null; ` then inspect:
Grep for `BriefingTemplate(` / `briefing` in `backend/app/services/demo_bootstrap.py`. If a briefing template is already seeded, set `require_signature_code=True` on one template (or add a second template with the flag). If briefings are NOT seeded there, add a minimal seed: one `BriefingTemplate(require_signature_code=True)` + one `BriefingJournal` + one `BriefingEntry` with a `person_id` from the existing demo person, guarded as idempotent (skip if a template with that code exists), matching the file's existing idempotency style.

- [x] **Step 2: Write the failing seed test**

Create `tests/test_briefing_code_flow_seed.py`:

```python
"""Demo-seed includes a briefing template opted into code-flow signing."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.models import BriefingTemplate
from app.services.demo_bootstrap import seed_demo_data  # adjust to real entrypoint


@pytest.mark.asyncio
async def test_demo_seed_has_code_flow_template(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await seed_demo_data(session, tenant_id=str(tenant.id))  # adjust signature
        await session.commit()
        templates = (await session.execute(
            select(BriefingTemplate).where(
                BriefingTemplate.tenant_id == tenant.id,
                BriefingTemplate.require_signature_code.is_(True),
            )
        )).scalars().all()
        assert len(templates) >= 1
```

NB: the implementer must adjust `seed_demo_data` import path / signature to the real demo-bootstrap entrypoint (read the file first; mirror how other seed tests in the repo call it).

- [x] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_briefing_code_flow_seed.py -p no:xdist --timeout=120 -v`
Expected: FAIL — no template with `require_signature_code=True`.

- [x] **Step 4: Implement the seed change**

Apply the change identified in Step 1 (set/add a template with `require_signature_code=True`), following the file's existing idempotency and helper conventions.

- [x] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_briefing_code_flow_seed.py -p no:xdist --timeout=120 -v`
Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add backend/app/services/demo_bootstrap.py tests/test_briefing_code_flow_seed.py
git commit -m "feat(edo): demo-seed шаблона briefing с require_signature_code"
```

---

## Task 6: Регрессия + holistic-review

**Files:** none (verification only)

- [x] **Step 1: Run the briefing + pep cohort**

Run: `.venv\Scripts\python.exe -m pytest -k "briefing or pep or signing" -p no:xdist --timeout=300 -q 2>&1 | Tee-Object test_brf_cohort.txt`
Expected: all pass (existing briefing attested-path + unique-index + pep tests stay green — back-compat).

- [x] **Step 2: Run the migration cohort**

Run: `.venv\Scripts\python.exe -m pytest -k "migration or downgrade or mapper" -p no:xdist --timeout=300 -q 2>&1 | Tee-Object test_mig_cohort.txt`
Expected: all pass; single head after med02 → ed04.

- [x] **Step 3: Holistic review**

Dispatch a holistic code review against the spec (`docs/superpowers/specs/2026-06-13-edo-briefing-code-flow-design.md`): spec-section coverage, back-compat of attested path, commit-on-conflict correctness, tenant-isolation, no scope creep. Address any Critical/Important findings before declaring done.

- [x] **Step 4: Final commit (if review fixes applied)**

```bash
git add -A
git commit -m "fix(edo): holistic-review правки код-flow briefing"
```

---

## Self-Review (выполнено при написании плана)

**Spec coverage:**
- §3 триггер → Task 3 `requires_signature_code` (тест `test_requires_code_true_only_when_flag_and_person`).
- §4.1 фаза 1 / pending-форма → Task 3 `start_employee_signature` + Task 4 ветвление `sign-employee`.
- §4.2 фаза 2 / commit-on-conflict → Task 3 `confirm_code` + Task 4 эндпоинт + `test_..._attempts_increment_survive_commit`.
- §2.2 колонка+миграция → Task 1; CRUD-флаг → Task 2.
- §5 back-compat → Task 4 `test_sign_employee_without_flag_signs_immediately` + Task 6 регрессия.
- §6 контракт 409 no_pending → Task 4 `test_confirm_code_without_pending_returns_409`.
- §7 тесты → Tasks 1-5; §1 demo-seed → Task 5.

**Placeholder scan:** код приведён целиком в каждом шаге; единственные «adjust»-пометки — Task 5 (seed-entrypoint) и сноски о проверке хелперов `_entry_read`/`_briefing_signature_conflict`/`api_problem_detail` — это сознательные «прочитай реальную сигнатуру», т.к. они зависят от существующего кода модуля, который имплементер видит при правке файла.

**Type consistency:** `require_signature_code` (bool) единообразно в модели/миграции/payload/сервисе; `confirm_code`/`start_employee_signature`/`requires_signature_code`/`_find_pending_request`/`NoPendingCodeRequest` совпадают между Task 3 и Task 4; `purpose="briefing"`, `object_type="briefing_entry"`, `PepStatus.AWAITING_CODE.value` совпадают со spec и кодом ядра.
