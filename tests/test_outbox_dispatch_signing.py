"""SEC-67-смежный фикс: путь OutboxProcessor → dispatcher обязан подписывать.

Дефект (найден исследованием OPS-73 срез-2, воспроизведён ревью): процессор
передаёт диспетчеру ЯВНЫЙ destination, и цель строилась без секрета — доставка
уходила неподписанной, хотя у подписки секрет есть. Подписчик, проверяющий
подпись, отвергал каждую такую доставку; подписчик без проверки получал
неаутентифицированные вызовы. Celery-путь (`tasks/_core.py`) подписывал всегда —
дефект жил только в этом конвейере и был неотличим от «вебхуки работают».

Что закрепляется:

* доставка через процессор ПОДПИСАНА, подпись сходится с плейнтекст-секретом
  (секрет хранится зашифрованным, SEC-67 — расшифровка в момент использования);
* секрет находится и по id подписки из заголовков записи, и по URL (fallback);
* назначение без секрета (env-URL) по-прежнему уходит без подписи и без падения;
* чужой арендаторской подписке секрет не утекает.
"""

from __future__ import annotations

import hmac
import json
from hashlib import sha256

import httpx
import pytest
from sqlalchemy import select

from app.core.secret_cipher import encrypt_secret
from app.models.models import Outbox, OutboxStatus, Tenant
from app.models.tenant_billing import WebhookSubscription
from app.services.outbox import OutboxProcessor
from app.services.webhooks import WebhookDispatcher

PLAINTEXT = "subscriber-plaintext-secret"


