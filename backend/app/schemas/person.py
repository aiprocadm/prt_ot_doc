from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import EmailStr, Field, TypeAdapter, ValidationInfo, computed_field, field_validator

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
        fixed = _truncate_qualification_row(item)
        if fixed is not None:
            out.append(fixed)
    return out


def _sanitize_ppe_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        fixed = _truncate_ppe_row(item)
        if fixed is not None:
            out.append(fixed)
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


def _coerce_optional_plain_str(value: object, *, max_len: int | None = None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
    elif isinstance(value, (int, float, bool)):
        text = str(value).strip()
    else:
        return None
    if not text:
        return None
    if max_len is not None and len(text) > max_len:
        return text[:max_len]
    return text


_email_adapter = TypeAdapter(EmailStr)

_READ_SCALAR_STR_MAX: dict[str, int] = {
    "middle_name": 100,
    "phone": 32,
    "snils": 32,
    "passport": 64,
    "personnel_number": 32,
    "working_conditions_class": 32,
}


def _coerce_uuid_like_str(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, UUID):
        return str(value)
    return str(value)


def _coerce_optional_uuid_like_str(value: object) -> str | None:
    if value is None:
        return None
    text = _coerce_uuid_like_str(value).strip()
    return text or None


def _coerce_calendar_date(value: object) -> object:
    """ORM/драйверы часто отдают datetime вместо date — Pydantic date поля это отвергают."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return _parse_date_string(value)
    return value


def _coerce_required_name_part(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", errors="replace")
    return str(value)


def _email_str_or_none(value: object) -> str | None:
    cleaned = _empty_str_to_none(value)
    if cleaned is None or not isinstance(cleaned, str):
        return None
    candidate = cleaned.strip()
    if not candidate:
        return None
    try:
        return str(_email_adapter.validate_python(candidate))
    except Exception:
        return None


def _truncate_qualification_row(row: dict[str, Any]) -> dict[str, Any] | None:
    name_raw = row.get("name")
    name = str(name_raw).strip() if name_raw is not None else ""
    if not name:
        return None
    if len(name) > 255:
        name = name[:255]
    row = dict(row)
    row["name"] = name
    kind_raw = row.get("kind")
    if kind_raw is None or (isinstance(kind_raw, str) and not kind_raw.strip()):
        row.pop("kind", None)
    else:
        kind = str(kind_raw).strip()[:64]
        if kind:
            row["kind"] = kind
        else:
            row.pop("kind", None)
    for dk in ("issued_at", "valid_until"):
        _normalize_optional_date_in_row(row, dk)
    for sk, mlen in (("issuer", 255), ("document", 255)):
        if sk not in row:
            continue
        coerced = _coerce_optional_plain_str(row.get(sk), max_len=mlen)
        if coerced is None:
            row.pop(sk, None)
        else:
            row[sk] = coerced
    return row


def _truncate_ppe_row(row: dict[str, Any]) -> dict[str, Any] | None:
    name_raw = row.get("name")
    name = str(name_raw).strip() if name_raw is not None else ""
    if not name:
        return None
    if len(name) > 255:
        name = name[:255]
    row = dict(row)
    row["name"] = name
    for dk in ("issued_at", "expires_at"):
        _normalize_optional_date_in_row(row, dk)
    if "status" in row:
        st = _coerce_optional_plain_str(row.get("status"), max_len=32)
        if st is None:
            row.pop("status", None)
        else:
            row["status"] = st
    return row


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

    @field_validator("id", "company_id", mode="before")
    @classmethod
    def _coerce_person_ids(cls, value: object) -> object:
        if value is None:
            return None
        return _coerce_uuid_like_str(value)

    @field_validator("position_id", "workplace_id", mode="before")
    @classmethod
    def _coerce_person_optional_fk(cls, value: object) -> object:
        return _coerce_optional_uuid_like_str(value)

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def _coerce_person_names(cls, value: object) -> object:
        return _coerce_required_name_part(value)

    @field_validator("birth_date", "hired_at", mode="before")
    @classmethod
    def _coerce_person_calendar_dates(cls, value: object) -> object:
        return _coerce_calendar_date(value)

    @field_validator("email", mode="before")
    @classmethod
    def _email_blank_or_invalid_to_none(cls, value: object) -> object:
        return _email_str_or_none(value)

    @field_validator("middle_name", "phone", "snils", "passport", "personnel_number", "working_conditions_class", mode="before")
    @classmethod
    def _optional_str_fields_coerce(cls, value: object, info: ValidationInfo) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
        elif isinstance(value, (int, float, bool)):
            text = str(value).strip()
        else:
            return None
        if not text:
            return None
        max_len = _READ_SCALAR_STR_MAX.get(info.field_name or "")
        if max_len is not None and len(text) > max_len:
            return text[:max_len]
        return text

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
