from __future__ import annotations

import enum
from datetime import date, datetime, timezone
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field


class EventType(str, enum.Enum):
    DOCUMENT_CREATED = "DocumentCreated"
    DOCUMENT_GENERATED = "DocumentGenerated"
    DOCUMENT_SIGNED = "DocumentSigned"
    SIGNED = "Signed"
    DOCUMENT_EXPORTED = "DocumentExported"
    EXPORTED = "Exported"
    RISK_ASSESSED = "RiskAssessed"
    PPE_ISSUED = "PPEIssued"
    PPE_RETURNED = "PPEReturned"
    TRAINING_COMPLETED = "TrainingCompleted"
    TRAINING_ASSIGNED = "TrainingAssigned"
    TASK_DUE_SOON = "TaskDueSoon"
    TASK_OVERDUE = "TaskOverdue"
    APPROVAL_STARTED = "approval.started"
    APPROVAL_DECISION_MADE = "approval.decision_made"
    APPROVAL_COMPLETED = "approval.completed"
    EDO_SENT = "edo.sent"
    EDO_STATUS_CHANGED = "edo.status_changed"
    INCIDENT_CREATED = "IncidentCreated"
    INSPECTION_CREATED = "InspectionCreated"
    PRESCRIPTION_OVERDUE = "PrescriptionOverdue"
    MEDICAL_EXAM_RECORDED = "MedicalExamRecorded"
    PERSON_SUSPENDED = "PersonSuspended"
    PERSON_REINSTATED = "PersonReinstated"
    CONTRACTOR_READINESS_BLOCKED = "contractor.readiness_blocked"
    CONTRACTOR_READINESS_WARNING = "contractor.readiness_warning"
    CONTRACTOR_DOCUMENT_EXPIRING = "contractor.document_expiring"
    CONTRACTOR_DOCUMENT_EXPIRED = "contractor.document_expired"
    PPE_WRITTEN_OFF = "PPEWrittenOff"
    PPE_REPLACEMENT_DUE = "PPEReplacementDue"


class BaseEventPayload(BaseModel):
    tenant_id: str
    actor_id: str | None = None
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    event_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class DocumentCreatedPayload(BaseEventPayload):
    document_id: str
    document_version_id: str
    template_id: str
    template_version_id: str
    company_id: str
    person_id: str | None = None
    storage_key: str | None = None
    status: str


class DocumentGeneratedPayload(DocumentCreatedPayload):
    pass


class DocumentSignedPayload(BaseEventPayload):
    document_id: str
    document_version_id: str
    status: str
    signed_at: datetime
    signed_file_id: str | None = None


class DocumentExportedItem(BaseModel):
    template_id: str
    template_name: str
    person_id: str | None = None
    person_label: str | None = None
    document_version_id: str | None = None
    docx_storage_key: str | None = None
    pdf_storage_key: str | None = None
    docx_zip_path: str | None = None
    pdf_zip_path: str | None = None

    model_config = ConfigDict(extra="forbid")


class DocumentExportedPayload(BaseEventPayload):
    pack_id: str
    pack_code: str
    zip_storage_key: str
    documents: list[DocumentExportedItem]


class RiskAssessedPayload(BaseEventPayload):
    risk_assessment_id: str
    hazard_code: str
    company_id: str
    place_id: str | None = None
    position_id: str | None = None
    document_pack_id: str | None = None
    before: Mapping[str, Any]
    after: Mapping[str, Any]
    controls: list[Mapping[str, Any]]
    action_plan: Mapping[str, Any]


class PPEIssuedPayload(BaseEventPayload):
    ppe_issue_id: str
    person_id: str
    item_id: str | None
    quantity: int
    issued_at: datetime
    expires_at: datetime | None = None
    status: str


class PPEReturnedPayload(BaseEventPayload):
    ppe_issue_id: str
    person_id: str
    item_id: str | None
    quantity: int
    returned_at: datetime
    status: str


class PPEWrittenOffPayload(BaseEventPayload):
    ppe_issue_id: str
    person_id: str
    item_id: str | None
    quantity: int
    reason: str | None = None
    status: str


class PPEReplacementDuePayload(BaseEventPayload):
    ppe_issue_id: str
    person_id: str
    item_id: str | None
    item_name: str
    expires_at: datetime
    status: str


class TrainingAssignedPayload(BaseEventPayload):
    training_event_id: str
    plan_id: str
    company_id: str
    course_id: str
    position_id: str | None = None
    person_id: str | None = None
    due_date: date | None = None
    is_mandatory: bool
    assigned_at: datetime


class TrainingCompletedPayload(BaseEventPayload):
    training_event_id: str
    session_id: str
    plan_id: str | None = None
    person_id: str
    course_id: str
    completed_at: datetime | None = None
    status: str
    score: int | None = None


class InternalEventPayload(BaseEventPayload):
    metadata: Mapping[str, Any] = Field(default_factory=dict)


class IncidentCreatedPayload(BaseEventPayload):
    incident_id: str
    company_id: str
    site_id: str
    status: str
    severity: str
    incident_type: str


class InspectionCreatedPayload(BaseEventPayload):
    inspection_id: str
    company_id: str
    site_id: str | None = None
    status: str
    inspection_type: str
    authority: str


class PrescriptionOverduePayload(BaseEventPayload):
    prescription_id: str
    inspection_id: str
    incident_id: str | None = None
    assignee_id: str | None = None
    status: str
    due_at: date | None = None


class TaskDuePayload(BaseEventPayload):
    task_id: str
    title: str
    due_at: datetime | None = None
    assignee_id: str | None = None
    status: str
    priority: str
    overdue: bool = False


