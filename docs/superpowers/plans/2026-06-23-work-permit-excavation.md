# Тираж наряда-допуска на земляные работы (excavation) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить 6-й (последний) вид наряда-допуска — земляные работы — через слой профилей, закрыв тираж видов работ.

**Architecture:** Подход A, паритет с электро. Правки бэкенда **только** в `profiles.py` (`structured_kind="excavation_safety"`: чек-лист подземных коммуникаций + enum защиты стенок выемки). Миграции нет. Frontend: vocab, zod, секция формы (через уже-общий `toggleTsCode` + расширение union-поля), read-only блок деталь-страницы, demo-seed.

**Tech Stack:** Python 3.13 local / 3.12 CI · FastAPI · Pydantic · pytest. React · react-hook-form · zod · vitest. Тесты локально через PowerShell→`.venv\Scripts\python.exe`, foreground.

---

### Task 1: Backend — профиль земляных работ в `profiles.py`

**Files:**
- Modify: `backend/app/domains/work_permits/profiles.py`
- Test (create): `backend/tests/test_work_permit_profiles_excavation.py`
- Test (modify): `backend/tests/test_work_permit_confined_schemas.py`

- [ ] **Step 1: Создать `backend/tests/test_work_permit_profiles_excavation.py`:**

```python
"""Профиль земляных работ (883н): валидация type_specific и печатная секция."""
from __future__ import annotations

import pytest

from app.domains.work_permits import profiles as p


def test_validate_accepts_valid_excavation():
    p.validate_type_specific(
        "excavation",
        {"utilities": ["power_cable", "water_sewer"], "shoring": "shield_bracing"},
    )


def test_validate_rejects_unknown_key():
    with pytest.raises(ValueError):
        p.validate_type_specific("excavation", {"gas_analysis": []})


def test_validate_rejects_bad_utility():
    with pytest.raises(ValueError):
        p.validate_type_specific("excavation", {"utilities": ["lava_tube"]})


def test_validate_rejects_bad_shoring():
    with pytest.raises(ValueError):
        p.validate_type_specific("excavation", {"shoring": "magic"})


def test_validate_accepts_empty():
    p.validate_type_specific("excavation", None)
    p.validate_type_specific("excavation", {})


def test_build_section_renders_shoring_and_utilities():
    section = p.build_structured_section(
        "excavation",
        safety_systems=None,
        type_specific={"utilities": ["power_cable"], "shoring": "shield_bracing"},
    )
    assert section is not None
    assert section.table is None
    flat = " ".join(f"{k}: {v}" for k, v in section.kv)
    assert "Крепление щитами" in flat
    assert "кабели" in flat.lower()


def test_build_section_none_when_empty():
    assert p.build_structured_section("excavation", safety_systems=None, type_specific={}) is None


def test_excavation_profile_structured_kind():
    assert p.profile_for("excavation").structured_kind == "excavation_safety"
```

- [ ] **Step 2: Прогнать — падает**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_work_permit_profiles_excavation.py -v 2>&1 | Tee-Object pytest_e1.txt`
Expected: FAIL (`structured_kind` ещё `None`).

- [ ] **Step 3: Реализовать в `profiles.py`**

После словаря `VOLTAGE_CONDITIONS` (добавлен в электро-срезе) добавить:

```python
# --- подземные коммуникации в зоне земляных работ ---
UTILITIES = {
    "power_cable": "Электрические кабели",
    "gas_pipe": "Газопровод",
    "water_sewer": "Водопровод / канализация",
    "heating": "Теплосеть",
    "comms": "Кабели связи",
}

# --- способ защиты стенок выемки (земляные работы) ---
SHORING_METHODS = {
    "natural_slopes": "Естественные откосы",
    "shield_bracing": "Крепление щитами / распорами",
    "sheet_piling": "Шпунтовое ограждение",
    "none_shallow": "Без крепления (мелкая выемка)",
}
```

В комментарии `structured_kind` дописать `"excavation_safety"`.

В `PROFILES["excavation"]` заменить `legal_reference` и `structured_kind`:

```python
    "excavation": WorkTypeProfile(
        "excavation",
        "Земляные работы",
        "Приказ Минтруда России от 11.12.2020 № 883н (ПОТ при строительстве, реконструкции и ремонте)",
        "excavation_safety",
    ),
