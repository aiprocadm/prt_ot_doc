import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.modules.branding.schemas import IssuerRef, LetterheadOverride


def test_letterhead_flag_defaults_off():
    settings = Settings()
    assert settings.doc_pipeline_letterhead_auto is False


def test_issuer_defaults_to_company_kind():
    issuer = IssuerRef(company_id="c-1")
    assert issuer.kind == "company"
    assert issuer.company_id == "c-1"


def test_adhoc_issuer_requires_legal_name():
    with pytest.raises(ValidationError):
        IssuerRef(kind="adhoc", inline={"inn": "7700000000"})


def test_adhoc_issuer_accepts_inline_legal_name():
    issuer = IssuerRef(kind="adhoc", inline={"legal_name": "ООО Ромашка"})
    assert issuer.inline.legal_name == "ООО Ромашка"


def test_letterhead_override_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        LetterheadOverride(unknown=True)
