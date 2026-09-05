"""Service that assembles the Unified Employee Card aggregate.

vNext-EMP-01 / Phase 3.2 — backend foundation for the unified Employee
view. This service intentionally relies on existing domain modules and does
not introduce new master data; it only reads and joins.

Implementation notes
--------------------
* Tenant scope is mandatory and is enforced for every query.
* Lists are bounded by `MAX_ITEMS_PER_SECTION` to keep payload sizes
  predictable. Counts always reflect the *unbounded* totals.
* The query plan is a small fixed number of selects (one per section); we
  trade a few round-trips for code simplicity.
* Сроки СИЗ/инструктажей/дедлайнов сравниваются через ``as_utc``: SQLite
  отдаёт время без зоны, и «истёк ли» падало бы ``TypeError`` ровно на живой
  ручке (срез-53 — поймано первым HTTP-тестом с выдачей СИЗ со сроком).

Светофор дисциплин (BIZ-54-57 срез-53, Доп. №1 разд. 57.1)
------------------------------------------------------------
ТЗ: «карточка сотрудника 360°: все его обучения, допуски, медосмотры, СИЗ,
аттестации по всем дисциплинам сразу». Вкладки показывают записи; светофор
отвечает на вопрос «всё ли положенное у человека действует» — по каждой
дисциплине словаря и одними правилами с карточкой площадки и светофором
клиента (``services/discipline_numbers`` + ``core/discipline_status``).
Своего здесь два решения (третье — общее с площадкой: дисциплины вне редакции
арендатора скрыты и названы фразой ``not_applicable``,
``services/discipline_applicability``, срез-54):

* **уволенный не красится.** Площадка и клиент уволенных не считают
  (``employment_status != terminated``); карточка уволенного показала бы
  красные разрывы по обязательствам, которых у него уже нет. Строки отдаются
  «не измеряется» с причиной, а не пустой таблицей;
* **«эталон не задан» — про должность человека.** Общая расшифровка говорит
  «у должностей клиента нет норм» — на карточке одного человека это либо
  «должность не указана», либо «у должности нет норм»; специалист по этим
  словам делает разное (заполнить карточку / завести норму);
* **ПБ — по его инструктажам, без объектов (срез-84).** Противопожарные
  инструктажи и ПТМ — поимённый срок, и считаются той же формулой, что у
  площадки и сводки модуля (``services/discipline_fire_safety``, человек ×
  вид по самой поздней дате действия). Средства защиты, тренировки и
  документы — сроки площадки, у человека их нет: строка не говорит про них
  ни слова (``objects_counted=False``).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.discipline_status import (
    DisciplineStatus,
    TrafficLight,
    build_discipline_statuses,
    worst_light,
)
from app.core.disciplines import DISCIPLINE_TITLES, Discipline
from app.core.feature_flags import as_utc
from app.models.document import Document
from app.models.models import (
    AuditLog,
    BriefingEntry,
    BriefingTemplate,
    Company,
    ComplianceDeadline,
    EmploymentStatus,
    Incident,
    IncidentPerson,
    MedicalExam,
    Permit,
    PermitStatus,
    Person,
    Position,
    PPEIssue,
    PPEIssueStatus,
    Template,
    Training,
    TrainingCertificate,
    TrainingCourse,
    TrainingSessionStatus,
    User,
    UserRole,
    Workplace,
)
from app.models.models import (
    TrainingSession as TrainingSessionModel,
)
from app.models.training import INTERNSHIP_STATUSES, Internship
from app.schemas.employee import (
    EmployeeAuditItem,
    EmployeeAuditSection,
    EmployeeBriefingItem,
    EmployeeBriefingsSection,
    EmployeeCard,
    EmployeeComplianceDeadlineItem,
    EmployeeComplianceDeadlinesSection,
    EmployeeDisciplinesSection,
    EmployeeDisciplineStatus,
    EmployeeDocumentItem,
    EmployeeDocumentsSection,
    EmployeeIncidentItem,
    EmployeeIncidentsSection,
    EmployeeInternshipItem,
    EmployeeMedicalItem,
    EmployeeMedicalSection,
    EmployeePermitItem,
    EmployeePermitsSection,
    EmployeePersonal,
    EmployeePPEIssueItem,
    EmployeePPESection,
    EmployeeRolesAndAssignments,
    EmployeeTrainingCertificate,
    EmployeeTrainingItem,
    EmployeeTrainingSection,
    EmployeeUserAccount,
)
from app.services.discipline_applicability import (
    DisciplineApplicability,
    collect_applicability,
    only_applicable,
)
from app.services.discipline_fire_safety import collect_fire_briefing_numbers
from app.services.discipline_numbers import collect_people_numbers

__all__ = ["EmployeeCardService", "MAX_ITEMS_PER_SECTION", "TERMINATED_REASON"]

MAX_ITEMS_PER_SECTION = 50

#: Почему у уволенного светофор не считается — одной строкой на всех дисциплинах.
TERMINATED_REASON = "Сотрудник уволен: обязательств нет, светофор не считается"

#: дисциплина стажировки словами — тот же словарь, что у реестра ``/internships``
_DISCIPLINE_CODES = {d.value: DISCIPLINE_TITLES[d] for d in Discipline}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return _utcnow().date()


class EmployeeCardService:
    """Build a tenant-scoped `EmployeeCard` for a single person."""

    def __init__(
        self,
        *,
        tenant_id: str,
        db: AsyncSession,
        max_items_per_section: int = MAX_ITEMS_PER_SECTION,
    ) -> None:
        self.tenant_id = str(tenant_id)
        self.db = db
        # UI-карточке хватает 50 строк на секцию; выгрузка ПДн по запросу субъекта
        # (SEC-66, разд. 66.2) поднимает предел — см. app/modules/privacy/service.py.
        self.max_items_per_section = int(max_items_per_section)

    async def build(self, person_id: str) -> EmployeeCard | None:
        person = await self._load_person(person_id)
        if person is None:
            return None

        company = await self._load_company(person.company_id) if person.company_id else None
        position = await self._load_position(person.position_id) if person.position_id else None
        workplace = await self._load_workplace(person.workplace_id) if person.workplace_id else None

        personal = self._build_personal(person, company, position, workplace)
        roles = await self._build_roles_and_assignments(person, company, position, workplace)
        disciplines = await self._build_disciplines(person)
        training = await self._build_training(person)
        medicals = await self._build_medicals(person)
        ppe = await self._build_ppe(person)
        permits = await self._build_permits(person)
        incidents = await self._build_incidents(person)
        documents = await self._build_documents(person)
        briefings = await self._build_briefings(person)
        compliance_deadlines = await self._build_compliance_deadlines(person)
        audit = await self._build_audit(person)

        return EmployeeCard(
            person_id=str(person.id),
            tenant_id=self.tenant_id,
            generated_at=_utcnow(),
            personal=personal,
            roles_and_assignments=roles,
            disciplines=disciplines,
            training=training,
            medicals=medicals,
            ppe=ppe,
            permits=permits,
            incidents=incidents,
            documents=documents,
            briefings=briefings,
            compliance_deadlines=compliance_deadlines,
            audit=audit,
        )

    async def _load_person(self, person_id: str) -> Person | None:
        stmt = select(Person).where(
            Person.id == person_id,
            Person.tenant_id == self.tenant_id,
            Person.deleted_at.is_(None),
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _load_company(self, company_id: str) -> Company | None:
        stmt = select(Company).where(
            Company.id == company_id,
            Company.tenant_id == self.tenant_id,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _load_position(self, position_id: str) -> Position | None:
        stmt = select(Position).where(
            Position.id == position_id,
            Position.tenant_id == self.tenant_id,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _load_workplace(self, workplace_id: str) -> Workplace | None:
        stmt = select(Workplace).where(
            Workplace.id == workplace_id,
            Workplace.tenant_id == self.tenant_id,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    def _build_personal(
        self,
        person: Person,
        company: Company | None,
        position: Position | None,
        workplace: Workplace | None,
    ) -> EmployeePersonal:
        full_name_parts = [
            person.last_name or "",
            person.first_name or "",
            person.middle_name or "",
        ]
        fio = " ".join(part for part in full_name_parts if part).strip()
        return EmployeePersonal(
            id=str(person.id),
            company_id=str(person.company_id) if person.company_id else "",
            company_name=getattr(company, "name", None),
            position_id=str(person.position_id) if person.position_id else None,
            position_name=getattr(position, "name", None),
            workplace_id=str(person.workplace_id) if person.workplace_id else None,
            workplace_name=getattr(workplace, "name", None),
            first_name=person.first_name or "",
            last_name=person.last_name or "",
            middle_name=person.middle_name,
            fio=fio,
            birth_date=person.birth_date,
            email=person.email,
            phone=person.phone,
            personnel_number=person.personnel_number,
            hired_at=person.hired_at,
            snils=person.snils,
            passport=person.passport,
            employment_status=person.employment_status,
            working_conditions_class=person.working_conditions_class,
            hazardous_factors=list(person.hazardous_factors or []),
            qualifications=list(person.qualifications or []),
            current_ppe=list(person.current_ppe or []),
        )

    async def _build_roles_and_assignments(
        self,
        person: Person,
        company: Company | None,
        position: Position | None,
        workplace: Workplace | None,
    ) -> EmployeeRolesAndAssignments:
        user_account: EmployeeUserAccount | None = None
        if person.email:
            stmt = (
                select(User)
                .where(
                    User.tenant_id == self.tenant_id,
                    func.lower(User.email) == person.email.lower(),
                    User.deleted_at.is_(None),
                )
                .limit(1)
            )
            user = (await self.db.execute(stmt)).scalar_one_or_none()
            if user is not None:
                additional_roles = (
                    (
                        await self.db.execute(
                            select(UserRole.role).where(
                                UserRole.tenant_id == self.tenant_id,
                                UserRole.user_id == user.id,
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                user_account = EmployeeUserAccount(
                    user_id=str(user.id),
                    email=user.email,
                    role=user.role.value if hasattr(user.role, "value") else str(user.role),
                    is_active=bool(user.is_active),
                    last_login_at=user.last_login_at,
                    additional_roles=[
                        r.value if hasattr(r, "value") else str(r) for r in additional_roles
                    ],
                )

        return EmployeeRolesAndAssignments(
            company_id=str(person.company_id) if person.company_id else "",
            company_name=getattr(company, "name", None),
            position_id=str(person.position_id) if person.position_id else None,
            position_name=getattr(position, "name", None),
            workplace_id=str(person.workplace_id) if person.workplace_id else None,
            workplace_name=getattr(workplace, "name", None),
            employment_status=person.employment_status,
            user_account=user_account,
        )

    async def _build_disciplines(self, person: Person) -> EmployeeDisciplinesSection:
        """Светофор по всем дисциплинам словаря — одними правилами с площадкой."""

        applicability = await collect_applicability(self.db, self.tenant_id)
        if person.employment_status == EmploymentStatus.TERMINATED:
            rows = [
                DisciplineStatus(
                    discipline=discipline,
                    title=DISCIPLINE_TITLES[discipline],
                    light=TrafficLight.NOT_MEASURED,
                    reason=TERMINATED_REASON,
                )
                for discipline in Discipline
                if applicability.applies(discipline)
            ]
            return _disciplines_section(rows, applicability, note=TERMINATED_REASON)

        numbers = await collect_people_numbers(self.db, tenant_id=self.tenant_id, people=[person])
        fire_safety = await collect_fire_briefing_numbers(
            self.db, tenant_id=self.tenant_id, person_ids=[str(person.id)]
        )
        rows = only_applicable(
            build_discipline_statuses(
                medical=numbers.medical,
                ppe=numbers.ppe,
                training_overdue=numbers.training_overdue,
                road_safety=numbers.road_safety,
                fire_safety=fire_safety,
            ),
            applicability,
        )
        no_norms = (
            "Эталон не задан: должность не указана"
            if not person.position_id
            else "Эталон не задан: у должности нет норм"
        )
        rows = [
            (
                replace(row, reason=no_norms)
                if row.discipline in (Discipline.MEDICAL, Discipline.PPE)
                and row.counts.required == 0
                else row
            )
            for row in rows
        ]
        return _disciplines_section(rows, applicability)

    async def _build_training(self, person: Person) -> EmployeeTrainingSection:
        # TrainingSession (modern) — primary timeline.
        sessions_stmt = (
            select(TrainingSessionModel, TrainingCourse.title)
            .outerjoin(
                TrainingCourse,
                TrainingCourse.id == TrainingSessionModel.course_id,
            )
            .where(
                TrainingSessionModel.tenant_id == self.tenant_id,
                TrainingSessionModel.person_id == person.id,
            )
            .order_by(
                desc(TrainingSessionModel.completed_at), desc(TrainingSessionModel.created_at)
            )
            .limit(self.max_items_per_section)
        )
        rows = (await self.db.execute(sessions_stmt)).all()
        sessions: list[EmployeeTrainingItem] = []
        for sess, course_title in rows:
            sessions.append(
                EmployeeTrainingItem(
                    id=str(sess.id),
                    course_id=str(sess.course_id) if sess.course_id else None,
                    course_title=course_title,
                    plan_id=str(sess.plan_id) if sess.plan_id else None,
                    status=sess.status,
                    started_at=sess.started_at,
                    completed_at=sess.completed_at,
                    score=sess.score,
                )
            )
        # Legacy `Training` rows (no soft-delete; mapped to enum via best effort).
        legacy_stmt = (
            select(Training)
            .where(
                Training.tenant_id == self.tenant_id,
                Training.person_id == person.id,
            )
            .order_by(desc(Training.completed_at), desc(Training.created_at))
            .limit(self.max_items_per_section)
        )
        legacy_rows = (await self.db.execute(legacy_stmt)).scalars().all()
        for legacy in legacy_rows:
            sessions.append(
                EmployeeTrainingItem(
                    id=str(legacy.id),
                    course_id=None,
                    course_title=legacy.course_name,
                    plan_id=None,
                    status=_legacy_training_status(legacy.status),
                    started_at=legacy.scheduled_at,
                    completed_at=legacy.completed_at,
                    score=None,
                )
            )
        sessions = sessions[: self.max_items_per_section]

        sessions_total = await self._count(
            select(func.count())
            .select_from(TrainingSessionModel)
            .where(
                TrainingSessionModel.tenant_id == self.tenant_id,
                TrainingSessionModel.person_id == person.id,
            )
        ) + await self._count(
            select(func.count())
            .select_from(Training)
            .where(
                Training.tenant_id == self.tenant_id,
                Training.person_id == person.id,
            )
        )

        cert_stmt = (
            select(TrainingCertificate, TrainingCourse.title)
            .outerjoin(
                TrainingCourse,
                TrainingCourse.id == TrainingCertificate.course_id,
            )
            .where(
                TrainingCertificate.tenant_id == self.tenant_id,
                TrainingCertificate.person_id == person.id,
                TrainingCertificate.deleted_at.is_(None),
            )
            .order_by(desc(TrainingCertificate.issued_at))
            .limit(self.max_items_per_section)
        )
        cert_rows = (await self.db.execute(cert_stmt)).all()
        certificates = [
            EmployeeTrainingCertificate(
                id=str(cert.id),
                code=cert.code,
                course_id=str(cert.course_id) if cert.course_id else None,
                course_title=course_title,
                issued_at=cert.issued_at,
                valid_until=cert.valid_until,
                status=cert.status,
            )
            for cert, course_title in cert_rows
        ]
        certificates_total = await self._count(
            select(func.count())
            .select_from(TrainingCertificate)
            .where(
                TrainingCertificate.tenant_id == self.tenant_id,
                TrainingCertificate.person_id == person.id,
                TrainingCertificate.deleted_at.is_(None),
            )
        )

        internships, internships_total = await self._build_internships(person)

        return EmployeeTrainingSection(
            sessions_count=sessions_total,
            certificates_count=certificates_total,
            internships_count=internships_total,
            sessions=sessions,
            certificates=certificates,
            internships=internships,
        )

    async def _build_internships(self, person: Person) -> tuple[list[EmployeeInternshipItem], int]:
        """Стажировки человека — из ОБЩЕГО реестра, без своей копии.

        Наставник — ядровой ``Person``, имя берётся оттуда же, что и в реестре.
        Недобор считается тем же правилом, что в ``/internships`` (под тестом
        сравнением с ручкой реестра): завершена, а смен меньше плана.
        """

        Mentor = aliased(Person)
        stmt = (
            select(Internship, Mentor)
            .outerjoin(Mentor, Mentor.id == Internship.mentor_person_id)
            .where(
                Internship.tenant_id == self.tenant_id,
                Internship.person_id == person.id,
                Internship.deleted_at.is_(None),
            )
            # свежие сверху: без даты начала — по дате назначения
            .order_by(
                desc(Internship.started_on).nulls_last(),
                desc(Internship.created_at),
            )
            .limit(self.max_items_per_section)
        )
        rows = (await self.db.execute(stmt)).all()
        items = [
            EmployeeInternshipItem(
                id=str(record.id),
                subject=record.subject,
                discipline=record.discipline,
                discipline_label=(
                    _DISCIPLINE_CODES.get(record.discipline) if record.discipline else None
                ),
                mentor_name=_person_name(mentor) if mentor is not None else None,
                planned_shifts=record.planned_shifts,
                completed_shifts=record.completed_shifts,
                completed_short=(
                    record.status == "completed" and record.completed_shifts < record.planned_shifts
                ),
                started_on=record.started_on,
                finished_on=record.finished_on,
                status=record.status,
                status_label=INTERNSHIP_STATUSES.get(record.status, record.status),
            )
            for record, mentor in rows
        ]
        total = await self._count(
            select(func.count())
            .select_from(Internship)
            .where(
                Internship.tenant_id == self.tenant_id,
                Internship.person_id == person.id,
                Internship.deleted_at.is_(None),
            )
        )
        return items, total

    async def _build_medicals(self, person: Person) -> EmployeeMedicalSection:
        today = _today()
        stmt = (
            select(MedicalExam)
            .where(
                MedicalExam.tenant_id == self.tenant_id,
                MedicalExam.person_id == person.id,
                MedicalExam.deleted_at.is_(None),
            )
            .order_by(desc(MedicalExam.exam_date))
            .limit(self.max_items_per_section)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        items = [
            EmployeeMedicalItem(
                id=str(exam.id),
                exam_type=exam.exam_type,
                exam_date=exam.exam_date,
                valid_until=exam.valid_until,
                conclusion=exam.conclusion,
                is_expired=exam.valid_until < today,
            )
            for exam in rows
        ]
        total = await self._count(
            select(func.count())
            .select_from(MedicalExam)
            .where(
                MedicalExam.tenant_id == self.tenant_id,
                MedicalExam.person_id == person.id,
                MedicalExam.deleted_at.is_(None),
            )
        )
        expired = await self._count(
            select(func.count())
            .select_from(MedicalExam)
            .where(
                MedicalExam.tenant_id == self.tenant_id,
                MedicalExam.person_id == person.id,
                MedicalExam.deleted_at.is_(None),
                MedicalExam.valid_until < today,
            )
        )
        return EmployeeMedicalSection(count=total, expired_count=expired, items=items)

    async def _build_ppe(self, person: Person) -> EmployeePPESection:
        now = _utcnow()
        stmt = (
            select(PPEIssue)
            .where(
                PPEIssue.tenant_id == self.tenant_id,
                PPEIssue.person_id == person.id,
                PPEIssue.deleted_at.is_(None),
            )
            .order_by(desc(PPEIssue.issued_at))
            .limit(self.max_items_per_section)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        items = [
            EmployeePPEIssueItem(
                id=str(issue.id),
                item_id=str(issue.item_id) if issue.item_id else None,
                item_name=issue.item_name,
                quantity=issue.quantity,
                issued_at=issue.issued_at,
                expires_at=issue.expires_at,
                returned_at=issue.returned_at,
                status=issue.status,
                is_expired=bool(
                    issue.status == PPEIssueStatus.ISSUED
                    and issue.expires_at is not None
                    and (as_utc(issue.expires_at) or now) < now
                ),
            )
            for issue in rows
        ]
        total = await self._count(
            select(func.count())
            .select_from(PPEIssue)
            .where(
                PPEIssue.tenant_id == self.tenant_id,
                PPEIssue.person_id == person.id,
                PPEIssue.deleted_at.is_(None),
            )
        )
        active = await self._count(
            select(func.count())
            .select_from(PPEIssue)
            .where(
                PPEIssue.tenant_id == self.tenant_id,
                PPEIssue.person_id == person.id,
                PPEIssue.deleted_at.is_(None),
                PPEIssue.status == PPEIssueStatus.ISSUED,
            )
        )
        expired = await self._count(
            select(func.count())
            .select_from(PPEIssue)
            .where(
                PPEIssue.tenant_id == self.tenant_id,
                PPEIssue.person_id == person.id,
                PPEIssue.deleted_at.is_(None),
                PPEIssue.status == PPEIssueStatus.ISSUED,
                PPEIssue.expires_at.is_not(None),
                PPEIssue.expires_at < now,
            )
        )
        return EmployeePPESection(
            count=total, active_count=active, expired_count=expired, items=items
        )

    async def _build_permits(self, person: Person) -> EmployeePermitsSection:
        today = _today()
        stmt = (
            select(Permit)
            .where(
                Permit.tenant_id == self.tenant_id,
                Permit.person_id == person.id,
            )
            .order_by(desc(Permit.issued_at))
            .limit(self.max_items_per_section)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        items = [
            EmployeePermitItem(
                id=str(permit.id),
                permit_type=permit.permit_type,
                issued_at=permit.issued_at,
                valid_until=permit.valid_until,
                status=permit.status,
                position_id=str(permit.position_id) if permit.position_id else None,
                is_expired=bool(
                    permit.status == PermitStatus.ACTIVE.value
                    and permit.valid_until is not None
                    and permit.valid_until < today
                ),
            )
            for permit in rows
        ]
        total = await self._count(
            select(func.count())
            .select_from(Permit)
            .where(
                Permit.tenant_id == self.tenant_id,
                Permit.person_id == person.id,
            )
        )
        active = await self._count(
            select(func.count())
            .select_from(Permit)
            .where(
                Permit.tenant_id == self.tenant_id,
                Permit.person_id == person.id,
                Permit.status == PermitStatus.ACTIVE.value,
            )
        )
        expired = await self._count(
            select(func.count())
            .select_from(Permit)
            .where(
                Permit.tenant_id == self.tenant_id,
                Permit.person_id == person.id,
                Permit.status == PermitStatus.ACTIVE.value,
                Permit.valid_until.is_not(None),
                Permit.valid_until < today,
            )
        )
        return EmployeePermitsSection(
            count=total, active_count=active, expired_count=expired, items=items
        )

    async def _build_incidents(self, person: Person) -> EmployeeIncidentsSection:
        stmt = (
            select(Incident, IncidentPerson.role)
            .join(IncidentPerson, IncidentPerson.incident_id == Incident.id)
            .where(
                Incident.tenant_id == self.tenant_id,
                IncidentPerson.tenant_id == self.tenant_id,
                IncidentPerson.person_id == person.id,
                Incident.deleted_at.is_(None),
            )
            .order_by(desc(Incident.occurred_at))
            .limit(self.max_items_per_section)
        )
        rows = (await self.db.execute(stmt)).all()
        items = [
            EmployeeIncidentItem(
                id=str(inc.id),
                title=inc.title,
                incident_type=inc.incident_type,
                severity=inc.severity,
                status=inc.status,
                occurred_at=inc.occurred_at,
                role=role,
            )
            for inc, role in rows
        ]
        total = await self._count(
            select(func.count())
            .select_from(IncidentPerson)
            .join(Incident, Incident.id == IncidentPerson.incident_id)
            .where(
                IncidentPerson.tenant_id == self.tenant_id,
                IncidentPerson.person_id == person.id,
                Incident.tenant_id == self.tenant_id,
                Incident.deleted_at.is_(None),
            )
        )
        open_count = sum(1 for inc, _ in rows if inc.status not in {"closed", "cancelled"})
        return EmployeeIncidentsSection(count=total, open_count=open_count, items=items)

    async def _build_documents(self, person: Person) -> EmployeeDocumentsSection:
        stmt = (
            select(Document, Template.name)
            .outerjoin(Template, Template.id == Document.template_id)
            .where(
                Document.tenant_id == self.tenant_id,
                Document.person_id == person.id,
            )
            .order_by(desc(Document.created_at))
            .limit(self.max_items_per_section)
        )
        rows = (await self.db.execute(stmt)).all()
        items = [
            EmployeeDocumentItem(
                id=str(doc.id),
                template_id=str(doc.template_id) if doc.template_id else None,
                template_name=template_name,
                status=doc.status,
                is_signed=doc.signed_file_id is not None,
                created_at=doc.created_at,
            )
            for doc, template_name in rows
        ]
        total = await self._count(
            select(func.count())
            .select_from(Document)
            .where(
                Document.tenant_id == self.tenant_id,
                Document.person_id == person.id,
            )
        )
        signed = await self._count(
            select(func.count())
            .select_from(Document)
            .where(
                Document.tenant_id == self.tenant_id,
                Document.person_id == person.id,
                Document.signed_file_id.is_not(None),
            )
        )
        return EmployeeDocumentsSection(count=total, signed_count=signed, items=items)

    async def _build_briefings(self, person: Person) -> EmployeeBriefingsSection:
        now = _utcnow()
        stmt = (
            select(BriefingEntry, BriefingTemplate.title)
            .outerjoin(
                BriefingTemplate,
                BriefingTemplate.id == BriefingEntry.briefing_template_id,
            )
            .where(
                BriefingEntry.tenant_id == self.tenant_id,
                BriefingEntry.person_id == person.id,
                BriefingEntry.deleted_at.is_(None),
            )
            .order_by(desc(BriefingEntry.briefing_date))
            .limit(self.max_items_per_section)
        )
        rows = (await self.db.execute(stmt)).all()
        items = [
            EmployeeBriefingItem(
                id=str(entry.id),
                briefing_template_id=(
                    str(entry.briefing_template_id) if entry.briefing_template_id else None
                ),
                briefing_template_title=template_title,
                briefing_type=entry.briefing_type,
                briefing_date=entry.briefing_date,
                valid_until=entry.valid_until,
                status=entry.status,
                is_expired=bool(
                    entry.valid_until is not None and (as_utc(entry.valid_until) or now) < now
                ),
            )
            for entry, template_title in rows
        ]
        total = await self._count(
            select(func.count())
            .select_from(BriefingEntry)
            .where(
                BriefingEntry.tenant_id == self.tenant_id,
                BriefingEntry.person_id == person.id,
                BriefingEntry.deleted_at.is_(None),
            )
        )
        expired = await self._count(
            select(func.count())
            .select_from(BriefingEntry)
            .where(
                BriefingEntry.tenant_id == self.tenant_id,
                BriefingEntry.person_id == person.id,
                BriefingEntry.deleted_at.is_(None),
                BriefingEntry.valid_until.is_not(None),
                BriefingEntry.valid_until < now,
            )
        )
        return EmployeeBriefingsSection(count=total, expired_count=expired, items=items)

    async def _build_compliance_deadlines(
        self, person: Person
    ) -> EmployeeComplianceDeadlinesSection:
        now = _utcnow()
        stmt = (
            select(ComplianceDeadline)
            .where(
                ComplianceDeadline.tenant_id == self.tenant_id,
                ComplianceDeadline.person_id == person.id,
            )
            .order_by(ComplianceDeadline.due_at.asc())
            .limit(self.max_items_per_section)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        items = [
            EmployeeComplianceDeadlineItem(
                id=str(deadline.id),
                entity_type=deadline.entity_type,
                entity_id=str(deadline.entity_id),
                due_at=deadline.due_at,
                status=deadline.status,
                reminder_policy=deadline.reminder_policy,
                is_overdue=bool(
                    deadline.status not in {"closed", "completed", "cancelled"}
                    and (as_utc(deadline.due_at) or now) < now
                ),
            )
            for deadline in rows
        ]
        total = await self._count(
            select(func.count())
            .select_from(ComplianceDeadline)
            .where(
                ComplianceDeadline.tenant_id == self.tenant_id,
                ComplianceDeadline.person_id == person.id,
            )
        )
        overdue = sum(1 for item in items if item.is_overdue)
        upcoming = sum(
            1
            for item in items
            if item.status not in {"closed", "completed", "cancelled"} and not item.is_overdue
        )
        return EmployeeComplianceDeadlinesSection(
            count=total,
            overdue_count=overdue,
            upcoming_count=upcoming,
            items=items,
        )

    async def _build_audit(self, person: Person) -> EmployeeAuditSection:
        stmt = (
            select(AuditLog)
            .where(
                AuditLog.tenant_id == self.tenant_id,
                AuditLog.object_type == "person",
                AuditLog.object_id == str(person.id),
            )
            .order_by(desc(AuditLog.when))
            .limit(self.max_items_per_section)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        items = [
            EmployeeAuditItem(
                id=str(entry.id),
                when=entry.when,
                action=entry.action,
                actor_email=entry.actor_email,
                correlation_id=entry.correlation_id,
                changed_fields=_safe_dict(entry.changed_fields),
            )
            for entry in rows
        ]
        total = await self._count(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.tenant_id == self.tenant_id,
                AuditLog.object_type == "person",
                AuditLog.object_id == str(person.id),
            )
        )
        return EmployeeAuditSection(count=total, items=items)

    async def _count(self, stmt: Any) -> int:
        return int((await self.db.execute(stmt)).scalar_one() or 0)


def _disciplines_section(
    rows: list[DisciplineStatus],
    applicability: DisciplineApplicability,
    *,
    note: str | None = None,
) -> EmployeeDisciplinesSection:
    return EmployeeDisciplinesSection(
        overall=worst_light(rows).value,
        not_applicable=applicability.note,
        rows=[
            EmployeeDisciplineStatus(
                discipline=row.discipline.value,
                title=row.title,
                light=row.light.value,
                reason=row.reason,
                required=row.counts.required,
                missing=row.counts.missing,
                lapsed=row.counts.lapsed,
                expiring=row.counts.expiring,
            )
            for row in rows
        ],
        note=note,
    )


def _person_name(person: Person) -> str:
    """ФИО наставника — тем же правилом, что ``/internships``."""

    return " ".join(
        part for part in (person.last_name, person.first_name, person.middle_name) if part
    )


def _legacy_training_status(value: Any) -> TrainingSessionStatus:
    raw = value.value if hasattr(value, "value") else str(value or "")
    mapping = {
        "completed": TrainingSessionStatus.COMPLETED,
        "scheduled": TrainingSessionStatus.SCHEDULED,
        "draft": TrainingSessionStatus.SCHEDULED,
    }
    return mapping.get(raw, TrainingSessionStatus.SCHEDULED)


def _safe_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}
