# RBAC-сверка роутеров route-групп — аудит 2026-07-12

> **Тип:** read-only security audit (без изменений кода). **Метод:** мульти-агентный Workflow (`wf_10f85ae9-671`) — по одному ридеру-аудитору на каждый из 74 роутер-модулей, зарегистрированных в [`route_groups.py`](../../backend/app/api/v1/route_groups.py), затем адверсариальная верификация каждой заявленной дыры (скептик пытался опровергнуть — искал гард в роутере, include-зависимостях, кастомных хелперах и сервисном слое). 92 агента, 0 ошибок.

Продолжение точечного фикса `/analytics` + `/exports` (`commit 618614d9`, ветка `fix/analytics-exports-rbac`): сверка 2026-07-10 нашла те два модуля; эта сверка проверила **всю** поверхность.

## TL;DR

- **118 подтверждённых дефектов авторизации** в **18 из 74 роутер-модулей** (адверсариальная верификация: 0 переживших false-positive — каждый трейснут по всей цепочке гардов).
- Это **не** локальная оплошность в 2 модулях, а **системная**: целые группы (`document_core` пайплайны/паки/replace/workflow, внутренний client-portal, public_api) защищены только tenant-scoping.
- **Две первопричины** (см. ниже) объясняют почти все находки — фикс шаблонный, но объём большой.
- **Самое страшное — не role-less, а auth-less:** `search /reindex` и `tenants` листинги достижимы **без токена вообще** (только tenant-slug).

### Разбивка по тирам (по типу фикса)

| Тир | Что это | Эндпоинтов | Модули |
|-----|---------|-----------:|--------|
| 🔴 T1 — нет аутентификации (auth bypass) | | 5 | search, tenants |
| 🔴 T1w — inbound webhooks без подписи | | 2 | approval_orchestration |
| 🔴 T2 — минтинг креденшелов / priv-esc / публикация | | 7 | client_portal(routes), public_api |
| 🟠 T3 — незащищённые config/write (RBAC-шаблон) | | 95 | approval_signing_v1, branding, client_portal(routes), compliance, files(v1), notifications, npa, packs(v2), pipelines, replace, workflow |
| 🟡 T4 — self-scoped вьюхи (data-scoping, не 403) | | 9 | pwa_sync, search, tenancy, workspace |
| **ИТОГО** | | **118** | **18 модулей** |

## Первопричины (два анти-паттерна)

Групповой роутер строится как `create_tenant_router() = APIRouter(dependencies=[Depends(require_tenant_slug)])` ([route_groups.py:212](../../backend/app/api/v1/route_groups.py)). Это создаёт **ложную уверенность**: выглядит как «защита на всю группу», но `require_tenant_slug` проверяет только *наличие валидного тенанта*, не *роль пользователя*.

**Анти-паттерн A — только `get_session` + `get_tenant_record`.** Пара зависимостей резолвит тенант и сессию, но не проверяет ни токен-роль, ни владение. Эндпоинт защищён исключительно tenant-scoping (`record.tenant_id == tenant.id` — это изоляция тенантов, НЕ RBAC). Затрагивает packs/pipelines/replace/branding/public_api/client_portal и др.

**Анти-паттерн B — `Depends(rbac())` БЕЗ `required_roles`.** Выглядит как ролевой гард, но в [`security.py:463-543`](../../backend/app/core/security.py) при пустом наборе ролей роль-гейт `if normalized_roles and not role_candidates.intersection(...)` (стр. 540) **пропускается целиком**. `rbac()` без аргументов = только аутентификация + tenant/company-scope, **ноль ролевой проверки**. Затрагивает notifications/workspace/pwa_sync/tenancy/search/npa/compliance/workflow.

**Под-класс — auth bypass.** Хуже обоих: `search /reindex` использует только `get_session`+`get_tenant_record` и **не читает bearer-токен вообще** (глобального auth-middleware нет — [`app.py`](../../backend/app/api/app.py) регистрирует только error/TrustedHost/CORS/Tenant/Billing/SlowAPI/Observability). `tenants` использует `HTTPBearer(auto_error=False)` + ролевую проверку внутри `if credentials:` → анонимный вызов с одним tenant-slug её обходит. Итог — **неаутентифицированный** доступ.

