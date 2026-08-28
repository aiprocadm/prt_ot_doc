"""Training-domain ORM models — extracted from models.py (ARCH-2 decomposition).

Pure move of class definitions: same ``TenantBase`` registry, identical tables.
The public import paths ``from app.models import X`` and
``from app.models.models import X`` are preserved by re-exports in
``models.py`` / ``__init__.py`` — zero import-contract change. External classes
referenced only in ``Mapped[...]`` annotations (Person/Company/Position/File)
are resolved by SQLAlchemy's class registry, so a ``TYPE_CHECKING`` import is
enough and there is no runtime import cycle back into models.py.
"""

from __future__ import annotations

import enum
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import SoftDeleteMixin, TenantBaseModel, native_enum

if TYPE_CHECKING:  # pragma: no cover - type-checker only; SA resolves via registry
    from app.models.file import File
    from app.models.models import Company, Person, Position


class TrainingStatus(str, enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"


class Training(TenantBaseModel):
    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), nullable=False, index=True)
    course_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[TrainingStatus] = mapped_column(Enum(TrainingStatus), nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    person: Mapped[Person] = relationship(backref="trainings")


class TrainingCourse(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "training_course"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text)
    duration_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valid_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Доп. №1 разд. 56.1: дисциплина программы — код из ОБЩЕГО словаря
    #: ``app.core.disciplines.Discipline``. До этой колонки курс «Курсовое
    #: обучение по ГО» был неотличим от курса по охране труда, и вопрос «какие
    #: программы обучения по ГО заведены» не имел ответа в данных. Дыра
    #: кросс-дисциплинарная: так же неотличимы ПТМ, обучение по отходам и
    #: подготовка по промбезопасности.
    #:
    #: ПУСТО означает «не размечено», а НЕ «общая охрана труда»: приписывать
    #: незаряженной записи принадлежность — то же враньё, что и у инструктажа
    #: с неизвестным видом (там ``discipline_of_briefing`` возвращает ``None``
    #: ровно с этим доводом).
    discipline: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "title", name="uq_training_course_title"),
        Index("ix_training_course_code", "tenant_id", "code"),
        Index("ix_training_course_discipline", "tenant_id", "discipline"),
    )


