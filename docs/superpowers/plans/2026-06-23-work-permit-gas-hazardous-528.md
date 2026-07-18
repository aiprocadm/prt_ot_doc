# Тираж наряда-допуска на газоопасные работы (ФНП 528) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить газоопасные работы (Приказ Ростехнадзора № 528, ФНП) как четвёртый полноценный вид наряда-допуска через слой профилей: структурная секция «СИЗ органов дыхания + замеры концентрации».

**Architecture:** Полиморфный шов `domains/work_permits/profiles.py` уже несёт per-type-специфику; бэкенд-обвязка (схемы / CRUD / печать) generic и не меняется. Новый вид = новый `structured_kind="gas_works"` + словарь `RESPIRATORY_PPE` + ветки валидации/сборки в `profiles.py`, плюс фронт-секция, demo-seed и тесты. **Миграции нет** — колонка `type_specific JSON` уже существует (wp06). Целевой рефактор: вынос общего `_validate_code_list` (используют огневые и газоопасные).

**Tech Stack:** Backend — Python/FastAPI/SQLAlchemy/Pydantic v2, pytest. Frontend — React/TS/Vite, react-hook-form + zod, vitest. Среда: Win+Py3.13.7/.venv (канон Py3.12.12 = CI, выключен). Сигнал прогона — EXIT-код / маркер `===RC=$LASTEXITCODE===`.

**Спека:** `docs/superpowers/specs/2026-06-23-work-permit-gas-hazardous-528-design.md`
**Ветка:** `feat/work-permit-gas-hazardous-528` (уже создана от `feat/work-permit-hot-work-1479`, спек закоммичен).

---

## Карта файлов

| Файл | Действие | Ответственность |
|---|---|---|
| `backend/app/domains/work_permits/profiles.py` | Modify | `RESPIRATORY_PPE`, `gas_hazardous` → `legal_reference` 528 + `structured_kind="gas_works"`, хелпер `_validate_code_list`, ветки `gas_works` |
| `tests/test_work_permit_profiles.py` | Modify | unit-тесты профиля газоопасных |
| `backend/tests/test_work_permit_confined_schemas.py` | Modify | 422-матрица для `gas_hazardous` |
| `tests/test_work_permit_print_service.py` | Modify | DOCX-тест газоопасного наряда |
| `backend/app/services/demo_bootstrap.py` | Modify | `_seed_work_permit_gas_demo` + вызов |
| `frontend/src/lib/workPermitVocab.ts` | Modify | `RESPIRATORY_PPE_LABELS` + правка `LEGAL_REFERENCE_LABELS.gas_hazardous` |
| `frontend/src/types/forms/workPermits.ts` | Modify | `RESPIRATORY_PPE_CODES`, `gasWorksSchema`, расширение `typeSpecificSchema` |
| `frontend/src/features/work-permits/WorkPermitFormDialog.tsx` | Modify | секция `gas_hazardous` + `toggleResp` + обобщение `toBody` |
| `frontend/src/pages/work-permits/WorkPermitDetailPage.tsx` | Modify | read-only блок газоопасных |
| `frontend/src/__tests__/WorkPermitGasWorksForm.test.tsx` | Create | vitest на газоопасную секцию |

---

## Task 1: Профиль `gas_hazardous` → `gas_works` + общий `_validate_code_list`

**Files:**
- Modify: `backend/app/domains/work_permits/profiles.py`
- Test: `tests/test_work_permit_profiles.py`

- [ ] **Step 1: Дописать падающие unit-тесты профиля газоопасных**

В конец `tests/test_work_permit_profiles.py` добавить:

