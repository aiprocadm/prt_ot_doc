# Spec ↔ Code Mapping

> **Назначение:** карта соответствия разделов канонического ТЗ ([`TZ_FULL_UNIFIED.md`](./TZ_FULL_UNIFIED.md)) и блоков продуктовой рамки ([`PLATFORM_VNEXT_UPGRADE_SPEC.md`](./PLATFORM_VNEXT_UPGRADE_SPEC.md)) реальным модулям backend / frontend / тестам.
>
> Если запись помечена как `MVP` в столбце «Тег», значит она входит в раздел A канона; `vNext` — в раздел B (полный объём, см. фазы в `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`).
>
> Проверять статус (`done/partial/missing`) — в [`docs/audit/TZ_COVERAGE_MATRIX.md`](../audit/TZ_COVERAGE_MATRIX.md).

## Платформенное ядро

| Раздел канона / vNext | Тег | Backend | Frontend | Тесты |
|----------------------|-----|---------|----------|-------|
| `A.2.1` / `vNext §32` Multi-tenancy + X-Tenant | MVP | `backend/app/middleware/tenant.py`, `backend/app/modules/tenancy/*`, `backend/app/db/{session,tenant_row_guard}.py` | `frontend/src/stores/tenant.ts` | `tests/test_tenant_header_required.py`, `tests/test_files_tenant_isolation_strict.py` |
| `A.2.2` / `vNext §32` RBAC + ABAC | MVP | `backend/app/modules/rbac_abac/{engine,permission_codes,deps}.py` | `frontend/src/permissions/*` | `tests/test_rbac_abac.py`, `tests/test_rbac_module_access.py`, `tests/test_abac_deny_allow_matrix.py` |
| `A.2.3` / `vNext §32` Immutable audit | MVP | `backend/app/modules/audit/writer.py`, `backend/app/domains/audit/service.py` | `frontend/src/features/audit/*` | `tests/test_audit_log_immutability.py`, `tests/test_audit_chain_and_diff.py` |
| `A.2.4` / `vNext §31.1` Idempotency | MVP | `backend/app/services/idempotency.py` | `frontend/src/features/documents/DocumentCreateWizard.tsx` | `tests/test_idempotency.py`, `tests/test_services_idempotency_unit.py` |
| `A.2.6` / `vNext §31.1` Outbox + DLQ + webhooks | MVP | `backend/app/services/{outbox,webhooks,events}.py`, `backend/app/api/routes/outbox_admin.py`, `backend/app/api/routes/webhooks.py` | `frontend/src/pages/admin/*` | `tests/test_outbox_dispatch.py`, `tests/test_webhook_routing.py`, `tests/test_next43_outbox_webhooks.py` |
| `A.2.7` / `vNext §6` Domain events | MVP | `backend/app/services/{domain_hooks,events}.py` | — | `tests/test_event_completeness_mvp.py`, `tests/services/test_domain_hooks_document_signed.py` |
| `vNext §28.3` Bounded contexts | vNext | `backend/app/modules/*`, `backend/app/domains/*`, `backend/app/api/routes/*` | `frontend/src/{features,pages}/*` | — |

## Документная фабрика и ЭДО

