# Дизайн: тираж наряда-допуска на газоопасные работы (ФНП РФ № 528)

**Дата:** 2026-06-23
**Контур:** Наряды-допуски (§16) — тираж эталона на четвёртый вид работ (газоопасные)
**Статус:** проектирование (brainstorming → этот спек → writing-plans)
**Ветка:** `feat/work-permit-gas-hazardous-528` от `feat/work-permit-hot-work-1479` (стопкой; огневые 1479 ещё не в `main`)

## 1. Контекст и задача

Контур наряд-допусков доведён до зрелого состояния через **слой профилей** (`domains/work_permits/profiles.py`) — полиморфный шов per-type-специфики (приказ / структурная секция / валидация `type_specific` / сборка печатной секции):
- **Эталон — работа на высоте (782н)** — построен полностью (Ф1→Ф4), `structured_kind="safety_systems"`.
- **ОЗП (902н)** — `structured_kind="confined_env"` (вентиляция + анализ воздушной среды).
- **Огневые работы (ППР 1479)** — `structured_kind="fire_safety"` (чек-лист средств пожаротушения + таблица замеров горючих паров).

Газоанализ-машинерия (`GAS_PARAMETERS`, `_validate_gas_analysis`, `_gas_table`) уже вынесена в переиспользуемые хелперы (рефактор сделан на огневых).

**Задача:** взять следующий вид — **газоопасные работы (Приказ Ростехнадзора от 15.12.2020 № 528, ФНП «Правила безопасного ведения газоопасных, огневых и ремонтных работ»)** — как четвёртый полноценный вид через слой профилей.

**Ключевой дивиденд слоя профилей:** колонка `type_specific JSON` универсальна и уже существует → **новая миграция НЕ нужна**. Схемы (`@model_validator` уже зовёт `profiles.validate_type_specific`), CRUD-сервис и сервис печати — generic, не меняются. Реальные правки бэкенда сводятся к одному модулю `profiles.py` (+ тесты).

### Решения пользователя (brainstorming 2026-06-23)
1. **Следующий вид:** газоопасные работы (528).
2. **Содержание структурной секции (новый `structured_kind="gas_works"`):** (а) чек-лист СИЗ органов дыхания (СИЗОД), (б) таблица замеров концентрации (переиспользует `GAS_PARAMETERS`). Юр-различимо от ОЗП. Прозу мер (продувка/вентиляция, подготовка, контроль) оставляем в generic-полях `measures_*`/`special_conditions_text`, как для ОЗП/огневых.
3. **Группа газоопасных работ (I/II):** НЕ фиксируем отдельным полем — наряд-допуск уже подразумевает группу I (группа II выполняется без наряда); при необходимости — прозой в `special_conditions_text`. YAGNI.
4. **Фронтенд:** буквальный паритет с ОЗП/огневыми — на форме чек-лист СИЗОД + подсказка по параметрам замеров; сами замеры `gas_analysis` задаются через API/seed, read-only на деталь-странице. Построчный редактор замеров на форме остаётся отложенным для всех видов.
5. **Demo-seed:** да, лёгкий идемпотентный.

## 2. Профиль `gas_hazardous` (`domains/work_permits/profiles.py`)

Профиль `gas_hazardous` уже присутствует как заглушка (`legal_reference="Правила проведения газоопасных работ"`, `structured_kind=None`). Правим существующую запись реестра `PROFILES` (НЕ добавляем новую — реестр-guard `set(PROFILES) == lifecycle.WORK_TYPES` сохраняется):
- `legal_reference` → `"Приказ Ростехнадзора от 15.12.2020 № 528 (ФНП «Правила безопасного ведения газоопасных, огневых и ремонтных работ»)"` (юр-корректно, как 1479 для огневых; вместо расплывчатой заглушки).
- `structured_kind` → новый **`"gas_works"`** (рядом с `safety_systems`/`confined_env`/`fire_safety`).

**Новый словарь — СИЗ органов дыхания** (чек-лист, паттерн `FIRE_FIGHTING_MEANS`):
```python
RESPIRATORY_PPE = {
    "hose_mask":      "Шланговый противогаз (ПШ-1/ПШ-2)",
    "scba":           "Автономный дыхательный аппарат (ИДА)",
    "isolating_mask": "Изолирующий противогаз",
    "filter_mask":    "Фильтрующий противогаз/респиратор",
    "air_supply":     "Аппарат с принудительной подачей воздуха",
}
```