## План устранения по тирам

### TIER 1 — MISSING AUTHENTICATION (auth bypass)

Reachable by an **unauthenticated** caller who supplies only the tenant-slug header. Fix = require a valid access token **first**, then an admin-grade role. These are the most severe: not merely role-less, but auth-less.

| Модуль | Эндпоинт | Sens | Контроль |
|--------|----------|:----:|----------|
| search | `POST /search/reindex` | HIGH | 🔴 Требовать токен + admin-роль |
| search | `POST /search/reindex/{entity_type}` | HIGH | 🔴 Требовать токен + admin-роль |
| tenants | `GET /tenants` | HIGH | 🔴 Требовать токен + admin-роль |
| tenants | `GET /admin/tenants` | HIGH | 🔴 Требовать токен + admin-роль |
| tenants | `GET /tenants/me` | MEDIUM | 🔴 Требовать токен + admin-роль |

### TIER 1w — INBOUND WEBHOOKS WITHOUT SIGNATURE

External machine callers (EDO/signature providers). RBAC roles do **not** apply — the correct control is **HMAC/shared-secret signature verification** of the payload, plus a per-request nonce/id binding. Currently guarded by tenant-scope only, so anyone who knows the tenant slug + a request id can flip signing/EDO state.

| Модуль | Эндпоинт | Sens | Контроль |
|--------|----------|:----:|----------|
| approval_orchestration | `POST /webhooks/edo/{operator_code}` | HIGH | 🔴 HMAC/подпись вебхука |
| approval_orchestration | `POST /webhooks/sign/{provider_code}` | HIGH | 🔴 HMAC/подпись вебхука |

### TIER 2 — CREDENTIAL MINTING / PRIVILEGE ESCALATION / PUBLISHING

Authenticated but role-less operations that mint credentials, return plaintext secrets, issue external access links, or publish tenant content. Any tenant role (incl. `worker`) can perform them. Fix = **strict least-privilege RBAC (owner/admin, HSE-lead at most)**. Highest priority among authenticated gaps.

| Модуль | Эндпоинт | Sens | Контроль |
|--------|----------|:----:|----------|
| client_portal(routes) | `POST /packages/runs/{run_id}/portal-link` | HIGH | 🔴 Строгий RBAC (owner/admin) |
| public_api | `GET /machine-keys` | HIGH | 🔴 Строгий RBAC (owner/admin) |
| public_api | `POST /machine-keys` | HIGH | 🔴 Строгий RBAC (owner/admin) |
| public_api | `POST /machine-keys/{item_id}/revoke` | HIGH | 🔴 Строгий RBAC (owner/admin) |
| public_api | `POST /machine-keys/{item_id}/rotate` | HIGH | 🔴 Строгий RBAC (owner/admin) |
| public_api | `POST /marketplace` | HIGH | 🔴 Строгий RBAC (owner/admin) |
| public_api | `POST /marketplace/{item_id}/install` | MEDIUM | 🔴 Строгий RBAC (owner/admin) |

### TIER 3 — UNGUARDED CONFIG & WRITE SURFACES

The bulk. Sensitive domain config/exec endpoints (pipelines, packs, replace, workflow, approval routing, branding, etc.) protected only by tenant-scope. Fix = the shipped **analytics/exports `abac()` read/write pattern** (`commit 618614d9`): read = management/specialist set, write = admin/owner/HSE-lead.

