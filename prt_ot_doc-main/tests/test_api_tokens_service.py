from app.services.api_tokens import ApiTokenService


def test_issue_token_hashes_raw_token() -> None:
    raw, model = ApiTokenService.issue_token(
        tenant_id="tenant-1",
        name="ci",
        scopes=["reports:read"],
        created_by_user_id="user-1",
        expires_at=None,
    )

    assert raw.startswith("ptd_")
    assert model.token_hash != raw
    assert ApiTokenService.verify_hash(raw, model.token_hash)


def test_verify_hash_rejects_other_token() -> None:
    raw, model = ApiTokenService.issue_token(
        tenant_id="tenant-1",
        name="ci",
        scopes=[],
        created_by_user_id=None,
        expires_at=None,
    )

    assert not ApiTokenService.verify_hash(raw + "x", model.token_hash)