```python
def test_legal_reference_gas_hazardous_is_528():
    assert "528" in pr.legal_reference("gas_hazardous")


def test_validate_gas_hazardous_accepts_valid_payload():
    pr.validate_type_specific(
        "gas_hazardous",
        {
            "respiratory_ppe": ["hose_mask", "scba"],
            "gas_analysis": [{"parameter": "oxygen", "value": "20.9", "norm": "≥ 20 об.%"}],
        },
    )


def test_validate_gas_hazardous_rejects_unknown_key():
    with pytest.raises(ValueError):
        pr.validate_type_specific("gas_hazardous", {"fire_fighting_means": ["sand"]})


def test_validate_gas_hazardous_rejects_bad_ppe():
    with pytest.raises(ValueError):
        pr.validate_type_specific("gas_hazardous", {"respiratory_ppe": ["spacesuit"]})


def test_validate_gas_hazardous_rejects_bad_gas_parameter():
    with pytest.raises(ValueError):
        pr.validate_type_specific(
            "gas_hazardous", {"gas_analysis": [{"parameter": "xx", "value": "1"}]}
        )


def test_build_section_gas_hazardous_ppe_and_gas():
    sec = pr.build_structured_section(
        "gas_hazardous",
        safety_systems=None,
        type_specific={
            "respiratory_ppe": ["hose_mask", "scba"],
            "gas_analysis": [{"parameter": "oxygen", "value": "20.9", "norm": "≥ 20 об.%"}],
        },
    )
    assert isinstance(sec, StructuredSection)
    assert "528" in sec.title
    assert any(k == "СИЗОД" for k, _ in sec.kv)
    assert "Шланговый противогаз" in sec.kv[0][1]
    assert sec.table is not None and "Кислород" in sec.table.rows[0][0]


def test_build_section_gas_hazardous_empty_returns_none():
    assert (
        pr.build_structured_section("gas_hazardous", safety_systems=None, type_specific={}) is None
    )
```

- [ ] **Step 2: Запустить — убедиться, что тесты падают**

Run: `.venv\Scripts\python.exe -m pytest tests/test_work_permit_profiles.py -q`
Expected: FAIL — `gas_hazardous` сейчас `structured_kind=None` и `legal_reference` без «528»; `validate_type_specific("gas_hazardous", {...})` бросает «not accepted»; `build_structured_section` возвращает `None`.

- [ ] **Step 3: Реализация в `profiles.py`**

(а) После словаря `FIRE_FIGHTING_MEANS` (заканчивается строкой `}` на ~37) добавить словарь СИЗОД:

```python
# --- словарь СИЗ органов дыхания (газоопасные работы, ФНП 528) ---
RESPIRATORY_PPE = {
    "hose_mask": "Шланговый противогаз (ПШ-1/ПШ-2)",
    "scba": "Автономный дыхательный аппарат (ИДА)",
    "isolating_mask": "Изолирующий противогаз",
    "filter_mask": "Фильтрующий противогаз/респиратор",
    "air_supply": "Аппарат с принудительной подачей воздуха",
}
```

(б) В реестре `PROFILES` заменить запись `gas_hazardous` (исправить расплывчатый `legal_reference` и `structured_kind`):

```python
    "gas_hazardous": WorkTypeProfile(
        "gas_hazardous",
        "Газоопасные работы",
        "Приказ Ростехнадзора от 15.12.2020 № 528 "
        "(ФНП «Правила безопасного ведения газоопасных, огневых и ремонтных работ»)",
        "gas_works",
    ),
```

(в) После `_validate_gas_analysis` (заканчивается ~строкой 110) добавить общий валидатор списка кодов:

```python
def _validate_code_list(values, allowed, field_name) -> None:
    """Список кодов ⊆ allowed (или None). Общий для fire_fighting_means и respiratory_ppe."""
    if values is None:
        return
    if not isinstance(values, list):
        raise ValueError(f"{field_name} must be a list")
    for v in values:
        if v not in allowed:
            raise ValueError(f"invalid {field_name}: {v!r}")
```

(г) Заменить тело `validate_type_specific` целиком — ветка `fire_safety` переходит на `_validate_code_list`, добавляется ветка `gas_works`:

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
        _validate_code_list(payload.get("fire_fighting_means"), FIRE_FIGHTING_MEANS, "fire_fighting_means")
        _validate_gas_analysis(payload.get("gas_analysis"))
    elif kind == "gas_works":
        unknown = set(payload) - {"respiratory_ppe", "gas_analysis"}
        if unknown:
            raise ValueError(f"unknown type_specific keys: {sorted(unknown)}")
        _validate_code_list(payload.get("respiratory_ppe"), RESPIRATORY_PPE, "respiratory_ppe")
        _validate_gas_analysis(payload.get("gas_analysis"))
    else:
        raise ValueError(f"type_specific is not accepted for work_type {work_type!r}")