| Раздел | Тег | Backend | Frontend | Тесты |
|--------|-----|---------|----------|-------|
| `A.2.5` / `vNext §6.2` Templates strict | MVP | `backend/app/modules/templates/{service,api}.py`, `backend/app/domains/templating/*` | `frontend/src/features/templates/*`, `frontend/src/pages/templates/*` | `tests/test_template_delete.py`, `tests/test_templates_pipeline_api.py` |
| `vNext §6.3` Header/Footer Engine | MVP | `backend/app/modules/{branding,headers}/*` | `frontend/src/pages/branding/BrandingSettingsPage.tsx`, `frontend/src/pages/documents/DocumentsWizardPage.tsx` | `tests/api/test_branding_api.py`, `tests/headers/test_engine.py` |
| `A.2.9` / `vNext §6.4` Replace Engine | MVP | `backend/app/modules/replace/service.py`, `backend/app/api/routes/replace.py`, `backend/app/domains/replace/*` | `frontend/src/pages/documents/wizard/*` | `tests/test_replace_engine_advanced.py`, `tests/test_replace_api.py` |
| `A.2.8` / `vNext §6.5` Pipeline Engine | MVP | `backend/app/modules/pipelines/orchestrator.py`, `backend/app/services/pipelines_orchestrator.py`, `backend/app/modules/jobs/*` | `frontend/src/pages/PipelineRuns.tsx`, `frontend/src/pages/PipelineRunDetails.tsx`, `frontend/src/pages/documents/*` | `tests/test_next39_pipeline_orchestrator.py`, `tests/test_next23_pipelines.py` |
| `A.2.10` / `vNext §6.6` PDF + шрифты | MVP | `backend/app/modules/pdf/service_pool.py`, `backend/app/services/pdf.py` | `frontend/src/pages/documents/DocumentsPage.tsx` | `tests/pdf/test_validators.py`, `tests/test_documents_generate.py` |
| `vNext §6.7` Document readiness | vNext | `backend/app/modules/doc_render/*`, `backend/app/modules/inspection_prep/*` | `frontend/src/features/documents/*` | `tests/test_inspection_prep.py` (subset) |
| `vNext §6.8` Compare / Visual diff | vNext | `backend/app/modules/templates/*` | `frontend/src/features/documents/*`, `frontend/src/__tests__/{JobTimeline,ApprovalTimeline,WizardJobTimeline}.test.tsx` | `tests/test_replace_engine_advanced.py` (diff-структура) |
| `vNext §6.9` ЭДО и подпись | vNext | `backend/app/modules/{edo,sign,approval,approvals}/*`, `backend/app/api/routes/{edo_workflow,approval_orchestration,approval_signing_v1}.py` | `frontend/src/pages/{edo,signatures,approvals}/*` | `backend/tests/test_next57_approval_sign_edo_services.py` |
| `vNext §6.10` Реестр НПА | vNext | `backend/app/modules/compliance_deadlines/*`, `backend/app/api/routes/{npa,compliance,obligations}.py`, `backend/app/domains/npa/*` | `frontend/src/pages/npa/*` | `tests/api/test_npa_api.py` (если есть) |

## Master data и data quality

| Раздел | Тег | Backend | Frontend | Тесты |
|--------|-----|---------|----------|-------|
| `vNext §5.1` Базовые сущности (org-структура) | MVP | `backend/app/modules/org_structure/*`, `backend/app/api/routes/{companies,sites,departments,persons,tenants,tenancy}.py` | `frontend/src/pages/{companies,persons,reference}/*` | `backend/tests/test_tenant_core_mvp.py` |
| `vNext §5.2` Единая карточка сотрудника (360°) | vNext (Phase 3.2) | `backend/app/api/routes/persons.py` (расширяется) | `frontend/src/pages/persons/*` | планируется |
| `vNext §5.3` Единая карточка объекта | vNext | `backend/app/api/routes/sites.py` | `frontend/src/pages/companies/*`, `frontend/src/pages/access/*` | планируется |
| `vNext §5.4` Data Quality Layer | vNext (Phase 3.1 backend done) | `backend/app/modules/data_quality/{rules,service,schemas}.py`, `backend/app/api/routes/data_quality.py` | `frontend/src/pages/admin/*` (Dashboard UI планируется) | `tests/test_data_quality.py` |

## UX / навигация (vNext §4)

