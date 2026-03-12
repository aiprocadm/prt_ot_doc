# FRONTEND_TEST_PLAN

## 1. Цели тестирования

- Гарантировать стабильность маршрутизации, защиты доступа и tenant-aware поведения.
- Зафиксировать критические пользовательские потоки платформы (документы, шаблоны, задачи, архив/поиск, approvals, client-portal).
- Удерживать quality gate фронтенда в зелёном состоянии: lint + typecheck + test.

## 2. Текущий стек

- Unit/component: **Vitest + Testing Library**.
- Статический контроль: **ESLint**, **TypeScript (strict)**.
- Текущая команда тестов запускает coverage (`vitest run --coverage`).

## 3. Базовые команды качества

Запускать из `frontend/`:

1. `npm run lint`
2. `npm run typecheck`
3. `npm run test -- --run`

## 4. Ключевые уже покрытые сценарии

1. **Protected routing / permissions**
   - `ProtectedRoute.test.tsx`, `Can.test.tsx`, `ability.test.ts`, `RightDrawerPermissions.test.tsx`, `AppRouterSmoke.test.tsx`.

2. **Tenant safety / request preparation**
   - `apiClient.test.ts`, `tenantStore.test.ts`, `TenantGate.test.tsx`.

3. **Критические экранные потоки**
   - documents + wizard + diff: `DocumentsPage.test.tsx`, `DocumentsWizardPage.test.tsx`, `ReplaceDiffViewer.test.tsx`;
   - tasks/timeline: `TasksPage.test.tsx`, `TaskTable.test.tsx`;
   - archive/search filters + saved views: `ArchiveSearch.test.tsx`;
   - approvals inbox: `ApprovalsInboxPage.test.tsx`;
   - incidents/inspections list behavior: `IncidentsPage.test.tsx`, `InspectionsPage.test.tsx`.

4. **Новый тест в этом инкременте**
   - `TemplateDetails.test.tsx`:
     - рендер версий;
     - read-only текущей версии;
     - активация выбранной версии и проверка вызова store action.

## 5. Интеграционные проверки (план)

Приоритетно добавить browser-level e2e (Playwright/Cypress, в зависимости от принятого в репозитории контура):

1. `RBAC/ABAC matrix`:
   - запрет/доступ к маршрутам;
   - скрытие действий;
   - read-only режимы для `client` и `auditor_ro`.

2. `Master package flow`:
   - preset -> upload -> mapping -> dry-run/diff -> run -> monitor -> export/sign/edo.

3. `Client portal isolation`:
   - проверка отсутствия утечки данных из основного контура.

4. `Archive global search`:
   - фильтры, сохранённые представления, переходы в карточки.

## 6. Пробелы покрытия

- Недостаточно e2e-покрытия сложных сквозных процессов.
- Не везде формализованы негативные backend-контракты (409/422/500 с прикладным payload).
- Нужна глубже автоматизация сценариев файлового доступа/скачиваний с проверкой прав.

## 7. Definition of Done для изменений фронтенда

Изменение считается завершённым, если:

1. маршрут и права корректно описаны/проверены;
2. есть loading/error/empty/access-denied состояния;
3. добавлен или обновлён соответствующий тест;
4. проходят `lint`, `typecheck`, `test`;
5. обновлены `docs/FRONTEND_*`, если изменилась архитектура/маршруты/матрица доступа.
