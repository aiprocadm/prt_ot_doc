# P10-10 Rules-engine срез-1 — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Событийный движок правил автоматизации (§25.2 ядро): tenant-scoped правила «событие → условия → действия (задача/уведомление/webhook)» с приоритетами, логом срабатываний, dry-run/тестом по истории и admin-UI `/rules`.

**Architecture:** Синхронный hook в конце `OutboxService.enqueue` (та же транзакция, что и доменное событие; только для НОВЫХ outbox-строк; guard от каскада `rule.triggered`). Новый модуль `backend/app/modules/rules_engine/` + модели в `backend/app/models/rules_engine.py` + миграция `re01`. Фронт — новая страница `/rules` по паттерну ReportBuilderPage.

**Tech Stack:** FastAPI/SQLAlchemy(async)/Alembic + React/TS/Radix/vitest. Спека: `docs/superpowers/specs/2026-07-15-p10-10-rules-engine-srez1-design.md` (читать ПЕРЕД началом задачи).

**Операционка для всех задач:**
- Рабочая копия: worktree `D:\Кодинг\3. Создание платформы по ОТ\worktrees\p10-10-rules-engine` (ветка `feat/p10-10-rules-engine-srez1`). Все пути ниже — относительно корня worktree.
- Python: `D:\Кодинг\3. Создание платформы по ОТ\Создание платформы по ОТ\.venv\Scripts\python.exe` (3.12.10; канон 3.12.12 — отметить mismatch в отчёте). Ручные команды: `$env:PYTHONPATH="backend"`.
- pytest: PowerShell, ОДИН прогон на команду, timeout 600000 мс, батчи ≤5 файлов, НЕ параллелить два прогона с импортом app.
- Коммиты: атомарно `git add <точные пути> && git commit` в worktree; НЕ трогать main-tree.

---

### Task 1: Модели + миграция `re01` + расширение NotificationType

**Files:**
- Create: `backend/app/models/rules_engine.py`
- Modify: `backend/app/models/models.py` (re-export, паттерн строки 222 для report_builder)
- Modify: `backend/app/models/notifications.py` (NotificationType + `AUTOMATION_RULE`)
- Create: `backend/app/migrations/versions/20260715_re01_automation_rules.py`
- Test: `tests/api/test_rules_engine_model.py`

- [ ] **Step 1: Модель**

`backend/app/models/rules_engine.py`:

```python
"""Automation rules engine models (P10-10 срез-1, vNext §25.2)."""

from __future__ import annotations

import enum
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import SoftDeleteMixin, TenantBaseModel, native_enum

JSONBType = JSONB().with_variant(JSON(), "sqlite")


class RuleTriggerStatus(str, enum.Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    ERROR = "error"


class AutomationRule(TenantBaseModel, SoftDeleteMixin):
    """Правило автоматизации: событие → условия → действия.

    ``name`` уникален per tenant БЕЗ фильтра deleted_at (паттерн ReportDefinition):
    soft-deleted тёзка блокирует создание — осознанно, пин-тест ниже.
    """

    __tablename__ = "automation_rule"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    conditions_json: Mapped[dict[str, Any]] = mapped_column(
        JSONBType, nullable=False, default=dict
    )
    actions_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONBType, nullable=False, default=list
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_automation_rule_tenant_name"),
        Index("ix_automation_rule_tenant_event", "tenant_id", "event_type"),
    )


class AutomationRuleTrigger(TenantBaseModel):
    """Append-only лог срабатываний. Пишется ТОЛЬКО при матче условий или ошибке движка."""

    __tablename__ = "automation_rule_trigger"

    rule_id: Mapped[str] = mapped_column(
        ForeignKey("automation_rule.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_key: Mapped[str] = mapped_column(String(255), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_payload: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False, default=dict)
    status: Mapped[RuleTriggerStatus] = mapped_column(
        native_enum(RuleTriggerStatus, name="ruletriggerstatus"), nullable=False
    )
    actions_result: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONBType, nullable=False, default=list
    )

    __table_args__ = (
        Index("ix_automation_rule_trigger_rule_created", "tenant_id", "rule_id", "created_at"),
        Index("ix_automation_rule_trigger_tenant_created", "tenant_id", "created_at"),
    )
```

- [ ] **Step 2: Re-export для регистрации в metadata**

В `backend/app/models/models.py` найти блок `# P10-07 rb01: re-export report-builder models...` (~строка 222) и добавить рядом аналогичный:

```python
# P10-10 re01: re-export rules-engine models from app.models.rules_engine.
from app.models.rules_engine import (  # noqa: E402
    AutomationRule,
    AutomationRuleTrigger,
    RuleTriggerStatus,
)
```

(Точный стиль — скопировать соседний rb01-блок: положение импорта, наличие в `__all__` если есть.)

- [ ] **Step 3: Новый член NotificationType**

В `backend/app/models/notifications.py`, enum `NotificationType`, добавить в конец:

```python
    AUTOMATION_RULE = "AutomationRule"
```

- [ ] **Step 4: Миграция**

`backend/app/migrations/versions/20260715_re01_automation_rules.py` (шаблон — `20260714_cmt02_committee_proceedings.py`, включая `_common()`):

```python
"""re01: automation rules engine — rules + trigger log (P10-10 срез-1, vNext §25.2).

Additive. Adds:
- enum ruletriggerstatus + tables automation_rule / automation_rule_trigger
- enum label 'AutomationRule' on notificationtype (notify-действие движка)

Chains off cmt02. Downgrade drops tables/enum; enum LABEL на notificationtype
не удаляется (PG не умеет DROP VALUE) — безопасный no-op.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260715_re01_automation_rules"
down_revision = "20260714_cmt02_committee_proceedings"
branch_labels = None
depends_on = None

_TRIGGER_STATUS = postgresql.ENUM(
    "success", "partial", "error", name="ruletriggerstatus", create_type=False
)


def _common(*extra: sa.Column) -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=36),
            sa.ForeignKey("tenant.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        *extra,
    ]


def _json_type(bind) -> sa.types.TypeEngine:
    return postgresql.JSONB() if bind.dialect.name == "postgresql" else sa.JSON()


def upgrade() -> None:
    bind = op.get_bind()
    json_t = _json_type(bind)
    if bind.dialect.name == "postgresql":
        _TRIGGER_STATUS.create(bind, checkfirst=True)
        # Новый label для notify-действия движка. IF NOT EXISTS — идемпотентно (PG>=12).
        op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'AutomationRule'")

    op.create_table(
        "automation_rule",
        *_common(
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("conditions_json", json_t, nullable=False),
            sa.Column("actions_json", json_t, nullable=False),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        ),
        sa.UniqueConstraint("tenant_id", "name", name="uq_automation_rule_tenant_name"),
    )
    op.create_index(
        "ix_automation_rule_tenant_event", "automation_rule", ["tenant_id", "event_type"]
    )

    trigger_status_col = (
        _TRIGGER_STATUS
        if bind.dialect.name == "postgresql"
        else sa.Enum("success", "partial", "error", name="ruletriggerstatus", native_enum=False)
    )
    op.create_table(
        "automation_rule_trigger",
        *_common(
            sa.Column(
                "rule_id",
                sa.String(length=36),
                sa.ForeignKey("automation_rule.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("event_key", sa.String(length=255), nullable=False),
            sa.Column("correlation_id", sa.String(length=128), nullable=True),
            sa.Column("event_payload", json_t, nullable=False),
            sa.Column("status", trigger_status_col, nullable=False),
            sa.Column("actions_result", json_t, nullable=False),
        ),
    )
    op.create_index(
        "ix_automation_rule_trigger_rule_created",
        "automation_rule_trigger",
        ["tenant_id", "rule_id", "created_at"],
    )
    op.create_index(
        "ix_automation_rule_trigger_tenant_created",
        "automation_rule_trigger",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_index("ix_automation_rule_trigger_tenant_created", "automation_rule_trigger")
    op.drop_index("ix_automation_rule_trigger_rule_created", "automation_rule_trigger")
    op.drop_table("automation_rule_trigger")
    op.drop_index("ix_automation_rule_tenant_event", "automation_rule")
    op.drop_table("automation_rule")
    if bind.dialect.name == "postgresql":
        _TRIGGER_STATUS.drop(bind, checkfirst=True)
        # label 'AutomationRule' на notificationtype остаётся — PG не умеет удалять значения enum.
```

**ВАЖНО:** сверить точный стиль соседних миграций (`server_default` у created_at? В cmt02 его нет — оставить как в шаблоне). Если PG16-гейт (Task 8) поймает `ALTER TYPE ... ADD VALUE` внутри транзакции с последующим использованием — мы значение в этой транзакции НЕ используем, только объявляем; это допустимо в PG≥12.

- [ ] **Step 5: Пин-тесты модели**

`tests/api/test_rules_engine_model.py` (паттерн `tests/api/test_report_builder_model.py` — прочитать его и скопировать фикстурный стиль; ключевые кейсы):

```python
"""Пин-тесты модели AutomationRule: unique-инвариант имени (включая soft-deleted тёзку)."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.rules_engine import AutomationRule, AutomationRuleTrigger, RuleTriggerStatus


@pytest.mark.asyncio
async def test_name_unique_per_tenant(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tenant_id = str(tenant.id)
        session.add(
            AutomationRule(
                tenant_id=tenant_id, name="Правило", event_type="IncidentCreated",
                conditions_json={}, actions_json=[],
            )
        )
        await session.commit()

    async with sessionmaker() as session:
        session.add(
            AutomationRule(
                tenant_id=tenant_id, name="Правило", event_type="IncidentCreated",
                conditions_json={}, actions_json=[],
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_name_unique_includes_soft_deleted(sessionmaker, data_factory):
    # deleted_at IS NOT NULL НЕ освобождает имя — паттерн ReportDefinition (пин осознанного решения)
    from datetime import datetime, timezone

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tenant_id = str(tenant.id)
        session.add(
            AutomationRule(
                tenant_id=tenant_id, name="Тёзка", event_type="IncidentCreated",
                conditions_json={}, actions_json=[],
                deleted_at=datetime.now(tz=timezone.utc),
            )
        )
        await session.commit()

    async with sessionmaker() as session:
        session.add(
            AutomationRule(
                tenant_id=tenant_id, name="Тёзка", event_type="IncidentCreated",
                conditions_json={}, actions_json=[],
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_trigger_row_roundtrip(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        rule = AutomationRule(
            tenant_id=str(tenant.id), name="RT", event_type="IncidentCreated",
            conditions_json={}, actions_json=[],
        )
        session.add(rule)
        await session.flush()
        session.add(
            AutomationRuleTrigger(
                tenant_id=str(tenant.id), rule_id=rule.id, event_type="IncidentCreated",
                event_key="k1", event_payload={"a": 1},
                status=RuleTriggerStatus.SUCCESS, actions_result=[],
            )
        )
        await session.commit()
```

