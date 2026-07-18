# Дизайн: тираж наряда-допуска на ОЗП (902н) + обобщающий слой «профилей вида работ»

**Дата:** 2026-06-21
**Контур:** Наряды-допуски (§16) — тираж эталона (высота, 782н) на второй вид работ
**Статус:** проектирование (brainstorming → этот спек → writing-plans)
**Ветка-база:** `feat/work-permits-782n-print` (Ф4) — стопкой; merge-порядок = решение пользователя.

## 1. Контекст и задача

Эталонный вид работ — **работа на высоте (Приказ Минтруда № 782н)** — построен полностью (Ф1→Ф4: ядро+FSM+гейт допуска → поля 782н → инструктаж/ежедневный допуск → подписи ПЭП → закрытие актом → печатный бланк DOCX/PDF). Каркас мультивидовости частично заложен: `work_type` — это `frozenset` из 6 значений (`hot_work`, `gas_hazardous`, `height`, `confined_space`, `excavation`, `electrical`), печатная шапка уже подставляет `work_type_label`.

Однако специфика 782н «зашита» в трёх местах:
- **Колонка `safety_systems`** (удерживающие/позиционирования/страховочные/эвакуация/доступ) — чисто высотная секция «системы обеспечения безопасности работ на высоте».
- **Печатная шапка** `print_form.py:99` хардкодит «Приказ Минтруда № 782н» для **всех** видов работ — для огневых/электро это юридически неверно.
- **Форма фронта** жёстко высотная: дефолт `work_type:"height"`, описание «Работа на высоте (форма 782н)», блок `safety_systems` показывается всегда.

**Задача:** взять **один** новый вид работ — **работа в ограниченных и замкнутых пространствах (ОЗП, Приказ Минтруда № 902н)** — глубоко, юридически корректно, как второй полноценный эталон; **заодно вынуть обобщающий слой** («профиль вида работ»), чтобы виды N+1 (огневые 1479, электро 903н, …) добавлялись дёшево.

### Выбранный вид: ОЗП (902н)
902н — приказ Минтруда с тем же скелетом наряда-допуска, что и высота → чистая абстракция. Type-specific секция (анализ воздушной среды / вентиляция) структурно аналогична высотной `safety_systems`.

### Решения пользователя (brainstorming)
1. **Глубина:** один вид глубоко + обобщающий слой (не широко-тонко, не все три сразу).
2. **Вид:** ОЗП (902н) первым.
3. **Хранение type-specific:** generic `type_specific: JSON` + реестр профилей (не выделенные колонки на тип, не дочерняя таблица).
4. **Demo-seed:** да, лёгкий идемпотентный.

## 2. Архитектура: `WorkTypeProfile` (новый чистый модуль)

Новый `backend/app/domains/work_permits/profiles.py` — без I/O / без sqlalchemy, как `lifecycle.py`. Это **полиморфный шов**: вся per-type-специфика (приказ, словари структурной секции, валидация, сборка печатной секции) живёт здесь. `lifecycle.py` остаётся глобальным FSM+вокабуляром; `print_form.py` — тупым рендерером.

```python
@dataclass(frozen=True)
class WorkTypeProfile:
    code: str                    # "height" | "confined_space" | ...
    label: str                   # "Работа в замкнутых пространствах"
    legal_reference: str         # "Приказ Минтруда России от 15.12.2020 № 902н ..."
    structured_kind: str | None  # "safety_systems" | "confined_env" | None
```

**Реестр** `PROFILES: dict[str, WorkTypeProfile]`, ключ = код вида работ. Покрывает ВСЕ 6 видов (guard-тест полноты vs `lifecycle.WORK_TYPES`):

| код | приказ (`legal_reference`) | `structured_kind` |
|---|---|---|
| `height` | Приказ Минтруда № 782н (работа на высоте) | `safety_systems` |
| `confined_space` | Приказ Минтруда № 902н (ОЗП) | `confined_env` |
| `electrical` | Приказ Минтруда № 903н (электроустановки) | `None` |
| `hot_work` | Постановление Правительства РФ № 1479 (ППР, огневые) | `None` |
| `gas_hazardous` | Приказ Минтруда № 902н (смежн.) / generic | `None` |
| `excavation` | generic (СП/правила земляных работ) | `None` |

- **height** читает существующую колонку `safety_systems` (**высота не трогается — ноль churn на отгруженном эталоне**); `type_specific` у неё `null`.
- **confined_space** читает новую `type_specific` JSON.
- Остальные 4 — `legal_reference` заполнен (**чинит юр-баг шапки**), `structured_kind=None` → переиспользуют generic-поля; тираж вглубь — следующие срезы.