| Модуль | Эндпоинт | Sens | Контроль |
|--------|----------|:----:|----------|
| approval_signing_v1 | `POST /v1/approvals/processes/{process_id}:cancel` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| approval_signing_v1 | `GET /v1/approvals/routes` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| approval_signing_v1 | `POST /v1/approvals/routes` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| approval_signing_v1 | `PATCH /v1/approvals/routes/{route_id}` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| approval_signing_v1 | `POST /v1/webhooks` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| approval_signing_v1 | `POST /v1/approvals:start` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| approval_signing_v1 | `GET /v1/approvals/processes` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| approval_signing_v1 | `GET /v1/approvals/processes/{process_id}` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| approval_signing_v1 | `GET /v1/approvals/process-tasks` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| approval_signing_v1 | `POST /v1/sign:request` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| approval_signing_v1 | `GET /v1/sign/requests` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| approval_signing_v1 | `GET /v1/sign/requests/{request_id}` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| approval_signing_v1 | `POST /v1/approvals/start` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| approval_signing_v1 | `GET /v1/approvals/instances` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| approval_signing_v1 | `GET /v1/approvals/tasks` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| approval_signing_v1 | `POST /v1/sign/request` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| approval_signing_v1 | `POST /v1/sign/submit` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| approval_signing_v1 | `GET /v1/sign/status` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| approval_signing_v1 | `GET /v1/webhooks` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| approval_signing_v1 | `PATCH /v1/webhooks/{webhook_id}/disable` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| branding | `GET /branding/profile` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| branding | `PATCH /branding/profile/{company_id}` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| branding | `GET /branding/history` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| branding | `POST /branding/preview` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| client_portal(routes) | `POST /presets/packages` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| client_portal(routes) | `PATCH /presets/packages/{preset_id}` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| client_portal(routes) | `POST /packages/runs` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| client_portal(routes) | `GET /presets/packages` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| client_portal(routes) | `GET /packages/runs` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| client_portal(routes) | `GET /packages/runs/{run_id}` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| compliance | `POST /compliance/deadlines/recompute` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| compliance | `GET /compliance/persons/{person_id}/summary` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| files(v1) | `POST /files/{file_id}:reindex` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| notifications | `POST /notifications/templates` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| npa | `POST /npa/{act_id}/impact/tasks` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| packs(v2) | `POST /package-profiles` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| packs(v2) | `PATCH /package-profiles/{profile_id}` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| packs(v2) | `DELETE /package-profiles/{profile_id}` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| packs(v2) | `POST /package-presets` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| packs(v2) | `PATCH /package-presets/{preset_id}` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| packs(v2) | `DELETE /package-presets/{preset_id}` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| packs(v2) | `POST /package-presets/{preset_id}:upload-source` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| packs(v2) | `POST /package-presets/{preset_id}:preview-mapping` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| packs(v2) | `POST /pack-runs` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| packs(v2) | `POST /pack-runs/{run_id}:cancel` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| packs(v2) | `POST /pack-runs/{run_id}:retry-failed` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| packs(v2) | `GET /pack-runs/{run_id}/download` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| packs(v2) | `GET /package-profiles` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| packs(v2) | `GET /package-profiles/{profile_id}` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| packs(v2) | `GET /package-presets` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| packs(v2) | `GET /package-presets/{preset_id}` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| packs(v2) | `POST /package-presets/{preset_id}/items` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| packs(v2) | `PATCH /package-presets/{preset_id}/items/{item_id}` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| packs(v2) | `DELETE /package-presets/{preset_id}/items/{item_id}` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| packs(v2) | `POST /package-presets/{preset_id}:validate` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| packs(v2) | `GET /pack-runs` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| packs(v2) | `GET /pack-runs/{run_id}` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| packs(v2) | `GET /pack-runs/{run_id}/items` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| packs(v2) | `GET /pack-runs/{run_id}/timeline` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| pipelines | `POST /pipelines/profiles` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| pipelines | `PATCH /pipelines/profiles/{profile_id}` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| pipelines | `PUT /pipelines/profiles/{profile_id}` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| pipelines | `POST /pipelines/profiles/{profile_id}:activate` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| pipelines | `DELETE /pipelines/profiles/{profile_id}` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| pipelines | `POST /pipelines/runs` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| pipelines | `POST /pipelines/run` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| pipelines | `GET /pipelines/runs` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| pipelines | `POST /pipelines/runs:bulk` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| pipelines | `POST /pipelines/runs/{run_id}:cancel` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| pipelines | `POST /pipelines/runs/{run_id}:retry` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| pipelines | `POST /pipelines/runs/{run_id}/steps/{step_run_id}:retry` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| pipelines | `GET /pipelines/profiles` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| pipelines | `GET /pipelines/profiles/{profile_id}` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| pipelines | `GET /pipelines/runs/{run_id}` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| pipelines | `GET /pipelines/runs/{run_id}/events` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| replace | `POST /replace-maps` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| replace | `PATCH /replace-maps/{replace_map_id}` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| replace | `DELETE /replace-maps/{replace_map_id}` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| replace | `POST /documents/{document_version_id}/replace:apply` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| replace | `POST /replace-runs/{replace_run_id}/rollback` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| replace | `GET /replace-maps` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| replace | `GET /replace-maps/{replace_map_id}` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| replace | `POST /documents/{document_version_id}/replace:dry-run` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| replace | `GET /replace-runs/{replace_run_id}` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| replace | `GET /replace-runs/{replace_run_id}/report` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| replace | `GET /replace-runs/{replace_run_id}/report.csv` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| workflow | `POST /workflow/definitions` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| workflow | `GET /workflow/definitions` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| workflow | `POST /workflow/versions/{version_id}/publish` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| workflow | `POST /workflow/versions/{version_id}/archive` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| workflow | `GET /workflow/definitions/{definition_id}` | HIGH | 🟠 abac() read/write (шаблон analytics/exports) |
| workflow | `POST /workflow/instances` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| workflow | `GET /workflow/instances` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| workflow | `GET /workflow/instances/{instance_id}` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |
| workflow | `GET /workflow/tasks` | MEDIUM | 🟠 abac() read/write (шаблон analytics/exports) |

