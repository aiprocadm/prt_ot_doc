from __future__ import annotations

from app.api.routes.tasks import _task_unprocessable


def test_task_unprocessable_has_structured_error_detail() -> None:
    exc = _task_unprocessable("unsupported task status")

    assert exc.status_code == 422
    assert exc.detail["code"] == "TASK_VALIDATION_ERROR"
    assert exc.detail["error_code"] == "TASK_VALIDATION_ERROR"
    assert exc.detail["message"] == "unsupported task status"