**Чистые функции:**
- `profile_for(work_type) -> WorkTypeProfile` (KeyError-safe → дефолт generic для неизвестного, но `WORK_TYPES`-валидация уже на входе).
- `legal_reference(work_type) -> str`.
- `validate_type_specific(work_type, payload) -> None` — raises `ValueError` на неизвестный ключ / плохой вокабуляр / секцию-не-для-этого-вида.
- `build_structured_section(work_type, *, safety_systems, type_specific) -> StructuredSection | None` — собирает уже-олейбленную печатную секцию.

## 3. Структурная секция ОЗП (`type_specific` JSON)

Одна nullable-колонка `type_specific: JSON` на `work_permit`. Миграция **wp06** (`20260621_wp06_work_permit_type_specific`), цепочка `wp05 → wp06`, аддитивная, имя таблицы литералом, честный downgrade (drop колонки). VARCHAR/JSON — без PG-enum ([[enum_pg_label_parity]]); имена литералами ([[audit_static_analysis_blindspots]]).

**Форма ОЗП** (юридически значимое из 902н, чего нет в generic-полях):
```jsonc
{
  "gas_analysis": [                                  // анализ воздушной среды — таблица замеров
    {"parameter": "oxygen", "value": "20.9", "norm": "≥ 20", "measured_at": "2026-06-21 08:00"}
  ],
  "ventilation": "forced"                            // natural | forced | none | not_required
}
```

Словари в `profiles.py`:
- `GAS_PARAMETERS`: `oxygen` «Кислород (O₂), %» / `flammable` «Горючие газы и пары, % НКПР» / `harmful` «Вредные вещества, мг/м³».
- `VENTILATION_MODES`: `natural` «Естественная» / `forced` «Принудительная» / `none` «Не применяется» / `not_required` «Не требуется».

**Намеренно НЕ структурируется** (кладётся в существующие generic-поля — честно, без оверинжиниринга): изоляция/заглушка коммуникаций, очистка/промывка/пропарка, средства связи и эвакуации → `measures_before_text` / `measures_during_text` / `special_conditions_text`; СИЗОД → `ppe_text`; наблюдающий снаружи → уже роль `observer`.

**Валидация формы `type_specific` для ОЗП:** ключи ⊆ {`gas_analysis`, `ventilation`}; каждый замер — ключи ⊆ {`parameter`, `value`, `norm`, `measured_at`}, `parameter ∈ GAS_PARAMETERS`; `ventilation ∈ VENTILATION_MODES` (если задано). Для видов с `structured_kind=None` непустой `type_specific` → ошибка (422).

## 4. Печатный бланк (генерализация `print_form.py`)

Два точечных изменения в чистом рендерере (Ф4):
1. **Заголовок** (`print_form.py:99`): `legal_reference` приходит полем `WorkPermitPrintData` вместо хардкода «№ 782н». H0 строится как `f"НАРЯД-ДОПУСК на производство работ повышенной опасности ({work_type_label}, {legal_reference})"`.
2. **Высото-специфичная строка** «Системы обеспечения безопасности» → заменяется **generic-секцией**:
   - `WorkPermitPrintData.safety_systems_labels: list[str]` → `structured_section: StructuredSection | None`.
   - Новые датаклассы в `print_form.py`:
     ```python
     @dataclass
     class StructuredTable:
         headers: list[str]
         rows: list[list[str]]

     @dataclass
     class StructuredSection:
         title: str
         kv: list[tuple[str, str]]            # label:value-строки
         table: StructuredTable | None        # опц. таблица
     ```
   - Рендер: `add_heading(section.title, level=1)`; каждая `kv` через `_kv`; если `table` — docx-таблица «Table Grid».
   - **height** → `StructuredSection(title="Системы обеспечения безопасности (782н)", kv=[("Системы", "Удерживающие, Страховочные, …")], table=None)`.
   - **confined_space** → `StructuredSection(title="Анализ воздушной среды и вентиляция (902н)", kv=[("Вентиляция", "Принудительная")], table=StructuredTable(headers=["Параметр","Значение","Норма","Замер"], rows=[…]))`.
   - **None-профиль** → секция не выводится.

Секцию собирает **сервис** через `profiles.build_structured_section(...)` и передаёт в `WorkPermitPrintData`. `print_form.py` остаётся без зависимостей от модели/профиля — чистый рендерер.

## 5. Схемы + сервисы (бэкенд-обвязка)

