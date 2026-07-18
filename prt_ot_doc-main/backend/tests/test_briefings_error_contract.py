from __future__ import annotations

from app.api.routes.briefings import _briefing_bad_request


def test_briefing_bad_request_has_structured_error_detail() -> None:
    exc = _briefing_bad_request("missing signatures")

    assert exc.status_code == 400
    assert exc.detail == {
        "code": "briefing_validation_error",
        "message": "missing signatures",
    }
