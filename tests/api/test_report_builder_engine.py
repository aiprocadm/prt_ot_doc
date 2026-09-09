"""Engine behaviour: filters / grouping / sort / validation / tenant isolation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.models import Company, Person, Training, TrainingStatus
from tests.utils.factories import TestDataFactory

NOW = datetime.now(tz=timezone.utc)


async def _seed_training(session, data_factory: TestDataFactory):
    tenant = await data_factory.ensure_tenant(session=session)
    tid = str(tenant.id)
    company = Company(tenant_id=tid, name="ООО Ромашка")
    session.add(company)
    await session.flush()
    p1 = Person(
        tenant_id=tid,
        company_id=company.id,
        first_name="Иван",
        last_name="Иванов",
        position_title="Электрик",
    )
    p2 = Person(
        tenant_id=tid,
        company_id=company.id,
        first_name="Пётр",
        last_name="Петров",
        position_title="Сварщик",
    )
    session.add_all([p1, p2])
    await session.flush()
    session.add_all(
        [
            Training(
                tenant_id=tid,
                person_id=p1.id,
                course_name="Охрана труда",
                status=TrainingStatus.COMPLETED,
                expires_at=NOW - timedelta(days=5),
            ),
            Training(
                tenant_id=tid,
                person_id=p1.id,
                course_name="Первая помощь",
                status=TrainingStatus.COMPLETED,
                expires_at=NOW + timedelta(days=300),
            ),
            Training(
                tenant_id=tid,
                person_id=p2.id,
                course_name="Охрана труда",
                status=TrainingStatus.SCHEDULED,
                scheduled_at=NOW + timedelta(days=10),
            ),
        ]
    )
    await session.commit()
    return tid


@pytest.mark.asyncio
async def test_plain_columns_filter_sort(sessionmaker, data_factory: TestDataFactory):
    from app.modules.report_builder.engine import run_report

    async with sessionmaker() as session:
        tid = await _seed_training(session, data_factory)
        result = await run_report(
            session,
            tenant_id=tid,
            dataset_code="employees_training",
            config={
                "columns": ["person_name", "course_name", "is_overdue"],
                "filters": [{"field": "status", "op": "eq", "value": "completed"}],
                "sort": [{"field": "course_name", "dir": "asc"}],
            },
            limit=100,
        )
        assert result.total == 2
        assert [c.key for c in result.columns] == ["person_name", "course_name", "is_overdue"]
        assert [r["course_name"] for r in result.rows] == ["Охрана труда", "Первая помощь"]
        overdue = {r["course_name"]: r["is_overdue"] for r in result.rows}
        assert overdue == {"Охрана труда": True, "Первая помощь": False}


@pytest.mark.asyncio
async def test_bool_filter_on_computed_column(sessionmaker, data_factory: TestDataFactory):
    from app.modules.report_builder.engine import run_report

    async with sessionmaker() as session:
        tid = await _seed_training(session, data_factory)
        result = await run_report(
            session,
            tenant_id=tid,
            dataset_code="employees_training",
            config={
                "columns": ["course_name"],
                "filters": [{"field": "is_overdue", "op": "eq", "value": True}],
            },
            limit=100,
        )
        assert result.total == 1
        assert result.rows[0]["course_name"] == "Охрана труда"


@pytest.mark.asyncio
async def test_group_by_with_aggregates(sessionmaker, data_factory: TestDataFactory):
    from app.modules.report_builder.engine import run_report

    async with sessionmaker() as session:
        tid = await _seed_training(session, data_factory)
        result = await run_report(
            session,
            tenant_id=tid,
            dataset_code="employees_training",
            config={
                "group_by": ["course_name"],
                "aggregates": [{"fn": "count"}],
                "sort": [{"field": "count", "dir": "desc"}],
            },
            limit=100,
        )
        assert [c.key for c in result.columns] == ["course_name", "count"]
        assert result.rows[0] == {"course_name": "Охрана труда", "count": 2}
        assert result.total == 2  # 2 группы


@pytest.mark.asyncio
async def test_preview_limit_and_total(sessionmaker, data_factory: TestDataFactory):
    from app.modules.report_builder.engine import run_report

    async with sessionmaker() as session:
        tid = await _seed_training(session, data_factory)
        result = await run_report(
            session,
            tenant_id=tid,
            dataset_code="employees_training",
            config={"columns": ["course_name"]},
            limit=1,
        )
        assert len(result.rows) == 1
        assert result.total == 3


@pytest.mark.asyncio
async def test_tenant_isolation(sessionmaker, data_factory: TestDataFactory):
    from app.modules.report_builder.engine import run_report

    async with sessionmaker() as session:
        await _seed_training(session, data_factory)
        result = await run_report(
            session,
            tenant_id="other-tenant",
            dataset_code="employees_training",
            config={},
            limit=100,
        )
        assert result.total == 0 and result.rows == []


@pytest.mark.asyncio
async def test_validation_errors(sessionmaker, data_factory: TestDataFactory):
    from app.modules.report_builder.engine import ReportConfigError, run_report, validate_config

    async with sessionmaker() as session:
        tid = await _seed_training(session, data_factory)
        with pytest.raises(ReportConfigError) as e1:
            await run_report(session, tenant_id=tid, dataset_code="nope", config={}, limit=1)
        assert e1.value.code == "dataset_unknown"
        with pytest.raises(ReportConfigError) as e2:
            await run_report(
                session,
                tenant_id=tid,
                dataset_code="employees_training",
                config={"columns": ["bogus"]},
                limit=1,
            )
        assert e2.value.code == "column_unknown"
        with pytest.raises(ReportConfigError) as e3:
            await run_report(
                session,
                tenant_id=tid,
                dataset_code="employees_training",
                config={"filters": [{"field": "person_name", "op": "gte", "value": "x"}]},
                limit=1,
            )
        assert e3.value.code == "filter_op_invalid"
        with pytest.raises(ReportConfigError) as e4:
            await run_report(
                session,
                tenant_id=tid,
                dataset_code="employees_training",
                config={
                    "group_by": ["course_name"],
                    "aggregates": [{"fn": "sum", "field": "course_name"}],
                },
                limit=1,
            )
        assert e4.value.code == "aggregate_not_allowed"
        with pytest.raises(ReportConfigError) as e5:
            await run_report(
                session,
                tenant_id=tid,
                dataset_code="employees_training",
                config={"sort": [{"field": "bogus", "dir": "asc"}]},
                limit=1,
            )
        assert e5.value.code == "sort_unknown"
        # validate_config — та же валидация без исполнения SQL
        with pytest.raises(ReportConfigError):
            validate_config("employees_training", {"columns": ["bogus"]})
        validate_config("employees_training", {"columns": ["person_name"]})  # не бросает


@pytest.mark.asyncio
async def test_contains_filter_binds_metacharacters(sessionmaker, data_factory: TestDataFactory):
    from app.modules.report_builder.engine import run_report

    async with sessionmaker() as session:
        tid = await _seed_training(session, data_factory)
        result = await run_report(
            session,
            tenant_id=tid,
            dataset_code="employees_training",
            config={
                "columns": ["course_name"],
                "filters": [{"field": "course_name", "op": "contains", "value": "хран"}],
            },
            limit=100,
        )
        assert result.total == 2  # обе «Охрана труда»
        # метасимволы связаны bind-параметром — ни исключения, ни инъекции
        hostile = await run_report(
            session,
            tenant_id=tid,
            dataset_code="employees_training",
            config={
                "columns": ["course_name"],
                "filters": [{"field": "course_name", "op": "contains", "value": "100%';DROP"}],
            },
            limit=100,
        )
        assert hostile.total == 0


@pytest.mark.asyncio
async def test_in_filter_on_enum(sessionmaker, data_factory: TestDataFactory):
    from app.modules.report_builder.engine import run_report

    async with sessionmaker() as session:
        tid = await _seed_training(session, data_factory)
        result = await run_report(
            session,
            tenant_id=tid,
            dataset_code="employees_training",
            config={
                "columns": ["course_name"],
                "filters": [{"field": "status", "op": "in", "value": ["completed"]}],
            },
            limit=100,
        )
        assert result.total == 2


@pytest.mark.asyncio
async def test_sum_aggregate_success(sessionmaker, data_factory: TestDataFactory):
    # Срез-134: набор строк «риски» строился по реестру `risk` — таблице, в
    # которую продукт не пишет никогда (срез-131 перевёл его на живые оценки).
    # Сеять надо тем же способом, каким данные создаёт продукт.
    from app.models.risk import RiskAssessment, RiskHazard
    from app.modules.report_builder.engine import run_report

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        company = Company(tenant_id=tid, name="ООО Вектор")
        session.add(company)
        await session.flush()

        def assessment(code: str, title: str, probability: int, severity: int, score: int):
            hazard = RiskHazard(
                tenant_id=tid,
                code=code,
                title=title,
                module="ot",
                recommended_measures=[],
            )
            session.add(hazard)
            return hazard, score, probability, severity

        prepared = [
            assessment("HZ-N", "Шум", 2, 3, 6),
            assessment("HZ-V", "Вибрация", 3, 3, 9),
        ]
        await session.flush()
        for hazard, score, probability, severity in prepared:
            session.add(
                RiskAssessment(
                    tenant_id=tid,
                    assessment_key=hazard.code,
                    assessment_version=1,
                    methodology_version=1,
                    company_id=company.id,
                    hazard_id=hazard.id,
                    severity_before=severity,
                    likelihood_before=probability,
                    score_before=score,
                    band_before="medium",
                    severity_after=severity,
                    likelihood_after=probability,
                    score_after=score,
                    band_after="medium",
                )
            )
        await session.commit()
        result = await run_report(
            session,
            tenant_id=tid,
            dataset_code="risks",
            config={
                "group_by": ["company_name"],
                "aggregates": [{"fn": "sum", "field": "level"}],
            },
            limit=100,
        )
        assert [(c.key, c.label) for c in result.columns] == [
            ("company_name", "Компания"),
            ("sum_level", "Сумма: Уровень"),
        ]
        assert result.rows[0]["sum_level"] == 15


@pytest.mark.asyncio
async def test_datetime_gte_filter(sessionmaker, data_factory: TestDataFactory):
    from app.modules.report_builder.engine import run_report

    async with sessionmaker() as session:
        tid = await _seed_training(session, data_factory)
        result = await run_report(
            session,
            tenant_id=tid,
            dataset_code="employees_training",
            config={
                "columns": ["course_name"],
                "filters": [
                    {
                        "field": "expires_at",
                        "op": "gte",
                        "value": (NOW + timedelta(days=1)).isoformat(),
                    }
                ],
            },
            limit=100,
        )
        assert result.total == 1
        assert result.rows[0]["course_name"] == "Первая помощь"
