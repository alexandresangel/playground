"""Container build identity; no mutable runtime build-info file."""

import os

from capture import __version__


def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "capture",
        "version": os.getenv("APP_VERSION", __version__),
        "revision": os.getenv("APP_REVISION", "local"),
    }