### TIER 4 — SELF-SCOPED / APP-CRITICAL VIEWS (data-scoping, not a blanket gate)

Real over-exposure, BUT a blanket 403 would break the PWA or user dashboards (every logged-in user legitimately calls these). Fix = **per-role data-scoping / result filtering**, not an all-or-nothing role gate. **Verify each against product intent before gating** — some (e.g. `/tenancy/context`) may be acceptable as-is.

| Модуль | Эндпоинт | Sens | Контроль |
|--------|----------|:----:|----------|
| pwa_sync | `GET /pwa/bootstrap` | HIGH | 🟡 Data-scoping по роли (проверить намерение) |
| pwa_sync | `POST /pwa/sync/batch` | MEDIUM | 🟡 Data-scoping по роли (проверить намерение) |
| pwa_sync | `POST /pwa/media/commit` | MEDIUM | 🟡 Data-scoping по роли (проверить намерение) |
| search | `GET /search` | HIGH | 🟡 Data-scoping по роли (проверить намерение) |
| search | `GET /search/suggest` | HIGH | 🟡 Data-scoping по роли (проверить намерение) |
| tenancy | `GET /tenancy/context` | HIGH | 🟡 Data-scoping по роли (проверить намерение) |
| workspace | `GET /workspace/attention` | MEDIUM | 🟡 Data-scoping по роли (проверить намерение) |
| workspace | `GET /workspace/task-inbox` | MEDIUM | 🟡 Data-scoping по роли (проверить намерение) |
| workspace | `GET /workspace/role-summary` | MEDIUM | 🟡 Data-scoping по роли (проверить намерение) |

## Приложение — детали и rationale по модулям

Для каждого модуля: заметка верификатора (усечена) и предложенные роли (уже подобраны аудиторами по least-privilege, зеркалируя `abac()`-фикс analytics/exports). Полные rationale — в `journal.jsonl` рана `wf_10f85ae9-671`.

### packs(v2) — 24 дыр (12 high) · тир C3

**Верификатор:** All 24 claims CONFIRMED as genuine RBAC gaps. Verification chain: (1) Router constructor backend/app/modules/packs/api.py:46 = APIRouter(tags=["packs-v2"]) — no dependencies. (2) Mount point route_groups.py:181 includes packs_v2_api.router with kwargs {} — no include-level dependencies; parent create_tenant_router (line 211-218) adds only Depends(require_tenant_slug) = tenant-scoping. (3) Dependencies get_tenant_record (dependencies.py:158) and get_session (:213) are [...]

