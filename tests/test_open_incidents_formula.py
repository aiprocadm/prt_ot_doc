"""«Открытое происшествие» — одна формула на всю платформу (срез-69).

ЗАЧЕМ. Число «открытых происшествий» показывают шесть мест: сводка дашборда,
KPI отчётов, рабочий стол роли, проекции площадок, сводка аналитики, отчёты
по дисциплинам. Формула была написана в каждом заново: две копии считали
удалённые, рабочий стол не считал «корректирующие действия» — и один и тот
же человек видел на дашборде одно число, на рабочем столе другое. Теперь все
берут ``open_incidents_where`` из ``services/discipline_incidents.py``.

ЧТО ПРОВЕРЯЕТСЯ: сторож — никто в ``backend/app`` не пишет условие по статусу
происшествия сам; живьём — рабочий стол считает «корректирующие действия»
открытым, а сводка дашборда и KPI отчётов не считают удалённое.
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
