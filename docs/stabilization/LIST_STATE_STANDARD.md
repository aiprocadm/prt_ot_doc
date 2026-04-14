# Стандарт состояний реестров

Для страниц со списками и таблицами используем единый порядок отображения:

1. `ErrorState` с `onRetry`.
2. `LoadingScreen` только при первичной загрузке (`itemsCount === 0`).
3. `EmptyState` только если `!loading && !error && itemsCount === 0`.
4. Таблица/список только при `!loading || itemsCount > 0`.

## Базовая обёртка

В `frontend` используется компонент [`ListStateGuard`](../../frontend/src/components/common/ListStateGuard.tsx), который инкапсулирует этот порядок.

Применять его для новых реестров по умолчанию:

- [DocumentsPage](../../frontend/src/pages/documents/DocumentsPage.tsx)
- [TasksPage](../../frontend/src/pages/tasks/TasksPage.tsx)
- [PacksPage](../../frontend/src/pages/packs/PacksPage.tsx)
- [FilesPage](../../frontend/src/pages/files/FilesPage.tsx)
- [TemplatesPage](../../frontend/src/pages/templates/TemplatesPage.tsx)
- [PersonsPage](../../frontend/src/pages/persons/PersonsPage.tsx)

## Почему это важно

- снимает визуальную дрожь таблицы на первой загрузке;
- делает поведение предсказуемым между разделами;
- снижает риск регрессий при копировании шаблонов страниц.
