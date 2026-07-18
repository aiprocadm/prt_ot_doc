# Построчный редактор замеров gas_analysis на форме — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Добавить на форму наряда построчный редактор замеров `gas_analysis` для видов ОЗП/огневые/газоопасные — закрыть многократно отложенный фронт-пробел.

**Architecture:** Презентационный компонент `GasAnalysisEditor` (рендер строк + эмит событий) + проводка в `WorkPermitFormDialog` через хелпер `updateGas` на `form.getValues`. Без бэкенда, без миграции — `gas_analysis` уже в `type_specific JSON`, валидируется и рендерится.

**Tech Stack:** React · react-hook-form · zod · vitest. Команды через PowerShell.

---

### Task 1: Компонент `GasAnalysisEditor` (презентационный)

**Files:**
- Create: `frontend/src/features/work-permits/GasAnalysisEditor.tsx`
- Test (create): `frontend/src/__tests__/GasAnalysisEditor.test.tsx`

- [ ] **Step 1: Написать падающий тест**

Create `frontend/src/__tests__/GasAnalysisEditor.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { GasAnalysisEditor } from "@/features/work-permits/GasAnalysisEditor";

const rows = [
  { parameter: "oxygen", value: "20.9", norm: "≥ 20" },
  { parameter: "flammable", value: "0" },
];

describe("GasAnalysisEditor", () => {
  it("рендерит строки замеров", () => {
    render(<GasAnalysisEditor rows={rows} onAdd={vi.fn()} onRemove={vi.fn()} onCell={vi.fn()} />);
    expect(screen.getAllByLabelText("Параметр замера")).toHaveLength(2);
    expect((screen.getAllByLabelText("Значение")[0] as HTMLInputElement).value).toBe("20.9");
  });

  it("пустой список показывает только кнопку добавления", () => {
    render(<GasAnalysisEditor rows={[]} onAdd={vi.fn()} onRemove={vi.fn()} onCell={vi.fn()} />);
    expect(screen.queryByLabelText("Параметр замера")).not.toBeInTheDocument();
    expect(screen.getByText("Добавить замер")).toBeInTheDocument();
  });

  it("клик «Добавить замер» зовёт onAdd", () => {
    const onAdd = vi.fn();
    render(<GasAnalysisEditor rows={[]} onAdd={onAdd} onRemove={vi.fn()} onCell={vi.fn()} />);
    fireEvent.click(screen.getByText("Добавить замер"));
    expect(onAdd).toHaveBeenCalledOnce();
  });

  it("удаление строки зовёт onRemove с индексом", () => {
    const onRemove = vi.fn();
    render(<GasAnalysisEditor rows={rows} onAdd={vi.fn()} onRemove={onRemove} onCell={vi.fn()} />);
    fireEvent.click(screen.getAllByLabelText("Удалить замер")[1]);
    expect(onRemove).toHaveBeenCalledWith(1);
  });

  it("изменение значения зовёт onCell(index, 'value', newValue)", () => {
    const onCell = vi.fn();
    render(<GasAnalysisEditor rows={rows} onAdd={vi.fn()} onRemove={vi.fn()} onCell={onCell} />);
    fireEvent.change(screen.getAllByLabelText("Значение")[0], { target: { value: "19.5" } });
    expect(onCell).toHaveBeenCalledWith(0, "value", "19.5");
  });

  it("смена параметра зовёт onCell(index, 'parameter', code)", () => {
    const onCell = vi.fn();
    render(<GasAnalysisEditor rows={rows} onAdd={vi.fn()} onRemove={vi.fn()} onCell={onCell} />);
    fireEvent.change(screen.getAllByLabelText("Параметр замера")[1], { target: { value: "harmful" } });
    expect(onCell).toHaveBeenCalledWith(1, "parameter", "harmful");
  });
});
```

- [ ] **Step 2: Прогнать — FAIL**

Run: `cd frontend; npx vitest run src/__tests__/GasAnalysisEditor.test.tsx; cd ..`
Expected: FAIL (компонента нет).

- [ ] **Step 3: Реализовать компонент**

Create `frontend/src/features/work-permits/GasAnalysisEditor.tsx`:

```tsx
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { GAS_PARAMETER_CODES } from "@/types/forms/workPermits";
import { GAS_PARAMETER_LABELS } from "@/lib/workPermitVocab";

export interface GasRow {
  parameter: string;
  value: string;
  norm?: string;
  measured_at?: string;
}

interface Props {
  rows: GasRow[];
  onAdd: () => void;
  onRemove: (index: number) => void;
  onCell: (index: number, field: keyof GasRow, value: string) => void;
}

export const GasAnalysisEditor = ({ rows, onAdd, onRemove, onCell }: Props) => (
  <div className="space-y-2">
    {rows.map((row, i) => (
      <div key={i} className="flex flex-wrap items-end gap-2">
        <select
          aria-label="Параметр замера"
          className="h-9 rounded-md border px-2 text-sm"
          value={row.parameter}
          onChange={(e) => onCell(i, "parameter", e.target.value)}
        >
          {GAS_PARAMETER_CODES.map((c) => (
            <option key={c} value={c}>{GAS_PARAMETER_LABELS[c]}</option>
          ))}
        </select>
        <Input
          aria-label="Значение"
          className="w-24"
          value={row.value}
          onChange={(e) => onCell(i, "value", e.target.value)}
        />
        <Input
          aria-label="Норма"
          className="w-28"
          value={row.norm ?? ""}
          onChange={(e) => onCell(i, "norm", e.target.value)}
        />
        <Input
          aria-label="Время замера"
          className="w-36"
          value={row.measured_at ?? ""}
          onChange={(e) => onCell(i, "measured_at", e.target.value)}
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-label="Удалить замер"
          onClick={() => onRemove(i)}
        >
          ✕
        </Button>
      </div>
    ))}
    <Button type="button" variant="outline" size="sm" onClick={onAdd}>
      Добавить замер
    </Button>
  </div>
);
```

Примечание: проверь сигнатуры `Button`/`Input` (`variant`/`size`/`className`) по соседним использованиям в `WorkPermitFormDialog.tsx` — если `size="sm"`/`variant="outline"` не поддержаны, убрать пропсы (функциональность не зависит от них). Не выдумывай несуществующие пропсы.

- [ ] **Step 4: Прогнать — зелёный**

Run: `cd frontend; npx vitest run src/__tests__/GasAnalysisEditor.test.tsx; cd ..`
Expected: 6 passed.

- [ ] **Step 5: tsc + eslint**

Run: `cd frontend; npx tsc --noEmit; npx eslint --max-warnings=0 src/features/work-permits/GasAnalysisEditor.tsx src/__tests__/GasAnalysisEditor.test.tsx; cd ..`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/work-permits/GasAnalysisEditor.tsx frontend/src/__tests__/GasAnalysisEditor.test.tsx
git commit -m "feat(work-permits): презентационный GasAnalysisEditor (построчный редактор замеров)"
```

---

### Task 2: Проводка редактора в форму (3 секции)

**Files:**
- Modify: `frontend/src/features/work-permits/WorkPermitFormDialog.tsx`
- Test (create): `frontend/src/__tests__/WorkPermitGasAnalysisForm.test.tsx`

- [ ] **Step 1: Написать падающий интеграционный тест**

Create `frontend/src/__tests__/WorkPermitGasAnalysisForm.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { WorkPermitFormDialog } from "@/features/work-permits/WorkPermitFormDialog";
import { workPermitsApi } from "@/api/workPermits";

vi.mock("@/api/workPermits", () => ({
  workPermitsApi: { create: vi.fn().mockResolvedValue({ id: "x" }), update: vi.fn() },
}));

