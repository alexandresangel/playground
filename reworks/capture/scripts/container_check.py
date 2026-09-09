"""Offline/non-root startup check with Capture disabled; not a live-dependency test."""

import os
from pathlib import Path

from fastapi.testclient import TestClient

from capture.main import create_app

assert os.getuid() == 10001
assert not Path("/app/config.json").exists()
assert not Path("/app/jwt_keystore.p12").exists()
assert Path("/app/config/catalog.json").is_file()
app = create_app(
    config={"capture": {"enabled": False}, "mcp": {"enabled": False}},
    security=object(),
)
with TestClient(app) as client:
    assert client.get("/health").json()["version"] == os.environ["APP_VERSION"]
    assert client.get("/ready").status_code == 200
    assert client.post("/mcp").status_code == 404
print("Non-root image: offline import, HTTP-only lifespan, probes and catalog assets passed.")
