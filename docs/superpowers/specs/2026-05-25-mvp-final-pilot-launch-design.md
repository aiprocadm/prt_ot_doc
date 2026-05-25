# MVP Final Closure → Friendly Pilot Launch (Design)

- **Date:** 2026-05-25
- **Author:** Brainstorm session (Claude Opus 4.7 + product owner)
- **Status:** Approved for plan
- **Branch context:** session started on `fix/iter-16f-cross-base-fk-schema-and-authz-seed`
- **Approach selected:** A — Maximum closure (full RB + 142 backend-tests green before pilot)
- **Pilot target:** 1–2 friendly clients, managed hosting (own server или Timeweb VPS)

## 1. Scope & Definition of Done

### In scope

- Release blockers RB-001..006 all `done` per `docs/stabilization/RELEASE_BLOCKERS_STATUS.md`.
- ~142 backend-test fails (per Session 65 handoff) reduced to 0.
- Frontend label drift (`ClientPortalHistoryAndRequests` + любые cousin'ы класса `/no-access`) green.
- `make final-acceptance`: `overall_status=pass`.
- Tag `v1.0-RC1` on `main`.
- Managed production stack: `docker-compose.prod.yml` + Caddy (TLS) + Prometheus/Grafana/Loki + автоматический backup в Timeweb S3.
- On-call lite: Prometheus → Telegram-бот.
- Юр.пакет для пилота: 7 документов + Роскомнадзор-уведомление.
- Pilot onboarding playbook (12-шаговый чеклист).

### Out of scope (defer)

- RC-011 Notifications escalation polishing → v1.1.
- RC-012 Формальные RTO/RPO go/no-go подписи → v1.1 (restore-drill работает, но без подписанных метрик).
- RC-013 Scope model migration в relational → v1.x.
- RC-014 Branch entity separate from Site → v1.x.
- Полноценный публичный сайт / self-serve sign-up → закрытая бета.
- Биллинг integration → закрытая бета (manual invoicing для friendly).
- Полноценный DPA по 152-ФЗ → закрытая бета (DPA-lite для friendly + явный disclaimer).
- ISO 27001 / SOC 2 → public GA.

### Definition of Done — «MVP green»

1. `RELEASE_BLOCKERS_STATUS.md` 6/6 blockers `done`.
2. `make final-acceptance` artifact: `overall_status=pass`.
3. Backend-tests + frontend-tests + e2e-smoke: green на main commit.
4. Coverage gate green vs baseline (RB-006 не регрессируем).
5. `RELEASE_READINESS.md` + 4 синхронизированных дока обновлены, вердикт `READY`.
6. Tag `v1.0-RC1` создан.

### Definition of Done — «Pilot launchable»

7. Managed stack развёрнут на staging-VPS, smoke-test проходит из браузера.
8. Backup автоматически уезжает в off-site (Timeweb S3); restore-drill зелёный на staging данных.
9. Pilot contract template подписан минимум одним клиентом.
10. Onboarding playbook прогнан dry-run на staging-tenant без ошибок.
11. РКН-уведомление подано (даже если ещё не зарегистрировано).

## 2. Architecture — Work Streams

| WS | Тема | Что чинит | Артефакт «done» |
|---|---|---|---|
| WS1 | iter-16f closure (текущая ветка) | cross-base FK schema + tenant-scoped authz seed | PR merged, tenant-isolation тесты green |
| WS2 | Backend app drift sweep (iter-17..N) | 142 backend-test fails по 7 классам | каждый класс — отдельный iter с pin-test |
| WS3 | RB closure + final-acceptance | RB-002 perf verify, RB-003 final-acceptance bundle, sync 5 doc'ов | RB 6/6 done, tag `v1.0-RC1` |
| WS4 | Managed deployment stack | docker-compose.prod, Prometheus/Grafana/Loki, backup automation, secrets | staging работает end-to-end |
| WS5 | Pilot prep | ToS/DPA/SLA templates, onboarding playbook, support channel, РКН | pilot готов к contract sign |

### DAG зависимостей

```
WS1 (iter-16f) ──┐
                 ├──► WS2 (backend drift sweep) ──┐
                 │                                  ├──► WS3 (RB closure + tag) ──► WS5 (pilot launch)
                 └──► WS4 (managed deploy) ────────┘                                  ▲
                                                                                       │
                                                   WS5 prep (legal/docs) ──────────────┘
```

### Точки синхронизации

- `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` — только WS3 трогает (single source of truth).
- `RELEASE_READINESS.md` + 4 synced docs (`ACCEPTANCE_TEST_MATRIX.md`, `KNOWN_LIMITATIONS.md`, `GAP_REPORT.md`, `docs/stabilization/PLAN.md`) — обновляются WS3 в конце.
- `AI_IMPLEMENTATION_REPORT.md` handoff entries — каждая итерация добавляет сверху.

### Стратегия итераций (унаследована от iter-13..15h)

- Один класс ошибок = один `iter-NN-<topic>` branch = один PR.
- Pin-test против рецидива (по примеру `test_migrations_comprehensive_safety.py`).
- Handoff entry в `AI_IMPLEMENTATION_REPORT.md` после каждой сессии.
- CI must be green на main перед открытием следующего iter.

## 3. App Drift Triage Matrix (WS2)

| Класс | ~Кол-во fails | Где | Гипотеза природы | Итерация | Pin-test |
|---|---|---|---|---|---|
| C1: RBAC pattern mismatch | ~50 | tests / API error codes | `module_access_denied` vs `missing_permission` контракт сдвинулся | iter-17a (батчи) | `test_rbac_error_contract.py` |
| C2: Missing domain modules | ~10 | `app.domains.{audit,workflows,integrations,notifications}` | Refactor delete vs TODO — нужен decision | iter-17b (decision + fix/delete) | `test_domain_module_imports.py` |
| C3: Workspace role config 404s | ~7 | API workspace endpoints | Routes удалены или config slot пустой | iter-17c | `test_workspace_role_routes.py` |
| C4: Healthcheck FrozenInstanceError + missing webhook_notification_url | ~8 | tests/test_health*.py | Pydantic v1→v2 frozen-dataclass change или required field удалено | iter-17d | `test_health_check_contract.py` |
| C5: Staging hardening "DID NOT RAISE" | ~4 | tests / staging guards | Защитный код перестал падать или conftest не выставляет env=staging | iter-17e | `test_staging_guards.py` |
| C6: DocumentTemplate ImportError | 1 | один тест | Переезд импорта | iter-17f (inline) | inline |
| C7: Frontend label drift | 1 | frontend/... | Cousin /no-access; перевод селекторов на `data-testid` | iter-17g | `data-testid` sweep |

**Sequencing внутри WS2:**
1. C6 + C7 (10 мин каждый — quick wins).
2. C2 scoping (decision doc git log → fix/delete strategy).
3. C5 staging.
4. C4 healthcheck.
5. C3 workspace.
6. C1 RBAC (большой; последним).

**Итого WS2:** 7–9 PRs + WS1 iter-16f = 8–10 PRs до backend-tests green.

**Strict policy для C2:** Если scope восстановления модуля > 80% от полного фича-build'а — удалить тесты + добавить запись в `KNOWN_LIMITATIONS.md`, фичу в v1.1. Не дать unbounded scope разрушить timeline.

## 4. Managed Deployment Stack (WS4)

### Топология

```
[VPS Timeweb или own-server — Ubuntu 22.04, 4 vCPU / 8 GB RAM minimum]
   │
   ├─ docker-compose (prod profile):
   │    ├─ backend (FastAPI + uvicorn + gunicorn workers)
   │    ├─ frontend (статика через nginx)
   │    ├─ postgres (data volume на отдельном диске)
   │    ├─ minio (S3 для file storage)
   │    ├─ redis (celery broker)
   │    ├─ celery-worker
   │    ├─ celery-beat (для backup cron)
   │    ├─ prometheus + grafana + loki + promtail (наблюдаемость)
   │    └─ caddy (reverse proxy + automatic TLS Let's Encrypt)
   │
   ├─ systemd unit: docker-compose-platform.service (auto-start, restart on fail)
   │
   ├─ cron / celery-beat:
   │    ├─ daily pg_dump → minio bucket `backups/`
   │    ├─ daily rsync `backups/` → Timeweb S3 (off-site, RU-юрисдикция)
   │    └─ weekly automated restore-drill (через `scripts/restore_drill.py`)
   │
   └─ secrets: `.env.prod` через ansible-vault (или sops), не в git
```

### Артефакты (создаём в репо)

| Артефакт | Путь |
|---|---|
| Compose prod profile | `docker-compose.prod.yml` |
| Reverse proxy / TLS | `caddy/Caddyfile` |
| Monitoring config | `monitoring/prometheus.yml`, `monitoring/grafana-dashboards/*.json` |
| Logs config | `monitoring/loki-config.yml`, `monitoring/promtail-config.yml` |
| Backup script | `scripts/ops/daily_backup.sh` |
| systemd unit | `systemd/docker-compose-platform.service` |
| Deploy runbook | `docs/ops/MANAGED_DEPLOY.md` |
| Incident runbook | `docs/ops/INCIDENT_RUNBOOK.md` |
| Alerts catalog | `docs/ops/ALERTS.md` |

### Prometheus → Telegram alerts (on-call lite)

1. `up{job="backend"} == 0` for 2m → "backend down"
2. Disk usage > 85% on data volume
3. PG connection pool exhausted > 90% for 5m
4. HTTP 5xx rate > 1/min for 5m
5. Celery queue depth > 1000 for 10m
6. Last successful backup > 26h ago

### Secret management

- `.env.prod` зашифрован в `ansible-vault`, расшифровывается на хосте при deploy.
- Минимальный набор: `SECRET_KEY`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `POSTGRES_PASSWORD`, `SMTP_PASSWORD`, `TELEGRAM_BOT_TOKEN` — каждый минимум 32 случайных байта.
- Никаких default-секретов в prod (RB-004 escalation policy уже это требует).

### Tenant provisioning

- CLI команда уже есть в `backend/app/cli/main.py`.
- Обернуть в `make pilot:create-tenant TENANT=acme SUBDOMAIN=acme.<наш-домен>.ru ADMIN_EMAIL=...`.

### TLS-домены для пилота

- Wildcard A-record `*.<наш-домен>.ru → prod IP`.
- Caddy выпускает Let's Encrypt сертификат автоматически.
- Каждый клиент получает свой `<tenant_slug>.<наш-домен>.ru`.

## 5. Pilot Readiness Checklist (WS5)

### Юр.пакет (7 документов + 1 регуляторное действие)

| # | Документ / Действие | Тип | Срок |
|---|---|---|---|
| 1 | `legal/ToS-pilot.md` | пилот-договор (scope, ответственность best-effort, расторжение) | неделя 1 |
| 2 | `legal/DPA-lite.md` | согласие на обработку ПДн (цели, срок, удаление) | неделя 1 |
| 3 | `legal/SLA-pilot.md` | "best effort, без фин.компенсации, реакция ≤ 1 раб.день" | неделя 1 |
| 4 | `legal/incident-disclosure.md` | шаблон уведомления клиента об инциденте | неделя 1 |
| 5 | `legal/pilot-agreement.docx` | сводный 1-страничный договор, подписывается реально | неделя 2 |
| 6 | `legal/consent-template-employees.md` | шаблон согласия, клиент даёт **своим** работникам (152-ФЗ ст. 9) | неделя 1 |
| 7 | `legal/policy-pdn-our.md` | публично на `<наш-домен>.ru/privacy` (152-ФЗ ст. 18.1) | неделя 2 |
| ✓ | Уведомление в Роскомнадзор | онлайн на pd.rkn.gov.ru (~30 мин подача, 7–14 дней ответ) | неделя 1 |

### Дисклеймеры в продукте

- Footer login-страницы: «Пилотная версия. Не использовать для критических ОТ-процессов без backup на бумаге.»
- Welcome-email: «Поддержка — best effort в рабочие дни. SLA не предусмотрен на этапе пилота.»

### Onboarding playbook — 12 шагов

Файл `docs/pilot/ONBOARDING_PLAYBOOK.md`:

1. Заполнить `clients/<tenant_slug>.yml` (имя, контакты, отрасль, размер).
2. Подписать pilot-agreement (PDF → google drive / nextcloud).
3. Получить от клиента: list of admin users (ФИО + email), желаемый subdomain.
4. DNS: добавить A-record `<tenant_slug>.<наш-домен>.ru` → prod IP.
5. SSH: `make pilot:create-tenant TENANT=<slug> SUBDOMAIN=<slug>.<наш-домен>.ru ADMIN_EMAIL=<lead>`.
6. Проверить вышедший magic-link, открыть в private window.
7. Создать первого admin'а через CLI, выслать одноразовый пароль.
8. Импортировать demo-данные (опционально): `make pilot:seed-demo TENANT=<slug>`.
9. Smoke-чек: войти как клиент-admin, создать одного работника, оформить один документ.
10. Подписаться на Prometheus alerts для tenant'а (label `tenant=<slug>`).
11. Welcome-email клиенту: ссылка, login, краткий how-to.
12. Запись в `clients/<tenant_slug>.yml`: дата запуска, ответственный support.

### Support setup

- 1 общий канал support в Telegram (или per-tenant каналы).
- Бот для алертов из Prometheus (тот же канал).
- Часы реакции: рабочие дни 10:00–18:00 МСК, best effort вне.
- Эскалация: incident > 4ч → созвон с клиентом + запись в `incidents/`.
- `docs/pilot/SUPPORT_PLAYBOOK.md`: первая помощь по 5 типичным проблемам (login failed, file upload error, PDF gen timeout, slow query, browser console error).

## 6. Timeline + Risks + ответ на «когда в комерцию»

### 4-недельный план (base case)

```
Week 1
  WS1 (iter-16f)   merge PR cross-base FK
  WS5 legal        drafts 5 documents
  WS5 РКН          filed day 2 (ответ через ~2 нед.)
  WS4 deploy       compose.prod + caddy + secrets
  WS2 quick wins   C6 (DocTemplate) + C7 (frontend label)
  WS2 C2 scope     decision doc для missing modules

Week 2
  WS2              C2 fix/delete, C5 staging, C4 healthcheck
  WS4              Prometheus/Grafana/Loki + backup cron
  WS5              docs 6, 7, pilot-agreement compile

Week 3
  WS2              C3 workspace 404s + start C1 RBAC
  WS4              deploy to staging, smoke + restore-drill
  WS5              pilot client outreach + первая подпись

Week 4
  WS2              finish C1 batches
  WS3              RB-002 re-verify, RB-003 final-acceptance,
                   sync 5 doc'ов, tag v1.0-RC1
  WS5              onboarding dry-run + pilot live
  ─────────────► ✅ PILOT LAUNCH READY (day ~28)
```

### Риски и митигации

| # | Риск | Вероятность | Impact | Митигация |
|---|---|---|---|---|
| R1 | C1 RBAC "вернуть контракт" глубже ожиданий | средняя | +1 нед. | timebox decision 4ч; fallback "обновить тесты" если > 50 LOC API surface |
| R2 | C2 missing modules — TODO, не deleted | высокая | +2 нед. unbounded | strict policy: scope > 80% полного фича-build → удалить тесты + v1.1 |
| R3 | РКН задерживает ответ > 14 дней | низкая | блокирует publish policy-pdn-our.md | публиковать драфт с пометкой "уведомление подано" |
| R4 | Frontend label drift — класс из 10+, не 2 | средняя | +3 дня | iter-17g sweep на `data-testid` |
| R5 | Off-site backup gotchas с Timeweb S3 | низкая | +1-2 дня | тест в неделе 2, не 4 |
| R6 | Friendly клиент не доступен в week 4 | средняя | +1-3 нед. | outreach начало week 3, bench 2-3 кандидатов |
| R7 | Windows+Py 3.13 локальная среда тормозит | известная | -20% velocity | CI на 3.12.12 — source of truth |
| R8 | WS4 monitoring stack ест RAM | низкая | апгрейд VPS | сразу 8 GB RAM, не 4 |

### Когда «можно в комерцию» — ответ

| Сценарий | Срок | Что готово |
|---|---|---|
| **Friendly pilot (бесплатно/символически)** | день ~28 (конец 4 недели base case) | Всё из этой спеки |
| **Friendly pilot с buffer на риски R1–R6** | день ~42 (6 недель) | То же + если ≥ 2 риска сработают |
| Первый платный клиент (фикс. сумма) | +2 нед. после успешного пилота (~неделя 6–8) | Подтверждённый пилот + manual billing (счёт через банк, акт) |
| Закрытая бета (5–20 paid) | +1.5–2 мес. после пилота | Полноценный DPA, billing integration, self-serve onboarding, monitoring per-tenant |
| Public GA | +3–6 мес. после пилота | Compliance audit, support tier, landing site, SLA с финансовой ответственностью |

**Прямой ответ:** если стартуем по этой спеке завтра — **первого пилотного friendly-клиента в production можно ставить через ~4 недели (целевая дата)**, с реалистичным запасом 6 недель.

## 7. Cross-links и обновляемые документы

После закрытия каждой части спеки обновляются:

- `docs/stabilization/RELEASE_BLOCKERS_STATUS.md` (single source of truth)
- `RELEASE_READINESS.md` (вердикт + RC summary)
- `ACCEPTANCE_TEST_MATRIX.md`
- `KNOWN_LIMITATIONS.md`
- `GAP_REPORT.md`
- `docs/stabilization/PLAN.md`
- `AI_IMPLEMENTATION_REPORT.md` (handoff entry для каждой итерации)
