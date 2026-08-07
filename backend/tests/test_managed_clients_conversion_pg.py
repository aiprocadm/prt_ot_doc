"""BIZ-49 срез-14 — перевод Lightweight → Dedicated на живом PostgreSQL (RLS).

Регресс дефекта среза-13: фаза записи перевода шла через сессию ЗАПРОСА,
приколотую к арендатору аутсорсера, а bootstrap нового арендатора пишет строки
ЧУЖОГО tenant_id — под FORCE RLS их отвергает WITH CHECK. На SQLite (юниты)
это невидимо: RLS там не существует. Тест гоняет НАСТОЯЩИЙ маршрут на
непривилегированной роли БД (без SUPERUSER/BYPASSRLS) и живых сессиях
приложения: до починки падал, с _trusted_session — проходит.

Skips unless ``TEST_PG_ADMIN_URL`` is set.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.db

ADMIN_URL = os.environ.get("TEST_PG_ADMIN_URL")


def _sync_base() -> str:
    return ADMIN_URL.rsplit("/", 1)[0]


def _async_url(dbname: str, *, user: str | None = None, password: str | None = None) -> str:
    base = _sync_base().replace("postgresql://", "postgresql+asyncpg://", 1)
    if user is not None:
        # postgresql+asyncpg://user:pass@host:port
        scheme, rest = base.split("://", 1)
        hostpart = rest.split("@", 1)[1] if "@" in rest else rest
        base = f"{scheme}://{user}:{password}@{hostpart}"
    return f"{base}/{dbname}"


async def _admin_exec(dbname: str, sql: str) -> None:
    import asyncpg

    url = f"{_sync_base()}/{dbname}"
    conn = await asyncpg.connect(url)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


def _upgrade(dbname: str) -> None:
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    from app.core.config import get_settings

    os.environ["DATABASE_URL"] = _async_url(dbname)
    get_settings.cache_clear()
    repo_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(repo_root / "backend" / "app" / "migrations" / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "backend" / "app" / "migrations"))
    command.upgrade(cfg, "heads")


@pytest.mark.skipif(not ADMIN_URL, reason="set TEST_PG_ADMIN_URL to run the PG conversion guard")
def test_conversion_survives_force_rls_with_unprivileged_role(monkeypatch) -> None:
    from app.db import session as dbs

    dbname = f"mc_convert_{uuid.uuid4().hex[:12]}"
    probe_role = f"probe_{uuid.uuid4().hex[:8]}"
    original_url = os.environ.get("DATABASE_URL")

    async def _seed_and_convert() -> None:
        from sqlalchemy import select

        from app.api.routes import managed_clients as routes
        from app.domains.managed_clients.lifecycle import ContractStatus, ManagedClientMode
        from app.models.identity import RoleEnum
        from app.models.managed_clients import ManagedClient
        from app.models.master_data import Company
        from app.models.models import Tenant, User
        from app.schemas.managed_clients import ConvertToDedicated

        # Посев под админом (суперюзер обходит RLS — это только подготовка).
        admin_engine_url = _async_url(dbname)
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        admin_engine = create_async_engine(admin_engine_url)
        outsourcer_id = str(uuid.uuid4())
        client_id = None
        admin_id = None
        try:
            async with async_sessionmaker(admin_engine, expire_on_commit=False)() as s:
                s.add(
                    Tenant(
                        id=outsourcer_id,
                        slug="outsourcer",
                        code="outsourcer",
                        name="Аутсорсер",
                        schema_name="tenant_outsourcer",
                        contact_email="boss@outsourcer.ru",
                    )
                )
                await s.flush()
                company = Company(tenant_id=outsourcer_id, name="ООО Ромашка (клиент)")
                s.add(company)
                await s.flush()
                admin_user = User(
                    tenant_id=outsourcer_id,
                    email="boss@outsourcer.ru",
                    full_name="Босс Аутсорсера",
                    role=RoleEnum.ADMIN,
                    hashed_password="not-a-real-hash",
                )
                s.add(admin_user)
                await s.flush()
                admin_id = admin_user.id
                mc = ManagedClient(
                    tenant_id=outsourcer_id,
                    name="ООО Ромашка",
                    mode=ManagedClientMode.LIGHTWEIGHT,
                    company_id=company.id,
                    contract_status=ContractStatus.ACTIVE,
                )
                s.add(mc)
                await s.flush()
                client_id = mc.id
                await s.commit()
        finally:
            await admin_engine.dispose()

        # Глобальный движок приложения — НЕПРИВИЛЕГИРОВАННАЯ роль (как в проде
        # по SEC-65): и сессия запроса, и _trusted_session пойдут через неё.
        dbs._initialize_engine(
            _async_url(dbname, user=probe_role, password="probe-pass"), echo=False
        )

        monkeypatch.setattr(routes, "is_feature_enabled", AsyncMock(return_value=True))
        tenant_ns = SimpleNamespace(
            id=outsourcer_id, is_active=True, slug="outsourcer", code="outsourcer"
        )
        auth_ns = SimpleNamespace(
            sub=admin_id, tenant_id=outsourcer_id, roles=["admin"], company_id=None
        )
        request_ns = SimpleNamespace(
            headers={"user-agent": "tests"},
            client=SimpleNamespace(host="127.0.0.1"),
            state=SimpleNamespace(trace_id="trace-pg"),
        )

        # Сессия запроса — приколота к арендатору аутсорсера, RLS в силе.
        async with dbs.AsyncSessionLocal(
            tenant="outsourcer", include_public=True, create_schema=False
        ) as request_session:
            request_session.info["tenant_id"] = outsourcer_id
            await dbs.rearm_session_tenant_context(request_session)
            out = await routes.convert_to_dedicated(
                mcid=client_id,
                payload=ConvertToDedicated(
                    tenant_slug="romashka-dedicated",
                    owner_email="owner@romashka.ru",
                    owner_password="Secret123!",
                ),
                request=request_ns,
                tenant=tenant_ns,
                session=request_session,
                access=SimpleNamespace(),
                auth=auth_ns,
            )
        assert out.client.mode == ManagedClientMode.DEDICATED
        assert out.tenant_created, "bootstrap обязан отчитаться о созданном"

        # Проверка под админом: арендатор создан, владелец есть, клиент переведён.
        verify_engine = create_async_engine(admin_engine_url)
        try:
            async with async_sessionmaker(verify_engine, expire_on_commit=False)() as s:
                created = (
                    await s.execute(select(Tenant).where(Tenant.slug == "romashka-dedicated"))
                ).scalar_one()
                owner = (
                    (await s.execute(select(User).where(User.tenant_id == created.id)))
                    .scalars()
                    .first()
                )
                assert owner is not None and owner.email == "owner@romashka.ru"
                mc_row = (
                    await s.execute(select(ManagedClient).where(ManagedClient.id == client_id))
                ).scalar_one()
                assert mc_row.mode == ManagedClientMode.DEDICATED
                assert mc_row.dedicated_tenant_slug == "romashka-dedicated"
                assert mc_row.company_id is not None  # ссылка на историю жива
        finally:
            await verify_engine.dispose()

    async def _admin_root_exec(sql: str) -> None:
        import asyncpg

        conn = await asyncpg.connect(ADMIN_URL)
        try:
            await conn.execute(sql)
        finally:
            await conn.close()

    asyncio.run(_admin_root_exec(f'CREATE DATABASE "{dbname}"'))
    try:
        _upgrade(dbname)

        async def _probe_types() -> None:
            import asyncpg

            conn = await asyncpg.connect(f"{_sync_base()}/{dbname}")
            try:
                rows = await conn.fetch(
                    "select typname from pg_type where typname in ('tenantkind','managedclientmode')"
                )
                names = {r["typname"] for r in rows}
                assert "tenantkind" in names, f"после upgrade нет tenantkind: {names}"
            finally:
                await conn.close()

        asyncio.run(_probe_types())
        # Непривилегированная роль: NO superuser / NO bypassrls (SEC-65).
        asyncio.run(
            _admin_root_exec(
                f"CREATE ROLE \"{probe_role}\" LOGIN PASSWORD 'probe-pass' "
                "NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
            )
        )
        asyncio.run(
            _admin_exec(
                dbname,
                f'GRANT USAGE ON SCHEMA public TO "{probe_role}"; '
                f'GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO "{probe_role}"; '
                f'GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO "{probe_role}"; '
                # Как в проде (scripts/provision_app_role.py): CREATE на базе
                # нужен для создания схем арендаторов (ensure_tenant_schema),
                # к RLS это отношения не имеет.
                f'GRANT CREATE ON DATABASE "{dbname}" TO "{probe_role}";',
            )
        )
        asyncio.run(_seed_and_convert())
    finally:
        try:
            from app.core.config import get_settings

            if original_url is not None:
                os.environ["DATABASE_URL"] = original_url
            else:
                os.environ.pop("DATABASE_URL", None)
            get_settings.cache_clear()
            from app.db import session as dbs2

            if original_url is not None:
                dbs2._initialize_engine(original_url, echo=False)
        finally:
            asyncio.run(_admin_root_exec(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
            asyncio.run(_admin_root_exec(f'DROP ROLE IF EXISTS "{probe_role}"'))
