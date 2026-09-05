from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import MappingProxyType, SimpleNamespace

import pytest
from sqlalchemy import Column, String, Table, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.routes.workspace import (
    role_workspace_summary,
    workspace_attention,
    workspace_task_inbox,
)
from app.core.security import AccessContext
from app.db.session import SharedBase, TenantBase
from app.models.briefings import BriefingEntry, BriefingJournal
from app.models.civil_defense import CivilDefenseDrill
from app.models.ecology import EmissionNorm, EmissionSource, EnvironmentalFacility
from app.models.feature import Feature, FeatureEnablement
from app.models.industrial_safety import HazardousFacility, TechnicalDevice
from app.models.medical import MedicalExam
from app.models.models import (
    ComplianceDeadline,
    OfflineSyncBatch,
    Person,
    PPEIssue,
    PPEIssueStatus,
    TrainingCertificate,
    TrainingEnrollment,
    TrainingProgram,
)
from app.models.obligations import Task, TaskPriority, TaskStatus
from app.models.road_safety import Driver, Vehicle


@pytest.fixture()
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    if "tenant" not in TenantBase.metadata.tables:
        Table("tenant", TenantBase.metadata, Column("id", String(36), primary_key=True))
    async with engine.begin() as conn:
        # Флаги модулей живут в общей схеме: без неё применимость дисциплин
        # (срез-56) упала бы на «no such table: feature».
        await conn.run_sync(SharedBase.metadata.create_all)
        await conn.run_sync(TenantBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


#: Дисциплины Доп. №1 — продаваемые модули; без выдачи их строк в сводке нет
#: (BIZ-61 умолчание «выключено», срез-56).
DISCIPLINE_MODULES = ("fire_safety", "industrial_safety", "ecology", "civil_defense", "road_safety")


async def _grant_modules(session, tenant_id: str, codes=DISCIPLINE_MODULES, *, on=True) -> None:
    for code in codes:
        feature = (
            await session.execute(select(Feature).where(Feature.code == code))
        ).scalar_one_or_none()
        if feature is None:
            feature = Feature(code=code, title=code)
            session.add(feature)
            await session.flush()
        session.add(FeatureEnablement(tenant_id=tenant_id, feature_id=feature.id, on=on))
    await session.flush()


def _access(user_id: str, role: str, tenant_id: str, tenant_slug: str) -> AccessContext:
    user = SimpleNamespace(
        id=user_id,
        email=f"{user_id}@tenant.test",
        role=SimpleNamespace(value=role),
        company_id=None,
    )
    return AccessContext(
        user=user,
        claims=MappingProxyType(
            {
                "sub": user_id,
                "tenant": tenant_slug,
                "tenant_id": tenant_id,
                "role": role,
                "roles": [role],
            }
        ),
        tenant_slug=tenant_slug,
        tenant_id=tenant_id,
        company_id=None,
    )


@pytest.mark.asyncio
async def test_workspace_attention_returns_overdue_deadlines_and_sync_counts(db_session) -> None:
    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    access = _access("user-1", "admin", tenant.id, tenant.slug)
    now = datetime.now(timezone.utc)

    db_session.add_all(
        [
            Task(
                tenant_id=tenant.id,
                title="Overdue task",
                status=TaskStatus.OPEN,
                priority=TaskPriority.HIGH,
                due_at=now - timedelta(days=1),
                assignee_id=access.user.id,
            ),
            ComplianceDeadline(
                tenant_id=tenant.id,
                entity_type="training",
                entity_id="tr-1",
                due_at=now - timedelta(hours=1),
                status="overdue",
            ),
            OfflineSyncBatch(
                tenant_id=tenant.id,
                user_id=access.user.id,
                device_id="d-1",
                entity_type="incident",
                status="failed",
                payload={"id": "1"},
                error_payload={"error": "conflict"},
            ),
        ]
    )
    await db_session.commit()

    payload = await workspace_attention(tenant=tenant, session=db_session, access=access, limit=20)

    assert payload.summary.overdue_tasks == 1
    assert payload.summary.overdue_deadlines == 1
    assert payload.summary.failed_sync_batches == 1
    assert payload.summary.readiness_blockers >= 1
    assert payload.items
    assert any(blocker.code == "templates_not_ready" for blocker in payload.blockers)
    assert any("блокеры готовности" in rec for rec in payload.recommendations)
    assert any("просроченные задачи" in rec for rec in payload.recommendations)


# ── BIZ-54-57 срез-73: просрочка контрольных сроков считается по времени ──────


@pytest.mark.asyncio
async def test_attention_counts_stale_upcoming_deadline_as_overdue(db_session) -> None:
    """Статус `overdue` пишет только ручной пересчёт сертификатов. Без него строка
    `upcoming` с прошедшей датой всё равно просрочена — и Центр внимания, и сводка
    роли, и календарь считают её по одной формуле (разд. 57.2). Закрытые не считаются."""
    from app.services.calendar_aggregator import CalendarAggregatorService

    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    access = _access("user-1", "admin", tenant.id, tenant.slug)
    now = datetime.now(timezone.utc)

    db_session.add_all(
        [
            ComplianceDeadline(
                tenant_id=tenant.id,
                entity_type="certificate",
                entity_id="cert-stale",
                due_at=now - timedelta(hours=1),
                status="upcoming",  # пересчёт не запускали — статус устарел
            ),
            ComplianceDeadline(
                tenant_id=tenant.id,
                entity_type="certificate",
                entity_id="cert-future",
                due_at=now + timedelta(days=3),
                status="upcoming",
            ),
            ComplianceDeadline(
                tenant_id=tenant.id,
                entity_type="certificate",
                entity_id="cert-done",
                due_at=now - timedelta(days=2),
                status="completed",
            ),
        ]
    )
    await db_session.commit()

    attention = await workspace_attention(
        tenant=tenant, session=db_session, access=access, limit=20
    )
    summary = await role_workspace_summary(tenant=tenant, session=db_session, access=access)
    calendar = await CalendarAggregatorService(tenant_id=tenant.id, db=db_session).list_events(
        source_types=("compliance_deadline",)
    )
    calendar_overdue = {c.source_type: c.overdue_count for c in calendar.by_source}

    assert attention.summary.overdue_deadlines == 1
    assert summary.overdue_deadlines == 1
    assert calendar_overdue["compliance_deadline"] == 1


# ── BIZ-54-57 срез-1: дисциплины в Центре внимания (Доп. №1 разд. 57.2) ──────


def _person(tenant_id: str, *, email: str | None = None, **extra):
    return Person(
        tenant_id=tenant_id,
        company_id="company-1",
        first_name="Иван",
        last_name="Иванов",
        email=email,
        **extra,
    )


@pytest.mark.asyncio
async def test_attention_shows_overdue_medical_with_discipline(db_session) -> None:
    """Просроченный медосмотр попадает в ленту внимания и размечен дисциплиной.

    До этого среза items собирались ТОЛЬКО из задач: медосмотр, СИЗ и обучение
    в Центр внимания не попадали никогда, хотя агрегатор их уже считал.
    """

    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    access = _access("user-1", "admin", tenant.id, tenant.slug)
    today = datetime.now(timezone.utc).date()

    person = _person(tenant.id)
    db_session.add(person)
    await db_session.flush()
    db_session.add(
        MedicalExam(
            tenant_id=tenant.id,
            person_id=person.id,
            exam_type="периодический",
            exam_date=today - timedelta(days=400),
            valid_until=today - timedelta(days=35),
        )
    )
    await db_session.commit()

    payload = await workspace_attention(tenant=tenant, session=db_session, access=access)

    medical_items = [item for item in payload.items if item.discipline == "medical"]
    assert medical_items, "просроченный медосмотр обязан попасть в Центр внимания"
    assert medical_items[0].severity == "critical"
    assert medical_items[0].item_type == "medical_exam"
    assert any("Просрочено по дисциплинам" in rec for rec in payload.recommendations)


@pytest.mark.asyncio
async def test_attention_reports_unmeasured_disciplines_honestly(db_session) -> None:
    """Пять дисциплин ТЗ без данных отдаются с причиной, а не нулём.

    Ноль по неизмеряемой дисциплине читался бы как «нарушений нет» — это ложь
    вместо «мы это не считаем» (правило not_measured из BIZ-51).
    """

    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    access = _access("user-1", "admin", tenant.id, tenant.slug)
    # медосмотры — тоже модуль; без выдачи пустая строка «Медосмотры» скрыта
    await _grant_modules(db_session, tenant.id, (*DISCIPLINE_MODULES, "medical"))
    await db_session.commit()

    payload = await workspace_attention(tenant=tenant, session=db_session, access=access)

    by_code = {row.code: row for row in payload.disciplines}
    assert len(payload.disciplines) == 8, "все дисциплины ТЗ обязаны быть в ответе"
    assert payload.not_applicable is None
    for code in ("fire_safety", "industrial_safety", "ecology", "civil_defense", "road_safety"):
        assert by_code[code].measured is False
        assert by_code[code].reason and "не ведётся" in by_code[code].reason
    for code in ("medical", "ppe", "training"):
        assert by_code[code].measured is True
        assert by_code[code].reason is None
    # Источники без дисциплины названы, а не спрятаны.
    assert payload.unclassified_sources
    assert any("Наряд-допуск" in reason for reason in payload.unclassified_sources)


@pytest.mark.asyncio
async def test_attention_hides_empty_disciplines_outside_edition_but_keeps_facts(
    db_session,
) -> None:
    """BIZ-54-57 срез-56, приёмка §58.3: модуль не выдан — пустой строки нет,
    строка с просрочкой остаётся, скрытое названо фразой."""

    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    access = _access("user-1", "admin", tenant.id, tenant.slug)
    today = datetime.now(timezone.utc).date()
    # выдано только два из пяти; медосмотры не выданы, но просрочка есть
    await _grant_modules(db_session, tenant.id, ("fire_safety", "industrial_safety"))
    person = _person(tenant.id)
    db_session.add(person)
    await db_session.flush()
    db_session.add(
        MedicalExam(
            tenant_id=tenant.id,
            person_id=person.id,
            exam_type="периодический",
            exam_date=today - timedelta(days=400),
            valid_until=today - timedelta(days=35),
        )
    )
    await db_session.commit()

    payload = await workspace_attention(tenant=tenant, session=db_session, access=access)

    codes = [row.code for row in payload.disciplines]
    assert codes == ["medical", "ppe", "training", "fire_safety", "industrial_safety"]
    medical = next(row for row in payload.disciplines if row.code == "medical")
    assert medical.overdue == 1, "факт остаётся, даже если модуль не куплен"
    assert payload.not_applicable == (
        "Вне редакции арендатора (модуль не выдан или выключен): Экология, ГО и ЧС, БДД; "
        "Медосмотры — модуль не выдан или выключен, но открытые записи есть и показаны как факты"
    )
    assert any("Просрочено по дисциплинам: Медосмотры" in rec for rec in payload.recommendations)


@pytest.mark.asyncio
async def test_attention_aggregates_epb_drills_and_vehicle_documents(db_session) -> None:
    """BIZ-54-57 срез-57, разд. 57.2: «просрочена ЭПБ на ОПО», «не проведены
    учения по ГО», «просрочен техосмотр ТС» — в одном Центре внимания.

    До среза у трёх дисциплин не было ни одного источника сроков: модули
    считали просрочки у себя, а строки «Промышленная безопасность», «ГО и ЧС»
    и «БДД» в центре всегда стояли по нулям.
    """

    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    access = _access("user-1", "admin", tenant.id, tenant.slug)
    today = datetime.now(timezone.utc).date()
    await _grant_modules(db_session, tenant.id, (*DISCIPLINE_MODULES, "medical"))
    facility = HazardousFacility(
        tenant_id=tenant.id, name="Котельная", register_number="А01-1", hazard_class="III"
    )
    db_session.add(facility)
    await db_session.flush()
    db_session.add_all(
        [
            TechnicalDevice(
                tenant_id=tenant.id,
                facility_id=facility.id,
                kind="boiler",
                name="Котёл №1",
                epb_valid_until=today - timedelta(days=10),
            ),
            CivilDefenseDrill(
                tenant_id=tenant.id,
                kind="evacuation",
                title="Тренировка по эвакуации",
                planned_on=today - timedelta(days=7),
            ),
            Vehicle(
                tenant_id=tenant.id,
                plate_number="А123БВ77",
                brand_model="ГАЗель",
                kind="truck",
                inspection_due=today - timedelta(days=1),
                insurance_due=today + timedelta(days=2),
            ),
        ]
    )
    await db_session.commit()

    payload = await workspace_attention(tenant=tenant, session=db_session, access=access)

    by_code = {row.code: row for row in payload.disciplines}
    assert by_code["industrial_safety"].overdue == 1
    assert by_code["civil_defense"].overdue == 1
    assert by_code["road_safety"].overdue == 1
    assert by_code["road_safety"].due_soon == 1, "ОСАГО через два дня — «скоро срок»"
    # поимённого учёта у этих дисциплин по-прежнему нет — причина остаётся
    assert by_code["industrial_safety"].measured is False
    titles = {item.item_type: item.title for item in payload.items}
    assert titles["industrial_safety_epb"] == "ЭПБ: Котёл №1"
    assert titles["civil_defense_drill"] == "Учение ГО: Тренировка по эвакуации"
    assert titles["road_safety_vehicle"] in {"Техосмотр ТС: А123БВ77", "Полис ОСАГО: А123БВ77"}
    rec = next(r for r in payload.recommendations if r.startswith("Просрочено по дисциплинам"))
    for title in ("Промышленная безопасность", "ГО и ЧС", "БДД"):
        assert title in rec, rec
    # приёмка §58.3: дедлайны минимум из трёх дисциплин — здесь их три без
    # единого медосмотра, СИЗ или обучения
    assert len({item.discipline for item in payload.items if item.discipline}) >= 3


@pytest.mark.asyncio
async def test_attention_ecology_overdue_is_counted_not_zero(db_session) -> None:
    """Сторож против потери честных COUNT'ов у дисциплин без поимённого учёта.

    Словарь счётчиков заводился только по измеримым дисциплинам, и просроченное
    разрешение на выброс в строке «Экология» стояло нулём, хотя агрегатор его
    посчитал (срез-57 нашёл это на сверке разд. 57.2).
    """

    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    access = _access("user-1", "admin", tenant.id, tenant.slug)
    today = datetime.now(timezone.utc).date()
    await _grant_modules(db_session, tenant.id, (*DISCIPLINE_MODULES, "medical"))
    facility = EnvironmentalFacility(
        tenant_id=tenant.id, name="Площадка", register_number="12-1", category="II"
    )
    db_session.add(facility)
    await db_session.flush()
    source = EmissionSource(
        tenant_id=tenant.id,
        facility_id=facility.id,
        source_number="0001",
        name="Труба",
        kind="organized",
    )
    db_session.add(source)
    await db_session.flush()
    db_session.add(
        EmissionNorm(
            tenant_id=tenant.id,
            source_id=source.id,
            substance="Азота диоксид",
            limit_grams_per_second=1,
            permit_number="РВ-1",
            valid_until=today - timedelta(days=3),
        )
    )
    await db_session.commit()

    payload = await workspace_attention(tenant=tenant, session=db_session, access=access)

    ecology = next(row for row in payload.disciplines if row.code == "ecology")
    assert ecology.overdue == 1
    assert any("Экология" in rec for rec in payload.recommendations)


@pytest.mark.asyncio
async def test_attention_fire_briefing_counts_as_fire_safety_not_training(db_session) -> None:
    """BIZ-54-57 срез-58: противопожарный инструктаж — в строку «Пожарная
    безопасность», а не в «Обучение» скопом.

    До среза источник инструктажей целиком был размечен обучением: просроченный
    ПТМ и просроченный повторный инструктаж по охране труда давали «Обучение:
    2», а строка пожарной безопасности сроков «не имела» вовсе. Дисциплина
    инструктажа зависит от его вида (разд. 54.1 / 56.2), и центр внимания
    обязан это видеть — и в счётчиках (честный COUNT по видам), и в пунктах.
    """

    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    access = _access("user-1", "admin", tenant.id, tenant.slug)
    now = datetime.now(timezone.utc)
    await _grant_modules(db_session, tenant.id, (*DISCIPLINE_MODULES, "medical"))
    person = _person(tenant.id)
    journal = BriefingJournal(tenant_id=tenant.id, code="J-1", title="Журнал", journal_type="fire")
    db_session.add_all([person, journal])
    await db_session.flush()

    def entry(kind: str, *, days_ago: int) -> BriefingEntry:
        return BriefingEntry(
            tenant_id=tenant.id,
            briefing_journal_id=journal.id,
            person_id=person.id,
            briefing_type=kind,
            briefing_date=now - timedelta(days=400),
            valid_until=now - timedelta(days=days_ago),
            status="done",
        )

    db_session.add_all(
        [
            entry("fire_ptm", days_ago=35),
            entry("fire_repeat", days_ago=10),
            entry("repeat", days_ago=20),
            entry("road_pre_trip", days_ago=1),
        ]
    )
    await db_session.commit()

    payload = await workspace_attention(tenant=tenant, session=db_session, access=access)

    by_code = {row.code: row for row in payload.disciplines}
    assert by_code["fire_safety"].overdue == 2, "ПТМ и противопожарный повторный"
    assert by_code["training"].overdue == 1, "только повторный по охране труда"
    assert by_code["road_safety"].overdue == 1, "предрейсовый — БДД"
    by_kind = {
        item.title: item.discipline for item in payload.items if item.item_type == "briefing_entry"
    }
    # срез-81: вид — словами, человек — в заголовке (раньше на экране был код)
    assert by_kind == {
        "Инструктаж: Пожарно-технический минимум (ПТМ) — Иванов Иван": "fire_safety",
        "Инструктаж: Противопожарный повторный — Иванов Иван": "fire_safety",
        "Инструктаж: Повторный — Иванов Иван": "training",
        "Инструктаж: Предрейсовый инструктаж — Иванов Иван": "road_safety",
    }
    rec = next(r for r in payload.recommendations if r.startswith("Просрочено по дисциплинам"))
    assert "Пожарная безопасность" in rec, rec


@pytest.mark.asyncio
async def test_attention_worker_without_person_sees_no_foreign_records(db_session) -> None:
    """Рабочая роль без связанного сотрудника не получает ЧУЖИХ записей.

    Связи User→Person в моделях нет, она ищется по e-mail. Нет совпадения —
    персональных записей нет; откат на общий список арендатора был бы утечкой
    персональных данных.
    """

    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    worker = _access("worker-1", "worker", tenant.id, tenant.slug)
    today = datetime.now(timezone.utc).date()

    stranger = _person(tenant.id, email="stranger@tenant.test")
    db_session.add(stranger)
    await db_session.flush()
    db_session.add(
        MedicalExam(
            tenant_id=tenant.id,
            person_id=stranger.id,
            exam_type="периодический",
            exam_date=today - timedelta(days=400),
            valid_until=today - timedelta(days=35),
        )
    )
    await db_session.commit()

    payload = await workspace_attention(tenant=tenant, session=db_session, access=worker)

    assert not [
        item for item in payload.items if item.discipline == "medical"
    ], "рабочая роль без своей кадровой записи не должна видеть чужой медосмотр"


@pytest.mark.asyncio
async def test_attention_ordinary_role_does_not_see_foreign_medical(db_session) -> None:
    """Роль без доступа к профильным экранам не видит ЧУЖИХ медосмотров.

    Найдено адверсарной проверкой среза: ручка висит на ``rbac()`` без ролей,
    поэтому сотрудник, ученик или бухгалтер получали построчный перечень
    медосмотров и выдач СИЗ по всему арендатору — обход прав профильных
    модулей, где СИЗ отдаётся одному администратору.
    """

    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    today = datetime.now(timezone.utc).date()

    stranger = _person(tenant.id, email="stranger@tenant.test")
    db_session.add(stranger)
    await db_session.flush()
    db_session.add(
        MedicalExam(
            tenant_id=tenant.id,
            person_id=stranger.id,
            exam_type="периодический",
            exam_date=today - timedelta(days=400),
            valid_until=today - timedelta(days=35),
        )
    )
    await db_session.commit()

    for role in ("employee", "student", "accountant", "contractor_inspector"):
        access = _access(f"user-{role}", role, tenant.id, tenant.slug)
        payload = await workspace_attention(tenant=tenant, session=db_session, access=access)
        assert not [
            item for item in payload.items if item.discipline == "medical"
        ], f"роль {role} не должна видеть чужой медосмотр"


@pytest.mark.asyncio
async def test_attention_counts_come_from_totals_not_from_page(db_session) -> None:
    """Число просрочек — это количество, а не размер показанной страницы.

    Найдено адверсарной проверкой: счётчики считались по уже обрезанному
    лимитом списку, поэтому при тридцати семи просрочках и лимите 5 экран
    писал «5», а дисциплина, чьи строки не влезли, уходила в зелёный ноль.
    """

    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    access = _access("user-1", "admin", tenant.id, tenant.slug)
    today = datetime.now(timezone.utc).date()

    person = _person(tenant.id)
    db_session.add(person)
    await db_session.flush()
    for shift in range(8):
        db_session.add(
            MedicalExam(
                tenant_id=tenant.id,
                person_id=person.id,
                exam_type="периодический",
                exam_date=today - timedelta(days=400 + shift),
                valid_until=today - timedelta(days=35 + shift),
            )
        )
    await db_session.commit()

    payload = await workspace_attention(tenant=tenant, session=db_session, access=access, limit=3)

    medical = next(row for row in payload.disciplines if row.code == "medical")
    assert medical.overdue == 8, "счётчик обязан показывать все просрочки, а не страницу"
    assert len([item for item in payload.items if item.discipline == "medical"]) == 3
    assert payload.items_truncated is True, "обрезанный список обязан назвать себя обрезанным"


@pytest.mark.asyncio
async def test_attention_closed_ppe_is_not_overdue(db_session) -> None:
    """Возвращённая выдача СИЗ с прошедшим сроком просрочкой не считается.

    Найдено адверсарной проверкой: признак брался у полосы SLA, а она означает
    лишь «дата в прошлом» — закрытые записи попадали бы в просрочку.
    """

    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    access = _access("user-1", "admin", tenant.id, tenant.slug)
    now = datetime.now(timezone.utc)

    person = _person(tenant.id)
    db_session.add(person)
    await db_session.flush()
    db_session.add(
        PPEIssue(
            tenant_id=tenant.id,
            person_id=person.id,
            item_name="Каска",
            quantity=1,
            status=PPEIssueStatus.RETURNED,
            issued_at=now - timedelta(days=400),
            expires_at=now - timedelta(days=30),
            returned_at=now - timedelta(days=25),
        )
    )
    await db_session.commit()

    payload = await workspace_attention(tenant=tenant, session=db_session, access=access)

    ppe_row = next(row for row in payload.disciplines if row.code == "ppe")
    assert ppe_row.overdue == 0, "возвращённый СИЗ не просрочен — он уже не у человека"


@pytest.mark.asyncio
async def test_attention_worker_sees_own_records_only(db_session) -> None:
    """Рабочая роль со своей кадровой записью видит СВОЙ медосмотр и только его."""

    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    worker = _access("worker-1", "worker", tenant.id, tenant.slug)
    today = datetime.now(timezone.utc).date()

    mine = _person(tenant.id, email=worker.user.email)
    stranger = _person(tenant.id, email="stranger@tenant.test")
    db_session.add_all([mine, stranger])
    await db_session.flush()
    db_session.add_all(
        [
            MedicalExam(
                tenant_id=tenant.id,
                person_id=mine.id,
                exam_type="периодический",
                exam_date=today - timedelta(days=400),
                valid_until=today - timedelta(days=35),
            ),
            MedicalExam(
                tenant_id=tenant.id,
                person_id=stranger.id,
                exam_type="периодический",
                exam_date=today - timedelta(days=400),
                valid_until=today - timedelta(days=40),
            ),
        ]
    )
    await db_session.commit()

    payload = await workspace_attention(tenant=tenant, session=db_session, access=worker)

    medical_items = [item for item in payload.items if item.discipline == "medical"]
    assert len(medical_items) == 1, "видна ровно одна запись — своя"
    assert medical_items[0].entity_id == str(
        (await db_session.execute(select(MedicalExam.id).where(MedicalExam.person_id == mine.id)))
        .scalars()
        .first()
    )


@pytest.mark.asyncio
async def test_attention_worker_sees_own_driver_license_only(db_session) -> None:
    """Срез-59 (разд. 56.2): удостоверение — поимённый срок БДД.

    Рабочая роль видит просроченное СВОЁ удостоверение в личном центре
    внимания (строка «БДД», пункт с дисциплиной), а чужое — нет. Документы
    машин при этом в личный список не входят вовсе: они про организацию.
    """

    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    worker = _access("worker-1", "worker", tenant.id, tenant.slug)
    today = datetime.now(timezone.utc).date()
    await _grant_modules(db_session, tenant.id, ("road_safety",))

    mine = _person(tenant.id, email=worker.user.email)
    stranger = _person(tenant.id, email="stranger@tenant.test")
    db_session.add_all([mine, stranger])
    await db_session.flush()
    db_session.add_all(
        [
            Driver(
                tenant_id=tenant.id,
                person_id=mine.id,
                license_number="77 01",
                categories=["B"],
                license_due=today - timedelta(days=3),
            ),
            Driver(
                tenant_id=tenant.id,
                person_id=stranger.id,
                license_number="77 02",
                categories=["B"],
                license_due=today - timedelta(days=3),
            ),
            Vehicle(
                tenant_id=tenant.id,
                plate_number="А123БВ77",
                brand_model="ГАЗель",
                kind="truck",
                inspection_due=today - timedelta(days=3),
            ),
        ]
    )
    await db_session.commit()

    payload = await workspace_attention(tenant=tenant, session=db_session, access=worker)

    road = [item for item in payload.items if item.discipline == "road_safety"]
    assert [item.item_type for item in road] == ["road_safety_driver"]
    assert road[0].title == "Водительское удостоверение: Иванов Иван"
    by_code = {row.code: row for row in payload.disciplines}
    assert by_code["road_safety"].overdue == 1, "своё — да, чужое и машина — нет"


@pytest.mark.asyncio
async def test_attention_worker_sees_own_training_certificate_only(db_session) -> None:
    """Разд. 57.2 (срез-75): истёкшее удостоверение — событие дисциплины «Обучение».

    Рабочий видит только своё: чужое удостоверение того же арендатора в ленту
    и в итог строки «Обучение» не попадает (``PERSON_SCOPED_SOURCES``).
    """

    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    worker = _access("worker-1", "worker", tenant.id, tenant.slug)
    today = datetime.now(timezone.utc).date()

    mine = _person(tenant.id, email=worker.user.email)
    stranger = _person(tenant.id, email="stranger@tenant.test")
    program = TrainingProgram(
        tenant_id=tenant.id, code="ОТ-1", title="Охрана труда", category="ot", kind="program"
    )
    db_session.add_all([mine, stranger, program])
    await db_session.flush()
    db_session.add_all(
        [
            TrainingCertificate(
                tenant_id=tenant.id,
                number="УД-1",
                training_program_id=program.id,
                person_id=mine.id,
                issued_at=today - timedelta(days=400),
                valid_until=today - timedelta(days=3),
            ),
            TrainingCertificate(
                tenant_id=tenant.id,
                number="УД-2",
                training_program_id=program.id,
                person_id=stranger.id,
                issued_at=today - timedelta(days=400),
                valid_until=today - timedelta(days=3),
            ),
        ]
    )
    await db_session.commit()

    payload = await workspace_attention(tenant=tenant, session=db_session, access=worker)

    training = [item for item in payload.items if item.item_type == "training_certificate"]
    assert [item.title for item in training] == ["Удостоверение: Охрана труда — Иванов Иван"]
    assert training[0].discipline == "training"
    by_code = {row.code: row for row in payload.disciplines}
    assert by_code["training"].overdue == 1, "своё — да, чужое — нет"


@pytest.mark.asyncio
async def test_attention_worker_sees_own_training_enrollment_only(db_session) -> None:
    """Разд. 57.2 (срез-77): просроченное назначение обучения — событие «Обучение».

    Та же формула, что у блокера готовности ``training_overdue``. Рабочий видит
    только своё назначение; чужое того же арендатора в ленту и в итог строки
    не попадает (``PERSON_SCOPED_SOURCES``).
    """

    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    worker = _access("worker-1", "worker", tenant.id, tenant.slug)
    now = datetime.now(timezone.utc)

    mine = _person(tenant.id, email=worker.user.email)
    stranger = _person(tenant.id, email="stranger@tenant.test")
    program = TrainingProgram(
        tenant_id=tenant.id, code="ОТ-1", title="Охрана труда", category="ot", kind="program"
    )
    db_session.add_all([mine, stranger, program])
    await db_session.flush()
    db_session.add_all(
        [
            TrainingEnrollment(
                tenant_id=tenant.id,
                training_program_id=program.id,
                person_id=mine.id,
                status="assigned",
                due_at=now - timedelta(days=3),
            ),
            TrainingEnrollment(
                tenant_id=tenant.id,
                training_program_id=program.id,
                person_id=stranger.id,
                status="in_progress",
                due_at=now - timedelta(days=3),
            ),
        ]
    )
    await db_session.commit()

    payload = await workspace_attention(tenant=tenant, session=db_session, access=worker)

    training = [item for item in payload.items if item.item_type == "training_enrollment"]
    assert [item.title for item in training] == ["Назначение: Охрана труда — Иванов Иван"]
    assert training[0].discipline == "training"
    by_code = {row.code: row for row in payload.disciplines}
    assert by_code["training"].overdue == 1, "своё — да, чужое — нет"


@pytest.mark.asyncio
async def test_attention_orders_by_severity_then_due(db_session) -> None:
    """Разд. 57.2: «всё в одном месте, с приоритизацией» (срез-70).

    До среза лента шла «сначала все задачи, потом дисциплины»: просроченная
    ЭПБ на ОПО (critical) стояла под открытой задачей без срока (medium), и
    специалист начинал день не с того, что горит. Теперь порядок: тяжесть →
    ближайший срок; без срока — в конец.
    """

    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    access = _access("user-1", "admin", tenant.id, tenant.slug)
    now = datetime.now(timezone.utc)
    today = now.date()
    await _grant_modules(db_session, tenant.id, ("industrial_safety",))
    facility = HazardousFacility(
        tenant_id=tenant.id, name="Котельная", register_number="А01-1", hazard_class="III"
    )
    db_session.add(facility)
    await db_session.flush()
    db_session.add_all(
        [
            # Задачи заводятся в «неправильном» порядке нарочно: без срока —
            # первой, чтобы сортировка не выглядела случайным совпадением.
            Task(
                tenant_id=tenant.id,
                title="Открытая задача без срока",
                status=TaskStatus.OPEN,
                priority=TaskPriority.MEDIUM,
                assignee_id=access.user.id,
            ),
            Task(
                tenant_id=tenant.id,
                title="Задача на завтра",
                status=TaskStatus.OPEN,
                priority=TaskPriority.MEDIUM,
                due_at=now + timedelta(days=1),
                assignee_id=access.user.id,
            ),
            Task(
                tenant_id=tenant.id,
                title="Задача просрочена вчера",
                status=TaskStatus.OPEN,
                priority=TaskPriority.MEDIUM,
                due_at=now - timedelta(days=1),
                assignee_id=access.user.id,
            ),
            TechnicalDevice(
                tenant_id=tenant.id,
                facility_id=facility.id,
                kind="boiler",
                name="Котёл №1",
                epb_valid_until=today - timedelta(days=10),
            ),
        ]
    )
    await db_session.commit()

    payload = await workspace_attention(tenant=tenant, session=db_session, access=access)

    assert [item.severity for item in payload.items] == ["critical", "critical", "high", "medium"]
    # Самое давнее просроченное — первым: ЭПБ (10 дней) выше задачи (1 день).
    assert payload.items[0].item_type == "industrial_safety_epb"
    assert payload.items[0].title == "ЭПБ: Котёл №1"
    assert payload.items[1].title == "Задача просрочена вчера"
    assert payload.items[2].title == "Задача на завтра"
    assert payload.items[-1].title == "Открытая задача без срока"


@pytest.mark.asyncio
async def test_workspace_task_inbox_worker_sees_only_own_tasks(db_session) -> None:
    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    worker = _access("worker-1", "worker", tenant.id, tenant.slug)
    now = datetime.now(timezone.utc)

    db_session.add_all(
        [
            Task(
                tenant_id=tenant.id,
                title="Worker task",
                status=TaskStatus.OPEN,
                priority=TaskPriority.MEDIUM,
                due_at=now + timedelta(hours=6),
                assignee_id=worker.user.id,
            ),
            Task(
                tenant_id=tenant.id,
                title="Other task",
                status=TaskStatus.OPEN,
                priority=TaskPriority.MEDIUM,
                due_at=now + timedelta(hours=12),
                assignee_id="another-user",
            ),
        ]
    )
    await db_session.commit()

    payload = await workspace_task_inbox(
        tenant=tenant,
        session=db_session,
        access=worker,
        limit=50,
        offset=0,
    )

    assert payload.total == 1
    assert len(payload.items) == 1
    assert payload.items[0].title == "Worker task"


@pytest.mark.asyncio
async def test_role_workspace_summary_for_manager_scopes_to_assignee(db_session) -> None:
    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A", is_active=True)
    manager = _access("manager-1", "line_manager", tenant.id, tenant.slug)
    now = datetime.now(timezone.utc)

    db_session.add_all(
        [
            Task(
                tenant_id=tenant.id,
                title="Own overdue task",
                status=TaskStatus.OPEN,
                priority=TaskPriority.HIGH,
                due_at=now - timedelta(hours=2),
                assignee_id=manager.user.id,
            ),
            Task(
                tenant_id=tenant.id,
                title="Other user task",
                status=TaskStatus.OPEN,
                priority=TaskPriority.MEDIUM,
                due_at=now + timedelta(hours=2),
                assignee_id="other-user",
            ),
        ]
    )
    await db_session.commit()

    payload = await role_workspace_summary(tenant=tenant, session=db_session, access=manager)

    assert payload.role == "line_manager"
    assert payload.open_tasks == 1
    assert payload.overdue_tasks == 1
    assert payload.open_incidents == 0
