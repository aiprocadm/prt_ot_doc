# P10-03 Медосмотры — срез «Фронт: контингент / направления / отстранения» — Design

**Дата:** 2026-07-09
**Контур:** P10-03 Медосмотры (Section B, `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md:655`; ТЗ `B.8` → `vNext §9.1/§9.2`)
**Предшественник (в main):** психиатрия 342н (PR #729) закрыла последнюю функциональную дыру backend'а.
Роадмап-строка P10-03 фиксирует остаток: **«фронт для контингента/направлений/отстранения (backend готов)»** — это и есть срез.
**Driver:** brainstorming → writing-plans → subagent-driven-development.
**База ветки:** `main`@`5c06b3dc` (merge PR #729). Новая ветка `feat/p10-03-medical-oversight-ui`.
**Тип среза: чисто фронтовый.** 0 миграций, 0 новых эндпоинтов/схем, OpenAPI-baseline и PG16-гейт не затрагиваются
(прецедент — мобильная выдача СИЗ, PR #726).

## Цель

Три полных контура медосмотров живут в API (за флагом `medical`, ETag, RBAC), но не имеют ни одного пикселя UI:

- **контингент** — `GET /medical/contingent/register` (по должностям), `GET /medical/named-list` (поимённый),
  печатные формы обоих (`…/print?format=docx|pdf`), `GET /medical/summary`;
- **направления** — `GET/POST /medical/referrals`, FSM-переход `POST /medical/referrals/{id}/transition`
  (`issued → scheduled → completed/cancelled`; `completed` требует `result_exam_id` осмотра **того же person**),
  bulk-генерация `POST /medical/contingent/generate-referrals` → `{count}`;
- **отстранения** — `GET /medical/suspensions` (+`?status=active`), `POST /medical/suspensions/{id}/lift`
  (backend: только admin/owner, иначе 403).

Срез делает эти контуры видимыми и управляемыми со страницы «Медосмотры и допуски» (`/medical`).

## Принятые решения (brainstorming, 2026-07-09, AskUserQuestion)

1. **Срез = P10-03 фронт медосмотров** (не P10-07 analytics, не §12.4 бюджетный контур) — backend готов,
   высокая видимая ценность, минимальный риск.
2. **Размещение = секции на `MedicalPage`** (не вкладки, не отдельные маршруты) — house-style паттерн
   секционной страницы (прецедент `WarehousePage`, 1141 строк, 8+ секций).
3. **Контингент = оба представления + печать** — реестр по должностям и поимённый список с переключателем
   внутри секции, кнопки скачивания DOCX/PDF для обоих.
4. **Направления = полный FSM-воркфлоу** — список с фильтром, bulk-генерация, ручное создание,
   переходы «Запланировать»/«Отменить»/«Завершить» (с выбором осмотра-результата).

## Инвариант (обязательный якорь)

Существующие секции `MedicalPage` (реестр осмотров, «Психиатрическое освидетельствование (342н)») и их
тесты (`MedicalPage.test.tsx`, 2 passed) остаются зелёными. Backend не трогается вообще — ни одного
изменения в `backend/`.

## Архитектура

### 1. API-слой — `frontend/src/api/operations.ts`

Новые DTO-типы (зеркалируют Pydantic-схемы `backend/app/schemas/medical.py`):

```ts
export type ContingentRegisterRowDto = {
  position_id: string; position_name: string;
  factors: { code: string; name: string }[];
  headcount: number; exam_kinds: string[]; periodicity_months?: number | null;
};
export type NamedListRowDto = {
  person_id: string; full_name: string; position_name?: string | null; department?: string | null;
  factors: { code: string; name: string }[]; required_kinds: string[];
  last_exam_date?: string | null; next_due_date?: string | null; status: string;
};
export type MedicalReferralDto = {
  id: string; person_id: string; exam_kind: string; due_at?: string | null;
  status: "issued" | "scheduled" | "completed" | "cancelled";
  medical_org_name?: string | null; result_exam_id?: string | null; is_overdue: boolean;
};
export type MedicalSuspensionDto = {
  id: string; person_id: string; reason: "unfit" | "contraindication";
  status: "active" | "lifted"; source_exam_id?: string | null;
};
export type MedicalSummaryDto = {
  by_status: Record<string, number>; total: number; overdue_count: number; suspended_count: number;
};
```

Новые методы `operationsApi` (стиль существующих методов файла):

- `getMedicalOversightSnapshot()` — `Promise.all`: `/medical/summary` + `/medical/contingent/register` +
  `/medical/named-list` → `{ summary, register, namedList }` (одна загрузка для шапки и секции контингента);
- `downloadContingentRegisterPrint(fmt: "docx" | "pdf")`, `downloadNamedListPrint(fmt)` —
  `apiClient.get(url, { params: { format: fmt }, responseType: "blob" })` + `downloadBlob` из
  `frontend/src/utils/download.ts` (паттерн `api/sout.ts` / `api/workPermits.ts`); имя файла — из
  локальной константы (`Content-Disposition` не парсим — консистентно с `sout.ts`);
- `listMedicalReferrals(params?: { status?: string })` → `GET /medical/referrals` (limit 100);
- `createMedicalReferral(payload: { person_id: string; exam_kind: string; due_at?: string; medical_org_name?: string })`;
- `transitionMedicalReferral(id: string, payload: { to: string; result_exam_id?: string })`;
- `generateMedicalReferrals()` → `POST /medical/contingent/generate-referrals` → `{ count: number }`;
- `listMedicalSuspensions(params?: { status?: "active" })`;
- `liftMedicalSuspension(id: string)`.

### 2. Страница — `frontend/src/pages/medical/MedicalPage.tsx` (single-file, house-style)

Три независимых `useAsyncResource`-блока добавляются к двум существующим:

- `oversight` — `getMedicalOversightSnapshot()` (summary + register + namedList);
- `referrals` — `listMedicalReferrals({ status: referralStatusFilter })` (перезагрузка при смене фильтра
  и после мутаций);
- `suspensions` — `listMedicalSuspensions(activeOnly ? { status: "active" } : undefined)`.

Существующий `data` (exams/persons/tasks) переиспользуется: словарь `person_id → full_name` для
резолва имён в направлениях/отстранениях; осмотры person'а — для пикера «Завершить».

**Шапка (`RegistryPageHeader`):** stats заменяются данными `/medical/summary`:
«Позиций контингента» (`summary.total`), «Просрочено/отсутствует» (`summary.overdue_count`),
«Активных отстранений» (`summary.suspended_count`). Клиентские подсчёты по exams убираются
(источник истины — backend-агрегат). При падении `oversight`-загрузки шапка показывает прочерки
(stats опциональны), сама секция — `ErrorState`.

**Секция «Контингент медосмотров»:**
- переключатель представлений (локальный `useState`, две кнопки-таба в заголовке секции):
  - **«По должностям»** — таблица: Должность · Численность · Факторы (`code — name` через запятую) ·
    Виды осмотров (RU-лейблы) · Периодичность, мес;
  - **«Поимённый список»** — таблица: ФИО · Должность · Подразделение · Виды осмотров ·
    Последний осмотр · Следующий · Статус (`StatusBadge`);
- кнопки «Реестр DOCX» / «Реестр PDF» / «Поимённый DOCX» / «Поимённый PDF» (per-view — показываются
  кнопки активного представления); 503 (`pdf_renderer_unavailable`) → локальное сообщение об ошибке
  секции, не page-error;
- RU-лейблы статусов контингента (единая константа страницы):
  `ok` → «В норме», `due_soon` → «Истекает», `overdue` → «Просрочен», `missing` → «Отсутствует»
  (зеркало `domains/medical/print_form.py:23`);
- RU-лейблы видов осмотров: `periodic` → «Периодический», `preliminary` → «Предварительный»,
  `psychiatric` → «Психиатрическое (342н)», `fluorography` → «Флюорография», `health_book` → «Медкнижка».

**Секция «Направления»:**
- заголовок: кнопка **«Сформировать по контингенту»** → `generateMedicalReferrals()` → сообщение
  «Создано направлений: N» + `referrals.reload()`;
- **форма ручного создания** (сворачиваемая, паттерн форм `WarehousePage`): Сотрудник (select из
  `data.persons`) · Вид осмотра (select, 5 RU-лейблов) · Срок (date, опц.) · Медорганизация (text, опц.)
  → `createMedicalReferral` → reload;
- **фильтр по статусу** (select: Все / Выдано / Запланировано / Завершено / Отменено) — server-side
  `?status=`;
- **таблица**: Сотрудник · Вид · Статус (badge; `is_overdue` → доп. бейдж «Просрочено») · Срок ·
  Медорганизация · Действия:
  - `issued` → «Запланировать» (`transition {to: "scheduled"}`), «Отменить» (`{to: "cancelled"}`);
  - `scheduled` → «Завершить», «Отменить»;
  - `completed` / `cancelled` — терминальные, без действий;
- **«Завершить»** раскрывает инлайн-строку выбора осмотра-результата: select из
  `data.exams.filter(e => e.person_id === referral.person_id)` (лейбл: `exam_type · exam_date`) +
  кнопка «Подтвердить» → `transition {to: "completed", result_exam_id}`. Если осмотров у person нет —
  текст-подсказка «Сначала зафиксируйте осмотр в реестре выше» вместо селекта. Кнопка «Подтвердить»
  disabled без выбранного осмотра (backend-контракт: `completed` без `result_exam_id` → 422).

**Секция «Отстранения»:**
- чекбокс «Только активные» (default on) — server-side `?status=active`;
- таблица: Сотрудник · Причина (`unfit` → «Негоден», `contraindication` → «Противопоказания») ·
  Статус (`active` → «Действует», `lifted` → «Снято») · Осмотр-источник (`source_exam_id` резолвится
  в `exam_type · exam_date` по `data.exams`, иначе «—») · Действие;
- для `active`: кнопка **«Снять отстранение»** с `window.confirm` (паттерн подтверждений репо) →
  `liftMedicalSuspension(id)` → reload (+ reload шапки: `suspended_count` меняется);
- **фронт-гейтинга по ролям нет** (осознанно): backend отдаёт 403 для не-admin/owner, фронт показывает
  ошибку секции — консистентно с сид-кнопкой психиатрии на этой же странице.

**Обработка ошибок мутаций:** локальный `useState<string | null>` на секцию (`referralError` /
`suspensionError` / `printError`), заполняется в `catch` человекочитаемым текстом (детали от
`api_problem_detail` если есть), сбрасывается при следующем действии. Мутации не валят страницу.

### 3. Что НЕ трогаем

- Существующие секции (реестр осмотров, психиатрия 342н) и их методы API.
- `backend/` целиком; `routeGroups`/`pageRegistry`/`navigationConfig` (маршрут `/medical` уже есть).
- `permissions.ts` — новых permission-констант не вводим (решение №4 + прецедент страницы).

## Тестирование

`frontend/src/__tests__/MedicalPage.test.tsx` расширяется (мок `operationsApi` — полный, по граблям
`OpsPages.test.tsx`: страница на маунте зовёт ВСЕ методы):

1. секции «Контингент», «Направления», «Отстранения» рендерятся с данными (имена person резолвятся);
2. переключатель представлений контингента: реестр ↔ поимённый список;
3. «Сформировать по контингенту» вызывает `generateMedicalReferrals`, показывает счётчик, перезагружает список;
4. создание направления шлёт корректный payload;
5. «Запланировать»/«Отменить» шлют `{to: "scheduled"|"cancelled"}`;
6. «Завершить»: выбор осмотра обязателен; подтверждение шлёт `{to: "completed", result_exam_id}`;
   у person без осмотров — подсказка вместо селекта;
7. «Снять отстранение»: confirm → `liftMedicalSuspension`; отказ в confirm — вызова нет;
8. скачивание печати: `downloadContingentRegisterPrint("pdf")` вызывается (мок `createObjectURL`
   не нужен — blob-логика внутри API-метода, мокается сам метод);
9. существующие 2 теста страницы остаются зелёными.

## Верификация (гейты среза)

- `npx vitest run src/__tests__/MedicalPage.test.tsx` — точечно;
- полный `vitest run` (НЕ параллельно с pytest; при флейке — подозрительные файлы в изоляции);
- `npm --prefix frontend run typecheck` (`tsc` 0);
- `npm --prefix frontend run build` (exit 0).

Backend-гейты (pytest / OpenAPI baseline / PG16) — **не требуются** (нет изменений backend).

## Осознанные границы (follow-up, вне среза)

- Пикеры ограничены первыми 100 persons / 100 exams (существующее ограничение `getMedicalSnapshot`);
  серверный typeahead — follow-up.
- Печатная форма направления на ОПО / решения врачебной комиссии (из handoff психиатрии).
- Редактор маппинга должность→вид деятельности 342н на UI.
- Пагинация направлений server-side (limit 100 хватает демо/малым тенантам; таблица пагинируется клиентски).
- ETag/304-оптимизация списков на фронте (apiClient не кэширует — консистентно со всеми страницами).
