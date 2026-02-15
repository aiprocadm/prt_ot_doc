# Документация

## Индекс
- **ТЗ платформы:** [spec/TZ.md](spec/TZ.md)
- **Runbook Codespaces:** [runbook-codespaces.md](runbook-codespaces.md)
- **Testing guide:** [testing.md](testing.md)
- **Архитектура:** [ARCHITECTURE.md](ARCHITECTURE.md)
- **OpenAPI контракт:** [openapi.yaml](openapi.yaml)
- **Аудит соответствия ТЗ:** [audit/TZ_COMPLIANCE.md](audit/TZ_COMPLIANCE.md)
- **Карта архитектуры (audit):** [audit/ARCHITECTURE_MAP.md](audit/ARCHITECTURE_MAP.md)
- **Failure map:** [audit/FAILURE_MAP.md](audit/FAILURE_MAP.md)
- **Repo hygiene:** [audit/REPO_HYGIENE.md](audit/REPO_HYGIENE.md)

## Ключевые инженерные документы
- [Интеграции](INTEGRATIONS.md)
- [Модель предметной области](DOMAIN_MODEL.md)
- [Аудит фронтенда (historical)](audit/FRONTEND_AUDIT.md)
- [Roadmap](NEXT_FEATURES.md)


## Примеры окружений
- Пилотный профиль окружения: [`examples/.env.pilot.example`](examples/.env.pilot.example)

## Infra (optional для Codespaces)
- `proxy/` и `infra/docker-compose.migration.yml` используются для compose/deploy сценариев и не обязательны для dockerless `make cs:dev`.