ВНИМАНИЕ: `data_factory.ensure_tenant` может возвращать один и тот же demo-tenant между тестами одного файла — если `test_name_unique_per_tenant` и `test_name_unique_includes_soft_deleted` конфликтуют по имени, использовать разные имена правил (уже так).

- [ ] **Step 6: Прогнать тесты + линт**

```powershell
$env:PYTHONPATH="backend"
& "D:\Кодинг\3. Создание платформы по ОТ\Создание платформы по ОТ\.venv\Scripts\python.exe" -m pytest "tests/api/test_rules_engine_model.py" -v --timeout=300
& "D:\Кодинг\3. Создание платформы по ОТ\Создание платформы по ОТ\.venv\Scripts\python.exe" -m ruff check backend/app/models/rules_engine.py backend/app/migrations/versions/20260715_re01_automation_rules.py tests/api/test_rules_engine_model.py
& "D:\Кодинг\3. Создание платформы по ОТ\Создание платформы по ОТ\.venv\Scripts\python.exe" -m black --check backend/app/models/rules_engine.py backend/app/migrations/versions/20260715_re01_automation_rules.py tests/api/test_rules_engine_model.py
```

Expected: 3 passed; ruff/black clean. Conftest создаёт схему через `metadata.create_all` — миграция тестами не исполняется (её проверит PG16-гейт в Task 8).

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/rules_engine.py backend/app/models/models.py backend/app/models/notifications.py backend/app/migrations/versions/20260715_re01_automation_rules.py tests/api/test_rules_engine_model.py
git commit -m "feat(rules): automation rule models + re01 migration (P10-10 срез-1)"
```

---

### Task 2: Evaluator условий (`conditions.py`)

**Files:**
- Create: `backend/app/modules/rules_engine/__init__.py` (пустой)
- Create: `backend/app/modules/rules_engine/conditions.py`
- Test: `tests/api/test_rules_engine_conditions.py`

- [ ] **Step 1: Написать evaluator**

`backend/app/modules/rules_engine/conditions.py`:

```python
"""Чистый evaluator условий правил (без I/O).

Формат: {"match": "all"|"any", "conditions": [{"field","op","value"}]}.
``field`` — dot-путь по нормализованному payload события.
Оценка устойчива: отсутствующее поле / несравнимые типы → условие НЕ матчится
(исключений наружу нет); ``exists`` — единственный op, матчащийся на отсутствии.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

ALLOWED_OPS = frozenset(
    {"eq", "ne", "in", "not_in", "gt", "gte", "lt", "lte", "contains", "exists"}
)
ALLOWED_MATCH = frozenset({"all", "any"})
MAX_CONDITIONS = 20
MAX_IN_VALUES = 50

_FIELD_RE = re.compile(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$")


class ConditionsError(ValueError):
    """Typed-ошибка валидации; code уходит в 422 API."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def validate_conditions(raw: Any, *, known_fields: frozenset[str] | None = None) -> None:
    """422-валидация структуры. ``known_fields`` — top-level поля payload-модели события
    (первый сегмент dot-пути обязан входить в них, если каталог передан)."""
    if not isinstance(raw, Mapping):
        raise ConditionsError("invalid_conditions", "conditions_json must be an object")
    match = raw.get("match", "all")
    if match not in ALLOWED_MATCH:
        raise ConditionsError("invalid_match", f"match must be one of {sorted(ALLOWED_MATCH)}")
    conditions = raw.get("conditions", [])
    if not isinstance(conditions, list):
        raise ConditionsError("invalid_conditions", "conditions must be a list")
    if len(conditions) > MAX_CONDITIONS:
        raise ConditionsError("too_many_conditions", f"at most {MAX_CONDITIONS} conditions")
    for idx, cond in enumerate(conditions):
        if not isinstance(cond, Mapping):
            raise ConditionsError("invalid_condition", f"condition #{idx} must be an object")
        field = cond.get("field")
        op = cond.get("op")
        if not isinstance(field, str) or not _FIELD_RE.match(field):
            raise ConditionsError("invalid_condition_field", f"condition #{idx}: bad field")
        if op not in ALLOWED_OPS:
            raise ConditionsError("invalid_condition_op", f"condition #{idx}: bad op {op!r}")
        if known_fields is not None and field.split(".", 1)[0] not in known_fields:
            raise ConditionsError(
                "unknown_condition_field",
                f"condition #{idx}: field {field!r} is not part of the event payload",
            )
        value = cond.get("value")
        if op in {"in", "not_in"}:
            if not isinstance(value, list) or len(value) > MAX_IN_VALUES:
                raise ConditionsError(
                    "invalid_condition_value",
                    f"condition #{idx}: {op} needs a list of <= {MAX_IN_VALUES} items",
                )
        if op == "exists" and value is not None and not isinstance(value, bool):
            raise ConditionsError(
                "invalid_condition_value", f"condition #{idx}: exists needs a bool value"
            )


def resolve_field(payload: Mapping[str, Any], path: str) -> tuple[bool, Any]:
    """(found, value) по dot-пути. Отсутствие любого сегмента → (False, None)."""
    current: Any = payload
    for segment in path.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            return False, None
        current = current[segment]
    return True, current


def _as_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _loose_eq(actual: Any, expected: Any) -> bool:
    if actual == expected:
        return True
    a_num, e_num = _as_decimal(actual), _as_decimal(expected)
    if a_num is not None and e_num is not None:
        return a_num == e_num
    return False


def _compare(actual: Any, expected: Any, op: str) -> bool:
    a_num, e_num = _as_decimal(actual), _as_decimal(expected)
    if a_num is not None and e_num is not None:
        a, b = a_num, e_num
    elif isinstance(actual, str) and isinstance(expected, str):
        a, b = actual, expected  # ISO-даты сравниваются лексикографически корректно
    else:
        return False
    return {"gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b}[op]


def evaluate_condition(cond: Mapping[str, Any], payload: Mapping[str, Any]) -> bool:
    field = str(cond.get("field", ""))
    op = str(cond.get("op", ""))
    expected = cond.get("value")
    found, actual = resolve_field(payload, field)
    if op == "exists":
        want = True if expected is None else bool(expected)
        return (found and actual is not None) == want
    if not found or actual is None:
        return False
    if op == "eq":
        return _loose_eq(actual, expected)
    if op == "ne":
        return not _loose_eq(actual, expected)
    if op == "in":
        return isinstance(expected, list) and any(_loose_eq(actual, v) for v in expected)
    if op == "not_in":
        return isinstance(expected, list) and not any(_loose_eq(actual, v) for v in expected)
    if op == "contains":
        if isinstance(actual, str):
            return isinstance(expected, str) and expected.lower() in actual.lower()
        if isinstance(actual, (list, tuple)):
            return any(_loose_eq(item, expected) for item in actual)
        return False
    if op in {"gt", "gte", "lt", "lte"}:
        return _compare(actual, expected, op)
    return False


def evaluate(conditions_json: Mapping[str, Any] | None, payload: Mapping[str, Any]) -> bool:
    """Пустые условия = матч любого события своего event_type."""
    raw = conditions_json or {}
    conditions = raw.get("conditions") or []
    if not conditions:
        return True
    results = (evaluate_condition(c, payload) for c in conditions)
    return any(results) if raw.get("match", "all") == "any" else all(results)
```

- [ ] **Step 2: Table-driven тесты**

`tests/api/test_rules_engine_conditions.py` — БЕЗ БД, чистый unit. Покрыть: каждый op (позитив+негатив), dot-путь (`before.level`), отсутствующее поле для каждого op-класса, `exists` true/false/absent, числовое сравнение строки с числом (`"17" gt 15` → True), bool не считается числом, `in` по enum-строкам, `contains` регистронезависимый для строк и membership для списков, `match: any` vs `all`, пустые условия → True, `validate_conditions` — все коды ошибок (`invalid_match`, `too_many_conditions`, `invalid_condition_field`, `invalid_condition_op`, `unknown_condition_field`, `invalid_condition_value`), лимиты MAX_CONDITIONS/MAX_IN_VALUES, известные поля через `known_fields`.

```python
"""Unit: evaluator условий (table-driven, без БД)."""

from __future__ import annotations

import pytest

from app.modules.rules_engine.conditions import (
    ConditionsError,
    evaluate,
    evaluate_condition,
    validate_conditions,
)

PAYLOAD = {
    "tenant_id": "t1",
    "actor_id": "u1",
    "severity": "critical",
    "incident_type": "injury",
    "count": 17,
    "count_str": "17",
    "flag": True,
    "before": {"level": 12},
    "tags": ["a", "b"],
    "empty": None,
    "occurred_at": "2026-07-15T10:00:00+00:00",
}


@pytest.mark.parametrize(
    ("cond", "expected"),
    [
        ({"field": "severity", "op": "eq", "value": "critical"}, True),
        ({"field": "severity", "op": "eq", "value": "low"}, False),
        ({"field": "severity", "op": "ne", "value": "low"}, True),
        ({"field": "severity", "op": "in", "value": ["high", "critical"]}, True),
        ({"field": "severity", "op": "not_in", "value": ["high", "critical"]}, False),
        ({"field": "count", "op": "gt", "value": 15}, True),
        ({"field": "count_str", "op": "gt", "value": 15}, True),  # строка-число сравнима
        ({"field": "count", "op": "lte", "value": 17}, True),
        ({"field": "count", "op": "lt", "value": 17}, False),
        ({"field": "flag", "op": "gt", "value": 0}, False),  # bool — не число
        ({"field": "before.level", "op": "gte", "value": 12}, True),  # dot-путь
        ({"field": "severity", "op": "contains", "value": "CRIT"}, True),
        ({"field": "tags", "op": "contains", "value": "b"}, True),
        ({"field": "tags", "op": "contains", "value": "z"}, False),
        ({"field": "missing", "op": "eq", "value": "x"}, False),
        ({"field": "missing", "op": "exists"}, False),
        ({"field": "missing", "op": "exists", "value": False}, True),
        ({"field": "empty", "op": "exists"}, False),  # None == отсутствие
        ({"field": "severity", "op": "exists"}, True),
        ({"field": "occurred_at", "op": "gte", "value": "2026-07-01T00:00:00+00:00"}, True),
    ],
)
def test_evaluate_condition(cond, expected):
    assert evaluate_condition(cond, PAYLOAD) is expected


def test_match_all_vs_any():
    conds = [
        {"field": "severity", "op": "eq", "value": "critical"},
        {"field": "count", "op": "gt", "value": 100},
    ]
    assert evaluate({"match": "all", "conditions": conds}, PAYLOAD) is False
    assert evaluate({"match": "any", "conditions": conds}, PAYLOAD) is True


def test_empty_conditions_match_everything():
    assert evaluate({}, PAYLOAD) is True
    assert evaluate(None, PAYLOAD) is True


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ([], "invalid_conditions"),
        ({"match": "some"}, "invalid_match"),
        ({"conditions": [{"field": "bad field!", "op": "eq"}]}, "invalid_condition_field"),
        ({"conditions": [{"field": "a", "op": "like"}]}, "invalid_condition_op"),
        ({"conditions": [{"field": "a", "op": "in", "value": "x"}]}, "invalid_condition_value"),
        (
            {"conditions": [{"field": "a", "op": "in", "value": list(range(51))}]},
            "invalid_condition_value",
        ),
        (
            {"conditions": [{"field": "a", "op": "eq", "value": 1}] * 21},
            "too_many_conditions",
        ),
    ],
)
def test_validate_conditions_errors(raw, code):
    with pytest.raises(ConditionsError) as exc:
        validate_conditions(raw)
    assert exc.value.code == code