- `WorkPermitCreate` / `WorkPermitUpdate` (`schemas/work_permit.py`): поле `type_specific: dict | None = None`; кросс-полевая валидация через `@model_validator(mode="after")` → `profiles.validate_type_specific(self.work_type, self.type_specific)` (`field_validator` не видит `work_type`). `ValueError` → 422 (по существующему контракту схем). `safety_systems` остаётся как есть (высота, не трогаем).
- `WorkPermitRead`: += `type_specific: dict | None`.
- `domains/work_permits/service.py`: CRUD сохраняет/обновляет `type_specific` (draft-only edit, как прочие поля наряда).
- `services/work_permit_print.py`: `legal_reference = profiles.legal_reference(wp.work_type)` и `structured_section = profiles.build_structured_section(wp.work_type, safety_systems=wp.safety_systems, type_specific=wp.type_specific)` → в `WorkPermitPrintData`. Строка-маппинг `safety_systems → labels` (текущая `:171`) удаляется.

## 6. Фронтенд (параметризация по виду)

- `lib/workPermitVocab.ts`: += `LEGAL_REFERENCE_LABELS` (приказ на вид), `GAS_PARAMETER_LABELS`, `VENTILATION_LABELS`.
- `features/work-permits/WorkPermitFormDialog.tsx`:
  - `DialogDescription` **динамическое** по `work_type` (label + приказ).
  - Структурная секция **условная** по `work_type`: `height` → чекбоксы `safety_systems` (как есть); `confined_space` → редактор строк газоанализа (добавить/удалить замер: параметр-select + значение + норма + дата) + select вентиляции; прочие → ничего.
  - Form-values += `type_specific`; `toBody` сериализует `type_specific` (или `null`).
- `types/forms/workPermits.ts` + `types/dto/workPermits.ts`: += `type_specific`.
- `pages/work-permits/WorkPermitDetailPage.tsx`: показ секции ОЗП (газоанализ + вентиляция) для `confined_space`.

## 7. Demo-seed (лёгкий, идемпотентный)

Новая `_seed_work_permit_confined_demo(session, tenant_db_id, person, site)` в `services/demo_bootstrap.py`, рядом с `_seed_briefing_code_flow_demo`, вызывается из `bootstrap_demo_tenant`. Lookup-or-create по `number` (напр. `"WP-OZP-DEMO"`), идемпотентно: `WorkPermit(work_type="confined_space", zone_text=…, type_specific={"gas_analysis":[{"parameter":"oxygen","value":"20.9","norm":"≥ 20"}], "ventilation":"forced"})` + 1–2 члена бригады (issuer/foreman) на демо-person. Цель: ОЗП-наряд печатается «из коробки» (902н в шапке + таблица газоанализа).

## 8. Тесты

- **profiles** (unit, чистый): `legal_reference` на каждый вид; `validate_type_specific` accept/reject (хороший ОЗП-payload; неизвестный ключ; плохой `parameter`; плохая `ventilation`; непустой `type_specific` для `None`-профиля); `build_structured_section` для height (из `safety_systems`) и confined (из `type_specific`); **guard-тест полноты реестра** — `set(PROFILES) == lifecycle.WORK_TYPES` (зеркало vocab-guard'а Ф4).
- **wp06 migration-guard**: цепочка `wp05 → wp06` single-head, аддитивность (колонка `type_specific` на `work_permit`), честный downgrade (drop).
- **schemas** (422-матрица): ОЗП-create с валидным/невалидным `type_specific`; `type_specific` на height → 422.
- **print-service**: ОЗП-наряд → DOCX содержит «902н» в шапке + таблицу газоанализа + «Принудительная»; высота **не регрессировала** (782н в шапке + строка систем безопасности).
- **frontend** (vitest): форма рендерит ОЗП-секцию при `work_type=confined_space` и скрывает `safety_systems`; деталь-страница показывает газоанализ.

Прогон локально (Win + Py3.13.7/.venv; канон Py3.12.12 = CI, выключен — [[ci_disabled_actions_off]]); сигнал — EXIT-код / маркер `===RC=$LASTEXITCODE===` ([[py313_win_pytest_invocation]]). Фронт — `npm run build` + vitest.

## 9. Объём НЕ включает (YAGNI / следующие срезы)

- Глубокий тираж огневых (1479) / электро (903н) / газоопасных / земляных — сейчас профили-заглушки (`legal_reference` есть, `structured_kind=None`, generic-поля).
- Пиксель-точную типографику официального бланка 902н (как и у 782н — полный юр-значимый наряд, но не факсимиле формы).
- Группы по электробезопасности бригады (903н-специфика) — отдельный срез при тираже электро.
- Конфигурируемость профилей по тенанту (жёсткие по приказам — YAGNI).

## 10. Ветка и merge

`feat/work-permit-types-confined-space` **стопкой поверх `feat/work-permits-782n-print`** (Ф4) — генерализуем `print_form.py` / `WorkPermitPrintData` из Ф4. Кодовых блокеров нет. Порядок merge (Ф4 → этот, либо stacked-PR) — решение пользователя (CI off → local-evidence).
