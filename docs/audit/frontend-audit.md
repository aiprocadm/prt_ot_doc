# Frontend audit (2026-02)

## Текущее состояние
- Routing: React Router v6 с lazy routes и `MainLayout/AuthLayout`.
- API: единый axios-клиент (`frontend/src/api/client.ts`) с токен-рефрешем и tenant header enforcement.
- State: Zustand stores по доменам.
- UI: базовые shadcn-like UI-компоненты + общие registry-компоненты.
- Tests: Vitest + Testing Library (smoke/feature tests), Python pytest для backend.

## Проблемы, найденные в аудите
1. **Разрозненный UX реестров** — повторяемые паттерны таблиц, фильтров и действий не полностью унифицированы.
2. **Documents UX gap** — не хватало явного wizard-потока для `template_code/template_version` и видимого pipeline status.
3. **Tasks UX gap** — в реестре не было быстрых действий по закрытию задач.
4. **Employee card depth** — карточка сотрудника была одноэкранной без доменных вкладок.
5. **Dev admin onboarding** — отсутствовал безопасный/воспроизводимый workflow входа в админку в Codespaces без коммита паролей.

## План внедрения
1. Ввести `RegistryTable` и перейти на него в ключевых реестрах (Documents/Tasks).
2. Добавить `DocumentCreateWizard` с idempotency-key, pipeline status и отображением `request_id`.
3. Расширить Tasks table быстрым действием закрытия (`PATCH /tasks/{id}`).
4. Обновить Employee карточку вкладками `Training/PPE/Risks/Medical`.
5. Добавить dev-only admin bootstrap по env (`ADMIN_BOOTSTRAP/...`) и обновить runbook/README.
6. Доработать тесты smoke для Documents/Tasks/Employee и discovery-настройки в Codespaces.
