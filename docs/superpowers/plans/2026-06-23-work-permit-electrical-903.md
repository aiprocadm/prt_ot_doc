# Тираж наряда-допуска на электроустановки (903н) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить 5-й полноценный вид наряда-допуска — работы в электроустановках (903н) — через слой профилей, с DRY-рефактором тогглеров формы.

**Architecture:** Подход A. Правки бэкенда **только** в `backend/app/domains/work_permits/profiles.py` (новый `structured_kind="electrical_safety"`: чек-лист технических мероприятий + enum условия по напряжению). Миграции нет — `type_specific JSON` универсальна. Frontend добавляет vocab, zod-схему, секцию формы (с обобщённым `toggleTsCode`), read-only блок деталь-страницы, demo-seed.

**Tech Stack:** Python 3.12 (CI) / 3.13 (local) · FastAPI · Pydantic · pytest. React · react-hook-form · zod · vitest. Локальный pytest — через PowerShell→файл (см. [[py313_win_pytest_invocation]]).

---

### Task 1: Backend — профиль электроустановок в `profiles.py` (валидация + печатная секция)

**Files:**
- Modify: `backend/app/domains/work_permits/profiles.py`
- Test (create): `backend/tests/test_work_permit_profiles_electrical.py`
- Test (modify): `backend/tests/test_work_permit_confined_schemas.py`

- [ ] **Step 1: Написать падающие юнит-тесты профиля**

Create `backend/tests/test_work_permit_profiles_electrical.py`:

```python
"""Профиль электроустановок (903н): валидация type_specific и печатная секция."""
from __future__ import annotations

import pytest

from app.domains.work_permits import profiles as p


def test_validate_accepts_valid_electrical():
    p.validate_type_specific(
        "electrical",
        {"technical_measures": ["disconnect", "grounding"], "voltage_condition": "de_energized"},
    )  # не бросает


def test_validate_rejects_unknown_key():
    with pytest.raises(ValueError):
        p.validate_type_specific("electrical", {"gas_analysis": []})


def test_validate_rejects_bad_measure():
    with pytest.raises(ValueError):
        p.validate_type_specific("electrical", {"technical_measures": ["laser"]})


def test_validate_rejects_bad_voltage_condition():
    with pytest.raises(ValueError):
        p.validate_type_specific("electrical", {"voltage_condition": "underwater"})


def test_validate_accepts_empty():
    p.validate_type_specific("electrical", None)
    p.validate_type_specific("electrical", {})


def test_build_section_renders_condition_and_measures():
    section = p.build_structured_section(
        "electrical",
        safety_systems=None,
        type_specific={"technical_measures": ["disconnect", "grounding"], "voltage_condition": "de_energized"},
    )
    assert section is not None
    assert section.table is None
    flat = " ".join(f"{k}: {v}" for k, v in section.kv)
    assert "Со снятием напряжения" in flat
    assert "заземление" in flat.lower()


def test_build_section_none_when_empty():
    assert p.build_structured_section("electrical", safety_systems=None, type_specific={}) is None


def test_electrical_profile_structured_kind():
    assert p.profile_for("electrical").structured_kind == "electrical_safety"
```

- [ ] **Step 2: Прогнать — убедиться, что падают**

Run (PowerShell→файл, см. memory):
```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_work_permit_profiles_electrical.py -v 2>&1 | Tee-Object pytest_t1.txt
```
Expected: FAIL (`structured_kind` ещё `None` → `validate_type_specific` бросает «not accepted», `build_structured_section` возвращает `None`).

- [ ] **Step 3: Реализовать профиль в `profiles.py`**

После словаря `RESPIRATORY_PPE` (строка ~46) добавить:

```python
# --- технические мероприятия подготовки места (электроустановки, ПОТЭЭ 903н п.16.1) ---
ELECTRICAL_MEASURES = {
    "disconnect": "Произведены отключения, приняты меры против ошибочного включения",
    "lockout_signs": "На приводах и ключах управления вывешены запрещающие плакаты",
    "verify_no_voltage": "Проверено отсутствие напряжения на токоведущих частях",
    "grounding": "Установлено заземление (включены ЗН / наложены переносные заземления)",
    "barriers_signs": "Вывешены плакаты, ограждены рабочие места и токоведущие части под напряжением",
}

# --- условие производства работ по напряжению (электроустановки) ---
VOLTAGE_CONDITIONS = {
    "de_energized": "Со снятием напряжения",
    "near_live": "Без снятия напряжения вблизи токоведущих частей",
    "away_live": "Без снятия напряжения вдали от токоведущих частей",
}
```

