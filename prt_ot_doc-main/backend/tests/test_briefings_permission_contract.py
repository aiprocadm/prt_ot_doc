from __future__ import annotations

from app.api.routes.briefings import (
    _BRIEFINGS_CREATE_PERMISSION,
    _BRIEFINGS_READ_PERMISSION,
    _BRIEFINGS_WRITE_PERMISSION,
)


def test_briefings_permission_constants_are_distinct_and_expected() -> None:
    assert _BRIEFINGS_READ_PERMISSION == "briefings.read"
    assert _BRIEFINGS_WRITE_PERMISSION == "briefings.update"
    assert _BRIEFINGS_CREATE_PERMISSION == "briefings.create"
    assert len({_BRIEFINGS_READ_PERMISSION, _BRIEFINGS_WRITE_PERMISSION, _BRIEFINGS_CREATE_PERMISSION}) == 3