```

(д) В `build_structured_section`, перед финальным `return None`, добавить ветку `gas_works` (после ветки `fire_safety`):

```python
    if kind == "gas_works":
        ts = type_specific or {}
        kv = []
        ppe = ts.get("respiratory_ppe") or []
        if ppe:
            kv.append(("СИЗОД", ", ".join(RESPIRATORY_PPE.get(c, c) for c in ppe)))
        table = _gas_table(ts.get("gas_analysis"))
        if not kv and table is None:
            return None
        return pf.StructuredSection(
            title="Защита органов дыхания и анализ среды (528)", kv=kv, table=table
        )
```

- [ ] **Step 4: Запустить — все тесты профиля зелёные (огневые-регресс + газоопасные)**

Run: `.venv\Scripts\python.exe -m pytest tests/test_work_permit_profiles.py -q`
Expected: PASS — включая `test_*_hot_work_*` (поведение `fire_safety` не изменилось после перехода на `_validate_code_list`), `test_*_confined_*`, `test_registry_covers_all_work_types` (правили существующую запись реестра, не добавляли).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/work_permits/profiles.py tests/test_work_permit_profiles.py
git commit -m "feat(work-permits): профиль газоопасных работ (528) — gas_works structured_kind"
```

---

## Task 2: Схема-валидация (422) + печать газоопасного наряда

Прод-код не меняется (схемы/печать generic) — задача доказывает, что обвязка подхватывает новый профиль. Тесты должны пройти сразу после Task 1.

**Files:**
- Test: `backend/tests/test_work_permit_confined_schemas.py`
- Test: `tests/test_work_permit_print_service.py`

- [ ] **Step 1: Дописать 422-кейсы для `gas_hazardous`**

В конец `backend/tests/test_work_permit_confined_schemas.py` добавить:

```python
def test_create_accepts_valid_gas_hazardous_type_specific():
    m = WorkPermitCreate(
        work_type="gas_hazardous",
        zone_text="колодец К-12",
        type_specific={
            "respiratory_ppe": ["hose_mask", "scba"],
            "gas_analysis": [{"parameter": "oxygen", "value": "20.9", "norm": "≥ 20 об.%"}],
        },
    )
    assert m.type_specific["respiratory_ppe"] == ["hose_mask", "scba"]


def test_create_rejects_bad_respiratory_ppe():
    with pytest.raises(ValidationError):
        WorkPermitCreate(
            work_type="gas_hazardous", zone_text="колодец",
            type_specific={"respiratory_ppe": ["spacesuit"]},
        )


def test_create_rejects_fire_means_on_gas_hazardous():
    with pytest.raises(ValidationError):
        WorkPermitCreate(
            work_type="gas_hazardous", zone_text="колодец",
            type_specific={"fire_fighting_means": ["sand"]},
        )
```

- [ ] **Step 2: Дописать DOCX-тест газоопасного наряда**

В конец `tests/test_work_permit_print_service.py` добавить:

```python
@pytest.mark.asyncio
async def test_render_gas_hazardous_uses_528_and_respiratory_ppe(sessionmaker, data_factory):
    tenant, (foreman,) = await _persons(data_factory, "Galina")
    tid = str(tenant.id)
    async with sessionmaker() as session:
        wp = await svc.create_work_permit(
            session,
            tenant_id=tid,
            work_type="gas_hazardous",
            zone_text="колодец К-12",
            number="НД-ГАЗ-1",
            type_specific={
                "respiratory_ppe": ["hose_mask", "scba"],
                "gas_analysis": [{"parameter": "oxygen", "value": "20.9", "norm": "≥ 20 об.%"}],
            },
        )
        await svc.add_member(
            session, tenant_id=tid, work_permit_id=wp.id, person_id=foreman.id, role="foreman"
        )
        rendered = await render_work_permit(
            session, tenant=tenant, permit_id=wp.id, fmt="docx", with_letterhead=False
        )
        text = _docx_text(rendered.content)
        assert "528" in text
        assert "Шланговый противогаз" in text and "Автономный дыхательный аппарат" in text
        assert "Кислород" in text and "20.9" in text
        assert "782н" not in text
```

