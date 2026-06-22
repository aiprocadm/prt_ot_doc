# Дизайн: тираж наряда-допуска на огневые работы (ППР РФ № 1479)

**Дата:** 2026-06-22
**Контур:** Наряды-допуски (§16) — тираж эталона на третий вид работ (огневые)
**Статус:** проектирование (brainstorming → этот спек → writing-plans)
**Ветка:** `feat/work-permit-hot-work-1479` от `main` (высота 782н Ф1→Ф4, слой профилей и ОЗП 902н уже влиты — PR #677/#678/#679/#680)

## 1. Контекст и задача

Контур наряд-допусков доведён до зрелого состояния:
- **Эталон — работа на высоте (Приказ Минтруда № 782н)** — построен полностью (Ф1→Ф4: ядро+FSM+гейт допуска → поля 782н → инструктаж/ежедневный допуск → подписи ПЭП → закрытие актом → печатный бланк DOCX/PDF).
- **Слой профилей** (`domains/work_permits/profiles.py`) вынесен: полиморфный шов per-type-специфики (приказ / структурная секция / валидация `type_specific` / сборка печатной секции). `lifecycle.py` — глобальный FSM+вокабуляр; `print_form.py` — тупой рендерер.
- **Первый тираж — ОЗП (902н)** — построен: structured_kind `confined_env`, секция «анализ воздушной среды + вентиляция» в generic-колонке `type_specific JSON` (миграция wp06).

**Задача:** взять следующий вид — **огневые работы (Постановление Правительства РФ от 16.09.2020 № 1479, ППР, приложение «Наряд-допуск на выполнение огневых работ»)** — как третий полноценный вид через слой профилей.

**Ключевой дивиденд слоя профилей:** колонка `type_specific JSON` универсальна и уже существует → **новая миграция НЕ нужна**. Схемы (`@model_validator` уже зовёт `profiles.validate_type_specific`), CRUD-сервис (уже сохраняет `type_specific`) и сервис печати (уже строит секцию через `profiles.build_structured_section` по `work_type`) — **generic, не меняются**. Реальные правки бэкенда сводятся к одному модулю `profiles.py`.

### Решения пользователя (brainstorming 2026-06-22)
1. **Следующий вид:** огневые работы (1479).
2. **Содержание структурной секции (вариант A):** структурируем юридически-различимое и табличное — (а) чек-лист первичных средств пожаротушения, (б) таблица замеров концентрации горючих паров/газов; прозу мер (подготовка/очистка места, контроль после работ) оставляем в generic-полях `measures_*`/`special_conditions_text`, как для ОЗП.
3. **Фронтенд:** буквальный паритет с ОЗП — на форме чек-лист средств пожаротушения + подсказка по параметрам замеров (как у ОЗП сейчас: вентиляция-select + подсказка). Сами замеры `gas_analysis` задаются через API/seed и показываются read-only на деталь-странице. Построчный редактор замеров на форме остаётся отложенным для обоих видов (уточнено 2026-06-22 после сверки кода: такого редактора нет ни у одного вида).
4. **Demo-seed:** да, лёгкий идемпотентный.

## 2. Профиль `hot_work` (`domains/work_permits/profiles.py`)

Расширяем существующий реестр `PROFILES`. Профиль `hot_work` уже присутствует с верным `legal_reference` («Постановление Правительства РФ от 16.09.2020 № 1479 (ППР)») и `structured_kind=None` — меняем `structured_kind` на новый **`"fire_safety"`** (рядом с `"safety_systems"` высоты и `"confined_env"` ОЗП). `legal_reference` не трогаем.

**Новый словарь — первичные средства пожаротушения** (чек-лист, паттерн `safety_systems` высоты):
```python
FIRE_FIGHTING_MEANS = {
    "extinguisher_powder": "Огнетушитель порошковый",
    "extinguisher_co2": "Огнетушитель углекислотный",
    "water": "Вода (ёмкость/ведро)",
    "sand": "Ящик с песком",
    "felt": "Кошма / асбестовое полотно",
    "fire_hose": "Пожарный кран/рукав",
}
```

**Замеры концентрации — переиспользуют существующий `GAS_PARAMETERS`** (введён для ОЗП): `flammable` «Горючие газы и пары, % НКПР» уже есть и является основным параметром огневых работ; `oxygen`/`harmful` также валидны (огневые во взрывопожароопасных/замкнутых зонах). Отдельный словарь не вводим — без дублирования.

**Целевой рефактор (улучшение кода, в котором работаем):** валидация `gas_analysis` сейчас инлайн в ветке `confined_env` функции `validate_type_specific`. Выносим в чистый хелпер `_validate_gas_analysis(rows)` — его теперь используют ДВЕ ветки (`confined_env` и `fire_safety`); дублировать логику замеров нельзя. Рефактор поведенчески нейтрален для ОЗП (та же проверка), покрыт существующими ОЗП-тестами.

## 3. Форма `type_specific` для огневых

Generic-колонка `type_specific JSON` на `work_permit` (уже есть, миграция wp06). Форма для `hot_work`:
```jsonc
{
  "fire_fighting_means": ["extinguisher_powder", "sand", "felt"],   // коды ⊆ FIRE_FIGHTING_MEANS
  "gas_analysis": [                                                  // замеры концентрации (форма ОЗП)
    {"parameter": "flammable", "value": "0", "norm": "≤ 10 % НКПР", "measured_at": "2026-06-22 08:00"}
  ]
}
```

**Валидация** `validate_type_specific("hot_work", payload)`:
- ключи payload ⊆ {`fire_fighting_means`, `gas_analysis`};
- `fire_fighting_means` (если задано) — список; каждый элемент ∈ `FIRE_FIGHTING_MEANS`;
- `gas_analysis` (если задано) — через общий `_validate_gas_analysis` (список объектов; ключи строки ⊆ {`parameter`,`value`,`norm`,`measured_at`}; `parameter ∈ GAS_PARAMETERS`);
- `None`/пустой payload — всегда ок;
- виды с `structured_kind=None` по-прежнему отвергают непустой `type_specific` → `ValueError` → 422.

**Сборка печатной секции** `build_structured_section("hot_work", …, type_specific=…)` — ветка `fire_safety`:
- `title="Пожарная безопасность огневых работ (1479)"`;
- `kv=[("Средства пожаротушения", ", ".join(FIRE_FIGHTING_MEANS[c] for c in means))]` (если средства заданы);
- `table=StructuredTable(headers=["Параметр","Значение","Норма","Замер"], rows=…)` (если замеры заданы), маппинг параметра через `GAS_PARAMETERS` — идентично ОЗП;
- если ни средств, ни замеров → секция не выводится (`None`), как у прочих kind.

**Намеренно НЕ структурируется** (в generic-поля, прецедент ОЗП): подготовка/очистка места, удаление горючих материалов, контроль места после работ, средства связи/эвакуации → `measures_before_text` / `measures_during_text` / `special_conditions_text`; СИЗ → `ppe_text`; наблюдающий → роль `observer`.

## 4. Бэкенд-обвязка (без миграции, без правок схем/сервисов)

Проверено по коду — generic, изменений не требует:
- `schemas/work_permit.py`: `type_specific: dict | None` уже в `WorkPermitCreate`/`Update`/`Read`; `@model_validator(mode="after")` уже зовёт `profiles.validate_type_specific(self.work_type, self.type_specific)`. 422-контракт работает для `hot_work` автоматически.
- `services/work_permit_print.py`: уже передаёт `legal_reference = profiles.legal_reference(wp.work_type)` и `structured_section = profiles.build_structured_section(wp.work_type, safety_systems=…, type_specific=…)` в `WorkPermitPrintData`. Новая ветка профиля подхватывается без правки сервиса.
- `domains/work_permits/service.py`: CRUD уже сохраняет/обновляет `type_specific` (draft-only edit).

Итог: **единственный изменяемый файл бэкенда — `profiles.py`** (+ тесты).

## 5. Фронтенд (буквальный паритет с ОЗП)

Реальное состояние ОЗП-формы (сверено по коду 2026-06-22): `<select>` вентиляции + текст-подсказка; `gas_analysis` НЕ редактируется на форме, задаётся через API/seed и показывается read-only на деталь-странице (`WorkPermitDetailPage.tsx:318-328`). Огневые делаем по тому же образцу — без построчного редактора замеров (отложен для обоих видов).

- `lib/workPermitVocab.ts`: += `FIRE_FIGHTING_MEANS_LABELS` (код→рус-метка); `GAS_PARAMETER_LABELS` переиспользуется.
- `types/forms/workPermits.ts`: текущая `type_specific: confinedEnvSchema.nullable()` не покрывает огневую форму. += `FIRE_FIGHTING_MEANS_CODES` + `fireSafetySchema` (`fire_fighting_means: array(enum).optional()` + `gas_analysis: array(gasMeasurementSchema).optional()`); `type_specific` расширяем до надмножества ключей обоих видов (zod `confinedEnvSchema.merge(fireSafetySchema)` или эквивалент), чтобы форма обоих видов проходила клиентскую валидацию — серверная `validate_type_specific` остаётся источником истины по виду.
- `features/work-permits/WorkPermitFormDialog.tsx`:
  - ветка структурной секции по `work_type`: `height` → чекбоксы `safety_systems` (как есть); `confined_space` → select вентиляции + подсказка (как есть); **`hot_work` → чек-лист средств пожаротушения (чекбоксы по `FIRE_FIGHTING_MEANS_CODES`, паттерн `toggleSystem`, пишет в `type_specific.fire_fighting_means`) + текст-подсказка по параметрам замеров**; прочие → ничего.
  - `toBody` строка 112 сейчас: `type_specific: v.work_type === "confined_space" ? (v.type_specific ?? null) : null` → **обобщаем** на оба вида: `["confined_space","hot_work"].includes(v.work_type) ? (v.type_specific ?? null) : null`; прочие → `null`.
  - `DialogDescription` — динамическое по `work_type` (label + приказ), механизм уже есть.
- `pages/work-permits/WorkPermitDetailPage.tsx`: для `hot_work` read-only блок (средства через `FIRE_FIGHTING_MEANS_LABELS` + замеры через `GAS_PARAMETER_LABELS`), по образцу существующего `confined_space`-блока (строки 318-328).

## 6. Demo-seed (лёгкий, идемпотентный)

Новая `_seed_work_permit_hot_work_demo(session, tenant_db_id, person, site)` в `services/demo_bootstrap.py` рядом с `_seed_work_permit_confined_demo`, вызывается из `bootstrap_demo_tenant`. Lookup-or-create по `number="WP-HOT-DEMO"`, идемпотентно: `WorkPermit(work_type="hot_work", zone_text=…, type_specific={"fire_fighting_means":["extinguisher_powder","sand"], "gas_analysis":[{"parameter":"flammable","value":"0","norm":"≤ 10 % НКПР"}]})` + 1–2 члена бригады (issuer/foreman) на демо-person. Цель: огневой наряд печатается «из коробки» (1479 в шапке + средства + таблица замеров).

## 7. Тесты

- **profiles** (unit, чистый): `legal_reference("hot_work")` = строка 1479; `validate_type_specific("hot_work", …)` accept (валидный fire-payload) / reject (неизвестный ключ; плохой код средства; плохой `parameter` замера; непустой payload для `None`-вида); `build_structured_section("hot_work", …)` для `fire_safety` (средства + таблица; только средства; только замеры; пусто→None); **guard-полнота реестра** `set(PROFILES) == lifecycle.WORK_TYPES` (уже есть — не должна сломаться); регресс ОЗП-валидации после выноса хелпера.
- **schemas** (422-матрица): `hot_work` create с валидным `type_specific` (ок) / невалидным (422); `type_specific` для `None`-вида → 422.
- **print-service**: огневой наряд → DOCX содержит «1479» в шапке + строку средств пожаротушения + таблицу замеров; **высота (782н + системы безопасности) и ОЗП (902н + газоанализ) не регрессировали**.
- **frontend** (vitest): форма рендерит огневую секцию при `work_type=hot_work` (чек-лист средств пожаротушения + подсказка) и скрывает `safety_systems`/ОЗП-блок; деталь-страница показывает средства (+ замеры read-only, если заданы).

Прогон локально (Win + Py3.13.7/.venv; канон Py3.12.12 = CI, выключен — [[ci_disabled_actions_off]]); сигнал — EXIT-код / маркер `===RC=$LASTEXITCODE===` ([[py313_win_pytest_invocation]]). Фронт — `npm run build` + vitest.

## 8. Объём НЕ включает (YAGNI / следующие срезы)

- Глубокий тираж электро (903н, +группы электробезопасности бригады) / газоопасных / земляных — остаются профили-заглушки (`legal_reference` есть, `structured_kind=None`, generic-поля).
- Пиксель-точную типографику официального бланка 1479 (как и у 782н/902н — полный юр-значимый наряд, но не факсимиле формы).
- Авто-контроль места после огневых работ (наблюдение N часов) как отдельную сущность/таймер — прозой в `special_conditions_text`.
- **Построчный редактор замеров `gas_analysis` на форме** (для обоих видов — огневые и ОЗП) — остаётся отложенным; замеры задаются через API/seed, на форме редактируется только чек-лист средств (огневые) / вентиляция (ОЗП), read-only показ на деталь-странице.
- Конфигурируемость профилей по тенанту (жёсткие по приказам — YAGNI).

## 9. Ветка и merge

`feat/work-permit-hot-work-1479` от `main` (всё предыдущее влито). Кодовых блокеров нет; порядок merge — решение пользователя (CI off → local-evidence). Канон Py3.12 CI = финальный гейт.