```

В `validate_type_specific` перед финальным `else` добавить ветку:

```python
    elif kind == "excavation_safety":
        unknown = set(payload) - {"utilities", "shoring"}
        if unknown:
            raise ValueError(f"unknown type_specific keys: {sorted(unknown)}")
        _validate_code_list(payload.get("utilities"), UTILITIES, "utilities")
        shoring = payload.get("shoring")
        if shoring is not None and shoring not in SHORING_METHODS:
            raise ValueError(f"invalid shoring: {shoring!r}")
```

В `build_structured_section` перед финальным `return None` добавить:

```python
    if kind == "excavation_safety":
        ts = type_specific or {}
        kv = []
        shoring = ts.get("shoring")
        if shoring:
            kv.append(("Защита стенок выемки", SHORING_METHODS.get(shoring, shoring)))
        utils = ts.get("utilities") or []
        if utils:
            kv.append(("Подземные коммуникации", ", ".join(UTILITIES.get(u, u) for u in utils)))
        if not kv:
            return None
        return pf.StructuredSection(
            title="Безопасность земляных работ (883н)", kv=kv, table=None
        )
```

- [ ] **Step 4: Прогнать профиль-тесты — 8 passed**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_work_permit_profiles_excavation.py -v 2>&1 | Tee-Object pytest_e1.txt`

- [ ] **Step 5: Добавить excavation-кейсы в `test_work_permit_confined_schemas.py` (в конец):**

```python
def test_create_accepts_valid_excavation_type_specific():
    m = WorkPermitCreate(
        work_type="excavation",
        zone_text="Траншея вдоль корпуса №4",
        type_specific={"utilities": ["power_cable", "water_sewer"], "shoring": "shield_bracing"},
    )
    assert m.type_specific["shoring"] == "shield_bracing"


def test_create_rejects_bad_utility():
    with pytest.raises(ValidationError):
        WorkPermitCreate(
            work_type="excavation", zone_text="траншея",
            type_specific={"utilities": ["lava_tube"]},
        )


def test_create_rejects_gas_analysis_on_excavation():
    with pytest.raises(ValidationError):
        WorkPermitCreate(
            work_type="excavation", zone_text="траншея",
            type_specific={"gas_analysis": [{"parameter": "oxygen", "value": "20"}]},
        )
```

- [ ] **Step 6: Прогнать схемную матрицу — зелёная**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_work_permit_confined_schemas.py -v 2>&1 | Tee-Object pytest_e1b.txt`

- [ ] **Step 7: Commit**

```bash
git add backend/app/domains/work_permits/profiles.py backend/tests/test_work_permit_profiles_excavation.py backend/tests/test_work_permit_confined_schemas.py
git commit -m "feat(work-permits): профиль земляных работ 883н (валидация + печатная секция)"
```

---

### Task 2: Backend — demo-seed земляного наряда

**Files:**
- Modify: `backend/app/services/demo_bootstrap.py`

- [ ] **Step 1: Добавить seed-функцию** (после `_seed_work_permit_electrical_demo`):

```python
async def _seed_work_permit_excavation_demo(session, tenant_db_id: str, person) -> None:
    """Демо-наряд земляных работ (883н): коммуникации + защита стенок выемки. Идемпотентно."""
    from app.models.work_permit import WorkPermit, WorkPermitMember

    wp = (
        await session.execute(
            select(WorkPermit).where(
                WorkPermit.tenant_id == tenant_db_id,
                WorkPermit.number == "WP-DIG-DEMO",
            )
        )
    ).scalar_one_or_none()
    if wp is None:
        wp = WorkPermit(
            tenant_id=tenant_db_id,
            number="WP-DIG-DEMO",
            work_type="excavation",
            zone_text="Траншея вдоль корпуса №4 (теплотрасса)",
            status="draft",
            type_specific={
                "utilities": ["power_cable", "water_sewer"],
                "shoring": "shield_bracing",
            },
        )
        session.add(wp)
        await session.flush()
    member = (
        await session.execute(
            select(WorkPermitMember).where(
                WorkPermitMember.tenant_id == tenant_db_id,
                WorkPermitMember.work_permit_id == wp.id,
                WorkPermitMember.person_id == person.id,
                WorkPermitMember.role == "foreman",
            )
        )
    ).scalar_one_or_none()
    if member is None:
        session.add(
            WorkPermitMember(
                tenant_id=tenant_db_id, work_permit_id=wp.id, person_id=person.id, role="foreman"
            )
        )
```

- [ ] **Step 2: Зарегистрировать вызов** (после `await _seed_work_permit_electrical_demo(session, tenant_db_id, person)`):

```python
            await _seed_work_permit_excavation_demo(session, tenant_db_id, person)