- [ ] **Step 3: Запустить оба файла**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_work_permit_confined_schemas.py tests/test_work_permit_print_service.py -q`
Expected: PASS (все, включая существующие огневые/ОЗП/высота — не регрессировали).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_work_permit_confined_schemas.py tests/test_work_permit_print_service.py
git commit -m "test(work-permits): 422-матрица и печать газоопасного наряда (528)"
```

---

## Task 3: Demo-seed газоопасного наряда

**Files:**
- Modify: `backend/app/services/demo_bootstrap.py`

- [ ] **Step 1: Добавить seed-функцию (зеркало огневого seed)**

После `_seed_work_permit_hot_work_demo` (заканчивается ~строкой 393) добавить:

```python
async def _seed_work_permit_gas_demo(session, tenant_db_id: str, person) -> None:
    """Демо-наряд газоопасных работ (528) с СИЗОД и замером — печатается «из коробки». Идемпотентно."""
    from app.models.work_permit import WorkPermit, WorkPermitMember

    wp = (
        await session.execute(
            select(WorkPermit).where(
                WorkPermit.tenant_id == tenant_db_id,
                WorkPermit.number == "WP-GAS-DEMO",
            )
        )
    ).scalar_one_or_none()
    if wp is None:
        wp = WorkPermit(
            tenant_id=tenant_db_id,
            number="WP-GAS-DEMO",
            work_type="gas_hazardous",
            zone_text="Колодец К-12, узел запорной арматуры",
            status="draft",
            type_specific={
                "respiratory_ppe": ["hose_mask"],
                "gas_analysis": [{"parameter": "oxygen", "value": "20.9", "norm": "≥ 20 об.%"}],
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

Сразу после строки `await _seed_work_permit_hot_work_demo(session, tenant_db_id, person)` добавить (тот же отступ):

```python
            await _seed_work_permit_gas_demo(session, tenant_db_id, person)
```

- [ ] **Step 3: Smoke — bootstrap импортируется без синтаксических ошибок**

Run: `.venv\Scripts\python.exe -c "import app.services.demo_bootstrap as m; assert hasattr(m, '_seed_work_permit_gas_demo')"`
Expected: без ошибок (exit 0).

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/demo_bootstrap.py
git commit -m "feat(work-permits): demo-seed газоопасного наряда (WP-GAS-DEMO)"
```

---

## Task 4: Фронт — словарь + zod-схема формы

**Files:**
- Modify: `frontend/src/lib/workPermitVocab.ts`
- Modify: `frontend/src/types/forms/workPermits.ts`

- [ ] **Step 1: Добавить словарь меток СИЗОД и поправить юр-метку газоопасных**

(а) В `frontend/src/lib/workPermitVocab.ts` после `FIRE_FIGHTING_MEANS_LABELS` (перед `labelOf`, ~строка 96) добавить:

```typescript
export const RESPIRATORY_PPE_LABELS: Record<string, string> = {
  hose_mask: "Шланговый противогаз (ПШ-1/ПШ-2)",
  scba: "Автономный дыхательный аппарат (ИДА)",
  isolating_mask: "Изолирующий противогаз",
  filter_mask: "Фильтрующий противогаз/респиратор",
  air_supply: "Аппарат с принудительной подачей воздуха",
};
```

(б) В `LEGAL_REFERENCE_LABELS` заменить строку `gas_hazardous: "Правила газоопасных работ",` на:

```typescript
  gas_hazardous: "Приказ Ростехнадзора № 528 (ФНП)",
```

- [ ] **Step 2: Расширить zod-схему формы под газоопасные**

В `frontend/src/types/forms/workPermits.ts`:

(а) После `FIRE_FIGHTING_MEANS_CODES` (заканчивается ~строкой 11) добавить коды СИЗОД:

```typescript
export const RESPIRATORY_PPE_CODES = [
  "hose_mask", "scba", "isolating_mask", "filter_mask", "air_supply",
] as const;
```

(б) После `fireSafetySchema`/`FireSafetyValues` (~строка 30) добавить газоопасную схему:

```typescript
export const gasWorksSchema = z.object({
  respiratory_ppe: z.array(z.enum(RESPIRATORY_PPE_CODES)).optional(),
  gas_analysis: z.array(gasMeasurementSchema).optional(),
});
export type GasWorksValues = z.infer<typeof gasWorksSchema>;
```

(в) Заменить строку `export const typeSpecificSchema = confinedEnvSchema.merge(fireSafetySchema);` на надмножество всех трёх видов:

```typescript
// Надмножество ключей всех видов — клиентская форма; серверная validate_type_specific — источник истины по виду.
export const typeSpecificSchema = confinedEnvSchema.merge(fireSafetySchema).merge(gasWorksSchema);
```

- [ ] **Step 3: Проверить типы**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json`
Expected: без ошибок.
*(Если в репо `tsc` запускается только через `npm run build` — отложить до Task 7; не блокирующий шаг.)*

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/workPermitVocab.ts frontend/src/types/forms/workPermits.ts
git commit -m "feat(work-permits): фронт-словарь и zod-схема газоопасных работ"
```

---

## Task 5: Фронт — секция газоопасных на форме + `toggleResp` + обобщение `toBody` + vitest

**Files:**
- Modify: `frontend/src/features/work-permits/WorkPermitFormDialog.tsx`
- Create: `frontend/src/__tests__/WorkPermitGasWorksForm.test.tsx`

- [ ] **Step 1: Написать падающий vitest**

Создать `frontend/src/__tests__/WorkPermitGasWorksForm.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { WorkPermitFormDialog } from "@/features/work-permits/WorkPermitFormDialog";

vi.mock("@/api/workPermits", () => ({ workPermitsApi: { create: vi.fn(), update: vi.fn() } }));

describe("WorkPermitFormDialog gas_hazardous section", () => {
  it("показывает секцию газоопасных при выборе gas_hazardous и скрывает огневую/ОЗП/высоту", async () => {
    render(<WorkPermitFormDialog trigger={<button>open</button>} />);
    fireEvent.click(screen.getByText("open"));
    fireEvent.change(screen.getByLabelText("Вид работ"), { target: { value: "gas_hazardous" } });
    expect(screen.getByText(/Защита органов дыхания/i)).toBeInTheDocument();
    expect(screen.getByText("Шланговый противогаз (ПШ-1/ПШ-2)")).toBeInTheDocument();
    expect(screen.queryByText("Системы обеспечения безопасности")).not.toBeInTheDocument();
    expect(screen.queryByText(/Пожарная безопасность/i)).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Запустить — упадёт (секции нет)**

Run: `cd frontend && npx vitest run src/__tests__/WorkPermitGasWorksForm.test.tsx`
Expected: FAIL — текст «Защита органов дыхания» не найден.

- [ ] **Step 3: Реализация — импорт кодов/словаря, toggleResp, секция, toBody**

(а) В импортах из `@/types/forms/workPermits` (строки 20-27) добавить `RESPIRATORY_PPE_CODES`:

```typescript
import {
  SAFETY_SYSTEM_CODES,
  GAS_PARAMETER_CODES,
  VENTILATION_CODES,
  FIRE_FIGHTING_MEANS_CODES,
  RESPIRATORY_PPE_CODES,
  workPermitSchema,
  type WorkPermitFormValues,
} from "@/types/forms/workPermits";
```

(б) В импортах из `@/lib/workPermitVocab` (строки 28-35) добавить `RESPIRATORY_PPE_LABELS`:

```typescript
import {
  SAFETY_SYSTEM_LABELS,
  WORK_TYPE_LABELS,
  LEGAL_REFERENCE_LABELS,
  GAS_PARAMETER_LABELS,
  VENTILATION_LABELS,
  FIRE_FIGHTING_MEANS_LABELS,
  RESPIRATORY_PPE_LABELS,
} from "@/lib/workPermitVocab";
```

(в) Обобщить `toBody` (строка 114) — `type_specific` сериализуется для ОЗП, огневых И газоопасных:

```typescript
    type_specific: ["confined_space", "hot_work", "gas_hazardous"].includes(v.work_type)
      ? (v.type_specific ?? null)
      : null,
