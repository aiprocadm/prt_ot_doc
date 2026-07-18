"""Regression guard for the FeatureEnablement cross-base foreign-key bug
(W-A · TZ-3.2-V11-01).

``FeatureEnablement`` is a ``TenantBaseModel`` (TenantBase metadata) while
``Feature`` is a ``SharedModel`` (SharedBase metadata). A SQLAlchemy
``ForeignKey("feature.id")`` therefore crosses the two declarative metadatas.
SQLAlchemy resolves string-form foreign keys by name within the *source*
table's own ``MetaData``; the shared ``feature`` table only becomes visible to
``TenantBase.metadata`` after ``register_cross_base_fk_resolution()`` runs on
the ``after_configured`` mapper event. The test harness (and any boot path that
calls ``metadata.create_all()`` before the first ``configure_mappers()``)
creates tables *before* that mirror exists, so the unresolved FK raised
``sqlalchemy.exc.NoReferencedTableError`` and broke the entire app at import
time.

The fix keeps ``feature_id`` a plain ``String(36)`` column (cross-base FKs are
unenforceable in this two-metadata setup anyway — the repo references shared
rows from tenant tables via plain string columns). These tests fail before the
fix and pass after it.
"""

from __future__ import annotations


def test_feature_models_import_and_configure_mappers() -> None:
    """Importing the feature models must not break mapper configuration."""

    from sqlalchemy.orm import configure_mappers

    from app.models.feature import Feature, FeatureEnablement  # noqa: F401

    configure_mappers()  # must not raise


def test_feature_enablement_has_no_cross_base_foreign_key() -> None:
    """``feature_id`` must be a plain column, not a cross-base FK to ``feature``.

    This is the precise root-cause invariant: a SQLAlchemy ForeignKey from the
    tenant-scoped ``featureenablement`` table to the shared ``feature`` table is
    unresolvable during a create_all-first boot and re-introducing it would once
    again raise ``NoReferencedTableError`` and break app startup.
    """

    from app.models.feature import FeatureEnablement

    fks = list(FeatureEnablement.__table__.c.feature_id.foreign_keys)
    assert fks == [], (
        "feature_id must not declare a cross-base ForeignKey to `feature`; "
        f"found {[str(fk.target_fullname) for fk in fks]}"
    )


def test_feature_enablement_table_creates_without_resolvable_feature() -> None:
    """Reproduce the app-boot ordering that originally failed.

    Copy only the tenant-scoped tables into a fresh ``MetaData`` where the
    shared ``feature`` table is intentionally absent (mirroring the harness'
    create_all-before-mirror window). ``tenant`` is copied so the always-present
    ``tenant_id`` FK resolves and ``feature`` is the only possible unresolved
    reference. With the cross-base FK present this raised
    ``NoReferencedTableError``; with ``feature_id`` as a plain column it creates
    cleanly.
    """

    from sqlalchemy import MetaData, create_engine

    from app.models.feature import FeatureEnablement
    from app.models.models import Tenant

    md = MetaData()
    Tenant.__table__.to_metadata(md, schema=None)
    FeatureEnablement.__table__.to_metadata(md, schema=None)

    engine = create_engine("sqlite:///:memory:")
    try:
        md.create_all(engine)  # must not raise NoReferencedTableError
    finally:
        engine.dispose()
