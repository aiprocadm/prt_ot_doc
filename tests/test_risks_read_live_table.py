"""Риски считаются по живой таблице и одной формулой (BIZ-54-57 срез-131).

ЗАЧЕМ. В базе ДВЕ таблицы про риски. Живая — оценки (``risk_assessments`` и
строки ``risk_assessment_items``), их заводит контур рисков. Мёртвая — реестр
``risk``: в неё не пишет никто во всём ``backend/app``.

По мёртвому реестру считали три места: разрез аналитики (высокие риски по
организациям и площадкам), сигнал Командного центра и набор строк конструктора
отчётов. Все три показывали НОЛЬ при любом количестве настоящих рисков — и это
не выглядело поломкой, потому что «рисков нет» читается как хорошая новость.
Тот же класс, что «давление происшествий» в срезе-74.

ЧТО ПРОВЕРЯЕТСЯ: у арендатора с одной высокой оценкой риска все четыре
поверхности (KPI отчётов, разрез, Командный центр, конструктор отчётов)
показывают ЕДИНИЦУ, а не ноль. Формула «высокий риск» — одна на всех
(``services/discipline_risks``); сторож не даёт написать её копию.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app.models.models import RoleEnum
from app.models.risk import RiskAssessment, RiskAssessmentItem, RiskHazard

REPO = pathlib.Path(__file__).resolve().parents[1]
APP = REPO / "backend" / "app"
FORMULA_HOME = "services/discipline_risks.py"
#: Своя копия перечня уровней — та же ошибка, что чинил срез-131.
_LEVELS_BY_HAND = re.compile(r'level\.in_\(\s*[\[\(]\s*"(high|crit)"')

pytestmark = pytest.mark.anyio


async def _tenant_with_high_risk(sessionmaker, data_factory):
    """Одна высокая оценка риска у организации и площадки."""

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(
            tenant=tenant, name="ООО Срез-131", session=session
        )
        site = await data_factory.create_site(tenant=tenant, company=company, session=session)
        hazard = RiskHazard(
            tenant_id=str(tenant.id),
            code="HZ-131",
            title="Шум на участке",
            module="ot",
            recommended_measures=[],
        )
        session.add(hazard)
        await session.flush()
        assessment = RiskAssessment(
            tenant_id=str(tenant.id),
            assessment_key="srez-131",
            assessment_version=1,
            methodology_version=1,
            company_id=company.id,
            place_id=site.id,
            hazard_id=hazard.id,
            severity_before=4,
            likelihood_before=4,
            score_before=16,
            band_before="high",
            severity_after=4,
            likelihood_after=4,
            score_after=16,
            band_after="high",
            controls="Наушники, ротация",
        )
        session.add(assessment)
        await session.flush()
        session.add(
            RiskAssessmentItem(
                tenant_id=str(tenant.id),
                assessment_id=assessment.id,
                hazard_id=hazard.id,
                probability=4,
                severity=4,
                score=16,
                level="high",
                methodology_version=1,
            )
        )
        await session.commit()
        return str(tenant.id), str(company.id), str(site.id)


def test_сторож_перечень_высоких_уровней_пишется_один_раз() -> None:
    """Своя копия перечня разойдётся с остальными на первой правке шкалы."""

    offenders: list[str] = []
    for path in APP.rglob("*.py"):
        rel = path.relative_to(APP).as_posix()
        if rel.startswith("migrations/") or rel == FORMULA_HOME:
            continue
        if _LEVELS_BY_HAND.search(path.read_text(encoding="utf-8")):
            offenders.append(rel)
    assert offenders == [], (
        "перечень «высоких» уровней написан заново — возьмите "
        f"high_risk_item_where из {FORMULA_HOME}: {offenders}"
    )


async def test_разрез_аналитики_видит_живые_риски(sessionmaker, data_factory) -> None:
    """Раньше разрез считал по мёртвому реестру — ноль при любых рисках."""

    from app.modules.analytics.breakdown import compute_breakdown

    tenant_id, company_id, site_id = await _tenant_with_high_risk(sessionmaker, data_factory)
    async with sessionmaker() as session:
        by_company = await compute_breakdown(session, tenant_id, "company")
        by_site = await compute_breakdown(session, tenant_id, "site")

    company_row = next(row for row in by_company["items"] if row["id"] == company_id)
    site_row = next(row for row in by_site["items"] if row["id"] == site_id)
    assert company_row["risks_high"] == 1
    assert site_row["risks_high"] == 1


async def test_командный_центр_говорит_о_высоком_риске(sessionmaker, data_factory) -> None:
    """Сигнал считался по мёртвому реестру — Командный центр молчал всегда."""

    from app.core.config import get_settings
    from app.modules.operational_dashboard.service import OperationalDashboardService

    tenant_id, _company_id, _site_id = await _tenant_with_high_risk(sessionmaker, data_factory)
    service = OperationalDashboardService(get_settings())
    async with sessionmaker() as session:
        alerts = await service._get_high_risk_alerts(tenant_id, session)

    high = [alert for alert in alerts if alert.id == "high_risk_register_items"]
    assert len(high) == 1, [alert.id for alert in alerts]
    assert "1" in high[0].title


async def test_конструктор_отчётов_отдаёт_живые_оценки(sessionmaker, data_factory) -> None:
    """Набор строк «риски» строился по мёртвому реестру — отчёт был пуст всегда."""

    from datetime import datetime, timezone

    from app.modules.report_builder.datasets import DATASETS

    tenant_id, _company_id, _site_id = await _tenant_with_high_risk(sessionmaker, data_factory)
    async with sessionmaker() as session:
        stmt = DATASETS["risks"].build_stmt(tenant_id, datetime.now(tz=timezone.utc))
        rows = (await session.execute(stmt)).mappings().all()

    assert len(rows) == 1, rows
    assert rows[0]["hazard"] == "Шум на участке"
    assert rows[0]["level"] == 16
    assert rows[0]["company_name"] == "ООО Срез-131"


async def test_kpi_отчётов_считает_ту_же_единицу(
    async_client, make_auth_headers, sessionmaker, data_factory
) -> None:
    """KPI считал по живой таблице и раньше — но своей копией условия.

    Проверка держит главное обещание среза: все поверхности дают ОДНО число.
    """

    await _tenant_with_high_risk(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.get("/api/v1/reports/kpi", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["risks_high"] == 1


async def test_шкалу_задаёт_методология_а_не_ручка(
    async_client, make_auth_headers, sessionmaker, data_factory
) -> None:
    """Срез-132: оценка по Fine-Kinney в старый предел не влезала.

    Схема ответа держала ``probability``/``severity`` в 1..5 — шкалу мёртвого
    реестра. У Fine-Kinney вероятность идёт до 10, последствия до 100: такая
    оценка ломала бы ручку на живых данных. Урезать чужую шкалу нельзя, а
    пересчитывать в 5×5 — значит показать число, которого нет ни в одном
    документе арендатора. Поэтому верхней границы нет, нижняя осталась.
    """

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(
            tenant=tenant, name="ООО Файн-Кинни", session=session
        )
        hazard = RiskHazard(
            tenant_id=str(tenant.id),
            code="FK-1",
            title="Работа на высоте",
            module="ot",
            recommended_measures=[],
        )
        session.add(hazard)
        await session.flush()
        session.add(
            RiskAssessment(
                tenant_id=str(tenant.id),
                assessment_key="fine-kinney",
                assessment_version=1,
                methodology_version=1,
                company_id=company.id,
                hazard_id=hazard.id,
                severity_before=40,
                likelihood_before=6,
                score_before=1440,
                band_before="crit",
                severity_after=40,
                likelihood_after=6,
                score_after=1440,
                band_after="crit",
            )
        )
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get("/api/v1/risks", headers=headers)

    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["severity"] == 40, "последствия по Fine-Kinney не влезали в прежний предел"
    assert item["probability"] == 6
    assert item["level"] == 1440
    assert item["hazard"] == "Работа на высоте"


async def test_организация_берётся_по_связям_а_пустота_называется(
    async_client, make_auth_headers, sessionmaker, data_factory
) -> None:
    """Срез-132: у оценки организация необязательна, а договор ручки её требует.

    Сделать поле пустым нельзя — смена типа в опубликованном ответе ломающая
    (docs/API_VERSIONING.md), ей место в новой мажорной версии. Поэтому
    организация берётся по связям (площадка, рабочее место), а когда её нет ни
    по одной — пустой строкой: строку теряют молча, а пустоту называют.
    """

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(
            tenant=tenant, name="ООО Связи", session=session
        )
        site = await data_factory.create_site(tenant=tenant, company=company, session=session)
        hazard = RiskHazard(
            tenant_id=str(tenant.id),
            code="HZ-132",
            title="Опасность без организации",
            module="ot",
            recommended_measures=[],
        )
        session.add(hazard)
        await session.flush()

        def assessment(key: str, *, place_id: str | None) -> RiskAssessment:
            return RiskAssessment(
                tenant_id=str(tenant.id),
                assessment_key=key,
                assessment_version=1,
                methodology_version=1,
                company_id=None,
                place_id=place_id,
                hazard_id=hazard.id,
                severity_before=2,
                likelihood_before=2,
                score_before=4,
                band_before="medium",
                severity_after=2,
                likelihood_after=2,
                score_after=4,
                band_after="medium",
            )

        session.add_all(
            [
                assessment("by-site", place_id=site.id),
                assessment("no-links", place_id=None),
            ]
        )
        await session.commit()
        company_id, site_id = str(company.id), str(site.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get("/api/v1/risks", headers=headers)

    assert response.status_code == 200, response.text
    items = {item["site_id"]: item for item in response.json()["items"]}
    assert items[site_id]["company_id"] == company_id, "организация есть у площадки"
    assert items[None]["company_id"] == "", "организации нет ни по одной связи — пустота названа"
