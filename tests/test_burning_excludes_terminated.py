"""Уволенный не горит: сводки, KPI, качество данных и «истекает скоро» (срез-127).

ЗАЧЕМ. Одно и то же «что горит» платформа считала по-разному, смотря какой
экран открыть: календарь и Центр внимания уволенного не считали (срез-93,
срез-96), а сводка дашборда, KPI отчётов, счётчики рабочего места, снимок
сроков соответствия, списки «истекает скоро» у СИЗ и удостоверений и три
правила качества данных — считали. Хуже всего это выглядело у аутсорсера:
лента сигналов по портфелю строится ровно на тех трёх правилах просрочки, и
клиент «горел» там, где его собственный светофор был чист.

ЧТО ПРОВЕРЯЕТСЯ. У арендатора три человека с одинаковой просрочкой —
работающий, уволенный и удалённый. Каждая починенная поверхность обязана
показать ЕДИНИЦУ. Запись без человека (план обучения на организацию) остаётся
в счёте: увольнять там некого.

Сторож против нового пропуска правила — ``test_burning_selection_scope``.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.models import (
    ComplianceDeadline,
    EmploymentStatus,
    MedicalExam,
    Permit,
    PermitStatus,
    PPEIssue,
    PPEIssueStatus,
    RoleEnum,
    Training,
    TrainingCertificate,
    TrainingCourse,
    TrainingPlan,
    TrainingStatus,
)
from app.modules.data_quality.rules import (
    ExpiredPermitsRule,
    ExpiredPPEIssuesRule,
    ExpiredRecordsRule,
)
from app.modules.ppe.operations import list_expiring_issues
from app.modules.training.operations import upcoming_certificate_expirations

API_PREFIX = "/api/v1"


async def _tenant_with_burning(sessionmaker, data_factory) -> str:
    """Одинаковая просрочка у работающего, уволенного и удалённого.

    Плюс один план обучения БЕЗ человека — он на организацию, и правило его
    не трогает.
    """

    now = datetime.now(tz=timezone.utc)
    today = date.today()
    yesterday = today - timedelta(days=1)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(
            tenant=tenant, name="ООО Срез-127", session=session
        )
        working = await data_factory.create_person(
            tenant=tenant, company=company, last_name="Работает", session=session
        )
        fired = await data_factory.create_person(
            tenant=tenant,
            company=company,
            last_name="Уволен",
            session=session,
            employment_status=EmploymentStatus.TERMINATED,
        )
        erased = await data_factory.create_person(
            tenant=tenant, company=company, last_name="Удалён", session=session, deleted_at=now
        )
        course = TrainingCourse(tenant_id=tenant.id, title="Курс-127")
        session.add(course)
        await session.flush()

        for person in (working, fired, erased):
            session.add_all(
                [
                    MedicalExam(
                        tenant_id=tenant.id,
                        person_id=person.id,
                        exam_type="periodic",
                        exam_date=today - timedelta(days=400),
                        valid_until=yesterday,
                        conclusion="fit",
                    ),
                    PPEIssue(
                        tenant_id=tenant.id,
                        person_id=person.id,
                        item_name="Каска",
                        quantity=1,
                        status=PPEIssueStatus.ISSUED,
                        issued_at=now - timedelta(days=400),
                        expires_at=now - timedelta(days=30),
                    ),
                    # Вторая выдача — «истекает скоро», для списка /issues/expiring.
                    PPEIssue(
                        tenant_id=tenant.id,
                        person_id=person.id,
                        item_name="Перчатки",
                        quantity=1,
                        status=PPEIssueStatus.ISSUED,
                        issued_at=now - timedelta(days=100),
                        expires_at=now + timedelta(days=10),
                    ),
                    Permit(
                        tenant_id=tenant.id,
                        person_id=person.id,
                        permit_type="Работы на высоте",
                        issued_at=today - timedelta(days=400),
                        valid_until=yesterday,
                        status=PermitStatus.ACTIVE.value,
                    ),
                    Training(
                        tenant_id=tenant.id,
                        person_id=person.id,
                        course_name="Курс-127",
                        status=TrainingStatus.COMPLETED,
                        expires_at=now - timedelta(days=5),
                    ),
                    TrainingCertificate(
                        tenant_id=tenant.id,
                        person_id=person.id,
                        course_id=course.id,
                        number=f"УД-{person.last_name}",
                        issued_at=today - timedelta(days=400),
                        valid_until=today + timedelta(days=10),
                    ),
                    TrainingPlan(
                        tenant_id=tenant.id,
                        company_id=company.id,
                        course_id=course.id,
                        person_id=person.id,
                        due_date=yesterday,
                    ),
                    ComplianceDeadline(
                        tenant_id=tenant.id,
                        entity_type="training_certificate",
                        entity_id=f"ent-{person.id}",
                        person_id=person.id,
                        due_at=now - timedelta(days=3),
                        status="overdue",
                    ),
                ]
            )
        # План на организацию, без человека — остаётся в счёте.
        session.add(
            TrainingPlan(
                tenant_id=tenant.id,
                company_id=company.id,
                course_id=course.id,
                due_date=yesterday,
            )
        )
        await session.commit()
        return str(tenant.id)


@pytest.mark.anyio
async def test_правила_качества_данных_не_считают_уволенного(sessionmaker, data_factory) -> None:
    """Просроченный медосмотр уволенного — история, а не разрыв с эталоном.

    Эти же три правила кормят ленту сигналов по портфелю
    (``services/client_dq_signals``): без отбора аутсорсер видел «горит» у
    клиента, чей светофор чист.
    """

    tenant_id = await _tenant_with_burning(sessionmaker, data_factory)
    async with sessionmaker() as session:
        records = ExpiredRecordsRule(tenant_id, session)
        permits = ExpiredPermitsRule(tenant_id, session)
        ppe = ExpiredPPEIssuesRule(tenant_id, session)
        for rule in (records, permits, ppe):
            await rule.check()

    # Медосмотр + обучение работающего — по одной находке на каждое.
    assert len(records.issues) == 2, [issue.title for issue in records.issues]
    assert len(permits.issues) == 1, [issue.title for issue in permits.issues]
    assert len(ppe.issues) == 1, [issue.title for issue in ppe.issues]


@pytest.mark.anyio
async def test_истекающие_сиз_и_удостоверения_только_по_работающим(
    sessionmaker, data_factory
) -> None:
    """«Что истекает скоро» — вопрос о будущей работе, а не о выданном когда-то."""

    tenant_id = await _tenant_with_burning(sessionmaker, data_factory)
    async with sessionmaker() as session:
        issues = await list_expiring_issues(session, tenant_id=tenant_id, within_days=30)
        certificates = list(await upcoming_certificate_expirations(session, tenant_id=tenant_id))

    assert [issue.item_name for issue in issues] == ["Перчатки"]
    assert [certificate.number for certificate in certificates] == ["УД-Работает"]


@pytest.mark.asyncio
async def test_сводка_и_kpi_считают_обучение_одинаково(
    async_client, sessionmaker, data_factory, make_auth_headers
) -> None:
    """Раньше сводка и KPI считали троих, а виджеты аналитики рядом — одного.

    План на организацию (без человека) считается везде — отсюда двойка.
    """

    await _tenant_with_burning(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    summary = await async_client.get(f"{API_PREFIX}/dashboard/summary", headers=headers)
    kpi = await async_client.get(f"{API_PREFIX}/reports/kpi", headers=headers)

    assert summary.status_code == 200, summary.text
    assert kpi.status_code == 200, kpi.text
    assert summary.json()["training"]["overdue"] == 2
    assert kpi.json()["trainings_overdue"] == 2


@pytest.mark.asyncio
async def test_сроки_соответствия_и_счётчики_рабочего_места(
    async_client, sessionmaker, data_factory, make_auth_headers
) -> None:
    """Снимок сроков хранит и уволенных (это история) — но при чтении их нет."""

    await _tenant_with_burning(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    deadlines = await async_client.get(f"{API_PREFIX}/compliance/deadlines", headers=headers)
    attention = await async_client.get(f"{API_PREFIX}/workspace/attention", headers=headers)
    role_summary = await async_client.get(f"{API_PREFIX}/workspace/role-summary", headers=headers)

    assert deadlines.status_code == 200, deadlines.text
    assert attention.status_code == 200, attention.text
    assert role_summary.status_code == 200, role_summary.text
    assert deadlines.json()["total"] == 1
    assert attention.json()["summary"]["overdue_deadlines"] == 1
    assert role_summary.json()["overdue_deadlines"] == 1


@pytest.mark.asyncio
async def test_календарь_допусков_молчит_про_уволенного(
    async_client, sessionmaker, data_factory, make_auth_headers
) -> None:
    """Наряды-допуски были единственной веткой календаря без отбора: список
    медосмотров уволенного уже не показывал, а список допусков — показывал."""

    await _tenant_with_burning(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.get(
        f"{API_PREFIX}/calendar/events?source_types=permit", headers=headers
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["items"]) == 1, payload["items"]
    # Итог рядом со списком считался отдельным запросом — и тоже без отбора.
    permits = next(row for row in payload["by_source"] if row["source_type"] == "permit")
    assert permits["count"] == 1