describe("WorkPermitFormDialog gas_analysis editor", () => {
  beforeEach(() => vi.clearAllMocks());

  it("показывает редактор замеров для confined_space и добавляет строку в payload", async () => {
    render(<WorkPermitFormDialog trigger={<button>open</button>} />);
    fireEvent.click(screen.getByText("open"));
    fireEvent.change(screen.getByLabelText("Вид работ"), { target: { value: "confined_space" } });
    fireEvent.change(screen.getByLabelText("Зона работ"), { target: { value: "колодец К-9" } });

    expect(screen.getByText("Добавить замер")).toBeInTheDocument();
    act(() => {
      fireEvent.click(screen.getByText("Добавить замер"));
    });
    fireEvent.change(screen.getByLabelText("Значение"), { target: { value: "20.9" } });

    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await screen.findByText("open"); // дождаться завершения сабмита

    expect(workPermitsApi.create).toHaveBeenCalled();
    const body = (workPermitsApi.create as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(body.type_specific.gas_analysis).toEqual([{ parameter: "oxygen", value: "20.9" }]);
  });
});
```

Примечание: точные имена кнопки сабмита («Сохранить») и поля «Зона работ» сверь с формой; если сабмит-флоу в тесте не доезжает до `create` (валидация), добей минимально-обязательные поля по образцу соседних тестов формы.

- [ ] **Step 2: Прогнать — FAIL**

Run: `cd frontend; npx vitest run src/__tests__/WorkPermitGasAnalysisForm.test.tsx; cd ..`
Expected: FAIL (редактора в форме нет).

- [ ] **Step 3: Реализация в `WorkPermitFormDialog.tsx`**

(a) Импорты:
```ts
import { GasAnalysisEditor, type GasRow } from "@/features/work-permits/GasAnalysisEditor";
```

(b) После хелпера `toggleTsCode` (и снимков `selected*`) добавить хелпер и снимок:
```ts
  // Редактор замеров (общий для ОЗП/огневых/газоопасных). Мутации через getValues — без stale-snapshot.
  const updateGas = (mut: (rows: GasRow[]) => GasRow[]) => {
    const current = (form.getValues("type_specific") ?? {}) as { gas_analysis?: GasRow[] };
    const rows = mut([...(current.gas_analysis ?? [])]);
    form.setValue("type_specific", {
      ...current,
      gas_analysis: rows,
    } as WorkPermitFormValues["type_specific"]);
  };
  const gasRows =
    ((form.watch("type_specific") as { gas_analysis?: GasRow[] } | null)?.gas_analysis) ?? [];
  const gasEditorProps = {
    rows: gasRows,
    onAdd: () => updateGas((r) => [...r, { parameter: "oxygen", value: "" }]),
    onRemove: (i: number) => updateGas((r) => r.filter((_, j) => j !== i)),
    onCell: (i: number, f: keyof GasRow, v: string) =>
      updateGas((r) =>
        r.map((row, j) =>
          j === i ? { ...row, [f]: f === "value" ? v : v || undefined } : row,
        ),
      ),
  };
```

(c) В каждой из 3 секций (`confined_space` ~строка 294, `hot_work` ~317, `gas_hazardous` ~340)
ПОСЛЕ существующего `<p className="text-xs text-muted-foreground">…</p>` добавить:
```tsx
              <GasAnalysisEditor {...gasEditorProps} />
```
(подсказку-`<p>` оставить, она поясняет назначение параметров).

- [ ] **Step 4: Прогнать новый + регресс наряд-тестов**

Run: `cd frontend; npx vitest run src/__tests__/WorkPermitGasAnalysisForm.test.tsx src/__tests__/WorkPermitConfinedForm.test.tsx src/__tests__/WorkPermitGasWorksForm.test.tsx src/__tests__/WorkPermitHotWorkForm.test.tsx; cd ..`
Expected: все passed.

- [ ] **Step 5: tsc + eslint**

Run: `cd frontend; npx tsc --noEmit; npx eslint --max-warnings=0 src/features/work-permits/WorkPermitFormDialog.tsx src/__tests__/WorkPermitGasAnalysisForm.test.tsx; cd ..`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/work-permits/WorkPermitFormDialog.tsx frontend/src/__tests__/WorkPermitGasAnalysisForm.test.tsx
git commit -m "feat(work-permits): редактор замеров gas_analysis в 3 секциях формы (ОЗП/огневые/газоопасные)"
```

---

### Task 3: Верификация + handoff

**Files:**
- Modify: `AI_IMPLEMENTATION_REPORT.md`

- [ ] **Step 1: Backend когорт** (доказать, что бэкенд не задет — приёмка gas_analysis уже была)

Run: `.venv\Scripts\python.exe -m pytest backend/tests -k "work_permit or profile or confined" -q -p no:warnings 2>&1 | Out-Null` ; затем проверить `$LASTEXITCODE` = 0.

- [ ] **Step 2: Frontend сборка + наряд-тесты**

Run: `cd frontend; npm run build; npx vitest run src/__tests__/WorkPermit src/__tests__/GasAnalysisEditor; cd ..`
Expected: BUILD exit 0; все passed.

- [ ] **Step 3: Handoff** — секция в начало `AI_IMPLEMENTATION_REPORT.md`: редактор замеров построен, дивиденд-дружественный (без бэкенда/миграции), польза 3 видам, отложенное.

- [ ] **Step 4: Commit** — `git add AI_IMPLEMENTATION_REPORT.md; git commit -m "docs: handoff — редактор замеров gas_analysis на форме"`

- [ ] **Step 5: Финальное ревью** (opus) по диффу ветки.

---

## Self-Review (выполнено)

- **Покрытие спеки:** компонент презентационный ✓(T1) · проводка getValues ✓(T2) · 3 секции ✓(T2) · тесты компонент+интеграция ✓(T1/T2) · без бэкенда/миграции ✓(T3 доказывает).
- **Плейсхолдеры:** нет; весь код приведён (с оговоркой сверить пропсы Button/Input и имена полей по соседям).
- **Согласованность типов:** `GasRow` определён в T1, импортируется в T2; ключи `parameter/value/norm/measured_at` ↔ zod `gasMeasurementSchema`. `updateGas`-мутатор сохраняет `value:""`, коэрсит norm/measured_at пусто→undefined.
- **Отложено явно:** валидация диапазонов, автонорма, группы/котлован/глубина.
