from app.modules.approval.core import cond_matches, make_request_hash


def test_route_matching_counts_hits() -> None:
    assert cond_matches({"document_type": "invoice", "risk_level": "high"}, {"document_type": "invoice", "risk_level": "high"}) == 2


def test_route_matching_fails_on_mismatch() -> None:
    assert cond_matches({"document_type": "invoice"}, {"document_type": "act"}) == -1


def test_idempotency_hash_stable() -> None:
    first = make_request_hash("/v1/approvals:start", "t1", "u1", {"a": 1, "b": 2})
    second = make_request_hash("/v1/approvals:start", "t1", "u1", {"b": 2, "a": 1})
    assert first == second