```

- [ ] **Step 3: py_compile**

Run: `.venv\Scripts\python.exe -m py_compile backend/app/services/demo_bootstrap.py`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/demo_bootstrap.py
git commit -m "feat(work-permits): demo-seed WP-DIG-DEMO (земляные работы 883н)"
```

---

### Task 3: Frontend — vocab + zod-схема excavation

**Files:**
- Modify: `frontend/src/lib/workPermitVocab.ts`
- Modify: `frontend/src/types/forms/workPermits.ts`

- [ ] **Step 1: Словари в vocab** (после `VOLTAGE_CONDITION_LABELS`):

```ts
export const UTILITIES_LABELS: Record<string, string> = {
  power_cable: "Электрические кабели",
  gas_pipe: "Газопровод",
  water_sewer: "Водопровод / канализация",
  heating: "Теплосеть",
  comms: "Кабели связи",
};

export const SHORING_METHOD_LABELS: Record<string, string> = {
  natural_slopes: "Естественные откосы",
  shield_bracing: "Крепление щитами / распорами",
  sheet_piling: "Шпунтовое ограждение",
  none_shallow: "Без крепления (мелкая выемка)",
};
```

Заменить `LEGAL_REFERENCE_LABELS.excavation` строку `excavation: "Правила земляных работ",` на:
```ts
  excavation: "Приказ Минтруда № 883н (ПОТ в строительстве)",
```

- [ ] **Step 2: Коды и zod** (после `VOLTAGE_CONDITION_CODES`):

```ts
export const UTILITY_CODES = ["power_cable", "gas_pipe", "water_sewer", "heating", "comms"] as const;
export const SHORING_METHOD_CODES = ["natural_slopes", "shield_bracing", "sheet_piling", "none_shallow"] as const;

export const excavationSafetySchema = z.object({
  utilities: z.array(z.enum(UTILITY_CODES)).optional(),
  shoring: z.enum(SHORING_METHOD_CODES).optional(),
});
export type ExcavationSafetyValues = z.infer<typeof excavationSafetySchema>;
```

Заменить `typeSpecificSchema` (сейчас оканчивается `.merge(electricalSafetySchema);`) добавив ещё один merge:
```ts
export const typeSpecificSchema = confinedEnvSchema
  .merge(fireSafetySchema)
  .merge(gasWorksSchema)
  .merge(electricalSafetySchema)
  .merge(excavationSafetySchema);
```

- [ ] **Step 3: tsc** — `cd frontend; npx tsc --noEmit; cd ..` → exit 0.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/workPermitVocab.ts frontend/src/types/forms/workPermits.ts
git commit -m "feat(work-permits): фронт-словари + zod-схема земляных работ (883н)"
```

---

### Task 4: Frontend — секция формы excavation (через общий toggleTsCode)

**Files:**
- Modify: `frontend/src/features/work-permits/WorkPermitFormDialog.tsx`
- Test (create): `frontend/src/__tests__/WorkPermitExcavationForm.test.tsx`

- [ ] **Step 1: Падающий тест** — создать `WorkPermitExcavationForm.test.tsx` по образцу `WorkPermitElectricalForm.test.tsx` (взять рабочий приём матчинга чекбоксов оттуда). Проверяет:
1) при выборе `excavation` видна секция «Безопасность земляных работ», виден пункт «Электрические кабели», скрыты секции высоты/электро;
2) накопление двух чекбоксов коммуникаций (через `act`) — оба checked;
3) select «Защита стенок выемки» выставляет `shield_bracing`.

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { WorkPermitFormDialog } from "@/features/work-permits/WorkPermitFormDialog";

vi.mock("@/api/workPermits", () => ({ workPermitsApi: { create: vi.fn(), update: vi.fn() } }));

describe("WorkPermitFormDialog excavation section", () => {
  it("показывает секцию земляных при выборе excavation и скрывает чужие", () => {
    render(<WorkPermitFormDialog trigger={<button>open</button>} />);
    fireEvent.click(screen.getByText("open"));
    fireEvent.change(screen.getByLabelText("Вид работ"), { target: { value: "excavation" } });
    expect(screen.getByText(/Безопасность земляных работ/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Электрические кабели")).toBeInTheDocument();
    expect(screen.queryByText(/Меры безопасности в электроустановках/i)).not.toBeInTheDocument();
  });

  it("накапливает чекбоксы коммуникаций и выставляет защиту стенок", () => {
    render(<WorkPermitFormDialog trigger={<button>open</button>} />);
    fireEvent.click(screen.getByText("open"));
    fireEvent.change(screen.getByLabelText("Вид работ"), { target: { value: "excavation" } });
    act(() => {
      fireEvent.click(screen.getByLabelText("Электрические кабели"));
      fireEvent.click(screen.getByLabelText("Водопровод / канализация"));
    });
    expect((screen.getByLabelText("Электрические кабели") as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText("Водопровод / канализация") as HTMLInputElement).checked).toBe(true);
    fireEvent.change(screen.getByLabelText("Защита стенок выемки"), { target: { value: "shield_bracing" } });
    expect((screen.getByLabelText("Защита стенок выемки") as HTMLSelectElement).value).toBe("shield_bracing");
  });
});
```
Примечание: если `getByLabelText` для чекбоксов не сматчит — взять приём из соседнего теста.

