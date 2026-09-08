"""«Открытое происшествие» — одна формула на всю платформу (срез-69).

ЗАЧЕМ. Число «открытых происшествий» показывают семь мест: сводка дашборда,
KPI отчётов, рабочий стол роли, проекции площадок, сводка аналитики, отчёты
по дисциплинам, сводка карты рисков. Формула была написана в каждом заново:
две копии считали удалённые, рабочий стол не считал «корректирующие
действия» — и один и тот же человек видел на дашборде одно число, на рабочем
столе другое. Сводка карты рисков (срез-74) и вовсе считала строки
``IncidentCase`` — таблицы, которую ни одна ручка не заполняет, — и её
«давление происшествий» было нулём всегда. Теперь все берут
``open_incidents_where`` из ``services/discipline_incidents.py``.

ЧТО ПРОВЕРЯЕТСЯ: сторож — никто в ``backend/app`` не пишет условие по статусу
происшествия сам; живьём — рабочий стол считает «корректирующие действия»
открытым, сводка дашборда и KPI отчётов не считают удалённое, сводка карты
рисков видит живые происшествия.
"""

from __future__ import annotations

import pathlib
import re
from datetime import datetime, timezone

import pytest

from app.models.models import Incident, IncidentStage, IncidentStatus, IncidentType, RoleEnum

REPO = pathlib.Path(__file__).resolve().parents[1]
APP = REPO / "backend" / "app"

#: Единственное место, где формула НАПИСАНА; остальные обязаны её импортировать.
FORMULA_HOME = "services/discipline_incidents.py"
_STATUS_CONDITION = re.compile(r"Incident\.status\.(not)?in_\(")


def test_сторож_условие_по_статусу_происшествия_пишется_один_раз() -> None:
    """Своя копия формулы разойдётся с остальными на первой правке словаря."""

    offenders: list[str] = []
    for path in APP.rglob("*.py"):
        rel = path.relative_to(APP).as_posix()
        if rel.startswith("migrations/") or rel == FORMULA_HOME:
            continue
        text = path.read_text(encoding="utf-8")
        if not _STATUS_CONDITION.search(text):
            continue
        # реестр отбирает по слову «open» той же константой — это импорт, не копия
        if "FINISHED_INCIDENT_STATUSES" in text and "discipline_incidents" in text:
            continue
        offenders.append(rel)
    assert offenders == [], (
        "условие по статусу происшествия написано заново — возьмите "
        f"open_incidents_where из {FORMULA_HOME}: {offenders}"
    )


async def _tenant_with_incidents(sessionmaker, data_factory):
    """Три происшествия: в корректирующих действиях, закрытое и удалённое (сообщено)."""

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(tenant=tenant, company=company, session=session)

        def make(status: IncidentStatus, *, deleted: bool = False) -> Incident:
            return Incident(
                tenant_id=tenant.id,
                title=f"Происшествие {status.value}",
                incident_type=IncidentType.ACCIDENT,
                occurred_at=datetime.now(timezone.utc),
                company_id=company.id,
                site_id=site.id,
                status=status,
                investigation_stage=IncidentStage.REGISTRATION,
                deleted_at=datetime.now(timezone.utc) if deleted else None,
            )

        session.add_all(
            [
                make(IncidentStatus.ACTIONS),
                make(IncidentStatus.CLOSED),
                make(IncidentStatus.REPORTED, deleted=True),
            ]
        )
        await session.commit()


@pytest.mark.asyncio
async def test_рабочий_стол_считает_корректирующие_действия_открытым(
    async_client, sessionmaker, data_factory, make_auth_headers
) -> None:
    """Раньше рабочий стол считал только «сообщено» и «расследуется»."""

    await _tenant_with_incidents(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.get("/api/v1/workspace/role-summary", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["open_incidents"] == 1


@pytest.mark.asyncio
async def test_сводка_дашборда_и_kpi_не_считают_удалённое(
    async_client, sessionmaker, data_factory, make_auth_headers
) -> None:
    """Раньше обе копии не смотрели на ``deleted_at``."""

    await _tenant_with_incidents(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    summary = await async_client.get("/api/v1/dashboard/summary", headers=headers)
    kpi = await async_client.get("/api/v1/reports/kpi", headers=headers)

    assert summary.status_code == 200, summary.text
    assert kpi.status_code == 200, kpi.text
    assert summary.json()["incidents_open"] == 1
    assert kpi.json()["incidents_open"] == 1


@pytest.mark.asyncio
async def test_сводка_карты_рисков_считает_живые_происшествия(
    async_client, sessionmaker, data_factory, make_auth_headers
) -> None:
    """Раньше «давление происшествий» считало пустую таблицу ``IncidentCase`` (срез-74)."""

    await _tenant_with_incidents(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    methodology = await async_client.post(
        "/api/v1/risk/advanced/methodologies",
        json={
            "code": "fk-open-incidents",
            "name": "Fine Kinney",
            "type": "fine_kinney",
            "formula_json": {"ranges": [{"min": 0, "max": 10000, "level": "low"}]},
        },
        headers=headers,
    )
    assert methodology.status_code == 201, methodology.text
    risk_map = await async_client.post(
        "/api/v1/risk/advanced/maps",
        json={
            "entity_type": "site",
            "entity_id": "site-1",
            "risk_methodology_id": methodology.json()["id"],
        },
        headers=headers,
    )
    assert risk_map.status_code == 201, risk_map.text

    summary = await async_client.get(
        f"/api/v1/risk/advanced/maps/{risk_map.json()['id']}/summary", headers=headers
    )

    assert summary.status_code == 200, summary.text
    assert summary.json()["incident_pressure"] == 1


def test_мёртвый_жизненный_цикл_incident_case_не_воскрешён() -> None:
    """Срез-117: слой ЖЦ ``IncidentCase`` удалён — сторож против возврата вслепую.

    ``IncidentCaseService`` / ``IncidentInvestigationService`` /
    ``RiskReviewTriggerService`` описывали переходы статусов таблицы, которую
    не заполняет ни одна ручка, и не имели потребителей в продукте. Живой
    контур происшествий — ядровая ``Incident``; второе описание того же
    процесса означало бы два места правды.

    Если контур понадобится — возвращать его надо ВМЕСТЕ с ручками; тогда этот
    тест обновляют осознанно.
    """

    import app.modules.incidents as incidents

    for dead in (
        "IncidentCaseService",
        "IncidentInvestigationService",
        "RiskReviewTriggerService",
    ):
        assert not hasattr(incidents, dead), dead
    # Живые операции контура на месте.
    assert hasattr(incidents, "register_incident")
    assert hasattr(incidents, "append_log_entry")