class TrainingPlan(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "training_plan"

    company_id: Mapped[str] = mapped_column(
        ForeignKey("company.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position_id: Mapped[str | None] = mapped_column(
        ForeignKey("position.id", ondelete="SET NULL"), nullable=True, index=True
    )
    person_id: Mapped[str | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), nullable=True, index=True
    )
    course_id: Mapped[str] = mapped_column(
        ForeignKey("training_course.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(tz=timezone.utc), nullable=False
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    company: Mapped[Company] = relationship(backref="training_plans")
    position: Mapped[Position | None] = relationship(backref="training_plans")
    person: Mapped[Person | None] = relationship(backref="training_plans")
    course: Mapped[TrainingCourse] = relationship(backref="training_plans")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "course_id",
            "company_id",
            "position_id",
            "person_id",
            name="uq_training_plan_target",
        ),
    )


class TrainingSessionStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class TrainingSession(TenantBaseModel):
    __tablename__ = "training_session"

    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), nullable=False, index=True)
    course_id: Mapped[str] = mapped_column(
        ForeignKey("training_course.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[str | None] = mapped_column(
        ForeignKey("training_plan.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[TrainingSessionStatus] = mapped_column(
        native_enum(TrainingSessionStatus), nullable=False, default=TrainingSessionStatus.SCHEDULED
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    person: Mapped[Person] = relationship(backref="training_sessions")
    course: Mapped[TrainingCourse] = relationship(backref="training_sessions")
    plan: Mapped[TrainingPlan | None] = relationship(backref="sessions")

    __table_args__ = (Index("ix_training_session_status", "tenant_id", "status"),)


class TrainingCertificate(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "training_certificates"

    code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    training_program_id: Mapped[str | None] = mapped_column(
        ForeignKey("training_programs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    person_id: Mapped[str | None] = mapped_column(
        ForeignKey("person.id"), nullable=True, index=True
    )
    issued_at: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    file_id: Mapped[str | None] = mapped_column(
        ForeignKey("file.id", ondelete="SET NULL"), nullable=True, index=True
    )
    external_registry_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    external_registry_payload: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )

    # backward-compatible legacy fields
    course_id: Mapped[str | None] = mapped_column(
        ForeignKey("training_course.id", ondelete="CASCADE"), nullable=True, index=True
    )
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("training_session.id", ondelete="SET NULL"), nullable=True, index=True
    )
    plan_id: Mapped[str | None] = mapped_column(
        ForeignKey("training_plan.id", ondelete="SET NULL"), nullable=True, index=True
    )
    number: Mapped[str | None] = mapped_column(String(64), nullable=True)

    person: Mapped[Person | None] = relationship(backref="training_certificates")
    course: Mapped[TrainingCourse | None] = relationship(backref="training_certificates")
    session: Mapped[TrainingSession | None] = relationship(backref="certificate")
    plan: Mapped[TrainingPlan | None] = relationship(backref="certificates")
    file: Mapped[File | None] = relationship("File", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_training_certificates_code"),
        UniqueConstraint("tenant_id", "number", name="uq_training_certificate_number"),
        Index("ix_training_certificate_valid", "tenant_id", "valid_until"),
    )


class TrainingProgram(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "training_programs"

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    duration_hours: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    validity_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    external_registry_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_training_programs_code"),)


class TrainingModule(TenantBaseModel):
    __tablename__ = "training_modules"

    training_program_id: Mapped[str] = mapped_column(
        ForeignKey("training_programs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    module_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    materials_json: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )


class TrainingLesson(TenantBaseModel):
    __tablename__ = "training_lessons"

    training_module_id: Mapped[str] = mapped_column(
        ForeignKey("training_modules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    lesson_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False, default="document")
    content_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    materials_json: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class TrainingTest(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "training_tests"

    training_program_id: Mapped[str] = mapped_column(
        ForeignKey("training_programs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    passing_score: Mapped[int] = mapped_column(Integer, nullable=False)
    time_limit_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempts_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    randomize_questions: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class TrainingTestQuestion(TenantBaseModel):
    __tablename__ = "training_test_questions"

    training_test_id: Mapped[str] = mapped_column(
        ForeignKey("training_tests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    question_type: Mapped[str] = mapped_column(String(16), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    options_json: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    correct_answer_json: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    weight: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False, default=1)


class TrainingGroup(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "training_groups"

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    training_program_id: Mapped[str] = mapped_column(
        ForeignKey("training_programs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    teacher_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    planned_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    planned_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    site_id: Mapped[str | None] = mapped_column(
        ForeignKey("site.id", ondelete="SET NULL"), nullable=True
    )
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("company.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_training_groups_code"),)


class TrainingEnrollment(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "training_enrollments"

    training_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("training_groups.id", ondelete="SET NULL"), nullable=True, index=True
    )
    training_program_id: Mapped[str] = mapped_column(
        ForeignKey("training_programs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[str | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assigned_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    assignment_source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc)
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="assigned")
    score: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    certificate_id: Mapped[str | None] = mapped_column(
        ForeignKey("training_certificates.id", ondelete="SET NULL"), nullable=True
    )
    protocol_id: Mapped[str | None] = mapped_column(
        ForeignKey("training_protocols.id", ondelete="SET NULL"), nullable=True
    )
    progress_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    completion_status: Mapped[str] = mapped_column(String(32), nullable=False, default="assigned")
    completion_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completion_payload: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    external_runtime_state: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )


class TrainingAttempt(TenantBaseModel):
    __tablename__ = "training_attempts"

    training_enrollment_id: Mapped[str] = mapped_column(
        ForeignKey("training_enrollments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    score: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    answers_json: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    external_session_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_payload: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )


class TrainingProtocol(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "training_protocols"

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    training_program_id: Mapped[str] = mapped_column(
        ForeignKey("training_programs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    training_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("training_groups.id", ondelete="SET NULL"), nullable=True, index=True
    )
    protocol_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    file_id: Mapped[str | None] = mapped_column(
        ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_training_protocols_code"),)


class TrainingProtocolItem(TenantBaseModel):
    __tablename__ = "training_protocol_items"

    training_protocol_id: Mapped[str] = mapped_column(
        ForeignKey("training_protocols.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[str | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), nullable=True
    )
    fio_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    enrollment_id: Mapped[str | None] = mapped_column(
        ForeignKey("training_enrollments.id", ondelete="SET NULL"), nullable=True
    )
