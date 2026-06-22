# Тираж наряда-допуска на огневые работы (1479) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить огневые работы (ППР РФ № 1479) как третий полноценный вид наряда-допуска через слой профилей: структурная секция «средства пожаротушения + замеры концентрации».

**Architecture:** Полиморфный шов `domains/work_permits/profiles.py` уже несёт per-type-специфику; бэкенд-обвязка (схемы / CRUD / печать) generic и не меняется. Новый вид = новый `structured_kind="fire_safety"` + словарь + ветки валидации/сборки в `profiles.py`, плюс фронт-секция, demo-seed и тесты. **Миграции нет** — колонка `type_specific JSON` уже существует (wp06).

**Tech Stack:** Backend — Python/FastAPI/SQLAlchemy/Pydantic v2, pytest. Frontend — React/TS/Vite, react-hook-form + zod, vitest. Среда: Win+Py3.13.7/.venv (канон Py3.12.12 = CI, выключен). Сигнал прогона — EXIT-код / маркер `===RC=$LASTEXITCODE===`.

**Спека:** `docs/superpowers/specs/2026-06-22-work-permit-hot-work-1479-design.md`
**Ветка:** `feat/work-permit-hot-work-1479` (уже создана от `main`, спек закоммичен).

---

## Карта файлов

| Файл | Действие | Ответственность |
|---|---|---|
| `backend/app/domains/work_permits/profiles.py` | Modify | `FIRE_FIGHTING_MEANS`, `hot_work.structured_kind="fire_safety"`, хелперы `_validate_gas_analysis`/`_gas_table`, ветки `fire_safety` |
| `tests/test_work_permit_profiles.py` | Modify | unit-тесты профиля огневых |
| `backend/tests/test_work_permit_confined_schemas.py` | Modify | 422-матрица для `hot_work` |
| `tests/test_work_permit_print_service.py` | Modify | DOCX-тест огневого наряда |
| `backend/app/services/demo_bootstrap.py` | Modify | `_seed_work_permit_hot_work_demo` + вызов |
| `frontend/src/lib/workPermitVocab.ts` | Modify | `FIRE_FIGHTING_MEANS_LABELS` |
| `frontend/src/types/forms/workPermits.ts` | Modify | `FIRE_FIGHTING_MEANS_CODES`, `fireSafetySchema`, расширение `type_specific` |
| `frontend/src/features/work-permits/WorkPermitFormDialog.tsx` | Modify | секция `hot_work` + обобщение `toBody` |
| `frontend/src/pages/work-permits/WorkPermitDetailPage.tsx` | Modify | read-only блок огневых |
| `frontend/src/__tests__/WorkPermitHotWorkForm.test.tsx` | Create | vitest на огневую секцию |

---

## Task 1: Профиль `hot_work` → `fire_safety` + общие газо-хелперы

**Files:**
- Modify: `backend/app/domains/work_permits/profiles.py`
- Test: `tests/test_work_permit_profiles.py`

- [ ] **Step 1: Дописать падающие unit-тесты профиля огневых**

В конец `tests/test_work_permit_profiles.py` добавить:

```python
def test_validate_hot_work_accepts_valid_payload():
    pr.validate_type_specific(
        "hot_work",
        {
            "fire_fighting_means": ["extinguisher_powder", "sand"],
            "gas_analysis": [{"parameter": "flammable", "value": "0", "norm": "≤ 10 % НКПР"}],
        },
    )


def test_validate_hot_work_rejects_unknown_key():
    with pytest.raises(ValueError):
        pr.validate_type_specific("hot_work", {"ventilation": "forced"})


def test_validate_hot_work_rejects_bad_means():
    with pytest.raises(ValueError):
        pr.validate_type_specific("hot_work", {"fire_fighting_means": ["laser"]})


def test_validate_hot_work_rejects_bad_gas_parameter():
    with pytest.raises(ValueError):
        pr.validate_type_specific(
            "hot_work", {"gas_analysis": [{"parameter": "xx", "value": "1"}]}
        )


def test_build_section_hot_work_means_and_gas():
    sec = pr.build_structured_section(
        "hot_work",
        safety_systems=None,
        type_specific={
            "fire_fighting_means": ["extinguisher_powder", "sand"],
            "gas_analysis": [{"parameter": "flammable", "value": "0", "norm": "≤ 10 % НКПР"}],
        },
    )
    assert isinstance(sec, StructuredSection)
    assert "1479" in sec.title
    assert any(k == "Средства пожаротушения" for k, _ in sec.kv)
    assert "Огнетушитель порошковый" in sec.kv[0][1]
    assert sec.table is not None and "Горючие" in sec.table.rows[0][0]


def test_build_section_hot_work_empty_returns_none():
    assert (
        pr.build_structured_section("hot_work", safety_systems=None, type_specific={}) is None
    )
```

