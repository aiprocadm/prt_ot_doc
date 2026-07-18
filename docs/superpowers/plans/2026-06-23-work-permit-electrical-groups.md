# Группы по электробезопасности (903н) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Каждая задача — свежий имплементер + spec→quality ревью. Шаги — чекбоксы `- [ ]`.

**Goal:** Группы по электробезопасности у членов бригады электронаряда: хранение в `Person.qualifications` (без миграции), показ + мягкая готовность в наряде (без FSM-гейта).

**Architecture:** Чистый домен `electrical_groups.py` (резолв группы + readiness) ← обогащение read электронаряда ← точечный контрол группы на карточке персоны (merge-safe) + баннер готовности на детали.

**Tech:** Python/FastAPI/pytest · React/react-hook-form/zod/vitest. Команды через **PowerShell tool**. Среда Win+Py3.13.7/.venv (канон Py3.12=CI). `git status` перед коммитом — только свои файлы.

**Ветка:** `feat/work-permit-electrical-groups` (стек поверх `feat/work-permit-gas-analysis-editor`). НЕ переключать.

---

### Task 1: Чистый домен `electrical_groups.py` + юниты

**Files:** Create `backend/app/domains/work_permits/electrical_groups.py`; Create `backend/tests/unit/test_electrical_groups.py` (путь сверь с соседними unit-тестами домена work_permits, напр. `test_work_permit_profiles.py`/`test_work_permit_lifecycle.py` — положи рядом).

- [ ] **Step 1: Падающие юнит-тесты.** Покрыть:
  - `current_group`: высшая из нескольких действующих (`["III","IV"]`→`"IV"`); истёкшая (`valid_until` < as_of) исключена; запись без `valid_until` действует всегда; нет электро-записей → `None`; игнор записей kind!=electrical_safety_group.
  - `meets_minimum`: ровно на минимуме (III для foreman)→True; ниже (II для foreman)→False; роль без требования→True; `None`-группа при наличии требования→False; неизвестный level→False.
  - `readiness`: все достаточны→`{ok:True, insufficient:[]}`; один нарушитель→`ok:False`, `insufficient` содержит `{person_id, role, group, required}`.

Сигнатуры (точно):
```python
current_group(qualifications: list[dict] | None, as_of: date) -> str | None
meets_minimum(group: str | None, role: str) -> bool
readiness(members: list[dict]) -> dict   # member: {"person_id","role","group"}
```
as_of передавать как `date` (тест передаёт фиксированную дату; даты записей — ISO-строки или `date`, нормализуй обе формы).

- [ ] **Step 2:** Прогнать → FAIL: `.venv\Scripts\python.exe -m pytest backend/tests/unit/test_electrical_groups.py -q -p no:warnings`

- [ ] **Step 3: Реализация** `backend/app/domains/work_permits/electrical_groups.py`:
```python
"""Группы по электробезопасности (903н): резолв текущей группы персоны + готовность бригады.

Чистый модуль (без I/O / без sqlalchemy) — как lifecycle.py / profiles.py. Группа живёт
в Person.qualifications (kind="electrical_safety_group", level ∈ I..V). Read-путь наряда
обогащает членов резолвнутой группой и считает мягкую готовность.
"""
from __future__ import annotations

from datetime import date, datetime

GROUP_ORDER = ["I", "II", "III", "IV", "V"]

# Упрощённые минимумы 903н (контекст ≤1000В). >1000В строже — отложено.
ROLE_MIN_GROUP: dict[str, str] = {
    "issuer": "IV", "supervisor": "IV", "admitter": "IV",
    "foreman": "III", "member": "III", "observer": "III",
}
_KIND = "electrical_safety_group"


def rank(level: str | None) -> int:
    if level in GROUP_ORDER:
        return GROUP_ORDER.index(level)
    return -1


def _as_date(v) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


def current_group(qualifications: list[dict] | None, as_of: date) -> str | None:
    best: str | None = None
    for q in qualifications or []:
        if not isinstance(q, dict) or q.get("kind") != _KIND:
            continue
        level = q.get("level")
        if rank(level) < 0:
            continue
        vu = _as_date(q.get("valid_until"))
        if vu is not None and vu < as_of:
            continue  # истекла
        if best is None or rank(level) > rank(best):
            best = level
    return best


def meets_minimum(group: str | None, role: str) -> bool:
    required = ROLE_MIN_GROUP.get(role)
    if required is None:
        return True
    return rank(group) >= rank(required)


def readiness(members: list[dict]) -> dict:
    insufficient = []
    for m in members:
        role = m.get("role")
        group = m.get("group")
        if not meets_minimum(group, role):
            insufficient.append({
                "person_id": m.get("person_id"),
                "role": role,
                "group": group,
                "required": ROLE_MIN_GROUP.get(role),
            })
    return {"ok": not insufficient, "insufficient": insufficient}
```

