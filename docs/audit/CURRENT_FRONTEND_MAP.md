# Current Frontend Map

## Ключевые точки маршрутизации

- Router shell: `frontend/src/router/AppRouter.tsx`
- Protected routes: `frontend/src/router/routeGroups.tsx`
- Documents/search feature routes: `frontend/src/router/features/documentRoutes.tsx`, `frontend/src/router/features/searchAndFilesRoutes.tsx`
- Lazy pages registry: `frontend/src/router/pageRegistry.tsx`
- Main navigation: `frontend/src/components/layout/SideNav.tsx`
- Layout shell: `frontend/src/layouts/MainLayout.tsx`, `frontend/src/components/layout/TopNav.tsx`

## Навигация (as-is)

### Документооборот

- `/documents`
- `/templates`
- `/packs`
- `/generation` и `/documents/wizard`
- `/pipelines/runs`
- `/archive`
- `/search`

### ОТ/ПБ и операционка

- `/risk`
- `/activities`
- `/training`
- `/briefings`
- `/incidents`
- `/inspections`
- `/audit-prep`
- `/ppe`
- `/warehouse`
- `/tasks`
- `/workflow`
- `/notifications`
- `/calendar`

### Бизнес и администрирование

- `/reports`
- `/exports`
- `/analytics/trends`
- `/crm-finance`
- `/admin`
- `/admin/billing`
- `/admin/outbox`
- `/settings`
- `/audit`
- `/integrations`

### Клиентский портал

- `/client-portal/dashboard`
- `/client-portal/packages`
- `/client-portal/documents`
- `/client-portal/history`
- `/client-portal/requests`

## UX/IA проблемы

1. Перегруженный первый уровень меню: много разделов с неоднородной терминологией.
2. Смешение доменных и технических сущностей (`pipelines`, `jobs`, `workspace` рядом с бизнес-разделами).
3. Разрывы контекста: ключевые действия часто доступны только из глобального раздела, не из карточки сущности.
4. Дубли пользовательских путей (`/generation` и `/documents/wizard`), что снижает предсказуемость.
5. Неравномерная детализация в IA: у одних доменов глубокая структура, у других — только плоский список.
6. В UI-слое есть прямые API-вызовы, из-за чего сложнее поддерживать и тестировать пользовательские сценарии.

