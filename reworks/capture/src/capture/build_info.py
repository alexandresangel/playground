"""Build identity exposed by the health endpoint."""

from __future__ import annotations

import json
from pathlib import Path

from capture import __version__


def health() -> dict[str, str]:
    path = Path("/app/build-info.json")
    if path.is_file():
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(body, dict):
                return {
                    "status": "ok",
                    "service": "capture",
                    "version": str(body.get("version") or __version__),
                    "revision": str(body.get("revision") or "unknown"),
                }
        except (OSError, json.JSONDecodeError):
            pass
    return {"status": "ok", "service": "capture", "version": __version__, "revision": "local"}
