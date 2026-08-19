"""Движок, закрытый после теста, не должен оставаться в памяти вместе с диалектом.

Зачем этот тест. ``app_fixture`` создаёт отдельный движок на каждый тест — это
и даёт изоляцию. Но у КАЖДОГО ORM-маппера есть свой кэш скомпилированных
запросов (``Mapper._compiled_cache``, до 100 записей), а ключ такой записи
содержит диалект движка. Мапперы живут всё время процесса (это атрибуты классов
моделей), поэтому каждый закрытый движок оседал в них навсегда — вместе со
своим кэшем адаптированных типов (~120 ``Enum`` на диалект).

Замерено на полном прогоне: воркер xdist разрастался до 8-11 ГБ, машина уходила
в OOM. Тест сторожит, что закрытый движок действительно отпускается.
"""

from __future__ import annotations

import gc
import os
import tempfile
import weakref

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base, SharedBase
from app.models.models import Tenant
from tests.conftest import _prepare_sqlite_metadata
from tests.utils.engine_cleanup import release_mapper_query_caches


async def _run_engine_lifecycle(db_file: str) -> weakref.ref:
    """Полный цикл жизни тестового движка внутри отдельного кадра.

    Всё — движок, соединение, сессия — остаётся локальным для этой функции,
    поэтому после выхода из неё ни одна временная ссылка не удерживает движок
    искусственно. Возвращаем слабую ссылку на диалект: она не мешает сборке.
    """

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(SharedBase.metadata.create_all)
        await conn.run_sync(Base.metadata.create_all)

    # ORM-запись и чтение наполняют Mapper._compiled_cache ключами,
    # в которые входит диалект этого движка.
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_maker() as session:
        session.add(Tenant(slug="memcheck", name="Memcheck", contact_email="m@example.com"))
        await session.commit()
        await session.execute(select(Tenant))

    dialect_ref = weakref.ref(engine.sync_engine.dialect)
    await engine.dispose()
    return dialect_ref


async def test_disposed_engine_dialect_is_released() -> None:
    """После ``dispose()`` диалект движка не должен удерживаться кэшами мапперов."""

    _prepare_sqlite_metadata()

    db_fd, db_file = tempfile.mkstemp(prefix="prt_mem_test_", suffix=".db")
    os.close(db_fd)
    try:
        dialect_ref = await _run_engine_lifecycle(db_file)

        release_mapper_query_caches()
        gc.collect()

        assert dialect_ref() is None, (
            "Диалект закрытого движка остался в памяти. Обычная причина — кэш "
            "скомпилированных запросов у мапперов (Mapper._compiled_cache): ключи "
            "в нём содержат диалект, а мапперы живут всё время процесса. "
            "Очищайте эти кэши при закрытии тестового движка."
        )
    finally:
        if os.path.exists(db_file):
            os.remove(db_file)
