# Дизайн: экран «Личные допуски» (Permit UI, Л1)

- **Дата:** 2026-06-17
- **Контур:** Личные допуски (Permit), ТЗ B.15 / vNext §16 — фронтенд-срез «Л1».
- **Статус backend:** полностью на `main` (`/permits` CRUD + lifecycle + авто-просрочка). Этот срез — **только фронтенд**, серверный код не меняется.
- **Драйвер:** `brainstorming` → `writing-plans` → реализация.

## 1. Контекст и цель

Backend личных допусков влит (`backend/app/api/routes/permits.py`, `backend/app/domains/permits/*`, `backend/app/schemas/permit.py`), но **экрана нет** — пользователь не может ни увидеть, ни завести допуск из интерфейса. Цель: дать специалисту по ОТ (роль `admin`) рабочий экран управления личными допусками поверх уже готового API.

«Личный допуск» (`Permit`) = запись «сотрудник X допущен к работе Y до даты Z» (например, «работа на высоте»), заводится вручную или авто-создаётся из обучения. Это **не** медицинский допуск-по-здоровью (он живёт на `/medical`). Поэтому экран — отдельный пункт меню, чтобы не путать две сущности.

## 2. Объём

**В объёме (Л1):**
- Страница `/permits`: список допусков с поиском, фильтром по статусу, переключателем «только просроченные», пагинацией, счётчиками (всего / действует / просрочено).
- Создание допуска (модальная форма).
- Редактирование допуска (только пока действует).
- Продление (новая дата «действует до»).
- Отзыв (с подтверждением, без причины — API причину не принимает).
- Права: только роль `admin` (зеркало backend).

**Вне объёма (отдельные срезы, не здесь):**
- Справочник типов допусков — тип остаётся свободным текстом (это срез Л2).
- Demo-данные (срез Л3).
- Просмотр работником своих допусков / расширение прав на другие роли (потребует доработки backend).
- Экран наряда-допуска §16 (контур Н, отдельные срезы).

## 3. Аудитория и права

- Единственная роль — `admin` (специалист по ОТ). Backend-ручка `/permits` гейтит и чтение, и запись на `required_roles=["admin"]`.
- Во фронтенде `permissions.ts`: у роли `admin` стоит `ALL_PERMISSIONS`, поэтому новые коды получит только admin:
  - `PERMIT_VIEW = "permit.view"` — пункт меню + маршрут + видимость страницы.
  - `PERMIT_MANAGE = "permit.manage"` — кнопки «Новый допуск» / «Редактировать» / «Продлить» / «Отозвать».
- Backend не меняем: расширять права на другие роли — отдельный объём.

## 4. Контракт API (уже построен — справочно)

Базовый путь `/permits` (клиент `apiClient` сам подставляет `Authorization` и `X-Tenant`):

| Метод | Путь | Тело | Ответ | Заметки |
|---|---|---|---|---|
| GET | `/permits?person_id=&status=&expired_only=&limit=&offset=` | — | `PermitPage {items: PermitRead[], total}` | `status` и `expired_only` **взаимоисключающие** (иначе 422) |
| POST | `/permits` | `PermitCreate` | `201 PermitRead` | 404, если `person_id`/`position_id` не найдены |
| GET | `/permits/{id}` | — | `PermitRead` | 404 |
| PATCH | `/permits/{id}` | `PermitUpdate` | `PermitRead` | редактируемо **только в статусе active**; иначе 409 `PERMIT_TRANSITION_INVALID` |
| POST | `/permits/{id}/extend` | `PermitExtend {valid_until}` | `PermitRead` | active/expired → active; иначе 409 |
| POST | `/permits/{id}/revoke` | — (без тела) | `PermitRead` | active/expired → revoked; revoked терминальный → 409 |

Типы (зеркало `backend/app/schemas/permit.py`):

```
PermitRead   = { id, person_id, position_id|null, permit_type, issued_at,
                 valid_until|null, status, is_expired, created_at, updated_at }
PermitCreate = { person_id, permit_type, issued_at?, valid_until?, position_id? }
PermitUpdate = { permit_type?, valid_until?, position_id? }
PermitExtend = { valid_until }
```

Статусы: `active` | `expired` | `revoked`. Поле `is_expired` — вычисляемое (может быть `true`, даже когда `status="active"`, если фоновая авто-просрочка ещё не отработала).

## 5. Архитектура фронтенда (вариант A — «лёгкий»)

Следуем конвенциям существующих экранов. Данные — через `useAsyncResource` + api-модуль (как `ppe`/`prescriptions`); форма — модалка на `react-hook-form` + `zod` (как `PersonFormDialog`). **Без Zustand-стора** — допуски используются только на этом экране (YAGNI).

Новые/изменяемые файлы:

