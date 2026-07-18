# Наряд-допуск: тираж на работы в электроустановках (903н)

**Дата:** 2026-06-23
**Статус:** Design (утверждён пользователем: подход A + DRY тогглеров в этот срез)
**Контур:** наряды-допуски §16, слой профилей видов работ

## Контекст

Контур нарядов-допусков построен по программе Ф1→Ф4 на эталоне «работа на высоте (782н)»
и затем тиражирован на 3 вида через **слой профилей** (`backend/app/domains/work_permits/profiles.py`):
ОЗП (902н), огневые (1479), газоопасные (528). Остаётся 2 вида-заглушки
(`structured_kind=None`): **электроустановки (903н)** и земляные работы. Этот срез строит
электроустановки — 5-й полноценный вид.

**Дивиденд слоя (доказан 3 раза):** новый вид работ = правки **только** в `profiles.py`;
**миграции нет** (`type_specific JSON` универсальна с wp06). Обвязка generic:
`schemas/work_permit.py` зовёт `wp_profiles.validate_type_specific(work_type, type_specific)`,
печать — `wp_profiles.build_structured_section(...)`, сервис хранит `type_specific` как есть.

## Решения (утверждены)

- **Подход A** — паритет с паттерном остальных видов, без миграции. Структурная секция =
  чек-лист кодов + одиночный enum-выбор. Группы по электробезопасности **отложены**
  (per-person данные → требуют изменения модели бригады + миграцию → ломают «без миграции»).
- **DRY-рефактор тогглеров формы — в этот срез** (5-й вид = плановый порог пересмотра абстракции).

## Backend (только `profiles.py`)

### Словари структурной секции

```python
# Технические мероприятия подготовки рабочего места (ПОТЭЭ 903н, п.16.1)
ELECTRICAL_MEASURES = {
    "disconnect": "Произведены отключения, приняты меры против ошибочного включения",
    "lockout_signs": "На приводах и ключах управления вывешены запрещающие плакаты",
    "verify_no_voltage": "Проверено отсутствие напряжения на токоведущих частях",
    "grounding": "Установлено заземление (включены ЗН / наложены переносные заземления)",
    "barriers_signs": "Вывешены плакаты, ограждены рабочие места и токоведущие части под напряжением",
}

# Условие производства работ по напряжению
VOLTAGE_CONDITIONS = {
    "de_energized": "Со снятием напряжения",
    "near_live": "Без снятия напряжения вблизи токоведущих частей",
    "away_live": "Без снятия напряжения вдали от токоведущих частей",
}
```

### Профиль

`PROFILES["electrical"]` уже существует со `structured_kind=None` и корректным
`legal_reference` («Приказ Минтруда России от 15.12.2020 № 903н»). Меняем только
`structured_kind` → `"electrical_safety"`. `label` остаётся «Работа в электроустановках».

### Валидация (`validate_type_specific`, новая ветка `electrical_safety`)

`type_specific` для электро = `{technical_measures: [коды], voltage_condition: enum | None}`.

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

- `technical_measures` переиспользует существующий `_validate_code_list` (как fire/gas).
- `voltage_condition` — enum-проверка по образцу `ventilation` (None ок).
- **Нет** `gas_analysis` — электрики воздух не меряют; ключ не входит в whitelist → 422.

### Печать (`build_structured_section`, новая ветка `electrical_safety`)

```python
if kind == "electrical_safety":
    ts = type_specific or {}
    kv = []
    vc = ts.get("voltage_condition")
    if vc:
        kv.append(("Условие проведения", VOLTAGE_CONDITIONS.get(vc, vc)))
    measures = ts.get("technical_measures") or []
    if measures:
        kv.append(("Технические мероприятия",
                   "; ".join(ELECTRICAL_MEASURES.get(m, m) for m in measures)))
    if not kv:
        return None
    return pf.StructuredSection(
        title="Меры безопасности в электроустановках (903н)", kv=kv, table=None
    )
```

Таблицы нет (`table=None`) — отличие от ОЗП/огневых/газоопасных, у которых газозамеры.

### Комментарий типа

Обновить комментарий поля `structured_kind` в `WorkTypeProfile`:
добавить `"electrical_safety"` в перечисление допустимых значений.

## Frontend

### `lib/workPermitVocab.ts`

```ts
export const ELECTRICAL_MEASURES_LABELS: Record<string, string> = { /* 5 кодов */ };
export const VOLTAGE_CONDITION_LABELS: Record<string, string> = { /* 3 кода */ };
```

(`LEGAL_REFERENCE_LABELS.electrical` уже есть: «Приказ Минтруда № 903н».)

### `types/forms/workPermits.ts`

```ts
export const ELECTRICAL_MEASURE_CODES = [
  "disconnect", "lockout_signs", "verify_no_voltage", "grounding", "barriers_signs",
] as const;
export const VOLTAGE_CONDITION_CODES = ["de_energized", "near_live", "away_live"] as const;

export const electricalSafetySchema = z.object({
  technical_measures: z.array(z.enum(ELECTRICAL_MEASURE_CODES)).optional(),
  voltage_condition: z.enum(VOLTAGE_CONDITION_CODES).optional(),
});
// typeSpecificSchema = confined.merge(fire).merge(gas).merge(electrical)
```

