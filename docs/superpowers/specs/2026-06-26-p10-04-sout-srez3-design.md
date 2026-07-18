# P10-04 СОУТ — срез-3: полу-авто предложения норм СИЗ/медосмотров

**Дата:** 2026-06-26
**Контур:** P10-04 «СОУТ» (ФЗ-426 / TZ B.10), срез-3
**Ветка:** `feat/sout-srez3-p10-04` (stacked на `feat/sout-srez2-p10-04`)
**Предшественники:** срез-1 skeleton (PR #696), срез-2 версионирование класса (PR #697)

## Проблема

Срез-2 дал прозрачную историю изменения класса условий труда (`SoutClassHistory` +
`is_class_worsening`). Но класс СОУТ остаётся изолированным: при выявлении вредного
фактора на рабочем месте администратору приходится **вручную** заводить
соответствующие нормы СИЗ и медосмотры в других контурах, без подсказки от СОУТ.

Полный авто-каскад (СОУТ сам пишет строки норм) отвергнут осознанно: он требует
кросс-модульной хирургии на `PPENorm`/`MedicalNorm`/personal card и непрозрачно
мутирует чужие таблицы. Выбран **полу-авто** путь: СОУТ строит явные связи
к должности и вредности, затем **предлагает** нормы; запись остаётся за
администратором через существующие эндпоинты целевых контуров.

## Решения (зафиксированы в brainstorming)

1. **Тип каскада:** полу-авто предложения (advisory с явными мостами). СОУТ
   ничего не мутирует в СИЗ/медосмотрах.
2. **Мосты:** явные nullable FK + ручной маппинг (не name/code-эвристики).
3. **Модель предложений:** read-проекция (без новой таблицы предложений),
   дедуп против уже существующих норм, идемпотентно.
4. **Объём целей:** СИЗ + медосмотры — две параллельные проекции.

## Технический контекст

- `TenantBaseModel(TenantBase, __abstract__=True)` — общая `metadata` с `TenantBase`.
  `RiskHazard(TenantBase)` и `SoutFactor(TenantBaseModel)` в одной метадате →
  **cross-base барьера нет**. Подтверждение: `PPENorm.hazard_id → risk_hazards.id`
  и `SoutWorkplace.person_id → person.id` уже работают (срез-1 зелёный).
- `PPENorm` (`backend/app/models/models.py`): ключи `position_id` (FK `position.id`),
  `hazard_id` (FK `risk_hazards.id`), `item_name`, `quantity`, `interval_days`,
  `item_id`. Unique `(tenant_id, position_id, hazard_id, item_name)`. Создаётся
  **только вручную** через `POST /ppe/norms` — авто-вывода сегодня нет.
- Медицинский движок (`backend/app/domains/medical/...`): `factors_for_hazards`,
  `required_exams_from_factors` уже выводят виды/периодичность осмотров из
  `RiskHazard.medical_factor_code → MedicalFactor` (29н). Срез-3 **переиспользует**
  его, а не дублирует.
- `SoutWorkplace.position_name` — свободный текст (НЕ FK). Срез-3 добавляет
  отдельную явную связь `position_id`, не трогая `position_name`.

## Архитектура

### 1. Схема — миграция `so03` (аддитивная, цепь `so03 → so02`)

Два моста, форма зеркалит `PPENorm`:

| Колонка | Тип | Поведение |
|---|---|---|
| `SoutWorkplace.position_id` | `String(36)` FK `position.id` | `nullable=True`, `ondelete=SET NULL`, `index=True` |
| `SoutFactor.hazard_id` | `String(36)` FK `risk_hazards.id` | `nullable=True`, `ondelete=SET NULL`, `index=True` |

- `SET NULL` (не `CASCADE`): удаление должности/вредности обнуляет связь, но не
  стирает строку СОУТ — измерение условий труда неизменяемо как факт.
- Downgrade честно дропает обе колонки.
- Имена таблиц литералами в миграции (audit-static-analysis урок).
- Guard-тест: цепь single-head (`so03→so02`), наличие/форма колонок.

### 2. Чистый движок проекций — `backend/app/domains/sout/suggestions.py`

Чистые функции по образцу `build_report` — принимают уже загруженные ORM-строки
(или `SimpleNamespace` в тестах), без сессии:

**`build_ppe_norm_suggestions(workplace, factors, existing_norms) -> list[PpeNormSuggestion]`**
- Только для РМ со связанной `position_id`.
- По каждому фактору со связанной `hazard_id`: предложить норму СИЗ для пары
  `(position_id, hazard_id)`, **если для этой пары нет ни одной `PPENorm`**
  (дедуп по наличию — item_name мы не угадываем).
- Поля предложения: `position_id`, `hazard_id`, `hazard_title`, `factor_name`,
  `factor_code`, `measured_class`, `reason` (напр. «СОУТ класс 3.2 по фактору „Шум"»).
- Дедуп: если у пары `(position_id, hazard_id)` уже есть ≥1 норма — предложения нет.

**`build_medical_exam_suggestions(workplace, factors, factor_catalog, existing_medical_norms) -> list[MedicalExamSuggestion]`**
- Переиспользует `factors_for_hazards` / `required_exams_from_factors`.
- Из связанных hazards → `medical_factor_code` → `MedicalFactor` → виды осмотра +
  периодичность.
- Предложить там, где нет `MedicalNorm` для `(position_id, exam_kind)`.
- Поля: `position_id`, `exam_kind`, `periodicity_months`, `factor_code_29n`, `reason`.

### 3. Сервис / роуты — `backend/app/api/routes/sout.py`

- Расширить CRUD РМ: принимать/патчить `position_id` (валидация существования,
  tenant-scoped getter, 404 на чужой/несуществующий) — ручной маппинг должности.
- Расширить CRUD фактора: принимать/патчить `hazard_id` (та же валидация) —
  ручной маппинг вредности.
- Новый эндпоинт: `GET /sout/workplaces/{id}/norm-suggestions`
  → `{"ppe": [...], "medical": [...]}` — read-проекция, ETag как у прочих GET.
- **Подтверждение предложения** НЕ добавляет путь записи в СОУТ: администратор
  вызывает существующий `POST /ppe/norms` (СИЗ) / профильный эндпоинт медосмотров
  с предложенными ключами + выбранным item/деталями. Идемпотентно: появилась норма
  → дедуп убирает предложение.

### 4. Фронтенд (тонкий, по образцу среза-2)

`frontend/src/pages/sout/SoutPage.tsx` + `frontend/src/api/sout.ts`:
- В карточке РМ: селектор «Связать должность» (`position_id`); пер-фактор
  «Связать вредность» (`hazard_id`).
- Lazy-секция «Предложения норм» (ppe[] + medical[]) с пометкой «подтвердите в
  разделе СИЗ / Медосмотры». Только поверхность чтения — без inline-создания норм,
  чтобы не сцеплять модули.
- За `SOUT_VIEW` + флаг `sout` (как срезы 1–2).

## Поток данных

```
Админ связывает РМ → position_id (PATCH workplace)
Админ связывает фактор → hazard_id (PATCH factor)
                  │
                  ▼
GET /sout/workplaces/{id}/norm-suggestions
   ├─ build_ppe_norm_suggestions(workplace, factors, existing PPENorm)
   │     для каждой (position_id, hazard_id) без нормы → предложение СИЗ
   └─ build_medical_exam_suggestions(workplace, factors, factor_catalog, existing MedicalNorm)
         hazards → medical_factor_code → 29н факторы → виды осмотра без MedicalNorm
                  │
                  ▼
Админ подтверждает → POST /ppe/norms (существующий) → дедуп убирает предложение
```

## Обработка ошибок

- PATCH `position_id`/`hazard_id` на несуществующий/чужой id → 404 (tenant-scoped
  getter, как остальные FK-валидации в роуте).
- Кампания закрыта (не planned/in_progress) → `ensure_campaign_open` → 409
  (мост — это редактирование реестра).
- `GET norm-suggestions` для РМ без `position_id` → `{"ppe": [], "medical": []}`
  (не ошибка — просто нечего предлагать без моста).
- Фактор без `hazard_id` молча пропускается в проекции (не вносит предложений).

## Тестирование (~20+ новых, весь СОУТ зелёный)

- `test_so03_*_migration`: цепь single-head, наличие/форма колонок, downgrade.
- models/schemas: новые поля `position_id`/`hazard_id` + сериализация.
- движок предложений (юнит, без сессии):
  - связано (position+hazard) и нормы нет → предложение есть;
  - дедуп: норма для пары уже есть → предложения нет;
  - РМ без `position_id` → пусто;
  - фактор без `hazard_id` → не вносит предложение;
  - `reason` содержит класс + имя фактора;
  - медицинская проекция переиспользует движок 29н (виды/периодичность из фактора).
- роуты: PATCH `position_id`/`hazard_id` (успех + 404 на битый FK), эндпоинт
  предложений (форма ответа, ETag/304), изоляция тенантов.

## Объём НЕ входит (срез-4+)

- Авто-запись норм (полный каскад с мутацией `PPENorm`/`MedicalNorm`).
- Декларация соответствия (классы 1–2).
- Импорт файла отчёта СОУТ + валидация.
- Печатные формы (карта СОУТ / сводная ведомость).
- Агрегат предложений на уровне кампании (`GET /sout/campaigns/{id}/norm-suggestions`).
- Таблица жизненного цикла предложений (pending/accepted/dismissed) с аудитом.

## Заметки реализации

- Зеркалить форму FK `PPENorm` дословно (тот же `String(36)`, та же целевая таблица).
- Движок проекций — чистые функции, как `build_report`; дедуп-множества строить
  из `(position_id, hazard_id)` / `(position_id, exam_kind)` существующих норм.
- Медицинскую проекцию строить **через импорт** `factors_for_hazards` /
  `required_exams_from_factors`, не копировать логику.
- Флаг `sout` default-off; admin role module defaults уже включают `sout` (срез-1).
