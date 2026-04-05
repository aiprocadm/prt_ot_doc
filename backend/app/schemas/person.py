from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import EmailStr, Field, computed_field, field_validator

from app.models.models import EmploymentStatus
from app.schemas.base import BaseSchema


def _empty_str_to_none(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _parse_date_string(raw: str) -> date | None:
    text = raw.strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _normalize_optional_date_in_row(row: dict[str, Any], key: str) -> None:
    if key not in row:
        return
    val = row[key]
    if val is None:
        return
    if isinstance(val, date):
        return
    if isinstance(val, datetime):
        row[key] = val.date()
        return
    if isinstance(val, str):
        parsed = _parse_date_string(val)
        if parsed is not None:
            row[key] = parsed
        else:
            row.pop(key, None)
        return
    row.pop(key, None)


def _sanitize_qualifications_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        row = dict(item)
        row["name"] = name
        kind = row.get("kind")
        if kind is None or (isinstance(kind, str) and not kind.strip()):
            row.pop("kind", None)
        for dk in ("issued_at", "valid_until"):
            _normalize_optional_date_in_row(row, dk)
        out.append(row)
    return out


def _sanitize_ppe_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        row = dict(item)
        row["name"] = name
        for dk in ("issued_at", "expires_at"):
            _normalize_optional_date_in_row(row, dk)
        out.append(row)
    return out


def _sanitize_hazardous_factors_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if item is None or isinstance(item, (dict, list)):
            continue
        text = str(item).strip()
        if text:
            out.append(text)
    return out


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

    @field_validator("email", mode="before")
    @classmethod
    def _email_blank_to_none(cls, value: object) -> object:
        return _empty_str_to_none(value)

    @field_validator("qualifications", mode="before")
    @classmethod
    def _qualifications_drop_invalid(cls, value: Any) -> Any:
        return _sanitize_qualifications_list(value)

    @field_validator("current_ppe", mode="before")
    @classmethod
    def _ppe_drop_invalid(cls, value: Any) -> Any:
        return _sanitize_ppe_list(value)

    @field_validator("hazardous_factors", mode="before")
    @classmethod
    def _hazardous_factors_sanitize(cls, value: Any) -> Any:
        return _sanitize_hazardous_factors_list(value)

    @field_validator("employment_status", mode="before")
    @classmethod
    def _employment_status_coerce(cls, value: object) -> object:
        if value is None:
            return EmploymentStatus.ACTIVE
        if isinstance(value, EmploymentStatus):
            return value
        if isinstance(value, str):
            try:
                return EmploymentStatus(value)
            except ValueError:
                return EmploymentStatus.ACTIVE
        return EmploymentStatus.ACTIVE

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

    @field_validator("email", mode="before")
    @classmethod
    def _email_blank_to_none_create(cls, value: object) -> object:
        return _empty_str_to_none(value)


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

    @field_validator("email", mode="before")
    @classmethod
    def _email_blank_to_none_update(cls, value: object) -> object:
        return _empty_str_to_none(value)