**Предложенные роли:** write: OWNER, ADMIN, OT_PB_LEAD

### approval_signing_v1 — 20 дыр (5 high) · тир C3

**Верификатор:** Adversarial re-verification complete: all 20 claimed gaps CONFIRMED, zero false positives. Refutation attempts and what I found: (1) Router constructor — backend/app/api/routes/approval_signing_v1.py:34 is `router = APIRouter()` with NO dependencies. (2) Mount point — backend/app/api/v1/route_groups.py:172 registers it with only {"prefix":"/v1","tags":[...]}, and _include_registrations (line 229) passes no dependencies; the parent create_tenant_router (line 212) has [...]

**Предложенные роли:** write(start): OWNER, ADMIN, OT_PB_LEAD, OT_HEAD, OT_SPECIALIST, LINE_MANAGER, MANAGER — via Depends(rbac([...])) mirroring the analytics/exports fix

### pipelines — 16 дыр (12 high) · тир C3

**Верификатор:** All 16 claims CONFIRMED; zero false positives. Verified four layers: (1) per-endpoint deps in backend/app/modules/pipelines/api.py are exclusively Depends(get_session)+Depends(get_tenant_record); (2) router registered at route_groups.py:178 with empty kwargs {} — no include-level dependencies; (3) tenant router adds only Depends(require_tenant_slug) at route_groups.py:212 (tenant-scoping, not RBAC), and get_tenant_record in api/dependencies.py is pure tenant resolution [...]

**Предложенные роли:** write via abac(_tenant_resource_id, required_roles=['admin','owner','ot_specialist'], action='manage pipelines'), mirroring _EXPORT_WRITE_ROLES

### replace — 11 дыр (5 high) · тир C3

**Верификатор:** All 11 claimed gaps CONFIRMED. I tried to refute each by checking: (1) router mount — replace_api.router is included with empty kwargs {} at route_groups.py:175, so no include-level dependencies; (2) parent tenant router (create_tenant_router, route_groups.py:211-218) carries only Depends(require_tenant_slug) which is pure tenant-scoping; (3) route deps get_session + get_tenant_record (dependencies.py) resolve/scope tenant only, no user/role; (4) notably NO current_user [...]

**Предложенные роли:** write: abac(tenant.id, required_roles=[admin, owner, ot_specialist], action='create replace map') mirroring exports write set

### workflow — 9 дыр (5 high) · тир C3

**Верификатор:** Adversarial re-verification complete. Checked: (1) rbac() in app/core/security.py — with no required_roles, normalized_roles is empty, so the role gate at line 540 is skipped; Depends(rbac()) enforces auth + tenant-id/slug consistency ONLY, no role/ownership. (2) Router constructor api.py:18 `APIRouter(prefix="/workflow", tags=["workflow"])` — no dependencies=[...]. (3) Mount route_groups.py:179 `(workflow_router, {})` — no include-level deps; parent [...]

**Предложенные роли:** WRITE: rbac(["owner","admin","ot_pb_lead"]) — workflow/process configuration is admin-grade tenant config.

### client_portal(routes) — 7 дыр (4 high) · тир C2, C3

**Верификатор:** All 7 claims CONFIRMED as genuine RBAC gaps after adversarial re-check of the full chain. Verified: (1) presets_router/internal_router constructors (client_portal.py:36-37) declare NO dependencies=; (2) route_groups.py:141-142 include them with empty {} kwargs (no include-level deps); (3) create_tenant_router (route_groups.py:212) applies only Depends(require_tenant_slug) which dependencies.py:204-205 shows is pure tenant-scoping; (4) get_session/get_tenant_record [...]

**Предложенные роли:** Read-only guard mirroring analytics abac pattern: abac(_tenant_resource_id, required_roles=['admin','owner','ot_pb_lead','ot_head','ot_specialist','pb_engineer','manager','line_manager','auditor_ro'], action='read package presets')

