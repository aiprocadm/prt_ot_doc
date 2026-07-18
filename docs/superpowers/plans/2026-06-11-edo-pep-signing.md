# ЭДО Срез-1: ПЭП внутренний контур — Implementation Plan

> **✅ РЕАЛИЗОВАНО И ВЛИТО — PR #649 (`974cd30`) + чистка PR #650 (`a006d6e`).** Проверено аудитом кода 2026-06-15: домен `domains/signing/pep.py`, сервис `PepSigningService`, миграция `ed01`, роуты `/sign/pep/*`, все потребители + outbox-события + тесты, симуляция вычищена. Чекбоксы ниже отмечены пост-фактум.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Рабочая простая электронная подпись (ПЭП): hash содержимого, подтверждение разовым кодом для сотрудников без учётки, верификация, журнал; потребители — докфабрика (с гейтом согласования), СИЗ МБ-7, ознакомления, briefings; честная чистка симуляции ЭДО.

**Architecture:** Чистый домен `domains/signing/pep.py` (канонизация+hash+FSM+код) → session-aware сервис `services/pep_signing.py` (загрузка объектов, гейт, диспетчер потребителей, события) → новый роутер `/sign/pep/*`. Аддитивная миграция `ed01` расширяет существующую полиморфную таблицу `signature_requests`. Симуляция (`edo_status_simulation_job`, `MockEdoOperator`, `MockSignatureProvider`, мгновенный INTERNAL) удаляется; внешние типы подписи и отправка в ЭДО возвращают честный 409.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, pytest(-asyncio). Спек: `docs/superpowers/specs/2026-06-11-edo-pep-signing-design.md`.

**Среда:** Win+Py3.13.7/.venv; pytest через PowerShell→file ([[py313_win_pytest_invocation]]); канон Py3.12 = CI (выключен). Запуск: `python -m pytest <paths> -p no:xdist --timeout=300 -q`.

---

## Карта файлов

| Файл | Действие | Ответственность |
|---|---|---|
| `backend/app/domains/signing/__init__.py` | Create | пакет |
| `backend/app/domains/signing/pep.py` | Create | чистые функции: канонизация, hash, FSM, исход confirm |
| `backend/tests/test_pep_signing_domain.py` | Create | unit домена (герметично) |
| `backend/app/models/models.py` | Modify | +6 колонок и статусы `SignatureRequest` |
| `backend/app/migrations/versions/20260611_ed01_pep_signing_columns.py` | Create | аддитивная миграция |
| `backend/tests/test_ed01_pep_signing_migration.py` | Create | guard-тест миграции |
| `backend/app/services/events.py` | Modify | EventType + payloads + dedupe |
| `backend/app/services/outbox.py` | Modify | pipeline-маппинг |
| `backend/tests/test_pep_events_registration.py` | Create | unit регистрации событий |
| `backend/app/services/pep_signing.py` | Create | сервис: builders, create/confirm/decline/verify, гейт, диспетчер |
| `tests/api/test_pep_signing_service.py` | Create | DB-тесты сервиса |
| `backend/app/api/routes/pep_signing.py` | Create | роутер `/sign/pep/*`, `/sign/acknowledgements` |
| `backend/app/api/v1/route_groups.py` | Modify | регистрация роутера |
| `tests/api/test_pep_signing_api.py` | Create | API-тесты |
| `backend/app/modules/briefings/services.py` | Modify | sign через ПЭП-ядро |
| `tests/api/test_briefing_pep_parity.py` | Create | parity-тесты briefings |
| `backend/app/api/routes/edo_workflow.py` | Modify | чистка: /edo/send 409, /signatures через ядро |
| `backend/app/api/routes/approval_orchestration.py` | Modify | чистка: kep/unep 409, refresh/verify 409, refresh_edo_status 409 |
| `backend/app/modules/sign/service.py` | Modify | удалить MockSignatureProvider (+сервисы на честные ошибки) |
| `backend/app/modules/edo/service.py` | Modify | удалить MockEdoOperator |
| `backend/app/tasks/_core.py` | Modify | удалить `edo_status_simulation_job`, `send_edo_job` |
| `backend/tests/test_document_jobs_required.py` | Modify | убрать удалённые jobs из списка |
| `backend/tests/test_edo_simulation_cleanup.py` | Create | guard чистки |

Константы домена, используемые всеми задачами (определяются в Task 1):
`PepStatus.CREATED/AWAITING_CODE/SIGNED/DECLINED/EXPIRED`, `PEP_PURPOSES = {"document", "acknowledgement", "ppe_issue", "briefing"}`, `MAX_CONFIRM_ATTEMPTS = 5`, `CONFIRM_TTL_MINUTES = 15`, функции `canonical_payload`, `content_hash`, `hash_confirm_code`, `assert_transition`, `confirm_outcome`. Сервисные сигнатуры (Task 4-5): `PepSigningService(session, tenant_id).create_request(...)`, `.confirm(...)`, `.decline(...)`, `.verify(...)`, `.create_attested(...)`.

---

### Task 1: Чистый домен `domains/signing/pep.py`

**Files:**
- Create: `backend/app/domains/signing/__init__.py` (пустой)
- Create: `backend/app/domains/signing/pep.py`
- Test: `backend/tests/test_pep_signing_domain.py`

- [x] **Step 1: Написать падающие unit-тесты**

```python
"""PEP (simple e-signature) pure domain: canonical hash, FSM, confirm-code outcome.

Hermetic: no DB, no routes (see [[local_env_drift_windows]] - route-importing
tests are un-collectable on this machine).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domains.signing.pep import (
    CONFIRM_TTL_MINUTES,
    MAX_CONFIRM_ATTEMPTS,
    PEP_PURPOSES,
    ConfirmOutcome,
    InvalidTransition,
    PepStatus,
    assert_transition,
    canonical_payload,
    confirm_outcome,
    content_hash,
    hash_confirm_code,
)

NOW = datetime.now(tz=timezone.utc)


def test_canonical_payload_is_stable_and_key_sorted():
    a = canonical_payload("document_version", "dv-1", {"b": 2, "a": 1})
    b = canonical_payload("document_version", "dv-1", {"a": 1, "b": 2})
    assert a == b
    assert a == '{"content":{"a":1,"b":2},"object_id":"dv-1","object_type":"document_version"}'


def test_canonical_payload_keeps_unicode_readable():
    payload = canonical_payload("ppe_issue", "i-1", {"item_name": "Каска"})
    assert "Каска" in payload  # ensure_ascii=False


def test_content_hash_is_sha256_hex():
    h = content_hash("payload")
    assert len(h) == 64
    assert h == content_hash("payload")
    assert h != content_hash("payload2")


def test_hash_confirm_code_salts_with_request_id():
    assert hash_confirm_code("req-1", "123456") != hash_confirm_code("req-2", "123456")
    assert hash_confirm_code("req-1", "123456") == hash_confirm_code("req-1", "123456")


def test_valid_transitions_pass():
    assert_transition(PepStatus.CREATED, PepStatus.SIGNED)
    assert_transition(PepStatus.CREATED, PepStatus.AWAITING_CODE)
    assert_transition(PepStatus.CREATED, PepStatus.DECLINED)
    assert_transition(PepStatus.AWAITING_CODE, PepStatus.SIGNED)
    assert_transition(PepStatus.AWAITING_CODE, PepStatus.DECLINED)
    assert_transition(PepStatus.AWAITING_CODE, PepStatus.EXPIRED)


@pytest.mark.parametrize(
    "src,dst",
    [
        (PepStatus.SIGNED, PepStatus.DECLINED),
        (PepStatus.DECLINED, PepStatus.SIGNED),
        (PepStatus.EXPIRED, PepStatus.SIGNED),
        (PepStatus.CREATED, PepStatus.EXPIRED),  # expire only from awaiting_code
    ],
)
def test_invalid_transitions_raise(src, dst):
    with pytest.raises(InvalidTransition):
        assert_transition(src, dst)


def _outcome(*, code="123456", stored_code="123456", attempts=0, expired=False):
    expires_at = NOW + (timedelta(minutes=-1) if expired else timedelta(minutes=5))
    return confirm_outcome(
        stored_code_hash=hash_confirm_code("req-1", stored_code),
        provided_code=code,
        request_id="req-1",
        attempts=attempts,
        expires_at=expires_at,
        now=NOW,
    )


def test_confirm_ok():
    assert _outcome() is ConfirmOutcome.OK


def test_confirm_wrong_code():
    assert _outcome(code="999999") is ConfirmOutcome.WRONG_CODE


def test_confirm_expired_wins_over_wrong_code():
    assert _outcome(code="999999", expired=True) is ConfirmOutcome.EXPIRED


def test_confirm_last_attempt_exhausts():
    # attempts уже сделанных = MAX-1; этот неверный ввод — последний
    assert _outcome(code="999999", attempts=MAX_CONFIRM_ATTEMPTS - 1) is ConfirmOutcome.EXHAUSTED


def test_purposes_vocabulary():
    assert PEP_PURPOSES == {"document", "acknowledgement", "ppe_issue", "briefing"}
    assert CONFIRM_TTL_MINUTES == 15
```

- [x] **Step 2: Убедиться, что тесты падают**

Run: `python -m pytest backend/tests/test_pep_signing_domain.py -p no:xdist --timeout=120 -q`
Expected: FAIL/ERROR `ModuleNotFoundError: app.domains.signing`

- [x] **Step 3: Реализовать домен**

`backend/app/domains/signing/__init__.py` — пустой файл.

`backend/app/domains/signing/pep.py`:

```python
"""PEP (простая электронная подпись, vNext §6.9) — чистый домен.

Канонизация подписываемого содержимого, SHA-256, FSM запроса подписи и
исход проверки разового кода. Без I/O — по образцу domains/ppe/lifecycle.py.
"""
from __future__ import annotations

import enum
import hashlib
import json
from datetime import datetime

PEP_PURPOSES = {"document", "acknowledgement", "ppe_issue", "briefing"}
MAX_CONFIRM_ATTEMPTS = 5
CONFIRM_TTL_MINUTES = 15


class PepStatus(str, enum.Enum):
    CREATED = "created"
    AWAITING_CODE = "awaiting_code"
    SIGNED = "signed"
    DECLINED = "declined"
    EXPIRED = "expired"


_TRANSITIONS: dict[PepStatus, frozenset[PepStatus]] = {
    PepStatus.CREATED: frozenset({PepStatus.AWAITING_CODE, PepStatus.SIGNED, PepStatus.DECLINED}),
    PepStatus.AWAITING_CODE: frozenset({PepStatus.SIGNED, PepStatus.DECLINED, PepStatus.EXPIRED}),
    PepStatus.SIGNED: frozenset(),
    PepStatus.DECLINED: frozenset(),
    PepStatus.EXPIRED: frozenset(),
}


class InvalidTransition(ValueError):
    pass


def assert_transition(src: PepStatus, dst: PepStatus) -> None:
    if dst not in _TRANSITIONS[src]:
        raise InvalidTransition(f"pep signature request: {src.value} -> {dst.value}")


def canonical_payload(object_type: str, object_id: str, content: dict) -> str:
    """Каноничный JSON того, ЧТО подписывается: sorted keys, компактно, юникод."""
    return json.dumps(
        {"content": content, "object_id": object_id, "object_type": object_type},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def content_hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def hash_confirm_code(request_id: str, code: str) -> str:
    """Код в БД не хранится: только SHA-256 с солью = id запроса."""
    return hashlib.sha256(f"{request_id}:{code}".encode("utf-8")).hexdigest()


class ConfirmOutcome(str, enum.Enum):
    OK = "ok"
    WRONG_CODE = "wrong_code"
    EXPIRED = "expired"
    EXHAUSTED = "exhausted"


def confirm_outcome(
    *,
    stored_code_hash: str,
    provided_code: str,
    request_id: str,
    attempts: int,
    expires_at: datetime,
    now: datetime,
) -> ConfirmOutcome:
    """Исход попытки подтверждения. Порядок проверок: TTL → код → счётчик."""
    if now >= expires_at:
        return ConfirmOutcome.EXPIRED
    if hash_confirm_code(request_id, provided_code) == stored_code_hash:
        return ConfirmOutcome.OK
    if attempts + 1 >= MAX_CONFIRM_ATTEMPTS:
        return ConfirmOutcome.EXHAUSTED
    return ConfirmOutcome.WRONG_CODE
```

- [x] **Step 4: Тесты зелёные**

Run: `python -m pytest backend/tests/test_pep_signing_domain.py -p no:xdist --timeout=120 -q`
Expected: PASS (все)

- [x] **Step 5: Commit**

```bash
git add backend/app/domains/signing backend/tests/test_pep_signing_domain.py
git commit -m "feat(edo): чистый домен ПЭП — канонизация, hash, FSM, исход кода"
```

---

### Task 2: ORM-колонки `SignatureRequest` + миграция `ed01`

**Files:**
- Modify: `backend/app/models/models.py:2900-2930` (enum + класс SignatureRequest)
- Create: `backend/app/migrations/versions/20260611_ed01_pep_signing_columns.py`
- Test: `backend/tests/test_ed01_pep_signing_migration.py`

- [x] **Step 1: Написать guard-тест миграции (падающий)**

`backend/tests/test_ed01_pep_signing_migration.py` (стиль `test_sz02_drop_ppe_family_b_migration.py` — importlib + monkeypatch op):

```python
"""ed01 migration guard: PEP columns on signature_requests, additive + reversible."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("S3_ACCESS_KEY", "test-access-key")
os.environ.setdefault("S3_SECRET_KEY", "test-secret-key")

MIGRATION = Path(__file__).resolve().parents[1] / "app" / "migrations" / "versions" / "20260611_ed01_pep_signing_columns.py"

PEP_COLUMNS = {
    "signer_person_id",
    "content_hash",
    "purpose",
    "confirm_code_hash",
    "confirm_code_expires_at",
    "confirm_attempts",
}


def _load_module():
    spec = importlib.util.spec_from_file_location("ed01_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_revision_chain():
    src = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260611_ed01_pep_signing_columns"' in src
    assert 'down_revision = "20260611_sz02_drop_ppe_family_b_tables"' in src
    assert "depends_on = None" in src


def test_upgrade_adds_exactly_pep_columns(monkeypatch):
    module = _load_module()
    added: list[tuple[str, str]] = []
    monkeypatch.setattr(module.op, "add_column", lambda table, col, *a, **k: added.append((table, col.name)))
    monkeypatch.setattr(module.op, "create_index", lambda *a, **k: None)
    monkeypatch.setattr(module.op, "create_foreign_key", lambda *a, **k: None)
    monkeypatch.setattr(module.op, "execute", lambda *a, **k: None)

    class _FakeBatch:
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            return False
        def alter_column(self, *a, **k):
            return None

    monkeypatch.setattr(module.op, "batch_alter_table", lambda *a, **k: _FakeBatch())

    class _FakeDialect:
        name = "sqlite"

    class _FakeBind:
        dialect = _FakeDialect()

    monkeypatch.setattr(module.op, "get_bind", lambda: _FakeBind())
    module.upgrade()
    assert {(t, c) for t, c in added} == {("signature_requests", c) for c in PEP_COLUMNS}


def test_downgrade_drops_exactly_pep_columns(monkeypatch):
    module = _load_module()
    dropped: list[tuple[str, str]] = []
    monkeypatch.setattr(module.op, "drop_column", lambda table, col, *a, **k: dropped.append((table, col)))
    monkeypatch.setattr(module.op, "drop_index", lambda *a, **k: None)
    monkeypatch.setattr(module.op, "drop_constraint", lambda *a, **k: None)
    monkeypatch.setattr(module.op, "execute", lambda *a, **k: None)

    class _FakeBatch:
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            return False
        def alter_column(self, *a, **k):
            return None

    monkeypatch.setattr(module.op, "batch_alter_table", lambda *a, **k: _FakeBatch())

    class _FakeDialect:
        name = "sqlite"

    class _FakeBind:
        dialect = _FakeDialect()

    monkeypatch.setattr(module.op, "get_bind", lambda: _FakeBind())
    module.downgrade()
    assert {(t, c) for t, c in dropped} == {("signature_requests", c) for c in PEP_COLUMNS}
```

- [x] **Step 2: Убедиться, что guard падает**

Run: `python -m pytest backend/tests/test_ed01_pep_signing_migration.py -p no:xdist --timeout=120 -q`
Expected: FAIL (файла миграции нет)

- [x] **Step 3: Написать миграцию**

`backend/app/migrations/versions/20260611_ed01_pep_signing_columns.py` (стиль sz01: диалект-гард `op.get_bind().dialect.name`, batch для SQLite):

```python
"""ed01: PEP signing columns on signature_requests (ЭДО Срез-1, vNext §6.9).

Additive: the polymorphic signature_requests table (next57) gains the PEP
internal-signature fields — signer person, canonical content hash, purpose,
one-time confirm-code state — plus a status widening VARCHAR(16)->VARCHAR(32)
for the new awaiting_code/declined/expired values. New rows are written with
signature_type='pep', provider='internal'; legacy kep/unep rows are untouched.

Downgrade drops the six columns and narrows status back; it fails honestly on
PG if rows carry status values longer than 16 chars (same policy as sz01's
honest downgrade on written_off/replaced).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260611_ed01_pep_signing_columns"
down_revision = "20260611_sz02_drop_ppe_family_b_tables"
branch_labels = None
depends_on = None

TABLE = "signature_requests"


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.add_column(TABLE, sa.Column("signer_person_id", sa.String(length=36), nullable=True))
    op.add_column(TABLE, sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.add_column(TABLE, sa.Column("purpose", sa.String(length=32), nullable=True))
    op.add_column(TABLE, sa.Column("confirm_code_hash", sa.String(length=64), nullable=True))
    op.add_column(TABLE, sa.Column("confirm_code_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(TABLE, sa.Column("confirm_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("ix_signature_requests_signer_person_id", TABLE, ["signer_person_id"])
    if dialect == "postgresql":
        op.create_foreign_key(
            "fk_signature_requests_signer_person_id_person",
            TABLE,
            "person",
            ["signer_person_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.execute(f"ALTER TABLE {TABLE} ALTER COLUMN status TYPE VARCHAR(32)")
    else:
        with op.batch_alter_table(TABLE) as batch:
            batch.alter_column(
                "status",
                existing_type=sa.String(length=16),
                type_=sa.String(length=32),
                existing_nullable=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.drop_constraint("fk_signature_requests_signer_person_id_person", TABLE, type_="foreignkey")
        # honest narrowing: fails if awaiting_code rows exist (longer than 16)
        op.execute(f"ALTER TABLE {TABLE} ALTER COLUMN status TYPE VARCHAR(16)")
    else:
        with op.batch_alter_table(TABLE) as batch:
            batch.alter_column(
                "status",
                existing_type=sa.String(length=32),
                type_=sa.String(length=16),
                existing_nullable=False,
            )
    op.drop_index("ix_signature_requests_signer_person_id", table_name=TABLE)
    op.drop_column(TABLE, "confirm_attempts")
    op.drop_column(TABLE, "confirm_code_expires_at")
    op.drop_column(TABLE, "confirm_code_hash")
    op.drop_column(TABLE, "purpose")
    op.drop_column(TABLE, "content_hash")
    op.drop_column(TABLE, "signer_person_id")
```

- [x] **Step 4: Обновить ORM-модель**

В `backend/app/models/models.py`: расширить enum (после класса `SignatureRequestStatus`, строка ~2900 — НЕ трогая существующие значения):

```python
class SignatureRequestStatus(str, enum.Enum):
    CREATED = "created"
    REQUESTED = "requested"
    SIGNED = "signed"
    FAILED = "failed"
    AWAITING_CODE = "awaiting_code"
    DECLINED = "declined"
    EXPIRED = "expired"
```

В класс `SignatureRequest` (после `result_json`, перед `__table_args__`) добавить:

```python
    # --- PEP (простая электронная подпись, ed01) ---
    signer_person_id: Mapped[str | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), nullable=True, index=True
    )
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confirm_code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confirm_code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirm_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
```

И в той же модели `status` сменить длину: `String(16)` → `String(32)` (поле объявлено как `mapped_column(String(16), ...)` — найти в классе и заменить на `String(32)`).

- [x] **Step 5: Guard + mapper-конфигурация зелёные**

Run: `python -m pytest backend/tests/test_ed01_pep_signing_migration.py backend/tests/test_orm_mapper_configuration.py -p no:xdist --timeout=300 -q`
Expected: PASS

- [x] **Step 6: Миграционный когорт зелёный**

Run: `python -m pytest backend/tests -k "migration or downgrade or mapper" -p no:xdist --timeout=600 -q`
Expected: PASS (как в Срезе-2-мини: ~102+ passed)

- [x] **Step 7: Commit**

```bash
git add backend/app/models/models.py backend/app/migrations/versions/20260611_ed01_pep_signing_columns.py backend/tests/test_ed01_pep_signing_migration.py
git commit -m "feat(edo): ed01 — ПЭП-колонки signature_requests + ORM (sz02->ed01)"
```

---

### Task 3: События `PEPSigned` / `PEPDeclined`

**Files:**
- Modify: `backend/app/services/events.py` (EventType ~строки 39-40 соседство, payloads ~128, `_PAYLOADS` ~230, `dedupe_key_for` ~292)
- Modify: `backend/app/services/outbox.py:45-76` (`_pipeline_for_event`)
- Test: `backend/tests/test_pep_events_registration.py`

- [x] **Step 1: Падающий unit-тест**

```python
"""PEP events are first-class citizens of the outbox pipeline (sibling parity
with PPEWrittenOff/PPEReplacementDue registration, СИЗ Срез-1)."""
from __future__ import annotations

import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("S3_ACCESS_KEY", "test-access-key")
os.environ.setdefault("S3_SECRET_KEY", "test-secret-key")

from app.services.events import (  # noqa: E402
    _PAYLOADS,
    EventType,
    PEPDeclinedPayload,
    PEPSignedPayload,
    dedupe_key_for,
)
from app.services.outbox import PipelineType, _pipeline_for_event  # noqa: E402


def test_event_types_registered():
    assert EventType.PEP_SIGNED.value == "PEPSigned"
    assert EventType.PEP_DECLINED.value == "PEPDeclined"
    assert _PAYLOADS[EventType.PEP_SIGNED] is PEPSignedPayload
    assert _PAYLOADS[EventType.PEP_DECLINED] is PEPDeclinedPayload


def test_dedupe_keys():
    signed = PEPSignedPayload(
        tenant_id="t1", signature_request_id="sr-1", object_type="ppe_issue",
        object_id="i-1", purpose="ppe_issue", signer_user_id=None, signer_person_id="p-1",
    )
    declined = PEPDeclinedPayload(tenant_id="t1", signature_request_id="sr-1", reason="manual")
    assert dedupe_key_for(EventType.PEP_SIGNED, signed) == "sr-1:pep_signed"
    assert dedupe_key_for(EventType.PEP_DECLINED, declined) == "sr-1:pep_declined"


def test_pipeline_routing():
    assert _pipeline_for_event("PEPSigned") is PipelineType.DOCUMENT
    assert _pipeline_for_event("PEPDeclined") is PipelineType.DOCUMENT
```

- [x] **Step 2: Убедиться, что падает**

Run: `python -m pytest backend/tests/test_pep_events_registration.py -p no:xdist --timeout=120 -q`
Expected: FAIL (ImportError PEPSignedPayload)

- [x] **Step 3: Реализовать регистрацию**

В `backend/app/services/events.py`:

В `EventType` (рядом с PPE_WRITTEN_OFF):
```python
    PEP_SIGNED = "PEPSigned"
    PEP_DECLINED = "PEPDeclined"
```

Payload-классы (рядом с PPEWrittenOffPayload):
```python
class PEPSignedPayload(BaseEventPayload):
    signature_request_id: str
    object_type: str
    object_id: str
    purpose: str
    signer_user_id: str | None = None
    signer_person_id: str | None = None


class PEPDeclinedPayload(BaseEventPayload):
    signature_request_id: str
    reason: str | None = None
```

В `_PAYLOADS`:
```python
    EventType.PEP_SIGNED: PEPSignedPayload,
    EventType.PEP_DECLINED: PEPDeclinedPayload,
```

В `dedupe_key_for` (рядом с PPE-ветками):
```python
    if isinstance(payload, PEPSignedPayload):
        return f"{payload.signature_request_id}:pep_signed"
    if isinstance(payload, PEPDeclinedPayload):
        return f"{payload.signature_request_id}:pep_declined"
```

В `backend/app/services/outbox.py` `_pipeline_for_event` — добавить в существующий set с `EventType.DOCUMENT_SIGNED` (возвращающий `PipelineType.DOCUMENT`) два значения: `EventType.PEP_SIGNED, EventType.PEP_DECLINED`.

- [x] **Step 4: Тесты зелёные + outbox-регрессия**

Run: `python -m pytest backend/tests/test_pep_events_registration.py backend/tests -k "outbox" -p no:xdist --timeout=300 -q`
Expected: PASS (новые + ~22 outbox-теста)

- [x] **Step 5: Commit**

```bash
git add backend/app/services/events.py backend/app/services/outbox.py backend/tests/test_pep_events_registration.py
git commit -m "feat(edo): события PEPSigned/PEPDeclined в outbox-пайплайне"
```

---

### Task 4: Сервис `PepSigningService` — create/confirm/decline

**Files:**
- Create: `backend/app/services/pep_signing.py`
- Test: `tests/api/test_pep_signing_service.py` (DB-тесты: фикстуры `sessionmaker`/`data_factory` живут в корневом `tests/conftest.py` — НЕ в `backend/tests/`, урок Подрядчиков Среза-3)

- [x] **Step 1: Падающие DB-тесты ядра сервиса**

```python
"""PepSigningService: create/confirm/decline + builders (DB-level, no HTTP)."""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.domains.signing.pep import MAX_CONFIRM_ATTEMPTS, PepStatus
from app.models.models import PPEIssue, SignatureRequest
from app.services.pep_signing import PepConflict, PepNotFound, PepSigningService


async def _person_with_issue(session, data_factory, *, tag: str):
    tenant = await data_factory.ensure_tenant(session=session)
    company = await data_factory.create_company(tenant=tenant, session=session, name=f"PEP {tag}")
    person = await data_factory.create_person(tenant=tenant, company=company, session=session)
    issue = PPEIssue(
        tenant_id=tenant.id, person_id=person.id, item_name=f"Каска {tag}",
        quantity=1, status="issued",
    )
    session.add(issue)
    await session.flush()
    return tenant, person, issue


@pytest.mark.asyncio
async def test_create_for_person_returns_one_time_code_and_awaits(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, person, issue = await _person_with_issue(session, data_factory, tag="c1")
        svc = PepSigningService(session, str(tenant.id))
        req, code = await svc.create_request(
            object_type="ppe_issue", object_id=issue.id, purpose="ppe_issue",
            signer_person_id=person.id, requested_by="user-1",
        )
        await session.commit()
        assert req.status == PepStatus.AWAITING_CODE.value
        assert code is not None and len(code) == 6 and code.isdigit()
        assert req.confirm_code_hash and req.confirm_code_hash != code
        assert req.content_hash and len(req.content_hash) == 64
        assert req.signature_type == "pep" and req.provider == "internal"
        assert req.purpose == "ppe_issue"


@pytest.mark.asyncio
async def test_confirm_with_valid_code_signs_and_snapshots_name(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, person, issue = await _person_with_issue(session, data_factory, tag="c2")
        svc = PepSigningService(session, str(tenant.id))
        req, code = await svc.create_request(
            object_type="ppe_issue", object_id=issue.id, purpose="ppe_issue",
            signer_person_id=person.id, requested_by="user-1",
        )
        signed = await svc.confirm(req.id, code=code)
        await session.commit()
        assert signed.status == PepStatus.SIGNED.value
        assert signed.signed_at is not None
        assert person.last_name in (signed.signer_name or "")


@pytest.mark.asyncio
async def test_confirm_wrong_code_5_times_declines(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, person, issue = await _person_with_issue(session, data_factory, tag="c3")
        svc = PepSigningService(session, str(tenant.id))
        req, _code = await svc.create_request(
            object_type="ppe_issue", object_id=issue.id, purpose="ppe_issue",
            signer_person_id=person.id, requested_by="user-1",
        )
        for attempt in range(MAX_CONFIRM_ATTEMPTS):
            with pytest.raises(PepConflict):
                await svc.confirm(req.id, code="000000")
        assert req.status == PepStatus.DECLINED.value
        assert req.confirm_attempts == MAX_CONFIRM_ATTEMPTS


@pytest.mark.asyncio
async def test_confirm_expired_code_expires(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, person, issue = await _person_with_issue(session, data_factory, tag="c4")
        svc = PepSigningService(session, str(tenant.id))
        req, code = await svc.create_request(
            object_type="ppe_issue", object_id=issue.id, purpose="ppe_issue",
            signer_person_id=person.id, requested_by="user-1",
        )
        req.confirm_code_expires_at = req.confirm_code_expires_at - timedelta(minutes=60)
        with pytest.raises(PepConflict):
            await svc.confirm(req.id, code=code)
        assert req.status == PepStatus.EXPIRED.value


@pytest.mark.asyncio
async def test_duplicate_active_request_conflicts(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, person, issue = await _person_with_issue(session, data_factory, tag="c5")
        svc = PepSigningService(session, str(tenant.id))
        await svc.create_request(
            object_type="ppe_issue", object_id=issue.id, purpose="ppe_issue",
            signer_person_id=person.id, requested_by="user-1",
        )
        with pytest.raises(PepConflict):
            await svc.create_request(
                object_type="ppe_issue", object_id=issue.id, purpose="ppe_issue",
                signer_person_id=person.id, requested_by="user-1",
            )


@pytest.mark.asyncio
async def test_user_signer_self_signs_instantly(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, person, issue = await _person_with_issue(session, data_factory, tag="c6")
        svc = PepSigningService(session, str(tenant.id))
        req, code = await svc.create_request(
            object_type="ppe_issue", object_id=issue.id, purpose="ppe_issue",
            signer_user_id="user-1", requested_by="user-1",
        )
        await session.commit()
        assert code is None
        assert req.status == PepStatus.SIGNED.value


@pytest.mark.asyncio
async def test_unknown_object_raises_not_found(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        svc = PepSigningService(session, str(tenant.id))
        with pytest.raises(PepNotFound):
            await svc.create_request(
                object_type="ppe_issue", object_id="missing", purpose="ppe_issue",
                signer_user_id="user-1", requested_by="user-1",
            )


@pytest.mark.asyncio
async def test_decline_from_awaiting(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, person, issue = await _person_with_issue(session, data_factory, tag="c7")
        svc = PepSigningService(session, str(tenant.id))
        req, _ = await svc.create_request(
            object_type="ppe_issue", object_id=issue.id, purpose="ppe_issue",
            signer_person_id=person.id, requested_by="user-1",
        )
        declined = await svc.decline(req.id, reason="отказ сотрудника")
        assert declined.status == PepStatus.DECLINED.value


@pytest.mark.asyncio
async def test_tenant_isolation_on_confirm(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, person, issue = await _person_with_issue(session, data_factory, tag="c8")
        other = await data_factory.ensure_tenant(session=session, slug="other-pep")
        svc = PepSigningService(session, str(tenant.id))
        req, code = await svc.create_request(
            object_type="ppe_issue", object_id=issue.id, purpose="ppe_issue",
            signer_person_id=person.id, requested_by="user-1",
        )
        foreign = PepSigningService(session, str(other.id))
        with pytest.raises(PepNotFound):
            await foreign.confirm(req.id, code=code)
```

