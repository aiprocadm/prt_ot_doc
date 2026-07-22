# SEC-64 §64.3 — SSRF-защита исходящих вебхуков — design spec

- **Дата:** 2026-07-22
- **Статус:** approved (scope + глубина зафиксированы пользователем через AskUserQuestion)
- **Ветка:** `feat/sec64-webhook-ssrf-guard` от `main` (head `983d10e1`, после мержа PR #773).
- **Канон ТЗ:** `docs/spec/TZ_FULL_UNIFIED.md` B-NEXT.7 → «AppSec/OWASP … SSRF-защита — разд. 64». Матрица: `docs/audit/TZ_COVERAGE_MATRIX.md` строка **SEC-64** (было `partial(xml_security)` — XXE закрыт, SSRF нет). Roadmap: Phase 16 (security, приоритет выше бизнес-фаз).
- **Аддитивно:** новых таблиц/миграций НЕТ. Только новый core-модуль + guard-вызов в двух точках отправки + settings-флаг.

## 1. Контекст (сверка код↔ТЗ)

Исходящие вебхуки могут быть нацелены арендатором/админом на **внутренние адреса** (cloud-metadata `169.254.169.254`, `localhost`-админ-порты, приватные подсети) — классический SSRF: сервер сам сходит туда и может утечь секреты/обойти сетевую изоляцию.

**Что есть:** `backend/app/core/integration_url_validation.py::assert_safe_http_base_url` — блокирует приватные/link-local/multicast/reserved литеральные IP и требует https в prod/staging. Но:
- применён **только** к EDO-интеграции (`config.py`, `services/integrations/http_edo.py`);
- **НЕ применён** к исходящим вебхукам;
- **не резолвит DNS** — имя, указывающее на внутренний IP, проходит проверку.

**Реальные точки исходящей отправки вебхуков (ровно две; проверено grep):**
1. `backend/app/services/webhooks.py::WebhookDispatcher._deliver` (строка `client.post(dest.url, …)`) — общий диспетчер, адреса `dest.url` из БД/конфига арендатора. **Основной риск.** `services/outbox.py` шлёт **через** этот диспетчер (делегирует), поэтому одна точка покрывает и outbox.
2. `backend/app/modules/notifications/providers/webhook.py::WebhookProvider.deliver` (`client.post(url, …)`) — уведомления на `WEBHOOK_NOTIFICATION_URL` (env-конфиг). Defense-in-depth.

`approval/webhook_utils.py` — только подписи, HTTP не шлёт. `events.py` — не шлёт.

## 2. Решения (зафиксированы пользователем через AskUserQuestion)

1. **Объём среза = SSRF-защита исходящих вебхуков** (SEC-64 §64.3). Секреты (SEC-67), 152-ФЗ (SEC-66), RLS (SEC-65), impersonation (SEC-63) — отдельными срезами. impersonation как фичи в коде НЕТ (только константы `product_spec.py`) — защищать нечего; RLS требует отдельного плана + списка таблиц.
2. **Глубина = тщательно, с проверкой DNS.** Кроме литеральных IP — резолвить имя и проверять **все** полученные адреса.

## 3. Не-цели (осознанно вне объёма)

- **Пиннинг соединения к проверенному IP** (полная защита от DNS-rebinding TOCTOU между проверкой и connect). Резолвим непосредственно перед отправкой — остаточный TOCTOU задокументирован как известный лимит; пиннинг через кастомный httpx-transport — отдельный follow-up.
- Проверка входящих вебхуков (там своя HMAC-аутентификация — `core/inbound_webhook_auth.py`).
- SSRF в других исходящих клиентах (EDO уже прикрыт; прочие интеграции — по мере появления).
- Аллоу-лист доменов на арендатора (v1 — deny-лист внутренних адресов, не allow-лист).

## 4. Данные — без миграции

Ничего не хранится. Guard — чистая проверка URL + резолвинг в рантайме перед отправкой.

## 5. Backend — guard-модуль

**Новый модуль** `backend/app/core/ssrf_guard.py`:
- `class UnsafeWebhookURLError(ValueError)`.
- `def _ip_is_blocked(ip: IPv4Address | IPv6Address) -> bool` — True для `is_private | is_loopback | is_link_local | is_multicast | is_reserved | is_unspecified`; IPv4-mapped IPv6 (`::ffff:a.b.c.d`) разворачивать в IPv4 перед проверкой (иначе `10.0.0.1` в IPv6-обёртке пройдёт).
- `async def assert_safe_webhook_url(url: str, *, app_env: str, resolver=None) -> None`:
  1. parse; scheme ∈ {http, https} иначе raise; host непустой иначе raise.
  2. `strict = app_env in ("production", "staging")`.
  3. В strict: **требовать https** (http reject) — согласовано с §64-харденингом (loopback для вебхуков всё равно заблокирован).
  4. Кандидаты-IP: host — литеральный IP → `[ip]`; иначе:
     - strict → резолвить (`resolver(host)`, дефолт `asyncio.to_thread(socket.getaddrinfo, host, None)`), собрать **все** IP; пустой/ошибка резолва → **raise (fail-closed)**;
     - не-strict (dev/test) → **вернуть без резолва** (permissive: чтобы `http://testserver`, `https://example.test` в тестах не били по сети и не падали).
  5. Каждый кандидат-IP: `_ip_is_blocked` → raise.
- Дефолтный резолвер инъектируемый (для тестов — фейковый, без сети).

**Почему env-зависимо:** в тестах `app_env="development"` (conftest не переопределяет), вебхуки шлют на выдуманные не-резолвящиеся имена. Строгий guard с реальным DNS уронил бы 4253+ тестов и был бы флейки в CI без сети. Угроза-модель — прод; там guard строгий и fail-closed.

**Settings-флаг** (`config.py`): `webhook_ssrf_guard_enabled: bool = Field(True, alias="WEBHOOK_SSRF_GUARD_ENABLED")` — оперативный kill-switch, дефолт **включён**.

## 6. Backend — врезка guard в точки отправки

Обе точки — перед реальным `client.post`, под флагом `settings.webhook_ssrf_guard_enabled`:

1. **`services/webhooks.py::WebhookDispatcher._deliver`** — в цикле по `destinations`, до `client.post(dest.url…)`:
   `try: await assert_safe_webhook_url(dest.url, app_env=self.settings.app_env) except UnsafeWebhookURLError: log "webhook.blocked_ssrf" (tenant_id, url, reason); failures.append((dest.url, 0)); continue`. Sentinel-статус `0` = «заблокирован до отправки» (в сообщении об ошибке отличим от HTTP-кодов). Флаг off → врезку пропускаем.
2. **`notifications/providers/webhook.py::WebhookProvider.deliver`** — до `client.post(url…)`:
   `try: await assert_safe_webhook_url(url, app_env=s.app_env) except UnsafeWebhookURLError as e: return DeliveryResult.fail(f"webhook blocked (ssrf): {e}")`. Флаг off → пропускаем.

Guard **await-ится** (резолвинг в thread) — обе функции async, ок.

## 7. Frontend

Изменений нет — чисто серверная защита. (Опц. будущее: показывать причину «адрес заблокирован» в UI настроек вебхуков — вне объёма.)

## 8. Demo-seed

Не трогаем.

## 9. Тест-план

**Unit (чистый guard, без сети — фейковый резолвер):** `tests/test_ssrf_guard.py` (НОВЫЙ):
- scheme reject (`ftp://`, `file://`, пусто); host отсутствует.
- литеральные блок-IP: `169.254.169.254` (metadata), `127.0.0.1`, `10.0.0.5`, `192.168.1.1`, `::1`, `::ffff:10.0.0.1` (IPv4-mapped), `0.0.0.0`, `224.0.0.1` (multicast).
- prod: имя резолвится в приватный IP (fake resolver) → raise; имя резолвится в публичный → ok; имя не резолвится → raise (fail-closed); http в prod → raise; https публичный → ok.
- dev: любое имя без резолва → ok (permissive); литеральный приватный IP → всё равно raise (даже в dev).
- IPv6-mapped и смешанный резолв (один публичный + один приватный → raise).

**API/service (dispatch-интеграция):**
- `tests/test_webhooks_ssrf.py` (НОВЫЙ): `WebhookDispatcher` со stub-settings `app_env="production"` + инъекция fake resolver + mock httpx-client → небезопасный `dest.url` → `client.post` НЕ вызван, в failures `(url, 0)`, лог `webhook.blocked_ssrf`; безопасный публичный URL → post вызван. Флаг off → guard пропущен (post вызван даже для приватного).
- Регресс существующих: `tests/test_webhooks_dispatch.py`, `test_webhook_routing.py`, `test_notification_delivery.py` — должны остаться зелёными (dev-env permissive).

**Гейты (порядок как в прошлых срезах):**
1. Backend-регресс батчами: новые + смежные webhooks/notifications/outbox тесты (ОДИН прогон, timeout 600000).
2. `ruff check --no-fix` + `ruff format` clean.
3. **OpenAPI baseline** — не меняется (роутов не добавляли); `check_openapi_snapshot.py` = EXIT 0 (сверить, что не поехало).
4. Frontend — не трогали; гейты не требуются (но typecheck/build не ломаются, т.к. изменений нет).
5. `TZ_COVERAGE_MATRIX.md` SEC-64 → `partial(xml_security)` → `partial(xml_security+webhook_ssrf)`; handoff в `AI_IMPLEMENTATION_REPORT.md`, `CHANGELOG.md`.

## 10. Риски / грабли

- **Ложное срабатывание в тестах** → env-зависимая строгость (dev permissive) + инъектируемый резолвер (без реальной сети).
- **IPv4-mapped IPv6-байпас** (`::ffff:10.0.0.1`) → разворачивать в IPv4 до проверки.
- **DNS-rebinding TOCTOU** → резолв непосредственно перед отправкой; полный пиннинг вне объёма (документировано).
- **Fail-closed в prod при недоступном DNS** — осознанно: лучше не отправить, чем отправить вслепую. Флаг `WEBHOOK_SSRF_GUARD_ENABLED=false` — аварийный kill-switch.
- **Не сломать outbox** — он делегирует диспетчеру, отдельной врезки не требует; sentinel-статус `0` в failures не должен ломать retry-классификацию (`webhook_retry_telemetry`) — проверить, что `0` трактуется как неретраебл/логируемый, не как krash.

## 11. Порядок реализации

1. Модуль `core/ssrf_guard.py` + settings-флаг.
2. Врезка в `services/webhooks.py` и `notifications/providers/webhook.py`.
3. Unit-тесты guard.
4. Dispatch-интеграционные тесты.
5. Гейты: pytest батч, ruff, openapi-снапшот; матрица + handoff + CHANGELOG.
