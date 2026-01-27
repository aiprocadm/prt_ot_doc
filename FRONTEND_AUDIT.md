# Frontend Audit (React + TypeScript)

## Scope
- Аудит фронтенда SPA в `frontend/` согласно чеклисту. Фокус на P0 риски и базовую готовность приложения.

## P0 Issues (fixed in this change)

### P0-1: Отсутствовал обязательный tenant-gate, запросы уходили без контекста
**Impact:** риск утечки/перемешивания данных между арендаторами; запросы стартуют даже без выбранного контура.  
**Repro:**
1. Очистить localStorage.
2. Зайти в приложение.
3. Приложение сразу делает запросы данных, используя “первый” контур по умолчанию без явного выбора.
**Fix:** добавлен `TenantGate`, блокирующий основной интерфейс, пока пользователь не выберет контур, и запрет запросов без `X-Tenant`.  
**Affected files:** `frontend/src/components/layout/TopNav.tsx`, `frontend/src/components/tenant/TenantGate.tsx`, `frontend/src/api/client.ts`, `frontend/src/api/tenantStorage.ts`, `frontend/src/stores/tenant.ts`, `frontend/src/layouts/MainLayout.tsx`.

### P0-2: Кэш стора не сбрасывался при смене контура
**Impact:** данные предыдущего арендатора оставались в Zustand-сторах, что создаёт “bleed” между tenant’ами.  
**Repro:**
1. Выбрать контур A, загрузить список.
2. Переключить контур на B.
3. В списках остаются данные контура A, пока не произойдёт ручная перезагрузка.
**Fix:** добавлены `reset()` методы для stores и общий `resetTenantStores()`; вызывается на смене контура и при logout.  
**Affected files:** `frontend/src/stores/*.ts`, `frontend/src/stores/reset.ts`, `frontend/src/stores/tenant.ts`, `frontend/src/stores/auth.ts`.

### P0-3: Не было глобальной обработки 401/403/409/422/5xx и boundary
**Impact:** ошибки API не перехватывались централизованно; при 401 не происходил корректный возврат на логин; сбой UI приводил к “белому экрану”.  
**Repro:** вернуть 403/422/500 из API или бросить исключение в компоненте.  
**Fix:** добавлен `AppErrorBoundary` и `handleApiError` с редиректом на `/auth/login` + `return-to`, а также toast-сообщениями.  
**Affected files:** `frontend/src/components/common/AppErrorBoundary.tsx`, `frontend/src/api/errorHandling.ts`, `frontend/src/api/client.ts`, `frontend/src/App.tsx`, `frontend/src/utils/returnTo.ts`, `frontend/src/pages/auth/LoginPage.tsx`.

### P0-4: Конфигурация окружения не была централизована и валидирована
**Impact:** невозможно гарантировать корректность `VITE_API_BASE_URL`.  
**Fix:** добавлен валидируемый `appConfig` через Zod.  
**Affected files:** `frontend/src/config/env.ts`, `frontend/src/api/client.ts`.

### P0-5: Приложение не рендерилось из-за отсутствующего икон-экспорта
**Impact:** белый экран при старте UI (Vite runtime error).  
**Repro:** открыть приложение в браузере — падает модуль `lucide-react` из-за отсутствующего `Hospital`.  
**Fix:** заменён на доступный `HeartPulse`.  
**Affected files:** `frontend/src/components/layout/SideNav.tsx`.

## P1 Issues (not fixed)

### P1-1: RBAC/ABAC признаки не применяются в UI
**Impact:** действия и элементы интерфейса не скрываются/не блокируются по ролям, хотя `/auth/me` возвращается.  
**Evidence:** нет проверок ролей/permissions в компонентах.  
**Affected files:** `frontend/src/stores/auth.ts`, страницы и компоненты по всему `frontend/src/pages` и `frontend/src/features`.

### P1-2: Нет отдельных экранов 403/404
**Impact:** пользователи не получают корректных экранов “нет доступа”/“не найдено”, риски по раскрытию наличия объекта.  
**Affected files:** `frontend/src/router/AppRouter.tsx` (нет маршрутов/страниц 403/404).

### P1-3: Документ-карточка неполная относительно требований
**Impact:** отсутствуют таймлайны согласований/EDO, комментарии, подробные статусы и история согласований.  
**Evidence:** `DocumentPreview` показывает только preview + историю версий.  
**Affected files:** `frontend/src/features/documents/DocumentPreview.tsx`.

### P1-4: Tasks Inbox без SLA/overdue, фильтров и открытия карточки
**Impact:** нарушена функциональная полнота задач: нет SLA/overdue бейджей, фильтров, перехода в карточку.  
**Affected files:** `frontend/src/features/tasks/TaskTable.tsx`, `frontend/src/pages/tasks/TasksPage.tsx`.

## P2 Issues (not fixed)

### P2-1: FileUploader без лимитов типов/размера, ретраев и прогресса
**Impact:** слабый UX и потенциальная нестабильность загрузки файлов.  
**Affected files:** `frontend/src/features/files/FileUploader.tsx`.

### P2-2: Wizard skeleton без сохранения черновиков и валидации шагов
**Impact:** неполная поддержка многошаговых форм и возврата к черновикам.  
**Affected files:** `frontend/src/features/packs/PackWizard.tsx` (и другие wizard-потоки).

## Notes
- Проведён минимальный ремонт P0, связанный с tenant-контекстом, глобальными ошибками и конфигурацией.
- Для полноты MVP необходимо закрыть P1/P2 пункты, включая документ-карточки, RBAC-ограничения и расширенную работу с задачами.