def _recording_dispatcher(requests: list[httpx.Request]) -> WebhookDispatcher:
    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204)

    from app.core.config import get_settings

    return WebhookDispatcher(
        settings=get_settings(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def _verify_signature(request: httpx.Request) -> bool:
    signature = request.headers.get("X-Signature", "").removeprefix("v1=")
    timestamp = request.headers.get("X-Timestamp", "")
    expected = hmac.new(
        PLAINTEXT.encode("utf-8"),
        f"{timestamp}.".encode("utf-8") + request.content,
        sha256,
    ).hexdigest()
    return bool(signature) and hmac.compare_digest(signature, expected)


async def _make_entry(session, tenant_id: str, *, url: str, headers: dict | None = None) -> Outbox:
    from datetime import datetime, timezone

    entry = Outbox(
        tenant_id=tenant_id,
        event_type="DocumentExported",
        destination=url,
        payload={"event_id": "evt-sign-1", "zip_storage_key": "s3/key"},
        headers=headers or {},
        status=OutboxStatus.PENDING,
        attempts=0,
        next_attempt_at=datetime.now(tz=timezone.utc),
    )
    session.add(entry)
    await session.commit()
    return entry


@pytest.mark.anyio
async def test_processor_delivery_is_signed_via_endpoint_id(sessionmaker) -> None:
    """Главный сценарий: id подписки в заголовках записи → подпись сходится."""

    requests: list[httpx.Request] = []
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        sub = WebhookSubscription(
            tenant_id=tenant.id,
            event_type="DocumentExported",
            url="https://example.test/hooks/signed",
            secret=encrypt_secret(PLAINTEXT),
            enabled=True,
        )
        session.add(sub)
        await session.flush()
        await _make_entry(
            session,
            tenant.id,
            url=sub.url,
            headers={"X-Webhook-Endpoint-Id": sub.id},
        )

        processor = OutboxProcessor(session, dispatcher=_recording_dispatcher(requests))
        processed = await processor.process_once()

    assert processed == 1
    assert len(requests) == 1
    assert _verify_signature(
        requests[0]
    ), "доставка через OutboxProcessor обязана быть подписана секретом подписки"


@pytest.mark.anyio
async def test_secret_is_found_by_url_when_headers_have_no_id(sessionmaker) -> None:
    """Записи, созданные до появления X-Webhook-Endpoint-Id, тоже подписываются."""

    requests: list[httpx.Request] = []
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        session.add(
            WebhookSubscription(
                tenant_id=tenant.id,
                event_type="DocumentExported",
                url="https://example.test/hooks/by-url",
                secret=encrypt_secret(PLAINTEXT),
                enabled=True,
            )
        )
        await session.flush()
        await _make_entry(session, tenant.id, url="https://example.test/hooks/by-url")

        processor = OutboxProcessor(session, dispatcher=_recording_dispatcher(requests))
        await processor.process_once()

    assert len(requests) == 1
    assert _verify_signature(requests[0])


@pytest.mark.anyio
async def test_destination_without_secret_still_delivers_unsigned(sessionmaker) -> None:
    """env-URL назначения секрета не имеют — доставка не должна падать."""

    requests: list[httpx.Request] = []
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        await _make_entry(session, tenant.id, url="https://example.test/hooks/no-secret")

        processor = OutboxProcessor(session, dispatcher=_recording_dispatcher(requests))
        processed = await processor.process_once()

    assert processed == 1
    assert len(requests) == 1
    assert "X-Signature" not in requests[0].headers


@pytest.mark.anyio
async def test_foreign_tenant_subscription_secret_is_not_used(sessionmaker, data_factory) -> None:
    """Подписка ЧУЖОГО арендатора с тем же URL не должна дать свой секрет."""

    requests: list[httpx.Request] = []
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        other = await data_factory.ensure_tenant(slug="other-hooks", session=session)
        session.add(
            WebhookSubscription(
                tenant_id=other.id,
                event_type="DocumentExported",
                url="https://example.test/hooks/foreign",
                secret=encrypt_secret("foreign-secret"),
                enabled=True,
            )
        )
        await session.flush()
        await _make_entry(session, tenant.id, url="https://example.test/hooks/foreign")

        processor = OutboxProcessor(session, dispatcher=_recording_dispatcher(requests))
        await processor.process_once()

    assert len(requests) == 1
    # Чужой секрет не подошёл — доставка ушла без подписи, а не с чужой.
    assert "X-Signature" not in requests[0].headers


@pytest.mark.anyio
async def test_foreign_tenant_endpoint_id_does_not_leak_secret(sessionmaker, data_factory) -> None:
    """CRITICAL из ревью: id ЧУЖОЙ подписки в заголовке НЕ должен дать её секрет.

    Заголовки Outbox формирует enqueue, но запись могла быть создана раньше или
    подделана — резолв по id обязан сверять арендатора, иначе секрет жертвы
    подписывает доставку на её URL под именем чужого арендатора.
    """

    requests: list[httpx.Request] = []
    async with sessionmaker() as session:
        attacker = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        victim = await data_factory.ensure_tenant(slug="victim-hooks", session=session)
        victim_sub = WebhookSubscription(
            tenant_id=victim.id,
            event_type="DocumentExported",
            url="https://victim.test/hooks/secret",
            secret=encrypt_secret("victim-secret"),
            enabled=True,
        )
        session.add(victim_sub)
        await session.flush()
        # Запись атакующего с ЧУЖИМ endpoint_id в заголовке.
        await _make_entry(
            session,
            attacker.id,
            url="https://victim.test/hooks/secret",
            headers={"X-Webhook-Endpoint-Id": victim_sub.id},
        )

        processor = OutboxProcessor(session, dispatcher=_recording_dispatcher(requests))
        await processor.process_once()

    assert len(requests) == 1
    # Секрет жертвы не использован — доставка ушла без подписи, а не с чужой.
    assert "X-Signature" not in requests[0].headers


@pytest.mark.anyio
async def test_disabled_subscription_does_not_sign(sessionmaker) -> None:
    """Отключённая подписка не должна подписывать (ветка по id раньше это игнорировала)."""

    requests: list[httpx.Request] = []
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        sub = WebhookSubscription(
            tenant_id=tenant.id,
            event_type="DocumentExported",
            url="https://example.test/hooks/disabled",
            secret=encrypt_secret(PLAINTEXT),
            enabled=False,
        )
        session.add(sub)
        await session.flush()
        await _make_entry(
            session, tenant.id, url=sub.url, headers={"X-Webhook-Endpoint-Id": sub.id}
        )

        processor = OutboxProcessor(session, dispatcher=_recording_dispatcher(requests))
        await processor.process_once()

    assert len(requests) == 1
    assert "X-Signature" not in requests[0].headers


@pytest.mark.anyio
async def test_wrong_event_type_subscription_does_not_sign(sessionmaker) -> None:
    """Подписка на ДРУГОЙ тип события не должна подписывать чужое событие."""

    requests: list[httpx.Request] = []
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        sub = WebhookSubscription(
            tenant_id=tenant.id,
            event_type="TrainingCompleted",  # не DocumentExported
            url="https://example.test/hooks/othertype",
            secret=encrypt_secret(PLAINTEXT),
            enabled=True,
        )
        session.add(sub)
        await session.flush()
        await _make_entry(
            session, tenant.id, url=sub.url, headers={"X-Webhook-Endpoint-Id": sub.id}
        )

        processor = OutboxProcessor(session, dispatcher=_recording_dispatcher(requests))
        await processor.process_once()

    assert "X-Signature" not in requests[0].headers


@pytest.mark.anyio
async def test_event_type_alias_is_signed(sessionmaker) -> None:
    """Подписка на алиас (Exported) обязана подписывать DocumentExported."""

    requests: list[httpx.Request] = []
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        session.add(
            WebhookSubscription(
                tenant_id=tenant.id,
                event_type="Exported",  # алиас DocumentExported
                url="https://example.test/hooks/alias",
                secret=encrypt_secret(PLAINTEXT),
                enabled=True,
            )
        )
        await session.flush()
        await _make_entry(session, tenant.id, url="https://example.test/hooks/alias")

        processor = OutboxProcessor(session, dispatcher=_recording_dispatcher(requests))
        await processor.process_once()

    assert len(requests) == 1
    assert _verify_signature(requests[0]), "подписка на алиас события должна подписываться"


@pytest.mark.anyio
async def test_global_subscription_signs_for_any_tenant(sessionmaker) -> None:
    """Глобальная подписка (tenant_id=NULL) с секретом подписывает доставку арендатора."""

    requests: list[httpx.Request] = []
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        session.add(
            WebhookSubscription(
                tenant_id=None,  # глобальная
                event_type="DocumentExported",
                url="https://example.test/hooks/global",
                secret=encrypt_secret(PLAINTEXT),
                enabled=True,
            )
        )
        await session.flush()
        await _make_entry(session, tenant.id, url="https://example.test/hooks/global")

        processor = OutboxProcessor(session, dispatcher=_recording_dispatcher(requests))
        await processor.process_once()

    assert len(requests) == 1
    assert _verify_signature(requests[0])


@pytest.mark.anyio
async def test_signature_uses_the_right_subscription_secret(sessionmaker, data_factory) -> None:
    """Подпись сходится ИМЕННО с секретом своей подписки, а не с чужой на том же URL.

    Свежая БД с одной подпиской не различала бы «правильный» и «любой» секрет —
    поэтому здесь ДВЕ подписки на один URL: чужая (её секрет не должен подойти)
    и своя (её секретом обязана считаться подпись).
    """

    requests: list[httpx.Request] = []
    async with sessionmaker() as session:
        mine = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        other = await data_factory.ensure_tenant(slug="other-secret", session=session)
        url = "https://example.test/hooks/shared"
        session.add_all(
            [
                WebhookSubscription(
                    tenant_id=other.id,
                    event_type="DocumentExported",
                    url=url,
                    secret=encrypt_secret("not-my-secret"),
                    enabled=True,
                ),
                WebhookSubscription(
                    tenant_id=mine.id,
                    event_type="DocumentExported",
                    url=url,
                    secret=encrypt_secret(PLAINTEXT),
                    enabled=True,
                ),
            ]
        )
        await session.flush()
        await _make_entry(session, mine.id, url=url)

        processor = OutboxProcessor(session, dispatcher=_recording_dispatcher(requests))
        await processor.process_once()

    assert len(requests) == 1
    # _verify_signature считает по PLAINTEXT — сходится только если взят МОЙ секрет.
    assert _verify_signature(requests[0])


@pytest.mark.anyio
async def test_retired_key_fails_closed_not_unsigned(sessionmaker, monkeypatch) -> None:
    """Отозванный ключ = не можем подписать → доставка FAILED (ретрай), а не тихо
    без подписи. Fail-open здесь означал бы вебхуки, которые подписчик отвергнет,
    но система считает доставленными (найдено ревью)."""

    from app.services import webhooks as webhooks_module

    requests: list[httpx.Request] = []
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        session.add(
            WebhookSubscription(
                tenant_id=tenant.id,
                event_type="DocumentExported",
                url="https://example.test/hooks/retired",
                secret=encrypt_secret(PLAINTEXT),
                enabled=True,
            )
        )
        await session.flush()
        entry = await _make_entry(session, tenant.id, url="https://example.test/hooks/retired")

        def _boom(_value):
            raise RuntimeError("key retired")

        monkeypatch.setattr(webhooks_module, "decrypt_secret", _boom)

        processor = OutboxProcessor(session, dispatcher=_recording_dispatcher(requests))
        await processor.process_once()

        await session.refresh(entry)

    # Доставка не выполнена: секрет расшифровать нельзя, отправлять неподписанное
    # нельзя. Запись НЕ помечена sent — уйдёт в ретрай.
    assert entry.status != OutboxStatus.SENT
    assert len(requests) == 0
