# FRONTEND_ROUTES_AND_PERMISSIONS

Документ фиксирует текущую матрицу доступа в UI: маршруты, разрешения, режимы read-only и скрытие действий.

## 1) Глобальные правила доступа

- Все бизнес-маршруты идут через `ProtectedRoute`.
- При нехватке прав пользователь получает `AccessDeniedPage` (а не runtime-ошибку).
- На уровне компонентов/кнопок используется `Can`/`PermissionGate`/`ActionButton`.
- Для ролей `client` и `auditor_ro` действует приоритетный режим чтения в чувствительных разделах (скрытие create/edit/sign/export действий, если нет прямого permission).

## 2) Основные маршруты и required permission

| Раздел | Маршруты | Permission |
|---|---|---|
| Дашборд | `/dashboard`, `/dashboard/*` | `dashboard.view` |
| Документы | `/documents` | `doc.view` |
| Шаблоны | `/templates` | `template.view` |
| Генерация | `/generation`, `/documents/wizard` | `generation.view` |
| Пакеты | `/packs`, `/pack-runs/:id` | `pack.view` / `doc.view` |
| Пайплайны / Jobs | `/pipelines/runs`, `/jobs`, `/:id` | `doc.view` |
| Архив / Поиск | `/archive`, `/archive/search`, `/search` | `file.view` |
| ЭДО / Согласования | `/approvals/inbox`, `/approvals/outbox`, `/approval-routes`, `/signatures`, `/edo` | `doc.view` |
| Риски | `/risk` | `risk.view` |
| СИЗ | `/ppe` | `ppe.view` |
| Склад СИЗ | `/warehouse` | `warehouse.view` |
| Обучение | `/training` | `training.view` |
| Инциденты | `/incidents` | `incident.view` |
| Проверки/предписания | `/inspections`, `/inspection-plans`, `/inspection-checklists`, `/findings`, `/prescriptions`, `/corrective-actions`, `/inspection-prep/packages` | `inspection.view` |
| CRM / Финансы | `/crm-finance` | `crm_finance.view` |

Примечание: маршрут `/crm-finance` в этой волне переведён с demo-данных на реальные tenant-scoped вызовы `/contracts`, `/orders`, `/invoices` и `/billing/plan` без изменения permission-модели.
| Отчеты / Экспорты | `/reports`, `/exports`, `/analytics/trends` | `reports.view` |
| Интеграции | `/integrations` | `integrations.view` |
| Админка | `/admin`, `/admin/outbox`, `/admin/billing`, `/admin/layout-presets` | `admin.manage_roles` |
| Кабинет клиента | `/client-portal/dashboard`, `/client-portal/packages`, `/client-portal/documents`, `/client-portal/history`, `/client-portal/requests` | `client_portal.view` |

## 3) Дополнительные домены

| Маршруты | Permission |
|---|---|
| `/companies` | `company.view` |
| `/persons` | `person.view` |
| `/files` | `file.view` |
| `/tasks` | `task.view` |
| `/notifications`, `/calendar` | `task.view` |
| `/activities` | `activity.view` |
| `/medical` | `medical.view` |
| `/audit-prep` | `audit_prep.view` |
| `/fire-safety` | `fire_safety.view` |
| `/fire-training` | `fire_training.view` |
| `/fire-inspections` | `fire_inspections.view` |
| `/reference` | `reference.view` |
| `/contractors` | `contractor.view` |
| `/npa` | `npa.view` |
| `/audit` | `audit.view` |
| `/settings` | `settings.view` |
| `/portal-requests` | `reports.view` |

## 4) Где явно read-only

- `TemplatesPage`: если нет `template.create` и `template.edit`, отображается бейдж «Только просмотр», create/edit actions скрываются.
- `ActionButton`: при запрете права кнопка блокируется или скрывается (если `hideWhenDenied=true`).
- `Can`/`PermissionGate`: запрещённые действия не рендерятся.

## 5) Изоляция клиентского портала

- Маршруты клиентского портала находятся в отдельном сегменте `/client-portal/*`.
- Доступ в сегмент возможен только при `client_portal.view`.
- На уровне роли `client` используется ограниченный набор разрешений без админских и операционных write-прав.

## 2026-03-22 note
- No route contract or permission requirement was changed in this wave.
- Further work is still needed on action-level hiding/guarding consistency and tenant bootstrap/switch stability.
