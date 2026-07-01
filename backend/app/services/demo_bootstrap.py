"""Development demo data bootstrap routines."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import Settings
from app.db import aensure_tenant_schema, session_scope
from app.models.feature import Feature
from app.models.finance import Department
from app.models.models import (
    BriefingEntry,
    BriefingJournal,
    BriefingTemplate,
    Company,
    MedicalExamKind,
    MedicalFactor,
    MedicalNorm,
    Person,
    Position,
    PositionHazardLink,
    PPEIssue,
    PPEItem,
    PPENorm,
    Site,
    Tenant,
    TrainingCourse,
)
from app.models.risk import RiskHazard
from app.modules.contractors.models import (
    ComplianceStatus,
    ContractorDocument,
    ContractorDocumentRequirement,
    ContractorEmployee,
    ContractorRegistry,
)
from app.modules.packs.seeder import ensure_default_packs

logger = logging.getLogger(__name__)


async def _seed_contractor_documents(
    session, tenant_db_id: str, contractor_id: str, employee_id: str
) -> None:
    """Seed 3 demo documents: valid (org), expiring (employee), expired (employee)."""
    today = date.today()
    session.add(
        ContractorDocument(
            tenant_id=tenant_db_id,
            contractor_id=contractor_id,
            doc_type="sro",
            title="СРО допуск (демо)",
            valid_until=today + timedelta(days=180),
            status="active",
        )
    )
    session.add(
        ContractorDocument(
            tenant_id=tenant_db_id,
            contractor_id=contractor_id,
            employee_id=employee_id,
            doc_type="medical_cert",
            title="Медзаключение (истекает)",
            valid_until=today + timedelta(days=15),
            status="active",
        )
    )
    session.add(
        ContractorDocument(
            tenant_id=tenant_db_id,
            contractor_id=contractor_id,
            employee_id=employee_id,
            doc_type="access_permit",
            title="Допуск на объект (просрочен)",
            valid_until=today - timedelta(days=5),
            status="active",
        )
    )


async def _seed_contractor_requirements(session, tenant_db_id: str) -> None:
    """Seed 2 admission document requirements (idempotent on tenant+doc_type+scope)."""
    wanted = [("sro", "company"), ("medical_cert", "employee")]
    for doc_type, scope in wanted:
        existing = (
            await session.execute(
                select(ContractorDocumentRequirement).where(
                    ContractorDocumentRequirement.tenant_id == tenant_db_id,
                    ContractorDocumentRequirement.doc_type == doc_type,
                    ContractorDocumentRequirement.scope == scope,
                    ContractorDocumentRequirement.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                ContractorDocumentRequirement(
                    tenant_id=tenant_db_id,
                    doc_type=doc_type,
                    scope=scope,
                    mandatory=True,
                )
            )


async def _seed_ppe_demo(session, tenant_db_id: str, person, position_id: str) -> None:
    """Seed PPE norms/sizes/issues so the 766н card demos all line statuses.

    Idempotent: keyed lookups on (tenant, name/code) before each insert.
    Card outcome: каска=ok (активная выдача), перчатки=overdue (просрочена),
    очки=missing (норма без выдачи).
    """
    hazard = (
        await session.execute(
            select(RiskHazard).where(
                RiskHazard.tenant_id == tenant_db_id,
                RiskHazard.code == "demo_general",
            )
        )
    ).scalar_one_or_none()
    if hazard is None:
        hazard = RiskHazard(
            tenant_id=tenant_db_id, code="demo_general", title="Общие производственные факторы"
        )
        session.add(hazard)
        await session.flush()

    async def _ensure_item(name: str, wear_days: int) -> PPEItem:
        item = (
            await session.execute(
                select(PPEItem).where(
                    PPEItem.tenant_id == tenant_db_id,
                    PPEItem.name == name,
                    PPEItem.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if item is None:
            item = PPEItem(tenant_id=tenant_db_id, name=name, default_wear_days=wear_days)
            session.add(item)
            await session.flush()
        return item

    helmet = await _ensure_item("Каска защитная (демо)", 730)
    gloves = await _ensure_item("Перчатки защитные (демо)", 90)
    glasses = await _ensure_item("Очки защитные (демо)", 365)

    for item, qty, interval in ((helmet, 1, 730), (gloves, 2, 90), (glasses, 1, 365)):
        existing = (
            await session.execute(
                select(PPENorm).where(
                    PPENorm.tenant_id == tenant_db_id,
                    PPENorm.position_id == position_id,
                    PPENorm.hazard_id == hazard.id,
                    PPENorm.item_name == item.name,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                PPENorm(
                    tenant_id=tenant_db_id,
                    position_id=position_id,
                    hazard_id=hazard.id,
                    item_id=item.id,
                    item_name=item.name,
                    quantity=qty,
                    interval_days=interval,
                )
            )

    if not person.ppe_sizes:
        person.ppe_sizes = {
            "height": 178,
            "clothing_size": "52-54",
            "shoe_size": "43",
            "headgear_size": "58",
        }

    now = datetime.now(timezone.utc)
    existing_issue = (
        (
            await session.execute(
                select(PPEIssue).where(
                    PPEIssue.tenant_id == tenant_db_id,
                    PPEIssue.person_id == person.id,
                    PPEIssue.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .first()
    )
    if existing_issue is None:
        session.add(
            PPEIssue(  # активная, с сертификатом → строка ok
                tenant_id=tenant_db_id,
                person_id=person.id,
                item_id=helmet.id,
                item_name=helmet.name,
                quantity=1,
                issued_at=now,
                expires_at=now + timedelta(days=700),
                wear_days=730,
                status="issued",
                certificate_no="ЕАЭС RU С-RU.ДЕМО.В.00001/26",
            )
        )
        session.add(
            PPEIssue(  # просроченная → строка overdue
                tenant_id=tenant_db_id,
                person_id=person.id,
                item_id=gloves.id,
                item_name=gloves.name,
                quantity=2,
                issued_at=now - timedelta(days=120),
                expires_at=now - timedelta(days=30),
                wear_days=90,
                status="issued",
            )
        )
        # очки: норма есть, выдачи нет → строка missing


async def _seed_medical_factor_demo(session, tenant_db_id: str, position_id: str) -> None:
    """§9.2: seed one 29н factor, map the demo hazard to it, and link the hazard to
    the demo position — so the demo контингент/поименный список are non-empty
    factor-driven (no manual MedicalNorm needed). Idempotent (lookup-or-create each)."""
    hazard = (
        await session.execute(
            select(RiskHazard).where(
                RiskHazard.tenant_id == tenant_db_id,
                RiskHazard.code == "demo_general",
            )
        )
    ).scalar_one_or_none()
    if hazard is None:
        hazard = RiskHazard(
            tenant_id=tenant_db_id, code="demo_general", title="Общие производственные факторы"
        )
        session.add(hazard)
        await session.flush()
    if not hazard.medical_factor_code:
        hazard.medical_factor_code = "4.4"
    factor = (
        await session.execute(
            select(MedicalFactor).where(
                MedicalFactor.tenant_id == tenant_db_id,
                MedicalFactor.code == "4.4",
            )
        )
    ).scalar_one_or_none()
    if factor is None:
        session.add(
            MedicalFactor(
                tenant_id=tenant_db_id,
                code="4.4",
                name="Шум",
                category="factor",
                exam_kinds=[MedicalExamKind.PERIODIC.value],
                periodicity_months=12,
            )
        )
    link = (
        await session.execute(
            select(PositionHazardLink).where(
                PositionHazardLink.tenant_id == tenant_db_id,
                PositionHazardLink.position_id == position_id,
                PositionHazardLink.hazard_id == hazard.id,
            )
        )
    ).scalar_one_or_none()
    if link is None:
        session.add(
            PositionHazardLink(
                tenant_id=tenant_db_id,
                position_id=position_id,
                hazard_id=hazard.id,
            )
        )


async def _seed_briefing_code_flow_demo(session, tenant_db_id: str, person) -> None:
    """§6.9 Срез-3: seed a briefing template opted into code-flow signing
    (require_signature_code=True) + a journal + one assigned entry for the demo
    person, so the code-flow (sign-employee → confirm-code) is demoable out-of-box.
    Idempotent (lookup-or-create each)."""
    template = (
        await session.execute(
            select(BriefingTemplate).where(
                BriefingTemplate.tenant_id == tenant_db_id,
                BriefingTemplate.code == "demo-primary-code",
            )
        )
    ).scalar_one_or_none()
    if template is None:
        template = BriefingTemplate(
            tenant_id=tenant_db_id,
            code="demo-primary-code",
            title="Вводный инструктаж (с кодом)",
            briefing_type="primary",
            require_signature_code=True,
        )
        session.add(template)
        await session.flush()
    journal = (
        await session.execute(
            select(BriefingJournal).where(
                BriefingJournal.tenant_id == tenant_db_id,
                BriefingJournal.code == "demo-brf-journal",
            )
        )
    ).scalar_one_or_none()
    if journal is None:
        journal = BriefingJournal(
            tenant_id=tenant_db_id,
            code="demo-brf-journal",
            title="Журнал инструктажей (демо)",
            journal_type="workplace",
            status="active",
        )
        session.add(journal)
        await session.flush()
    entry = (
        await session.execute(
            select(BriefingEntry).where(
                BriefingEntry.tenant_id == tenant_db_id,
                BriefingEntry.briefing_journal_id == journal.id,
                BriefingEntry.person_id == person.id,
                BriefingEntry.briefing_template_id == template.id,
            )
        )
    ).scalar_one_or_none()
    if entry is None:
        session.add(
            BriefingEntry(
                tenant_id=tenant_db_id,
                person_id=person.id,
                briefing_journal_id=journal.id,
                briefing_template_id=template.id,
                briefing_type="primary",
                briefing_date=datetime.now(timezone.utc),
                status="assigned",
            )
        )


async def _seed_work_permit_confined_demo(session, tenant_db_id: str, person) -> None:
    """Демо-наряд ОЗП (902н) с газоанализом — печатается «из коробки». Идемпотентно."""
    from app.models.work_permit import WorkPermit, WorkPermitMember

    wp = (
        await session.execute(
            select(WorkPermit).where(
                WorkPermit.tenant_id == tenant_db_id,
                WorkPermit.number == "WP-OZP-DEMO",
            )
        )
    ).scalar_one_or_none()
    if wp is None:
        wp = WorkPermit(
            tenant_id=tenant_db_id,
            number="WP-OZP-DEMO",
            work_type="confined_space",
            zone_text="Колодец К-12, насосная станция",
            status="draft",
            type_specific={
                "gas_analysis": [{"parameter": "oxygen", "value": "20.9", "norm": "≥ 20"}],
                "ventilation": "forced",
            },
        )
        session.add(wp)
        await session.flush()
    member = (
        await session.execute(
            select(WorkPermitMember).where(
                WorkPermitMember.tenant_id == tenant_db_id,
                WorkPermitMember.work_permit_id == wp.id,
                WorkPermitMember.person_id == person.id,
                WorkPermitMember.role == "foreman",
            )
        )
    ).scalar_one_or_none()
    if member is None:
        session.add(
            WorkPermitMember(
                tenant_id=tenant_db_id, work_permit_id=wp.id, person_id=person.id, role="foreman"
            )
        )


async def _seed_work_permit_hot_work_demo(session, tenant_db_id: str, person) -> None:
    """Демо-наряд огневых работ (1479) со средствами пожаротушения и замером — печатается «из коробки». Идемпотентно."""
    from app.models.work_permit import WorkPermit, WorkPermitMember

    wp = (
        await session.execute(
            select(WorkPermit).where(
                WorkPermit.tenant_id == tenant_db_id,
                WorkPermit.number == "WP-HOT-DEMO",
            )
        )
    ).scalar_one_or_none()
    if wp is None:
        wp = WorkPermit(
            tenant_id=tenant_db_id,
            number="WP-HOT-DEMO",
            work_type="hot_work",
            zone_text="Эстакада №3, участок сварки",
            status="draft",
            type_specific={
                "fire_fighting_means": ["extinguisher_powder", "sand"],
                "gas_analysis": [{"parameter": "flammable", "value": "0", "norm": "≤ 10 % НКПР"}],
            },
        )
        session.add(wp)
        await session.flush()
    member = (
        await session.execute(
            select(WorkPermitMember).where(
                WorkPermitMember.tenant_id == tenant_db_id,
                WorkPermitMember.work_permit_id == wp.id,
                WorkPermitMember.person_id == person.id,
                WorkPermitMember.role == "foreman",
            )
        )
    ).scalar_one_or_none()
    if member is None:
        session.add(
            WorkPermitMember(
                tenant_id=tenant_db_id, work_permit_id=wp.id, person_id=person.id, role="foreman"
            )
        )


async def _seed_work_permit_gas_demo(session, tenant_db_id: str, person) -> None:
    """Демо-наряд газоопасных работ (528) с СИЗОД и замером — печатается «из коробки». Идемпотентно."""
    from app.models.work_permit import WorkPermit, WorkPermitMember

    wp = (
        await session.execute(
            select(WorkPermit).where(
                WorkPermit.tenant_id == tenant_db_id,
                WorkPermit.number == "WP-GAS-DEMO",
            )
        )
    ).scalar_one_or_none()
    if wp is None:
        wp = WorkPermit(
            tenant_id=tenant_db_id,
            number="WP-GAS-DEMO",
            work_type="gas_hazardous",
            zone_text="ГРП-3, газорегуляторный пункт (узел запорной арматуры)",
            status="draft",
            type_specific={
                "respiratory_ppe": ["hose_mask"],
                "gas_analysis": [{"parameter": "oxygen", "value": "20.9", "norm": "≥ 20 об.%"}],
            },
        )
        session.add(wp)
        await session.flush()
    member = (
        await session.execute(
            select(WorkPermitMember).where(
                WorkPermitMember.tenant_id == tenant_db_id,
                WorkPermitMember.work_permit_id == wp.id,
                WorkPermitMember.person_id == person.id,
                WorkPermitMember.role == "foreman",
            )
        )
    ).scalar_one_or_none()
    if member is None:
        session.add(
            WorkPermitMember(
                tenant_id=tenant_db_id, work_permit_id=wp.id, person_id=person.id, role="foreman"
            )
        )


async def _seed_work_permit_electrical_demo(session, tenant_db_id: str, person) -> None:
    """Демо-наряд работ в электроустановках (903н): тех. мероприятия + условие по напряжению. Идемпотентно."""
    from app.models.work_permit import WorkPermit, WorkPermitMember

    wp = (
        await session.execute(
            select(WorkPermit).where(
                WorkPermit.tenant_id == tenant_db_id,
                WorkPermit.number == "WP-ELEC-DEMO",
            )
        )
    ).scalar_one_or_none()
    if wp is None:
        wp = WorkPermit(
            tenant_id=tenant_db_id,
            number="WP-ELEC-DEMO",
            work_type="electrical",
            zone_text="РУ-0,4 кВ, ячейка №7, цех №2",
            status="draft",
            type_specific={
                "voltage_level": "le_1000",
                "technical_measures": ["disconnect", "verify_no_voltage", "grounding"],
                "voltage_condition": "de_energized",
            },
        )
        session.add(wp)
        await session.flush()
    member = (
        await session.execute(
            select(WorkPermitMember).where(
                WorkPermitMember.tenant_id == tenant_db_id,
                WorkPermitMember.work_permit_id == wp.id,
                WorkPermitMember.person_id == person.id,
                WorkPermitMember.role == "foreman",
            )
        )
    ).scalar_one_or_none()
    if member is None:
        session.add(
            WorkPermitMember(
                tenant_id=tenant_db_id, work_permit_id=wp.id, person_id=person.id, role="foreman"
            )
        )
    # Производитель работ должен иметь группу по электробезопасности (903н) — показ + готовность
    # в наряде. Хранится в Person.qualifications (без миграции). Идемпотентно.
    quals = list(person.qualifications or [])
    if not any(q.get("kind") == "electrical_safety_group" for q in quals):
        quals.append(
            {
                "kind": "electrical_safety_group",
                "level": "IV",
                "name": "Группа по электробезопасности",
                "valid_until": "2027-12-31",
            }
        )
        person.qualifications = quals


async def _seed_work_permit_excavation_demo(session, tenant_db_id: str, person) -> None:
    """Демо-наряд земляных работ (883н): коммуникации + защита стенок выемки. Идемпотентно."""
    from app.models.work_permit import WorkPermit, WorkPermitMember

    wp = (
        await session.execute(
            select(WorkPermit).where(
                WorkPermit.tenant_id == tenant_db_id,
                WorkPermit.number == "WP-DIG-DEMO",
            )
        )
    ).scalar_one_or_none()
    if wp is None:
        wp = WorkPermit(
            tenant_id=tenant_db_id,
            number="WP-DIG-DEMO",
            work_type="excavation",
            zone_text="Траншея вдоль корпуса №4 (теплотрасса)",
            status="draft",
            type_specific={
                "utilities": ["power_cable", "water_sewer"],
                "shoring": "shield_bracing",
            },
        )
        session.add(wp)
        await session.flush()
    member = (
        await session.execute(
            select(WorkPermitMember).where(
                WorkPermitMember.tenant_id == tenant_db_id,
                WorkPermitMember.work_permit_id == wp.id,
                WorkPermitMember.person_id == person.id,
                WorkPermitMember.role == "foreman",
            )
        )
    ).scalar_one_or_none()
    if member is None:
        session.add(
            WorkPermitMember(
                tenant_id=tenant_db_id, work_permit_id=wp.id, person_id=person.id, role="foreman"
            )
        )


async def _seed_committees_demo(session, tenant_db_id: str) -> None:
    """Seed a minimal committees demo (P10-01 срез-1).

    Does NOT require a Person row — all person FK fields are left NULL to keep
    this seed independent of the rest of the demo bootstrap.  Idempotent:
    keyed on (tenant_id, name) for the Committee root.
    """
    from app.models.committees import (
        Committee,
        CommitteeAgendaItem,
        CommitteeDecision,
        CommitteeDecisionTask,
        CommitteeKind,
        CommitteeMeeting,
        DecisionTaskStatus,
        MeetingStatus,
    )

    committee = (
        await session.execute(
            select(Committee).where(
                Committee.tenant_id == tenant_db_id,
                Committee.name == "Комитет по охране труда",
                Committee.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if committee is not None:
        return  # already seeded — full idempotent bail-out

    committee = Committee(
        tenant_id=tenant_db_id,
        kind=CommitteeKind.OSMS,
        name="Комитет по охране труда",
        description="Демо-комитет по охране труда (срез-1)",
        is_active=True,
    )
    session.add(committee)
    await session.flush()

    meeting = CommitteeMeeting(
        tenant_id=tenant_db_id,
        committee_id=committee.id,
        scheduled_at=datetime.now(timezone.utc) - timedelta(days=30),
        location="Конференц-зал №1 (демо)",
        status=MeetingStatus.HELD,
    )
    session.add(meeting)
    await session.flush()

    agenda_item = CommitteeAgendaItem(
        tenant_id=tenant_db_id,
        meeting_id=meeting.id,
        seq=1,
        title="Утверждение плана мероприятий по охране труда",
        presenter_person_id=None,
    )
    session.add(agenda_item)
    await session.flush()

    decision = CommitteeDecision(
        tenant_id=tenant_db_id,
        meeting_id=meeting.id,
        agenda_item_id=agenda_item.id,
        text="Утвердить план мероприятий по охране труда на текущий год",
        decided_at=datetime.now(timezone.utc) - timedelta(days=30),
    )
    session.add(decision)
    await session.flush()

    # due_date in the past → overdue badge is visible on first login
    session.add(
        CommitteeDecisionTask(
            tenant_id=tenant_db_id,
            decision_id=decision.id,
            assignee_person_id=None,
            due_date=(datetime.now(timezone.utc) - timedelta(days=10)).date(),
            status=DecisionTaskStatus.OPEN,
            evidence_note=None,
        )
    )

    # Enable the default-off ``committees`` flag for the demo tenant so the
    # seeded data is visible in the demo walkthrough. The flag stays default-off
    # in production; this only writes a per-tenant enablement for the demo tenant.
    from app.models.feature import Feature, FeatureEnablement

    feature = (
        await session.execute(select(Feature).where(Feature.code == "committees"))
    ).scalar_one_or_none()
    if feature is None:
        feature = Feature(code="committees", title="Комитеты")
        session.add(feature)
        await session.flush()
    enablement = (
        await session.execute(
            select(FeatureEnablement).where(
                FeatureEnablement.tenant_id == tenant_db_id,
                FeatureEnablement.feature_id == feature.id,
            )
        )
    ).scalar_one_or_none()
    if enablement is None:
        session.add(FeatureEnablement(tenant_id=tenant_db_id, feature_id=feature.id, on=True))


async def _seed_sout_demo(session, tenant_db_id: str, position_id: str | None = None) -> None:
    """Seed a minimal СОУТ demo (P10-04 срез-1).

    Does NOT require a Person row — ``person_id`` is left NULL to keep this seed
    independent of the rest of the demo bootstrap. Idempotent: keyed on
    (tenant_id, name) for the SoutCampaign root.
    """
    from app.models.sout import (
        SoutCampaign,
        SoutCampaignStatus,
        SoutClass,
        SoutFactor,
        SoutGuarantee,
        SoutGuaranteeKind,
        SoutWorkplace,
    )

    campaign = (
        await session.execute(
            select(SoutCampaign).where(
                SoutCampaign.tenant_id == tenant_db_id,
                SoutCampaign.name == "СОУТ 2026 (демо)",
                SoutCampaign.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if campaign is not None:
        return  # already seeded — full idempotent bail-out

    campaign = SoutCampaign(
        tenant_id=tenant_db_id,
        name="СОУТ 2026 (демо)",
        expert_org_name="ООО «Эксперт-Оценка» (демо)",
        report_number="СОУТ-2026-001",
        report_date=(datetime.now(timezone.utc) - timedelta(days=60)).date(),
        status=SoutCampaignStatus.COMPLETED,
        completed_date=(datetime.now(timezone.utc) - timedelta(days=60)).date(),
    )
    session.add(campaign)
    await session.flush()

    workplace = SoutWorkplace(
        tenant_id=tenant_db_id,
        campaign_id=campaign.id,
        workplace_code="РМ-001",
        position_name="Электрогазосварщик",
        person_id=None,
        position_id=position_id,
        assessed_class=SoutClass.HARMFUL_3_2,
        assessment_date=(datetime.now(timezone.utc) - timedelta(days=60)).date(),
        # next assessment already in the past → reassessment-due badge visible
        next_assessment_date=(datetime.now(timezone.utc) - timedelta(days=5)).date(),
    )
    session.add(workplace)
    await session.flush()

    demo_hazard = (
        await session.execute(
            select(RiskHazard).where(
                RiskHazard.tenant_id == tenant_db_id,
                RiskHazard.code == "demo_general",
            )
        )
    ).scalar_one_or_none()

    session.add(
        SoutFactor(
            tenant_id=tenant_db_id,
            workplace_id=workplace.id,
            hazard_id=demo_hazard.id if demo_hazard else None,
            code="4.50",
            name="Шум",
            measured_class=SoutClass.HARMFUL_3_1,
            note="Превышение ПДУ по эквивалентному уровню звука (демо)",
        )
    )
    session.add(
        SoutGuarantee(
            tenant_id=tenant_db_id,
            workplace_id=workplace.id,
            kind=SoutGuaranteeKind.ADDITIONAL_LEAVE,
            detail="Дополнительный отпуск 7 календарных дней",
        )
    )

    # Enable the default-off ``sout`` flag for the demo tenant so the seeded data
    # is visible in the demo walkthrough. The flag stays default-off in production.
    from app.models.feature import Feature, FeatureEnablement

    feature = (
        await session.execute(select(Feature).where(Feature.code == "sout"))
    ).scalar_one_or_none()
    if feature is None:
        feature = Feature(code="sout", title="СОУТ")
        session.add(feature)
        await session.flush()
    enablement = (
        await session.execute(
            select(FeatureEnablement).where(
                FeatureEnablement.tenant_id == tenant_db_id,
                FeatureEnablement.feature_id == feature.id,
            )
        )
    ).scalar_one_or_none()
    if enablement is None:
        session.add(FeatureEnablement(tenant_id=tenant_db_id, feature_id=feature.id, on=True))


async def bootstrap_demo_tenant(settings: Settings) -> None:
    """Create a deterministic tenant with baseline entities for demo walkthrough."""

    if not settings.demo_bootstrap:
        return
    if settings.app_env not in {"development", "test"}:
        logger.warning(
            "demo.bootstrap.skipped", extra={"reason": "not-dev", "env": settings.app_env}
        )
        return

    tenant_slug = settings.demo_tenant_id.strip() or "demo"
    company_name = settings.demo_company_name.strip() or "ООО Демо Строй"
    site_name = settings.demo_site_name.strip() or "Площадка Север"

    async with session_scope(tenant="public") as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))
        ).scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(
                slug=tenant_slug,
                code=tenant_slug,
                name=f"{company_name} ({tenant_slug})",
                contact_email="demo@example.local",
                schema_name=f"tenant_{tenant_slug}",
                is_active=True,
            )
            session.add(tenant)
            await session.flush()
        tenant_db_id = str(tenant.id)
        tenant_schema_name = str(tenant.schema_name or f"tenant_{tenant_slug}")

        # Seed shared Feature catalogue row for medical (idempotent).
        medical_feature = (
            await session.execute(select(Feature).where(Feature.code == "medical"))
        ).scalar_one_or_none()
        if medical_feature is None:
            session.add(Feature(code="medical", title="Медосмотры"))
            await session.flush()

        # Seed shared Feature catalogue row for contractors (idempotent).
        contractors_feature = (
            await session.execute(select(Feature).where(Feature.code == "contractors"))
        ).scalar_one_or_none()
        if contractors_feature is None:
            session.add(Feature(code="contractors", title="Подрядчики"))
            await session.flush()

    await aensure_tenant_schema(tenant_slug, schema_name=tenant_schema_name)

    # Pass schema_name explicitly: when DEFAULT_TENANT_SLUG=demo (CI default),
    # session_scope(tenant="demo") would otherwise short-circuit to the shared
    # schema and read training_course from public instead of tenant_demo.
    async with session_scope(tenant=tenant_slug, schema_name=tenant_schema_name) as session:
        company = (
            await session.execute(select(Company).where(Company.name == company_name))
        ).scalar_one_or_none()
        if company is None:
            company = Company(tenant_id=tenant_db_id, name=company_name, legal_address="г. Москва")
            session.add(company)
            await session.flush()

        site = (
            await session.execute(
                select(Site).where(Site.company_id == company.id, Site.name == site_name)
            )
        ).scalar_one_or_none()
        if site is None:
            site = Site(
                tenant_id=tenant_db_id,
                company_id=company.id,
                name=site_name,
                address="Москва, Тестовая 1",
            )
            session.add(site)
            await session.flush()

        department = (
            await session.execute(
                select(Department).where(
                    Department.company_id == company.id, Department.name == "Производство"
                )
            )
        ).scalar_one_or_none()
        if department is None:
            session.add(
                Department(
                    tenant_id=tenant_db_id,
                    company_id=company.id,
                    name="Производство",
                    code="DEMO-PROD",
                )
            )

        position = (
            await session.execute(
                select(Position).where(
                    Position.company_id == company.id, Position.name == "Мастер участка"
                )
            )
        ).scalar_one_or_none()
        if position is None:
            position = Position(
                tenant_id=tenant_db_id, company_id=company.id, name="Мастер участка"
            )
            session.add(position)
            await session.flush()

        person = (
            await session.execute(
                select(Person).where(
                    Person.company_id == company.id,
                    Person.first_name == "Иван",
                    Person.last_name == "Иванов",
                )
            )
        ).scalar_one_or_none()
        if person is None:
            person = Person(
                tenant_id=tenant_db_id,
                company_id=company.id,
                position_id=position.id if position else None,
                first_name="Иван",
                last_name="Иванов",
                personnel_number="D-001",
                email="ivanov@example.local",
            )
            session.add(person)
            await session.flush()

        course = (
            await session.execute(
                select(TrainingCourse).where(TrainingCourse.title == "Вводный инструктаж (демо)")
            )
        ).scalar_one_or_none()
        if course is None:
            session.add(
                TrainingCourse(
                    tenant_id=tenant_db_id,
                    title="Вводный инструктаж (демо)",
                    code="demo-intro",
                    duration_hours=2,
                )
            )

        # Seed a MedicalNorm for periodic exam on the demo Position (idempotent).
        # This ensures the demo contingent list shows a "missing" row so the
        # /medical/contingent endpoint is non-empty out-of-the-box.
        if position is not None:
            existing_norm = (
                await session.execute(
                    select(MedicalNorm).where(
                        MedicalNorm.position_id == position.id,
                        MedicalNorm.exam_kind == MedicalExamKind.PERIODIC,
                    )
                )
            ).scalar_one_or_none()
            if existing_norm is None:
                session.add(
                    MedicalNorm(
                        tenant_id=tenant_db_id,
                        position_id=position.id,
                        exam_kind=MedicalExamKind.PERIODIC,
                        interval_days=365,
                    )
                )

        # Seed a demo ContractorRegistry + 2 ContractorEmployee rows (idempotent).
        demo_contractor_name = "Демо-подрядчик"
        contractor = (
            await session.execute(
                select(ContractorRegistry).where(
                    ContractorRegistry.tenant_id == tenant_db_id,
                    ContractorRegistry.name == demo_contractor_name,
                )
            )
        ).scalar_one_or_none()
        if contractor is None:
            contractor = ContractorRegistry(
                tenant_id=tenant_db_id,
                name=demo_contractor_name,
                status="active",
            )
            session.add(contractor)
            await session.flush()

            now = datetime.now(timezone.utc)
            ready_emp = ContractorEmployee(
                tenant_id=tenant_db_id,
                contractor_id=contractor.id,
                full_name="Готовый Иван",
                access_status=ComplianceStatus.VALID,
                training_status=ComplianceStatus.VALID,
                medical_status=ComplianceStatus.VALID,
                last_training_at=now,
                next_medical_at=now + timedelta(days=200),
            )
            session.add(ready_emp)
            # Пётр keeps a manually-VALID medical_status, yet next_medical_at is in the
            # past → the admission engine BLOCKS him on the OVERDUE deadline. This is the
            # headline demo: a "stale-valid" status flag is caught by the real deadline.
            session.add(
                ContractorEmployee(
                    tenant_id=tenant_db_id,
                    contractor_id=contractor.id,
                    full_name="Просроченный Пётр",
                    access_status=ComplianceStatus.VALID,
                    training_status=ComplianceStatus.VALID,
                    medical_status=ComplianceStatus.VALID,
                    last_training_at=now,
                    next_medical_at=now - timedelta(days=1),
                )
            )
            await session.flush()  # assign ids before seeding documents
            await _seed_contractor_documents(session, tenant_db_id, contractor.id, ready_emp.id)
            await _seed_contractor_requirements(session, tenant_db_id)

        # Seed PPE norms/sizes/issues for the 766н card demo (idempotent;
        # called unconditionally so existing demo tenants get the data too).
        if position is not None and person is not None:
            await _seed_ppe_demo(session, tenant_db_id, person, str(position.id))
            await _seed_medical_factor_demo(session, tenant_db_id, str(position.id))
            await _seed_briefing_code_flow_demo(session, tenant_db_id, person)
            await _seed_work_permit_confined_demo(session, tenant_db_id, person)
            await _seed_work_permit_hot_work_demo(session, tenant_db_id, person)
            await _seed_work_permit_gas_demo(session, tenant_db_id, person)
            await _seed_work_permit_electrical_demo(session, tenant_db_id, person)
            await _seed_work_permit_excavation_demo(session, tenant_db_id, person)

        await ensure_default_packs(session, tenant_slug=tenant_slug)
        await _seed_committees_demo(session, tenant_db_id)
        await _seed_sout_demo(
            session, tenant_db_id, str(position.id) if position is not None else None
        )
        logger.info(
            "demo.bootstrap.done",
            extra={"tenant": tenant_slug, "company": company_name, "site": site_name},
        )
