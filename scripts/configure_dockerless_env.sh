#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-.env}"

if [ ! -f "$ENV_FILE" ]; then
  cp .env.example "$ENV_FILE"
fi

python - "$ENV_FILE" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

env_path = Path(sys.argv[1])
lines = env_path.read_text(encoding="utf-8").splitlines()

updates = {
    "APP_RUN_MODE": "dockerless",
    "DATABASE_URL": "sqlite+aiosqlite:///./dev.db",
    "STORAGE_BACKEND": "local",
    "S3_BACKEND": "local",
    "STORAGE_ROOT": "./.local_storage",
    "CELERY_EAGER": "true",
    "REDIS_URL": "memory://",
    "REDIS_RESULT_URL": "memory://",
    "RATE_LIMIT_STORAGE_URI": "memory://",
    "ENABLE_METRICS": "false",
    "LIBREOFFICE_BIN": "python",
    "DEMO_BOOTSTRAP": "0",
}

updated = set()
new_lines = []
for line in lines:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in line:
        new_lines.append(line)
        continue
    key, _, _ = line.partition("=")
    if key in updates:
        new_lines.append(f"{key}={updates[key]}")
        updated.add(key)
    else:
        new_lines.append(line)

for key, value in updates.items():
    if key not in updated:
        new_lines.append(f"{key}={value}")

env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
PY
