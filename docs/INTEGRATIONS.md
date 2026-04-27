# План интеграций с внешними системами

Этот документ описывает слой абстракций для интеграции с внешними системами (1С, оператор ЭДО/ЭП, ФРДО, ЕИСОТ) и порядок их включения.

## Maturity matrix

| Adapter | Maturity | Фактический режим | Production path |
|---|---|---|---|
| 1C | `pilot` | Контракт + in-memory pilot adapter, без реального внешнего обмена | Нет |
| EDO | `production-ready` | HTTP-адаптер с env-контрактом (`HttpEDOIntegration`) | Да |
| FRDO | `pilot` | Контракт + in-memory pilot adapter, без реального внешнего обмена | Нет |
| EISOT | `pilot` | Контракт + in-memory pilot adapter, без реального внешнего обмена | Нет |

Статусы `stub | pilot | production-ready` используются как декларация зрелости и должны соответствовать фактическому поведению адаптеров.

## Цели

- Сформировать единый контракт для каждой интеграции.
- Дать возможность подключать или отключать интеграции через feature-флаги.
- Обеспечить заглушечные реализации до появления реальных клиентов.

## Интерфейсы

Все интерфейсы расположены в `backend/app/services/integrations/interfaces.py` и используют тип `IntegrationStatus` для нормализованного статуса операции.

### 1С (`BaseAccountingIntegration`)

Все методы — `async`.

- `async export_document(payload: dict[str, Any]) -> IntegrationStatus` — отправить документ в 1С.
- `async fetch_document(external_id: str) -> dict[str, Any] | None` — получить сохранённый документ из 1С.
- `async sync_status(external_id: str) -> IntegrationStatus` — обновить статус обработки.
- `async health_check() -> bool` — проверка доступности канала.

### Оператор ЭДО/ЭП (`BaseEDOIntegration`)

Все методы — `async`. Аргументы `send_document` передаются только как keyword-аргументы.

- `async send_document(*, content: bytes, filename: str, metadata: dict[str, Any] | None = None) -> IntegrationStatus` — отправка документа в ЭДО/ЭП.
- `async download_document(external_id: str) -> bytes` — загрузка переданного документа.
- `async get_document_status(external_id: str) -> IntegrationStatus` — проверка доставки/подписи.
- `async health_check() -> bool` — проверка доступности оператора.

### ФРДО (`BaseFRDOIntegration`)

Все методы — `async`.

- `async submit_record(payload: dict[str, Any]) -> IntegrationStatus` — отправка записи об образовании.
- `async fetch_record(external_id: str) -> dict[str, Any] | None` — получение сохранённой записи.
- `async get_record_status(external_id: str) -> IntegrationStatus` — проверка статуса регистрации.
- `async health_check() -> bool` — проверка доступности сервиса.

### ЕИСОТ (`BaseEISOTIntegration`)

Все методы — `async`.

- `async publish_report(payload: dict[str, Any]) -> IntegrationStatus` — публикация отчёта по охране труда.
- `async get_publication_status(external_id: str) -> IntegrationStatus` — проверка обработки отчёта.
- `async pull_notifications() -> list[IntegrationStatus]` — получение уведомлений из ЕИСОТ.
- `async health_check() -> bool` — проверка доступности сервиса.

## Реализации по зрелости

- `PilotAccountingIntegration`, `PilotFRDOIntegration`, `PilotEISOTIntegration` — **pilot**-контракт с in-memory поведением и минимальной валидацией входа (без production promises).
- `StubEDOIntegration` — **stub** для локальной разработки, когда EDO feature flag включен, но URL оператора не задан.
- `HttpEDOIntegration` — **production-ready** path для EDO (реальный HTTP клиент).
- `Disabled*Integration` — поднимают `IntegrationDisabledError`, когда интеграция отключена feature-флагом.

Для pilot-адаптеров (1C/FRDO/EISOT) ошибки валидации нормализуются через `IntegrationContractError` + `IntegrationErrorContract`.

## Фабрики и DI

Фабрики находятся в `backend/app/services/integrations/factory.py` и кэшируют экземпляры интеграций:
- `get_accounting_integration()` — 1С.
- `get_edo_integration()` — ЭДО/ЭП.
- `get_frdo_integration()` — ФРДО.
- `get_eisot_integration()` — ЕИСОТ.

Для сброса кэша после смены конфигурации используйте `reset_integration_providers()`.

## Включение и отключение

Каждая интеграция управляется отдельным feature-флагом в `.env`:

```env
USE_1C_INTEGRATION=false
USE_EDO_INTEGRATION=false
USE_FRDO_INTEGRATION=false
USE_EISOT_INTEGRATION=false
```

- Значение `true`/`1` включает заглушечную реализацию (до появления реальных клиентов).
- Для 1C/FRDO/EISOT значение `true`/`1` включает pilot adapter (in-memory, contract-only).
- Для EDO значение `true`/`1` включает:
  - production-ready HTTP adapter, если задан `EDO_INTEGRATION_BASE_URL`;
  - stub adapter, если URL не задан.
- Значение `false`/`0` возвращает `Disabled*Integration`, методы которой генерируют `IntegrationDisabledError`.

После изменения переменных окружения нужно перезапустить приложение или вызвать `reset_settings_cache()` и `reset_integration_providers()` перед следующим использованием фабрик.
