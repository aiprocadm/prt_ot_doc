"""Pin test for ``Person.employment_status`` enum value casing (iter-17 RB-002c).

The PG enum ``employmentstatus`` was created with lowercase values
("active", "on_leave", "suspended", "terminated") in migration
``8d2c1a6c5e24_domain_normalization.py``. SQLAlchemy ``Enum(EmploymentStatus)``
defaults to sending the Python enum *member name* (uppercase) for INSERT,
which PG rejects with ``InvalidTextRepresentationError: invalid input
value for enum employmentstatus: "ACTIVE"``.

This pin asserts the column type's accepted-value list matches the
lowercase ``.value`` strings, which is what ``values_callable=`` forces.
"""

from __future__ import annotations

from sqlalchemy import inspect

from app.models.models import EmploymentStatus, Person


def test_employment_status_column_uses_enum_values_not_names() -> None:
    column = inspect(Person).columns["employment_status"]
    enum_type = column.type

    # SQLAlchemy ``Enum`` stores the accepted DB values in ``.enums``.
    # With ``values_callable=`` returning ``.value`` for each member, this
    # list must match the PG type's accepted lowercase strings.
    assert list(enum_type.enums) == [member.value for member in EmploymentStatus]
    assert list(enum_type.enums) == ["active", "on_leave", "suspended", "terminated"]


def test_employment_status_python_member_names_diverge_from_values() -> None:
    # Sanity check the precondition for this pin: if member.name and
    # member.value ever align, the values_callable workaround becomes a
    # no-op and someone might be tempted to remove it. Keep this assertion
    # so a future refactor of the Python enum (e.g. ``ACTIVE = "ACTIVE"``)
    # has to consciously address this pin.
    assert EmploymentStatus.ACTIVE.name != EmploymentStatus.ACTIVE.value
    assert EmploymentStatus.ACTIVE.value == "active"
