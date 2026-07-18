"""Pin tests for ``NPABinding.entity_type`` enum value casing.

iter-19 RB-002h — final cohort closure for migration
``8d2c1a6c5e24_domain_normalization.py:43-62`` (5 lowercase PG enum types).
With this pin, all 5 enum columns from that migration use
``values_callable=`` to match the lowercase PG values:

* ``Person.employment_status``            (RB-002c, PR #583)
* ``DocumentPack.module``                 (RB-002d, PR #584)
* ``DocumentPack.scenario_type``          (RB-002d, PR #584)
* ``DocumentVersion.status``              (RB-002g, this iter)
* ``NPABinding.entity_type``              (RB-002h, this iter)

The PG enum ``npabindingtarget`` was created with lowercase values
("template_version", "document", "pack") by migration
``8d2c1a6c5e24:59-62``. ``NPABinding.entity_type`` used
``Enum(NpaBindingTarget)`` without ``name=`` or ``values_callable=``,
so SQLAlchemy would send the *member name* ("TEMPLATE_VERSION") on
INSERT. PG rejects with
``InvalidTextRepresentationError: invalid input value for enum
npabindingtarget: "TEMPLATE_VERSION"``. SQLite is tolerant; only PG
strict mode surfaces this.

NPABinding is not exercised by ``bootstrap_demo_tenant``, so this
column was deferred from Session 67/68 (RB-002c/d). iter-19 closes
proactively per cohort principle.
"""

from __future__ import annotations

from sqlalchemy import inspect

from app.models.models import NPABinding, NpaBindingTarget


def test_npabinding_entity_type_column_uses_enum_values_not_names() -> None:
    column = inspect(NPABinding).columns["entity_type"]
    enum_type = column.type

    assert list(enum_type.enums) == [member.value for member in NpaBindingTarget]
    assert list(enum_type.enums) == ["template_version", "document", "pack"]


def test_npabinding_target_python_member_names_diverge_from_values() -> None:
    # Precondition guard mirroring the rest of the cohort: if member.name
    # and member.value ever align, ``values_callable=`` silently becomes a
    # no-op. Keep this so a future refactor of the Python enum (e.g.
    # ``TEMPLATE_VERSION = "TEMPLATE_VERSION"``) has to consciously address
    # this pin.
    assert NpaBindingTarget.TEMPLATE_VERSION.name != NpaBindingTarget.TEMPLATE_VERSION.value
    assert NpaBindingTarget.TEMPLATE_VERSION.value == "template_version"
