"""SEC-64, разд. 64.1: метка сессии из заголовка запроса — проверка НА ЖИВОЙ БАЗЕ.

Дефект среза-210: ``application_name`` собирался в текст SQL из значения
заголовка ``X-Correlation-Id``, а «обезвреживание» снимало двойную кавычку,
хотя строка стояла в одинарных. На SQLite этого не увидеть вовсе — путь
включается только на PostgreSQL, поэтому проверка живая и пропускается без
``TEST_PG_ADMIN_URL``.

Проверяется ПОВЕДЕНИЕ, а не наличие строк в коде:

1. старая склейка на враждебном значении ПАДАЕТ — то есть дефект был настоящий,
   а не придуманный (доказательство поломкой прямо в тесте);
2. новый запрос с параметром проходит, и опасные знаки лежат в метке ОБЫЧНЫМ
   ТЕКСТОМ, ничего не исполняя.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.sql_text import session_label_params, session_label_statement

ADMIN_URL = os.environ.get("TEST_PG_ADMIN_URL")

#: Значение, которое может прийти в заголовке запроса от кого угодно.
HOSTILE = "trace'; SELECT pg_sleep(0) --"

pytestmark = pytest.mark.skipif(
    not ADMIN_URL,
    reason="нужен TEST_PG_ADMIN_URL: метка сессии живёт только на PostgreSQL",
)


def _async_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


@pytest.mark.asyncio
async def test_старая_склейка_падает_на_враждебной_метке() -> None:
    """Доказательство поломкой: так, как было, запрос ломается."""

    engine = create_async_engine(_async_url(ADMIN_URL or ""))
    try:
        # Ровно прежний код: снимался только двойной знак кавычки.
        broken = HOSTILE.replace('"', "")
        async with engine.connect() as conn:
            with pytest.raises(Exception):
                await conn.execute(text(f"SET LOCAL application_name TO 'api:{broken}'"))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_метка_с_кавычкой_сохраняется_как_обычный_текст() -> None:
    engine = create_async_engine(_async_url(ADMIN_URL or ""))
    try:
        async with engine.connect() as conn:
            await conn.execute(session_label_statement(), session_label_params(HOSTILE))
            stored = (await conn.execute(text("SHOW application_name"))).scalar()
            await conn.rollback()
    finally:
        await engine.dispose()

    # Знаки на месте и ничего не исполнилось: значение осталось значением.
    assert stored == f"api:{HOSTILE}"


@pytest.mark.asyncio
async def test_схема_арендатора_с_дефисом_живёт() -> None:
    """Проверка формата имён не должна ронять настоящих арендаторов.

    Слаг описан как ``[a-z][a-z0-9_-]``, схема зовётся ``tenant_<слаг>``.
    Первая версия проверки дефис запрещала — такой арендатор падал бы на каждом
    запросе. Здесь это проверено на живой базе, а не рассуждением.
    """

    from app.core.sql_text import quote_identifier

    schema = "tenant_probe-210"
    quoted = quote_identifier(schema, source="проверка")
    engine = create_async_engine(_async_url(ADMIN_URL or ""))
    try:
        async with engine.connect() as conn:
            await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {quoted}"))
            await conn.execute(text(f"SET search_path TO {quoted}"))
            active = (await conn.execute(text("SHOW search_path"))).scalar()
            await conn.execute(text(f"DROP SCHEMA {quoted}"))
            await conn.commit()
    finally:
        await engine.dispose()

    assert schema in str(active)