В `WorkTypeProfile.structured_kind` комментарий (строка 54) дополнить значением `"electrical_safety"`:

```python
    structured_kind: str | None  # "safety_systems" | "confined_env" | "fire_safety" | "gas_works" | "electrical_safety" | None
```

В `PROFILES["electrical"]` заменить `None` на `"electrical_safety"`:

```python
    "electrical": WorkTypeProfile(
        "electrical",
        "Работа в электроустановках",
        "Приказ Минтруда России от 15.12.2020 № 903н",
        "electrical_safety",
    ),
```

В `validate_type_specific`, перед финальным `else`, добавить ветку:

```python
    elif kind == "electrical_safety":
        unknown = set(payload) - {"technical_measures", "voltage_condition"}
        if unknown:
            raise ValueError(f"unknown type_specific keys: {sorted(unknown)}")
        _validate_code_list(payload.get("technical_measures"), ELECTRICAL_MEASURES, "technical_measures")
        vc = payload.get("voltage_condition")
        if vc is not None and vc not in VOLTAGE_CONDITIONS:
            raise ValueError(f"invalid voltage_condition: {vc!r}")
```

В `build_structured_section`, перед финальным `return None`, добавить ветку:

```python
    if kind == "electrical_safety":
        ts = type_specific or {}
        kv = []
        vc = ts.get("voltage_condition")
        if vc:
            kv.append(("Условие проведения", VOLTAGE_CONDITIONS.get(vc, vc)))
        measures = ts.get("technical_measures") or []
        if measures:
            kv.append(
                ("Технические мероприятия", "; ".join(ELECTRICAL_MEASURES.get(m, m) for m in measures))
            )
        if not kv:
            return None
        return pf.StructuredSection(
            title="Меры безопасности в электроустановках (903н)", kv=kv, table=None
        )
```

- [ ] **Step 4: Прогнать профиль-тесты — зелёные**

Run:
```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_work_permit_profiles_electrical.py -v 2>&1 | Tee-Object pytest_t1.txt
```
Expected: 8 passed.

- [ ] **Step 5: Добавить electrical-кейсы в схемную 422-матрицу**

В `backend/tests/test_work_permit_confined_schemas.py` дописать в конец:

```python
def test_create_accepts_valid_electrical_type_specific():
    m = WorkPermitCreate(
        work_type="electrical",
        zone_text="РУ-0,4 кВ, ячейка №7",
        type_specific={
            "technical_measures": ["disconnect", "verify_no_voltage", "grounding"],
            "voltage_condition": "de_energized",
        },
    )
    assert m.type_specific["voltage_condition"] == "de_energized"


def test_create_rejects_bad_technical_measure():
    with pytest.raises(ValidationError):
        WorkPermitCreate(
            work_type="electrical", zone_text="РУ",
            type_specific={"technical_measures": ["laser"]},
        )


def test_create_rejects_gas_analysis_on_electrical():
    with pytest.raises(ValidationError):
        WorkPermitCreate(
            work_type="electrical", zone_text="РУ",
            type_specific={"gas_analysis": [{"parameter": "oxygen", "value": "20"}]},
        )
```

- [ ] **Step 6: Прогнать схемную матрицу — зелёная**

Run:
```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_work_permit_confined_schemas.py -v 2>&1 | Tee-Object pytest_t1b.txt
```
Expected: все passed (старые confined/hot/gas + 3 новых electrical).

- [ ] **Step 7: Commit**

```bash
git add backend/app/domains/work_permits/profiles.py backend/tests/test_work_permit_profiles_electrical.py backend/tests/test_work_permit_confined_schemas.py
git commit -m "feat(work-permits): профиль электроустановок 903н (валидация + печатная секция)"
```

---

### Task 2: Backend — demo-seed электро-наряда

**Files:**
- Modify: `backend/app/services/demo_bootstrap.py`

- [ ] **Step 1: Добавить seed-функцию**

После `_seed_work_permit_gas_demo` (заканчивается ~строка 480) добавить:

```python
async def _seed_work_permit_electrical_demo(session, tenant_db_id: str, person) -> None:
    """Демо-наряд работ в электроустановках (903н): тех. мероприятия + условие по напряжению. Идемпотентно."""
    from app.models.work_permit import WorkPermit, WorkPermitMember

    wp = (
        await session.execute(
            select(WorkPermit).where(
                WorkPermit.tenant_id == tenant_db_id,
                WorkPermit.number == "WP-ELEC-DEMO",
            )
        )
    ).scalar_one_or_none()
    if wp is None:
        wp = WorkPermit(
            tenant_id=tenant_db_id,
            number="WP-ELEC-DEMO",
            work_type="electrical",
            zone_text="РУ-0,4 кВ, ячейка №7, цех №2",
            status="draft",
            type_specific={
                "technical_measures": ["disconnect", "verify_no_voltage", "grounding"],
                "voltage_condition": "de_energized",
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

- [ ] **Step 2: Зарегистрировать вызов**

Рядом со строками `await _seed_work_permit_gas_demo(session, tenant_db_id, person)` (~709) добавить:

```python
            await _seed_work_permit_electrical_demo(session, tenant_db_id, person)
```

- [ ] **Step 3: Проверить компиляцию**

Run:
```powershell
.venv\Scripts\python.exe -m py_compile backend/app/services/demo_bootstrap.py
```
Expected: exit 0, без вывода.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/demo_bootstrap.py
git commit -m "feat(work-permits): demo-seed WP-ELEC-DEMO (электроустановки 903н)"
```

---

### Task 3: Frontend — vocab + zod-схема electrical

**Files:**
- Modify: `frontend/src/lib/workPermitVocab.ts`
- Modify: `frontend/src/types/forms/workPermits.ts`

- [ ] **Step 1: Добавить словари в vocab**

В `frontend/src/lib/workPermitVocab.ts` после `RESPIRATORY_PPE_LABELS` (строка ~104) добавить:

```ts
export const ELECTRICAL_MEASURES_LABELS: Record<string, string> = {
  disconnect: "Отключения + меры против ошибочного включения",
  lockout_signs: "Запрещающие плакаты на приводах/ключах",
  verify_no_voltage: "Проверено отсутствие напряжения",
  grounding: "Установлено заземление (ЗН / переносные)",
  barriers_signs: "Плакаты, ограждение мест и токоведущих частей",
};

export const VOLTAGE_CONDITION_LABELS: Record<string, string> = {
  de_energized: "Со снятием напряжения",
  near_live: "Без снятия напряжения вблизи токоведущих частей",
  away_live: "Без снятия напряжения вдали от токоведущих частей",
};
```

- [ ] **Step 2: Добавить коды и zod-схему**

В `frontend/src/types/forms/workPermits.ts` после `RESPIRATORY_PPE_CODES` добавить:

```ts
export const ELECTRICAL_MEASURE_CODES = [
  "disconnect", "lockout_signs", "verify_no_voltage", "grounding", "barriers_signs",
] as const;
export const VOLTAGE_CONDITION_CODES = ["de_energized", "near_live", "away_live"] as const;

export const electricalSafetySchema = z.object({
  technical_measures: z.array(z.enum(ELECTRICAL_MEASURE_CODES)).optional(),
  voltage_condition: z.enum(VOLTAGE_CONDITION_CODES).optional(),
});
export type ElectricalSafetyValues = z.infer<typeof electricalSafetySchema>;
```

Заменить строку `export const typeSpecificSchema = confinedEnvSchema.merge(fireSafetySchema).merge(gasWorksSchema);` на:

```ts
export const typeSpecificSchema = confinedEnvSchema
  .merge(fireSafetySchema)
  .merge(gasWorksSchema)
  .merge(electricalSafetySchema);
```

- [ ] **Step 3: Проверить типы**

Run:
```powershell
cd frontend; npx tsc --noEmit; cd ..
```
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/workPermitVocab.ts frontend/src/types/forms/workPermits.ts
git commit -m "feat(work-permits): фронт-словари + zod-схема электроустановок (903н)"
```

---

### Task 4: Frontend — DRY-тогглер + секция формы electrical

**Files:**
- Modify: `frontend/src/features/work-permits/WorkPermitFormDialog.tsx`
- Test (create): `frontend/src/__tests__/WorkPermitElectricalForm.test.tsx`

- [ ] **Step 1: Написать падающий тест секции electrical**

Create `frontend/src/__tests__/WorkPermitElectricalForm.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { WorkPermitFormDialog } from "@/features/work-permits/WorkPermitFormDialog";

vi.mock("@/api/workPermits", () => ({ workPermitsApi: { create: vi.fn(), update: vi.fn() } }));

