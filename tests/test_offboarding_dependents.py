"""Сторож: партнёр с живыми клиентами не уходит молча (OPS-72, срез-190).

ЧТО БЫЛО. Строка держала остаток «каскад по иерархии (BIZ-52)» — он ждал самой
иерархии. Иерархия появилась, и вопрос стал конкретным: что происходит с
клиентами, когда уходит ПАРТНЁР, который их привёл.

ДВА ПЛОХИХ ОТВЕТА И ОДИН ВЫБРАННЫЙ.

* Каскадно удалить клиентов — значит принять за них решение. Это самостоятельные
  организации со своими договорами и своими обязательствами по 152-ФЗ, а ошибка
  необратима: восстановить удалённое нечем.
* Молча разрешить — значит оставить клиентов сиротами: родитель, которого нет,
  наследование бренда в никуда, обращения некому.
* ВЫБРАНО: отказать и НАЗВАТЬ клиентов поимённо. Решение принимает человек.

ГЛАВНАЯ ТОНКОСТЬ, которую держит отдельная проверка: клиент, который САМ уже
уходит (в grace или удалён), не должен удерживать партнёра — иначе партнёр,
чьи клиенты ушли вместе с ним, не смог бы уйти никогда.

ЗАПУСК: ``PYTHONPATH=backend pytest tests/test_offboarding_dependents.py -v``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.models import Tenant
from app.models.offboarding import TenantOffboarding
from app.modules.offboarding.lifecycle import (
    DependentTenantsError,
    TenantOffboardingService,
    active_dependents,
)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


async def _tenant(session, *, slug: str, parent_id: str | None = None) -> Tenant:
    row = Tenant(
        id=str(uuid.uuid4()),
        code=slug,
        slug=slug,
        name=slug,
        contact_email=f"{slug}@example.test",
        parent_id=parent_id,
    )
    session.add(row)
    await session.flush()
    return row


@pytest.mark.asyncio
async def test_партнёр_без_клиентов_уходит_как_прежде(sessionmaker) -> None:
    async with sessionmaker() as session:
        partner = await _tenant(session, slug="partner-alone")
        service = TenantOffboardingService(
            session, tenant_id=str(partner.id), tenant_slug=partner.slug
        )
        record = await service.request(reason="закрываемся")
        assert record.status == "grace"


@pytest.mark.asyncio
async def test_партнёр_с_живыми_клиентами_получает_отказ_со_списком(sessionmaker) -> None:
    """«Нельзя» без списка означало бы искать клиентов вручную по всей базе."""

    async with sessionmaker() as session:
        partner = await _tenant(session, slug="partner-with-clients")
        await _tenant(session, slug="romashka", parent_id=str(partner.id))
        await _tenant(session, slug="vasilek", parent_id=str(partner.id))

        service = TenantOffboardingService(
            session, tenant_id=str(partner.id), tenant_slug=partner.slug
        )
        with pytest.raises(DependentTenantsError) as err:
            await service.request()
        assert set(err.value.slugs) == {"romashka", "vasilek"}
        assert "romashka" in str(err.value)


@pytest.mark.asyncio
async def test_клиент_который_сам_уходит_не_удерживает_партнёра(sessionmaker) -> None:
    """ГЛАВНАЯ ТОНКОСТЬ: иначе партнёр, чьи клиенты ушли вместе с ним, заперт навсегда."""

    async with sessionmaker() as session:
        partner = await _tenant(session, slug="partner-leaving")
        leaving = await _tenant(session, slug="leaving-client", parent_id=str(partner.id))
        session.add(
            TenantOffboarding(
                tenant_id=str(leaving.id),
                status="grace",
                requested_at=_now(),
                grace_days=30,
                grace_until=_now() + timedelta(days=30),
            )
        )
        await session.flush()

        assert await active_dependents(session, tenant_id=str(partner.id)) == []
        service = TenantOffboardingService(
            session, tenant_id=str(partner.id), tenant_slug=partner.slug
        )
        assert (await service.request()).status == "grace"


@pytest.mark.asyncio
async def test_удалённый_клиент_тоже_не_удерживает(sessionmaker) -> None:
    async with sessionmaker() as session:
        partner = await _tenant(session, slug="partner-purged-client")
        purged = await _tenant(session, slug="purged-client", parent_id=str(partner.id))
        session.add(
            TenantOffboarding(
                tenant_id=str(purged.id),
                status="purged",
                requested_at=_now(),
                grace_days=0,
                grace_until=_now(),
            )
        )
        await session.flush()
        assert await active_dependents(session, tenant_id=str(partner.id)) == []


@pytest.mark.asyncio
async def test_чужие_клиенты_не_считаются(sessionmaker) -> None:
    """Клиенты ДРУГОГО партнёра не должны мешать этому уйти."""

    async with sessionmaker() as session:
        partner = await _tenant(session, slug="partner-a")
        other = await _tenant(session, slug="partner-b")
        await _tenant(session, slug="client-of-b", parent_id=str(other.id))

        assert await active_dependents(session, tenant_id=str(partner.id)) == []