```

(г) После `toggleMean` (заканчивается строкой 160) добавить toggler СИЗОД:

```typescript
  const selectedResp = new Set(
    ((form.watch("type_specific") as { respiratory_ppe?: string[] } | null)?.respiratory_ppe) ?? [],
  );
  const toggleResp = (code: (typeof RESPIRATORY_PPE_CODES)[number]) => {
    const next = new Set(selectedResp);
    next.has(code) ? next.delete(code) : next.add(code);
    form.setValue("type_specific", {
      ...(form.watch("type_specific") ?? {}),
      respiratory_ppe: Array.from(next),
    } as WorkPermitFormValues["type_specific"]);
  };
```

(д) После блока `hot_work` (заканчивается строкой 301 `)}`) добавить блок `gas_hazardous`:

```tsx
          {form.watch("work_type") === "gas_hazardous" && (
            <div className="space-y-2">
              <Label>Защита органов дыхания и анализ среды (528)</Label>
              <Label className="text-xs">СИЗ органов дыхания (СИЗОД)</Label>
              <div className="flex flex-wrap gap-3">
                {RESPIRATORY_PPE_CODES.map((code) => (
                  <label key={code} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={selectedResp.has(code)}
                      onChange={() => toggleResp(code)}
                    />
                    {RESPIRATORY_PPE_LABELS[code]}
                  </label>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">
                Параметры замеров концентрации: {GAS_PARAMETER_CODES.map((c) => GAS_PARAMETER_LABELS[c]).join(", ")}.
                Продувка/вентиляция и контроль среды — в полях «Мероприятия» / «Особые условия».
              </p>
            </div>
          )}
```

- [ ] **Step 4: Запустить — все формы зелёные**

Run: `cd frontend && npx vitest run src/__tests__/WorkPermitGasWorksForm.test.tsx src/__tests__/WorkPermitHotWorkForm.test.tsx src/__tests__/WorkPermitConfinedForm.test.tsx`
Expected: PASS (газоопасная секция рендерится; огневая/ОЗП не регрессировали).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/work-permits/WorkPermitFormDialog.tsx frontend/src/__tests__/WorkPermitGasWorksForm.test.tsx
git commit -m "feat(work-permits): секция газоопасных работ на форме наряда + toBody"
```

---

## Task 6: Фронт — read-only блок газоопасных на деталь-странице

**Files:**
- Modify: `frontend/src/pages/work-permits/WorkPermitDetailPage.tsx`

- [ ] **Step 1: Добавить импорт `RESPIRATORY_PPE_LABELS`**

В импорт из `@/lib/workPermitVocab` (строки 21-29) добавить `RESPIRATORY_PPE_LABELS`:

```typescript
import {
  MEMBER_ROLE_LABELS,
  SAFETY_SYSTEM_LABELS,
  WORK_TYPE_LABELS,
  VENTILATION_LABELS,
  GAS_PARAMETER_LABELS,
  FIRE_FIGHTING_MEANS_LABELS,
  RESPIRATORY_PPE_LABELS,
  labelOf,
} from "@/lib/workPermitVocab";
```

- [ ] **Step 2: Добавить read-only блок газоопасных после блока огневых**

После закрывающего `) : null}` блока `hot_work` (строка 345) добавить:

```tsx
          {wp.work_type === "gas_hazardous" && wp.type_specific ? (
            <div className="text-sm">
              <div className="font-medium">Защита органов дыхания и анализ среды (528)</div>
              {((wp.type_specific as { respiratory_ppe?: string[] }).respiratory_ppe ?? []).length ? (
                <div>
                  СИЗОД:{" "}
                  {((wp.type_specific as { respiratory_ppe: string[] }).respiratory_ppe)
                    .map((c) => RESPIRATORY_PPE_LABELS[c] ?? c)
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
Expected: BUILD ok (TS чист).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/work-permits/WorkPermitDetailPage.tsx
git commit -m "feat(work-permits): read-only блок газоопасных на деталь-странице наряда"
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
  -q 2>&1 | Tee-Object gas_cohort.txt; Add-Content gas_cohort.txt "===RC=$LASTEXITCODE==="
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
npx vitest run src/__tests__/WorkPermitGasWorksForm.test.tsx src/__tests__/WorkPermitHotWorkForm.test.tsx src/__tests__/WorkPermitConfinedForm.test.tsx
```
Expected: build `===BUILD_RC=0===`; vitest — все passed.

- [ ] **Step 4: Дописать handoff-блок в `AI_IMPLEMENTATION_REPORT.md`**

Вставить новый блок СВЕРХУ (после `# AI Implementation Report`), формат — как у предыдущих handoff (дата, ГЛАВНОЕ, Построено, Тесты, Отложено, Next). Зафиксировать: четвёртый вид через слой профилей, без миграции, целевой рефактор `_validate_code_list`, исправление расплывчатого legal_reference на ФНП 528, буквальный паритет фронта с ОЗП/огневыми, отложенный построчный редактор замеров.

- [ ] **Step 5: Удалить временные лог-файлы и закоммитить handoff**

```bash
rm -f gas_cohort.txt mig_cohort.txt fe_build.txt
git add AI_IMPLEMENTATION_REPORT.md
git commit -m "docs: handoff — тираж наряда-допуска на газоопасные работы (528)"
```

---

## Self-Review (выполнено при написании плана)

**1. Spec coverage:**
- §2 профиль `gas_hazardous`/`gas_works` + `RESPIRATORY_PPE` + правка `legal_reference` 528 → Task 1. ✓
- §3 рефактор `_validate_code_list` (общий для огневых и газоопасных) → Task 1 шаг 3(в,г). ✓
- §4 `type_specific` форма/валидация → Task 1. ✓
- §5 печатная секция `gas_works` → Task 1 шаг 3(д). ✓
- §6 generic-обвязка без правок (доказано тестами) → Task 2. ✓
- §7 фронт: словарь+схема+юр-метка (Task 4), форма+toBody+toggleResp (Task 5), деталь-страница (Task 6). ✓
- §8 demo-seed → Task 3. ✓
- §9 тесты: profiles (T1), schemas+print (T2), vitest (T5), регрессия (T7). ✓
- §10 YAGNI (редактор замеров отложен; группа I/II не фиксируется) — фронт-задачи их не строят. ✓

**2. Placeholder scan:** код в каждом шаге конкретный; нет «TBD»/«добавить валидацию». ✓ (handoff-текст Task 7 шаг 4 — содержательное описание формата, не код-плейсхолдер.)

**3. Type consistency:** `structured_kind="gas_works"` единообразно в validate/build; `RESPIRATORY_PPE` (backend) ↔ `RESPIRATORY_PPE_LABELS`/`RESPIRATORY_PPE_CODES` (frontend) — коды совпадают (`hose_mask`/`scba`/`isolating_mask`/`filter_mask`/`air_supply`). `_validate_code_list(values, allowed, field_name)` — сигнатура единая, зовётся из обеих веток. `gasWorksSchema` влит в `typeSpecificSchema` через `.merge`. `toggleResp` пишет `respiratory_ppe` (совпадает с ключом валидации/печати). ✓

**4. Корректность образцов:** `_seed_work_permit_gas_demo(session, tenant_db_id, person)` — 3 аргумента (без site), зеркалит реальную сигнатуру огневого/ОЗП seed; тест-харнес печати использует `_persons`/`_docx_text`/`svc.create_work_permit`/`svc.add_member`/`render_work_permit` — переиспользуются. `build_structured_section` использует `_gas_table(ts.get("gas_analysis"))` без `or []` — как в текущем коде. ✓
