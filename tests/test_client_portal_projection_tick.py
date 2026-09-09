"""Снимок кабинета клиента пересобирается ночью (BIZ-54-57 срез-128).

ЗАЧЕМ. Кабинет клиента (`/portal/dashboard`, `/portal/packages`) читает
ТОЛЬКО снимок ``client_portal_read_models`` — живого запроса к пакетам у него
нет. Пересобирала снимок одна Celery-задача, которую не звал никто: ни
расписание, ни ручка. То есть заказчик видел пустой кабинет, а выглядело это
как «подрядчик ничего не сделал».

Срез-97 вытащил из ровно того же положения три соседние проекции и этот
снимок не тронул. Сторож против третьего раза —
``tests/test_projection_rebuild_schedule.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.models import ClientPackagePreset, ClientPackageRun, PackageRunStatus
from app.modules.projections.models import ClientPortalReadModel

pytestmark = pytest.mark.anyio


async def test_ночной_тик_наполняет_кабинет_клиента(sessionmaker, data_factory) -> None:
    """Раньше строка кабинета появлялась только после ручного запуска задачи."""

    from app.tasks._core import _analytics_projections_tick

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(slug="test", session=session)
        preset = ClientPackagePreset(
            tenant_id=tenant.id,
            code="OUT_TO_SITE",
            name="Выход на объект",
            steps_json={},
            required_inputs_json=[],
        )
        session.add(preset)
        await session.flush()
        run = ClientPackageRun(
            tenant_id=tenant.id, preset_id=preset.id, status=PackageRunStatus.RUNNING
        )
        session.add(run)
        await session.commit()
        tenant_id = str(tenant.id)
        run_id = str(run.id)

    await _analytics_projections_tick()

    async with sessionmaker() as session:
        row = (
            await session.execute(
                select(ClientPortalReadModel).where(
                    ClientPortalReadModel.tenant_id == tenant_id,
                    ClientPortalReadModel.package_id == run_id,
                )
            )
        ).scalar_one()
    assert row.item_type == "package"
    assert str(PackageRunStatus.RUNNING.value) in str(row.status)


async def test_пересборка_не_падает_на_прогоне_пакета(sessionmaker, data_factory) -> None:
    """Раньше ночной тик умирал на первом же прогоне пакета.

    Проекция пакетов читала ``run.progress_percent`` — поля, которого у
    прогона нет. Ошибка обрывала ВЕСЬ тик, поэтому вместе с пакетами
    переставали пересобираться соответствие по людям и площадки. Прежний тест
    тика этого не видел: у его арендатора прогонов пакетов не было.
    """

    from app.modules.projections.models import PackageReadModel
    from app.tasks._core import _analytics_projections_tick

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(slug="test", session=session)
        preset = ClientPackagePreset(
            tenant_id=tenant.id,
            code="OUT_TO_SITE",
            name="Выход на объект",
            steps_json={},
            required_inputs_json=[],
        )
        session.add(preset)
        await session.flush()
        running = ClientPackageRun(
            tenant_id=tenant.id, preset_id=preset.id, status=PackageRunStatus.RUNNING
        )
        done = ClientPackageRun(
            tenant_id=tenant.id,
            preset_id=preset.id,
            status=PackageRunStatus.SUCCESS,
            finished_at=datetime.now(tz=timezone.utc),
        )
        session.add_all([running, done])
        await session.commit()
        tenant_id = str(tenant.id)
        running_id, done_id = str(running.id), str(done.id)

    await _analytics_projections_tick()

    async with sessionmaker() as session:
        rows = {
            str(row.package_id): row
            for row in (
                (
                    await session.execute(
                        select(PackageReadModel).where(PackageReadModel.tenant_id == tenant_id)
                    )
                )
                .scalars()
                .all()
            )
        }
    # Промежуточных процентов у прогона взять неоткуда: достоверно известно
    # только «завершён / не завершён».
    assert float(rows[running_id].progress_percent) == 0
    assert float(rows[done_id].progress_percent) == 100
