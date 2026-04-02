from app.modules.audit.diff import field_diff, mask_pii


def test_field_diff_nested_payload_is_stable() -> None:
    before = {"status": "draft", "payload": {"email": "a@example.com", "v": [1, 2]}}
    after = {"status": "signed", "payload": {"email": "b@example.com", "v": [1, 2, 3]}}

    diff = field_diff(before, after)
    assert diff["fields"]["status"] == {"before": "draft", "after": "signed"}
    assert "payload" in diff["fields"]


def test_mask_pii_masks_email_phone_and_passport() -> None:
    payload = {
        "email": "user@example.com",
        "contact_phone": "+7...",
        "passport_number": "1234",
        "status": "ok",
    }
    masked = mask_pii(payload)
    assert masked["email"] == "***"
    assert masked["contact_phone"] == "***"
    assert masked["passport_number"] == "***"
    assert masked["status"] == "ok"
