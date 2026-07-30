"""OPS-73 срез-2 (разд. 73.3): контракт исходящего вебхука.

ТЗ: «Версионирование вебхуков и их payload'ов (не только REST) — событие тоже
контракт». До этого среза версии у конверта не было ВООБЩЕ: подписчик не мог
ни узнать, по какой схеме разбирать тело, ни заметить, что схема изменилась.

Здесь — канонические константы, которые читают ОБА конвейера доставки и
контрактный тест. Историческая правда, зафиксированная как есть: конвейера два
(`services/webhooks.py` и `tasks/_core.py`) и конверты у них РАЗНЫЕ. Слить их в
один формат сейчас нельзя — это само по себе ломающее изменение для уже живых
подписчиков (`change_semantics` из ``API_BREAKING_CHANGES``); путь к унификации
лежит через bump ``schema_version``, и ровно для этого версия и вводится.
"""

from __future__ import annotations

__all__ = [
    "DISPATCHER_ENVELOPE_KEYS",
    "OUTBOX_TASK_BODY_KEYS",
    "WEBHOOK_SCHEMA_VERSION",
    "WEBHOOK_SCHEMA_VERSION_HEADER",
]

# Версия схемы конверта И payload'ов. Поднимается только на ломающем изменении
# (список — ``product_spec.API_BREAKING_CHANGES``); добавление нового поля или
# нового типа события версию НЕ меняет (разд. 73.1: «добавления — в текущей»).
WEBHOOK_SCHEMA_VERSION = "1"

# Заголовок с версией: подписчик выбирает парсер, не заглядывая в тело.
WEBHOOK_SCHEMA_VERSION_HEADER = "X-Webhook-Schema-Version"

# Конверт конвейера подписок (`WebhookDispatcher.dispatch`).
DISPATCHER_ENVELOPE_KEYS: frozenset[str] = frozenset(
    {
        "id",
        "type",
        "event_type",
        "occurred_at",
        "correlation_id",
        "payload",
        "schema_version",
    }
)

# Тело конвейера очереди (`tasks._dispatch_outbox_events`).
OUTBOX_TASK_BODY_KEYS: frozenset[str] = frozenset(
    {
        "event_id",
        "event_type",
        "tenant_id",
        "payload",
        "headers",
        "correlation_id",
        "schema_version",
    }
)
