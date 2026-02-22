# Reliability core: Idempotency + Outbox + Jobs

## Idempotency-Key

- Для бизнес-POST/PUT/PATCH используйте заголовок `Idempotency-Key`.
- Для `POST /api/v1/documents:generate` ключ обязателен.
- Ключ привязывается к `tenant + endpoint + method + request_hash`.
- Повтор с тем же ключом и тем же payload возвращает сохранённый ответ (`task_id/job_id` и `document_version_id`, если уже известен).
- Повтор с тем же ключом и другим payload возвращает `409` (`idempotency_conflict`).
- Ошибки 4xx/5xx фиксируются в записи идемпотентности и повторяются для того же ключа.

## Outbox pattern

- Публикация внешних событий выполняется через `OutboxService.enqueue(...)` в той же транзакции, что и бизнес-изменения.
- После commit события выбираются диспетчером (`OutboxProcessor`) и отправляются в целевую систему.
- Ретраи: экспоненциальный backoff + jitter (`OUTBOX_RETRY_BACKOFF_SECONDS`, `OUTBOX_RETRY_BACKOFF_MAX_SECONDS`).
- После превышения лимита `OUTBOX_MAX_ATTEMPTS` событие помечается как poison/dead-letter (`DEAD`) и требует ручного разбора.
- Дедуп выполняется по `idempotency_key` и учёту уже доставленных событий у подписки.

## Job orchestration

- `DocumentJob` — верхнеуровневый процесс (queued/running/success/failed/canceled).
- `DocumentJobStep` — шаг пайплайна с попытками, входом/выходом, ошибками.
- API:
  - `GET /api/v1/jobs/{id}`
  - `GET /api/v1/jobs?status=&type=&created_by=`
  - `POST /api/v1/jobs/{id}:cancel`
  - `POST /api/v1/jobs/{id}:retry-step` с `{ "step_key": "convert_pdf" }`
- Повтор шага идемпотентен: если артефакт уже существует, шаг отмечается успешным без повторного создания.

## Как добавить новый step в pipeline

1. Добавьте `step_code` в список шагов оркестратора.
2. Определите выходной `artifact_kind` (если есть материализуемый артефакт).
3. Добавьте retry-политику (если шаг временно-ошибочный).
4. Обновите UI timeline (при необходимости) и тесты переходов статусов.
5. Убедитесь, что step при повторе не ломает существующие артефакты.