- [ ] **Step 4:** Прогнать → зелёный. **Step 5:** `py_compile`. **Step 6: Commit** `feat(work-permits): чистый домен групп по электробезопасности (903н)`.

---

### Task 2: Схема `QualificationRecord.level` + read-обогащение наряда

**Files:** Modify `backend/app/schemas/person.py` (level); Modify `backend/app/schemas/work_permit.py` (member group + readiness); Modify `backend/app/api/routes/work_permits.py` (enrichment); Test (create) `backend/tests/` integration по образцу существующих work_permit-API-тестов.

- [ ] **Step 1: Падающий тест.** Сверь харнес по существующему `test_work_permit_*` API-тесту (фикстуры tenant/person/сессии — паттерн как в `test_work_permit_signing.py`). Проверить: электро-наряд с членом, у чьей персоны `qualifications=[{kind:"electrical_safety_group", level:"IV"}]`, в GET-детали отдаёт `members[].electrical_group == "IV"` и `electrical_group_readiness.ok` корректно; член-`foreman` с группой `II` → `readiness.ok == False`, `insufficient` содержит его; **не-электро** наряд → `electrical_group is None` у членов и `electrical_group_readiness is None`.

- [ ] **Step 2:** Прогнать → FAIL.

- [ ] **Step 3: Реализация.**

(a) `schemas/person.py` — в `QualificationRecord` добавить `level: str | None = Field(default=None, max_length=8)`. Проверить, что `_sanitize_qualifications_list`/`_truncate_qualification_row` не выкидывают `level` (если там whitelist ключей — добавить `level`; сверь по коду).

(b) `schemas/work_permit.py`:
```python
class ElectricalGroupReadiness(BaseSchema):
    ok: bool
    insufficient: list[dict]   # [{person_id, role, group, required}]
```
В `WorkPermitMemberRead` добавить `electrical_group: str | None = None`.
В `WorkPermitRead` добавить `electrical_group_readiness: ElectricalGroupReadiness | None = None`.

(c) `api/routes/work_permits.py`:
- `_member_schema(m, *, electrical_group: str | None = None)` → прокинуть в схему `electrical_group=electrical_group`.
- В `_permit_read`: после `members = await list_members(...)`:
```python
from app.domains.work_permits import electrical_groups as eg
from datetime import date, timezone, datetime  # сверь существующие импорты, не дублируй

groups: dict[str, str | None] = {}
readiness = None
if wp.work_type == "electrical" and members:
    person_ids = [m.person_id for m in members]
    rows = (await session.execute(
        select(Person.id, Person.qualifications).where(
            Person.tenant_id == tenant.id, Person.id.in_(person_ids)
        )
    )).all()
    today = datetime.now(timezone.utc).date()
    quals_by_id = {str(pid): q for pid, q in rows}
    for m in members:
        groups[str(m.person_id)] = eg.current_group(quals_by_id.get(str(m.person_id)), today)
    readiness = eg.readiness([
        {"person_id": str(m.person_id), "role": m.role, "group": groups.get(str(m.person_id))}
        for m in members
    ])
```
- `members=[_member_schema(m, electrical_group=groups.get(str(m.person_id))) for m in members]`
- В конструктор `WorkPermitRead(...)` добавить `electrical_group_readiness=(ElectricalGroupReadiness(**readiness) if readiness else None)`.

