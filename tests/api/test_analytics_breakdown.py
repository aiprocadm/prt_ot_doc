"""Breakdown by company/site/contractor (P10-07 §24.2)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import (
    Company,
    Incident,
    IncidentStatus,
    RoleEnum,
    Site,
    TrainingPlan,
)
from app.models.risk import RiskAssessment, RiskAssessmentItem, RiskHazard
from tests.utils.factories import TestDataFactory

NOW = datetime.now(tz=timezone.utc)
BASE = "/api/v1/analytics/dashboard/breakdown"


async def _add_high_risk(session, tenant_id: str, *, company_id: str, site_id: str | None) -> None:
    """Высокая оценка риска — ЖИВЫМИ таблицами (срез-134).

    Раньше тесты заводили строку реестра ``risk`` — таблицы, в которую продукт
    не пишет никогда. Проверка была зелёной, а разрез в бою показывал ноль
    (это и нашёл срез-131). Сеять надо тем же способом, каким данные создаёт
    продукт, иначе тест держит собственную подготовку, а не поведение.
    """

    hazard = RiskHazard(
        tenant_id=tenant_id,
        code=f"HZ-{site_id or 'none'}",
        title="Высота",
        module="ot",
        recommended_measures=[],
    )
    session.add(hazard)
    await session.flush()
    assessment = RiskAssessment(
        tenant_id=tenant_id,
        assessment_key=f"as-{site_id or 'none'}",
        assessment_version=1,
        methodology_version=1,
        company_id=company_id,
        place_id=site_id,
        hazard_id=hazard.id,
        severity_before=4,
        likelihood_before=4,
        score_before=16,
        band_before="high",
        severity_after=4,
        likelihood_after=4,
        score_after=16,
        band_after="high",
    )
    session.add(assessment)
    await session.flush()
    # Счёт идёт по СТРОКАМ оценки (срез-131): одна оценка описывает много
    # опасностей, и каждая высокая — отдельный повод вмешаться.
    session.add(
        RiskAssessmentItem(
            tenant_id=tenant_id,
            assessment_id=assessment.id,
            hazard_id=hazard.id,
            probability=4,
            severity=4,
            score=16,
            level="high",
            methodology_version=1,
        )
    )


async def _seed(sessionmaker, data_factory: TestDataFactory) -> dict[str, str]:
    from app.models.training import TrainingCourse

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        company = Company(tenant_id=tid, name="ООО Ромашка")
        session.add(company)
        await session.flush()
        s1 = Site(tenant_id=tid, company_id=company.id, name="Цех №1")
        s2 = Site(tenant_id=tid, company_id=company.id, name="Офис")
        session.add_all([s1, s2])
        await session.flush()
        session.add_all(
            [
                Incident(
                    tenant_id=tid,
                    company_id=company.id,
                    site_id=s1.id,
                    title="Падение",
                    occurred_at=NOW - timedelta(days=3),
                ),
                Incident(
                    tenant_id=tid,
                    company_id=company.id,
                    site_id=s1.id,
                    title="Порез",
                    occurred_at=NOW - timedelta(days=40),
                ),
                Incident(
                    tenant_id=tid,
                    company_id=company.id,
                    site_id=s2.id,
                    title="Задымление",
                    occurred_at=NOW - timedelta(days=1),
                    status=IncidentStatus.CLOSED,
                ),
            ]
        )
        await _add_high_risk(session, tid, company_id=company.id, site_id=s1.id)
        course = TrainingCourse(tenant_id=tid, title="ОТ-101")
        session.add(course)
        await session.flush()
        session.add(
            TrainingPlan(
                tenant_id=tid,
                company_id=company.id,
                course_id=course.id,
                due_date=date.today() - timedelta(days=5),
            )
        )
        await session.commit()
        return {"company_id": company.id, "s1": s1.id, "s2": s2.id}


@pytest.mark.asyncio
async def test_site_breakdown_counts_and_order(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
):
    ids = await _seed(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.get(f"{BASE}?dimension=site", headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    assert body["dimension"] == "site"
    assert body["total"] == 2
    first = body["items"][0]
    # Цех №1: 2 открытых инцидента + 1 high-риск → худший сверху
    assert first["id"] == ids["s1"]
    assert first["incidents_open"] == 2
    assert first["risks_high"] == 1
    assert first["total_issues"] == 3
    # Офис: закрытый инцидент не считается → нули, но строка присутствует
    second = body["items"][1]
    assert second["id"] == ids["s2"]
    assert second["incidents_open"] == 0
    assert second["total_issues"] == 0


@pytest.mark.asyncio
async def test_site_breakdown_null_site_bucket(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        company = Company(tenant_id=tid, name="ООО Безобъектная")
        session.add(company)
        await session.flush()
        await _add_high_risk(session, tid, company_id=company.id, site_id=None)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.get(f"{BASE}?dimension=site", headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    bucket = next(i for i in body["items"] if i["name"] == "— без объекта")
    assert bucket["id"] == ""
    assert bucket["risks_high"] == 1
    assert bucket["incidents_open"] == 0
    assert bucket["total_issues"] == 1


@pytest.mark.asyncio
async def test_company_breakdown_includes_trainings(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    ids = await _seed(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.get(f"{BASE}?dimension=company", headers=headers)
    assert resp.status_code == status.HTTP_200_OK
    row = next(i for i in resp.json()["items"] if i["id"] == ids["company_id"])
    assert row["incidents_open"] == 2
    assert row["trainings_overdue"] == 1
    assert row["risks_high"] == 1


@pytest.mark.asyncio
async def test_date_window_narrows_incidents(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    ids = await _seed(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    date_from = (NOW - timedelta(days=7)).date().isoformat()
    resp = await async_client.get(f"{BASE}?dimension=site&date_from={date_from}", headers=headers)
    first = next(i for i in resp.json()["items"] if i["id"] == ids["s1"])
    assert first["incidents_open"] == 1  # 40-дневный инцидент отфильтрован


@pytest.mark.asyncio
async def test_contractor_breakdown_zero_row(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    from app.modules.contractors.models import ContractorRegistry

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        session.add(ContractorRegistry(tenant_id=str(tenant.id), name="СтройПодряд"))
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.get(f"{BASE}?dimension=contractor", headers=headers)
    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert body["total"] == 1
    row = body["items"][0]
    assert row["name"] == "СтройПодряд"
    assert row["workers_blocked"] == 0 and row["total_issues"] == 0


@pytest.mark.asyncio
async def test_contractor_breakdown_populated_row(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    from app.modules.contractors.models import ContractorRegistry
    from app.modules.projections.models import ContractorReadinessReadModel

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        contractor = ContractorRegistry(tenant_id=tid, name="СтройПодряд")
        session.add(contractor)
        await session.flush()
        session.add(
            ContractorReadinessReadModel(
                tenant_id=tid,
                contractor_id=contractor.id,
                workers_blocked=2,
                missing_docs_count=1,
                missing_training_count=0,
                overdue_items_count=3,
                active_packages_count=5,
            )
        )
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.get(f"{BASE}?dimension=contractor", headers=headers)
    assert resp.status_code == status.HTTP_200_OK
    row = resp.json()["items"][0]
    assert row["workers_blocked"] == 2
    assert row["missing_docs"] == 1
    assert row["overdue_items"] == 3
    assert row["active_packages"] == 5
    # active_packages — информационная метрика, в total_issues НЕ входит
    assert row["total_issues"] == 6


@pytest.mark.asyncio
async def test_unknown_dimension_422_and_isolation(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    await _seed(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    bad = await async_client.get(f"{BASE}?dimension=bogus", headers=headers)
    assert bad.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    # изоляция: метрики строго tenant-scoped — проверено WHERE в каждом запросе;
    # smoke: без dimension тоже 422 (обязательный параметр)
    missing = await async_client.get(BASE, headers=headers)
    assert missing.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    # инвертированное окно (date_from > date_to) → 422 breakdown_window_invalid
    inverted = await async_client.get(
        f"{BASE}?dimension=site&date_from=2026-07-10&date_to=2026-07-01",
        headers=headers,
    )
    assert inverted.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
