"""OPS-73 срез-2 (разд. 73.3): версия схемы в ЖИВЫХ конвертах вебхуков.

Контрактный гейт (tests/contract) стережёт состав контракта; здесь — рантайм:
оба конвейера доставки реально кладут ``schema_version`` в тело и заголовок
``X-Webhook-Schema-Version`` в запрос. Без рантайм-проверки константа и код
могли бы разойтись, и оба выглядели бы работающими.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.core.config import get_settings
from app.core.webhook_contract import (
    DISPATCHER_ENVELOPE_KEYS,
    WEBHOOK_SCHEMA_VERSION,
    WEBHOOK_SCHEMA_VERSION_HEADER,
)
from app.services.webhooks import WebhookDispatcher


@pytest.mark.anyio
async def test_dispatcher_envelope_carries_schema_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WEBHOOK_URLS_DOCUMENT_EXPORTED", "https://example.test/hooks/exported")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        dispatcher = WebhookDispatcher(settings=get_settings(), client=client)
        destinations = dispatcher.resolve_destinations("DocumentExported")
        await dispatcher.dispatch(
            event_type="DocumentExported",
            tenant_id="tenant-1",
            payload={"event_id": "evt-1", "zip_storage_key": "s3/key"},
            destination=destinations[0],
        )

    get_settings.cache_clear()  # type: ignore[attr-defined]

    assert len(requests) == 1
    body = json.loads(requests[0].content.decode("utf-8"))
    # Версия в теле: подписчик, у которого нет доступа к заголовкам (очередь,
    # реплей из лога), всё равно знает, каким парсером разбирать.
    assert body["schema_version"] == WEBHOOK_SCHEMA_VERSION
    # Версия в заголовке: маршрутизация до разбора тела.
    assert requests[0].headers.get(WEBHOOK_SCHEMA_VERSION_HEADER) == WEBHOOK_SCHEMA_VERSION
    # Конверт несёт РОВНО ключи контракта — не подмножество и не надмножество:
    # молчаливое расширение конверта тоже должно быть осознанным (через контракт).
    assert set(body) == set(DISPATCHER_ENVELOPE_KEYS)
