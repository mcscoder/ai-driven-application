#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

export UV_CACHE_DIR="${UV_CACHE_DIR:-.uv-cache}"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required but was not found on PATH." >&2
  exit 1
fi

if [ ! -f ".env" ]; then
  echo "No .env found. Creating one from .env.example."
  cp .env.example .env
  echo "Edit .env with your Neo4j and cliproxy settings, then run this script again." >&2
  exit 1
fi

uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