ПРИМЕЧАНИЕ исполнителю: если у `data_factory.ensure_tenant` нет параметра `slug` — посмотреть сигнатуру в `tests/conftest.py`/`TestDataFactory` и создать второй тенант принятым там способом (как в существующих tenant-isolation тестах, например `tests/api/test_ppe_norm_admission.py` или `test_contractor_*`).

- [x] **Step 2: Убедиться, что падают**

Run: `python -m pytest tests/api/test_pep_signing_service.py -p no:xdist --timeout=300 -q`
Expected: FAIL (ModuleNotFoundError app.services.pep_signing)

- [x] **Step 3: Реализовать сервис**

`backend/app/services/pep_signing.py`:

```python
"""PEP signing service (vNext §6.9): session-aware оркестрация чистого домена.

Создание/подтверждение/отклонение запросов ПЭП, построение канонического
payload по типу объекта, гейт согласования (Task 5), диспетчер потребителей
на signed (Task 5), outbox-события.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.signing.pep import (
    CONFIRM_TTL_MINUTES,
    PEP_PURPOSES,
    ConfirmOutcome,
    PepStatus,
    assert_transition,
    canonical_payload,
    confirm_outcome,
    content_hash,
    hash_confirm_code,
)
from app.models.document import DocumentVersion
from app.models.models import BriefingEntry, Person, PPEIssue, SignatureRequest
from app.services.events import EventType
from app.services.outbox import OutboxService


class PepNotFound(LookupError):
    """Объект/запрос не найден (или чужой тенант)."""


class PepConflict(ValueError):
    """Бизнес-конфликт: дубль, неверный/истёкший код, недопустимый переход."""


_ACTIVE_STATUSES = (PepStatus.CREATED.value, PepStatus.AWAITING_CODE.value)


class PepSigningService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    # --- payload builders -------------------------------------------------

    async def _build_content(self, object_type: str, object_id: str) -> dict[str, Any]:
        if object_type == "document_version":
            doc = await self.session.get(DocumentVersion, object_id)
            if doc is None or str(doc.tenant_id) != str(self.tenant_id):
                raise PepNotFound("document_version")
            return {
                "document_id": doc.document_id,
                "document_version_id": doc.id,
                "version_number": doc.version_number,
                "file_key": doc.file_key,
            }
        if object_type == "ppe_issue":
            issue = await self.session.get(PPEIssue, object_id)
            if issue is None or str(issue.tenant_id) != str(self.tenant_id):
                raise PepNotFound("ppe_issue")
            return {
                "ppe_issue_id": issue.id,
                "person_id": issue.person_id,
                "item_id": issue.item_id,
                "item_name": issue.item_name,
                "quantity": issue.quantity,
                "status": issue.status,
                "issued_at": issue.issued_at.isoformat() if issue.issued_at else None,
            }
        if object_type == "briefing_entry":
            entry = await self.session.get(BriefingEntry, object_id)
            if entry is None or str(entry.tenant_id) != str(self.tenant_id):
                raise PepNotFound("briefing_entry")
            return {
                "briefing_entry_id": entry.id,
                "person_id": entry.person_id,
                "briefing_template_id": entry.briefing_template_id,
                "briefing_date": entry.briefing_date.isoformat() if entry.briefing_date else None,
            }
        raise PepConflict(f"unsupported object_type: {object_type}")

    async def _signer_name(self, *, signer_user_id: str | None, signer_person_id: str | None) -> str | None:
        if signer_person_id:
            person = await self.session.get(Person, signer_person_id)
            if person is None or str(person.tenant_id) != str(self.tenant_id):
                raise PepNotFound("person")
            parts = [person.last_name, person.first_name, person.middle_name or ""]
            return " ".join(p for p in parts if p).strip()
        return signer_user_id

    # --- lifecycle ---------------------------------------------------------

    async def create_request(
        self,
        *,
        object_type: str,
        object_id: str,
        purpose: str,
        requested_by: str,
        signer_user_id: str | None = None,
        signer_person_id: str | None = None,
    ) -> tuple[SignatureRequest, str | None]:
        """Возвращает (запрос, разовый код | None). Код виден только здесь."""
        if purpose not in PEP_PURPOSES:
            raise PepConflict(f"unsupported purpose: {purpose}")
        if bool(signer_user_id) == bool(signer_person_id):
            raise PepConflict("exactly one of signer_user_id / signer_person_id is required")

        content = await self._build_content(object_type, object_id)
        await self._approval_gate(object_type, object_id, purpose)  # Task 5; до Task 5 — заглушка-noop

        dup = (
            await self.session.execute(
                select(SignatureRequest).where(
                    SignatureRequest.tenant_id == self.tenant_id,
                    SignatureRequest.object_type == object_type,
                    SignatureRequest.object_id == object_id,
                    SignatureRequest.purpose == purpose,
                    SignatureRequest.status.in_(_ACTIVE_STATUSES),
                    SignatureRequest.signer_user_id == signer_user_id
                    if signer_user_id
                    else SignatureRequest.signer_person_id == signer_person_id,
                )
            )
        ).scalars().first()
        if dup is not None:
            raise PepConflict("active pep request already exists for this signer/object")

        payload = canonical_payload(object_type, object_id, content)
        req = SignatureRequest(
            tenant_id=self.tenant_id,
            object_type=object_type,
            object_id=object_id,
            provider="internal",
            provider_code="internal",
            signature_type="pep",
            purpose=purpose,
            requested_by=requested_by,
            signer_user_id=signer_user_id,
            signer_person_id=signer_person_id,
            content_hash=content_hash(payload),
            payload_json={"canonical": payload},
            status=PepStatus.CREATED.value,
        )
        self.session.add(req)
        await self.session.flush()

        code: str | None = None
        if signer_person_id:
            code = f"{secrets.randbelow(1_000_000):06d}"
            req.confirm_code_hash = hash_confirm_code(req.id, code)
            req.confirm_code_expires_at = datetime.now(tz=timezone.utc) + timedelta(minutes=CONFIRM_TTL_MINUTES)
            assert_transition(PepStatus.CREATED, PepStatus.AWAITING_CODE)
            req.status = PepStatus.AWAITING_CODE.value
        elif signer_user_id == requested_by:
            await self._mark_signed(req)
        # else: чужой user-подписант подтверждает сам через confirm(code=None)
        await self.session.flush()
        return req, code

    async def _get_own(self, request_id: str) -> SignatureRequest:
        req = await self.session.get(SignatureRequest, request_id)
        if req is None or str(req.tenant_id) != str(self.tenant_id) or req.signature_type != "pep":
            raise PepNotFound("signature_request")
        return req

    async def confirm(self, request_id: str, *, code: str | None = None, acting_user_id: str | None = None) -> SignatureRequest:
        req = await self._get_own(request_id)
        if req.signer_person_id:
            if req.status != PepStatus.AWAITING_CODE.value:
                raise PepConflict(f"cannot confirm from status {req.status}")
            if not code:
                raise PepConflict("code is required for person signer")
            outcome = confirm_outcome(
                stored_code_hash=req.confirm_code_hash or "",
                provided_code=code,
                request_id=req.id,
                attempts=req.confirm_attempts,
                expires_at=req.confirm_code_expires_at,
                now=datetime.now(tz=timezone.utc),
            )
            if outcome is ConfirmOutcome.EXPIRED:
                assert_transition(PepStatus.AWAITING_CODE, PepStatus.EXPIRED)
                req.status = PepStatus.EXPIRED.value
                await self.session.flush()
                raise PepConflict("confirmation code expired")
            if outcome is ConfirmOutcome.EXHAUSTED:
                req.confirm_attempts += 1
                await self._mark_declined(req, reason="attempts_exhausted")
                raise PepConflict("confirmation attempts exhausted")
            if outcome is ConfirmOutcome.WRONG_CODE:
                req.confirm_attempts += 1
                await self.session.flush()
                raise PepConflict("wrong confirmation code")
        else:
            if req.status != PepStatus.CREATED.value:
                raise PepConflict(f"cannot confirm from status {req.status}")
            if acting_user_id is not None and acting_user_id != req.signer_user_id:
                raise PepConflict("only the designated signer can confirm")
        await self._mark_signed(req)
        return req

    async def decline(self, request_id: str, *, reason: str | None = None) -> SignatureRequest:
        req = await self._get_own(request_id)
        await self._mark_declined(req, reason=reason or "manual")
        return req

    # --- terminal transitions + events -------------------------------------

    async def _mark_signed(self, req: SignatureRequest) -> None:
        assert_transition(PepStatus(req.status), PepStatus.SIGNED)
        req.status = PepStatus.SIGNED.value
        req.signed_at = datetime.now(tz=timezone.utc)
        req.signer_name = await self._signer_name(
            signer_user_id=req.signer_user_id, signer_person_id=req.signer_person_id
        )
        req.confirm_code_hash = None
        await self._dispatch_signed(req)  # Task 5; до Task 5 — заглушка-noop
        await OutboxService(self.session).enqueue(
            tenant_id=self.tenant_id,
            event_type=EventType.PEP_SIGNED.value,
            idempotency_key=f"pep.signed:{req.id}",
            payload={
                "tenant_id": self.tenant_id,
                "signature_request_id": req.id,
                "object_type": req.object_type,
                "object_id": req.object_id,
                "purpose": req.purpose,
                "signer_user_id": req.signer_user_id,
                "signer_person_id": req.signer_person_id,
            },
        )
        await self.session.flush()

    async def _mark_declined(self, req: SignatureRequest, *, reason: str) -> None:
        assert_transition(PepStatus(req.status), PepStatus.DECLINED)
        req.status = PepStatus.DECLINED.value
        req.result_json = {**(req.result_json or {}), "declined_reason": reason}
        await OutboxService(self.session).enqueue(
            tenant_id=self.tenant_id,
            event_type=EventType.PEP_DECLINED.value,
            idempotency_key=f"pep.declined:{req.id}",
            payload={
                "tenant_id": self.tenant_id,
                "signature_request_id": req.id,
                "reason": reason,
            },
        )
        await self.session.flush()

    # --- hooks, реализуются в Task 5 ---------------------------------------

    async def _approval_gate(self, object_type: str, object_id: str, purpose: str) -> None:
        return None

    async def _dispatch_signed(self, req: SignatureRequest) -> None:
        return None
```