**Замеры концентрации — переиспользуют существующий `GAS_PARAMETERS`** (`oxygen`/`flammable`/`harmful` — все валидны для газоопасных работ). Отдельный словарь не вводим.

## 3. Целевой рефактор (улучшение кода, в котором работаем)

Ветки `fire_safety` и `gas_works` в `validate_type_specific` почти идентичны: «список кодов ⊆ словаря» + общий `_validate_gas_analysis`. Выносим чистый хелпер:
```python
def _validate_code_list(values, allowed, field_name):
    """Список кодов ⊆ allowed (или None). Общий для fire_fighting_means и respiratory_ppe."""
    if values is None:
        return
    if not isinstance(values, list):
        raise ValueError(f"{field_name} must be a list")
    for v in values:
        if v not in allowed:
            raise ValueError(f"invalid {field_name}: {v!r}")
```
Ветка `fire_safety` переходит на него (`_validate_code_list(means, FIRE_FIGHTING_MEANS, "fire_fighting_means")`) — поведенчески нейтрально, покрыто тестами огневых.

## 4. `type_specific` для газоопасных

Generic-колонка `type_specific JSON` (уже есть). Форма для `gas_hazardous`:
```jsonc
{
  "respiratory_ppe": ["hose_mask", "scba"],                  // коды ⊆ RESPIRATORY_PPE
  "gas_analysis": [                                          // замеры (форма ОЗП/огневых)
    {"parameter": "oxygen", "value": "20.9", "norm": "≥ 20 об.%", "measured_at": "2026-06-23 08:00"}
  ]
}
```

**Валидация** `validate_type_specific("gas_hazardous", payload)` — новая ветка `elif kind == "gas_works"`:
- ключи payload ⊆ `{respiratory_ppe, gas_analysis}`;
- `respiratory_ppe` — через `_validate_code_list(…, RESPIRATORY_PPE, "respiratory_ppe")`;
- `gas_analysis` — через общий `_validate_gas_analysis`;
- `None`/пустой payload — всегда ок; виды с `structured_kind=None` по-прежнему отвергают непустой `type_specific` → `ValueError` → 422.

## 5. Печатная секция — ветка `gas_works` в `build_structured_section`

- `title="Защита органов дыхания и анализ среды (528)"`;
- `kv=[("СИЗОД", ", ".join(RESPIRATORY_PPE.get(c, c) for c in ppe))]` (если СИЗОД заданы);
- `table=_gas_table(ts.get("gas_analysis"))` (если замеры заданы) — идентично ОЗП/огневым;
- если ни СИЗОД, ни замеров → секция не выводится (`None`).

## 6. Бэкенд-обвязка (без миграции, без правок схем/сервисов)

Проверено по коду — generic, изменений не требует:
- `schemas/work_permit.py`: `type_specific: dict | None` + `@model_validator(mode="after")` уже зовёт `profiles.validate_type_specific(self.work_type, self.type_specific)`. 422-контракт для `gas_hazardous` работает автоматически.
- `services/work_permit_print.py`: уже передаёт `legal_reference` и `structured_section` из `profiles.*` по `work_type`. Новая ветка подхватывается без правки сервиса.
- `domains/work_permits/service.py`: CRUD уже сохраняет/обновляет `type_specific` (draft-only edit).

Итог: **единственный изменяемый файл бэкенда — `profiles.py`** (+ тесты).

## 7. Фронтенд (буквальный паритет с ОЗП/огневыми)

- `lib/workPermitVocab.ts`: += `RESPIRATORY_PPE_LABELS` (код→рус-метка); `GAS_PARAMETER_LABELS` переиспользуется.
- `types/forms/workPermits.ts`: += `RESPIRATORY_PPE_CODES` + `gasWorksSchema` (`respiratory_ppe: array(enum).optional()` + `gas_analysis: array(gasMeasurementSchema).optional()`); `type_specific` расширяем до надмножества ключей всех видов (`confinedEnvSchema.merge(fireSafetySchema).merge(gasWorksSchema)` или эквивалент). Серверная `validate_type_specific` остаётся источником истины по виду.
- `features/work-permits/WorkPermitFormDialog.tsx`:
  - ветка структурной секции по `work_type`: `gas_hazardous` → чек-лист СИЗОД (чекбоксы по `RESPIRATORY_PPE_CODES`, паттерн `toggleSystem`, пишет в `type_specific.respiratory_ppe`) + текст-подсказка по параметрам замеров;
  - `toBody`: добавить `gas_hazardous` в список видов, чей `type_specific` уходит в payload (сейчас `["confined_space","hot_work"].includes(...)` → += `gas_hazardous`);
  - `DialogDescription` — динамическое по `work_type` (механизм уже есть).
