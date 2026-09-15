"""Выключенный модуль замолкает и в фоне (SEC-63 разд. 63.3, срез-205).

Реестр хозяев обходов проверяется без базы в ``tests/test_task_module_scope.py``.
Здесь — МЕСТО ПОДКЛЮЧЕНИЯ: что проверка действительно стоит внутри обхода и
действительно смотрит в выдачу модуля.

Урок среза-187 записан кровью: тесты шва не заменяют теста места подключения.
Реестр может быть безупречен, а в самом обходе проверки не окажется — и всё
останется зелёным.

ЗАПУСК: ``PYTHONPATH=backend pytest tests/test_task_module_gate_live.py -v``.
"""

from __future__ import annotations

import pytest

from app.core.feature_flags import is_module_enabled
from app.tasks._shared import task_module_is_on


@pytest.mark.anyio
async def test_модульный_обход_молчит_у_арендатора_без_модуля(sessionmaker, data_factory) -> None:
    """ГЛАВНАЯ ПРОВЕРКА СРЕЗА.

    До него ``contractors.readiness.tick`` слал уведомления и пересобирал
    витрину у КАЖДОГО активного арендатора — в том числе у того, кому модуль
    «Подрядчики» не продавали.
    """

    from sqlalchemy import select

    from app.models.feature import Feature, FeatureEnablement

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await session.commit()
        tenant_id = str(tenant.id)

        # Арендатору из фикстуры выданы все модули, поэтому выключаем нужный
        # ЯВНО: иначе проверялась бы фикстура, а не шлюз.
        feature = await session.scalar(select(Feature).where(Feature.code == "contractors"))
        if feature is None:
            feature = Feature(code="contractors", title="Подрядчики")
            session.add(feature)
            await session.flush()
        row = await session.scalar(
            select(FeatureEnablement).where(
                FeatureEnablement.tenant_id == tenant_id,
                FeatureEnablement.feature_id == feature.id,
            )
        )
        if row is None:
            session.add(FeatureEnablement(tenant_id=tenant_id, feature_id=feature.id, on=False))
        else:
            row.on = False
            row.expires_at = None
        await session.commit()

        assert await is_module_enabled(session, tenant_id, "contractors") is False
        assert await task_module_is_on(session, tenant_id, "contractors.readiness.tick") is False


@pytest.mark.anyio
async def test_ядровой_обход_работает_всегда(sessionmaker, data_factory) -> None:
    """Иначе выключение модуля глушило бы доставку уведомлений всей платформы."""

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await session.commit()

        assert (
            await task_module_is_on(session, str(tenant.id), "notifications.dispatch_pending")
            is True
        )


@pytest.mark.anyio
async def test_проверка_стоит_внутри_самих_обходов(sessionmaker, data_factory) -> None:
    """РАЗБОР ПО КОДУ, а не по тексту: у каждого модульного обхода в теле
    действительно вызывается ``task_module_is_on`` со СВОИМ именем задачи.

    Без этого реестр остался бы декларацией: запись есть, проверки нет.
    """

    import ast
    import inspect

    from app.tasks import _core, domain_ticks
    from app.tasks.module_scope import TASK_MODULE

    gated: set[str] = set()
    for module in (domain_ticks, _core):
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name != "task_module_is_on":
                continue
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    gated.add(arg.value)

    missing = sorted(set(TASK_MODULE) - gated)
    assert not missing, (
        "у этих обходов запись в реестре есть, а проверки в теле НЕТ:\n  " + "\n  ".join(missing)
    )
