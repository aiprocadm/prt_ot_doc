from types import SimpleNamespace

from app.services.package_pipeline import (
    PACK_TYPE_CODE_MAP,
    DocumentPackageType,
    build_idempotency_key,
)
from app.domains.packs.definitions import (
    PACK_CODE_INCIDENT,
    PACK_CODE_NEW_COMPANY,
    PACK_CODE_SITE_ACCESS,
)


def test_pack_type_mapping_matches_defaults():
    assert PACK_TYPE_CODE_MAP[DocumentPackageType.ENTER_SITE] == PACK_CODE_SITE_ACCESS
    assert PACK_TYPE_CODE_MAP[DocumentPackageType.INCIDENT] == PACK_CODE_INCIDENT
    assert PACK_TYPE_CODE_MAP[DocumentPackageType.NEW_COMPANY] == PACK_CODE_NEW_COMPANY
    assert PACK_TYPE_CODE_MAP[DocumentPackageType.PREPARE_INSPECTION] == PACK_CODE_NEW_COMPANY


def test_build_idempotency_key_is_deterministic():
    pack = SimpleNamespace(id="pack-1")
    template = SimpleNamespace(id="tpl-1")
    value_a = build_idempotency_key(
        pack=pack, template=template, company_id="comp", site_id=None, person_id=None
    )
    value_b = build_idempotency_key(
        pack=pack, template=template, company_id="comp", site_id=None, person_id=None
    )
    assert value_a == value_b
    assert value_a != build_idempotency_key(
        pack=pack, template=template, company_id="comp", site_id="site", person_id=None
    )
