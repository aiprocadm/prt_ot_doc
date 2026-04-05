from __future__ import annotations

from datetime import date

from pydantic import EmailStr, Field, computed_field

from app.models.models import EmploymentStatus
from app.schemas.base import BaseSchema


class QualificationRecord(BaseSchema):
    """Stored information about mandatory trainings and permits."""

    name: str = Field(min_length=1, max_length=255)
    kind: str = Field(default="training", min_length=1, max_length=64)
    issued_at: date | None = None
    valid_until: date | None = None
    issuer: str | None = Field(default=None, max_length=255)
    document: str | None = Field(default=None, max_length=255)


class PPEItem(BaseSchema):
    name: str = Field(min_length=1, max_length=255)
    issued_at: date | None = None
    expires_at: date | None = None
    status: str | None = Field(default=None, max_length=32)


class PersonRead(BaseSchema):
    id: str
    company_id: str
    position_id: str | None = None
    workplace_id: str | None = None
    first_name: str
    last_name: str
    middle_name: str | None = None
    birth_date: date | None = None
    personnel_number: str | None = None
    hired_at: date | None = None
    qualifications: list[QualificationRecord] = Field(default_factory=list)
    snils: str | None = None
    passport: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    employment_status: EmploymentStatus = EmploymentStatus.ACTIVE
    current_ppe: list[PPEItem] = Field(default_factory=list)
    working_conditions_class: str | None = None
    hazardous_factors: list[str] = Field(default_factory=list)

    @computed_field(return_type=str)
    def fio(self) -> str:
        parts = [self.last_name, self.first_name, self.middle_name or ""]
        return " ".join(part for part in parts if part).strip()


class PersonPage(BaseSchema):
    items: list[PersonRead]
    total: int


class PersonCreate(BaseSchema):
    company_id: str = Field(min_length=1, max_length=36)
    position_id: str | None = Field(default=None, min_length=1, max_length=36)
    workplace_id: str | None = Field(default=None, min_length=1, max_length=36)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    birth_date: date | None = None
    personnel_number: str | None = Field(default=None, max_length=32)
    hired_at: date | None = None
    qualifications: list[QualificationRecord] = Field(default_factory=list)
    snils: str | None = Field(default=None, max_length=32)
    passport: str | None = Field(default=None, max_length=64)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    employment_status: EmploymentStatus = EmploymentStatus.ACTIVE
    current_ppe: list[PPEItem] = Field(default_factory=list)
    working_conditions_class: str | None = Field(default=None, max_length=32)
    hazardous_factors: list[str] = Field(default_factory=list)


class PersonUpdate(BaseSchema):
    company_id: str | None = Field(default=None, min_length=1, max_length=36)
    position_id: str | None = Field(default=None, min_length=1, max_length=36)
    workplace_id: str | None = Field(default=None, min_length=1, max_length=36)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    birth_date: date | None = None
    personnel_number: str | None = Field(default=None, max_length=32)
    hired_at: date | None = None
    qualifications: list[QualificationRecord] | None = None
    snils: str | None = Field(default=None, max_length=32)
    passport: str | None = Field(default=None, max_length=64)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    employment_status: EmploymentStatus | None = None
    current_ppe: list[PPEItem] | None = None
    working_conditions_class: str | None = Field(default=None, max_length=32)
    hazardous_factors: list[str] | None = None