Импорт `Person` — сверь, как модель импортируется в этом роуте (возможно `from app.models.models import Person`). `select` уже импортирован (используется в `_closing_summary`).

- [ ] **Step 4:** Прогнать новый + work_permit-API-когорт → зелёный. **Step 5:** `py_compile`. **Step 6: Commit** `feat(work-permits): обогащение read электронаряда группами + готовность`.

---

### Task 3: Demo-seed группы

**Files:** Modify `backend/app/services/demo_bootstrap.py`.

- [ ] **Step 1:** Найти seed электро-демо-наряда (`WP-ELEC-DEMO`, функция `_seed_work_permit_*` — сверь имя; если электро-демо нет, добавь идемпотентный по образцу `_seed_work_permit_hot_work_demo`, work_type="electrical", zone_text напр. «РУ-6 кВ, ячейка №7», + foreman-член).
- [ ] **Step 2:** Производителю (персона `person`) идемпотентно записать в `person.qualifications` группу:
```python
quals = list(person.qualifications or [])
if not any(q.get("kind") == "electrical_safety_group" for q in quals):
    quals.append({"kind": "electrical_safety_group", "level": "IV",
                  "name": "Группа по электробезопасности", "valid_until": "2027-12-31"})
    person.qualifications = quals
```
(если `person` переиспользуется другими seed — убедись, что добавление группы не ломает их; группа аддитивна.)
- [ ] **Step 3:** `py_compile` + (если есть) demo-bootstrap smoke-тест. **Step 4: Commit** `feat(work-permits): demo-seed группы электробезопасности`.

---

### Task 4: Карточка персоны — контрол группы (merge-safe)

**Files:** Modify `frontend/src/types/forms/persons.ts`; Modify `frontend/src/features/persons/PersonFormDialog.tsx`; Modify `frontend/src/types/dto/employee.ts` (если `qualifications` нет в Person DTO, что читает форма — сверь, какой DTO); Test (create) `frontend/src/__tests__/PersonElectricalGroup.test.tsx`.

- [ ] **Step 1: Падающий тест** (footgun-merge в центре): рендер `PersonFormDialog` с `initialData`, у которого `qualifications=[{kind:"training", name:"Обучение по ОТ"}]`; выбрать группу «IV»; сабмит → `personsApi.update` (или create) вызван с `qualifications`, содержащим И тренинг, И `{kind:"electrical_safety_group", level:"IV"}`. Второй тест: снятие группы («—») удаляет только электро-запись. Сверь имена API/полей по существующим person-form тестам.

- [ ] **Step 2:** Прогнать → FAIL.

- [ ] **Step 3: Реализация.**
- `persons.ts` zod: добавить `electrical_group: z.enum(["", "I","II","III","IV","V"]).optional()` (+ опц. `electrical_group_valid_until: z.string().optional()`).
- `PersonFormDialog`:
  - Скрытое состояние существующих квалификаций: при reset/load — `form` несёт `qualifications` из `initialData` (default `[]`); извлечь текущую электро-группу (`current` запись kind=electrical_safety_group) в поле `electrical_group`.
  - JSX: секция «Группа по электробезопасности» — `select` (I–V + «—») + Input «действует до» (date, опц.).
  - `toBody`: `const others = (existingQuals).filter(q => q.kind !== "electrical_safety_group"); const next = electrical_group ? [...others, {kind:"electrical_safety_group", level: electrical_group, name:"Группа по электробезопасности", valid_until: electrical_group_valid_until || undefined}] : others;` → отправить `qualifications: next`.
  - Убедиться, что update-payload включает `qualifications` (иначе бэкенд не получит). Если форма раньше не слала qualifications — добавить в payload.

