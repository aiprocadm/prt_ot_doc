# FRONTEND_TEST_PLAN

## Стабилизация в рамках финального frontend pass

Проверены и прогнаны базовые quality gates:
- lint
- typecheck
- unit/integration (vitest)

## Добавленные/обновлённые тестовые зоны

1. **Route guards / access matrix**
   - `RoutePermissionMatrix.test.tsx`: проверка client portal isolation + admin-only access.

2. **Role-based action/rendering**
   - Existing guard coverage сохранён (`ProtectedRoute`, `Can`, drawer permissions).

3. **Tenant-aware request preparation**
   - `apiClient.test.ts`: добавлен кейс runtime tenant switch с проверкой корректного `X-Tenant`.

4. **Package wizard navigation + validation + recovery**
   - `PackWizard.test.tsx`: happy path и API fail path с сохранением контролируемого состояния шага.

5. **File upload error states**
   - `FileUploader.test.tsx`: успешная загрузка и отказ AV-проверки.

6. **Archive/search filters + saved views basics**
   - Existing coverage сохранён (`ArchiveSearch.test.tsx`).

## Устранённые flaky/нестабильные зоны

- Усилена предсказуемость UI-веток мастера и загрузчика (явные состояния и ошибки), что снижает недетерминизм тестов.
- Для tenant-aware кейсов добавлена прямая проверка корректной подстановки tenant после переключения.

## Риски, требующие backend/e2e completion

- Полные browser E2E сценарии для multi-tenant изоляции.
- Полноценная end-to-end проверка signed-url upload прогресса с реальным storage backend.
- Расширенная проверка jobs timeline/retry с реальными статусными переходами очереди.


## Текущая стабилизация тестов
- `FileUploader` получил управляемые параметры polling для тестов, что снижает риск таймаутов при проверке веток `ready/error`.
- Для `PackWizard` уточнены ожидания UI-сообщений после submit (успех/ошибка) с повышенным таймаутом ожидания.

## Update: тесты загрузки файлов
- Обновлён тест `uploads file and shows ready progress`: проверка прогресса переведена на устойчивый matcher (`/100%/`).
- Добавлен тест `disables new drops while upload is in progress`, который покрывает блокировку dropzone в процессе активной загрузки.

## Обновление стабилизации (текущий проход)
- Исправлен `typecheck`-блокер: `frontend/src/__tests__/FileUploader.test.tsx`.
- Исправлен flaky route smoke test: `frontend/src/__tests__/AppRouterSmoke.test.tsx`.
- Повторно подтверждено прохождение:
  - `npm run lint`
  - `npm run typecheck`
  - `npm run test`

## Тестовые обновления (текущий коммит)

### Добавлено
- `GeneratePackWizardPage.test.tsx`:
  - защита мастера от невалидного JSON в пользовательском вводе;
  - проверка блокировки перехода при пустом ключе идемпотентности.
- `FileUploader.test.tsx`:
  - сценарий rejected-файла с проверкой информативного error-notification.

### Стабилизировано
- Критичный сценарий «генерация пакета» теперь покрывает edge-case без runtime-crash.
- Проверка UX-ветки отклонения файлов подтверждает наличие пользовательского сообщения об ошибке.
