#!/usr/bin/env bash
# Lint, format check, and tests. Must pass before every merge.
set -euo pipefail
cd "$(dirname "$0")"
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pytest "$@"