ПРИМЕЧАНИЕ исполнителю: проверь импорт `BriefingEntry`, `Person`, `PPEIssue` из `app.models.models` (так делают существующие сервисы), `DocumentVersion` — из `app.models.document`. Если поле `briefing_date` у BriefingEntry называется иначе — посмотреть класс и взять фактические поля (дата + template id + person id).

- [x] **Step 4: Тесты зелёные**

Run: `python -m pytest tests/api/test_pep_signing_service.py -p no:xdist --timeout=300 -q`
Expected: PASS (9 тестов)

- [x] **Step 5: Commit**

```bash
git add backend/app/services/pep_signing.py tests/api/test_pep_signing_service.py
git commit -m "feat(edo): PepSigningService — create/confirm/decline, разовый код, события"
```

---

### Task 5: Гейт согласования + диспетчер потребителей + verify

**Files:**
- Modify: `backend/app/services/pep_signing.py` (заменить заглушки `_approval_gate`/`_dispatch_signed`, добавить `verify` и `create_attested`)
- Test: `tests/api/test_pep_signing_consumers.py` (Create)

- [x] **Step 1: Падающие тесты гейта/диспетчера/verify**

```python
"""PEP consumers: approval gate (document), signed-dispatch (DocumentVersion,
PPEIssue.signature_doc_ref), verify protocol."""
from __future__ import annotations

import pytest

from app.domains.signing.pep import PepStatus
from app.models.document import DocumentVersion
from app.models.models import ApprovalInstance, ApprovalRoute, PPEIssue
from app.models.approval_workflow import ApprovalInstanceStatus
from app.services.pep_signing import PepConflict, PepSigningService


async def _doc_version(session, data_factory, *, tag: str):
    tenant = await data_factory.ensure_tenant(session=session)
    # минимальный документ+версия; если в data_factory есть фабрика документов —
    # использовать её (посмотреть TestDataFactory), иначе создать напрямую:
    from app.models.document import Document

    doc = Document(tenant_id=tenant.id, title=f"ЛНА {tag}")
    session.add(doc)
    await session.flush()
    ver = DocumentVersion(
        tenant_id=tenant.id, document_id=doc.id, template_version="v1",
        data_json={}, file_key=f"docs/{tag}.docx", version_number=1,
    )
    session.add(ver)
    await session.flush()
    return tenant, doc, ver


@pytest.mark.asyncio
async def test_document_sign_without_route_is_allowed_and_projects_status(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, _doc, ver = await _doc_version(session, data_factory, tag="g1")
        svc = PepSigningService(session, str(tenant.id))
        req, _ = await svc.create_request(
            object_type="document_version", object_id=ver.id, purpose="document",
            signer_user_id="user-1", requested_by="user-1",
        )
        assert req.status == PepStatus.SIGNED.value
        assert ver.signature_status == "signed"


@pytest.mark.asyncio
async def test_document_sign_blocked_until_instance_approved(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, doc, ver = await _doc_version(session, data_factory, tag="g2")
        route = ApprovalRoute(tenant_id=tenant.id, code=f"r-{ver.id[:8]}", name="Маршрут")
        session.add(route)
        await session.flush()
        instance = ApprovalInstance(
            tenant_id=tenant.id, entity_type="document", entity_id=ver.id,
            approval_route_id=route.id, status=ApprovalInstanceStatus.RUNNING,
            started_by="user-1",
        )
        session.add(instance)
        await session.flush()
        svc = PepSigningService(session, str(tenant.id))
        with pytest.raises(PepConflict):
            await svc.create_request(
                object_type="document_version", object_id=ver.id, purpose="document",
                signer_user_id="user-1", requested_by="user-1",
            )
        instance.status = ApprovalInstanceStatus.APPROVED
        await session.flush()
        req, _ = await svc.create_request(
            object_type="document_version", object_id=ver.id, purpose="document",
            signer_user_id="user-1", requested_by="user-1",
        )
        assert req.status == PepStatus.SIGNED.value


@pytest.mark.asyncio
async def test_acknowledgement_skips_approval_gate(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, doc, ver = await _doc_version(session, data_factory, tag="g3")
        route = ApprovalRoute(tenant_id=tenant.id, code=f"r2-{ver.id[:8]}", name="Маршрут")
        session.add(route)
        await session.flush()
        session.add(ApprovalInstance(
            tenant_id=tenant.id, entity_type="document", entity_id=ver.id,
            approval_route_id=route.id, status=ApprovalInstanceStatus.RUNNING,
            started_by="user-1",
        ))
        company = await data_factory.create_company(tenant=tenant, session=session, name="ACK g3")
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        await session.flush()
        svc = PepSigningService(session, str(tenant.id))
        req, code = await svc.create_request(
            object_type="document_version", object_id=ver.id, purpose="acknowledgement",
            signer_person_id=person.id, requested_by="user-1",
        )
        assert req.status == PepStatus.AWAITING_CODE.value
        signed = await svc.confirm(req.id, code=code)
        # ознакомление НЕ трогает signature_status документа
        assert ver.signature_status is None
        assert signed.purpose == "acknowledgement"


@pytest.mark.asyncio
async def test_ppe_issue_signed_sets_signature_doc_ref(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session, name="PPE d1")
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        issue = PPEIssue(tenant_id=tenant.id, person_id=person.id, item_name="Каска d1", quantity=1, status="issued")
        session.add(issue)
        await session.flush()
        svc = PepSigningService(session, str(tenant.id))
        req, code = await svc.create_request(
            object_type="ppe_issue", object_id=issue.id, purpose="ppe_issue",
            signer_person_id=person.id, requested_by="user-1",
        )
        await svc.confirm(req.id, code=code)
        assert issue.signature_doc_ref == f"pep:{req.id}"


@pytest.mark.asyncio
async def test_verify_detects_content_drift(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session, name="PPE v1")
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        issue = PPEIssue(tenant_id=tenant.id, person_id=person.id, item_name="Каска v1", quantity=1, status="issued")
        session.add(issue)
        await session.flush()
        svc = PepSigningService(session, str(tenant.id))
        req, code = await svc.create_request(
            object_type="ppe_issue", object_id=issue.id, purpose="ppe_issue",
            signer_person_id=person.id, requested_by="user-1",
        )
        await svc.confirm(req.id, code=code)

        ok = await svc.verify(req.id)
        assert ok["match"] is True

        issue.quantity = 99  # дрейф содержимого после подписи
        await session.flush()
        drifted = await svc.verify(req.id)
        assert drifted["match"] is False
        assert req.verification_result_json["match"] is False
```

- [x] **Step 2: Убедиться, что падают**

Run: `python -m pytest tests/api/test_pep_signing_consumers.py -p no:xdist --timeout=300 -q`
Expected: FAIL (гейт-noop пропускает RUNNING; signature_doc_ref не проставлен; verify отсутствует)

- [x] **Step 3: Реализовать гейт, диспетчер, verify, create_attested**

В `backend/app/services/pep_signing.py` заменить заглушки:

```python
    async def _approval_gate(self, object_type: str, object_id: str, purpose: str) -> None:
        """Гейт: документ нельзя подписывать, пока активный маршрут не APPROVED.

        Ищем инстансы по обоим якорям (entity_id = id версии ИЛИ id документа) —
        в репо встречаются оба способа привязки. Ознакомления гейт не блокирует.
        """
        if purpose != "document" or object_type != "document_version":
            return None
        from app.models.approval_workflow import ApprovalInstanceStatus
        from app.models.models import ApprovalInstance

        doc = await self.session.get(DocumentVersion, object_id)
        anchor_ids = [object_id] + ([doc.document_id] if doc is not None else [])
        rows = (
            await self.session.execute(
                select(ApprovalInstance)
                .where(
                    ApprovalInstance.tenant_id == self.tenant_id,
                    ApprovalInstance.entity_id.in_(anchor_ids),
                )
                .order_by(ApprovalInstance.created_at.desc())
            )
        ).scalars().all()
        latest = rows[0] if rows else None
        if latest is not None and latest.status != ApprovalInstanceStatus.APPROVED:
            raise PepConflict("approval_required: document is not approved yet")

    async def _dispatch_signed(self, req: SignatureRequest) -> None:
        if req.purpose == "document" and req.object_type == "document_version":
            doc = await self.session.get(DocumentVersion, req.object_id)
            if doc is not None and str(doc.tenant_id) == str(self.tenant_id):
                doc.signature_status = "signed"
        elif req.purpose == "ppe_issue" and req.object_type == "ppe_issue":
            issue = await self.session.get(PPEIssue, req.object_id)
            if issue is not None and str(issue.tenant_id) == str(self.tenant_id):
                issue.signature_doc_ref = f"pep:{req.id}"
        # acknowledgement / briefing: сама запись и есть результат
```

