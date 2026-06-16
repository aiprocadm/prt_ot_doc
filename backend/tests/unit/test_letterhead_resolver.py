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


from app.modules.branding.schemas import BrandingProfilePayload


def test_assemble_header_context_shape():
    from app.modules.branding.service import assemble_header_context

    branding = BrandingProfilePayload(legal_name="ООО Тест", inn="7700000000")
    ctx = assemble_header_context(
        branding=branding,
        company_ref={"id": "c-1", "name": "ООО Тест"},
        site=None,
        doc={"title": "Приказ", "number": "12"},
    )
    assert ctx["organization"]["legal_name"] == "ООО Тест"
    assert ctx["company"] == {"id": "c-1", "name": "ООО Тест"}
    assert ctx["branch"] == {}
    assert ctx["doc"] == {"title": "Приказ", "number": "12"}


def test_build_adhoc_context_uses_inline_payload():
    from app.modules.branding.service import build_adhoc_context

    branding = BrandingProfilePayload(legal_name="ООО Внешняя", inn="5500000000")
    ctx = build_adhoc_context(branding=branding, doc={"title": "Договор"})
    assert ctx["organization"]["legal_name"] == "ООО Внешняя"
    assert ctx["company"]["id"] is None
    assert ctx["company"]["name"] == "ООО Внешняя"