- [ ] **Step 2: Запустить — убедиться, что тесты падают**

Run: `.venv\Scripts\python.exe -m pytest tests/test_work_permit_profiles.py -q`
Expected: FAIL — `hot_work` сейчас `structured_kind=None`, поэтому `validate_type_specific("hot_work", {...})` бросает «not accepted» (тест accept падает), а `build_structured_section` возвращает `None` (тесты build падают).

- [ ] **Step 3: Реализация в `profiles.py`**

(а) Под блоком словарей ОЗП (после `_GAS_KEYS = {...}`, строка ~27) добавить словарь средств пожаротушения:

```python
# --- словарь средств пожаротушения (огневые работы, ППР 1479) ---
FIRE_FIGHTING_MEANS = {
    "extinguisher_powder": "Огнетушитель порошковый",
    "extinguisher_co2": "Огнетушитель углекислотный",
    "water": "Вода (ёмкость/ведро)",
    "sand": "Ящик с песком",
    "felt": "Кошма / асбестовое полотно",
    "fire_hose": "Пожарный кран/рукав",
}
```

(б) В реестре `PROFILES` сменить `structured_kind` у `hot_work` с `None` на `"fire_safety"`:

```python
    "hot_work": WorkTypeProfile(
        "hot_work",
        "Огневые работы",
        "Постановление Правительства РФ от 16.09.2020 № 1479 (ППР)",
        "fire_safety",
    ),
```

(в) Перед `validate_type_specific` добавить общий хелпер замеров (вынос инлайн-логики ОЗП):

```python
def _validate_gas_analysis(rows) -> None:
    """Общая валидация таблицы замеров (ОЗП и огневые). None — ок."""
    if rows is None:
        return
    if not isinstance(rows, list):
        raise ValueError("gas_analysis must be a list")
    for r in rows:
        if not isinstance(r, dict):
            raise ValueError("gas_analysis row must be an object")
        bad = set(r) - _GAS_KEYS
        if bad:
            raise ValueError(f"unknown gas_analysis keys: {sorted(bad)}")
        if r.get("parameter") not in GAS_PARAMETERS:
            raise ValueError(f"invalid gas parameter: {r.get('parameter')!r}")
```

(г) Заменить тело `validate_type_specific` целиком на ветвление по `kind`:

```python
def validate_type_specific(work_type: str, payload: dict | None) -> None:
    """Raise ValueError если type_specific не соответствует профилю вида работ.

    None/пустой — всегда ок. Виды без структурной секции не принимают непустой payload
    (включая height — он использует safety_systems-колонку).
    """
    if not payload:
        return
    kind = profile_for(work_type).structured_kind
    if kind == "confined_env":
        unknown = set(payload) - {"gas_analysis", "ventilation"}
        if unknown:
            raise ValueError(f"unknown type_specific keys: {sorted(unknown)}")
        vent = payload.get("ventilation")
        if vent is not None and vent not in VENTILATION_MODES:
            raise ValueError(f"invalid ventilation: {vent!r}")
        _validate_gas_analysis(payload.get("gas_analysis"))
    elif kind == "fire_safety":
        unknown = set(payload) - {"fire_fighting_means", "gas_analysis"}
        if unknown:
            raise ValueError(f"unknown type_specific keys: {sorted(unknown)}")
        means = payload.get("fire_fighting_means")
        if means is not None:
            if not isinstance(means, list):
                raise ValueError("fire_fighting_means must be a list")
            for m in means:
                if m not in FIRE_FIGHTING_MEANS:
                    raise ValueError(f"invalid fire_fighting_means: {m!r}")
        _validate_gas_analysis(payload.get("gas_analysis"))
    else:
        raise ValueError(f"type_specific is not accepted for work_type {work_type!r}")
```

(д) Перед `build_structured_section` добавить общий построитель таблицы замеров:

```python
def _gas_table(rows):
    """StructuredTable из строк замеров (ОЗП и огневые) или None."""
    if not rows:
        return None
    return pf.StructuredTable(
        headers=["Параметр", "Значение", "Норма", "Замер"],
        rows=[
            [
                GAS_PARAMETERS.get(r.get("parameter"), r.get("parameter") or ""),
                str(r.get("value") or ""),
                str(r.get("norm") or ""),
                str(r.get("measured_at") or ""),
            ]
            for r in rows
        ],
    )
```

(е) В `build_structured_section` заменить ветку `confined_env` на использование `_gas_table` и добавить ветку `fire_safety`:

```python
    if kind == "confined_env":
        ts = type_specific or {}
        kv: list[tuple[str, str]] = []
        vent = ts.get("ventilation")
        if vent:
            kv.append(("Вентиляция", VENTILATION_MODES.get(vent, vent)))
        table = _gas_table(ts.get("gas_analysis") or [])
        if not kv and table is None:
            return None
        return pf.StructuredSection(
            title="Анализ воздушной среды и вентиляция (902н)", kv=kv, table=table
        )
    if kind == "fire_safety":
        ts = type_specific or {}
        kv = []
        means = ts.get("fire_fighting_means") or []
        if means:
            kv.append(
                ("Средства пожаротушения", ", ".join(FIRE_FIGHTING_MEANS.get(m, m) for m in means))
            )
        table = _gas_table(ts.get("gas_analysis") or [])
        if not kv and table is None:
            return None
        return pf.StructuredSection(
            title="Пожарная безопасность огневых работ (1479)", kv=kv, table=table
        )
    return None
```

- [ ] **Step 4: Запустить — все тесты профиля зелёные (ОЗП-регресс + огневые)**

Run: `.venv\Scripts\python.exe -m pytest tests/test_work_permit_profiles.py -q`
Expected: PASS (включая `test_validate_confined_*`/`test_build_section_confined_*` — поведение не изменилось после выноса хелперов; `test_registry_covers_all_work_types` держится).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/work_permits/profiles.py tests/test_work_permit_profiles.py
git commit -m "feat(work-permits): профиль огневых работ (1479) — fire_safety structured_kind"
```

---

## Task 2: Схема-валидация (422) + печать огневого наряда

Прод-код не меняется (схемы/печать generic) — задача доказывает, что обвязка подхватывает новый профиль. Тесты должны пройти сразу после Task 1.

**Files:**
- Test: `backend/tests/test_work_permit_confined_schemas.py`
- Test: `tests/test_work_permit_print_service.py`

- [ ] **Step 1: Дописать 422-кейсы для `hot_work`**

В конец `backend/tests/test_work_permit_confined_schemas.py` добавить:

```python
def test_create_accepts_valid_hot_work_type_specific():
    m = WorkPermitCreate(
        work_type="hot_work",
        zone_text="эстакада №3",
        type_specific={
            "fire_fighting_means": ["extinguisher_powder", "sand"],
            "gas_analysis": [{"parameter": "flammable", "value": "0", "norm": "≤ 10 % НКПР"}],
        },
    )
    assert m.type_specific["fire_fighting_means"] == ["extinguisher_powder", "sand"]


def test_create_rejects_bad_fire_fighting_means():
    with pytest.raises(ValidationError):
        WorkPermitCreate(
            work_type="hot_work", zone_text="эстакада",
            type_specific={"fire_fighting_means": ["laser"]},
        )


def test_create_rejects_ventilation_on_hot_work():
    with pytest.raises(ValidationError):
        WorkPermitCreate(
            work_type="hot_work", zone_text="эстакада",
            type_specific={"ventilation": "forced"},
        )
