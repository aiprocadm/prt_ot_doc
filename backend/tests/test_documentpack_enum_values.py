"""Pin tests for ``DocumentPack.{module,scenario_type}`` enum value casing.

iter-17 RB-002d follow-up to RB-002c (``Person.employment_status``).

Migration ``8d2c1a6c5e24_domain_normalization.py:43-66`` creates **five**
PG enum types with lowercase values:

* ``employmentstatus``      (active, on_leave, suspended, terminated)
* ``documentpackmodule``    (ot, fire_safety, health, custom)
* ``documentpackscenario``  (document_batch, report, workflow)
* ``documentversionstatus`` (draft, locked, published, archived)
* ``npabindingtarget``      (template_version, document, pack)

SQLAlchemy ``Enum(SomeEnum)`` defaults to sending the Python enum
*member name* (uppercase) when binding INSERT params. PG rejects this
with ``InvalidTextRepresentationError: invalid input value for enum
<name>: "<NAME>"``.

RB-002c fixed ``Person.employment_status`` (the first symptom that
surfaced in CI). RB-002d preemptively fixes the next two columns that
the demo bootstrap path touches: ``DocumentPack.module`` and
``DocumentPack.scenario_type`` (both inserted by
``app.modules.packs.seeder._ensure_pack`` via every ``DEFAULT_PACKS``
entry).

The remaining two enums from the same migration (``documentversionstatus``,
``npabindingtarget``) are *not* exercised by ``bootstrap_demo_tenant`` —
they will be fixed when (and if) they surface in CI per the established
incremental cadence.
"""

from __future__ import annotations

from sqlalchemy import inspect

from app.models.models import DocumentPack, DocumentPackModule, DocumentPackScenario


def test_document_pack_module_column_uses_enum_values_not_names() -> None:
    column = inspect(DocumentPack).columns["module"]
    enum_type = column.type

    assert list(enum_type.enums) == [member.value for member in DocumentPackModule]
    assert list(enum_type.enums) == ["ot", "fire_safety", "health", "custom"]


def test_document_pack_scenario_column_uses_enum_values_not_names() -> None:
    column = inspect(DocumentPack).columns["scenario_type"]
    enum_type = column.type

    assert list(enum_type.enums) == [member.value for member in DocumentPackScenario]
    assert list(enum_type.enums) == ["document_batch", "report", "workflow"]


def test_document_pack_python_member_names_diverge_from_values() -> None:
    # Precondition guard mirroring test_employmentstatus_enum_values.py:
    # if member.name and member.value ever align, ``values_callable=``
    # silently becomes a no-op. Keep this so a future refactor of the
    # Python enum (e.g. ``OT = "OT"``) has to consciously address this
    # pin.
    assert DocumentPackModule.OT.name != DocumentPackModule.OT.value
    assert DocumentPackModule.OT.value == "ot"
    assert DocumentPackScenario.DOCUMENT_BATCH.name != DocumentPackScenario.DOCUMENT_BATCH.value
    assert DocumentPackScenario.DOCUMENT_BATCH.value == "document_batch"
