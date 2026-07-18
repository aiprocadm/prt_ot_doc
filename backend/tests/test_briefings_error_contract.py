from __future__ import annotations

from app.api.routes.briefings import _briefing_bad_request


def test_briefing_bad_request_has_structured_error_detail() -> None:
    exc = _briefing_bad_request("missing signatures")

    assert exc.status_code == 400
    assert exc.detail["code"] == "BRIEFING_VALIDATION_ERROR"
    assert exc.detail["error_code"] == "BRIEFING_VALIDATION_ERROR"
    assert exc.detail["message"] == "missing signatures"