```

- [ ] **Step 2: Дописать DOCX-тест огневого наряда**

В конец `tests/test_work_permit_print_service.py` добавить:

```python
@pytest.mark.asyncio
async def test_render_hot_work_uses_1479_and_fire_means(sessionmaker, data_factory):
    tenant, (foreman,) = await _persons(data_factory, "Fedor")
    tid = str(tenant.id)
    async with sessionmaker() as session:
        wp = await svc.create_work_permit(
            session,
            tenant_id=tid,
            work_type="hot_work",
            zone_text="эстакада №3",
            number="НД-ОГН-1",
            type_specific={
                "fire_fighting_means": ["extinguisher_powder", "sand"],
                "gas_analysis": [{"parameter": "flammable", "value": "0", "norm": "≤ 10 % НКПР"}],
            },
        )
        await svc.add_member(
            session, tenant_id=tid, work_permit_id=wp.id, person_id=foreman.id, role="foreman"
        )
        rendered = await render_work_permit(
            session, tenant=tenant, permit_id=wp.id, fmt="docx", with_letterhead=False
        )
        text = _docx_text(rendered.content)
        assert "1479" in text
        assert "Огнетушитель порошковый" in text and "Ящик с песком" in text
        assert "Горючие" in text and "0" in text
        assert "782н" not in text