### `WorkPermitFormDialog.tsx`

- **DRY тогглеров:** ввести один хендлер для type_specific-массивов:
  ```ts
  const toggleTsCode = (field: "fire_fighting_means" | "respiratory_ppe" | "technical_measures", code: string) => {
    const current = (form.getValues("type_specific") ?? {}) as Record<string, string[] | undefined>;
    const next = new Set(current[field] ?? []);
    next.has(code) ? next.delete(code) : next.add(code);
    form.setValue("type_specific", { ...current, [field]: Array.from(next) } as WorkPermitFormValues["type_specific"]);
  };
  ```
  `toggleMean`/`toggleResp` удаляются, их JSX зовёт `toggleTsCode("fire_fighting_means", code)` /
  `toggleTsCode("respiratory_ppe", code)`. Новый electrical зовёт `toggleTsCode("technical_measures", code)`.
  `toggleSystem` (top-level `safety_systems`, не `type_specific`) остаётся отдельным — это
  честно другое место хранения (легаси-колонка высоты).
- **Секция electrical** (по `work_type==="electrical"`): чек-лист `ELECTRICAL_MEASURE_CODES`
  (как fire/gas) + `select` условия по напряжению по образцу `ventilation`-селекта ОЗП.
- **`toBody`:** whitelist type_specific += `"electrical"` →
  `["confined_space", "hot_work", "gas_hazardous", "electrical"]`.

### `WorkPermitDetailPage.tsx`

Read-only блок по `work_type==="electrical" && type_specific` (зеркало газоопасного блока):
условие по напряжению + перечень технических мероприятий. Без таблицы.

### Demo-seed (`services/demo_bootstrap.py`)

Новая `_seed_work_permit_electrical_demo(session, tenant_db_id, person)` по образцу
`_seed_work_permit_gas_demo` (сигнатура подтверждена по коду): `WP-ELEC-DEMO`,
`work_type="electrical"`, `zone_text` (контекстная электро-локация, НЕ дублировать чужие демо),
`type_specific={"technical_measures": ["disconnect", "verify_no_voltage", "grounding"], "voltage_condition": "de_energized"}`,
член бригады `foreman`. Зарегистрировать вызов в общем сидере рядом с остальными нарядами.

DRY 4 seed-функций — **отложено** (#2 follow-up; пользователь scoped DRY на тогглеры).

## Тестирование

**Backend:**
- `profiles`-юниты: `validate_type_specific("electrical", ...)` — принимает валидный payload;
  отвергает неизвестный ключ (напр. `gas_analysis`), неверный код мероприятия, неверное
  `voltage_condition`; пустой/None ок. `build_structured_section("electrical", ...)` — секция
  с kv (условие+мероприятия), `None` на пустом, без таблицы.
- Схемы: 422-матрица (Create/Update) на электро payload.
- Печать: DOCX-тест — шапка 903н + перечень мероприятий + условие по напряжению.
- Миграционный когорт (`migration or downgrade or mapper`) — прогнать, **миграции нет** →
  должен остаться зелёным (доказывает, что слой не задел миграции).

**Frontend (vitest):**
- `WorkPermitElectricalForm`: секция видна при `electrical`; накопление 2 чекбоксов мероприятий
  (через `act`-батч); `select` условия выставляет `voltage_condition`; **защита от копи-паста** —
  ключ `technical_measures` (а не `fire_fighting_means`/`respiratory_ppe`).
- Деталь-страница: блок electrical рендерит мероприятия+условие.
- Reset: `electrical`→другой вид очищает `type_specific` (существующий `onWorkTypeChange`).
- Регресс: огневые/газоопасные тоггл-тесты зелёные после DRY-рефактора (поведение сохранено).

## Изоляция и границы

- `profiles.py` — чистый модуль (без I/O), один полиморфный шов per-type. Новая ветка
  изолирована, не трогает height/confined/hot/gas.
- `toggleTsCode` — один хендлер с явным union-типом поля; consumers (3 чек-листа) не знают
  внутренностей. `toggleSystem` намеренно не сливаем (другое хранилище) — границы честные.
- Frontend-секция и detail-блок — независимые условные рендеры по `work_type`.

## Отложено (явно, не в этом срезе)

1. **Группы по электробезопасности** (I–V) у членов бригады — per-person, требует колонку
   на таблице членов + UI + миграцию. Отдельный контур.
2. **DRY 4 seed-функций** → общий `_seed_work_permit_demo(*, number, work_type, zone_text, type_specific)`.
3. **Построчный редактор замеров** на форме (все виды) — остаётся отложенным.
4. **Земляные работы** — последний вид-заглушка, следующий тираж.
5. Пиксель-точная типографика бланка 903н.
