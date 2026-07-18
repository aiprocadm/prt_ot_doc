"""Pin tests for ``DocumentVersion.status`` enum value casing.

iter-19 RB-002g cohort closure (closes 4 of 5 columns in the migration
``8d2c1a6c5e24_domain_normalization.py:43-62`` lowercase-enum cohort;
only ``NPABinding.entity_type`` remained after RB-002c (Person.employment_status)
and RB-002d (DocumentPack.module/scenario_type) — see
``backend/tests/test_documentpack_enum_values.py`` for the cohort log).

The PG enum ``documentversionstatus`` was created with lowercase values
("draft", "locked", "published", "archived") by migration
``8d2c1a6c5e24:55-58``. ``DocumentVersion.status`` uses
``Enum(DocumentVersionStatus, name="documentversionstatus")`` — the
defensive ``name=`` was already present, but ``values_callable=`` was
missing, so SQLAlchemy would send the *member name* (uppercase "DRAFT")
on INSERT. PG rejects with
``InvalidTextRepresentationError: invalid input value for enum
documentversionstatus: "DRAFT"``. SQLite is tolerant; only PG strict
mode surfaces this.

DocumentVersion is not exercised by ``bootstrap_demo_tenant`` (only Person
and DocumentPack are), so this column was deferred from Session 67/68
RB-002c/d. iter-19 closes proactively per cohort principle (shared root
cause + shared source migration = bundled fix preferable to one-at-a-time
discovery in CI).
"""

from __future__ import annotations

from sqlalchemy import inspect

from app.models.document import DocumentVersion, DocumentVersionStatus


def test_document_version_status_column_uses_enum_values_not_names() -> None:
    column = inspect(DocumentVersion).columns["status"]
    enum_type = column.type

    assert list(enum_type.enums) == [member.value for member in DocumentVersionStatus]
    assert list(enum_type.enums) == ["draft", "locked", "published", "archived"]


def test_document_version_status_python_member_names_diverge_from_values() -> None:
    # Precondition guard mirroring the rest of the cohort: if member.name
    # and member.value ever align, ``values_callable=`` silently becomes a
    # no-op. Keep this so a future refactor of the Python enum (e.g.
    # ``DRAFT = "DRAFT"``) has to consciously address this pin.
    assert DocumentVersionStatus.DRAFT.name != DocumentVersionStatus.DRAFT.value
    assert DocumentVersionStatus.DRAFT.value == "draft"
