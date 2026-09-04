"""Открытые происшествия контура в сводке дисциплины (срез-49).

Доп. №1 разд. 57.4: экран каждой дисциплины — её операционный дашборд. До
этого среза происшествий на нём не было вовсе, хотя разметка есть с
среза-44. Здесь проверяется, что каждая из пяти сводок ``/readiness``
отдаёт ``incidents_open`` и что число это:

- считает ТОЛЬКО свою дисциплину: чужие и неразмеченные не попадают
  (контур не угадывает дисциплину по типу события);
- считает ТОЛЬКО открытые: закрытое, отменённое и удалённое — нет;
- совпадает с разрезом «по дисциплинам» у директора — формула одна
  (``app.services.discipline_incidents``), тест держит их вместе.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.core.disciplines import Discipline
from app.models.feature import Feature, FeatureEnablement
from app.models.models import Company, Incident, IncidentStatus, RoleEnum, Site
from tests.utils.factories import TestDataFactory

NOW = datetime.now(tz=timezone.utc)
BREAKDOWN = "/api/v1/analytics/dashboard/breakdown?dimension=discipline"

#: модуль → его сводка и его дисциплина в общем словаре
CONTOURS = [
    ("fire_safety", "/api/v1/fire-safety/readiness", Discipline.FIRE_SAFETY),
    ("industrial_safety", "/api/v1/industrial-safety/readiness", Discipline.INDUSTRIAL_SAFETY),
    ("ecology", "/api/v1/ecology/readiness", Discipline.ECOLOGY),
    ("civil_defense", "/api/v1/civil-defense/readiness", Discipline.CIVIL_DEFENSE),
    ("road_safety", "/api/v1/road-safety/readiness", Discipline.ROAD_SAFETY),
]


async def _grant(session, tenant_id: str, code: str) -> None:
    """Выдать модуль арендатору — сводки контуров закрыты роутерным гейтом."""

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
                FeatureEnablement.tenant_id == tenant_id,
                FeatureEnablement.feature_id == feature.id,
            )
        )
    ).scalar_one_or_none()
    if grant is None:
        session.add(FeatureEnablement(tenant_id=tenant_id, feature_id=feature.id, on=True))
    else:
        grant.on = True


async def _seed(sessionmaker, data_factory: TestDataFactory, module: str, mine: Discipline) -> None:
    """Два открытых своей дисциплины и шесть «отвлекающих» — все должны пройти мимо."""

    other = Discipline.MEDICAL if mine is not Discipline.MEDICAL else Discipline.PPE
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        await _grant(session, tid, module)
        company = Company(tenant_id=tid, name="ООО Контур")
        session.add(company)
        await session.flush()
        site = Site(tenant_id=tid, company_id=company.id, name="Цех")
        session.add(site)
        await session.flush()

        def incident(title: str, *, discipline: str | None, **extra):
            return Incident(
                tenant_id=tid,
                company_id=company.id,
                site_id=site.id,
                title=title,
                occurred_at=NOW - timedelta(days=3),
                discipline=discipline,
                **extra,
            )

        session.add_all(
            [
                # свои открытые — «сообщено» и «корректирующие действия» оба живые
                incident("Своё, сообщено", discipline=mine.value),
                incident("Своё, в работе", discipline=mine.value, status=IncidentStatus.ACTIONS),
                # своё, но уже не открытое
                incident("Своё, закрыто", discipline=mine.value, status=IncidentStatus.CLOSED),
                incident("Своё, отменено", discipline=mine.value, status=IncidentStatus.CANCELLED),
                incident("Своё, удалено", discipline=mine.value, deleted_at=NOW),
                # чужое и неразмеченное — не этого контура
                incident("Чужое открытое", discipline=other.value),
                incident("Без разметки", discipline=None),
            ]
        )
        await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(("module", "url", "discipline"), CONTOURS, ids=[c[0] for c in CONTOURS])
async def test_контур_считает_только_свои_открытые_и_ровно_как_разрез(
    async_client: AsyncClient,
    make_auth_headers,
    sessionmaker,
    data_factory,
    module: str,
    url: str,
    discipline: Discipline,
):
    await _seed(sessionmaker, data_factory, module, discipline)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    readiness = await async_client.get(url, headers=headers)

    assert readiness.status_code == status.HTTP_200_OK, readiness.text
    assert readiness.json()["incidents_open"] == 2

    # директор в разрезе видит про эту дисциплину ТО ЖЕ число
    breakdown = await async_client.get(BREAKDOWN, headers=headers)
    assert breakdown.status_code == status.HTTP_200_OK, breakdown.text
    rows = {row["id"]: row for row in breakdown.json()["items"]}
    assert rows[discipline.value]["incidents_open"] == readiness.json()["incidents_open"]
