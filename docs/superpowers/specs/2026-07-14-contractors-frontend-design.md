# Подрядчики — полный фронтенд (contractors.py, 23 эндпоинта)

- **Дата:** 2026-07-14
- **Ветка:** `feat/contractors-frontend` (от `main`)
- **Статус:** design approved, к реализации
- **Backend (готов):** `backend/app/api/routes/contractors.py` — 23 эндпоинта, mount `/api/v1/contractors`

## Проблема

Backend реализует полный домен подрядчиков (реестр, сотрудники, документы, инциденты,
комплаенс, флоу допуска, tenant-level политика требований к документам), но фронт —
только **read-only агрегат**: [ContractorsPage.tsx](../../../frontend/src/pages/contractors/ContractorsPage.tsx)
строит одну таблицу реестра поверх `operationsApi.getContractorSnapshot()`. Нет ни
создания/редактирования, ни детального просмотра, ни документов, ни допуска, ни требований.

Цель — вывести **все 23 эндпоинта** в UI, следуя конвенциям репозитория.

## Цели / вне рамок

**Цели**
- Реестр подрядчиков: список + CRUD (создание, редактирование, архивирование).
- Детальная страница `/contractors/:id` с вкладками: Обзор, Сотрудники, Документы, Инциденты.
- Флоу допуска сотрудника: readiness → checklist → admit (с корректной обработкой 200-warning / 409 / 404).
- Tenant-level политика «Требования к документам» (вкладка на списке).
- Tenant-wide «Истекающие документы» (вкладка на списке).
- Права: новый `CONTRACTOR_MANAGE`, все write-действия под `<Can>`.
- Тесты (vitest) + прохождение typecheck/test/build.

**Вне рамок**
- Изменения backend (`contractors.py` не трогаем).
- Загрузка файлов документов. Поле `file_id` в диалоге документа — **необязательное текстовое поле** (id уже существующего файла). Собственный upload-flow не делаем в этой итерации.
- Массовые операции, экспорт реестра.

## Раскладка всех 23 эндпоинтов по UI

### `/contractors` — список, вкладки

**Вкладка «Реестр»**
- `GET /contractors/registry` — таблица реестра.
- `POST /contractors/registry` — диалог «Новый подрядчик».
- `PATCH /contractors/registry/{id}` — диалог «Изменить».
- `DELETE /contractors/registry/{id}` — действие «Архивировать» (soft-delete, 204).
- Счётчики в шапке: агрегируются из `GET /contractors/employees`, `GET /contractors/incidents`,
  `GET /contractors/documents/expiring` (tenant-wide) — для stat-плиток и производных колонок
  (кол-во сотрудников / инцидентов на подрядчика). Клик по строке → `/contractors/:id`.

**Вкладка «Истекающие документы»**
- `GET /contractors/documents/expiring` (без `contractor_id`) — tenant-wide таблица (DUE_SOON/OVERDUE).

**Вкладка «Требования к документам»**
- `GET /contractors/document-requirements` — таблица политики (тип × область × обязательность).
- `POST /contractors/document-requirements` — диалог «Добавить требование» (409 при дубле doc_type/scope).
- `DELETE /contractors/document-requirements/{id}` — действие «Удалить».

### `/contractors/:id` — деталь, вкладки

**Вкладка «Обзор»**
- `GET /contractors/registry/{id}` — карточка (name, legal_name, inn, статус, компания-заказчик, контакты).
- `GET /contractors/compliance-summary?contractor_id={id}` — KPI: разбивка admission/training/medical по статусам.

**Вкладка «Сотрудники»**
- `GET /contractors/employees?contractor_id={id}` — таблица сотрудников (позиция, три статуса комплаенса).
- `POST /contractors/employees` — диалог «Добавить сотрудника».
- `PATCH /contractors/employees/{id}` — диалог «Изменить» (position + access/training/medical status).
- Допуск (в `EmployeeAdmissionDialog`, открывается из строки):
  - `GET /contractors/employees/{id}/readiness` — вердикт (status/violations/warnings).
  - `GET /contractors/employees/{id}/document-checklist` — по-требованиям статус сбора документов.
  - `POST /contractors/employees/{id}/admit` — действие «Допустить».

