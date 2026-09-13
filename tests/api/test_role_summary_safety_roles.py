"""Сводка роли работает для ролей охраны труда, а не только для админа (срез-151).

ЗАЧЕМ. `GET /workspace/role-summary` открыт всем ролям арендатора и обещает
«aggregated workspace summary for safety leads, HR, managers». Разрез выбирался
по множеству `_SAFETY_ROLES`, в котором стояли `safety_lead` и
`safety_manager` — кодов, которых нет в ``RoleEnum``. Совпасть они не могли ни
с одним пользователем, поэтому происшествия и проверки считались только для
`admin` и `owner`, а специалист по ОТ, руководитель ОТиПБ, начальник отдела ОТ
и инженер ПБ видели у себя нули — при непустом арендаторе.

Дефект дожил до среза-151 потому, что существующие тесты сводки ходили
**администратором** — ролью, у которой открыто всё. Здесь проверка идёт теми
ролями, ради которых разрез написан.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.incidents import Incident, IncidentStage, IncidentStatus, IncidentType
from app.models.models import RoleEnum

pytestmark = pytest.mark.anyio

SUMMARY = "/api/v1/workspace/role-summary"

#: Роли, ради которых написан разрез охраны труда (все существуют в RoleEnum).
SAFETY_ROLES = [
    RoleEnum.OT_SPECIALIST,
    RoleEnum.OT_PB_LEAD,
    RoleEnum.OT_HEAD,
    RoleEnum.PB_ENGINEER,
]


async def _tenant_with_open_incident(sessionmaker, data_factory) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(tenant=tenant, company=company, session=session)
        session.add(
            Incident(
                tenant_id=tenant.id,
                title="Падение с высоты",
                incident_type=IncidentType.ACCIDENT,
                occurred_at=datetime.now(timezone.utc),
                company_id=company.id,
                site_id=site.id,
                status=IncidentStatus.REPORTED,
                investigation_stage=IncidentStage.REGISTRATION,
            )
        )
        await session.commit()


@pytest.mark.parametrize("role", SAFETY_ROLES, ids=[r.value for r in SAFETY_ROLES])
async def test_роль_охраны_труда_видит_открытое_происшествие_в_своей_сводке(
    async_client, sessionmaker, data_factory, make_auth_headers, role: RoleEnum
) -> None:
    await _tenant_with_open_incident(sessionmaker, data_factory)
    headers = await make_auth_headers(role, email=f"{role.value}-summary@example.com")

    response = await async_client.get(SUMMARY, headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["role"] == role.value
    # До среза здесь был ноль при непустом арендаторе.
    assert body["open_incidents"] == 1, body


async def test_рядовой_работник_разрез_охраны_труда_не_получает(
    async_client, sessionmaker, data_factory, make_auth_headers
) -> None:
    """Починка не раздала разрез всем подряд: у роли вне охраны труда, HR и
    руководителей происшествия по арендатору по-прежнему не считаются."""

    await _tenant_with_open_incident(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.WORKER, email="worker-summary@example.com")

    response = await async_client.get(SUMMARY, headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["open_incidents"] == 0