- [ ] **Step 2: Прогнать — FAIL**

Run: `cd frontend; npx vitest run src/__tests__/WorkPermitExcavationForm.test.tsx; cd ..`

- [ ] **Step 3: Реализация в `WorkPermitFormDialog.tsx`:**

(a) Импорты: из `@/types/forms/workPermits` добавить `UTILITY_CODES`, `SHORING_METHOD_CODES`; из `@/lib/workPermitVocab` добавить `UTILITIES_LABELS`, `SHORING_METHOD_LABELS`.

(b) Расширить union-поле `toggleTsCode` — добавить `"utilities"`:
```ts
  const toggleTsCode = (
    field: "fire_fighting_means" | "respiratory_ppe" | "technical_measures" | "utilities",
    code: string,
  ) => {
```

(c) Снимок (рядом с `selectedMeasures`):
```ts
  const selectedUtilities = new Set(
    ((form.watch("type_specific") as { utilities?: string[] } | null)?.utilities) ?? [],
  );
```

(d) После блока `electrical` (заканчивается `)}` секции electrical) добавить секцию excavation:
```tsx
          {form.watch("work_type") === "excavation" && (
            <div className="space-y-2">
              <Label>Безопасность земляных работ (883н)</Label>
              <Label className="text-xs">Подземные коммуникации в зоне работ</Label>
              <div className="flex flex-wrap gap-3">
                {UTILITY_CODES.map((code) => (
                  <label key={code} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={selectedUtilities.has(code)}
                      onChange={() => toggleTsCode("utilities", code)}
                    />
                    {UTILITIES_LABELS[code]}
                  </label>
                ))}
              </div>
              <div className="space-y-1">
                <Label htmlFor="shoring" className="text-xs">Защита стенок выемки</Label>
                <select
                  id="shoring"
                  className="h-10 w-full rounded-md border px-3"
                  value={(form.watch("type_specific")?.shoring as string) ?? ""}
                  onChange={(e) =>
                    form.setValue("type_specific", {
                      ...(form.watch("type_specific") ?? {}),
                      shoring: (e.target.value || undefined) as never,
                    })
                  }
                >
                  <option value="">—</option>
                  {SHORING_METHOD_CODES.map((c) => (
                    <option key={c} value={c}>{SHORING_METHOD_LABELS[c]}</option>
                  ))}
                </select>
              </div>
            </div>
          )}
```

(e) `toBody` whitelist += `"excavation"`:
```ts
    type_specific: ["confined_space", "hot_work", "gas_hazardous", "electrical", "excavation"].includes(v.work_type)
      ? (v.type_specific ?? null)
      : null,
```

- [ ] **Step 4: Прогнать новый + регресс**

Run: `cd frontend; npx vitest run src/__tests__/WorkPermitExcavationForm.test.tsx src/__tests__/WorkPermitElectricalForm.test.tsx src/__tests__/WorkPermitGasWorksForm.test.tsx src/__tests__/WorkPermitFormToggles.test.tsx; cd ..`
Expected: все passed.

- [ ] **Step 5: tsc + eslint**

