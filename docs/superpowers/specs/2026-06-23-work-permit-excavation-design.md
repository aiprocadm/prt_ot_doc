# Наряд-допуск: тираж на земляные работы (excavation)

**Дата:** 2026-06-23
**Статус:** Design (подход A — паритет с утверждённым паттерном электро; пользователь явно выбрал строить земляные)
**Контур:** наряды-допуски §16, слой профилей видов работ

## Контекст

Шестой и **последний** вид-заглушка слоя профилей (`backend/app/domains/work_permits/profiles.py`).
После него все `WORK_TYPES` имеют непустой `structured_kind` — тираж видов работ закрыт.
Зеркалит паттерн, отработанный на 5 видах (высота/ОЗП/огневые/газоопасные/электро):
чек-лист кодов + одиночный enum, **без миграции** (`type_specific JSON` универсальна).

Стек: ветка `feat/work-permit-excavation` от `feat/work-permit-electrical-903` (электро ещё
в PR #685, не в main) — во избежание add/add-конфликтов в общих файлах. При merge электро —
ребейз на main.

## Решения

- **Подход A** — чек-лист подземных коммуникаций + enum способа защиты стенок выемки. Без миграции,
  правки бэкенда только в `profiles.py`.
- **Глубина выемки** — во free-text «Особые условия» (как прочие виды выносят детали в текст),
  чтобы держать паттерн чек-лист+enum без числовых полей.
- **Отложено:** паспорт/проект котлована, наряд на работы в зоне действующих коммуникаций как
  отдельный документооборот, группы допуска.

## Backend (только `profiles.py`)

### Словари

```python
# --- подземные коммуникации в зоне земляных работ ---
UTILITIES = {
    "power_cable": "Электрические кабели",
    "gas_pipe": "Газопровод",
    "water_sewer": "Водопровод / канализация",
    "heating": "Теплосеть",
    "comms": "Кабели связи",
}

# --- способ защиты стенок выемки ---
SHORING_METHODS = {
    "natural_slopes": "Естественные откосы",
    "shield_bracing": "Крепление щитами / распорами",
    "sheet_piling": "Шпунтовое ограждение",
    "none_shallow": "Без крепления (мелкая выемка)",
}
```

### Профиль

`PROFILES["excavation"]`: `structured_kind` `None` → `"excavation_safety"`. Уточнить расплывчатый
`legal_reference` «Правила безопасности при производстве земляных работ» →
`"Приказ Минтруда России от 11.12.2020 № 883н (ПОТ при строительстве, реконструкции и ремонте)"`.
В комментарии поля `structured_kind` дописать `"excavation_safety"`.

### Валидация (`validate_type_specific`, ветка `excavation_safety`)

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

### Печать (`build_structured_section`, ветка `excavation_safety`)

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

Таблицы нет.

## Frontend

### `lib/workPermitVocab.ts`

`UTILITIES_LABELS` (5 кодов) + `SHORING_METHOD_LABELS` (4 кода). Уточнить
`LEGAL_REFERENCE_LABELS.excavation` «Правила земляных работ» → «Приказ Минтруда № 883н (ПОТ в строительстве)».

### `types/forms/workPermits.ts`

```ts
export const UTILITY_CODES = ["power_cable", "gas_pipe", "water_sewer", "heating", "comms"] as const;
export const SHORING_METHOD_CODES = ["natural_slopes", "shield_bracing", "sheet_piling", "none_shallow"] as const;

export const excavationSafetySchema = z.object({
  utilities: z.array(z.enum(UTILITY_CODES)).optional(),
  shoring: z.enum(SHORING_METHOD_CODES).optional(),
});
// typeSpecificSchema += .merge(excavationSafetySchema)
```

### `WorkPermitFormDialog.tsx`

- Расширить union-поле `toggleTsCode`: добавить `"utilities"` (DRY-дивиденд — хендлер уже общий).
- Снимок `selectedUtilities` (по образцу `selectedMeasures`).
- Секция по `work_type==="excavation"`: чек-лист `UTILITY_CODES` (через `toggleTsCode("utilities", code)`)
  + `select` способа защиты стенок по образцу `voltage_condition`/`ventilation`.
- `toBody` whitelist += `"excavation"`.

### `WorkPermitDetailPage.tsx`

Read-only блок по `work_type==="excavation" && type_specific`: защита стенок + перечень коммуникаций.

### Demo-seed (`services/demo_bootstrap.py`)

`_seed_work_permit_excavation_demo` по образцу: `WP-DIG-DEMO`, `work_type="excavation"`,
`zone_text` (траншея/котлован — контекстная локация, не дублировать чужие демо),
`type_specific={"utilities": ["power_cable", "water_sewer"], "shoring": "shield_bracing"}`,
член бригады `foreman`. Зарегистрировать вызов рядом с остальными.

## Тестирование

**Backend:** profiles-юниты (валидация excavation: валид/неизвестный ключ/неверный код
коммуникации/неверный shoring + сборка секции, без таблицы); схемная 422-матрица (Create);
миграционный когорт прогнать — **миграции нет** → зелёный.

**Frontend (vitest):** `WorkPermitExcavationForm` (секция видна при excavation; накопление
чекбоксов коммуникаций; select shoring выставляет значение; защита от копи-паста ключа
`utilities`); регресс electrical/gas/hot тоггл-тестов зелёный после расширения union;
деталь-блок excavation; reset excavation→другой вид.

## Отложено (явно)

1. Глубина выемки как структурное числовое поле (сейчас — текст «Особые условия»).
2. Паспорт/проект котлована, согласование-ордер на земляные работы как отдельный документооборот.
3. Группы допуска; DRY 5 seed-функций; редактор замеров; типографика бланка.

## Завершение тиража

После excavation `set(structured_kind != None)` покрывает все 6 `WORK_TYPES` —
заглушек не остаётся. Дальнейшее углубление (числовые поля, отдельные документообороты) —
новый объём, не «тираж видов».