def test_validate_known_fields():
    validate_conditions(
        {"conditions": [{"field": "severity", "op": "eq", "value": "x"}]},
        known_fields=frozenset({"severity"}),
    )
    with pytest.raises(ConditionsError) as exc:
        validate_conditions(
            {"conditions": [{"field": "bogus", "op": "eq", "value": "x"}]},
            known_fields=frozenset({"severity"}),
        )
    assert exc.value.code == "unknown_condition_field"


def test_dot_path_first_segment_validated():
    validate_conditions(
        {"conditions": [{"field": "before.level", "op": "gt", "value": 1}]},
        known_fields=frozenset({"before"}),
    )
```

- [ ] **Step 3: Прогнать + линт + commit**

```powershell
$env:PYTHONPATH="backend"
& "...\.venv\Scripts\python.exe" -m pytest "tests/api/test_rules_engine_conditions.py" -v --timeout=300
```
Expected: все passed. Затем ruff+black на оба файла и:

```bash
git add backend/app/modules/rules_engine/__init__.py backend/app/modules/rules_engine/conditions.py tests/api/test_rules_engine_conditions.py
git commit -m "feat(rules): condition evaluator + validation (P10-10)"
```

---

### Task 3: Событие `rule.triggered` + каталог событий (`catalog.py`)

**Files:**
- Modify: `backend/app/services/events.py`
- Create: `backend/app/modules/rules_engine/catalog.py`
- Test: `tests/api/test_rules_engine_catalog.py`

- [ ] **Step 1: Тип события + payload + dedupe**

В `backend/app/services/events.py`:

1. В `EventType` добавить: `RULE_TRIGGERED = "rule.triggered"`.
2. После `PersonReinstatedPayload` добавить:

```python
class RuleTriggeredPayload(BaseEventPayload):
    rule_id: str
    rule_name: str
    source_event_type: str
    source_event_key: str
    source_payload: Mapping[str, Any] = Field(default_factory=dict)
```

3. В `_PAYLOADS`: `EventType.RULE_TRIGGERED: RuleTriggeredPayload,`.
4. В `dedupe_key_for`, ПЕРЕД веткой `InternalEventPayload`, добавить:

```python
    if isinstance(payload, RuleTriggeredPayload):
        return f"rule-triggered:{payload.rule_id}:{payload.source_event_key}"
```

- [ ] **Step 2: Каталог событий**

`backend/app/modules/rules_engine/catalog.py`:

```python
"""Каталог событий для конструктора правил: интроспекция typed payload-моделей."""

from __future__ import annotations

import datetime
import types
import typing
from typing import Any

from app.services.events import _PAYLOADS, EventType

# rule.triggered исключён: правила на события самого движка запрещены (guard от каскада).
EXCLUDED_EVENT_TYPES = frozenset({EventType.RULE_TRIGGERED.value})

_SCALARS: list[tuple[type, str]] = [
    (bool, "boolean"),
    (int, "number"),
    (float, "number"),
    (datetime.datetime, "datetime"),
    (datetime.date, "date"),
    (str, "string"),
]


def _kind_for(annotation: Any) -> str:
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        return _kind_for(args[0]) if args else "object"
    if origin in (list, tuple, set):
        return "array"
    if origin is not None:  # Mapping[...] и прочие generic-контейнеры
        return "object"
    for base, kind in _SCALARS:
        if isinstance(annotation, type) and issubclass(annotation, base):
            return kind
    return "object"


def event_catalog() -> list[dict[str, Any]]:
    """[{event_type, fields: [{name, kind}]}] — отсортировано по event_type."""
    items: list[dict[str, Any]] = []
    for event_type, model_cls in _PAYLOADS.items():
        if event_type.value in EXCLUDED_EVENT_TYPES:
            continue
        fields = [
            {"name": name, "kind": _kind_for(field.annotation)}
            for name, field in model_cls.model_fields.items()
        ]
        items.append({"event_type": event_type.value, "fields": fields})
    # алиасы Signed/Exported дублируют payload-модель — дедуп по event_type.value не нужен,
    # они разные значения enum; оставляем как есть (создание правила валидируется по этому списку).
    items.sort(key=lambda i: i["event_type"])
    return items


def known_event_types() -> frozenset[str]:
    return frozenset(i["event_type"] for i in event_catalog())


def known_fields_for(event_type: str) -> frozenset[str] | None:
    for item in event_catalog():
        if item["event_type"] == event_type:
            return frozenset(f["name"] for f in item["fields"])
    return None
```

- [ ] **Step 3: Тесты каталога**

`tests/api/test_rules_engine_catalog.py`:

```python
"""Unit: каталог событий (интроспекция payload-моделей)."""

from __future__ import annotations

from app.modules.rules_engine.catalog import event_catalog, known_event_types, known_fields_for
from app.services.events import EventType, RuleTriggeredPayload, dedupe_key_for


def test_catalog_covers_registered_events_except_rule_triggered():
    types_ = known_event_types()
    assert "IncidentCreated" in types_
    assert "rule.triggered" not in types_


def test_incident_fields_and_kinds():
    incident = next(i for i in event_catalog() if i["event_type"] == "IncidentCreated")
    by_name = {f["name"]: f["kind"] for f in incident["fields"]}
    assert by_name["severity"] == "string"
    assert by_name["occurred_at"] == "datetime"
    assert "tenant_id" in by_name


def test_known_fields_for_unknown_event():
    assert known_fields_for("NoSuchEvent") is None


def test_rule_triggered_payload_dedupe():
    payload = RuleTriggeredPayload(
        tenant_id="t1", rule_id="r1", rule_name="R", source_event_type="IncidentCreated",
        source_event_key="inc-1",
    )
    assert dedupe_key_for(EventType.RULE_TRIGGERED, payload) == "rule-triggered:r1:inc-1"
