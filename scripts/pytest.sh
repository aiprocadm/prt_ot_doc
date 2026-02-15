#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -d ".venv" ]; then
  python -m venv .venv
fi

source .venv/bin/activate

REQ_STAMP=".venv/.requirements.stamp"
if [ ! -f "$REQ_STAMP" ] || [ requirements.txt -nt "$REQ_STAMP" ] || [ requirements-dev.txt -nt "$REQ_STAMP" ]; then
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt -r requirements-dev.txt
  touch "$REQ_STAMP"
fi

python -m pytest "$@"
