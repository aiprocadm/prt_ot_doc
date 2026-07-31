#!/usr/bin/env python3
"""Blocking npm-audit gate: fail on non-excepted high/critical advisories.

npm audit has no ignore mechanism at all (no ignore file, no CLI flag), so
``npm audit --audit-level=high`` cannot be made blocking directly: a single
accepted dev-tooling finding would paint CI red forever. This gate reproduces
the pip-audit approach (render_pip_audit_ignores.py) for the npm world:

1. Parse ``npm audit --json`` output.
2. Collect ROOT advisories (GHSA ids) of severity >= high. npm inflates one
   root advisory into many "vulnerable" packages by propagating it up the
   dependency chain (one minimatch ReDoS marks eslint, glob, rimraf, ... as
   high); gating on root ids keeps the exception list honest and short.
3. Subtract ``tool: npm-audit`` records from .github/security-exceptions.yml.
   Expiry is enforced by check_security_exceptions.py earlier in the workflow.
4. Any remaining advisory fails the build.

Usage:
    npm --prefix frontend audit --json > npm-audit.json || true
    python scripts/ci/check_npm_audit.py --audit-json npm-audit.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

_GATED_SEVERITIES = {"high", "critical"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-json", required=True, help="File with `npm audit --json` output.")
    parser.add_argument("--exceptions-file", default=".github/security-exceptions.yml")
    return parser.parse_args()


def load_root_advisories(audit_path: Path) -> dict[str, dict]:
    payload = json.loads(audit_path.read_text(encoding="utf-8"))
    if "error" in payload:
        raise SystemExit(f"ERROR: npm audit itself failed: {payload['error']}")

    advisories: dict[str, dict] = {}
    for package in payload.get("vulnerabilities", {}).values():
        # ``via`` mixes strings (package names the finding propagated through)
        # and dicts (the root advisories themselves) — only dicts carry ids.
        for via in package.get("via", []):
            if not isinstance(via, dict):
                continue
            if via.get("severity") not in _GATED_SEVERITIES:
                continue
            advisory_id = str(via.get("url", "")).rsplit("/", 1)[-1] or f"unknown:{via.get('name')}"
            advisories[advisory_id] = via
    return advisories


def load_excepted_ids(exceptions_path: Path) -> set[str]:
    payload = yaml.safe_load(exceptions_path.read_text(encoding="utf-8")) or {}
    return {
        str(item.get("id", "")).strip()
        for item in payload.get("exceptions", [])
        if isinstance(item, dict) and item.get("tool") == "npm-audit"
    }


def main() -> int:
    args = parse_args()
    advisories = load_root_advisories(Path(args.audit_json))
    excepted = load_excepted_ids(Path(args.exceptions_file))

    blocking = {aid: adv for aid, adv in advisories.items() if aid not in excepted}
    accepted = sorted(set(advisories) & excepted)
    stale = sorted(excepted - set(advisories))

    print(
        f"npm-audit gate: {len(advisories)} high/critical root advisories, "
        f"{len(accepted)} accepted via security-exceptions.yml"
    )
    # A stale exception means the advisory no longer fires (dependency was
    # bumped) — not an error, but worth surfacing so records get cleaned up.
    for aid in stale:
        print(f"  stale exception (advisory no longer reported): {aid}")

    if blocking:
        print("", file=sys.stderr)
        for aid, adv in sorted(blocking.items()):
            print(
                f"BLOCKING: {aid} [{adv.get('severity')}] {adv.get('name')}: "
                f"{adv.get('title')} ({adv.get('url')})",
                file=sys.stderr,
            )
        print(
            "\nFix the dependency or add a reviewed `tool: npm-audit` record with "
            "an expiry to .github/security-exceptions.yml (see docs/security/DEPENDENCY_AUDIT.md).",
            file=sys.stderr,
        )
        return 1

    print("npm-audit gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
