# Security baseline

## API tokens
- Токены хранятся только в виде SHA-256 хеша.
- Raw токен не хранится и возвращается только при создании.

## Logs and masking
- Не логируйте секреты и PII.
- Ошибки должны содержать correlation id и безопасный payload.

## File security
- Интеграция AV/macro checks должна выполняться в upload pipeline.

## 2026-03-22 document/pipeline hardening note
- Pipeline orchestration no longer returns raw `stub` results for the covered internal steps (`sign`, `verify_signature`, `send_edo`, `index_file_content`).
- Legacy Celery compatibility wrappers still exist, but they now surface explicit accepted/deferred bridge semantics instead of opaque stub statuses.
- Non-production integration adapters remain isolated in `backend/app/services/integrations/stubs.py` and must not be treated as certified providers.
