# Минимумы групп по напряжению (до/выше 1000В) — Implementation Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Шаги — чекбоксы.

**Goal:** Сделать минимумы групп по электробезопасности зависимыми от класса напряжения наряда (`voltage_level` в type_specific JSON, без миграции). Обратная совместимость: дефолт = «до 1000В» (текущее).

**Ветка:** `feat/work-permit-electrical-voltage-minimums` (стек поверх `feat/work-permit-electrical-groups`). НЕ переключать. Среда Win+Py3.13.7/.venv. PowerShell tool. `git status` перед коммитом.

---

### Task 1: `electrical_groups.py` — минимумы по напряжению (обратная совместимость)

**Files:** Modify `backend/app/domains/work_permits/electrical_groups.py`; Modify `backend/tests/test_electrical_groups.py` (добавить, не ломать существующие).

- [ ] **Step 1: Новые падающие тесты** (gt_1000): `meets_minimum("III","foreman","gt_1000")` → False (нужна IV); `meets_minimum("IV","foreman","gt_1000")` → True; `meets_minimum("IV","supervisor","gt_1000")` → False (нужна V); `role_min("foreman","gt_1000")=="IV"`, `role_min("foreman","le_1000")=="III"`, `role_min("foreman",None)=="III"`; `readiness([{person_id,role:"foreman",group:"III"}], "gt_1000")` → ok False, required "IV"; `readiness(..., None)` = как раньше. **Существующие тесты НЕ менять.**

- [ ] **Step 2:** прогнать ВЕСЬ файл → новые FAIL, старые PASS: `.venv\Scripts\python.exe -m pytest backend/tests/test_electrical_groups.py -q -p no:warnings`

- [ ] **Step 3: Реализация.** Сохрани `ROLE_MIN_GROUP` (le_1000) как есть. Добавь:
```python
ROLE_MIN_GROUP_HV: dict[str, str] = {           # выше 1000В (ПОТЭЭ; сверить с юристом)
    "issuer": "IV", "supervisor": "V", "admitter": "IV",
    "foreman": "IV", "member": "III", "observer": "IV",
}

def _min_table(voltage_level: str | None) -> dict[str, str]:
    return ROLE_MIN_GROUP_HV if voltage_level == "gt_1000" else ROLE_MIN_GROUP

def role_min(role: str, voltage_level: str | None = None) -> str | None:
    return _min_table(voltage_level).get(role)
```
Обнови сигнатуры (опциональный параметр — обратная совместимость):
```python
def meets_minimum(group: str | None, role: str, voltage_level: str | None = None) -> bool:
    required = _min_table(voltage_level).get(role)
    if required is None:
        return True
    return rank(group) >= rank(required)

def readiness(members: list[dict], voltage_level: str | None = None) -> dict:
    table = _min_table(voltage_level)
    insufficient = []
    for m in members:
        role = m.get("role"); group = m.get("group")
        if not meets_minimum(group, role, voltage_level):
            insufficient.append({"person_id": m.get("person_id"), "role": role,
                                 "group": group, "required": table.get(role)})
    return {"ok": not insufficient, "insufficient": insufficient}
```

- [ ] **Step 4:** прогнать → все зелёные (новые + 25 старых). **Step 5:** `py_compile`. **Step 6: Commit** `feat(work-permits): минимумы групп электробезопасности по классу напряжения`.

---

### Task 2: `profiles.py` — ключ voltage_level + валидация + печать

**Files:** Modify `backend/app/domains/work_permits/profiles.py`; Modify соответствующий тест профилей/печати.

- [ ] **Step 1:** падающие тесты: `validate_type_specific("electrical", {"voltage_level":"gt_1000"})` — ок; `{"voltage_level":"bad"}` → ValueError; `{"voltage_level":"le_1000","technical_measures":["disconnect"]}` — ок; `build_structured_section("electrical", ..., {"voltage_level":"gt_1000"})` содержит «Класс напряжения»/«Выше 1000 В».
- [ ] **Step 2:** прогнать → FAIL.
- [ ] **Step 3:** В `profiles.py` добавь `VOLTAGE_LEVELS = {"le_1000": "До 1000 В", "gt_1000": "Выше 1000 В"}`. В electrical-ветке `validate_type_specific`: допустимые ключи `{"technical_measures", "voltage_condition", "voltage_level"}`; после проверки voltage_condition — `vl = payload.get("voltage_level"); if vl is not None and vl not in VOLTAGE_LEVELS: raise ValueError(...)`. В `build_structured_section` electrical-ветка: если `ts.get("voltage_level")` — `kv.append(("Класс напряжения", VOLTAGE_LEVELS.get(vl, vl)))`.
- [ ] **Step 4:** прогнать → зелёный. **Step 5:** `py_compile`. **Step 6: Commit** `feat(work-permits): voltage_level в профиле электроустановок`.