```

- [ ] **Step 4: Прогнать + смежный регресс + commit**

```powershell
$env:PYTHONPATH="backend"
& "...\.venv\Scripts\python.exe" -m pytest "tests/api/test_rules_engine_catalog.py" -v --timeout=300
# смежные: outbox/events не сломаны новой веткой dedupe
& "...\.venv\Scripts\python.exe" -m pytest "tests/api/test_outbox.py" -v --timeout=600 2>$null; if (-not $?) { Write-Host "файл может называться иначе — найти тесты outbox: Get-ChildItem tests -Recurse -Filter '*outbox*'" }
```

```bash
git add backend/app/services/events.py backend/app/modules/rules_engine/catalog.py tests/api/test_rules_engine_catalog.py
git commit -m "feat(rules): rule.triggered event type + event catalog introspection (P10-10)"
```

---

### Task 4: Исполнители действий (`actions.py`)

**Files:**
- Create: `backend/app/modules/rules_engine/actions.py`
- Test: `tests/api/test_rules_engine_actions.py`

- [ ] **Step 1: Написать исполнители**

`backend/app/modules/rules_engine/actions.py`:

```python
"""Исполнители действий правил: create_task / notify / webhook.

Все действия flush-only — транзакцию владеет вызывающий (hook в enqueue).
Каждое действие возвращает ActionOutcome; исключение одного действия НЕ прерывает
остальные (ловится в engine.py).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import RoleEnum, User
from app.models.notifications import NotificationChannel, NotificationPriority, NotificationType
from app.models.obligations import Task, TaskPriority
from app.models.rules_engine import AutomationRule, AutomationRuleTrigger
from app.modules.rules_engine.conditions import resolve_field
from app.services.notifications import send_notification
from app.services.obligations import next_task_reminder

ALLOWED_ACTION_TYPES = frozenset({"create_task", "notify", "webhook"})
MAX_ACTIONS = 10
_TEMPLATE_RE = re.compile(r"\{([A-Za-z0-9_.]+)\}")
_TASK_PRIORITIES = frozenset(p.value for p in TaskPriority)
_RECIPIENT_MODES = frozenset({"actor", "user_id", "role"})
_KNOWN_ROLES = frozenset(r.value for r in RoleEnum)


class ActionsError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ActionOutcome:
    type: str
    outcome: str  # created | deduped | suppressed | error
    detail: str | None = None
    entity_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"type": self.type, "outcome": self.outcome}
        if self.detail:
            data["detail"] = self.detail
        if self.entity_ids:
            data["entity_ids"] = self.entity_ids
        return data


def validate_actions(raw: Any) -> None:
    if not isinstance(raw, list):
        raise ActionsError("invalid_actions", "actions_json must be a list")
    if not raw:
        raise ActionsError("invalid_actions", "at least one action is required")
    if len(raw) > MAX_ACTIONS:
        raise ActionsError("too_many_actions", f"at most {MAX_ACTIONS} actions")
    for idx, action in enumerate(raw):
        if not isinstance(action, Mapping):
            raise ActionsError("invalid_action", f"action #{idx} must be an object")
        a_type = action.get("type")
        if a_type not in ALLOWED_ACTION_TYPES:
            raise ActionsError("invalid_action_type", f"action #{idx}: bad type {a_type!r}")
        if a_type == "create_task":
            if not str(action.get("title_template") or "").strip():
                raise ActionsError("invalid_action", f"action #{idx}: title_template required")
            priority = action.get("priority", "medium")
            if priority not in _TASK_PRIORITIES:
                raise ActionsError("invalid_action", f"action #{idx}: bad priority {priority!r}")
            mode = action.get("assignee_mode", "none")
            if mode not in {"none", "actor", "user_id"}:
                raise ActionsError("invalid_action", f"action #{idx}: bad assignee_mode")
            if mode == "user_id" and not action.get("user_id"):
                raise ActionsError("invalid_action", f"action #{idx}: user_id required")
            due = action.get("due_in_days")
            if due is not None and (not isinstance(due, int) or due < 0 or due > 365):
                raise ActionsError("invalid_action", f"action #{idx}: due_in_days 0..365")
        elif a_type == "notify":
            if not str(action.get("title_template") or "").strip():
                raise ActionsError("invalid_action", f"action #{idx}: title_template required")
            if not str(action.get("body_template") or "").strip():
                raise ActionsError("invalid_action", f"action #{idx}: body_template required")
            mode = action.get("recipient_mode")
            if mode not in _RECIPIENT_MODES:
                raise ActionsError("invalid_action", f"action #{idx}: bad recipient_mode")
            if mode == "user_id" and not action.get("user_id"):
                raise ActionsError("invalid_action", f"action #{idx}: user_id required")
            if mode == "role":
                roles = action.get("roles")
                if not isinstance(roles, list) or not roles:
                    raise ActionsError("invalid_action", f"action #{idx}: roles list required")
                unknown = [r for r in roles if str(r).lower() not in _KNOWN_ROLES]
                if unknown:
                    raise ActionsError("invalid_action", f"action #{idx}: unknown roles {unknown}")
        # webhook: параметров в срезе-1 нет


def render_template(template: str, payload: Mapping[str, Any], *, limit: int) -> str:
    def _sub(match: re.Match[str]) -> str:
        found, value = resolve_field(payload, match.group(1))
        if not found or value is None:
            return ""
        return str(value)

    return _TEMPLATE_RE.sub(_sub, template)[:limit]


def short_key(event_key: str) -> str:
    return hashlib.sha256(event_key.encode("utf-8")).hexdigest()[:16]


def describe_action(action: Mapping[str, Any]) -> str:
    """Человекочитаемое описание для dry-run (без исполнения)."""
    a_type = action.get("type")
    if a_type == "create_task":
        return f"создать задачу «{action.get('title_template', '')}»"
    if a_type == "notify":
        return (
            f"уведомление ({action.get('recipient_mode')}) «{action.get('title_template', '')}»"
        )
    if a_type == "webhook":
        return "отправить webhook rule.triggered"
    return str(a_type)


async def _was_already_triggered(
    session: AsyncSession, *, tenant_id: str, rule_id: str, event_key: str
) -> bool:
    stmt = (
        select(AutomationRuleTrigger.id)
        .where(
            AutomationRuleTrigger.tenant_id == tenant_id,
            AutomationRuleTrigger.rule_id == rule_id,
            AutomationRuleTrigger.event_key == event_key,
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def _resolve_recipients(
    session: AsyncSession,
    *,
    tenant_id: str,
    action: Mapping[str, Any],
    actor_id: str | None,
) -> list[str]:
    mode = action.get("recipient_mode")
    if mode == "actor":
        return [actor_id] if actor_id else []
    if mode == "user_id":
        user_id = action.get("user_id")
        return [str(user_id)] if user_id else []
    if mode == "role":
        roles = [str(r).lower() for r in action.get("roles", [])]
        users = (
            (
                await session.execute(
                    select(User).where(
                        User.tenant_id == tenant_id,
                        User.deleted_at.is_(None),
                        User.role.in_(roles),
                    )
                )
            )
            .scalars()
            .all()
        )
        return [str(u.id) for u in users]
    return []


async def execute_action(
    session: AsyncSession,
    *,
    tenant_id: str,
    rule: AutomationRule,
    action: Mapping[str, Any],
    event_key: str,
    payload: Mapping[str, Any],
    already_triggered: bool,
) -> ActionOutcome:
    a_type = str(action.get("type"))
    actor_id = payload.get("actor_id")

    if a_type == "create_task":
        if already_triggered:
            return ActionOutcome(type=a_type, outcome="deduped", detail="already triggered")
        from datetime import datetime, timedelta, timezone

        due_at = None
        if action.get("due_in_days") is not None:
            due_at = datetime.now(tz=timezone.utc) + timedelta(days=int(action["due_in_days"]))
        assignee_id = None
        if action.get("assignee_mode") == "actor":
            assignee_id = actor_id
        elif action.get("assignee_mode") == "user_id":
            assignee_id = action.get("user_id")
        task = Task(
            tenant_id=tenant_id,
            title=render_template(str(action["title_template"]), payload, limit=255)
            or f"Правило: {rule.name}"[:255],
            description=render_template(
                str(action.get("description_template") or ""), payload, limit=2000
            )
            or None,
            entity_type="automation_rule",
            entity_id=rule.id,
            due_at=due_at,
            assignee_id=assignee_id,
            priority=TaskPriority(str(action.get("priority", "medium"))),
            next_remind_at=await next_task_reminder(session, due_at=due_at),
        )
        session.add(task)
        await session.flush()
        return ActionOutcome(type=a_type, outcome="created", entity_ids=[str(task.id)])

    if a_type == "notify":
        from app.models.notifications import Notification

        recipients = await _resolve_recipients(
            session, tenant_id=tenant_id, action=action, actor_id=actor_id
        )
        if not recipients:
            return ActionOutcome(type=a_type, outcome="suppressed", detail="no recipients")
        title = render_template(str(action["title_template"]), payload, limit=255)
        body = render_template(str(action["body_template"]), payload, limit=2000)
        created: list[str] = []
        deduped = 0
        suppressed = 0
        for user_id in recipients:
            dedup_key = f"rules:{rule.id}:{short_key(event_key)}:{user_id}"
            # send_notification возвращает СУЩЕСТВУЮЩУЮ строку при dedup-хите — чтобы
            # различить created/deduped детерминированно, проверяем ключ заранее.
            existing = (
                await session.execute(
                    select(Notification.id)
                    .where(
                        Notification.dedup_key == dedup_key,
                        Notification.deleted_at.is_(None),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if existing is not None:
                deduped += 1
                continue
            notification = await send_notification(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                channel=NotificationChannel.INAPP,
                type=NotificationType.AUTOMATION_RULE,
                title=title or f"Правило: {rule.name}"[:255],
                body=body or title or rule.name,
                payload={"rule_id": rule.id, "event_key": event_key},
                dedup_key=dedup_key,
                priority=NotificationPriority(str(action.get("priority", "medium"))),
            )
            if notification is None:  # opt-out канала пользователем
                suppressed += 1
            else:
                created.append(str(notification.id))
        outcome = "created" if created else ("deduped" if deduped else "suppressed")
        detail = f"created={len(created)} deduped={deduped} suppressed={suppressed}"
        return ActionOutcome(type=a_type, outcome=outcome, detail=detail, entity_ids=created)

    if a_type == "webhook":
        from app.services.outbox import OutboxService

        entries = await OutboxService(session).enqueue(
            tenant_id=tenant_id,
            event_type="rule.triggered",
            payload={
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "rule_id": rule.id,
                "rule_name": rule.name,
                "source_event_type": rule.event_type,
                "source_event_key": event_key,
                "source_payload": dict(payload),
            },
            idempotency_key=f"rule-triggered:{rule.id}:{short_key(event_key)}",
        )
        return ActionOutcome(
            type=a_type, outcome="created", entity_ids=[str(e.id) for e in entries]
        )

    return ActionOutcome(type=a_type, outcome="error", detail=f"unknown action {a_type!r}")
```

**Примечание к notify-дедупу:** пре-чек по `dedup_key` ДО `send_notification` (как в коде выше) — осознанный: `send_notification` возвращает существующую строку при dedup-хите, и постфактум отличить created от deduped нельзя без лишнего SELECT. Индекс `ix_notifications_dedup_active` глобальный (не tenant-scoped) — наш ключ содержит tenant-зависимый `short_key(event_key)` + `rule.id`, коллизий между тенантами нет.

- [ ] **Step 2: Тесты действий**

`tests/api/test_rules_engine_actions.py` (async, sessionmaker + data_factory; смотреть фикстуры соседних тестов):

Кейсы:
1. `create_task` создаёт Task с `entity_type="automation_rule"`, `entity_id=rule.id`, due_at≈now+N дней, priority, assignee по режимам (`none`→None, `actor`→payload.actor_id, `user_id`→указанный), title из шаблона `{severity}`.
2. `create_task` при `already_triggered=True` → `deduped`, Task не создан.
3. `notify` mode=user_id: первая отправка → `created` + строка Notification с dedup_key `rules:{rule_id}:{hash}:{user_id}` и type=AUTOMATION_RULE; повторный вызов с тем же event_key → `deduped`, вторая строка не создаётся.
4. `notify` mode=role: два пользователя с ролью admin у tenant'а → 2 получателя; mode=actor без actor_id → `suppressed`.
5. `webhook` → outbox-строка с event_type `rule.triggered`, payload содержит rule_id/source_event_type/source_payload; idempotency_key = `rule-triggered:{rule_id}:{hash}`.
6. `validate_actions`: пустой список → `invalid_actions`; >10 → `too_many_actions`; незнакомый тип → `invalid_action_type`; notify без body → `invalid_action`; role с неизвестной ролью → `invalid_action`.
7. `render_template`: `{severity}` подставляется, `{missing}` → пустая строка, `{before.level}` — dot-путь, обрезка по limit.

Каркас (дописать все кейсы по образцу):

```python
"""Unit/integration: исполнители действий правил."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.notifications import Notification
from app.models.obligations import Task
from app.models.outbox import Outbox  # если модуль другой — найти класс Outbox по grep
from app.models.rules_engine import AutomationRule
from app.modules.rules_engine.actions import (
    ActionsError,
    execute_action,
    render_template,
    validate_actions,
)


