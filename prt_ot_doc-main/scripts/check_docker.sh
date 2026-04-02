#!/usr/bin/env bash
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker CLI not found. Install Docker or run 'make dev:lite' for dockerless mode." >&2
  exit 1
fi

if ! output=$(docker ps 2>&1); then
  echo "Docker is not available: $output" >&2
  echo "If you're in Codespaces without Docker permissions, run 'make dev:lite'." >&2
  exit 1
fi
