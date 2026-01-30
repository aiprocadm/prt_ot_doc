#!/usr/bin/env bash
set -euo pipefail

./scripts/configure_dockerless_env.sh .env

poetry config virtualenvs.in-project true
poetry install --with dev

cd frontend
npm install