async def _make_rule(session, tenant_id: str, **overrides) -> AutomationRule:
    rule = AutomationRule(
        tenant_id=tenant_id,
        name=overrides.pop("name", "Правило-тест"),
        event_type="IncidentCreated",
        conditions_json={},
        actions_json=[],
        **overrides,
    )
    session.add(rule)
    await session.flush()
    return rule


PAYLOAD = {
    "tenant_id": "-",  # заменить на настоящий tenant_id в тесте
    "actor_id": None,
    "severity": "critical",
    "incident_id": "inc-1",
}


@pytest.mark.asyncio
async def test_create_task_outcome_created(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tenant_id = str(tenant.id)
        rule = await _make_rule(session, tenant_id)
        outcome = await execute_action(
            session,
            tenant_id=tenant_id,
            rule=rule,
            action={
                "type": "create_task",
                "title_template": "Инцидент {severity}",
                "priority": "high",
                "due_in_days": 3,
                "assignee_mode": "none",
            },
            event_key="inc-1",
            payload={**PAYLOAD, "tenant_id": tenant_id},
            already_triggered=False,
        )
        await session.commit()
        assert outcome.outcome == "created"
        task = (
            await session.execute(
                select(Task).where(Task.tenant_id == tenant_id, Task.entity_id == rule.id)
            )
        ).scalar_one()
        assert task.title == "Инцидент critical"
        assert task.entity_type == "automation_rule"
```

(остальные кейсы — по списку выше; проверить реальный модуль модели Outbox: `Get-ChildItem backend/app/models | Select-String -Pattern "class Outbox"` или grep.)

- [ ] **Step 3: Прогнать + линт + commit**

```bash
git add backend/app/modules/rules_engine/actions.py tests/api/test_rules_engine_actions.py
git commit -m "feat(rules): action executors create_task/notify/webhook (P10-10)"
```

---

### Task 5: Движок (`engine.py`) + hook в `OutboxService.enqueue`

**Files:**
- Create: `backend/app/modules/rules_engine/engine.py`
- Modify: `backend/app/services/outbox.py` (метод `enqueue`)
- Test: `tests/api/test_rules_engine_engine.py`

- [ ] **Step 1: Движок**

`backend/app/modules/rules_engine/engine.py`:

```python
"""Оркестрация движка правил: вызывается синхронно из OutboxService.enqueue.

Инварианты:
- ЛЮБАЯ ошибка движка изолируется (evaluate_event_safe) — исходная транзакция
  доменного события не страдает;
- события ``rule.triggered`` не оцениваются (guard от каскада, глубина = 1);
- лог пишется только при матче условий (или при ошибке действий/оценки);
- всё flush-only, транзакцию владеет вызывающий.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.feature_flags import is_feature_enabled
from app.models.rules_engine import AutomationRule, AutomationRuleTrigger, RuleTriggerStatus
from app.modules.rules_engine import actions as actions_mod
from app.modules.rules_engine import conditions as conditions_mod

logger = logging.getLogger(__name__)

FEATURE_CODE = "rules_engine"
RULE_TRIGGERED_EVENT = "rule.triggered"


async def evaluate_event_safe(
    session: AsyncSession,
    *,
    tenant_id: str,
    event_type: str,
    payload: Mapping[str, Any],
    event_key: str,
) -> None:
    try:
        await _evaluate_event(
            session,
            tenant_id=tenant_id,
            event_type=event_type,
            payload=payload,
            event_key=event_key,
        )
    except Exception:  # noqa: BLE001 — изоляция движка от доменной транзакции
        logger.exception(
            "rules_engine.evaluate_failed",
            extra={"tenant_id": tenant_id, "event_type": event_type},
        )


async def _evaluate_event(
    session: AsyncSession,
    *,
    tenant_id: str,
    event_type: str,
    payload: Mapping[str, Any],
    event_key: str,
) -> None:
    if event_type == RULE_TRIGGERED_EVENT:
        return
    if not await is_feature_enabled(session, tenant_id, FEATURE_CODE, default=False):
        return
    rules = (
        (
            await session.execute(
                select(AutomationRule)
                .where(
                    AutomationRule.tenant_id == tenant_id,
                    AutomationRule.event_type == event_type,
                    AutomationRule.is_enabled.is_(True),
                    AutomationRule.deleted_at.is_(None),
                )
                .order_by(AutomationRule.priority.asc(), AutomationRule.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    for rule in rules:
        await _fire_rule(
            session, tenant_id=tenant_id, rule=rule, payload=payload, event_key=event_key
        )


async def _fire_rule(
    session: AsyncSession,
    *,
    tenant_id: str,
    rule: AutomationRule,
    payload: Mapping[str, Any],
    event_key: str,
) -> None:
    try:
        matched = conditions_mod.evaluate(rule.conditions_json, payload)
    except Exception:  # noqa: BLE001
        logger.exception("rules_engine.condition_failed", extra={"rule_id": rule.id})
        await _write_trigger(
            session, tenant_id=tenant_id, rule=rule, event_key=event_key, payload=payload,
            status=RuleTriggerStatus.ERROR,
            results=[{"type": "conditions", "outcome": "error", "detail": "evaluation failed"}],
        )
        return
    if not matched:
        return

    already = await actions_mod._was_already_triggered(
        session, tenant_id=tenant_id, rule_id=rule.id, event_key=event_key
    )
    results: list[dict[str, Any]] = []
    errors = 0
    for action in rule.actions_json or []:
        try:
            outcome = await actions_mod.execute_action(
                session,
                tenant_id=tenant_id,
                rule=rule,
                action=action,
                event_key=event_key,
                payload=payload,
                already_triggered=already,
            )
        except Exception as exc:  # noqa: BLE001 — одно действие не роняет остальные
            logger.exception(
                "rules_engine.action_failed",
                extra={"rule_id": rule.id, "action_type": action.get("type")},
            )
            outcome = actions_mod.ActionOutcome(
                type=str(action.get("type")), outcome="error", detail=exc.__class__.__name__
            )
        if outcome.outcome == "error":
            errors += 1
        results.append(outcome.as_dict())

    if errors == 0:
        status = RuleTriggerStatus.SUCCESS
    elif errors == len(results) and results:
        status = RuleTriggerStatus.ERROR
    else:
        status = RuleTriggerStatus.PARTIAL
    await _write_trigger(
        session, tenant_id=tenant_id, rule=rule, event_key=event_key, payload=payload,
        status=status, results=results,
    )


async def _write_trigger(
    session: AsyncSession,
    *,
    tenant_id: str,
    rule: AutomationRule,
    event_key: str,
    payload: Mapping[str, Any],
    status: RuleTriggerStatus,
    results: list[dict[str, Any]],
) -> None:
    session.add(
        AutomationRuleTrigger(
            tenant_id=tenant_id,
            rule_id=rule.id,
            event_type=rule.event_type,
            event_key=event_key[:255],
            correlation_id=(str(payload.get("correlation_id"))[:128] if payload.get("correlation_id") else None),
            event_payload=dict(payload),
            status=status,
            actions_result=results,
        )
    )
    await session.flush()
```

- [ ] **Step 2: Hook в enqueue**

В `backend/app/services/outbox.py`, метод `enqueue`:

1. Завести счётчик новых строк. В начале try-блока (после `created: list[Outbox] = []`) добавить `new_entries = 0`.
2. В noop-ветке после `created.append(entry)` (создание новой noop-строки, ~строка 190) добавить `new_entries += 1`.
3. В основной ветке после `created.append(entry)` (~строка 224) добавить `new_entries += 1`.
4. После блока `if created:` с метриками (~строка 250) и ПЕРЕД финальным `record_pipeline_stage_end(... SUCCESS ...)` вставить:

```python
        if new_entries and resolved.value != "rule.triggered" and key:
            # P10-10: синхронная оценка правил автоматизации (той же транзакцией).
            # Только для НОВЫХ логических событий (dedup-реплей не перезапускает правила);
            # события самого движка (rule.triggered) не оцениваются — guard от каскада.
            from app.modules.rules_engine.engine import evaluate_event_safe

            await evaluate_event_safe(
                self.session,
                tenant_id=tenant_id,
                event_type=resolved.value,
                payload=normalized_payload,
                event_key=key,
            )
```

(Lazy-import обязателен: `actions.py` импортирует `OutboxService` — цикл на module-level.)

- [ ] **Step 3: Интеграционные тесты**

`tests/api/test_rules_engine_engine.py`. Хелперы: `_enable_flag` — скопировать из `tests/api/test_report_builder_api.py` c кодом `rules_engine`; enqueue делать через `OutboxService(session).enqueue(tenant_id=..., event_type="IncidentCreated", payload={...})` с валидным IncidentCreatedPayload (`incident_id/company_id/site_id/status/severity/incident_type` — см. events.py).

Кейсы:
1. **happy-path**: флаг on + правило (severity in [high,critical], действия create_task+notify user_id) → enqueue INCIDENT_CREATED(severity=critical) → Task создан + Notification создана + 1 строка AutomationRuleTrigger со status=success, event_key=idempotency-key события, actions_result из 2 элементов.
2. **не-матч** → нет строк лога, нет Task.
3. **флаг off** → нет строк лога.
4. **приоритет**: два правила (priority 1 и 2) на одно событие → строки лога в порядке priority (проверить по rule_id обеих строк; порядок вставки == порядок created_at/id).
5. **replay**: повторный enqueue с тем же `idempotency_key` → `_find_existing` вернёт строку, new_entries==0 → вторая строка лога НЕ появляется.
6. **изоляция ошибки**: правило с действием, у которого битый конфиг, не прошедший бы validate (положить руками `actions_json=[{"type": "create_task"}]` без title — execute_action упадёт на KeyError) → enqueue проходит успешно (исходное событие создано), строка лога status=error.
7. **guard каскада**: правило на webhook → срабатывание создаёт outbox `rule.triggered`; правило, руками созданное с event_type="rule.triggered", НЕ срабатывает (лога нет).
8. **выключенное правило** (`is_enabled=False`) не срабатывает.

- [ ] **Step 4: Прогнать + смежный регресс outbox + commit**

```powershell
$env:PYTHONPATH="backend"
& "...\.venv\Scripts\python.exe" -m pytest "tests/api/test_rules_engine_engine.py" -v --timeout=600
# найти и прогнать существующие тесты outbox (не сломали enqueue):
# Get-ChildItem tests -Recurse | Select-String -List "OutboxService" | Select-Object -First 5 Path
```

```bash
git add backend/app/modules/rules_engine/engine.py backend/app/services/outbox.py tests/api/test_rules_engine_engine.py
git commit -m "feat(rules): rule engine + sync hook in OutboxService.enqueue (P10-10)"
```

---

### Task 6: API (`schemas.py`, `service.py`, `api.py`) + регистрация

**Files:**
- Create: `backend/app/modules/rules_engine/schemas.py`
- Create: `backend/app/modules/rules_engine/service.py`
- Create: `backend/app/modules/rules_engine/api.py`
- Modify: `backend/app/api/v1/route_groups.py`
- Test: `tests/api/test_rules_engine_api.py`

**Образец для ВСЕХ трёх файлов — `backend/app/modules/report_builder/{schemas,service,api}.py`** (прочитать перед реализацией; зеркалить стиль: SessionDep/TenantDep, `_tenant_resource_id`, FeatureGate, ETag на списке, audit, коды ошибок через `api_problem_detail`).

- [ ] **Step 1: Схемы**

`schemas.py` (pydantic v2, `from __future__ import annotations`):

```python
class RuleActionDTO — свободный dict (валидация в actions.validate_actions), т.е. actions: list[dict]
class AutomationRuleBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    event_type: str
    conditions_json: dict = Field(default_factory=dict)
    actions_json: list[dict] = Field(default_factory=list)
    priority: int = Field(default=100, ge=0, le=10000)
    is_enabled: bool = True

class AutomationRuleCreate(AutomationRuleBase): ...
class AutomationRuleUpdate(BaseModel): все поля Optional (exclude_unset-патч)
class AutomationRuleRead(AutomationRuleBase): id, created_at, updated_at (model_config from_attributes)
class AutomationRulePage: items/total/limit/offset
class EventFieldMeta: name, kind
class EventTypeMeta: event_type, fields: list[EventFieldMeta]
class EventTypePage: items, total
class DryRunIn: rule: AutomationRuleBase; event: {event_type: str, payload: dict}
class ConditionResult: field, op, value(Any), actual(Any|None), matched(bool)
class DryRunOut: matched: bool; condition_results: list[ConditionResult]; would_actions: list[str]
class RuleTestIn: limit: int = Field(default=20, ge=1, le=50)
class RuleTestResultItem: event_key, occurred_at: str|None, matched: bool
class RuleTestOut: events_checked, matched_count, results
class TriggerRead: id, rule_id, event_type, event_key, status, actions_result, created_at, correlation_id
class TriggerPage: items/total/limit/offset
```

- [ ] **Step 2: Сервис**

`service.py` — класс `RulesEngineService(session, tenant_id)`:

- `list_rules(limit, offset)` → (rows, total), сортировка `priority.asc(), created_at.asc()`, фильтр `deleted_at.is_(None)`.
- `get_rule(rule_id)` → строка или raise `RuleNotFound` (typed exception, как ReportDefinitionNotFound).
- `create_rule(data: AutomationRuleCreate)`:
  - `event_type` ∈ `catalog.known_event_types()` иначе `RulesConfigError("unknown_event_type", ...)`;
  - `conditions_mod.validate_conditions(data.conditions_json, known_fields=catalog.known_fields_for(data.event_type))`;
  - `actions_mod.validate_actions(data.actions_json)`;
  - конфликт имени: SELECT по (tenant_id, name) без фильтра deleted_at → `RuleNameConflict`;
  - INSERT + flush; IntegrityError → `RuleNameConflict` (гонка).
- `update_rule(rule_id, patch)`: та же валидация для изменённых полей (при смене event_type — превалидировать условия против нового каталога); конфликт имени при переименовании.
- `delete_rule(rule_id)`: soft-delete (`deleted_at = now`).
- `dry_run(body: DryRunIn)`: validate event_type+conditions+actions (те же коды); `payload` берётся как есть (без pydantic-нормализации — dry-run работает по сырому образцу); посчитать per-condition `ConditionResult` (использовать `conditions_mod.evaluate_condition` + `resolve_field` для `actual`), `matched` по match-режиму, `would_actions = [actions_mod.describe_action(a) for a in actions]` (только при matched — иначе пустой список).
- `test_rule(rule_id, limit)`: SELECT Outbox-строк `(tenant_id, event_type == rule.event_type)` order by `created_at.desc()` limit `limit*5`; в Python дедуп по `idempotency_key` (None-ключи не дедупить), взять первые `limit` уникальных; для каждой — `evaluate(rule.conditions_json, row.payload)`; `occurred_at = row.payload.get("occurred_at")`. Вернуть RuleTestOut.
- `list_triggers(rule_id | None, limit, offset)` → (rows, total), `created_at.desc()`.

- [ ] **Step 3: Роутер**

`api.py` — `router = APIRouter(prefix="/rules", tags=["rules-engine"])`; `_READ_ROLES = _WRITE_ROLES = ["admin", "owner"]`; `Access = Annotated[AccessContext, Depends(abac(_tenant_resource_id, required_roles=["admin", "owner"], action="manage automation rules"))]`; FeatureGate по образцу report_builder c кодом/сообщением:

```python
_FEATURE_CODE = "rules_engine"
# message ОБЯЗАН содержать подстроку "feature is not enabled" — фронтовый
# isFeatureDisabledError матчит её регэкспом (прецедент contractors).
message="Rules engine feature is not enabled for this tenant",
code="RULES_ENGINE_DISABLED", error_type="rules_engine"
```

Эндпоинты (все с `dependencies=[FeatureGate]`, у всех Access-параметр):
- `GET /rules/event-types` → EventTypePage из `catalog.event_catalog()`.
- `GET /rules` → AutomationRulePage + ETag/304 (зеркалить list_definitions из report_builder: compute_list_etag + build_not_modified_headers + apply_etag_response_headers).
- `POST /rules` → 201 AutomationRuleRead; `RuleNameConflict` → 409, `RulesConfigError/ConditionsError/ActionsError` → 422 `api_problem_detail(code=exc.code, ...)`; audit action="create".
- `GET /rules/{rule_id}` → 200/404.
- `PATCH /rules/{rule_id}` → 200; те же коды ошибок; audit action="update".
- `DELETE /rules/{rule_id}` → 204; audit action="delete".
- `POST /rules/dry-run` → DryRunOut (200; 422 на битый конфиг).
- `POST /rules/{rule_id}/test` → RuleTestOut.
- `GET /rules/triggers` (query: rule_id?, limit=50 ≤200, offset=0) → TriggerPage. **Внимание к порядку роутов:** объявить `/rules/triggers` и `/rules/event-types` и `/rules/dry-run` ДО `/rules/{rule_id}` — иначе FastAPI сматчит их как rule_id.

Регистрация: в `backend/app/api/v1/route_groups.py` — импорт `from app.modules.rules_engine.api import router as rules_engine_router` рядом с report_builder (~строка 84) и `(rules_engine_router, {"tags": ["rules-engine"]})` в тот же кортеж, где `(report_builder_router, ...)` (~строка 186).

- [ ] **Step 4: API-тесты**

`tests/api/test_rules_engine_api.py` (образец: `tests/api/test_report_builder_api.py`, включая `_enable_flag` c кодом `rules_engine`):

```python
RULE = {
    "name": "Критичные инциденты",
    "event_type": "IncidentCreated",
    "conditions_json": {"match": "all", "conditions": [
        {"field": "severity", "op": "in", "value": ["high", "critical"]}
    ]},
    "actions_json": [{"type": "notify", "recipient_mode": "role", "roles": ["admin"],
                      "title_template": "Инцидент {severity}", "body_template": "Тип: {incident_type}"}],
    "priority": 10,
}
```

Кейсы:
1. `test_flag_off_404` — GET /rules без FeatureEnablement → 404.
2. `test_rbac` — WORKER → 403 на GET и POST; ADMIN → 200/201. (auditor_ro при наличии в RoleEnum — тоже 403.)
3. `test_crud_flow`: POST 201 → дубль имени 409 → POST с `event_type="NoSuchEvent"` 422 (`unknown_event_type` в detail.code) → POST с битым op 422 → GET list total=1 + ETag/304 → PATCH description/priority 200 → PATCH `is_enabled=false` 200 → DELETE 204 → GET {id} 404.
4. `test_event_types_catalog`: GET /rules/event-types → 200, есть IncidentCreated с полем severity, НЕТ rule.triggered.
5. `test_dry_run`: matched-кейс (payload severity=critical) → matched=true, condition_results[0].matched=true, would_actions непуст; не-матч → matched=false, would_actions=[].
6. `test_rule_test_by_history`: включить флаг, создать правило, enqueue 3 события INCIDENT_CREATED (2 critical, 1 low, разные idempotency_key) → POST /rules/{id}/test → events_checked=3, matched_count=2.
7. `test_triggers_journal`: после enqueue матчащего события GET /rules/triggers → total>=1, фильтр rule_id работает, status=success.

- [ ] **Step 5: Прогнать + линт + commit**

```powershell
$env:PYTHONPATH="backend"
& "...\.venv\Scripts\python.exe" -m pytest "tests/api/test_rules_engine_api.py" -v --timeout=600
```

```bash
git add backend/app/modules/rules_engine/schemas.py backend/app/modules/rules_engine/service.py backend/app/modules/rules_engine/api.py backend/app/api/v1/route_groups.py tests/api/test_rules_engine_api.py
git commit -m "feat(rules): rules CRUD/dry-run/test/triggers API (P10-10)"
```

---

### Task 7: Demo-сид

**Files:**
- Modify: `backend/app/services/demo_bootstrap.py`
- Test: `tests/test_rules_engine_seed.py`

- [ ] **Step 1: Сидер**

По образцу `_seed_report_builder_demo` (`demo_bootstrap.py:823-847`) написать `_seed_rules_engine_demo(session, tenant_id)`:

1. find-or-create `Feature(code="rules_engine", title="Правила автоматизации")` + flush;
2. find-or-create `FeatureEnablement(tenant_id, feature_id, on=True)`;
3. bail-out если уже есть AutomationRule с name первого правила; иначе создать 2 правила:

```python
AutomationRule(
    tenant_id=tenant_id,
    name="Критичный инцидент — задача и уведомление",
    description="Демо: при инциденте high/critical создать задачу и уведомить администраторов",
    event_type="IncidentCreated",
    conditions_json={"match": "all", "conditions": [
        {"field": "severity", "op": "in", "value": ["high", "critical"]},
    ]},
    actions_json=[
        {"type": "create_task", "title_template": "Разобрать инцидент ({severity})",
         "priority": "high", "due_in_days": 3, "assignee_mode": "none"},
        {"type": "notify", "recipient_mode": "role", "roles": ["admin"],
         "title_template": "Критичный инцидент", "body_template": "Тип: {incident_type}, серьёзность: {severity}"},
    ],
    priority=10,
),
AutomationRule(
    tenant_id=tenant_id,
    name="Истекающий документ подрядчика — уведомление",
    description="Демо: уведомить администраторов об истекающем документе подрядчика",
    event_type="contractor.document_expiring",
    conditions_json={},
    actions_json=[
        {"type": "notify", "recipient_mode": "role", "roles": ["admin"],
         "title_template": "Истекает документ подрядчика", "body_template": "Проверьте раздел подрядчиков"}],
    priority=100,
),
```

4. Вызвать из `bootstrap_demo_tenant` рядом с `_seed_report_builder_demo` (~строка 1259), той же сигнатурой, что соседние сидеры.

- [ ] **Step 2: Тест сида** — образец `tests/test_report_builder_seed.py` (прочитать; та же структура): прогнать сидер дважды → идемпотентно (2 правила, 1 Feature, 1 Enablement); флаг включён.

- [ ] **Step 3: Прогнать + commit**

```bash
git add backend/app/services/demo_bootstrap.py tests/test_rules_engine_seed.py
git commit -m "feat(rules): demo seed — flag + 2 sample rules (P10-10)"
```

---

### Task 8: Backend-гейты (контроллер)

**Files:** только артефакты гейтов (baseline).

- [ ] **Step 1: Линт всего диффа**: `ruff check` + `black --check` по всем изменённым backend-файлам.
- [ ] **Step 2: Батч-регресс** (PowerShell, по ≤5 файлов, timeout 600000):
  - батч A: `tests/api/test_rules_engine_model.py tests/api/test_rules_engine_conditions.py tests/api/test_rules_engine_catalog.py tests/api/test_rules_engine_actions.py`
  - батч B: `tests/api/test_rules_engine_engine.py tests/api/test_rules_engine_api.py tests/test_rules_engine_seed.py`
  - батч C (смежные): тесты outbox/events (найти по grep `OutboxService`), `tests/test_report_builder_seed.py`, тесты notifications (grep `send_notification` в tests), demo_bootstrap-тесты.
- [ ] **Step 3: OpenAPI baseline**: пере-снять снапшот тем же способом, что в прошлых волнах:
```powershell
$env:PYTHONPATH="backend"; $env:SECRET_KEY="x"; $env:S3_ACCESS_KEY="x"; $env:S3_SECRET_KEY="x"; $env:S3_BUCKET="x"
& "...\.venv\Scripts\python.exe" scripts/ci/check_openapi_snapshot.py --update   # либо режим из скрипта: прочитать --help
git diff --stat docs/stabilization/openapi_routes_baseline.json   # ожидание: только добавления (+9 операций /rules/*)
```
  Затем прогнать компаратор без --update → `✓ ARCH-4 unchanged`/`OK`.
- [ ] **Step 4: PG16-гейт** (нужен Docker): `& "...\.venv\Scripts\python.exe" scripts/ci/local_gate.py --db-only` — round-trip `re01` (enum ruletriggerstatus + ALTER TYPE notificationtype). Если Docker недоступен — зафиксировать в handoff как «отложено на CI», НЕ блокировать волну.
- [ ] **Step 5: Commit артефактов**: `git add docs/stabilization/openapi_routes_baseline.json && git commit -m "chore(openapi): baseline +rules-engine routes (P10-10)"`.

---

### Task 9: Frontend — API-клиент + DTO + vocab

**Files:**
- Create: `frontend/src/types/dto/rules.ts`
- Create: `frontend/src/api/rules.ts`
- Create: `frontend/src/pages/rules/rulesVocab.ts`
- Test: `frontend/src/api/rules.test.ts`

Образцы: `frontend/src/api/reportBuilder.ts` (+его тест), `frontend/src/api/contractors.ts:31` (isFeatureDisabledError).

- [ ] **Step 1: DTO** `types/dto/rules.ts`: зеркало схем Task 6 (`AutomationRuleRead/Create/Update`, `AutomationRulePage`, `EventTypeMeta/EventFieldMeta/EventTypePage`, `RuleCondition {field, op, value}`, `DryRunIn/DryRunOut/ConditionResult`, `RuleTestOut/RuleTestResultItem`, `TriggerRead/TriggerPage`, union-типы `RuleConditionOp`, `RuleActionType`, `TriggerStatus = "success"|"partial"|"error"`, `RuleAction = { type: RuleActionType } & Record<string, unknown>`).

- [ ] **Step 2: API-модуль** `api/rules.ts`:

```typescript
import { apiClient } from "./client";
import type { ... } from "../types/dto/rules";

const BASE = "/rules";

export const isFeatureDisabledError = (error: unknown): boolean => {
  const e = error as { status?: number; message?: string };
  return e?.status === 404 && /feature is not enabled/i.test(e?.message ?? "");
};

export const rulesApi = {
  async eventTypes(): Promise<EventTypePage> { return (await apiClient.get<EventTypePage>(`${BASE}/event-types`)).data; },
  async list(params: { limit?: number; offset?: number } = {}): Promise<AutomationRulePage> {
    return (await apiClient.get<AutomationRulePage>(BASE, { params: { limit: 100, offset: 0, ...params } })).data;
  },
  async create(body: AutomationRuleCreate): Promise<AutomationRuleRead> { return (await apiClient.post<AutomationRuleRead>(BASE, body)).data; },
  async get(id: string): Promise<AutomationRuleRead> { return (await apiClient.get<AutomationRuleRead>(`${BASE}/${id}`)).data; },
  async update(id: string, body: AutomationRuleUpdate): Promise<AutomationRuleRead> { return (await apiClient.patch<AutomationRuleRead>(`${BASE}/${id}`, body)).data; },
  async remove(id: string): Promise<void> { await apiClient.delete(`${BASE}/${id}`); },
  async dryRun(body: DryRunIn): Promise<DryRunOut> { return (await apiClient.post<DryRunOut>(`${BASE}/dry-run`, body)).data; },
  async test(id: string, body: { limit?: number } = {}): Promise<RuleTestOut> { return (await apiClient.post<RuleTestOut>(`${BASE}/${id}/test`, body)).data; },
  async triggers(params: { rule_id?: string; limit?: number; offset?: number } = {}): Promise<TriggerPage> {
    return (await apiClient.get<TriggerPage>(`${BASE}/triggers`, { params: { limit: 50, offset: 0, ...params } })).data;
  },
};
```

- [ ] **Step 3: Vocab** `pages/rules/rulesVocab.ts`: `OP_LABELS` (eq «равно», ne «не равно», in «одно из», not_in «не из», gt/gte/lt/lte «больше»/«не меньше»/«меньше»/«не больше», contains «содержит», exists «заполнено»); `ACTION_LABELS` (create_task «Создать задачу», notify «Уведомление», webhook «Webhook»); `STATUS_LABELS` (success «Успех», partial «Частично», error «Ошибка»); `OUTCOME_LABELS` (created «создано», deduped «дубль», suppressed «подавлено», error «ошибка»); `EVENT_LABELS: Record<string,string>` — RU-подписи хотя бы для: IncidentCreated «Создан инцидент», InspectionCreated «Создана проверка», TrainingCompleted «Обучение завершено», TrainingAssigned «Обучение назначено», PPEIssued «Выдано СИЗ», PPEReplacementDue «Замена СИЗ», MedicalExamRecorded «Медосмотр внесён», PersonSuspended «Отстранение», PrescriptionOverdue «Просрочено предписание», DocumentSigned «Документ подписан», TaskOverdue «Задача просрочена», TaskDueSoon «Задача скоро», contractor.document_expiring «Истекает документ подрядчика», contractor.readiness_blocked «Подрядчик не готов»; хелпер `eventLabel(code) => EVENT_LABELS[code] ?? code`.

- [ ] **Step 4: Тесты** `api/rules.test.ts` (образец соседний `api/committees.test.ts` или `api/contractors.test.ts` — vi.mock apiClient): list передаёт дефолтные params; create POST на /rules; dryRun POST /rules/dry-run; isFeatureDisabledError: 404+"feature is not enabled" → true; 404 иное сообщение → false; 403 → false.

- [ ] **Step 5: Прогнать + commit**

```powershell
Set-Location frontend; npx vitest run src/api/rules.test.ts
```

```bash
git add frontend/src/types/dto/rules.ts frontend/src/api/rules.ts frontend/src/pages/rules/rulesVocab.ts frontend/src/api/rules.test.ts
git commit -m "feat(rules): typed rules api client + vocab (P10-10)"
```

---

### Task 10: Frontend — RulesPage + проводка

**Files:**
- Create: `frontend/src/pages/rules/RulesPage.tsx`
- Create: `frontend/src/features/rules/RuleFormDialog.tsx`
- Create: `frontend/src/features/rules/DryRunPanel.tsx`
- Create: `frontend/src/features/rules/TriggerLogPanel.tsx`
- Modify: `frontend/src/permissions/permissions.ts` (+RULES_VIEW/RULES_MANAGE)
- Modify: `frontend/src/router/pageRegistry.tsx`, `frontend/src/router/routeGroups.tsx`, `frontend/src/router/navigationConfig.ts`, `frontend/src/router/navVisibility.ts`
- Test: `frontend/src/pages/rules/RulesPage.test.tsx`

Образцы: `pages/reports/ReportBuilderPage.tsx` (конструктор фильтров/discriminated union), `pages/contractors/ContractorsPage.tsx` (useAsyncResource+RegistryTable+EmptyState), `features/contractors/ContractorFormDialog.tsx` (Radix Dialog c DialogDescription!).

- [ ] **Step 1: Права** — в `permissions/permissions.ts` добавить `RULES_VIEW: "rules.view"`, `RULES_MANAGE: "rules.manage"` (в ROLE_PERMISSIONS НЕ добавлять никому явно: backend-гейт admin/owner, а owner/admin на фронте получают через ALL_PERMISSIONS).

- [ ] **Step 2: Страница** `pages/rules/RulesPage.tsx` (default export):
  - Заголовок RegistryPageHeader «Правила автоматизации» + описание + кнопка «Новое правило» (`<Can permission={PERMISSIONS.RULES_MANAGE}>`).
  - Данные: `useAsyncResource` × 3 (rules list, eventTypes catalog, triggers) — loader'ы в `useCallback`.
  - Feature-off: если у ЛЮБОГО загрузчика `isFeatureDisabledError(error)` → `<EmptyState title="Функция недоступна" description="Правила автоматизации не включены для этого тенанта." />` на всю страницу (ранний return, паттерн ContractorExpiringTab).
  - Таблица правил: колонки Имя / Событие (`eventLabel`) / Условий (count) / Действия (бейджи ACTION_LABELS) / Приоритет / Вкл (Switch → `rulesApi.update(id, {is_enabled})` + reload + toast) / кнопки «Изменить» (диалог), «Тест» (POST test → диалог/inline-результат `matched_count/events_checked`), «Удалить» (confirm → remove → reload).
  - Секция Dry-run (`DryRunPanel`), секция журнала (`TriggerLogPanel`).
- [ ] **Step 3: Диалог формы** `features/rules/RuleFormDialog.tsx` (`{trigger, eventTypes, initialData?, onSubmitted}`): controlled Radix Dialog + **DialogDescription** (a11y!); поля: имя, описание, селект события (RU-лейбл + код), приоритет (number), список условий (строки: field-селект из полей выбранного события / op-селект OP_LABELS / value-инпут; для in/not_in — значения через запятую → split/trim; кнопки добавить/удалить строку; смена события сбрасывает условия), список действий (карточка на действие: тип-селект; для create_task — title_template/priority/due_in_days/assignee_mode(+user_id); для notify — recipient_mode(+user_id/roles-чекбоксы admin/owner/ot_specialist/line_manager/hr)+title/body; для webhook — подсказка «отправит rule.triggered»); submit → create/update, 409 → toast «Имя занято», 422 → toast с detail.message; onSubmitted → reload.
- [ ] **Step 4: DryRunPanel** (`{eventTypes}`): селект события → textarea JSON payload (при выборе события — автозаполнить объектом-заготовкой `{поле: null}` из каталога) → выбор правила из списка ИЛИ инлайн-конфиг текущей формы? — в срезе-1: селект существующего правила + кнопка «Проверить» → собрать DryRunIn из выбранного правила (rule fields) + события → `rulesApi.dryRun` → вывод: bedge matched, таблица condition_results (field/op/ожидание/факт/матч), список would_actions. JSON-парс ошибки → inline error.
- [ ] **Step 5: TriggerLogPanel**: фильтр-селект по правилу → `rulesApi.triggers({rule_id})`; таблица: Время (`new Date(created_at).toLocaleString("ru")`), Правило (имя по rule_id из списка), Событие, Статус (badge STATUS_LABELS), Результаты (компакт: `type:outcome` бейджи из actions_result); кнопка «Обновить».
- [ ] **Step 6: Проводка**: `pageRegistry.tsx` — lazy `RulesPage`; `routeGroups.tsx` — группа `{permission: PERMISSIONS.RULES_VIEW, routes: [<Route path="/rules" .../>]}`; `navigationConfig.ts` — пункт `{label: "Правила автоматизации", to: "/rules", icon: <подобрать lucide, напр. Zap или Workflow>, permission: PERMISSIONS.RULES_VIEW}` в группу администрирования/настроек (найти группу, где живут «Комитеты»/«Конструктор отчётов» — положить рядом); `navVisibility.ts` — по образцу committees: `if (item.to === "/rules" && featureFlags.rules_engine === false) return false;` (проверить точный синтаксис соседних строк).
- [ ] **Step 7: Тесты** `pages/rules/RulesPage.test.tsx` (образец ReportBuilderPage.test.tsx; vi.mock rulesApi через `vi.hoisted`): (1) рендер списка правил + названий событий по-русски; (2) feature-off (reject c {status:404, message:"...feature is not enabled..."}) → «Функция недоступна»; (3) создание правила: открыть диалог, заполнить имя/событие/условие/действие notify, submit → rulesApi.create вызван с ожидаемым payload; (4) dry-run флоу: выбрать правило+событие, ввести JSON, «Проверить» → рендер matched; (5) журнал: строки со статус-бейджами. НЕ забыть ResizeObserver-полифилл уже в vitest.setup.ts; текст-коллизии искать через `within()`.
- [ ] **Step 8: Прогнать + commit**

```powershell
Set-Location frontend
npx vitest run src/pages/rules/RulesPage.test.tsx src/api/rules.test.ts
npx tsc --noEmit
```

```bash
git add frontend/src/pages/rules frontend/src/features/rules frontend/src/permissions/permissions.ts frontend/src/router/pageRegistry.tsx frontend/src/router/routeGroups.tsx frontend/src/router/navigationConfig.ts frontend/src/router/navVisibility.ts frontend/src/pages/rules/RulesPage.test.tsx
git commit -m "feat(rules): /rules page — registry, form dialog, dry-run, trigger log (P10-10)"
```

---

### Task 11: Финальные гейты + браузерная верификация + доки

- [ ] **Step 1: Фронт-гейты полностью** (worktree; node_modules — junction на main-tree или `npm ci --prefer-offline`):
```powershell
Set-Location frontend
npx tsc --noEmit          # exit 0
npx vitest run            # полный прогон, НЕ параллельно с pytest; флейк → перепрогнать файл изолированно
npm run build             # exit 0
```
- [ ] **Step 2: Браузерная верификация** (dev_lite из worktree, `python scripts/dev_lite.py --auto-kill-ports`; demo/admin@example.com/admin123): `/rules` открывается; список демо-правил (2 шт из сида); создать правило через UI → 201; dry-run вернул matched; **живая проверка hook'а**: создать инцидент severity=critical через UI/API → в журнале срабатываний появилась строка success, в задачах — новая задача, в уведомлениях — уведомление. Скриншот или read_page-подтверждение в отчёт. (Если Radix-вкладки/скриншоты в browser-pane деградированы — прецедент contractors-волны — верифицировать через живой API аутентифицированной сессией и vitest.)
- [ ] **Step 3: Доки**: `AI_IMPLEMENTATION_REPORT.md` — новый handoff-блок сверху (по шаблону прошлых: решения/архитектура/верификация/отложено/next); `CHANGELOG.md` — запись; `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md` — обновить строку P10-10 (rules-engine срез-1 на ветке/влит); спека+план отметить выполненными.
- [ ] **Step 4: Commit доков + пуш ветки** (PR — по решению пользователя/контроллера):
```bash
git add AI_IMPLEMENTATION_REPORT.md CHANGELOG.md docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md docs/superpowers/plans/2026-07-15-p10-10-rules-engine-srez1.md
git commit -m "docs(rules): wave handoff + changelog + roadmap (P10-10 срез-1)"
git push -u origin feat/p10-10-rules-engine-srez1
```
