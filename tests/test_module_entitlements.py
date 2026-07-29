"""SEC-63 (разд. 63.3): модульный доступ как поверхность атаки.

ТЗ: «Модульный доступ (Доп. №2, разд. 61) сам может стать вектором, если сделан
только на фронте». Три риска и что здесь закрепляется:

* **обход через прямой API** — выключенный модуль обязан отвечать 404 не только в
  интерфейсе, но и на прямой вызов; ратчет-гард требует backend-гейт у каждого
  модуля каталога, чтобы девятый модуль не появился без него;
* **эскалация через зависимости** — зависимостей между модулями сейчас нет, и гард
  падает, если они появятся: решение об их обработке надо принять осознанно;
* **осиротевшие доступы** — правила автоматизации не срабатывают при выключенном
  модуле (проверка идёт в момент исполнения, а не только при создании правила).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature import Feature, FeatureEnablement
from app.models.models import RoleEnum
from app.modules.subscription.plans import FEATURE_CATALOG

REPO_ROOT = Path(__file__).resolve().parents[1]
API_PREFIX = "/api/v1"


def _load_guard():
    path = REPO_ROOT / "scripts" / "ci" / "check_module_gates.py"
    spec = importlib.util.spec_from_file_location("check_module_gates", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_catalogued_module_has_a_backend_gate() -> None:
    assert _load_guard().main([]) == 0


def test_guard_catches_a_module_without_a_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Гард, который всегда возвращает 0, выглядел бы рабочим и защищал бы ноль."""

    guard = _load_guard()
    monkeypatch.setattr(
        guard, "_catalog", lambda: {**FEATURE_CATALOG, "totally_new_module": "Новый"}
    )
    assert guard.main([]) == 1


def test_guard_catches_newly_introduced_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    guard = _load_guard()
    monkeypatch.setattr(
        guard, "_catalog_dependencies", lambda: {"FEATURE_DEPENDS_ON": {"budget": ["sout"]}}
    )
    assert guard.main([]) == 1


def test_catalog_has_no_inter_module_dependencies() -> None:
    """Пока зависимостей нет, риск «эскалация через зависимости» неприменим."""

    assert _load_guard()._catalog_dependencies() == {}


async def _disable_module(session: AsyncSession, tenant_id: str, code: str) -> None:
    feature = (
        await session.execute(select(Feature).where(Feature.code == code))
    ).scalar_one_or_none()
    if feature is None:
        feature = Feature(code=code, title=FEATURE_CATALOG.get(code, code))
        session.add(feature)
        await session.flush()
    existing = (
        await session.execute(
            select(FeatureEnablement).where(
                FeatureEnablement.tenant_id == tenant_id,
                FeatureEnablement.feature_id == feature.id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(FeatureEnablement(tenant_id=tenant_id, feature_id=feature.id, on=False))
    else:
        existing.on = False
    await session.commit()


@pytest.mark.anyio
class TestDirectApiBypass:
    async def test_disabled_module_is_closed_for_direct_api_calls(
        self, async_client, make_auth_headers, sessionmaker, data_factory
    ) -> None:
        """Главный риск разд. 63.3: модуль убран из интерфейса, но жив по API."""

        headers = await make_auth_headers(RoleEnum.ADMIN)
        tenant_id = headers.get("x-tenant") or headers.get("X-Tenant")

        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(slug=tenant_id, session=session)
            await _disable_module(session, str(tenant.id), "contractors")

        response = await async_client.get(f"{API_PREFIX}/contractors", headers=headers)
        assert response.status_code == 404, response.text
