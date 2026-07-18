# Наряд-допуск: построчный редактор замеров gas_analysis на форме

**Дата:** 2026-06-23
**Статус:** Design (дивиденд-дружественный фронт-срез; пользователь — «продолжай по роадмап»)
**Контур:** наряды-допуски §16, форма

## Контекст

`gas_analysis` (таблица замеров воздушной среды/концентрации) — структурное поле в
`type_specific JSON`, общее для 3 видов: ОЗП (902н), огневые (1479), газоопасные (528).
Бэкенд его валидирует (`profiles._validate_gas_analysis`), seed заполняет, деталь-страница
рендерит read-only, zod `gasMeasurementSchema` поддерживает. **Единственный пробел:** на
форме нет редактора — секции показывают лишь подсказку «Параметры замеров: …», а сами строки
вводятся только через API/seed. Этот срез закрывает пробел.

Откладывался многократно (item «построчный редактор замеров» в handoff ОЗП/огневых/газоопасных).
Дивиденд-дружественный: **без бэкенда, без миграции** — чистый фронт.

Стек: ветка `feat/work-permit-gas-analysis-editor` от `feat/work-permit-excavation` (редактирует
тот же `WorkPermitFormDialog.tsx` в актуальном состоянии). При merge стека — по порядку.

## Структура данных

`type_specific.gas_analysis: Array<{parameter, value, norm?, measured_at?}>`, где
`parameter ∈ GAS_PARAMETER_CODES` (oxygen/flammable/harmful), `value: string`,
`norm`/`measured_at` — опциональные строки. zod `gasMeasurementSchema` уже это описывает.

## Компонент `GasAnalysisEditor`

**Презентационный** (без знания о react-hook-form — тестируется изолированно).

```tsx
interface GasRow { parameter: string; value: string; norm?: string; measured_at?: string }
interface Props {
  rows: GasRow[];
  onAdd: () => void;
  onRemove: (index: number) => void;
  onCell: (index: number, field: keyof GasRow, value: string) => void;
}
```

Рендер: для каждой строки — `select` параметра (`GAS_PARAMETER_CODES`/`GAS_PARAMETER_LABELS`) +
`input` value + `input` norm + `input` measured_at + кнопка «Удалить» (с `aria-label`). Снизу —
кнопка «Добавить замер». Пустой список → только кнопка добавления. Файл:
`frontend/src/features/work-permits/GasAnalysisEditor.tsx`.

## Проводка в `WorkPermitFormDialog`

Хелпер на `getValues` (дисциплина против stale-snapshot, как `toggleTsCode`):

```ts
const updateGas = (mut: (rows: GasRow[]) => GasRow[]) => {
  const current = (form.getValues("type_specific") ?? {}) as { gas_analysis?: GasRow[] };
  const rows = mut([...(current.gas_analysis ?? [])]);
  form.setValue("type_specific", { ...current, gas_analysis: rows } as WorkPermitFormValues["type_specific"]);
};
const gasRows = ((form.watch("type_specific") as { gas_analysis?: GasRow[] } | null)?.gas_analysis) ?? [];
```

Колбэки: `onAdd = () => updateGas(r => [...r, { parameter: "oxygen", value: "" }])`;
`onRemove = (i) => updateGas(r => r.filter((_, j) => j !== i))`;
`onCell = (i, f, v) => updateGas(r => r.map((row, j) => (j === i ? { ...row, [f]: v || undefined } : row)))`
(для `value` пустая строка допустима — оставляем как `""`; для norm/measured_at пусто → undefined).
**Уточнение:** `value` — обязательное поле (zod `z.string()`), не коэрсим в undefined; norm/measured_at — optional.

Встроить `<GasAnalysisEditor rows={gasRows} ... />` в 3 секции (`confined_space`, `hot_work`,
`gas_hazardous`) рядом с существующей подсказкой (подсказку ужать до одной строки про назначение).
Электро/земляные секции НЕ трогаем (у них нет gas_analysis).

`toBody` уже прокидывает `type_specific` для этих видов — менять не нужно.

## Тестирование

**Компонент (`GasAnalysisEditor.test.tsx`):** рендер строк из `rows`; клик «Добавить» зовёт `onAdd`;
«Удалить» у строки i зовёт `onRemove(i)`; изменение select/inputs зовёт `onCell(i, field, value)`
с верными аргументами; пустой `rows` показывает только «Добавить».

**Интеграция (в `WorkPermitConfinedForm.test.tsx` или новый):** при виде confined_space редактор виден;
«Добавить замер» → строка появляется; смена параметра/value пишет в `type_specific.gas_analysis`
(через сабмит-моки или чтение состояния); защита от stale — два быстрых добавления накапливаются.

**Регресс:** существующие наряд-vitest зелёные; `tsc`/`eslint --max-warnings=0`; `npm run build`.

## Изоляция и границы

- `GasAnalysisEditor` — презентационный, одна ответственность (рендер+эмит строк), тестируется без формы.
- Мутации в родителе через `updateGas`/`getValues` — единая точка, согласована с `toggleTsCode`.
- Затронуты 3 секции, общий редактор — DRY (один компонент на 3 вида), без дублирования JSX.

## Отложено (явно)

1. Валидация диапазонов значений на фронте (бэкенд проверяет только параметр); сейчас — свободный ввод.
2. Автоподстановка нормы по параметру (norm вводится вручную).
3. Группы по электробезопасности, паспорт котлована, глубина выемки — отдельные контуры (новый объём).