Добавить методы:

```python
    async def verify(self, request_id: str) -> dict[str, Any]:
        """Пересчёт канонического hash по ТЕКУЩЕМУ объекту; протокол — в запись."""
        req = await self._get_own(request_id)
        if req.status != PepStatus.SIGNED.value:
            raise PepConflict(f"only signed requests are verifiable, got {req.status}")
        content = await self._build_content(req.object_type, req.object_id)
        actual = content_hash(canonical_payload(req.object_type, req.object_id, content))
        protocol = {
            "checked_at": datetime.now(tz=timezone.utc).isoformat(),
            "expected_hash": req.content_hash,
            "actual_hash": actual,
            "match": actual == req.content_hash,
        }
        req.verification_result_json = protocol
        await self.session.flush()
        return protocol

    async def create_attested(
        self,
        *,
        object_type: str,
        object_id: str,
        purpose: str,
        requested_by: str,
        signer_user_id: str | None = None,
        signer_person_id: str | None = None,
    ) -> SignatureRequest:
        """Attested-подпись: оформитель фиксирует подпись в своём присутствии.

        Для briefings (Срез-1): мгновенный signed и для person-подписанта —
        без кода; факт attestation фиксируется в result_json.
        """
        content = await self._build_content(object_type, object_id)
        payload = canonical_payload(object_type, object_id, content)
        req = SignatureRequest(
            tenant_id=self.tenant_id,
            object_type=object_type,
            object_id=object_id,
            provider="internal",
            provider_code="internal",
            signature_type="pep",
            purpose=purpose,
            requested_by=requested_by,
            signer_user_id=signer_user_id,
            signer_person_id=signer_person_id,
            content_hash=content_hash(payload),
            payload_json={"canonical": payload},
            result_json={"attested_by": requested_by},
            status=PepStatus.CREATED.value,
        )
        self.session.add(req)
        await self.session.flush()
        await self._mark_signed(req)
        return req
```

- [x] **Step 4: Тесты зелёные (оба сервисных файла)**

