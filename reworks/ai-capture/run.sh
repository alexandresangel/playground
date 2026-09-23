#!/usr/bin/env bash
# Start Capture from any working directory after `uv sync --all-groups`.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ -z "${PYTHON:-}" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON="$ROOT/.venv/bin/python"
  elif [[ -x "$ROOT/.venv/Scripts/python.exe" ]]; then
    PYTHON="$ROOT/.venv/Scripts/python.exe"
  else
    PYTHON="$(command -v python3)"
  fi
fi

export PORT="${PORT:-8011}"
export HOST="${HOST:-0.0.0.0}"

exec "$PYTHON" -m uvicorn capture.asgi:app --host "$HOST" --port "$PORT" "$@"