```

- [ ] **Step 3: Запустить оба файла**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_work_permit_confined_schemas.py tests/test_work_permit_print_service.py -q`
Expected: PASS (все, включая существующие ОЗП/высота — не регрессировали).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_work_permit_confined_schemas.py tests/test_work_permit_print_service.py
git commit -m "test(work-permits): 422-матрица и печать огневого наряда (1479)"
```

---

## Task 3: Demo-seed огневого наряда

**Files:**
- Modify: `backend/app/services/demo_bootstrap.py`

- [ ] **Step 1: Добавить seed-функцию (зеркало ОЗП-seed)**

После `_seed_work_permit_confined_demo` (заканчивается ~строка 393) добавить:

```python
async def _seed_work_permit_hot_work_demo(session, tenant_db_id: str, person) -> None:
    """Демо-наряд огневых работ (1479) со средствами пожаротушения и замером — печатается «из коробки». Идемпотентно."""
    from app.models.work_permit import WorkPermit, WorkPermitMember

    wp = (
        await session.execute(
            select(WorkPermit).where(
                WorkPermit.tenant_id == tenant_db_id,
                WorkPermit.number == "WP-HOT-DEMO",
            )
        )
    ).scalar_one_or_none()
    if wp is None:
        wp = WorkPermit(
            tenant_id=tenant_db_id,
            number="WP-HOT-DEMO",
            work_type="hot_work",
            zone_text="Эстакада №3, участок сварки",
            status="draft",
            type_specific={
                "fire_fighting_means": ["extinguisher_powder", "sand"],
                "gas_analysis": [{"parameter": "flammable", "value": "0", "norm": "≤ 10 % НКПР"}],
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

- [ ] **Step 2: Зарегистрировать вызов в `bootstrap_demo_tenant`**

Сразу после строки `await _seed_work_permit_confined_demo(session, tenant_db_id, person)` (~строка 619) добавить:

```python
            await _seed_work_permit_hot_work_demo(session, tenant_db_id, person)
```

(Тот же отступ, что у вызова ОЗП-seed — внутри того же блока.)

- [ ] **Step 3: Smoke — bootstrap импортируется без синтаксических ошибок**

Run: `.venv\Scripts\python.exe -c "import app.services.demo_bootstrap as m; assert hasattr(m, '_seed_work_permit_hot_work_demo')"`
Expected: без ошибок (exit 0).

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/demo_bootstrap.py
git commit -m "feat(work-permits): demo-seed огневого наряда (WP-HOT-DEMO)"
```

---

## Task 4: Фронт — словарь + zod-схема формы

**Files:**
- Modify: `frontend/src/lib/workPermitVocab.ts`
- Modify: `frontend/src/types/forms/workPermits.ts`

- [ ] **Step 1: Добавить словарь меток средств пожаротушения**

В `frontend/src/lib/workPermitVocab.ts` после `VENTILATION_LABELS` (перед `labelOf`) добавить:

```typescript
export const FIRE_FIGHTING_MEANS_LABELS: Record<string, string> = {
  extinguisher_powder: "Огнетушитель порошковый",
  extinguisher_co2: "Огнетушитель углекислотный",
  water: "Вода (ёмкость/ведро)",
  sand: "Ящик с песком",
  felt: "Кошма / асбестовое полотно",
  fire_hose: "Пожарный кран/рукав",
};
```

- [ ] **Step 2: Расширить zod-схему формы под огневые**

В `frontend/src/types/forms/workPermits.ts`:

(а) После `VENTILATION_CODES` (строка 8) добавить коды средств:

```typescript
export const FIRE_FIGHTING_MEANS_CODES = [
  "extinguisher_powder", "extinguisher_co2", "water", "sand", "felt", "fire_hose",
] as const;
```

(б) После `confinedEnvSchema`/`ConfinedEnvValues` (строка 21) добавить огневую схему и объединить:

```typescript
export const fireSafetySchema = z.object({
  fire_fighting_means: z.array(z.enum(FIRE_FIGHTING_MEANS_CODES)).optional(),
  gas_analysis: z.array(gasMeasurementSchema).optional(),
});
export type FireSafetyValues = z.infer<typeof fireSafetySchema>;

// Надмножество ключей обоих видов — клиентская форма; серверная validate_type_specific — источник истины по виду.
export const typeSpecificSchema = confinedEnvSchema.merge(fireSafetySchema);
```

(в) В `workPermitSchema` заменить строку 39 `type_specific: confinedEnvSchema.nullable().optional(),` на:

```typescript
  type_specific: typeSpecificSchema.nullable().optional(),
```

- [ ] **Step 3: Проверить типы (tsc через build позже; здесь — точечно)**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json`
Expected: без ошибок (новые экспорты согласованы; `WorkPermitFormValues.type_specific` теперь надмножество).
*(Если в репо `tsc` запускается только через `npm run build` — отложить проверку до Task 7; не блокирующий шаг.)*

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/workPermitVocab.ts frontend/src/types/forms/workPermits.ts
git commit -m "feat(work-permits): фронт-словарь и zod-схема огневых работ"
```

---

## Task 5: Фронт — секция огневых на форме + обобщение `toBody` + vitest

**Files:**
- Modify: `frontend/src/features/work-permits/WorkPermitFormDialog.tsx`
- Create: `frontend/src/__tests__/WorkPermitHotWorkForm.test.tsx`

- [ ] **Step 1: Написать падающий vitest**

Создать `frontend/src/__tests__/WorkPermitHotWorkForm.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { WorkPermitFormDialog } from "@/features/work-permits/WorkPermitFormDialog";

vi.mock("@/api/workPermits", () => ({ workPermitsApi: { create: vi.fn(), update: vi.fn() } }));

describe("WorkPermitFormDialog hot_work section", () => {
  it("показывает секцию огневых при выборе hot_work и скрывает safety_systems/ОЗП", async () => {
    render(<WorkPermitFormDialog trigger={<button>open</button>} />);
    fireEvent.click(screen.getByText("open"));
    fireEvent.change(screen.getByLabelText("Вид работ"), { target: { value: "hot_work" } });
    expect(screen.getByText(/Средства пожаротушения/i)).toBeInTheDocument();
    expect(screen.getByText("Огнетушитель порошковый")).toBeInTheDocument();
    expect(screen.queryByText("Системы обеспечения безопасности")).not.toBeInTheDocument();
    expect(screen.queryByText(/Анализ воздушной среды/i)).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Запустить — упадёт (секции нет)**

Run: `cd frontend && npx vitest run src/__tests__/WorkPermitHotWorkForm.test.tsx`
Expected: FAIL — текст «Средства пожаротушения» не найден.

- [ ] **Step 3: Реализация — импорт словаря/кодов, чек-лист, toBody**

(а) В импортах из `@/types/forms/workPermits` добавить `FIRE_FIGHTING_MEANS_CODES`:

```typescript
import {
  SAFETY_SYSTEM_CODES,
  GAS_PARAMETER_CODES,
  VENTILATION_CODES,
  FIRE_FIGHTING_MEANS_CODES,
  workPermitSchema,
  type WorkPermitFormValues,
} from "@/types/forms/workPermits";
```

(б) В импортах из `@/lib/workPermitVocab` добавить `FIRE_FIGHTING_MEANS_LABELS`:

```typescript
import {
  SAFETY_SYSTEM_LABELS,
  WORK_TYPE_LABELS,
  LEGAL_REFERENCE_LABELS,
  GAS_PARAMETER_LABELS,
  VENTILATION_LABELS,
  FIRE_FIGHTING_MEANS_LABELS,
} from "@/lib/workPermitVocab";
```

(в) Обобщить `toBody` строка 112 — `type_specific` сериализуется для ОЗП И огневых:

```typescript
    type_specific: ["confined_space", "hot_work"].includes(v.work_type)
      ? (v.type_specific ?? null)
      : null,
```

(г) После `toggleSystem` (строка 134) добавить toggler средств пожаротушения:

```typescript
  const selectedMeans = new Set(
    ((form.watch("type_specific") as { fire_fighting_means?: string[] } | null)?.fire_fighting_means) ?? [],
  );
  const toggleMean = (code: (typeof FIRE_FIGHTING_MEANS_CODES)[number]) => {
    const next = new Set(selectedMeans);
    next.has(code) ? next.delete(code) : next.add(code);
    form.setValue("type_specific", {
      ...(form.watch("type_specific") ?? {}),
      fire_fighting_means: Array.from(next),
    } as WorkPermitFormValues["type_specific"]);
  };
```

(д) После блока `confined_space` (заканчивается строка 251) добавить блок `hot_work`:

```tsx
          {form.watch("work_type") === "hot_work" && (
            <div className="space-y-2">
              <Label>Пожарная безопасность огневых работ (1479)</Label>
              <div className="flex flex-wrap gap-3">
                {FIRE_FIGHTING_MEANS_CODES.map((code) => (
                  <label key={code} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={selectedMeans.has(code)}
                      onChange={() => toggleMean(code)}
                    />
                    {FIRE_FIGHTING_MEANS_LABELS[code]}
                  </label>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">
                Параметры замеров концентрации: {GAS_PARAMETER_CODES.map((c) => GAS_PARAMETER_LABELS[c]).join(", ")}.
                Подготовка/очистка места и контроль после работ — в полях «Мероприятия» / «Особые условия».
              </p>
            </div>
          )}
```

- [ ] **Step 4: Запустить — обе формы зелёные**

Run: `cd frontend && npx vitest run src/__tests__/WorkPermitHotWorkForm.test.tsx src/__tests__/WorkPermitConfinedForm.test.tsx`
Expected: PASS (огневая секция рендерится; ОЗП-тест не регрессировал).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/work-permits/WorkPermitFormDialog.tsx frontend/src/__tests__/WorkPermitHotWorkForm.test.tsx
git commit -m "feat(work-permits): секция огневых работ на форме наряда + toBody"
```

---

## Task 6: Фронт — read-only блок огневых на деталь-странице

**Files:**
- Modify: `frontend/src/pages/work-permits/WorkPermitDetailPage.tsx`

- [ ] **Step 1: Добавить импорт `FIRE_FIGHTING_MEANS_LABELS`**

В импорт из `@/lib/workPermitVocab` (строки 21-28) добавить `FIRE_FIGHTING_MEANS_LABELS`:

```typescript
import {
  MEMBER_ROLE_LABELS,
  SAFETY_SYSTEM_LABELS,
  WORK_TYPE_LABELS,
  VENTILATION_LABELS,
  GAS_PARAMETER_LABELS,
  FIRE_FIGHTING_MEANS_LABELS,
  labelOf,
} from "@/lib/workPermitVocab";
```

- [ ] **Step 2: Добавить read-only блок огневых после ОЗП-блока**

После закрывающего `) : null}` блока `confined_space` (строка 328) добавить:

```tsx
          {wp.work_type === "hot_work" && wp.type_specific ? (
            <div className="text-sm">
              <div className="font-medium">Пожарная безопасность огневых работ (1479)</div>
              {((wp.type_specific as { fire_fighting_means?: string[] }).fire_fighting_means ?? []).length ? (
                <div>
                  Средства пожаротушения:{" "}
                  {((wp.type_specific as { fire_fighting_means: string[] }).fire_fighting_means)
                    .map((c) => FIRE_FIGHTING_MEANS_LABELS[c] ?? c)
                    .join(", ")}
                </div>
              ) : null}
              {((wp.type_specific as { gas_analysis?: Array<{ parameter: string; value: string }> }).gas_analysis ?? []).map((m, i) => (
                <div key={i}>{GAS_PARAMETER_LABELS[m.parameter] ?? m.parameter}: {m.value}</div>
              ))}
            </div>
          ) : null}
```

- [ ] **Step 3: Проверить tsc/build**

Run: `cd frontend && npm run build`
Expected: BUILD ok (TS чист; маркер `===BUILD_RC=0===` если оборачивать в Tee).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/work-permits/WorkPermitDetailPage.tsx
git commit -m "feat(work-permits): read-only блок огневых на деталь-странице наряда"
```

---

## Task 7: Регрессия контура + фронт-билд + handoff

**Files:**
- Modify: `AI_IMPLEMENTATION_REPORT.md` (новый handoff-блок сверху)

- [ ] **Step 1: Бэкенд контурный когорт**

Run (PowerShell, foreground + маркер):
```powershell
.venv\Scripts\python.exe -m pytest `
  tests/test_work_permit_profiles.py `
  backend/tests/test_work_permit_confined_schemas.py `
  tests/test_work_permit_print_service.py `
  tests/test_work_permit_service.py `
  tests/api/test_work_permit_782n_fields.py `
  tests/test_work_permit_type_specific_migration.py `
  -q 2>&1 | Tee-Object fire_cohort.txt; Add-Content fire_cohort.txt "===RC=$LASTEXITCODE==="
```
Expected: маркер `===RC=0===`, ноль `failed`/`error`.

- [ ] **Step 2: Миграционный когорт (ничего не сломано — миграции мы не трогали)**

Run:
```powershell
.venv\Scripts\python.exe -m pytest -k "migration or downgrade or mapper" -q 2>&1 | Tee-Object mig_cohort.txt; Add-Content mig_cohort.txt "===RC=$LASTEXITCODE==="
```
Expected: `===RC=0===`.

- [ ] **Step 3: Фронт — build + vitest**

Run:
```powershell
cd frontend; npm run build 2>&1 | Tee-Object ..\fe_build.txt; Add-Content ..\fe_build.txt "===BUILD_RC=$LASTEXITCODE==="
npx vitest run src/__tests__/WorkPermitHotWorkForm.test.tsx src/__tests__/WorkPermitConfinedForm.test.tsx
```
Expected: build `===BUILD_RC=0===`; vitest — оба passed.

- [ ] **Step 4: Дописать handoff-блок в `AI_IMPLEMENTATION_REPORT.md`**

Вставить новый блок СВЕРХУ (после `# AI Implementation Report`), формат — как у предыдущих handoff (дата, ГЛАВНОЕ, Построено, Тесты, Отложено, Next). Зафиксировать: третий вид через слой профилей, без миграции, буквальный паритет фронта с ОЗП, отложенный построчный редактор замеров.

- [ ] **Step 5: Удалить временные лог-файлы и закоммитить handoff**

```bash
rm -f fire_cohort.txt mig_cohort.txt fe_build.txt
git add AI_IMPLEMENTATION_REPORT.md
git commit -m "docs: handoff — тираж наряда-допуска на огневые работы (1479)"
```

---

## Self-Review (выполнено при написании плана)

**1. Spec coverage:**
- §2 профиль `hot_work`/`fire_safety` + `FIRE_FIGHTING_MEANS` + вынос `_validate_gas_analysis` → Task 1. ✓
- §3 форма/валидация/сборка секции → Task 1. ✓
- §4 generic-обвязка без правок (доказано тестами) → Task 2. ✓
- §5 фронт: словарь+схема (Task 4), форма+toBody (Task 5), деталь-страница (Task 6). ✓
- §6 demo-seed → Task 3. ✓
- §7 тесты: profiles (T1), schemas+print (T2), vitest (T5), регрессия (T7). ✓
- §8 YAGNI (редактор замеров отложен) — фронт-задачи редактор не строят. ✓

**2. Placeholder scan:** код в каждом шаге конкретный; нет «TBD»/«добавить валидацию». ✓ (handoff-текст Task 7 шаг 4 — содержательное описание формата, не код-плейсхолдер.)

**3. Type consistency:** `structured_kind="fire_safety"` единообразно в validate/build; `FIRE_FIGHTING_MEANS` (backend) ↔ `FIRE_FIGHTING_MEANS_LABELS`/`FIRE_FIGHTING_MEANS_CODES` (frontend) — коды совпадают (`extinguisher_powder`/`extinguisher_co2`/`water`/`sand`/`felt`/`fire_hose`). `_gas_table`/`_validate_gas_analysis` — общие, имена согласованы. `typeSpecificSchema` используется в `workPermitSchema`. ✓

**4. Корректность образцов:** seed-функция `_seed_work_permit_confined_demo(session, tenant_db_id, person)` — 3 аргумента (без site); огневой seed зеркалит точно. Тест-харнес печати использует `_persons`/`_docx_text` — переиспользуются. ✓
