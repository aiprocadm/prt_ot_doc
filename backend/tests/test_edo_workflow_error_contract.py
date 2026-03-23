from fastapi import HTTPException, status
import pytest

from app.api.routes.edo_workflow import _validate_approval_rules


def test_validate_approval_rules_raises_structured_unprocessable_for_empty_steps() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _validate_approval_rules({"steps": []})

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert exc_info.value.detail == {
        "code": "edo_validation_error",
        "message": "steps must not be empty",
    }


def test_validate_approval_rules_returns_parsed_rules_for_valid_sequence() -> None:
    rules = _validate_approval_rules(
        {
            "steps": [
                {"order": 1, "role": "admin"},
                {"order": 2, "role": "employee"},
            ]
        }
    )

    assert [step.order for step in rules.steps] == [1, 2]
