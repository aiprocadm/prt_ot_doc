# GAP REPORT

Финальный gap analysis для release-candidate волны. Цель — не переписывать платформу, а зафиксировать, что уже стабилизировано, что закрыто в этой волне и что остается осознанным backlog/limitation.

## Closed in RC wave

- Сформирован единый acceptance gate: `make final-acceptance`, включая backend critical tests, e2e regression, OpenAPI validation, migration head sanity, health/readiness, schema consistency и release-doc checks.
- Формализованы точные release artifacts, ожидаемые на приемке: `ACCEPTANCE_TEST_MATRIX.md`, `GAP_REPORT.md`, `RELEASE_READINESS.md`, `KNOWN_LIMITATIONS.md`.
- Контракт ошибок закреплен тестами на `code`, `type`, `message`, `details`, `field_errors`, `correlation_id`, `timestamp`.
- Frontend client теперь нормализует structured error payload без потери `type`, `field_errors`, `correlation_id`, `timestamp`, а shared `ErrorState` показывает эти поля пользователю в критичных экранах.
- Появилась явная проверка наличия RC-docs и perf/load foundation в acceptance regression.
- Убраны два явных UX dead end на критичных путях: мастер генерации пакетов повторно грузит пресеты без полного reload страницы, а документный wizard завершает сценарий реальными переходами в архив/согласование вместо disabled placeholder.

## Remaining P0/P1 gaps

### 1. True multi-step UI e2e on browser level
- В репозитории уже есть backend/e2e acceptance и богатый smoke baseline, но нет полного browser-driven сценарного пакета на все 15 критичных сквозных потока.
- Для pilot/release candidate это компенсируется API/e2e/integration слоями и walkthrough/runbook evidence.
- Рекомендуемый следующий шаг: расширить Playwright/Cypress suite на onboarding, documents, portal, incident/inspection и billing flows.

### 2. Production-like performance numbers
- `scripts/perf/api_load.py` дает воспроизводимый smoke/load foundation, но не заменяет stage/perf-lab.
- Нет зафиксированных stage p95/p99 по search, export queue и PDF generation.
- В RC это признано ограничением, а не blocker'ом локального acceptance.

### 3. Deep external integrations verification
- Контракты, webhooks, retry и readiness foundation есть, но production контуры внешних провайдеров требуют отдельного стенда.
- Это остается отдельным приемочным этапом pilot/on-prem rollout.

### 4. UX/a11y breadth
- Критичные страницы и shared states уже существенно стабилизированы предыдущими волнами, но полный formal a11y audit на все кабинеты/реестры еще не завершен.
- Mobile-safe review и keyboard/focus coverage должны расширяться адресно по usage telemetry.
- После текущего hardening критичные wizard flows лучше проходят без ручного reload, но по-прежнему остается длинный хвост для унификации labels/ARIA и responsive-first table interactions.

## Hot-path / reliability notes

- Tenant boundary, idempotency, outbox/webhook retry и health/readiness — это текущие release blockers; они закрыты тестами и входят в acceptance gate.
- Perf/load groundwork присутствует и пригоден для пилотного smoke прогона.
- Для production cut-over еще нужны stage-specific benchmark artifacts и restore rehearsal evidence.

## Release recommendation

**Recommendation:** candidate is suitable for demo, pilot and formal acceptance rehearsal, with explicit known limitations captured in `KNOWN_LIMITATIONS.md`.
