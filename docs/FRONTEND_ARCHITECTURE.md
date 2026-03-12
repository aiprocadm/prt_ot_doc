# FRONTEND_ARCHITECTURE

## 1. Модульная структура

Текущая структура во `frontend/src` организована по устойчивой схеме:

- `api/` — типизированный клиент API, интерсепторы, общая обработка ошибок, tenant/auth headers;
- `router/` — маршрутизация и route-guards;
- `permissions/` — RBAC/ABAC модель (`permissions.ts`, `ability.ts`, `useAbility.ts`);
- `stores/` — Zustand-сторы по доменам (documents, templates, packs, tasks, risk, files, auth, tenant и т.д.);
- `pages/` — экранные модули по бизнес-разделам;
- `features/` — доменные составные компоненты (таблицы, формы, карточки, wizard-потоки);
- `components/` — shared/ui/layout primitives (`ui/*`, `common/*`, `permissions/*`, `layout/*`);
- `types/` — DTO/form-контракты;
- `hooks/`, `utils/`, `config/` — инфраструктурные слои.

## 2. Управление состоянием

- **Глобальное состояние:** Zustand stores по доменам.
- **Локальное UI-состояние:** `useState`/`useEffect` в страницах и фичах.
- **Сброс состояния между тестами:** `stores/reset.ts`.
- **Паттерн загрузки данных:** страницы вызывают доменные store-actions, UI-слой рендерит loading/error/empty.

## 3. API-уровень

- Центральный клиент: `api/client.ts`.
- Ключевые свойства:
  - автоматическое добавление `Authorization`;
  - tenant-context заголовки через `tenantStorage`;
  - единая обработка ошибок (`errorHandling.ts`);
  - поддержка бизнес-модулей (documents, incidents, inspections, approvals, edo, files, pipelines, search, billing).

## 4. Auth / Session / Tenant

- `stores/auth.ts` хранит профиль пользователя, роли, разрешения и статус сессии.
- `api/tokenStorage.ts` — токены доступа/обновления.
- `stores/tenant.ts` и `api/tenantStorage.ts` — контекст арендатора.
- Отсутствие tenant-контекста трактуется как блокер для бизнес-вызовов (через клиент/guards).

## 5. Уровень разрешений (RBAC/ABAC)

- Централизация в `permissions/*`.
- `ROLE_PERMISSIONS` покрывает роли платформы (owner/admin/methodist/lawyer/project_manager/executor/office_manager/trainer/student/ot_pb_head/ot_specialist/pb_engineer/ecologist/hr/accountant/line_manager/client/auditor_ro/contractor_inspector/worker).
- `ability.ts` дополнительно применяет ABAC-ограничения:
  - scope checks (`tenant_id`, `company_id`, `site_id`, `project_id`, `contractor_id`);
  - action checks (пример: подпись/экспорт документа только для релевантного статуса).
- UI-gates:
  - `ProtectedRoute` на уровне маршрутов;
  - `Can`, `PermissionGate`, `ActionButton` на уровне действий/кнопок.

## 6. Зоны маршрутизации

- **Auth-зона:** `/login` + `AuthLayout`.
- **Core app:** `MainLayout` + защищённые бизнес-маршруты.
- **Client portal:** отдельный сегмент `/client-portal/*` с отдельными экранами.
- **Admin:** `/admin/*` маршруты под admin permission.
- **No-access:** `/access-denied`.

## 7. Общие UI-паттерны

В проекте переиспользуются:

- `DataTable`, `RegistryTable`, `SavedViewsBar`, `FilterField`;
- `LoadingScreen`, `EmptyState`, `ErrorState`, `AccessDeniedPage`;
- единые `Card`, `Tabs`, `Dialog`, `Badge`, `Button`, `Input`, `Textarea`;
- layout primitives (`TopNav`, `SideNav`, `RightDrawer`).

## 8. Текущие ограничения архитектуры

- часть сложных потоков пока реализована как list-first без полноценных карточек расследования/жизненного цикла;
- server-side сортировка/пагинация/сохранённые представления не полностью унифицированы между доменами;
- для полного production-hardening нужен расширенный e2e-контур поверх текущего component/unit набора.