| Файл | Назначение |
|---|---|
| `frontend/src/api/permits.ts` | api-модуль: `listPermits(params)`, `createPermit`, `updatePermit`, `extendPermit`, `revokePermit` поверх `apiClient`. |
| `frontend/src/types/dto/permits.ts` | типы `PermitDto`, `PermitPage`, payload-типы. |
| `frontend/src/types/forms/permits.ts` | `permitSchema` (zod) + `PermitFormValues`. |
| `frontend/src/pages/permits/PermitsPage.tsx` | страница: заголовок+счётчики, фильтры, `RegistryTable`, состояния loading/error/empty, обработка действий. |
| `frontend/src/features/permits/PermitFormDialog.tsx` | модалка создания/редактирования (выбор сотрудника, тип, даты). |
| `frontend/src/features/permits/PermitExtendDialog.tsx` | мини-модалка продления (одна дата). |
| `frontend/src/permissions/permissions.ts` | + `PERMIT_VIEW`, `PERMIT_MANAGE`. |
| `frontend/src/router/pageRegistry.tsx` | lazy-импорт `PermitsPage`. |
| `frontend/src/router/routeGroups.tsx` | защищённый маршрут `/permits` под `PERMIT_VIEW`. |
| `frontend/src/router/navigationConfig.ts` | пункт меню «Личные допуски» (группа «ОТ и ПромБез»). |
| `frontend/src/__tests__/PermitsPage.test.tsx` | тест: loading/empty + гейт прав. |

Переиспользуем готовые компоненты: `RegistryPageHeader`, `RegistryTable`, `LoadingScreen`, `ErrorState`, `EmptyState`, `StatusBadge`, `Can`, `Dialog`, `Input`, `Label`, `Button`.

## 6. Поток данных

1. `PermitsPage` грузит **параллельно**: список допусков (`listPermits`), список сотрудников (`/persons`) и три лёгких count-запроса для счётчиков.
2. Счётчики — независимо от пагинации, через count-запросы (`limit=1`, читаем поле `total`): всего (`/permits`), действует (`/permits?status=active`), просрочено (`/permits?expired_only=true`). Точные при любом размере списка.
3. Сотрудники нужны, чтобы показать ФИО вместо `person_id` и наполнить выпадающий список в форме (приём как в «снапшотах» медосмотров). Сопоставление `person_id → ФИО` в памяти; в таблице показываем ФИО (fallback на `person_id`, если сотрудник не найден).
4. Поиск/пагинация — локально через `useLocalRegistry` (как `prescriptions`). Фильтр по статусу и «только просроченные» — параметры запроса к API (т.к. это серверные фильтры; помним про их взаимоисключение: при включённом «только просроченные» селект статуса блокируется).
5. После create/update/extend/revoke — `reload()` списка и счётчиков, `toast` об успехе.

## 7. Логика статусов и доступности действий

Значок статуса (`StatusBadge`):
- `revoked` → «Отозван» (серый).
- иначе `is_expired === true` **или** `status === "expired"` → «Просрочен» (красный).
- иначе → «Действует» (зелёный).

Доступность действий в строке (зеркало FSM backend):
- **Редактировать** — только `status === "active"` (PATCH active-only).
- **Продлить** — `status` ∈ {`active`, `expired`} (и при `is_expired`).
- **Отозвать** — `status` ∈ {`active`, `expired`}; для `revoked` действий нет.

Даже если фронт ошибётся с доступностью, backend вернёт 409 `PERMIT_TRANSITION_INVALID` — показываем понятный `toast`, список перегружаем.

## 8. Форма создания/редактирования

Поля:
- **Сотрудник** — нативный `<select>` из загруженного списка сотрудников (обязательно). При редактировании — только для чтения (смена сотрудника = другой допуск).
- **Тип допуска** — `<Input>` свободный текст (справочник — срез Л2). Подсказка-плейсхолдер «напр. Работа на высоте».
- **Выдан** — `<Input type="date">` (необязательно; backend по умолчанию ставит сегодня).
- **Действует до** — `<Input type="date">`.

Поле `position_id` API принимает, но в форме Л1 **не показываем** (необязательное; вынесено за объём, добавим позже при необходимости).

Валидация: `zod` (сотрудник и тип — обязательны). Серверные ошибки полей — через `applyApiFieldErrorsToForm`. Продление — отдельная мини-модалка с одной датой (vs полная форма редактирования, недоступная для просроченных).

## 9. Обработка ошибок

- Загрузка списка упала → `ErrorState` с кнопкой «Повторить».
- Пустой список (с учётом фильтров) → `EmptyState` с подсказкой создать допуск.
- 409 на действие → `toast.error` с текстом из `PERMIT_TRANSITION_INVALID`, затем `reload()`.
- 422 (статус + «только просроченные» одновременно) не достижим из UI: переключатель блокирует селект статуса.
- 404 на действие (допуск удалён в параллельной сессии) → `toast.error` + `reload()`.

## 10. Тестирование

- `frontend/src/__tests__/PermitsPage.test.tsx` (vitest + testing-library, мок `permitsApi` и `useAuthStore`):
  - рендер списка из мок-данных (ФИО подставлены);
  - состояние «пусто» → `EmptyState`;
  - роль без `permit.manage` → кнопка «Новый допуск» недоступна (гейт прав);
  - значок статуса: просроченный (по `is_expired`) показывается как «Просрочен».
- Ручная проверка через dev-preview (страница рендерится, действия дёргают нужные ручки) — на этапе верификации.

## 11. Критерии приёмки

1. `/permits` доступен только admin; другим ролям пункт меню и маршрут закрыты.
2. Список показывает ФИО, тип, даты, корректный значок статуса; работают поиск, фильтр по статусу, «только просроченные», пагинация.
3. Создание/редактирование/продление/отзыв работают против реального API и обновляют список.
4. Действия в строке показываются по правилам FSM; 409/404 обрабатываются понятным сообщением.
5. Тест компонента зелёный; сборка фронта без ошибок типов/линта.

## 12. Открытые вопросы

Нет. Тип допуска осознанно остаётся свободным текстом до среза Л2 (справочник).
