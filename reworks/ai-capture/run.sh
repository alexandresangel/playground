#!/usr/bin/env bash
# Start the agent (uvicorn). Same entrypoint shape as the container.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

export PORT="${PORT:-7703}"
export HOST="${HOST:-0.0.0.0}"

exec "$PYTHON" -m uvicorn capture.asgi:app --host "$HOST" --port "$PORT" "$@"