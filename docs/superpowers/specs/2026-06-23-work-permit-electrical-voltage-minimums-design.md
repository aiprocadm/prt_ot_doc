# Минимумы групп по электробезопасности по классу напряжения (до/выше 1000В)

**Дата:** 2026-06-23
**Статус:** Design (refinement групп 903н; «продолжай по роадмап», no-decision продолжение)
**Контур:** наряды-допуски §16, электроустановки (903н)

## Контекст

Фича групп по электробезопасности (PR #688) использует ЕДИНЫЙ набор минимумов `ROLE_MIN_GROUP`
(контекст ≤1000В). ПОТЭЭ (903н) требует более высокие группы в ЭУ **выше 1000В**. Этот срез
делает минимумы зависимыми от класса напряжения наряда.

**Дивиденд без миграции:** новое поле `voltage_level` в `type_specific JSON` электронаряда
(как `voltage_condition`/`technical_measures`). `voltage_level` (до/выше 1000В) — ОТЛИЧНО от
`voltage_condition` (со снятием / без снятия напряжения).

Ветка: `feat/work-permit-electrical-voltage-minimums` стеком поверх `feat/work-permit-electrical-groups`.

## Модель данных

`type_specific.voltage_level: "le_1000" | "gt_1000" | None`. Словарь:
```python
VOLTAGE_LEVELS = {"le_1000": "До 1000 В", "gt_1000": "Выше 1000 В"}
```

## `electrical_groups.py` — минимумы по напряжению (обратная совместимость)

```python
# До 1000В (текущий набор — сохраняется как ROLE_MIN_GROUP для обратной совместимости)
ROLE_MIN_GROUP = {issuer:IV, supervisor:IV, admitter:IV, foreman:III, member:III, observer:III}

# Выше 1000В (ПОТЭЭ — строже; сверить с юристом)
ROLE_MIN_GROUP_HV = {issuer:IV, supervisor:V, admitter:IV, foreman:IV, member:III, observer:IV}

def _min_table(voltage_level) -> dict:   # None или "le_1000" → ROLE_MIN_GROUP; "gt_1000" → HV
def role_min(role, voltage_level=None) -> str | None
def meets_minimum(group, role, voltage_level=None) -> bool   # voltage_level опционален
def readiness(members, voltage_level=None) -> dict           # voltage_level опционален
```

**Обратная совместимость критична:** `voltage_level` — опциональный параметр, дефолт `None` →
набор «до 1000В» = текущее поведение. → **25 существующих юнитов `electrical_groups` остаются
зелёными без изменений** (они зовут `meets_minimum(g, r)`/`readiness(m)` и ссылаются на
`ROLE_MIN_GROUP`).

## `profiles.py` — ключ voltage_level

- `VOLTAGE_LEVELS` словарь.
- electrical-секция `validate_type_specific`: допустимые ключи `{technical_measures,
  voltage_condition, voltage_level}`; `voltage_level` (если есть) ∈ `VOLTAGE_LEVELS`.
- `build_structured_section` electrical: kv «Класс напряжения» (если задан).

## Read-обогащение

`_permit_read` (электро): извлечь `voltage_level = (wp.type_specific or {}).get("voltage_level")`,
передать в `eg.readiness(members, voltage_level)`. Группа члена резолвится как раньше.

## Frontend

Электро-секция формы (`WorkPermitFormDialog`): `select` «Класс напряжения» (— / До 1000 В / Выше
1000 В), пишет `type_specific.voltage_level` (по образцу `voltage_condition`-селекта). Деталь —
показ класса (опционально, в существующем электро-блоке).

## Demo-seed

`WP-ELEC-DEMO` (зона «РУ-0,4 кВ» = до 1000В): `type_specific.voltage_level = "le_1000"`.

## Тестирование

- `electrical_groups`: новые юниты — `role_min`/`meets_minimum`/`readiness` для `gt_1000`
  (foreman III недостаточен выше 1000В → insufficient, required IV; supervisor IV недостаточен → V);
  `le_1000`/None = прежнее. **Существующие 25 юнитов прогнать — должны остаться зелёными.**
- `profiles`: `voltage_level` принимается; неверное значение → ValueError; печать содержит «Класс напряжения».
- read: электро-наряд `gt_1000` с foreman группы III → `electrical_group_readiness.ok == False`.
- frontend: select класса виден для электро, пишет `voltage_level` в payload.

## Отложено

1. Точные регуляторные минимумы — пометка «сверить с юристом» (структура voltage-aware — главное).
2. Связь `voltage_level` ↔ `voltage_condition` (без снятия выше 1000В строже) — не моделируем.
3. Печать класса напряжения — добавим в kv секции (уже в scope), отдельная типографика — нет.
