"""ARCH-3 — bounded-context import boundaries must stay clean.

Mirrors ``make check-boundaries`` inside the pytest suite: a NEW cross-context
import between ``app.modules.*`` and the legacy ``app.domains.*`` fails here, and
a stale allowlist entry (import that no longer exists) fails too — keeping the
debt list honest. Pure-stdlib AST walk, so it runs anywhere (no app import, no PG).
"""

from __future__ import annotations

import importlib

checker = importlib.import_module("scripts.ci.check_context_boundaries")


def test_no_new_cross_context_imports() -> None:
    violations, _stale = checker.scan()
    assert not violations, (
        "New cross-context import(s) — route via services/ or a public API, "
        "or allowlist with a note in scripts/ci/check_context_boundaries.py:\n"
        + "\n".join(f"  {a} -> {b}" for a, b in violations)
    )


def test_allowlist_has_no_stale_entries() -> None:
    _violations, stale = checker.scan()
    assert not stale, (
        "Stale ALLOWLIST entries (import no longer exists — remove them):\n"
        + "\n".join(f"  {a} -> {b}" for a, b in stale)
    )


def test_allowlist_is_the_expected_legacy_set() -> None:
    # Freezes the known legacy leak count (POST-1 2026-07-02: 2 modules→living-domains
    # + 3 modules→domains.shared). This number should go DOWN, never up.
    assert len(checker.ALLOWLIST) == 5
