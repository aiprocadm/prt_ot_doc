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


import pytest

from app.modules.branding.letterhead import LetterheadResolver, LetterheadDecision
from app.modules.branding.schemas import IssuerRef, LetterheadOverride


class _FakeProfile:
    def __init__(self):
        self.preferred_header_preset_code = "default-letterhead"
        self.header_context = {"organization": {"legal_name": "ООО Группа"}, "company": {"id": "c-1", "name": "ООО Группа"}, "branch": {}, "doc": {}}
        self.branding = type("B", (), {"watermark_enabled": False, "watermark_text": None})()
        self.reproducibility = {"branding_payload_hash": "hash-1"}


class _FakeBranding:
    def __init__(self):
        self.tenant = type("T", (), {"id": "t-1"})()

    async def get_company(self, company_id):
        return type("C", (), {"id": company_id, "name": "ООО Группа", "preferred_header_preset_code": "default-letterhead"})()

    async def get_site(self, site_id):
        return None

    def build_profile(self, *, company, site=None):
        return _FakeProfile()

    async def get_layout_preset(self, preset_code):
        if preset_code is None:
            return None
        return type("P", (), {"code": preset_code, "watermark": {}})()

    def resolve_watermark(self, *, profile, preset, override=None):
        return {"enabled": False}


@pytest.mark.asyncio
async def test_disabled_override_returns_no_apply():
    resolver = LetterheadResolver(_FakeBranding())
    decision = await resolver.resolve(
        issuer=IssuerRef(company_id="c-1"),
        site_id=None,
        doc={},
        override=LetterheadOverride(disabled=True),
    )
    assert decision.apply is False


@pytest.mark.asyncio
async def test_company_issuer_resolves_preset_from_chain():
    resolver = LetterheadResolver(_FakeBranding())
    decision = await resolver.resolve(issuer=IssuerRef(company_id="c-1"), site_id=None, doc={}, override=None)
    assert decision.apply is True
    assert decision.preset_code == "default-letterhead"
    assert decision.header_context["company"]["id"] == "c-1"
    assert decision.branding_payload_hash == "hash-1"


@pytest.mark.asyncio
async def test_contractor_issuer_not_supported_in_slice_1():
    resolver = LetterheadResolver(_FakeBranding())
    with pytest.raises(NotImplementedError):
        await resolver.resolve(issuer=IssuerRef(kind="contractor", company_id="x"), site_id=None, doc={}, override=None)


@pytest.mark.asyncio
async def test_explicit_unknown_preset_raises():
    class _NoPresetBranding(_FakeBranding):
        async def get_layout_preset(self, preset_code):
            return None

    resolver = LetterheadResolver(_NoPresetBranding())
    with pytest.raises(ValueError):
        await resolver.resolve(
            issuer=IssuerRef(company_id="c-1"),
            site_id=None,
            doc={},
            override=LetterheadOverride(preset_code="does-not-exist"),
        )


@pytest.mark.asyncio
async def test_adhoc_issuer_builds_inline_context():
    resolver = LetterheadResolver(_FakeBranding())
    issuer = IssuerRef(kind="adhoc", inline={"legal_name": "ООО Внешняя"})
    decision = await resolver.resolve(issuer=issuer, site_id=None, doc={}, override=LetterheadOverride(preset_code="default-letterhead"))
    assert decision.apply is True
    assert decision.header_context["organization"]["legal_name"] == "ООО Внешняя"
    assert decision.header_context["company"]["id"] is None