- `pages/work-permits/WorkPermitDetailPage.tsx`: read-only блок для `gas_hazardous` (СИЗОД через `RESPIRATORY_PPE_LABELS` + замеры через `GAS_PARAMETER_LABELS`), по образцу существующих `confined_space`/`hot_work`-блоков.

**Намеренно НЕ структурируется** (в generic-поля, прецедент ОЗП/огневых): продувка/вентиляция, подготовка места, контроль среды в процессе, эвакуация/связь, наблюдающий → `measures_*_text` / `special_conditions_text` / роль `observer`.

## 8. Demo-seed (лёгкий, идемпотентный)

Новая `_seed_work_permit_gas_demo(session, tenant_db_id, person)` в `services/demo_bootstrap.py` рядом с `_seed_work_permit_confined_demo`/`_seed_work_permit_hot_work_demo` (та же сигнатура — `(session, tenant_db_id: str, person)`, без `site`), вызывается из `bootstrap_demo_tenant` сразу после `_seed_work_permit_hot_work_demo`. Lookup-or-create по `number="WP-GAS-DEMO"`, идемпотентно: `WorkPermit(work_type="gas_hazardous", zone_text=…, type_specific={"respiratory_ppe":["hose_mask"], "gas_analysis":[{"parameter":"oxygen","value":"20.9","norm":"≥ 20 об.%"}]})` + 1–2 члена бригады. Цель: газоопасный наряд печатается «из коробки» (528 в шапке + СИЗОД + таблица замеров).

## 9. Тесты

- **profiles** (unit, чистый): `legal_reference("gas_hazardous")` = строка 528; `validate_type_specific("gas_hazardous", …)` accept (валидный gas-payload) / reject (неизвестный ключ; плохой код СИЗОД; плохой `parameter` замера; непустой payload для `None`-вида); `build_structured_section("gas_hazardous", …)` для `gas_works` (СИЗОД + таблица; только СИЗОД; только замеры; пусто→None); **guard-полнота реестра** `set(PROFILES) == lifecycle.WORK_TYPES` (не должна сломаться); регресс огневых (`fire_safety`) после выноса `_validate_code_list`.
- **schemas** (422-матрица): `gas_hazardous` create с валидным `type_specific` (ок) / невалидным (422); `type_specific` для `None`-вида (электро/земляные) → 422.
- **print-service**: газоопасный наряд → DOCX содержит «528» в шапке + строку СИЗОД + таблицу замеров; **высота (782н)/ОЗП (902н)/огневые (1479) не регрессировали**.
- **frontend** (vitest): форма рендерит газоопасную секцию при `work_type=gas_hazardous` (чек-лист СИЗОД + подсказка) и скрывает `safety_systems`/ОЗП/огневой блоки; деталь-страница показывает СИЗОД (+ замеры read-only, если заданы).

Прогон локально (Win + Py3.13.7/.venv; канон Py3.12.12 = CI, выключен — [[ci_disabled_actions_off]]); сигнал — EXIT-код / маркер `===RC=$LASTEXITCODE===` ([[py313_win_pytest_invocation]]). Фронт — `npm run build` + vitest.

## 10. Объём НЕ включает (YAGNI / следующие срезы)

- Глубокий тираж электро (903н, +группы электробезопасности бригады) / земляных — остаются профили-заглушки (`legal_reference` есть, `structured_kind=None`, generic-поля).
- Группу газоопасных работ I/II как отдельную сущность/поле — прозой в `special_conditions_text`.
- Пиксель-точную типографику официального бланка 528 (как и у 782н/902н/1479 — полный юр-значимый наряд, но не факсимиле формы).
- **Построчный редактор замеров `gas_analysis` на форме** (для всех видов) — остаётся отложенным; замеры через API/seed, на форме редактируется только чек-лист (СИЗОД/средства/вентиляция), read-only показ на деталь-странице.
- Конфигурируемость профилей по тенанту (жёсткие по приказам — YAGNI).

## 11. Ветка и merge

`feat/work-permit-gas-hazardous-528` от `feat/work-permit-hot-work-1479` (стопкой; огневые ещё не в `main`). Кодовых блокеров нет; порядок merge — решение пользователя (CI off → local-evidence). Канон Py3.12 CI = финальный гейт.
