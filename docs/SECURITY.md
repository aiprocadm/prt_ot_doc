# Security baseline

## API tokens
- Токены хранятся только в виде SHA-256 хеша.
- Raw токен не хранится и возвращается только при создании.

## Logs and masking
- Не логируйте секреты и PII.
- Ошибки должны содержать correlation id и безопасный payload.

## File security
- Интеграция AV/macro checks должна выполняться в upload pipeline.