**Вкладка «Документы»**
- `GET /contractors/documents?contractor_id={id}&employee_id=&doc_type=&status=` — таблица с фильтрами.
- `POST /contractors/documents` — диалог «Добавить документ» (валидация принадлежности employee→contractor: 422).
- `GET /contractors/documents/{id}` — детали (по необходимости; поля уже есть в списке через `_document_body`).
- `PATCH /contractors/documents/{id}` — диалог «Изменить».
- `DELETE /contractors/documents/{id}` — «Архивировать» (204).

**Вкладка «Инциденты»**
- `GET /contractors/incidents?contractor_id={id}` — таблица.
- `POST /contractors/incidents` — диалог «Зарегистрировать инцидент».

## Архитектура и файлы

Следуем существующим паттернам: типизированный `api/<domain>.ts` (как
[permits.ts](../../../frontend/src/api/permits.ts), [committees.ts](../../../frontend/src/api/committees.ts)),
`RegistryPageHeader`+`RegistryTable`+`useLocalRegistry`+`useAsyncResource` для списков,
`features/<domain>/*Dialog.tsx` для форм, `<Can permission=…>` для write-гейтинга,
детальный маршрут `/x/:id` (как work-permits).

**Новые файлы**
- `frontend/src/types/dto/contractors.ts` — канонические DTO (Registry, Employee, Incident, Document,
  Requirement, ComplianceSummary, Readiness, DocumentChecklist) + enum `ComplianceStatus`,
  литералы `DocType`, `Scope`.
- `frontend/src/api/contractors.ts` — `contractorsApi` со всеми методами (registry/employees/incidents/
  compliance/admission/documents/requirements). Base `/contractors`.
- `frontend/src/pages/contractors/ContractorDetailPage.tsx` — деталь с 4 вкладками.
- `frontend/src/features/contractors/ContractorFormDialog.tsx` — create/edit реестра.
- `frontend/src/features/contractors/ContractorEmployeeFormDialog.tsx` — create/edit сотрудника.
- `frontend/src/features/contractors/ContractorIncidentFormDialog.tsx` — create инцидента.
- `frontend/src/features/contractors/ContractorDocumentFormDialog.tsx` — create/edit документа.
- `frontend/src/features/contractors/DocumentRequirementFormDialog.tsx` — create требования.
- `frontend/src/features/contractors/EmployeeAdmissionDialog.tsx` — readiness + checklist + admit.

**Изменяемые файлы**
- `frontend/src/pages/contractors/ContractorsPage.tsx` — рефакторинг на `contractorsApi` + вкладки
  (Реестр / Истекающие документы / Требования). Клик по строке → деталь.
- `frontend/src/router/pageRegistry.tsx` — lazy-регистрация `ContractorDetailPage`.
- `frontend/src/router/routeGroups.tsx` — маршрут `/contractors/:id` под `CONTRACTOR_VIEW`.
- `frontend/src/permissions/permissions.ts` — `CONTRACTOR_MANAGE: "contractor.manage"`.
- `frontend/src/api/operations.ts` — при необходимости переиспользовать DTO из `types/dto/contractors.ts`
  (сохранить существующие type-экспорты обратносовместимо; `getContractorSnapshot` не ломать, т.к. на него
  могут ссылаться другие потребители — проверить и, если единственный потребитель ContractorsPage,
  снять зависимость аккуратно, оставив snapshot нетронутым для analytics).

## Права

Модель прав — клиентская: `resolvePermissions` в
[ability.ts](../../../frontend/src/permissions/ability.ts) отдаёт либо серверный список, либо
`ROLE_PERMISSIONS[role]`; owner/admin проходят всё через `isAdminUser`.