describe("WorkPermitFormDialog electrical section", () => {
  it("показывает секцию электро при выборе electrical и скрывает чужие секции", () => {
    render(<WorkPermitFormDialog trigger={<button>open</button>} />);
    fireEvent.click(screen.getByText("open"));
    fireEvent.change(screen.getByLabelText("Вид работ"), { target: { value: "electrical" } });
    expect(screen.getByText(/Меры безопасности в электроустановках/i)).toBeInTheDocument();
    expect(screen.getByText("Проверено отсутствие напряжения")).toBeInTheDocument();
    expect(screen.queryByText("Системы обеспечения безопасности")).not.toBeInTheDocument();
    expect(screen.queryByText(/Защита органов дыхания/i)).not.toBeInTheDocument();
  });

  it("накапливает чекбоксы тех. мероприятий и выставляет условие по напряжению", () => {
    render(<WorkPermitFormDialog trigger={<button>open</button>} />);
    fireEvent.click(screen.getByText("open"));
    fireEvent.change(screen.getByLabelText("Вид работ"), { target: { value: "electrical" } });
    act(() => {
      fireEvent.click(screen.getByLabelText("Отключения + меры против ошибочного включения"));
      fireEvent.click(screen.getByLabelText("Установлено заземление (ЗН / переносные)"));
    });
    const cb = screen.getByLabelText("Отключения + меры против ошибочного включения") as HTMLInputElement;
    const cb2 = screen.getByLabelText("Установлено заземление (ЗН / переносные)") as HTMLInputElement;
    expect(cb.checked).toBe(true);
    expect(cb2.checked).toBe(true);
    fireEvent.change(screen.getByLabelText("Условие проведения"), { target: { value: "de_energized" } });
    expect((screen.getByLabelText("Условие проведения") as HTMLSelectElement).value).toBe("de_energized");
  });
});
```

Примечание: чекбоксы рендерятся как `<label>` с текстом — `getByLabelText` сматчит, если `<input>` обёрнут текстом в `<label>` (текущий паттерн формы — текст рядом, не `htmlFor`). Если матч не сработает, заменить на `getByText(...).closest("label")!.querySelector("input")` как в `WorkPermitFormToggles.test.tsx`. Сверить с существующим тестом перед запуском.

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run:
```powershell
cd frontend; npx vitest run src/__tests__/WorkPermitElectricalForm.test.tsx; cd ..
```
Expected: FAIL (секции electrical ещё нет).

- [ ] **Step 3: DRY-рефактор тогглеров + добавить секцию**

В `WorkPermitFormDialog.tsx`:

(a) Импорты — добавить новые коды/словари:
```ts
// в импорт из "@/types/forms/workPermits":
  ELECTRICAL_MEASURE_CODES,
  VOLTAGE_CONDITION_CODES,
// в импорт из "@/lib/workPermitVocab":
  ELECTRICAL_MEASURES_LABELS,
  VOLTAGE_CONDITION_LABELS,
```

(b) Заменить блок `toggleMean` (строки ~157-168) и `toggleResp` (строки ~170-181) одним обобщённым хендлером + оставить `selected*`-снимки для `checked`:

```ts
  // Один хендлер для всех type_specific-массивов (огневые/газоопасные/электро).
  // Читает актуальный стор через getValues — два быстрых клика до ререндера не теряют друг друга.
  const toggleTsCode = (
    field: "fire_fighting_means" | "respiratory_ppe" | "technical_measures",
    code: string,
  ) => {
    const current = (form.getValues("type_specific") ?? {}) as Record<string, string[] | undefined>;
    const next = new Set(current[field] ?? []);
    next.has(code) ? next.delete(code) : next.add(code);
    form.setValue("type_specific", {
      ...current,
      [field]: Array.from(next),
    } as WorkPermitFormValues["type_specific"]);
  };

  const selectedMeans = new Set(
    ((form.watch("type_specific") as { fire_fighting_means?: string[] } | null)?.fire_fighting_means) ?? [],
  );
  const selectedResp = new Set(
    ((form.watch("type_specific") as { respiratory_ppe?: string[] } | null)?.respiratory_ppe) ?? [],
  );
  const selectedMeasures = new Set(
    ((form.watch("type_specific") as { technical_measures?: string[] } | null)?.technical_measures) ?? [],
  );
