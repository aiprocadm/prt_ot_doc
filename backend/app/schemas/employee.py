"""Employee Card aggregate schemas (vNext-EMP-01 / Phase 3.2).

Aggregate view of an employee that joins personal data with related domain
records (roles & assignments, training history, medicals, PPE, permits,
incidents and an audit trail). Designed for the Unified Employee Card UI.

Notes
-----
* Schemas are intentionally read-only and tolerant: we mirror what the source
  modules return today, without forcing a richer contract on them.
* Counters (`count`) live alongside the items list so the frontend can render
  tab badges without fetching each list separately.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import Field

from app.models.document import DocumentStatus
from app.models.models import (
    EmploymentStatus,
    IncidentPersonRole,
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
    PPEIssueStatus,
    TrainingSessionStatus,
)
from app.schemas.base import BaseSchema


class EmployeePersonal(BaseSchema):
    """Identity and HR core fields derived from `Person`."""

    id: str
    company_id: str
    company_name: str | None = None
    position_id: str | None = None
    position_name: str | None = None
    workplace_id: str | None = None
    workplace_name: str | None = None
    first_name: str
    last_name: str
    middle_name: str | None = None
    fio: str
    birth_date: date | None = None
    email: str | None = None
    phone: str | None = None
    personnel_number: str | None = None
    hired_at: date | None = None
    snils: str | None = None
    passport: str | None = None
    employment_status: EmploymentStatus = EmploymentStatus.ACTIVE
    working_conditions_class: str | None = None
    hazardous_factors: list[str] = Field(default_factory=list)
    qualifications: list[dict[str, Any]] = Field(default_factory=list)
    current_ppe: list[dict[str, Any]] = Field(default_factory=list)


class EmployeeUserAccount(BaseSchema):
    """Linked system-level user account (looked up by tenant+email)."""

    user_id: str
    email: str
    role: str
    is_active: bool
    last_login_at: datetime | None = None
    additional_roles: list[str] = Field(default_factory=list)


class EmployeeRolesAndAssignments(BaseSchema):
    """Org placement (Personal+) plus optional system account."""

    company_id: str
    company_name: str | None = None
    position_id: str | None = None
    position_name: str | None = None
    workplace_id: str | None = None
    workplace_name: str | None = None
    employment_status: EmploymentStatus = EmploymentStatus.ACTIVE
    user_account: EmployeeUserAccount | None = None


class EmployeeTrainingItem(BaseSchema):
    id: str
    course_id: str | None = None
    course_title: str | None = None
    plan_id: str | None = None
    status: TrainingSessionStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    score: int | None = None


class EmployeeTrainingCertificate(BaseSchema):
    id: str
    code: str | None = None
    course_id: str | None = None
    course_title: str | None = None
    issued_at: date
    valid_until: date | None = None
    status: str | None = None


class EmployeeInternshipItem(BaseSchema):
    """Стажировка человека — та же запись, что в общем реестре ``/internships``.

    Недобор (``completed_short``) считается ТЕМ ЖЕ правилом, что в реестре:
    стажировка завершена, а смен меньше плана. Это ФАКТ расхождения плана и
    факта, а не вердикт о допуске к самостоятельной работе.
    """

    id: str
    subject: str | None = None
    discipline: str | None = None
    #: дисциплина словами; пусто — не размечена
    discipline_label: str | None = None
    #: пусто — наставник НЕ НАЗНАЧЕН, а не «неизвестен»
    mentor_name: str | None = None
    planned_shifts: int
    completed_shifts: int
    completed_short: bool
    started_on: date | None = None
    finished_on: date | None = None
    status: str
    status_label: str


class EmployeeTrainingSection(BaseSchema):
    sessions_count: int
    certificates_count: int
    #: стажировки — с среза-45; до него реестр был общий, а на человеке пусто
    internships_count: int = 0
    sessions: list[EmployeeTrainingItem] = Field(default_factory=list)
    certificates: list[EmployeeTrainingCertificate] = Field(default_factory=list)
    internships: list[EmployeeInternshipItem] = Field(default_factory=list)


class EmployeeMedicalItem(BaseSchema):
    id: str
    exam_type: str
    exam_date: date
    valid_until: date
    conclusion: str | None = None
    is_expired: bool = False


class EmployeeMedicalSection(BaseSchema):
    count: int
    expired_count: int
    items: list[EmployeeMedicalItem] = Field(default_factory=list)


class EmployeePPEIssueItem(BaseSchema):
    id: str
    item_id: str | None = None
    item_name: str
    quantity: int
    issued_at: datetime
    expires_at: datetime | None = None
    returned_at: datetime | None = None
    status: PPEIssueStatus
    is_expired: bool = False


class EmployeePPESection(BaseSchema):
    count: int
    active_count: int
    expired_count: int
    items: list[EmployeePPEIssueItem] = Field(default_factory=list)


class EmployeePermitItem(BaseSchema):
    id: str
    permit_type: str
    issued_at: date
    valid_until: date | None = None
    status: str
    position_id: str | None = None
    is_expired: bool = False


class EmployeePermitsSection(BaseSchema):
    count: int
    active_count: int
    expired_count: int
    items: list[EmployeePermitItem] = Field(default_factory=list)


class EmployeeIncidentItem(BaseSchema):
    id: str
    title: str
    incident_type: IncidentType
    severity: IncidentSeverity
    status: IncidentStatus
    occurred_at: datetime
    role: IncidentPersonRole


class EmployeeIncidentsSection(BaseSchema):
    count: int
    open_count: int
    items: list[EmployeeIncidentItem] = Field(default_factory=list)


class EmployeeAuditItem(BaseSchema):
    id: str
    when: datetime
    action: str
    actor_email: str | None = None
    correlation_id: str | None = None
    changed_fields: dict[str, Any] = Field(default_factory=dict)


class EmployeeAuditSection(BaseSchema):
    count: int
    items: list[EmployeeAuditItem] = Field(default_factory=list)


class EmployeeDocumentItem(BaseSchema):
    """Tenant-scoped document referencing this person via `Document.person_id`."""

    id: str
    template_id: str | None = None
    template_name: str | None = None
    status: DocumentStatus
    is_signed: bool = False
    created_at: datetime


class EmployeeDocumentsSection(BaseSchema):
    count: int
    signed_count: int
    items: list[EmployeeDocumentItem] = Field(default_factory=list)


class EmployeeBriefingItem(BaseSchema):
    """Single instructional briefing entry referencing this person."""

    id: str
    briefing_template_id: str | None = None
    briefing_template_title: str | None = None
    briefing_type: str
    briefing_date: datetime
    valid_until: datetime | None = None
    status: str
    is_expired: bool = False


class EmployeeBriefingsSection(BaseSchema):
    count: int
    expired_count: int
    items: list[EmployeeBriefingItem] = Field(default_factory=list)


class EmployeeComplianceDeadlineItem(BaseSchema):
    """Compliance deadline (medicals/training/PPE/etc.) tied to this person."""

    id: str
    entity_type: str
    entity_id: str
    due_at: datetime
    status: str
    reminder_policy: str | None = None
    is_overdue: bool = False


class EmployeeComplianceDeadlinesSection(BaseSchema):
    count: int
    overdue_count: int
    upcoming_count: int
    items: list[EmployeeComplianceDeadlineItem] = Field(default_factory=list)


class EmployeeDisciplineStatus(BaseSchema):
    """Строка светофора дисциплин на карточке сотрудника (срез-53, разд. 57.1).

    Те же поля, что у строки карточки площадки 360° (``SiteDisciplineRead``):
    цвет и расшифровка считаются одними правилами (``core/discipline_status``),
    и экран сотрудника читается теми же словами, что экран площадки.
    """

    discipline: str
    title: str
    light: str
    reason: str
    required: int = 0
    missing: int = 0
    lapsed: int = 0
    expiring: int = 0


class EmployeeDisciplinesSection(BaseSchema):
    """Светофор по всем ПРИМЕНИМЫМ дисциплинам словаря для одного человека."""

    #: итог по худшей ИЗМЕРЕННОЙ дисциплине; ``not_measured`` — если не измерено ничего
    overall: str
    rows: list[EmployeeDisciplineStatus] = Field(default_factory=list)
    #: почему светофор не считался (уволен) — словами, а не пустой таблицей
    note: str | None = None
    #: дисциплины вне редакции арендатора — одной фразой, чтобы семь строк вместо
    #: восьми не читались как недоделка (срез-54)
    not_applicable: str | None = None


class EmployeeCard(BaseSchema):
    """Top-level Unified Employee Card response."""

    person_id: str
    tenant_id: str
    generated_at: datetime
    personal: EmployeePersonal
    roles_and_assignments: EmployeeRolesAndAssignments
    disciplines: EmployeeDisciplinesSection
    training: EmployeeTrainingSection
    medicals: EmployeeMedicalSection
    ppe: EmployeePPESection
    permits: EmployeePermitsSection
    incidents: EmployeeIncidentsSection
    documents: EmployeeDocumentsSection
    briefings: EmployeeBriefingsSection
    compliance_deadlines: EmployeeComplianceDeadlinesSection
    audit: EmployeeAuditSection
