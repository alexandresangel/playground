"""Build version stamped at image build time."""

from __future__ import annotations

import json
import os
from importlib.metadata import version as package_version, PackageNotFoundError
from pathlib import Path

_BUILD_INFO = Path("/app/build-info.json")
_VERSION_FILE = Path(__file__).resolve().parent / "VERSION"


def load() -> dict[str, str]:
    if _BUILD_INFO.is_file():
        data = json.loads(_BUILD_INFO.read_text(encoding="utf-8"))
        return {"version": str(data["version"]), "revision": str(data["revision"])}

    version = "0.0.0"
    try:
        version = package_version("diapason-agent")
    except PackageNotFoundError:
        pass
    if _VERSION_FILE.is_file():
        version = _VERSION_FILE.read_text(encoding="utf-8").strip()
    return {
        "version": os.environ.get("APP_VERSION", version),
        "revision": os.environ.get("APP_REVISION", "dev"),
    }


def health() -> dict[str, str]:
    info = load()
    return {"status": "ok", "version": info["version"], "revision": info["revision"]}