- Добавить `CONTRACTOR_MANAGE: "contractor.manage"`. Авто-выдаётся owner/admin (`ALL_PERMISSIONS`)
  и `ot_pb_head` (all кроме manage_tenants) — соответствует backend write-ролям admin/owner/hse_head.
- Чтение — существующий `CONTRACTOR_VIEW` (маршрут уже под ним).
- Backend остаётся истинным энфорсером (abac read/write роли) независимо от UI-гейтинга.

## Ключевое поведение

**Флоу допуска (`EmployeeAdmissionDialog`)**
- Открытие: грузим `readiness` + `document-checklist` параллельно, показываем вердикт и по-требованиям статус.
- «Допустить» → `POST /admit`:
  - `200` + `status:"warning"` → успех с предупреждениями (не блок), обновляем список.
  - `200` + `status:"ok"` → успех.
  - `409 requirements_not_met` → показываем `detail.details[]` списком нарушений, без закрытия.
  - `404` → сотрудник не найден (редкая гонка), сообщение + закрытие.

**Feature-flag `contractors`**
- Эндпоинты documents / admission / requirements отдают `404 "Contractors feature is not enabled for this tenant"`
  при выключенной фиче (registry/employees/incidents/compliance — НЕ gated).
- Хелпер `isFeatureDisabledError(error)` (детект по тексту detail) → рисуем «мягкое» состояние
  («Функция документов подрядчиков не включена для тенанта»), а не `ErrorState`.
- Для локальной проверки (preview) — убедиться, что демо-тенанту включён флаг `contractors`; иначе
  вкладки Документы/Требования и допуск покажут «мягкое» состояние (это корректное поведение).

**Прочие ошибки**
- Документ с `employee_id`, не принадлежащим `contractor_id` → `422`, показать в диалоге.
- Дубликат требования (doc_type/scope) → `409`, показать в диалоге.
- Общие ошибки — существующие `ErrorState`/`EmptyState`/`LoadingScreen`.

## Данные / загрузка

- **ContractorsPage**: один загрузчик через `useAsyncResource` — registry + employees(все) + incidents(все)
  + expiring(tenant) для stat-плиток и производных колонок; requirements грузятся при активации своей вкладки.
- **ContractorDetailPage**: грузим registry/{id} + compliance-summary на входе; сотрудники/документы/инциденты —
  по активации вкладки (или все сразу через `Promise.all`, если проще; объёмы малы). Каждый write-диалог по
  `onSubmitted` вызывает reload соответствующего ресурса.

## План тестов

Vitest по образцу существующих `frontend/src/__tests__` и `pages/**/*.test.tsx` (мок `@/api/contractors`):
- `ContractorsPage`: рендер вкладок; stat-плитки; create-диалог вызывает `contractorsApi.createRegistry`;
  строка ведёт на `/contractors/:id`.
- `ContractorDetailPage`: рендер шапки + 4 вкладок; загрузка сотрудников/документов/инцидентов; compliance KPI.
- Флоу допуска: readiness/checklist рендерятся; admit при 409 показывает нарушения; при 200-warning — успех.
- Требования: create/delete вызывают API; 409 обрабатывается.
- «Мягкое» состояние при 404 feature-flag на вкладке Документы.

Гейты перед PR: `npm --prefix frontend run typecheck`, `npm --prefix frontend run test`,
`npm --prefix frontend run build`. Затем прогон в браузере через preview.

## Доставка

- Ветка `feat/contractors-frontend` от `main`.
- Спек коммитится первым; далее — план реализации (skill writing-plans) и пошаговая реализация.
- Backend не меняется — миграций нет.

## Открытые вопросы

Нет (все архитектурные решения зафиксированы: детальная страница с вкладками; полный объём 23 эндпоинта
за один план; требования — вкладкой на списке).