Run: `cd frontend; npx tsc --noEmit; npx eslint --max-warnings=0 src/features/work-permits/WorkPermitFormDialog.tsx src/__tests__/WorkPermitExcavationForm.test.tsx; cd ..`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/work-permits/WorkPermitFormDialog.tsx frontend/src/__tests__/WorkPermitExcavationForm.test.tsx
git commit -m "feat(work-permits): секция формы земляных работ (883н)"
```

---

### Task 5: Frontend — read-only блок деталь-страницы

**Files:**
- Modify: `frontend/src/pages/work-permits/WorkPermitDetailPage.tsx`
- Test (modify): `frontend/src/__tests__/WorkPermitDetailPage.test.tsx`

- [ ] **Step 1: Падающий тест** — добавить в `WorkPermitDetailPage.test.tsx` (переиспользовать фабрику рендера файла, override на excavation):

```tsx
it("рендерит блок земляных работ (защита стенок + коммуникации)", async () => {
  // через существующий рендер-хелпер с wp:
  //   work_type: "excavation",
  //   type_specific: { utilities: ["power_cable"], shoring: "shield_bracing" }
  expect(await screen.findByText(/Безопасность земляных работ/i)).toBeInTheDocument();
  expect(screen.getByText(/Крепление щитами/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Прогнать — FAIL** — `cd frontend; npx vitest run src/__tests__/WorkPermitDetailPage.test.tsx; cd ..`

- [ ] **Step 3: Реализация** — в `WorkPermitDetailPage.tsx` после блока `electrical` добавить:

```tsx
          {wp.work_type === "excavation" && wp.type_specific ? (
            <div className="text-sm">
              <div className="font-medium">Безопасность земляных работ (883н)</div>
              {(wp.type_specific as { shoring?: string }).shoring ? (
                <div>
                  Защита стенок выемки:{" "}
                  {SHORING_METHOD_LABELS[(wp.type_specific as { shoring: string }).shoring] ?? "—"}
                </div>
              ) : null}
              {((wp.type_specific as { utilities?: string[] }).utilities ?? []).length ? (
                <div>
                  Подземные коммуникации:{" "}
                  {((wp.type_specific as { utilities: string[] }).utilities)
                    .map((c) => UTILITIES_LABELS[c] ?? c)
                    .join(", ")}
                </div>
              ) : null}
            </div>
          ) : null}
```

Добавить в импорт из `@/lib/workPermitVocab`: `UTILITIES_LABELS, SHORING_METHOD_LABELS`.

- [ ] **Step 4: Прогнать — зелёный** — `cd frontend; npx vitest run src/__tests__/WorkPermitDetailPage.test.tsx; cd ..`

- [ ] **Step 5: tsc + eslint** — `cd frontend; npx tsc --noEmit; npx eslint --max-warnings=0 src/pages/work-permits/WorkPermitDetailPage.tsx src/__tests__/WorkPermitDetailPage.test.tsx; cd ..` → exit 0.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/work-permits/WorkPermitDetailPage.tsx frontend/src/__tests__/WorkPermitDetailPage.test.tsx
git commit -m "feat(work-permits): read-only блок земляных работ на деталь-странице"
```

---

### Task 6: Верификация когорт + handoff

**Files:**
- Modify: `AI_IMPLEMENTATION_REPORT.md`

- [ ] **Step 1: Backend когорт**

Run: `.venv\Scripts\python.exe -m pytest backend/tests -k "work_permit or profile or confined or migration or downgrade or mapper" -q 2>&1 | Tee-Object pytest_dig_cohort.txt`
Expected: RC=0, миграционная часть зелёная (миграции не задеты).

- [ ] **Step 2: Frontend сборка + наряд-тесты**

Run: `cd frontend; npm run build; npx vitest run src/__tests__/WorkPermit; cd ..`
Expected: BUILD exit 0; все наряд-vitest passed.

- [ ] **Step 3: Handoff** — добавить секцию в начало `AI_IMPLEMENTATION_REPORT.md`: 6-й вид, тираж видов работ ЗАКРЫТ (все 6 WORK_TYPES имеют structured_kind), дивиденд слоя, отложенное.

- [ ] **Step 4: Commit** — `git add AI_IMPLEMENTATION_REPORT.md; git commit -m "docs: handoff — земляные работы 883н (тираж видов работ закрыт)"`

- [ ] **Step 5: Финальное холистическое ревью** (opus) по диффу ветки.

---

## Self-Review (выполнено)

- **Покрытие спеки:** словари ✓(T1) · structured_kind+legal_reference ✓(T1) · валидация ✓(T1) · печатная секция ✓(T1) · vocab+legal label ✓(T3) · zod ✓(T3) · toggleTsCode union+ ✓(T4) · секция формы ✓(T4) · toBody ✓(T4) · деталь-блок ✓(T5) · demo-seed ✓(T2) · тесты ✓ · миграционный когорт зелёный ✓(T6).
- **Плейсхолдеры:** нет.
- **Согласованность типов:** `excavation_safety`, ключи `utilities`/`shoring`, коды коммуникаций/методов — идентичны между profiles.py, zod, seed, тестами. `toggleTsCode` union включает `utilities`.
- **Отложено явно:** глубина как числовое поле, паспорт котлована, группы, DRY seed.
