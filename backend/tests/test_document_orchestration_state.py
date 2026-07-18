from app.services.document_orchestration import normalize_user_facing_error, set_state


def test_orchestration_state_records_timeline_without_duplicates() -> None:
    orchestration = set_state(None, state="generated")
    orchestration = set_state(orchestration, state="generated")
    orchestration = set_state(orchestration, state="headers_applied")

    timeline = orchestration["timeline"]
    assert len(timeline) == 2
    assert timeline[0]["state"] == "generated"
    assert timeline[1]["state"] == "headers_applied"


def test_orchestration_error_mapping_is_user_facing() -> None:
    message = normalize_user_facing_error("Template version payload is missing")
    assert message is not None
    assert "DOCX" in message
