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
    "ENVELOPE_KEYS_V2",
    "OUTBOX_TASK_BODY_KEYS",
    "SIGNATURE_TIME_UNIT",
    "SUPPORTED_SCHEMA_VERSIONS",
    "WEBHOOK_SCHEMA_VERSION",
    "WEBHOOK_SCHEMA_VERSION_HEADER",
    "WEBHOOK_SCHEMA_VERSION_V2",
    "build_envelope_v2",
    "resolve_schema_version",
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


# ---------------------------------------------------------------------------
# СРЕЗ-191 (OPS-73 разд. 73.1/73.3): схема 2 — единый конверт и единая подпись.
# ---------------------------------------------------------------------------
#
# ЧТО БЫЛО НЕ ТАК. Конвейера доставки два, и они расходились в ДВУХ местах:
#
# 1. Конверт. У подписок — id/type/event_type/occurred_at; у очереди —
#    event_id/event_type/tenant_id/headers. Подписчик, получающий события с
#    обоих путей, вынужден держать два разбора одного и того же.
# 2. ЕДИНИЦЫ ВРЕМЕНИ В ПОДПИСИ. Конвейер подписок ставит X-Timestamp в
#    МИЛЛИСЕКУНДАХ, конвейер очереди — X-Signature-Ts в СЕКУНДАХ. Подписчик,
#    проверяющий подпись по описанию, получает несходящуюся подпись на половине
#    доставок — и это выглядит как взлом, а не как расхождение форматов.
#
# Схема 2 сводит оба к одному виду. Единица — СЕКУНДЫ: так принято у платёжных
# провайдеров, чьи примеры проверки подписи люди и копируют.
#
# ПЕРЕКЛЮЧЕНИЕ ПОШТУЧНОЕ. Версия живёт у подписчика
# (webhook_endpoints.schema_version), умолчание развёртывания — константа выше.
# Старая схема продолжает работать, пока её кто-то использует: разд. 73.2.

WEBHOOK_SCHEMA_VERSION_V2 = "2"

SUPPORTED_SCHEMA_VERSIONS: frozenset[str] = frozenset(
    {WEBHOOK_SCHEMA_VERSION, WEBHOOK_SCHEMA_VERSION_V2}
)

#: Единый конверт схемы 2. Одинаковый у ОБОИХ конвейеров.
ENVELOPE_KEYS_V2: frozenset[str] = frozenset(
    {
        "schema_version",
        "id",
        "type",
        "tenant_id",
        "occurred_at",
        "correlation_id",
        "payload",
    }
)

#: Единица времени в подписи по версиям. Расхождение здесь и было главной
#: находкой среза-191.
SIGNATURE_TIME_UNIT = {
    WEBHOOK_SCHEMA_VERSION: "mixed",
    WEBHOOK_SCHEMA_VERSION_V2: "seconds",
}


def resolve_schema_version(endpoint_version: str | None, *, default: str | None = None) -> str:
    """Какую схему слать этому подписчику.

    Пустая строка и None — одно и то же: «не задано», то есть умолчание
    развёртывания. Разводить их значило бы получить подписчика, которому не
    шлют ничего. Неизвестная версия НЕ включает ничего нового: это опечатка, а
    молча слать по ней означало бы сломать живую доставку.
    """

    chosen = (endpoint_version or "").strip() or (default or "").strip() or WEBHOOK_SCHEMA_VERSION
    return chosen if chosen in SUPPORTED_SCHEMA_VERSIONS else WEBHOOK_SCHEMA_VERSION


def build_envelope_v2(
    *,
    event_id: str,
    event_type: str,
    tenant_id: str,
    occurred_at: str,
    correlation_id: str,
    payload: dict,
) -> dict:
    """Единый конверт схемы 2 — один и тот же у обоих конвейеров."""

    return {
        "schema_version": WEBHOOK_SCHEMA_VERSION_V2,
        "id": str(event_id),
        "type": str(event_type),
        "tenant_id": str(tenant_id),
        "occurred_at": occurred_at,
        "correlation_id": str(correlation_id),
        "payload": payload or {},
    }