---

### Task 3: Read-обогащение по voltage_level + demo-seed

**Files:** Modify `backend/app/api/routes/work_permits.py`; Modify `backend/app/services/demo_bootstrap.py`; тест.

- [ ] **Step 1:** падающий тест: электро-наряд с `type_specific.voltage_level="gt_1000"` + член foreman группы "III" → `electrical_group_readiness.ok == False`, required "IV" (та же группа при le_1000/без voltage_level → ok True).
- [ ] **Step 2:** прогнать → FAIL.
- [ ] **Step 3:** В `_permit_read` (электро-ветка): `voltage_level = (wp.type_specific or {}).get("voltage_level")`; `readiness = eg.readiness([...], voltage_level)`. Demo-seed `_seed_work_permit_electrical_demo`: в `type_specific` добавить `"voltage_level": "le_1000"` (зона РУ-0,4 кВ = до 1000В).
- [ ] **Step 4:** прогнать новый + work_permit-когорт → зелёный. **Step 5:** `py_compile`. **Step 6: Commit** `feat(work-permits): готовность по классу напряжения + seed`.

---

### Task 4: Frontend — select класса напряжения

**Files:** Modify `frontend/src/features/work-permits/WorkPermitFormDialog.tsx`; Modify `frontend/src/lib/workPermitVocab.ts` (+ `VOLTAGE_LEVEL_LABELS`); Modify zod (`frontend/src/types/forms/workPermits.ts` — добавить `voltage_level` в electrical-схему, если она есть); тест.

- [ ] **Step 1:** падающий vitest: при виде `electrical` виден select «Класс напряжения»; выбор «Выше 1000 В» → сабмит шлёт `type_specific.voltage_level == "gt_1000"`. Сверь харнес по существующему electrical-form тесту.
- [ ] **Step 2:** прогнать → FAIL.
- [ ] **Step 3:** В electrical-секции формы добавить `select` «Класс напряжения» (опции «—»/«До 1000 В»=le_1000/«Выше 1000 В»=gt_1000), пишущий `type_specific.voltage_level` по образцу существующего `voltage_condition`-селекта в той же секции (читай как там сделано). Добавить `VOLTAGE_LEVEL_LABELS` в vocab. zod electrical-схему расширить `voltage_level: z.enum(["le_1000","gt_1000"]).optional()` (+ merge), если схема типизирована.
- [ ] **Step 4:** прогнать новый + electrical/наряд-форма регресс → зелёный. **Step 5:** `tsc`+`eslint --max-warnings=0`. **Step 6: Commit** `feat(work-permits): select класса напряжения в электро-секции формы`.

---

### Task 5: Верификация + handoff

- [ ] **Step 1:** `.venv\Scripts\python.exe -m pytest backend/tests -k "electrical or work_permit or profile or print" -q -p no:warnings` → 0; миграционный когорт → 0 (без миграции).
- [ ] **Step 2:** `cd frontend; npm run build; npx vitest run src/__tests__/WorkPermit; cd ..` → build 0, passed.
- [ ] **Step 3:** Handoff в `AI_IMPLEMENTATION_REPORT.md` (минимумы по напряжению, обратная совместимость, без миграции, минимумы=ПОТЭЭ сверить с юристом).
- [ ] **Step 4:** Commit handoff. **Step 5:** Финальное ревью (sonnet) по диффу vs `feat/work-permit-electrical-groups`.

## Self-Review (выполнено)
- Обратная совместимость: опциональный `voltage_level`, дефолт=le_1000=текущее → 25 старых юнитов целы (центр T1).
- Дивиденд без миграции: voltage_level в JSON; T5 миграционный когорт.
- `voltage_level` ≠ `voltage_condition` — разные поля, оба в electrical type_specific.
- Минимумы HV — регуляторные, помечены «сверить с юристом».
