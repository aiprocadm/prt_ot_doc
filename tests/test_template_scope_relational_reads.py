"""RC-013 — template scope resolution reads the indexed relational columns.

The relational scope model (Template.scope_level / scope_company_id /
scope_site_id + index ix_template_scope_level_company_site, migration next68)
already exists. These pins lock the *reader* cutover: the document-resolution
path must read scope from the relational columns (with a JSON fallback for
rows written/backfilled before normalization), and the alias mapping must be
preserved so matching/scoring is identical.
"""

from __future__ import annotations

import importlib

documents = importlib.import_module("app.api.routes.documents")
Template = importlib.import_module("app.models.models").Template

_normalize_scope_level = documents._normalize_scope_level
_scope_target_ids = documents._scope_target_ids


def test_level_prefers_relational_column_over_json() -> None:
    # Column says "site"; legacy JSON disagrees ("tenant") — column wins.
    t = Template(scope_level="site", metadata_json={"scope": {"level": "tenant"}})
    assert _normalize_scope_level(t) == "site"


def test_level_aliases_applied_to_column_value() -> None:
    # organization/legal_entity → company, global → system, branch → site.
    assert (
        _normalize_scope_level(Template(scope_level="organization", metadata_json={})) == "company"
    )
    assert (
        _normalize_scope_level(Template(scope_level="legal_entity", metadata_json={})) == "company"
    )
    assert _normalize_scope_level(Template(scope_level="global", metadata_json={})) == "system"
    assert _normalize_scope_level(Template(scope_level="branch", metadata_json={})) == "site"


def test_level_falls_back_to_json_when_column_empty() -> None:
    t = Template(scope_level=None, metadata_json={"scope": {"level": "company"}})
    assert _normalize_scope_level(t) == "company"


def test_level_defaults_to_tenant_when_nothing_set() -> None:
    assert _normalize_scope_level(Template(scope_level=None, metadata_json={})) == "tenant"


def test_level_falls_back_to_json_when_column_holds_default_tenant() -> None:
    # A persisted un-backfilled row: scope_level is NOT NULL with a server default
    # of "tenant", so a row written/backfilled before normalization (or created
    # bypassing the catalog API) surfaces scope_level="tenant" even though its real
    # scope still lives in the JSON mirror. The default "tenant" must defer to a
    # more specific mirror level so the documented fallback reaches persisted rows.
    t = Template(scope_level="tenant", metadata_json={"scope": {"level": "site"}})
    assert _normalize_scope_level(t) == "site"


def test_level_keeps_default_tenant_when_mirror_agrees_or_absent() -> None:
    # A genuinely tenant-scoped row (mirror in sync, or no mirror) stays "tenant".
    assert (
        _normalize_scope_level(Template(scope_level="tenant", metadata_json={"scope": {}}))
        == "tenant"
    )
    assert (
        _normalize_scope_level(
            Template(scope_level="tenant", metadata_json={"scope": {"level": "tenant"}})
        )
        == "tenant"
    )


def test_target_ids_prefer_relational_columns() -> None:
    # Columns win even when the JSON mirror holds stale/different ids.
    t = Template(
        scope_company_id="c1",
        scope_site_id="s1",
        metadata_json={"scope": {"company_id": "STALE", "site_id": "STALE"}},
    )
    assert _scope_target_ids(t) == ("c1", "s1")


def test_target_ids_fall_back_to_json_when_columns_unset() -> None:
    t = Template(
        scope_company_id=None,
        scope_site_id=None,
        metadata_json={"scope": {"company_id": "c9", "site_id": "s9"}},
    )
    assert _scope_target_ids(t) == ("c9", "s9")