```

(c) В JSX огневых заменить `onChange={() => toggleMean(code)}` на `onChange={() => toggleTsCode("fire_fighting_means", code)}`; в JSX газоопасных — `onChange={() => toggleTsCode("respiratory_ppe", code)}`.

(d) После блока `gas_hazardous` (строка ~345) добавить секцию electrical:

```tsx
          {form.watch("work_type") === "electrical" && (
            <div className="space-y-2">
              <Label>Меры безопасности в электроустановках (903н)</Label>
              <Label className="text-xs">Технические мероприятия подготовки места</Label>
              <div className="flex flex-wrap gap-3">
                {ELECTRICAL_MEASURE_CODES.map((code) => (
                  <label key={code} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={selectedMeasures.has(code)}
                      onChange={() => toggleTsCode("technical_measures", code)}
                    />
                    {ELECTRICAL_MEASURES_LABELS[code]}
                  </label>
                ))}
              </div>
              <div className="space-y-1">
                <Label htmlFor="voltage_condition" className="text-xs">Условие проведения</Label>
                <select
                  id="voltage_condition"
                  className="h-10 w-full rounded-md border px-3"
                  value={(form.watch("type_specific")?.voltage_condition as string) ?? ""}
                  onChange={(e) =>
                    form.setValue("type_specific", {
                      ...(form.watch("type_specific") ?? {}),
                      voltage_condition: (e.target.value || undefined) as never,
                    })
                  }
                >
                  <option value="">—</option>
                  {VOLTAGE_CONDITION_CODES.map((c) => (
                    <option key={c} value={c}>{VOLTAGE_CONDITION_LABELS[c]}</option>
                  ))}
                </select>
              </div>
            </div>
          )}
```

(e) В `toBody` (строка ~116) расширить whitelist:

```ts
    type_specific: ["confined_space", "hot_work", "gas_hazardous", "electrical"].includes(v.work_type)
      ? (v.type_specific ?? null)
      : null,
```

- [ ] **Step 4: Прогнать новый + регрессионные тоггл-тесты**

Run:
```powershell
cd frontend; npx vitest run src/__tests__/WorkPermitElectricalForm.test.tsx src/__tests__/WorkPermitGasWorksForm.test.tsx src/__tests__/WorkPermitHotWorkForm.test.tsx src/__tests__/WorkPermitFormToggles.test.tsx; cd ..
```
Expected: все passed (новый electrical + огневые/газоопасные/тоггл-регресс после DRY).

- [ ] **Step 5: tsc + eslint изменённых**

Run:
```powershell
cd frontend; npx tsc --noEmit; npx eslint --max-warnings=0 src/features/work-permits/WorkPermitFormDialog.tsx src/__tests__/WorkPermitElectricalForm.test.tsx; cd ..
```
Expected: оба exit 0.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/work-permits/WorkPermitFormDialog.tsx frontend/src/__tests__/WorkPermitElectricalForm.test.tsx
git commit -m "feat(work-permits): секция формы электроустановок (903н) + DRY toggleTsCode"
```

---

### Task 5: Frontend — read-only блок деталь-страницы

**Files:**
- Modify: `frontend/src/pages/work-permits/WorkPermitDetailPage.tsx`
- Test (modify): `frontend/src/__tests__/WorkPermitDetailPage.test.tsx`

- [ ] **Step 1: Написать падающий тест блока**

В `frontend/src/__tests__/WorkPermitDetailPage.test.tsx` добавить тест (сверить фабрику данных/моки с существующими тестами файла, переиспользовать их хелперы рендера):

```tsx
it("рендерит блок электроустановок (условие + мероприятия)", async () => {
  // переиспользовать существующий рендер-хелпер файла с wp:
  //   work_type: "electrical",
  //   type_specific: { technical_measures: ["disconnect"], voltage_condition: "de_energized" }
  // затем:
  expect(await screen.findByText(/Меры безопасности в электроустановках/i)).toBeInTheDocument();
  expect(screen.getByText(/Со снятием напряжения/i)).toBeInTheDocument();
});
```

Примечание: точную форму рендера (provider, router, mock api) взять из соседних тестов в этом же файле — НЕ выдумывать. Если в файле есть фабрика `makeWp(overrides)` / `renderDetail(wp)`, использовать её с override на electrical.

- [ ] **Step 2: Прогнать — падает**

Run:
```powershell
cd frontend; npx vitest run src/__tests__/WorkPermitDetailPage.test.tsx; cd ..
```
Expected: новый тест FAIL.

- [ ] **Step 3: Добавить блок в деталь-страницу**

В `WorkPermitDetailPage.tsx` после блока `gas_hazardous` (строка ~364) добавить:

```tsx
          {wp.work_type === "electrical" && wp.type_specific ? (
            <div className="text-sm">
              <div className="font-medium">Меры безопасности в электроустановках (903н)</div>
              {(wp.type_specific as { voltage_condition?: string }).voltage_condition ? (
                <div>
                  Условие проведения:{" "}
                  {VOLTAGE_CONDITION_LABELS[
                    (wp.type_specific as { voltage_condition: string }).voltage_condition
                  ] ?? "—"}
                </div>
              ) : null}
              {((wp.type_specific as { technical_measures?: string[] }).technical_measures ?? []).length ? (
                <div>
                  Технические мероприятия:{" "}
                  {((wp.type_specific as { technical_measures: string[] }).technical_measures)
                    .map((c) => ELECTRICAL_MEASURES_LABELS[c] ?? c)
                    .join("; ")}
                </div>
              ) : null}
            </div>
          ) : null}
```

Добавить импорт в шапку файла:
```ts
import { ELECTRICAL_MEASURES_LABELS, VOLTAGE_CONDITION_LABELS } from "@/lib/workPermitVocab";
```
(если из `workPermitVocab` уже импортируется набор — дописать в существующий импорт.)

- [ ] **Step 4: Прогнать — зелёный**

Run:
```powershell
cd frontend; npx vitest run src/__tests__/WorkPermitDetailPage.test.tsx; cd ..
```
Expected: все passed.

- [ ] **Step 5: tsc + eslint**

Run:
```powershell
cd frontend; npx tsc --noEmit; npx eslint --max-warnings=0 src/pages/work-permits/WorkPermitDetailPage.tsx; cd ..
```
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/work-permits/WorkPermitDetailPage.tsx frontend/src/__tests__/WorkPermitDetailPage.test.tsx
git commit -m "feat(work-permits): read-only блок электроустановок на деталь-странице"
```

---

### Task 6: Верификация когорт + handoff

**Files:**
- Modify: `AI_IMPLEMENTATION_REPORT.md`

- [ ] **Step 1: Backend контурный + миграционный когорт**

Run (PowerShell→файл):
```powershell
.venv\Scripts\python.exe -m pytest backend/tests -k "work_permit or profile or confined or migration or downgrade or mapper" -q 2>&1 | Tee-Object pytest_cohort.txt
```
Expected: RC=0, все passed. Миграционная часть зелёная подтверждает: **миграции не задеты** (профиль-слой их не трогает).

- [ ] **Step 2: Frontend сборка + наряд-тесты**

Run:
```powershell
cd frontend; npm run build; npx vitest run src/__tests__/WorkPermit*; cd ..
```
Expected: BUILD_RC=0; все наряд-vitest passed.

- [ ] **Step 3: Дописать handoff в `AI_IMPLEMENTATION_REPORT.md`**

Добавить новую секцию `## Last Agent Handoff (2026-06-23, ЭЛЕКТРОУСТАНОВКИ 903н — 5-й вид через слой профилей)` в начало файла (после заголовка `# AI Implementation Report`), с: что построено, дивиденд слоя (правки только profiles.py, миграции нет), DRY toggleTsCode, отложенное (группы электробезопасности, DRY seed, земляные), результаты тестов.

- [ ] **Step 4: Commit**

```bash
git add AI_IMPLEMENTATION_REPORT.md
git commit -m "docs: handoff — электроустановки 903н (5-й вид нарядов)"
```

- [ ] **Step 5: Финальное холистическое ревью**

Запросить code-review по диффу ветки (см. `superpowers:requesting-code-review`). Зафиксировать вердикт; критичное — починить, non-blocking — в handoff.

---

## Self-Review (выполнено при написании плана)

- **Покрытие спеки:** словари ✓(T1) · structured_kind ✓(T1) · валидация ✓(T1 юнит+схема) · печатная секция ✓(T1 build_structured_section) · vocab ✓(T3) · zod ✓(T3) · DRY toggleTsCode ✓(T4) · секция формы ✓(T4) · toBody whitelist ✓(T4) · деталь-блок ✓(T5) · demo-seed ✓(T2) · тесты ✓(T1/T4/T5/T6) · миграционный когорт зелёный = «без миграции» ✓(T6).
- **Плейсхолдеры:** нет TBD/TODO; весь код приведён.
- **Согласованность типов:** `electrical_safety` (structured_kind), ключи `technical_measures`/`voltage_condition`, коды мероприятий/условий — идентичны между profiles.py, zod, seed, тестами. `toggleTsCode` union-поле включает все 3 потребителя.
- **Отложено явно:** группы электробезопасности (per-person+миграция), DRY seed, редактор замеров, земляные работы.
