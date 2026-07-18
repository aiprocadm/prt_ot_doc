import pytest
from pydantic import ValidationError

from app.schemas.work_permit import WorkPermitSignatureCreate


def test_signature_create_defaults_attested():
    s = WorkPermitSignatureCreate(person_id="p1")
    assert s.mode == "attested"


def test_signature_create_accepts_code():
    assert WorkPermitSignatureCreate(person_id="p1", mode="code").mode == "code"


def test_signature_create_rejects_unknown_mode():
    with pytest.raises(ValidationError):
        WorkPermitSignatureCreate(person_id="p1", mode="bogus")
