#!/usr/bin/env python3
"""Fail CI if runtime/build artifacts are committed to git."""

from __future__ import annotations

import subprocess
import sys
from pathlib import PurePosixPath

BLOCKED_PATTERNS = (
    "dev.db",
    "runtime-dev.db",
    ".local_storage/**",
    ".vite/**",
    "frontend/dev-dist/**",
    "frontend/.npm-ci.stamp",
)


def _match(path: str, pattern: str) -> bool:
    posix_path = PurePosixPath(path)
    return posix_path.match(pattern) or path == pattern


def main() -> int:
    tracked = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    violations = sorted(
        path
        for path in tracked
        if any(_match(path, pattern) for pattern in BLOCKED_PATTERNS)
    )

    if not violations:
        print("Runtime/build artifact guard passed.")
        return 0

    print("Runtime/build artifact guard failed. Remove these tracked files:", file=sys.stderr)
    for path in violations:
        print(f" - {path}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