- [ ] **Step 4:** Прогнать новый + person-form регресс → зелёный. **Step 5:** `tsc` + `eslint --max-warnings=0` на изменённых. **Step 6: Commit** `feat(persons): контрол группы по электробезопасности (merge-safe)`.

---

### Task 5: Деталь электронаряда — группы + баннер готовности

**Files:** Modify `frontend/src/pages/work-permits/WorkPermitDetailPage.tsx` (или `BrigadeMembersPanel` — сверь, где рендерятся члены); Modify `frontend/src/types/dto/workPermits.ts` (добавить `electrical_group` в member DTO + `electrical_group_readiness` в WP DTO); Test (create/extend) `frontend/src/__tests__/WorkPermitElectricalGroups.test.tsx`.

- [ ] **Step 1: Падающий тест:** деталь электро-наряда с членом группы и `electrical_group_readiness.ok=false` → виден бейдж группы И баннер готовности со строкой нарушителя; для не-электро наряда (или `electrical_group_readiness=null`) баннер НЕ виден.

- [ ] **Step 2:** Прогнать → FAIL.

- [ ] **Step 3: Реализация.**
- DTO `workPermits.ts`: `electrical_group?: string | null` в member; `electrical_group_readiness?: { ok: boolean; insufficient: Array<{person_id:string; role:string; group:string|null; required:string|null}> } | null` в WP.
- В бригадной панели: рядом с ролью/именем — бейдж `Группа: {electrical_group ?? "—"}` (только если `wp.work_type==="electrical"`).
- Баннер: если `wp.work_type==="electrical"` && `wp.electrical_group_readiness && !ok` → блок-предупреждение со списком `insufficient` (роль+группа+требуется), используя `MEMBER_ROLE_LABELS`. Мягко (не блокирует кнопки).

- [ ] **Step 4:** Прогнать новый + наряд-детали регресс → зелёный. **Step 5:** `tsc`+`eslint`. **Step 6: Commit** `feat(work-permits): группы и баннер готовности на детали электронаряда`.

---

### Task 6: Верификация + handoff

- [ ] **Step 1: Backend когорт:** `.venv\Scripts\python.exe -m pytest backend/tests -k "electrical or work_permit or person or qualif" -q -p no:warnings` → `$LASTEXITCODE`=0. Миграционный когорт (`-k "migration or downgrade"`) → 0 (миграции НЕТ — должен остаться зелёным).
- [ ] **Step 2: Frontend:** `cd frontend; npm run build; npx vitest run src/__tests__/PersonElectricalGroup src/__tests__/WorkPermitElectricalGroups src/__tests__/WorkPermit; cd ..` → build 0, все passed.
- [ ] **Step 3: Handoff** в начало `AI_IMPLEMENTATION_REPORT.md`: группы 903н построены, хранение на персоне (без миграции), показ+мягкая готовность, отложенное.
- [ ] **Step 4: Commit** handoff. **Step 5: Финальное холистическое ревью** (sonnet) по диффу ветки vs `feat/work-permit-gas-analysis-editor`.

---

## Self-Review (выполнено)

- **Покрытие спеки:** домен ✓(T1) · level+read-обогащение ✓(T2) · seed ✓(T3) · контрол персоны merge-safe ✓(T4) · показ+готовность ✓(T5) · тесты в каждой ✓ · верификация без миграции ✓(T6).
- **Footgun затирания квалификаций** — в центре T4 (тест с пред-существующим тренингом).
- **Гейт по work_type** — обогащение только для электро (T2), баннер только для электро (T5).
- **Плейсхолдеры:** код приведён; оговорки «сверь импорт/имя/харнес по соседям» — намеренные точки верификации, не TODO.
- **Без миграции:** `level` и группа — в JSON `qualifications`; T6 миграционный когорт доказывает.