| Раздел | Тег | Backend | Frontend | Тесты |
|--------|-----|---------|----------|-------|
| `vNext §4.2` Role-based workspaces | vNext (Phase 1.1 done) | `backend/app/api/routes/workspace.py` | `frontend/src/pages/workspace/*`, `frontend/src/router/AppRouter.tsx` (LandingRedirect) | `tests/test_workspace_role_based_config.py` |
| `vNext §4.3` Command Center | vNext (Phase 2.1 backend done) | `backend/app/modules/operational_dashboard/*`, `backend/app/api/routes/operational_dashboard.py` | (frontend планируется) | `tests/test_operational_dashboard.py` |
| `vNext §4.4` Smart calendar | vNext | `backend/app/modules/calendar/*`, `backend/app/api/routes/calendar.py` | `frontend/src/pages/calendar/*` | `tests/api/test_notifications_calendar_api.py` (часть) |
| `vNext §4.5` Universal search + command bar | vNext | `backend/app/modules/search/*` | `frontend/src/pages/search/*`, `frontend/src/pages/SearchPage.tsx`, `frontend/src/pages/ArchiveSearch.tsx` | планируется |
| `vNext §31.5` Health checks (платформенный) | vNext (Phase 2.2 done) | `backend/app/modules/health_checks/*`, `backend/app/api/routes/health.py` | — | `tests/test_health_comprehensive.py` |

## Доменные модули

| Раздел | Тег | Backend | Frontend | Тесты |
|--------|-----|---------|----------|-------|
| `A.3.1` / `vNext §11` Risk engine | MVP | `backend/app/modules/risk/services.py`, `backend/app/api/routes/{risk,risk_enterprise}.py`, `backend/app/domains/risk/*` | `frontend/src/features/risk/*`, `frontend/src/pages/risk/*` | `tests/test_risk_engine.py`, `tests/api/test_risk_events.py` |
| `A.3.2` / `vNext §12` СИЗ + склад | MVP / `[v1.1]` склад | `backend/app/modules/ppe/*`, `backend/app/domains/ppe/*` | `frontend/src/pages/ppe/*`, `frontend/src/pages/warehouse/*` | `tests/api/test_ppe_events.py`, `backend/tests/test_ppe_access_parity.py` |
| `A.3.3` / `vNext §7–8` Обучение/инструктажи | MVP | `backend/app/modules/training/*`, `backend/app/modules/briefings/*`, `backend/app/domains/training/*`, `backend/app/api/routes/{training,training_next,briefings,journals,attestations}.py` | `frontend/src/pages/training/*`, `frontend/src/pages/briefings/*` | `tests/api/test_training_api.py`, `backend/tests/test_training_access_parity.py` |
| `A.3.4` / `vNext §13–14` Инциденты / проверки / CAPA / предписания | MVP / `[v1.2]` prescriptions | `backend/app/modules/{incidents,inspections,inspection_prep,capa}/*`, `backend/app/domains/incidents/*`, `backend/app/api/routes/{incidents,inspections,prescriptions,findings...}` | `frontend/src/pages/{incidents,inspections,inspection-prep,prescriptions,findings,corrective-actions}/*` | `tests/api/test_incidents_api.py`, `backend/tests/test_incidents_access_parity.py` |
| `A.3.5` / `vNext §6.5` Пакеты документов | MVP | `backend/app/modules/packs/*`, `backend/app/domains/packs/*`, `backend/app/api/routes/packs.py` | `frontend/src/pages/packs/*` | `tests/test_package_pipeline.py`, `tests/integration/test_packages_e2e.py` |
| `vNext §9` Медосмотры | vNext (partial) | `backend/app/api/routes/medical.py` | `frontend/src/pages/medical/*` | tests TBD |
| `vNext §10` СОУТ | vNext (partial) | `backend/app/api/routes/risk.py` (связь) | `frontend/src/pages/risk/*` | tests TBD |
| `vNext §15` Подрядчики, посетители, допуск | vNext | `backend/app/modules/contractors/*`, `backend/app/api/routes/{contractors,access,client_portal,portal_requests,integration_readiness}.py`, `backend/app/modules/client_portal/*` | `frontend/src/pages/{contractors,client-portal,access,portal-requests}/*` | tests TBD |
| `vNext §16` Наряды-допуски | vNext (`[v1.2]`) | планируется | планируется | планируется |
| `vNext §17` Equipment / транспорт / электробезопасность | vNext (`[v1.2]`) | `backend/app/api/routes/items.py` (частично) | `frontend/src/pages/{reference,activities}/*` | tests TBD |
| `vNext §18` Комитеты, заседания | vNext | планируется (workflow + approvals base) | `frontend/src/pages/workflow/*` | планируется |
| `vNext §19` НПА, obligations, compliance | vNext (partial) | `backend/app/modules/compliance_deadlines/*`, `backend/app/api/routes/{npa,compliance,obligations}.py` | `frontend/src/pages/npa/*` | tests TBD |
| `vNext §20` Вертикали (ПБ / ПромБез / Экология / ГО-ЧС) | vNext (`[v1.2]`/`[v2.0]`) | `backend/app/api/routes/{fire-safety,fire-inspections,fire-training}.py` (только ПБ skeleton) | `frontend/src/pages/{fire-safety,fire-inspections,fire-training,audit-prep}/*` | tests TBD |
| `vNext §21` Терминалы / kiosk / биометрия | vNext (`[v2.0]`) | планируется | планируется | планируется |
| `vNext §22` Видеоналитика | vNext (`[v2.0]`) | планируется | планируется | планируется |
| `vNext §23` CRM / клиентский кабинет / sellability | vNext (`[v1.1]`) | `backend/app/api/routes/{billing,invoices,orders,contracts,client_portal}.py` | `frontend/src/pages/{crm-finance,client-portal,portal-requests}/*` | tests TBD |
| `vNext §24` Аналитика, отчёты, report builder | vNext (`[v1.1]`) | `backend/app/modules/{analytics,export_center,projections}/*`, `backend/app/api/routes/{reports,exports...}.py` | `frontend/src/pages/{analytics,reports,exports,dashboard}/*` | tests TBD |
| `vNext §25` Workflow, Rules, Smart Recommendations | vNext | `backend/app/modules/workflow/*`, `backend/app/api/routes/jobs.py` | `frontend/src/features/workflow/*`, `frontend/src/pages/workflow/*`, `frontend/src/pages/PipelineBuilderPage.tsx` | tests TBD |
| `vNext §26` AI Copilot | vNext (`[v2.0]`) | планируется | планируется | планируется |
| `vNext §27` Мобильная стратегия / PWA / offline | vNext (partial) | `backend/app/modules/pwa_sync/*`, `backend/app/api/routes/pwa_sync.py` | `frontend/src/pwa/*` | tests TBD |

