#!/usr/bin/env bash
set -euo pipefail

export APP_RUN_MODE="dockerless"
export DATABASE_URL="sqlite+aiosqlite:///./dev.db"
export STORAGE_BACKEND="local"
export S3_BACKEND="local"
export STORAGE_ROOT="./.local_storage"
export CELERY_EAGER="true"
export REDIS_URL="memory://"
export REDIS_RESULT_URL="memory://"
export RATE_LIMIT_STORAGE_URI="memory://"
export ENABLE_METRICS="false"
export LIBREOFFICE_BIN="${LIBREOFFICE_BIN:-python}"
export DEMO_BOOTSTRAP="0"
