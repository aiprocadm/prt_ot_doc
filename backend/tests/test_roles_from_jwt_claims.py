"""Unit tests for roles_from_jwt_claims (JWT role claims normalization)."""

from __future__ import annotations

from app.core.security import roles_from_jwt_claims


def test_roles_list_and_single_merged_deduped() -> None:
    assert roles_from_jwt_claims({"roles": ["Admin", "viewer"], "role": "owner"}) == (
        "admin",
        "viewer",
        "owner",
    )


def test_duplicate_role_claim_removed() -> None:
    assert roles_from_jwt_claims({"roles": ["a"], "role": "a"}) == ("a",)


def test_roles_string_claim_ignored_not_char_split() -> None:
    assert roles_from_jwt_claims({"roles": "admin"}) == ()


def test_whitespace_only_role_ignored() -> None:
    assert roles_from_jwt_claims({"role": "   "}) == ()


def test_empty_mapping() -> None:
    assert roles_from_jwt_claims({}) == ()