class MedicalExamRecordedPayload(BaseEventPayload):
    exam_id: str
    person_id: str
    exam_kind: str | None = None
    fitness: str | None = None
    valid_until: date | None = None


class PersonSuspendedPayload(BaseEventPayload):
    suspension_id: str
    person_id: str
    reason: str
    source_exam_id: str | None = None


class PersonReinstatedPayload(BaseEventPayload):
    suspension_id: str
    person_id: str


_PAYLOADS: dict[EventType, type[BaseEventPayload]] = {
    EventType.DOCUMENT_CREATED: DocumentCreatedPayload,
    EventType.DOCUMENT_GENERATED: DocumentGeneratedPayload,
    EventType.DOCUMENT_SIGNED: DocumentSignedPayload,
    EventType.SIGNED: DocumentSignedPayload,
    EventType.DOCUMENT_EXPORTED: DocumentExportedPayload,
    EventType.EXPORTED: DocumentExportedPayload,
    EventType.RISK_ASSESSED: RiskAssessedPayload,
    EventType.PPE_ISSUED: PPEIssuedPayload,
    EventType.PPE_RETURNED: PPEReturnedPayload,
    EventType.PPE_WRITTEN_OFF: PPEWrittenOffPayload,
    EventType.PPE_REPLACEMENT_DUE: PPEReplacementDuePayload,
    EventType.TRAINING_COMPLETED: TrainingCompletedPayload,
    EventType.TRAINING_ASSIGNED: TrainingAssignedPayload,
    EventType.TASK_DUE_SOON: TaskDuePayload,
    EventType.TASK_OVERDUE: TaskDuePayload,
    EventType.APPROVAL_STARTED: InternalEventPayload,
    EventType.APPROVAL_DECISION_MADE: InternalEventPayload,
    EventType.APPROVAL_COMPLETED: InternalEventPayload,
    EventType.EDO_SENT: InternalEventPayload,
    EventType.EDO_STATUS_CHANGED: InternalEventPayload,
    EventType.INCIDENT_CREATED: IncidentCreatedPayload,
    EventType.INSPECTION_CREATED: InspectionCreatedPayload,
    EventType.PRESCRIPTION_OVERDUE: PrescriptionOverduePayload,
    EventType.MEDICAL_EXAM_RECORDED: MedicalExamRecordedPayload,
    EventType.PERSON_SUSPENDED: PersonSuspendedPayload,
    EventType.PERSON_REINSTATED: PersonReinstatedPayload,
    EventType.CONTRACTOR_READINESS_BLOCKED: InternalEventPayload,
    EventType.CONTRACTOR_READINESS_WARNING: InternalEventPayload,
    EventType.CONTRACTOR_DOCUMENT_EXPIRING: InternalEventPayload,
    EventType.CONTRACTOR_DOCUMENT_EXPIRED: InternalEventPayload,
}


def resolve_event_type(event_type: EventType | str) -> EventType:
    if isinstance(event_type, EventType):
        return event_type
    aliases = {
        "Signed": EventType.DOCUMENT_SIGNED,
        "Exported": EventType.DOCUMENT_EXPORTED,
    }
    if event_type in aliases:
        return aliases[event_type]
    return EventType(event_type)


def normalize_payload(
    *,
    event_type: EventType,
    payload: Mapping[str, Any],
    tenant_id: str,
) -> tuple[BaseEventPayload, dict[str, Any]]:
    data = dict(payload)
    data.setdefault("tenant_id", tenant_id)
    if data["tenant_id"] != tenant_id:
        raise ValueError("Event payload tenant_id does not match outbox tenant_id")
    data.setdefault("occurred_at", datetime.now(tz=timezone.utc))
    model_cls = _PAYLOADS[event_type]
    parsed = model_cls.model_validate(data)
    return parsed, parsed.model_dump(mode="json")


def dedupe_key_for(event_type: EventType, payload: BaseEventPayload) -> str:
    if isinstance(payload, DocumentCreatedPayload):
        return f"{payload.document_id}:{payload.document_version_id}"
    if isinstance(payload, DocumentSignedPayload):
        return f"{payload.document_id}:{payload.document_version_id}:signed"
    if isinstance(payload, DocumentExportedPayload):
        return f"{payload.pack_id}:{payload.zip_storage_key}"
    if isinstance(payload, RiskAssessedPayload):
        return payload.risk_assessment_id
    if isinstance(payload, PPEIssuedPayload):
        return payload.ppe_issue_id
    if isinstance(payload, PPEReturnedPayload):
        return f"{payload.ppe_issue_id}:returned"
    if isinstance(payload, PPEWrittenOffPayload):
        return f"{payload.ppe_issue_id}:written_off"
    if isinstance(payload, PPEReplacementDuePayload):
        return f"{payload.ppe_issue_id}:replacement_due"
    if isinstance(payload, TrainingCompletedPayload):
        return payload.training_event_id
    if isinstance(payload, TrainingAssignedPayload):
        return payload.training_event_id
    if isinstance(payload, PrescriptionOverduePayload):
        return payload.prescription_id
    if isinstance(payload, TaskDuePayload):
        return payload.task_id
    if isinstance(payload, InternalEventPayload):
        return payload.event_id or f"internal:{event_type.value}:{payload.occurred_at.isoformat()}"
    if isinstance(payload, IncidentCreatedPayload):
        return payload.incident_id
    if isinstance(payload, InspectionCreatedPayload):
        return payload.inspection_id
    if isinstance(payload, MedicalExamRecordedPayload):
        return payload.exam_id
    if isinstance(payload, (PersonSuspendedPayload, PersonReinstatedPayload)):
        return payload.suspension_id
    raise ValueError(f"Unsupported event payload for {event_type.value}")
