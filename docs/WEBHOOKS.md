# OPS-73 (разд. 73.3): контракт исходящих вебхуков

> ТЗ: «Версионирование вебхуков и их payload'ов (не только REST) — событие тоже
> контракт».

## Версия схемы

Каждая доставка несёт версию дважды:

- в теле — поле `schema_version` (сейчас `"1"`);
- в заголовке — `X-Webhook-Schema-Version` (маршрутизация до разбора тела).

Версия поднимается **только** на ломающем изменении (список —
`product_spec.API_BREAKING_CHANGES`); добавление нового поля, типа события или
заголовка версию не меняет — пишите парсер толерантным к неизвестным полям.
Состав контракта стережёт CI-гейт `tests/contract/test_webhook_payload_contract.py`:
исчезновение типа события или поля payload — красный билд.

## Два конвейера доставки (историческая правда)

Конверты РАЗНЫЕ — это зафиксированное состояние, а не дизайн. Слить их сейчас
означало бы ломающее изменение для живых подписчиков; путь к унификации — через
bump `schema_version` в отдельной мажорной версии контракта.

### Конвейер подписок (`services/webhooks.py`)

Тело:

```json
{
  "id": "<event_id>",
  "type": "<event_type>",
  "event_type": "<event_type>",
  "occurred_at": "<ISO-8601, момент отправки>",
  "correlation_id": "<trace>",
  "payload": { "...": "поля события, см. каталог ниже" },
  "schema_version": "1"
}
```

Заголовки: `X-Correlation-Id`, `X-Event-Type`, `X-Tenant`,
`X-Timestamp` (**миллисекунды**), `X-Event-Id`, `Idempotency-Key`,
`X-Webhook-Schema-Version`; подпись `X-Signature: v1=<hex>` =
HMAC-SHA256(секрет, `"{X-Timestamp}." + тело`).

### Конвейер очереди (`tasks/_core.py`, задача `outbox.dispatch*`)

Тело:

```json
{
  "event_id": "<event_id>",
  "event_type": "<event_type>",
  "tenant_id": "<tenant>",
  "payload": { "...": "поля события" },
  "headers": { "...": "заголовки записи outbox" },
  "correlation_id": "<trace>",
  "schema_version": "1"
}
```

Заголовки: `X-Event-Id`, `X-Event-Type`, `X-Tenant`, `X-Correlation-Id`,
`X-Webhook-Schema-Version`; подпись `X-Signature: v1=<hex>` =
HMAC-SHA256(секрет, `"{X-Signature-Ts}." + тело`), где `X-Signature-Ts` —
**секунды** (не миллисекунды — проверяйте подпись меткой из СВОЕГО конвейера).

## Каталог событий

33 типа события перечислены в `backend/app/services/events.py::EventType`;
payload каждого типа описан pydantic-моделью (`_PAYLOADS`, `extra="forbid"`).
База всех payload'ов: `tenant_id`, `actor_id`, `occurred_at`, `event_id`.
Полная замороженная карта «тип → поля v1» —
`tests/contract/test_webhook_payload_contract.py::FROZEN_PAYLOAD_FIELDS`.

Удаление типа или поля без bump'а версии валит CI. Добавления законны.

## Зафиксированные несоответствия (кандидаты на v2)

- **Два формата конверта** — см. выше; унификация возможна только через bump.
- **Единицы метки времени подписи различаются**: миллисекунды (`X-Timestamp`)
  в конвейере подписок против секунд (`X-Signature-Ts`) в конвейере очереди.
- **Путь OutboxProcessor → WebhookDispatcher не подписывает доставку**: секрет
  не персистится в записи Outbox, и явный destination создаётся без секрета.
  Конвейер очереди (Celery-задача) подписывает корректно. Кандидат в отдельный
  фикс — смежен с SEC-67.
