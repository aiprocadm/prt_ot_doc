# P10-04 СОУТ срез-6 «Авто-каскад класса в нормы медосмотров (+ совет по СИЗ)» — Design

**Дата:** 2026-06-28
**Контур:** P10-04 СОУТ (Section B, `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`)
**Предшественники:** срезы 1-5 влиты в main (срез-5 импорт — PR #708, merge `3cd04883`).
**Driver:** brainstorming → writing-plans → subagent-driven-development.

## Цель

Когда класс рабочего места (РМ) меняется (через импорт среза-5 или ручную смену класса),
последствия для **медосмотров** проектируются автоматически: администратор открывает
**preview** «что каскаднёт» → жмёт **«Применить»** → мед-нормы должности обновляются
(штамп класса СОУТ + добор требуемых видов осмотров по факторам 29н). **СИЗ** —
advisory только в preview (авто-создать норму нельзя без выбора конкретного item из каталога).

Устраняет ручную синхронизацию мед-норм после получения/смены класса по результатам СОУТ.
Замыкает контур: `sout_class_history` (срез-2) **детектирует** изменение → каскад **реагирует**.

## Дивиденд без миграции (требование)

`MedicalNorm.working_conditions_class` (колонка `working_conditions_class`, `str | None`)
**уже существует**. `PPENorm` не трогаем. Схема СОУТ не меняется. Критерий приёмки:
`git diff origin/main...HEAD -- backend/app/migrations/versions/` ПУСТ.

## Принятые решения (brainstorming)

1. **Триггер:** Preview + Apply (явно, как срезы 4-5) — не автоматическая запись при смене класса.
2. **Охват:** per-workplace (расширение существующего `GET norm-suggestions` до apply), не batch по кампании.
3. **Apply scope:** Мед = apply (без миграции); СИЗ = advisory в preview.
4. **Reclass:** обновлять `working_conditions_class` **только когда он NULL/пуст**; непустой
   (возможно ручной) класс, отличающийся от текущего, помечается в preview как **conflict** и
   apply **не перезаписывает** его.

## Архитектура — 3 слоя + порт/адаптер (зеркало срезов 4-5)

### Слой 1 — чистый домен `backend/app/domains/sout/cascade.py` (без БД/FastAPI)

Датаклассы:
- `MedicalCascadeAction` — `exam_kind: str`, `op: Literal["create","reclass","conflict"]`,
  `periodicity_months: int`, `interval_days: int`, `target_class: str`, `current_class: str | None`,
  `factor_codes: list[str]`, `reason: str`.
- `PpeAdvisory` — переиспользует `PpeNormSuggestion` (существующая схема).
- `CascadePlan` — `assessed_class: str | None`, `medical: list[MedicalCascadeAction]`,
  `ppe_advisory: list[PpeNormSuggestion]`.

Функции:
- `months_to_interval_days(months: int) -> int` = `months * 365 // 12` (12→365, 60→1825 —
  совпадает с `DEFAULT_INTERVAL_DAYS`).
- `build_cascade_plan(*, assessed_class, factors, hazard_meta, factor_catalog,
  existing_med_norms, existing_ppe_pairs) -> CascadePlan`:
  - `assessed_class is None` → пустой план.
  - **medical:**
    - Требуемые виды осмотров выводятся через существующий `build_medical_exam_suggestions`
      (цепочка `hazard.medical_factor_code → MedicalFactor.exam_kinds →
      required_exams_from_factors` = kind→строжайшая периодичность).
    - `existing_med_norms` — список `(exam_kind, working_conditions_class)` для **общих**
      (`hazard_id IS NULL`) норм должности. Каскад работает только с общими нормами: create
      пишет `hazard_id=NULL`, reclass/conflict оценивает строку с `hazard_id IS NULL` для kind.
      Hazard-специфичные нормы (`hazard_id IS NOT NULL`) каскад не трогает и не учитывает при
      определении «норма для kind есть».
    - Для каждого требуемого `kind`:
      - нет нормы для kind → `op="create"` (interval из months, target_class = assessed_class).
      - норма есть, `working_conditions_class` пуст (None/"") → `op="reclass"` (set target_class).
      - норма есть, класс непуст и ≠ assessed_class → `op="conflict"` (current_class = старый,
        apply пропускает).
      - норма есть, класс == assessed_class → действие не порождается (идемпотентность).
  - **ppe_advisory:** существующий `build_ppe_norm_suggestions` (пары без `PPENorm`).

### Слой 2 — сервис `backend/app/services/sout_cascade.py`

- `preview_cascade(session, tenant, wid) -> CascadePreview` — read; `_get_workplace` `None`→404;
  загружает факторы/hazard-meta/каталог/существующие мед-нормы(+класс)/ppe-пары через loaders
  из `routes/sout.py` (переиспользование, DRY); зовёт `build_cascade_plan`; маппит в схему.
- `apply_cascade(session, tenant, wid) -> CascadeResult`:
  - `ensure_campaign_open` (как срез-5; закрытая кампания → 409 на уровне роута).
  - **Re-derives** план из БД (не доверяет клиенту → идемпотентность повторного apply).
  - Всё-или-ничего в одной транзакции:
    - `op="create"` → `INSERT MedicalNorm(tenant_id, position_id, exam_kind,
      hazard_id=NULL, interval_days, working_conditions_class=assessed_class)`.
    - `op="reclass"` → `UPDATE MedicalNorm.working_conditions_class = assessed_class`
      (только строки с пустым классом).
    - `op="conflict"` → **пропуск** (не записывается; учитывается в `conflicts` счётчике).
    - `ppe_advisory` → **пропуск** при apply.
  - Возвращает `CascadeResult{created, reclassified, conflicts, ppe_advisory_count}`.
- `CascadeApplyError` (если понадобится) → 409/422 на уровне роута.

### Слой 3 — эндпоинты `backend/app/api/routes/sout.py`

- `GET /sout/workplaces/{wid}/cascade/preview` → `CascadePreview`.
- `POST /sout/workplaces/{wid}/cascade/apply` → `CascadeResult`.
- Оба: admin (`_ROLES`), feature-flag `sout` (`_require_sout_enabled`), tenant-iso
  (`TenantContextValidator.ensure_tenant_context`), `@audit_operation` на apply.
- Существующий `GET /workplaces/{wid}/norm-suggestions` **не меняется** (обратная совместимость).

### Слой 4 — фронт

- `frontend/src/api/sout.ts` — интерфейсы `CascadeMedicalAction`/`CascadePreview`/`CascadeResult`
  + методы `previewCascade(wid)` / `applyCascade(wid)`.
- `frontend/src/pages/sout/SoutPage.tsx` — секция «Каскад в нормы» (per-workplace):
  кнопка preview → таблица мед-действий (create/reclass/conflict цветными метками) + блок
  СИЗ-advisory → «Применить» (disabled при отсутствии create/reclass; busy-guard; toast 409).

## Схемы (`backend/app/schemas/sout.py`, миграций 0)

```python
class CascadeMedicalAction(BaseSchema):
    exam_kind: str
    op: Literal["create", "reclass", "conflict"]
    periodicity_months: int
    interval_days: int
    target_class: str
    current_class: str | None = None
    factor_codes: list[str] = []
    reason: str

class CascadePreview(BaseSchema):
    assessed_class: str | None
    can_apply: bool                       # True если есть ≥1 create/reclass
    medical: list[CascadeMedicalAction] = []
    ppe_advisory: list[PpeNormSuggestion] = []

class CascadeResult(BaseSchema):
    created: int
    reclassified: int
    conflicts: int
    ppe_advisory_count: int
```

## Поток данных

```
смена класса РМ (импорт срез-5 / PATCH) → sout_class_history фиксирует
        ↓ (admin открывает)
GET cascade/preview → build_cascade_plan (factors→29н, existing med-norms)
        ↓ (admin жмёт «Применить»)
POST cascade/apply → re-derive план → транзакция:
   create MedicalNorm(class) · reclass пустых · skip conflict/ppe
        ↓
CascadeResult{created, reclassified, conflicts, ppe_advisory_count}
```

## Обработка ошибок

- РМ не найдено / чужой тенант → 404.
- Флаг `sout` выключен → 404 (`_feature_off`).
- Не admin → 403.
- Кампания закрыта → 409 (apply, `ensure_campaign_open`).
- `position_id is None` → preview = пустой план, `can_apply=false`; apply = пустой результат.
- Идемпотентность: повторный apply → `created=0, reclassified=0` (план уже покрыт).

## Тестирование

- `backend/tests/test_sout_cascade_domain.py` — план: create/reclass/conflict/идемпотентный
  skip; пустой при class=None и при position_id=None (через сервис); `months_to_interval_days`
  (12→365, 60→1825); ppe_advisory из факторов.
- `backend/tests/test_sout_cascade_service.py` — apply пишет create + reclass пустых, пропускает
  conflict и ppe; идемпотентность; all-or-nothing; closed-campaign.
- `backend/tests/test_sout_cascade_api.py` — preview/apply happy + flag-off 404 + tenant-iso +
  non-admin 403 + closed-campaign 409.
- `frontend/src/__tests__/SoutCascade.test.tsx` — preview→apply; «Применить» disabled при пустом
  плане; отображение меток create/reclass/conflict.

## Осознанно вне объёма (срез-7+)

- Периодичность, выводимая из самого класса (модель факторо-управляема, не классо-управляема —
  не выдумываем зависимость, которой нет в данных).
- Авто-создание СИЗ-норм (требует выбора item из каталога — человеческое решение; либо миграция
  под класс-привязку PPENorm).
- Batch-каскад по всей кампании (выбран per-workplace; batch — естественный срез-7 поверх этого).
- Soft-delete/деактивация мед-норм при downgrade класса.
- Перезапись непустого `working_conditions_class` (намеренно не трогаем ручные правки —
  только conflict-флаг).