Run: `python -m pytest tests/api/test_pep_signing_consumers.py tests/api/test_pep_signing_service.py -p no:xdist --timeout=300 -q`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add backend/app/services/pep_signing.py tests/api/test_pep_signing_consumers.py
git commit -m "feat(edo): гейт согласования, диспетчер потребителей (DocumentVersion/PPEIssue), verify-протокол"
```

---

### Task 6: API-роутер `/sign/pep/*` + `/sign/acknowledgements`

**Files:**
- Create: `backend/app/api/routes/pep_signing.py`
- Modify: `backend/app/api/v1/route_groups.py` (импорт ~строка 12-30, регистрация ~строка 161-163)
- Test: `tests/api/test_pep_signing_api.py`

- [x] **Step 1: Падающие API-тесты**

`tests/api/test_pep_signing_api.py` — использовать фикстуры `async_client` + `make_auth_headers` (посмотреть точную сигнатуру `make_auth_headers` в `tests/conftest.py` и существующий API-тест, например `tests/api/test_contractor_documents_api.py`, и повторить паттерн заголовков):

```python
"""PEP signing HTTP contract: full person-code cycle, errors, journal, acknowledgements."""
from __future__ import annotations

import pytest

from app.models.models import PPEIssue


async def _issue_world(session, data_factory):
    tenant = await data_factory.ensure_tenant(session=session)
    company = await data_factory.create_company(tenant=tenant, session=session, name="PEP API")
    person = await data_factory.create_person(tenant=tenant, company=company, session=session)
    issue = PPEIssue(tenant_id=tenant.id, person_id=person.id, item_name="Каска api", quantity=1, status="issued")
    session.add(issue)
    await session.commit()
    return tenant, person, issue


@pytest.mark.asyncio
async def test_full_person_cycle_via_http(async_client, sessionmaker, data_factory, make_auth_headers):
    async with sessionmaker() as session:
        tenant, person, issue = await _issue_world(session, data_factory)
    headers = await make_auth_headers(role="admin", tenant=tenant)

    created = await async_client.post(
        "/sign/pep/requests",
        json={
            "object_type": "ppe_issue", "object_id": issue.id,
            "purpose": "ppe_issue", "signer_person_id": person.id,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "awaiting_code"
    assert len(body["confirm_code"]) == 6  # единственный момент видимости кода
    rid = body["id"]

    confirmed = await async_client.post(
        f"/sign/pep/requests/{rid}/confirm", json={"code": body["confirm_code"]}, headers=headers
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "signed"
    assert "confirm_code" not in confirmed.json()

    verify = await async_client.get(f"/sign/pep/requests/{rid}/verify", headers=headers)
    assert verify.status_code == 200
    assert verify.json()["match"] is True

    journal = await async_client.get(
        "/sign/pep/requests", params={"object_type": "ppe_issue", "object_id": issue.id}, headers=headers
    )
    assert journal.status_code == 200
    assert any(item["id"] == rid for item in journal.json()["items"])


@pytest.mark.asyncio
async def test_wrong_code_409_and_unknown_object_404(async_client, sessionmaker, data_factory, make_auth_headers):
    async with sessionmaker() as session:
        tenant, person, issue = await _issue_world(session, data_factory)
    headers = await make_auth_headers(role="admin", tenant=tenant)

    missing = await async_client.post(
        "/sign/pep/requests",
        json={"object_type": "ppe_issue", "object_id": "no-such", "purpose": "ppe_issue", "signer_person_id": person.id},
        headers=headers,
    )
    assert missing.status_code == 404

    created = await async_client.post(
        "/sign/pep/requests",
        json={"object_type": "ppe_issue", "object_id": issue.id, "purpose": "ppe_issue", "signer_person_id": person.id},
        headers=headers,
    )
    rid = created.json()["id"]
    wrong = await async_client.post(f"/sign/pep/requests/{rid}/confirm", json={"code": "000000"}, headers=headers)
    assert wrong.status_code == 409


@pytest.mark.asyncio
async def test_acknowledgements_journal(async_client, sessionmaker, data_factory, make_auth_headers):
    from app.models.document import Document, DocumentVersion

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session, name="ACK API")
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        doc = Document(tenant_id=tenant.id, title="Инструкция ACK")
        session.add(doc)
        await session.flush()
        ver = DocumentVersion(
            tenant_id=tenant.id, document_id=doc.id, template_version="v1",
            data_json={}, file_key="docs/ack.docx", version_number=1,
        )
        session.add(ver)
        await session.commit()
    headers = await make_auth_headers(role="admin", tenant=tenant)

    created = await async_client.post(
        "/sign/pep/requests",
        json={"object_type": "document_version", "object_id": ver.id, "purpose": "acknowledgement", "signer_person_id": person.id},
        headers=headers,
    )
    code = created.json()["confirm_code"]
    rid = created.json()["id"]
    await async_client.post(f"/sign/pep/requests/{rid}/confirm", json={"code": code}, headers=headers)

    acks = await async_client.get(
        "/sign/acknowledgements", params={"document_version_id": ver.id}, headers=headers
    )
    assert acks.status_code == 200
    items = acks.json()["items"]
    assert len(items) == 1
    assert items[0]["signer_person_id"] == person.id
    assert items[0]["status"] == "signed"
```

ПРИМЕЧАНИЕ исполнителю: точную форму `make_auth_headers`/полей `Document` сверить с conftest и существующими API-тестами; если у `Document` обязательны другие поля — добавить их по фактической модели.

- [x] **Step 2: Убедиться, что падают**

Run: `python -m pytest tests/api/test_pep_signing_api.py -p no:xdist --timeout=300 -q`
Expected: FAIL (404 на /sign/pep/requests — роутера нет)

- [x] **Step 3: Реализовать роутер**

`backend/app/api/routes/pep_signing.py` (зависимости и error-хелперы зеркалят `approval_orchestration.py` — посмотреть его шапку и взять те же импорты `SessionDep`/`TenantDep`/`EditorAccess`/`ReaderAccess`/`_correlation_id`/`api_problem_detail`; если они определены локально в том файле — продублировать определения локально, НЕ импортировать кросс-роутерно):

```python
"""PEP signing API (vNext §6.9): внутренняя простая электронная подпись."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select

from app.core.audit_decorator import audit_operation
from app.models.models import SignatureRequest
from app.services.pep_signing import PepConflict, PepNotFound, PepSigningService

router = APIRouter()


class PepRequestIn(BaseModel):
    object_type: str
    object_id: str
    purpose: str
    signer_user_id: str | None = None
    signer_person_id: str | None = None


class PepConfirmIn(BaseModel):
    code: str | None = None


class PepDeclineIn(BaseModel):
    reason: str | None = None


def _pep_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PepNotFound):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(code="PEP_NOT_FOUND", message=str(exc), error_type="pep"),
        )
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=api_problem_detail(code="PEP_CONFLICT", message=str(exc), error_type="pep"),
    )


def _request_read(row: SignatureRequest) -> dict:
    return {
        "id": row.id,
        "object_type": row.object_type,
        "object_id": row.object_id,
        "purpose": row.purpose,
        "status": row.status,
        "signer_user_id": row.signer_user_id,
        "signer_person_id": row.signer_person_id,
        "signer_name": row.signer_name,
        "content_hash": row.content_hash,
        "signed_at": row.signed_at.isoformat() if row.signed_at else None,
    }


@router.post("/sign/pep/requests", status_code=status.HTTP_201_CREATED)
@audit_operation("create", "pep_signature_request")
async def create_pep_request(payload: PepRequestIn, request: Request, response: Response, session: SessionDep, tenant: TenantDep, access: EditorAccess):
    svc = PepSigningService(session, _tenant_id_value(tenant))
    try:
        req, code = await svc.create_request(
            object_type=payload.object_type,
            object_id=payload.object_id,
            purpose=payload.purpose,
            requested_by=str(access.user.id),
            signer_user_id=payload.signer_user_id,
            signer_person_id=payload.signer_person_id,
        )
    except (PepNotFound, PepConflict) as exc:
        raise _pep_error(exc) from exc
    body = _request_read(req)
    if code is not None:
        body["confirm_code"] = code  # единственный момент видимости кода
    return body


@router.post("/sign/pep/requests/{request_id}/confirm")
@audit_operation("confirm", "pep_signature_request")
async def confirm_pep_request(request_id: str, payload: PepConfirmIn, request: Request, response: Response, session: SessionDep, tenant: TenantDep, access: EditorAccess):
    svc = PepSigningService(session, _tenant_id_value(tenant))
    try:
        req = await svc.confirm(request_id, code=payload.code, acting_user_id=str(access.user.id))
    except (PepNotFound, PepConflict) as exc:
        raise _pep_error(exc) from exc
    return _request_read(req)


@router.post("/sign/pep/requests/{request_id}/decline")
@audit_operation("decline", "pep_signature_request")
async def decline_pep_request(request_id: str, payload: PepDeclineIn, request: Request, response: Response, session: SessionDep, tenant: TenantDep, _: EditorAccess):
    svc = PepSigningService(session, _tenant_id_value(tenant))
    try:
        req = await svc.decline(request_id, reason=payload.reason)
    except (PepNotFound, PepConflict) as exc:
        raise _pep_error(exc) from exc
    return _request_read(req)


@router.get("/sign/pep/requests")
async def list_pep_requests(session: SessionDep, tenant: TenantDep, _: ReaderAccess, object_type: str | None = None, object_id: str | None = None, signer_person_id: str | None = None, purpose: str | None = None, status_filter: str | None = None):
    q = select(SignatureRequest).where(
        SignatureRequest.tenant_id == _tenant_id_value(tenant),
        SignatureRequest.signature_type == "pep",
    )
    if object_type:
        q = q.where(SignatureRequest.object_type == object_type)
    if object_id:
        q = q.where(SignatureRequest.object_id == object_id)
    if signer_person_id:
        q = q.where(SignatureRequest.signer_person_id == signer_person_id)
    if purpose:
        q = q.where(SignatureRequest.purpose == purpose)
    if status_filter:
        q = q.where(SignatureRequest.status == status_filter)
    rows = (await session.execute(q.order_by(SignatureRequest.created_at.desc()))).scalars().all()
    return {"items": [_request_read(r) for r in rows]}


@router.get("/sign/pep/requests/{request_id}/verify")
async def verify_pep_request(request_id: str, session: SessionDep, tenant: TenantDep, _: ReaderAccess):
    svc = PepSigningService(session, _tenant_id_value(tenant))
    try:
        return await svc.verify(request_id)
    except (PepNotFound, PepConflict) as exc:
        raise _pep_error(exc) from exc


@router.get("/sign/acknowledgements")
async def list_acknowledgements(session: SessionDep, tenant: TenantDep, _: ReaderAccess, document_version_id: str | None = None, person_id: str | None = None):
    q = select(SignatureRequest).where(
        SignatureRequest.tenant_id == _tenant_id_value(tenant),
        SignatureRequest.signature_type == "pep",
        SignatureRequest.purpose == "acknowledgement",
    )
    if document_version_id:
        q = q.where(SignatureRequest.object_id == document_version_id)
    if person_id:
        q = q.where(SignatureRequest.signer_person_id == person_id)
    rows = (await session.execute(q.order_by(SignatureRequest.created_at.desc()))).scalars().all()
    return {"items": [_request_read(r) for r in rows]}
```

Регистрация в `backend/app/api/v1/route_groups.py`: добавить `pep_signing` в импорт из `app.api.routes` и в список групп строку `(pep_signing.router, {"tags": ["pep-signing"]}),` рядом с `approval_orchestration`.

- [x] **Step 4: Тесты зелёные**

Run: `python -m pytest tests/api/test_pep_signing_api.py -p no:xdist --timeout=300 -q`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add backend/app/api/routes/pep_signing.py backend/app/api/v1/route_groups.py tests/api/test_pep_signing_api.py
git commit -m "feat(edo): API /sign/pep/* + /sign/acknowledgements"
```

---

### Task 7: Briefings через ПЭП-ядро

**Files:**
- Modify: `backend/app/modules/briefings/services.py:14-55` (метод `sign`)
- Test: `tests/api/test_briefing_pep_parity.py` (Create)

- [x] **Step 1: Падающий parity-тест**

```python
"""Briefing signatures route through the PEP core (Срез-1: attested mode),
while the briefing HTTP/contract behaviour stays unchanged."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.models import BriefingEntry, BriefingSignature, SignatureRequest
from app.modules.briefings.services import BriefingEntryService


async def _entry(session, data_factory):
    tenant = await data_factory.ensure_tenant(session=session)
    company = await data_factory.create_company(tenant=tenant, session=session, name="BRF PEP")
    person = await data_factory.create_person(tenant=tenant, company=company, session=session)
    entry = BriefingEntry(tenant_id=tenant.id, person_id=person.id, briefing_type="primary", status="assigned")
    session.add(entry)
    await session.flush()
    return tenant, person, entry


@pytest.mark.asyncio
async def test_sign_creates_pep_record_and_links_it(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, person, entry = await _entry(session, data_factory)
        sig = await BriefingEntryService().sign(session, entry, "employee", None)
        await session.commit()

        pep = (
            await session.execute(
                select(SignatureRequest).where(
                    SignatureRequest.tenant_id == tenant.id,
                    SignatureRequest.purpose == "briefing",
                    SignatureRequest.object_id == entry.id,
                )
            )
        ).scalars().all()
        assert len(pep) == 1
        assert pep[0].status == "signed"
        assert pep[0].signer_person_id == person.id
        assert sig.signature_payload.get("pep_request_id") == pep[0].id
        # контракт briefing не сломан
        assert entry.status == "signed_employee"


@pytest.mark.asyncio
async def test_repeated_sign_does_not_duplicate_pep(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, person, entry = await _entry(session, data_factory)
        await BriefingEntryService().sign(session, entry, "employee", None)
        await BriefingEntryService().sign(session, entry, "employee", None)  # idempotent update-path
        pep = (
            await session.execute(
                select(SignatureRequest).where(
                    SignatureRequest.tenant_id == tenant.id,
                    SignatureRequest.purpose == "briefing",
                    SignatureRequest.object_id == entry.id,
                )
            )
        ).scalars().all()
        assert len(pep) == 1


@pytest.mark.asyncio
async def test_instructor_sign_pep_uses_user_signer(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant, person, entry = await _entry(session, data_factory)
        await BriefingEntryService().sign(session, entry, "instructor", "user-42")
        pep = (
            await session.execute(
                select(SignatureRequest).where(
                    SignatureRequest.tenant_id == tenant.id,
                    SignatureRequest.purpose == "briefing",
                    SignatureRequest.object_id == entry.id,
                )
            )
        ).scalars().one()
        assert pep.signer_user_id == "user-42"
        assert pep.signer_person_id is None
```

ПРИМЕЧАНИЕ исполнителю: проверь обязательные поля `BriefingEntry` (briefing_type/briefing_date/status) по модели — добавь минимально требуемые.

- [x] **Step 2: Убедиться, что падают**

Run: `python -m pytest tests/api/test_briefing_pep_parity.py -p no:xdist --timeout=300 -q`
Expected: FAIL (нет ПЭП-записей)

- [x] **Step 3: Реализовать sign через ядро**

В `BriefingEntryService.sign` (`backend/app/modules/briefings/services.py`) — в ветке создания НОВОЙ подписи (после существующего early-return для existing), перед `session.add(signature)`:

```python
        from app.services.pep_signing import PepSigningService

        pep_req = await PepSigningService(session, str(entry.tenant_id)).create_attested(
            object_type="briefing_entry",
            object_id=entry.id,
            purpose="briefing",
            requested_by=signer_user_id or "system",
            signer_user_id=signer_user_id if signer_type == "instructor" else None,
            signer_person_id=entry.person_id if signer_type == "employee" else None,
        )
        signature = BriefingSignature(
            tenant_id=entry.tenant_id,
            briefing_entry_id=entry.id,
            signer_type=signer_type,
            signer_user_id=signer_user_id,
            signature_mode="internal_simple",
            signature_payload={**(signature_payload or {}), "pep_request_id": pep_req.id},
        )
```

(заменив существующее создание `BriefingSignature`; update-path для existing НЕ трогаем — повторный sign не создаёт второй ПЭП-записи).

- [x] **Step 4: Parity + существующие briefing-тесты зелёные**

Run: `python -m pytest tests/api/test_briefing_pep_parity.py backend/tests tests -k "briefing" -p no:xdist --timeout=600 -q`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add backend/app/modules/briefings/services.py tests/api/test_briefing_pep_parity.py
git commit -m "feat(edo): briefing-подписи через ПЭП-ядро (attested), контракт прежний"
```

---

### Task 8: Чистка симуляции — `edo_workflow.py`

**Files:**
- Modify: `backend/app/api/routes/edo_workflow.py` (`create_signature` ~444-491, `sign_request` ~493, `sign_submit` ~506, `send_to_edo` ~561-618; импорт jobs ~строка 1-54)
- Test: `backend/tests/test_edo_simulation_cleanup.py` (Create, часть 1)

- [x] **Step 1: Падающие guard-тесты чистки (часть 1)**

`backend/tests/test_edo_simulation_cleanup.py` (герметичный: текст файлов, без импорта роутов — [[local_env_drift_windows]]):

```python
"""Simulation honesty guard: fake operator progress is gone from the codebase.

Text-level checks (no route imports — un-collectable on this machine, see
[[local_env_drift_windows]]); HTTP-level honesty is covered by tests/api/.
"""
from __future__ import annotations

from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"


def _src(rel: str) -> str:
    return (APP / rel).read_text(encoding="utf-8")


def test_edo_workflow_router_does_not_schedule_simulation():
    src = _src("api/routes/edo_workflow.py")
    assert "edo_status_simulation_job" not in src
    assert "send_edo_job" not in src
    assert "EDO_PROVIDER_NOT_CONFIGURED" in src


def test_internal_signature_routes_through_pep_core():
    src = _src("api/routes/edo_workflow.py")
    assert "PepSigningService" in src
    assert "SIGNATURE_PROVIDER_NOT_CONFIGURED" in src


def test_simulation_jobs_removed_from_tasks():
    src = _src("tasks/_core.py")
    assert "edo_status_simulation_job" not in src
    assert "def send_edo_job" not in src


def test_mock_providers_removed():
    assert "MockSignatureProvider" not in _src("modules/sign/service.py")
    assert "MockEdoOperator" not in _src("modules/edo/service.py")


def test_orchestration_refresh_is_honest():
    src = _src("api/routes/approval_orchestration.py")
    assert "EDO_PROVIDER_NOT_CONFIGURED" in src
    assert "SIGNATURE_PROVIDER_NOT_CONFIGURED" in src
```

- [x] **Step 2: Убедиться, что падают**

Run: `python -m pytest backend/tests/test_edo_simulation_cleanup.py -p no:xdist --timeout=120 -q`
Expected: FAIL (5/5)

- [x] **Step 3: Чистка edo_workflow.py**

1. Удалить из импортов `edo_status_simulation_job, send_edo_job` (оставить `process_inbound_webhook`).
2. Добавить хелпер рядом с `_edo_unprocessable`:

```python
def _provider_not_configured(kind: str) -> HTTPException:
    """Честный отказ вместо симуляции: внешний провайдер не настроен (Срез-1 ПЭП)."""
    code = f"{kind}_PROVIDER_NOT_CONFIGURED".upper()
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=api_problem_detail(
            code=code,
            message=f"external {kind} provider is not configured; internal PEP signing is available at /sign/pep",
            error_type="edo",
        ),
    )
```

3. `send_to_edo`: заменить ВСЁ тело после идемпотентного replay-блока на `raise _provider_not_configured("edo")` (создание EdoMessage/история/outbox/billing/`*.delay(...)` — удалить; BillingService.assert_allowed оставить ДО raise можно убрать тоже — убрать, биллинг не должен считать неотправленное).
4. `create_signature`: для `payload.type is not SignatureType.INTERNAL` → `raise _provider_not_configured("signature")`. Для INTERNAL — заменить создание `Signature` на вызов ядра:

```python
    svc = PepSigningService(session, str(tenant.id))
    try:
        req, _code = await svc.create_request(
            object_type="document_version",
            object_id=payload.document_version_id,
            purpose="document",
            requested_by=str(access.user.id),
            signer_user_id=str(access.user.id),
        )
    except PepNotFound:
        raise _edo_not_found("document_version")
    except PepConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_problem_detail(code="PEP_CONFLICT", message=str(exc), error_type="edo"),
        ) from exc
    return {"id": req.id, "status": req.status, "receipts_s3_key": None, "correlation_id": cid}
```

(старый outbox-enqueue `DOCUMENT_SIGNED` удалить — ядро уже шлёт `PEPSigned`; receipt-в-S3 удалить — протокол живёт в `verification_result_json`).
5. `sign_submit`: аналогично — INTERNAL через ядро, не-INTERNAL → `_provider_not_configured("signature")`. `sign_status`/GET `/signatures` оставить (читают историю v1).
6. Импорты: добавить `from app.services.pep_signing import PepConflict, PepNotFound, PepSigningService`.

- [x] **Step 4: Первые 3 guard-теста зелёные, существующие тесты роутера не сломаны**

Run: `python -m pytest backend/tests/test_edo_simulation_cleanup.py::test_edo_workflow_router_does_not_schedule_simulation backend/tests/test_edo_simulation_cleanup.py::test_internal_signature_routes_through_pep_core backend/tests/test_edo_workflow_error_contract.py -p no:xdist --timeout=300 -q`
Expected: PASS (остальные guard-тесты чистки падают до Task 9)

- [x] **Step 5: Commit**

```bash
git add backend/app/api/routes/edo_workflow.py backend/tests/test_edo_simulation_cleanup.py
git commit -m "feat(edo): честная чистка edo_workflow — /edo/send 409, INTERNAL через ПЭП-ядро"
```

---

### Task 9: Чистка симуляции — orchestration, моки, jobs

**Files:**
- Modify: `backend/app/api/routes/approval_orchestration.py:354-477`
- Modify: `backend/app/modules/sign/service.py` (удалить MockSignatureProvider)
- Modify: `backend/app/modules/edo/service.py` (удалить MockEdoOperator)
- Modify: `backend/app/tasks/_core.py:1831-1871` (удалить оба job)
- Modify: `backend/tests/test_document_jobs_required.py:38` (убрать удалённые jobs)
- Test: `backend/tests/test_edo_simulation_cleanup.py` (остальные guard'ы из Task 8)

- [x] **Step 1: approval_orchestration.py — честные отказы**

1. Добавить тот же хелпер `_provider_not_configured` (продублировать локально, как принято между роутерами).
2. `create_sign_request` (POST /sign/requests): `signature_type` в `{"kep","unep","mchd"}` → `raise _provider_not_configured("signature")` ДО создания записи. (`pep` сюда не ходит — у него свой роутер.)
3. `refresh_sign_status` и `verify_sign_request`: для строк с `signature_type != "pep"` → `raise _provider_not_configured("signature")`; для `pep` — `verify` делегирует `PepSigningService.verify`, `refresh-status` возвращает текущий статус без изменений (ПЭП не имеет внешнего статуса).
4. `refresh_edo_status` (POST /edo/messages/{id}/refresh-status): заменить тело (инлайн-прогрессию "sent"/"delivered") на `raise _provider_not_configured("edo")`.
5. `create_edo_message`: оставить (честная запись в реестре со статусом queued, без фейкового прогресса).

- [x] **Step 2: Удалить моки из modules**

`backend/app/modules/sign/service.py`: удалить класс `MockSignatureProvider`; `SignatureRequestService.__init__`/`SignatureVerificationService.__init__` — параметр `provider` оставить, но default `None` теперь означает «не сконфигурирован»: в `create`/`refresh`/`verify` при `self.provider is None` → `raise HTTPException(status.HTTP_409_CONFLICT, "signature provider is not configured")` (создание записи при этом не происходит).

`backend/app/modules/edo/service.py`: удалить класс `MockEdoOperator`; в сервисах default-оператор `None` (методы, требующие оператора, отсутствуют/не вызываются — `EdoWebhookService.ingest` и `EdoStatusProjectionService.apply_event` оператора не используют и остаются как есть).

- [x] **Step 3: Удалить jobs**

В `backend/app/tasks/_core.py` удалить целиком `send_edo_job` и `edo_status_simulation_job` (декораторы включительно). Проверить grep-ом, что других вызовов нет: `grep -rn "edo_status_simulation_job\|send_edo_job" backend/app` → пусто. В `backend/app/tasks/__init__.py` (или где экспортируются задачи через `__getattr__`) убрать их из экспортов, если они там перечислены.

В `backend/tests/test_document_jobs_required.py` убрать оба имени из списка required jobs (строка ~38).

- [x] **Step 4: Все guard-тесты чистки зелёные + регрессия роутеров**

Run: `python -m pytest backend/tests/test_edo_simulation_cleanup.py backend/tests/test_document_jobs_required.py backend/tests -k "approval_orchestration or edo_workflow or signing_v1 or next57" -p no:xdist --timeout=600 -q`
Expected: PASS. Если существующие тесты пинят симуляционное поведение (фейковый refresh и т.п.) — обновить их ожидания на честные 409 (это сознательное изменение контракта по спеку §6).

- [x] **Step 5: Commit**

```bash
git add backend/app/api/routes/approval_orchestration.py backend/app/modules/sign/service.py backend/app/modules/edo/service.py backend/app/tasks/_core.py backend/tests/test_document_jobs_required.py backend/tests/test_edo_simulation_cleanup.py
git commit -m "feat(edo): симуляция вычищена — честные 409 вместо фейковых статусов, моки и jobs удалены"
```

---

### Task 10: Смежная регрессия

**Files:** только запуск тестов; фиксы — точечно по падениям.

- [x] **Step 1: Контурный когорт**

Run: `python -m pytest backend/tests/test_pep_signing_domain.py backend/tests/test_ed01_pep_signing_migration.py backend/tests/test_pep_events_registration.py backend/tests/test_edo_simulation_cleanup.py tests/api/test_pep_signing_service.py tests/api/test_pep_signing_consumers.py tests/api/test_pep_signing_api.py tests/api/test_briefing_pep_parity.py -p no:xdist --timeout=600 -q`
Expected: PASS

- [x] **Step 2: Миграционный когорт**

Run: `python -m pytest backend/tests -k "migration or downgrade or mapper" -p no:xdist --timeout=900 -q`
Expected: PASS

- [x] **Step 3: Смежная регрессия (подписи/approvals/briefings/документы/outbox/СИЗ-гейт)**

Run: `python -m pytest backend/tests tests -k "approval or briefing or outbox or ppe_lifecycle or ppe_norm_admission or document_jobs" -p no:xdist --timeout=900 -q`
Expected: PASS (фиксы по падениям — только согласованные со спеком изменения контракта)

- [x] **Step 4: Commit (если были фиксы) + handoff**

Обновить `AI_IMPLEMENTATION_REPORT.md` новым handoff-блоком (паттерн прошлых срезов), закоммитить.

```bash
git add -A
git commit -m "docs(report): ЭДО Срез-1 — handoff (ПЭП внутренний контур)"
```
