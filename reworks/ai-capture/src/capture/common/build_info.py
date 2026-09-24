"""Build identity stamped in the image; release set when promoting to production."""

from __future__ import annotations

import json
import os
from pathlib import Path

_BUILD_INFO = Path("/app/build-info.json")
_VERSION_FILE = Path(__file__).resolve().parent / "VERSION"


def load() -> dict[str, str]:
    version = "0.0.0"
    if _VERSION_FILE.is_file():
        version = _VERSION_FILE.read_text(encoding="utf-8").strip()
    if _BUILD_INFO.is_file():
        data = json.loads(_BUILD_INFO.read_text(encoding="utf-8"))
        return {
            "version": str(data.get("version") or version),
            "build_date": str(data.get("build_date") or data.get("date") or data.get("version") or ""),
            "revision": str(data.get("revision") or ""),
        }
    return {
        "version": os.environ.get("APP_VERSION", version),
        "build_date": os.environ.get("BUILD_DATE", ""),
        "revision": os.environ.get("APP_REVISION", os.environ.get("GIT_REVISION", "dev")),
    }


def health() -> dict[str, str]:
    info = load()
    return {"status": "ok", **info, "release": os.environ.get("RELEASE_TAG", "")}