## Frontend архитектура (vNext §29 / канон F1..F4)

| Раздел | Тег | Файлы |
|--------|-----|-------|
| `A.4.1` / F1 feature-based structure | MVP | `frontend/src/features/*`, `frontend/src/router/{features,pageRegistry,routeGroups}.tsx` |
| `A.4.2` / F2 обязательные экраны MVP | MVP | `frontend/src/pages/*`, `frontend/src/router/AppRouter.tsx`; инвентаризация — `docs/FRONTEND_SCREENS_INVENTORY.md` |
| `A.4.3` / F3 UX-компоненты | MVP | `frontend/src/components/*`, `frontend/src/permissions/*`, `frontend/src/__tests__/{Can,DataTable,JobTimeline,ApprovalTimeline,WizardJobTimeline}.test.tsx` |
| `A.4.4` / F4 frontend smoke | MVP | `frontend/e2e/{smoke,key-scenarios}.spec.ts`, `frontend/vitest.critical.config.ts` |

## Замечания

- В backend сосуществуют два слоя: канонический `backend/app/modules/*` (новый код, bounded contexts) и легаси `backend/app/domains/*` (старый, постепенно поглощается модулями). См. `docs/MODULES.md` и `docs/audit/REPOSITORY_AUDIT.md` (раздел «Legacy / compatibility paths»).
- `frontend/src/features/*` (feature-slices) и `frontend/src/pages/*` (route-уровневые страницы) сосуществуют по соглашению Feature-Sliced Design.
- Поле «Тег» в этой таблице соответствует MVP / vNext-фазе из `TZ_FULL_UNIFIED.md`. Для машинно-проверяемого статуса (`done/partial/missing`) используйте `docs/audit/TZ_COVERAGE_MATRIX.md`.
