"""BIZ-61 (Доп. №2 разд. 61.2): безопасное выключение — данные в read-only.

ТЗ: «отключение модуля не удаляет данные — они переходят в read-only …;
при повторном включении всё возвращается». До этого среза выключенный модуль
отдавал 404 на ВСЁ: заказчик, переставший платить за модуль, терял доступ к
СВОИМ накопленным данным — а журналы медосмотров и выдач СИЗ нужны при
проверке ГИТ независимо от подписки.

Три исхода гейта (каждый доказан на живом API):

* модуль **включён** → работает как раньше;
* модуль **был выдан и отключён** (строка выдачи ``on=False`` или истёкшая) →
  чтение проходит, мутации — 403 ``MODULE_READ_ONLY`` СЛОВАМИ (объяснение,
  а не маскировка);
* модуль **никогда не выдавался** → прежний 404: существование модуля у
  арендатора не подтверждается (принцип 404-не-403, SEC-63).

Отдельно закреплено: у модулей ЯДРА read-only-режима нет — ядро выключается
только аварийной записью ``on=False``, и аварийное «закрыто» закрывает целиком.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.feature import Feature, FeatureEnablement
from app.models.models import Tenant

pytestmark = pytest.mark.anyio

_CODE = "medical"
# ГЕЙТЯЩИЙСЯ GET: список отстранений (у GET /medical/exams гейта нет вовсе —
# попутная находка среза, записана в PR).
_LIST = "/api/v1/medical/suspensions"


async def _set_grant(sessionmaker, tenant_slug: str, code: str, on: bool) -> None:
    """Создать/обновить строку выдачи модуля напрямую в базе."""

    async with sessionmaker() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))
        ).scalar_one()
        feature = (
            await session.execute(select(Feature).where(Feature.code == code))
        ).scalar_one_or_none()
        if feature is None:
            feature = Feature(code=code, title=code)
            session.add(feature)
            await session.flush()
        grant = (
            await session.execute(
                select(FeatureEnablement).where(
                    FeatureEnablement.tenant_id == tenant.id,
                    FeatureEnablement.feature_id == feature.id,
                )
            )
        ).scalar_one_or_none()
        if grant is None:
            grant = FeatureEnablement(tenant_id=tenant.id, feature_id=feature.id, on=on)
            session.add(grant)
        else:
            grant.on = on
        await session.commit()


async def _drop_grant(sessionmaker, tenant_slug: str, code: str) -> None:
    async with sessionmaker() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))
        ).scalar_one()
        feature = (
            await session.execute(select(Feature).where(Feature.code == code))
        ).scalar_one_or_none()
        if feature is None:
            return
        grant = (
            await session.execute(
                select(FeatureEnablement).where(
                    FeatureEnablement.tenant_id == tenant.id,
                    FeatureEnablement.feature_id == feature.id,
                )
            )
        ).scalar_one_or_none()
        if grant is not None:
            await session.delete(grant)
            await session.commit()


class TestБезопасноеВыключение:
    async def test_никогда_не_выдавался_прежний_404(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _drop_grant(sessionmaker, "test", _CODE)

        response = await async_client.get(_LIST, headers=headers)
        assert response.status_code == 404

        # SEC-63 срез (разд. 61.3): бывшие дыры «обход через прямой API»
        # закрыты роутерными гейтами — без выдачи модуля невидимы и они.
        exams = await async_client.get("/api/v1/medical/exams", headers=headers)
        assert exams.status_code == 404, exams.text

        await _drop_grant(sessionmaker, "test", "contractors")
        registry = await async_client.get("/api/v1/contractors/registry", headers=headers)
        assert registry.status_code == 404, registry.text

    async def test_отключённый_читается_а_мутация_объяснена_словами(
        self, async_client, make_auth_headers, sessionmaker, data_factory
    ) -> None:
        headers = await make_auth_headers()
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session)
            company = await data_factory.create_company(tenant=tenant, session=session)
            person = await data_factory.create_person(
                tenant=tenant,
                company=company,
                session=session,
                first_name="Марк",
                last_name="Лев",
            )
            await session.commit()
            pid = person.id

        def exam_body(day: str) -> dict:
            return {
                "person_id": pid,
                "exam_kind": "periodic",
                "exam_date": day,
                "fitness": "fit",
                "medical_org_name": "МЦ № 1",
            }

        # Модуль был выдан и накопил данные…
        await _set_grant(sessionmaker, "test", _CODE, on=True)
        created = await async_client.post(
            "/api/v1/medical/exams", json=exam_body("2026-03-01"), headers=headers
        )
        assert created.status_code in (200, 201), created.text

        # …потом его отключили (кончилась подписка на модуль).
        await _set_grant(sessionmaker, "test", _CODE, on=False)

        read = await async_client.get(_LIST, headers=headers)
        assert read.status_code == 200, read.text

        write = await async_client.post(
            "/api/v1/medical/exams", json=exam_body("2026-04-01"), headers=headers
        )
        assert write.status_code == 403, write.text
        assert "MODULE_READ_ONLY" in write.text
        assert "только для чтения" in write.text

        # При повторном включении всё возвращается.
        await _set_grant(sessionmaker, "test", _CODE, on=True)
        again = await async_client.post(
            "/api/v1/medical/exams", json=exam_body("2026-05-01"), headers=headers
        )
        assert again.status_code in (200, 201), again.text

    async def test_у_ядра_read_only_режима_нет(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Аварийное «закрыто» ядра закрывает целиком: явная запись on=False
        у модуля ядра даёт 404 и на чтение — прежний аварийный выключатель."""

        headers = await make_auth_headers()
        await _set_grant(sessionmaker, "test", "imports", on=False)
        try:
            response = await async_client.get("/api/v1/imports/positions/jobs", headers=headers)
            assert response.status_code == 404, response.text
        finally:
            await _drop_grant(sessionmaker, "test", "imports")
