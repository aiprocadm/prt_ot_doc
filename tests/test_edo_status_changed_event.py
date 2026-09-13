"""Срез-158: событие «статус в ЭДО изменился» рождается там, где статус меняется.

ЧТО БЫЛО. Оператор ЭДО присылает вебхук, обработчик меняет статус сообщения,
пишет историю и запись в журнал — и на этом всё. В ленту событий не уходило
ничего. А само событие ``edo.status_changed`` в ленте было: его клала задача
индексации файла с пометкой «FileIndexed». Получалось наоборот: правило
«когда изменился статус в ЭДО» срабатывало на разбор содержимого файла и
молчало на настоящую смену статуса.

ЗАЧЕМ ТЕСТ. Правила проверяются прямо внутри записи в ленту
(``OutboxService.enqueue``), поэтому «нет записи в ленте» = «правило никогда
не сработает». Сторож держит обе стороны: событие есть у вебхука и его нет у
индексации файла.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select

from app.models.models import EdoDirection, EdoMessage, EdoStatus, Outbox, Tenant
from app.tasks import _core as task_core


@pytest.fixture(autouse=True)
def _tasks_use_test_session(monkeypatch: pytest.MonkeyPatch, sessionmaker) -> None:
    """Задача ходит в базу сама — подменяем её сессию на тестовую."""

    @asynccontextmanager
    async def _scope(*, tenant: str | None = None):
        async with sessionmaker() as session:
            session.info["tenant"] = tenant or "test"
            # Боевая сессия кладёт сюда id арендатора: по нему задача и ищет
            # свои записи. Без него поиск идёт по slug и не находит ничего.
            session.info["tenant_id"] = await _tenant_id(sessionmaker)
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    monkeypatch.setattr(task_core, "session_scope", _scope)
    monkeypatch.setattr(task_core, "ensure_tenant_schema", lambda slug: None)


async def _tenant_id(sessionmaker) -> str:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        return str(tenant.id)


@pytest.mark.asyncio
async def test_смена_статуса_в_эдо_попадает_в_ленту_событий(sessionmaker) -> None:
    tenant_id = await _tenant_id(sessionmaker)
    async with sessionmaker() as session:
        message = EdoMessage(
            tenant_id=tenant_id,
            direction=EdoDirection.OUTGOING,
            provider_code="demo-operator",
            external_id="ext-slice-158",
            status=EdoStatus.QUEUED,
        )
        session.add(message)
        await session.commit()
        message_id = message.id

    processed = await task_core._process_inbound_webhook(
        source="edo",
        tenant_slug="test",
        payload={
            "provider_code": "demo-operator",
            "external_id": "ext-slice-158",
            "status": "delivered",
            "event_id": "evt-slice-158",
        },
    )
    assert processed == 1

    async with sessionmaker() as session:
        rows = (
            (await session.execute(select(Outbox).where(Outbox.event_type == "edo.status_changed")))
            .scalars()
            .all()
        )
    assert rows, "смена статуса в ЭДО не попала в ленту — правило по ней не сработает"
    payloads = [row.payload for row in rows]
    assert any(
        (p.get("metadata") or {}).get("edo_message_id") == message_id
        and (p.get("metadata") or {}).get("status") == "delivered"
        for p in payloads
    ), f"в ленте нет записи про это сообщение и этот статус: {payloads}"


@pytest.mark.asyncio
async def test_индексация_файла_не_притворяется_событием_эдо() -> None:
    """Пометка «FileIndexed» под видом события ЭДО не должна вернуться."""

    import inspect

    from app.tasks import file_jobs

    source = inspect.getsource(file_jobs)
    live = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    assert "EDO_STATUS_CHANGED" not in live, (
        "задача индексации файла снова публикует событие ЭДО — "
        "правило «изменился статус в ЭДО» будет срабатывать на чужое действие"
    )
    assert "FileIndexed" not in live