### public_api — 6 дыр (5 high) · тир C2

**Верификатор:** Adversarially re-checked all listed guard surfaces and found NO authz beyond tenant-scoping for any of the 6 endpoints. Verified: (1) admin_router (public_api.py:33) and marketplace_router (line 34) are plain APIRouters with NO dependencies= in their constructors; (2) both are included in route_groups.py:189-190 with empty options {} (no include-level dependencies); (3) the enclosing tenant router adds only Depends(require_tenant_slug) (route_groups.py:212) = tenant- [...]

**Предложенные роли:** read: OWNER, ADMIN (credential admin surface) via Depends(rbac([RoleEnum.OWNER, RoleEnum.ADMIN]))

### branding — 4 дыр (2 high) · тир C3

**Верификатор:** All four claimed gaps CONFIRMED after adversarial refutation attempt. Checked: (1) route-level deps in backend/app/modules/branding/api.py — every endpoint has only Depends(get_session)+Depends(get_tenant_record); (2) router constructor api.py:19 APIRouter(prefix=\"/branding\") declares NO dependencies; (3) include-level registration route_groups.py:177 (branding_router, {}) passes no dependencies; (4) parent create_tenant_router route_groups.py:212 adds only [...]

**Предложенные роли:** read (mirror analytics-read least-privilege): abac(_tenant_resource_id, required_roles=["admin","owner","ot_pb_lead","ot_head","ot_specialist","pb_engineer","manager","line_manager","clerk"], action="read branding") as a router-level or per-route Depends. RoleEnum values confirmed in models/tenant_billing.py:42-68.

### search — 4 дыр (4 high) · тир C1, C4

**Верификатор:** All four claims CONFIRMED after adversarial refutation. Reviewed: rbac()/_normalize_roles (security.py:459-582) — empty required_roles makes the sole role gate at line 540 unreachable, so rbac() with no args is authN-only; router construction/mounting (route_groups.py:182,205-231) — no include-level or tenant-router RBAC, only require_tenant_slug (tenant-scoping); tenant/session dependencies (dependencies.py:158-232) — pure tenant resolution, no bearer check; middleware [...]

**Предложенные роли:** read = management/specialist set mirroring the analytics/exports fix: owner, admin, ot_head, ot_pb_lead, ot_specialist, pb_engineer, ecologist, hr, lawyer, accountant, line_manager, manager, auditor_ro. Apply via rbac([...]) (or abac over tenant.id as resource). Exclude worker/employee/student/client_user. [...]

### pwa_sync — 3 дыр (1 high) · тир C4

**Верификатор:** All three claims CONFIRMED after adversarial refutation. Root cause: rbac() invoked with no required_roles across every /pwa endpoint (create_batch:379, commit_media:430, bootstrap:513) — at app/core/security.py:463-543 an empty role list makes the line-540 role gate a no-op, leaving only authn + tenant/company-slug scoping. Verified the router constructor (pwa_sync.py:31 `APIRouter(prefix=\"/pwa\", tags=[\"pwa\"])`) has NO router-level dependencies=[...], and the [...]

**Предложенные роли:** WRITE — restrict to operational field roles that legitimately perform offline OT/PB capture, mirroring the analytics/exports abac() fix pattern (403 {code:FORBIDDEN} otherwise): [...]

### tenants — 3 дыр (2 high) · тир C1

**Верификатор:** All three claims CONFIRMED. Root cause is shared: _optional_bearer = HTTPBearer(auto_error=False) combined with role enforcement placed inside `if credentials:` (tenants.py:59), so an unauthenticated caller who supplies only the tenant slug header bypasses the intended ADMIN/CLIENT_ADMIN check. There is no global authentication middleware (app.py:72-88), and the router-level dependency (create_tenant_router, route_groups.py:212) is only require_tenant_slug — pure [...]

**Предложенные роли:** Read-only. Make the guard unconditional by adding Depends(abac(_tenant_resource_id, required_roles=_MANAGEMENT_ROLES, action="read")) exactly like GET /tenants/{tenant_id}, or call _require_admin(credentials) unconditionally. Least-privilege read roles: RoleEnum.ADMIN, RoleEnum.CLIENT_ADMIN (optionally OWNER, [...]

### workspace — 3 дыр (0 high) · тир C4

**Верификатор:** All three claimed gaps are CONFIRMED after adversarial refutation attempts. I specifically tried to find a guard at the router constructor (workspace.py:32 — plain APIRouter, no dependencies), the include/mount site (route_groups.py:151 — empty kwargs), the group router (route_groups.py:212 — require_tenant_slug is tenant-scope only, not RBAC), the rbac() dependency internals (security.py:463-544 — with required_roles=None the role check at line 540 is short-circuited), [...]

**Предложенные роли:** Mirror analytics/exports fix: replace rbac() with Depends(rbac(["owner","admin","ot_head","ot_pb_lead","ot_specialist","pb_engineer","ecologist","hr","line_manager","manager"])). If the personal self-scoped task view must stay available to worker/client_user, split the response: keep the self-scoped task list [...]

### approval_orchestration — 2 дыр (2 high) · тир C1w

**Верификатор:** Both claimed gaps CONFIRMED after adversarial re-check. I actively tried to refute via (a) router-constructor guard — none: APIRouter() line 39; (b) include-level dependency — none: route_groups.py:173 registers with only tags, and the enclosing create_tenant_router adds only require_tenant_slug (line 212); (c) session/tenant deps implying user auth — none: get_tenant_record/get_session (dependencies.py:158-237) are pure tenant resolution; (d) service-layer authz — [...]

**Предложенные роли:** Correct primary guard for an external webhook is provider HMAC/signature verification (add per-operator secret + constant-time signature compare before ingest) — RBAC roles do not fit a machine caller. If parity with the file's other writes is desired as an interim guard, add EditorAccess = [...]

### compliance — 2 дыр (2 high) · тир C3

**Верификатор:** Adversarial re-check complete: read the route file, the rbac() implementation end-to-end (core/security.py:463-572), the ComplianceDeadlineService, and the router registration (route_groups.py:102-136). rbac() with no arguments authenticates the bearer token and enforces token↔user tenant/company consistency but does NOT enforce any role — the role check at line 540 is guarded by `if normalized_roles and ...` and normalized_roles is empty. No router-level dependencies, [...]

**Предложенные роли:** WRITE (bulk mutation) — restrict to rbac(['owner','admin','ot_pb_lead','ot_specialist']); mirror the analytics/exports management-op pattern (admin/HSE lead only).

### files(v1) — 1 дыр (0 high) · тир C3

**Верификатор:** Single claimed gap CONFIRMED. The reindex endpoint is verifiably the only handler in files/api.py that omits the abac(_tenant_resource_id, required_roles=...) guard that all 25 other sibling endpoint dependency sites carry. Fix is trivial and low-risk: add WRITE_ACCESS_DEP + _enforce_access_role(access, _FILE_UPLOAD_ROLES), consistent with delete/complete/upload handlers.

**Предложенные роли:** Mirror the sibling write pattern: add `access: AccessContext = WRITE_ACCESS_DEP` param and call `_enforce_access_role(access, _FILE_UPLOAD_ROLES)` at the top of the handler, restricting to RoleEnum admin + employee (write roles). No read-only role should trigger reindex.

### notifications — 1 дыр (1 high) · тир C3

**Верификатор:** Verified against the actual code, not memory. rbac() is a real auth+tenant-scope guard but provides ZERO role enforcement when invoked with no arguments (security.py:540 gate is conditional on normalized_roles being non-empty). No router-level dependency, no service-layer role/ownership check (service.py:286-318 scopes only by tenant_id). audit_operation logs but does not authorize. The claimed gap is CONFIRMED for the WRITE endpoint POST /notifications/templates. Note: [...]

**Предложенные роли:** Mirror the analytics/exports fix (commit 618614d9, write=admin/owner/ot_specialist). This is tenant-wide config mutation, so least-privilege WRITE should be config-admin roles only: rbac([RoleEnum.OWNER, RoleEnum.ADMIN, RoleEnum.OT_PB_LEAD, RoleEnum.OT_HEAD]) — i.e. owner/admin/ot_pb_lead/ot_head. Minimal safe [...]

### npa — 1 дыр (1 high) · тир C3

**Верификатор:** Adversarial re-check done. I attempted to refute by tracing rbac() end-to-end and opening the service method. rbac() with empty role list provably skips the role 403 (security.py:540) — auth + tenant/company-scoping only. NpaImpactService.create_update_tasks enforces no role/ownership (created_by is just the assignee). No router-level dependencies (router = APIRouter(tags=['npa']) at line 21, no dependencies=[...]); the tenant slug guard lives on the parent include and [...]

**Предложенные роли:** Add role restriction mirroring the analytics/exports fix, e.g. access=Depends(rbac([RoleEnum.OWNER, RoleEnum.ADMIN, RoleEnum.OT_PB_LEAD, RoleEnum.OT_HEAD, RoleEnum.OT_SPECIALIST, RoleEnum.LAWYER])) -> passing string values ['owner','admin','ot_pb_lead','ot_head','ot_specialist','lawyer']. Write action, so limit [...]

### tenancy — 1 дыр (1 high) · тир C4

**Верификатор:** Adversarial verification complete. I attempted to refute the single claimed gap by re-reading the route, the router constructor, both tenant dependencies (get_tenant_record, get_session), TenantContextValidator usage, and the full rbac()/_normalize_roles implementation. No authorization beyond authentication + tenant/company scoping exists on GET /tenancy/context. The auditor's chain (empty required_roles -> empty normalized_roles -> role gate at security.py:540 [...]

**Предложенные роли:** Read-only endpoint. Gate with owner-plus-admin read access mirroring the analytics/exports fix: rbac([RoleEnum.OWNER.value, RoleEnum.ADMIN.value]) (i.e. ["owner", "admin"]); optionally add CLIENT_ADMIN ("client_admin") if tenant self-service context is meant for client-portal admins. No write role needed (GET). [...]

## Координация и статус

- **`/analytics` + `/exports` уже пофикшены** (ветка `fix/analytics-exports-rbac`, `commit 618614d9`) — в этой сверке подтверждены как guarded (0 дыр), служат эталоном шаблона фикса.
- **Фоновая задача-реализатор** (`task_1000eebb`, запущена пользователем в отдельной сессии) фиксила исходный узкий список кандидатов (branding/packs/pipelines/replace). **Этот аудит — авторитетный суперсет**: реальный объём в ~9× больше. Рекомендуется переориентировать реализацию на этот worklist (тир за тиром, T1→T2→T3, T4 — после проверки намерения).
- **Особый статус `files(v1)`:** единственная дыра — `POST /files/{file_id}:reindex`, ровно один эндпоинт из 26, забывший `abac()`-гард, который несут все 25 соседних. Тривиальный consistency-фикс; показывает, что per-endpoint `abac()` там применён консистентно (в отличие от document_core-групп).

## Метод и оговорки

- **0 false-positive** означает: верификатор фактически подтвердил «только tenant-scoping» по каждой находке (трейс по роутеру/include/сервису). Суждение «это уязвимость vs намеренно» и *какой* контроль лечит — добавлено в тир-классификации данного отчёта, не самим верификатором.
- **Тир 4 требует продуктовой проверки перед гейтом:** self-scoped вьюхи (`/pwa/*`, `/workspace/*`, `/tenancy/context`) вызывает каждый залогиненный пользователь; правильный фикс — фильтрация данных по роли, а не блокировка. `/tenancy/context`, возможно, приемлем как есть.
- **Тир 1 (auth bypass) стоит подтвердить точечным ручным прогоном** до фикса — это сильное утверждение (неаутентифицированный destructive reindex / листинг тенантов); верификатор трейснул отсутствие auth-middleware, но независимая проверка курлом закрепит severity.

---
_Сгенерировано из рана `wf_10f85ae9-671` (74 модуля, 92 агента, 4.9M токенов). Дата: 2026-07-12._
