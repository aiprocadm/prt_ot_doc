# SPEC_TRACEABILITY_MATRIX

Статусы: **сделано / частично / отсутствует / сломано**.

| Блок ТЗ | Ожидаемое | Факт в коде | Статус | Связанные артефакты | Блокеры / следующее исправление |
|---|---|---|---|---|---|
| Аренда/Аутентификация/RBAC/ABAC/Аудит | X-Tenant обязателен, изоляция, role+attr checks, immutable audit | Tenant middleware принудительно требует `X-Tenant` для business-route; `/api/v1/auth` больше не открыт целиком (исключение только `/auth/login`), исключения по public-prefix проверяются только на границе пути (без обхода через `/api/v1/publicity`), JWT tenant-scope check + ABAC deps/rules + audit tests | сделано | `backend/app/middleware/tenant.py`, `modules/rbac_abac/*`, `tests/test_tenant_security.py`, `tests/test_auth_tenant_header_enforcement.py`, `tests/test_middleware_tenant.py`, `tests/test_audit_log_immutability.py` | Оставшийся риск: закрыть legacy SAWarning и расширить ABAC edge-case сценарии для сложных скоупов |
| Доменные объекты | ОТ/ПБ/ПромБез/экология/доки | Широкий набор моделей/роутов есть | частично | `api/routes/*.py`, `models/*.py`, `frontend/src/pages/*` | Нужна унификация справочников и контроль mandatory полей |
| Шаблоны/визуализация/замена/PDF | Template->replace->PDF pipeline | Реализовано, есть tests/linter/passport | сделано | `modules/templates/*`, `modules/replace/*`, `modules/pdf/*`, `tests/test_templates_pipeline_api.py` | Добавить нагрузочные тесты и контроль SLA job-очередей |
| EDO/подписание/утверждения | Approval/sign/edo workflow | Core flow есть, mock-провайдеры и тесты есть | частично | `modules/approval`, `modules/approvals`, `modules/sign`, `modules/edo`, `backend/tests/test_next57_approval_sign_edo_services.py` | Добавить провайдер-специфичные интеграционные контракты |
| Основные данные/NPA | Справочники/нормативка | Базовые CRUD есть | частично | `api/routes/npa.py`, `modules/external_registry/*` | Нужна версионируемая NPA governance |
| Риски | Карты риска/методики | Реализовано с сервисами и тестами | частично | `modules/risk/*`, `tests/test_risk_engine.py` | Закрыть ORM relation warnings |
| СИЗ/Склад | Нормы, выдача, контроль | Реализовано базово | частично | `modules/ppe/*`, `api/routes/ppe.py` | Добавить end-to-end отчеты по срокам/остаткам |
| Обучение/брифинги | Назначение/прохождение | Есть training/briefings modules | частично | `modules/training/*`, `modules/briefings/*` | Углубить аналитику и контроль просрочки |
| Инциденты/инспекции/предписания | Полный цикл CAPA | Есть incidents/inspections/capa services | частично | `modules/incidents/*`, `modules/inspections/*`, `modules/capa/*` | Добавить state machine invariants на API уровне |
| CRM/Finance link | Связь с биллингом/финансами | Есть billing/finance базово | частично | `api/routes/billing.py`, `models/finance.py` | Требуется двусторонняя интеграция с внешними ERP |
| Файлы/поиск | Tenant-safe storage/search | Реализовано; дополнительно ограничен TTL presigned download URL (`60..3600` сек) для безопасной эксплуатации | частично | `backend/app/core/config.py`, `tests/test_core_config_utils.py`, `modules/files/storage.py`, `tests/test_files_module_basics.py`, `modules/search/*` | Добавить централизованный AV policy enforcement |
| API/веб-справочники/CLI | OpenAPI + CLI ops | Есть docs/openapi + CLI | частично | `docs/openapi.yaml`, `app/cli/main.py` | Добавить contract checks в CI merge-gate |
| Отчеты/экспорт/дашборды | KPI + экспорт | Есть analytics/export_center | частично | `modules/analytics/*`, `modules/export_center/*`, `tests/test_next62_analytics_search_export_center.py` | Уточнить продуктовые KPI и ownership |
| Клиентский портал | Изолированный доступ клиента | Есть API + frontend страницы | частично | `modules/client_portal/*`, `api/routes/client_portal.py`, `frontend/src/pages/client-portal/*` | Усилить e2e тесты разграничения ролей |
| Биллинг | Ограничения тарифа/квоты | Есть guard middleware/tests | частично | `middleware/billing_guard.py`, `backend/tests/test_billing_guard_middleware.py` | Добавить self-service billing UI audit trail |
| Безопасность/комплаенс | tenant isolation + audit + secure files | Базово есть, критичные проверки покрыты | частично | `docs/security/*`, `tests/test_tenant_security.py`, `tests/test_webhooks_dispatch.py` | Укрепить secret rotation/runbook incident response |
| PWA/оффлайн | offline-ready workflows | Есть pwa_sync модуль, без full offline parity | частично | `modules/pwa_sync/services.py`, `api/routes/pwa_sync.py` | Завершить conflict resolution + offline UX |
| Наблюдаемость/backup/recovery | health/ready/logs/DR | Health/readiness есть, DR частично документирован | частично | `api/routes/health.py`, `docs/ops/*`, `docs/runbooks/RESTORE_TENANT.md` | Автоматизировать backup-restore проверки |
| Тестирование/CI/покрытие | Критический regression gate | Большой набор тестов + `make codex-audit` | сделано | `scripts/codex_audit.sh`, `.github/workflows/ci.yml` | Добавить обязательный publish отчета покрытия |

- [Обновление] Закрыт критический блокер в секции tenancy+webhooks: inbound webhook tasks теперь запускаются в корректном tenant slug-контексте (`webhooks.py`, `edo_workflow.py` + `tests/test_inbound_webhook_tenant_context.py`).

- Дополнение по tenancy-безопасности: закрыт маршрутный bypass через произвольные URL, оканчивающиеся на `openapi.json`; проверка добавлена в `tests/test_middleware_tenant.py`.
