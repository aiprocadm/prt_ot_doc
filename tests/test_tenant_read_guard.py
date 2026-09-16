"""SEC-64, разд. 64.1, строка «Broken Access Control»: рубеж на чтение чужой строки.

Требование ТЗ дословно: «IDOR на ВСЕХ ``/{id}``-роутах; cross-tenant deny».
Слово ВСЕХ проверяется обходом, и обход показал: почти каждая из 244 ручек,
достающих объект по номеру, привязывает его к арендатору САМА. Защита, которую
надо повторить 244 раза, держится на памяти автора.

Здесь проверяется второй рубеж — тот, что работает независимо от памяти: для
сессии одного арендатора строки другого НЕ СУЩЕСТВУЕТ. Проверяется ПОВЕДЕНИЕМ
(настоящая загрузка из базы), а не наличием строк в коде.

ПОЧЕМУ «НЕ СУЩЕСТВУЕТ», А НЕ «ЗАПРЕЩЕНО» — решение, поймавшееся прогоном: ответ
«нет доступа» сам подтверждает, что объект с таким номером есть, а ручка со
своей проверкой отвечает точнее общего отказа.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.tenant_read_guard import CROSS_TENANT_READ_KEY, allow_cross_tenant_read
from app.models.models import AuditLog, Tenant


async def _tenant_ids(session) -> tuple[str, str]:
    rows = (
        await session.execute(select(Tenant).where(Tenant.slug.in_(["acme", "beta"])))
    ).scalars()
    by_slug = {row.slug: str(row.id) for row in rows}
    return by_slug["acme"], by_slug["beta"]


async def _make_audit_row(sessionmaker, tenant_id: str, marker: str) -> str:
    async with sessionmaker() as session:
        row = AuditLog(tenant_id=tenant_id, action="probe", object_type="guard", object_id=marker)
        session.add(row)
        await session.commit()
        return str(row.id)


@pytest.mark.anyio
async def test_чужой_строки_для_арендатора_не_существует(sessionmaker) -> None:
    """ГЛАВНОЕ. Номер объекта подобран снаружи — объекта просто нет."""

    async with sessionmaker() as session:
        acme, beta = await _tenant_ids(session)
    row_id = await _make_audit_row(sessionmaker, acme, "read-guard-acme")

    async with sessionmaker() as session:
        # Сессия работает от имени ДРУГОГО арендатора и фильтр «забыт».
        session.info["tenant_id"] = beta
        assert await session.get(AuditLog, row_id) is None


@pytest.mark.anyio
async def test_список_без_фильтра_не_подмешивает_чужое(sessionmaker) -> None:
    """Рубеж шире, чем IDOR: он ловит и забытый фильтр в СПИСКЕ.

    Ручка, которая перечисляет объекты без условия по арендатору, выглядит
    работающей и молча отдаёт чужие строки вперемешку со своими.
    """

    async with sessionmaker() as session:
        acme, beta = await _tenant_ids(session)
    await _make_audit_row(sessionmaker, acme, "read-guard-list-acme")
    await _make_audit_row(sessionmaker, beta, "read-guard-list-beta")

    async with sessionmaker() as session:
        session.info["tenant_id"] = beta
        rows = (await session.execute(select(AuditLog))).scalars().all()

    markers = {row.object_id for row in rows}
    assert "read-guard-list-beta" in markers
    assert "read-guard-list-acme" not in markers


@pytest.mark.anyio
async def test_своя_строка_выдаётся(sessionmaker) -> None:
    """Сторож не должен мешать обычной работе: своё читается как раньше."""

    async with sessionmaker() as session:
        acme, _beta = await _tenant_ids(session)
    row_id = await _make_audit_row(sessionmaker, acme, "read-guard-own")

    async with sessionmaker() as session:
        session.info["tenant_id"] = acme
        row = await session.get(AuditLog, row_id)

    assert row is not None
    assert row.object_id == "read-guard-own"


@pytest.mark.anyio
async def test_явное_разрешение_показывает_чужое(sessionmaker) -> None:
    """Законное чтение чужого есть — управляющий арендатор ведёт клиентов.

    Оно разрешается ЯВНО и с причиной, а не молчаливым исключением.
    """

    async with sessionmaker() as session:
        acme, beta = await _tenant_ids(session)
    row_id = await _make_audit_row(sessionmaker, acme, "read-guard-allowed")

    async with sessionmaker() as session:
        session.info["tenant_id"] = beta
        with allow_cross_tenant_read(session, reason="партнёр смотрит данные своего клиента"):
            row = await session.get(AuditLog, row_id)

    assert row is not None
    assert row.object_id == "read-guard-allowed"


@pytest.mark.anyio
async def test_после_разрешения_рубеж_возвращается(sessionmaker) -> None:
    """Разрешение действует только внутри своего куска работы."""

    async with sessionmaker() as session:
        acme, beta = await _tenant_ids(session)
    row_id = await _make_audit_row(sessionmaker, acme, "read-guard-scope")

    async with sessionmaker() as session:
        session.info["tenant_id"] = beta
        with allow_cross_tenant_read(session, reason="партнёр смотрит данные своего клиента"):
            await session.get(AuditLog, row_id)
        assert CROSS_TENANT_READ_KEY not in session.info
        session.expunge_all()
        assert await session.get(AuditLog, row_id) is None


def test_разрешение_без_причины_не_принимается() -> None:
    """«Надо» — не причина: через полгода такое разрешение никто не снимет."""

    class _FakeSession:
        info: dict[str, object] = {}

    with pytest.raises(ValueError):
        with allow_cross_tenant_read(_FakeSession(), reason="надо"):
            pass


@pytest.mark.anyio
async def test_служебная_сессия_без_арендатора_не_трогается(sessionmaker) -> None:
    """Миграции, управление арендаторами и настройка читают без арендатора.

    Запрещать там значило бы сломать работу, к данным арендаторов отношения не
    имеющую.
    """

    async with sessionmaker() as session:
        acme, _beta = await _tenant_ids(session)
    row_id = await _make_audit_row(sessionmaker, acme, "read-guard-service")

    async with sessionmaker() as session:
        assert "tenant_id" not in session.info
        row = await session.get(AuditLog, row_id)

    assert row is not None
