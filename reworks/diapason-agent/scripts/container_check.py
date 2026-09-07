"""Run inside the built image with --network none, mounted read-only at /checks."""

import os
from pathlib import Path
from types import SimpleNamespace

import tiktoken
from fastapi.testclient import TestClient

from pascal.main import create_app

assert os.getuid() == 10001
assert Path("/app/static/js/vendor.bundle.js").is_file()
assert Path("/app/static/agent/agent-widget.js").is_file()
assert not Path("/app/config.json").exists()
assert not Path("/app/jwt_keystore.p12").exists()
tiktoken.get_encoding("cl100k_base")

# Explicit test doubles isolate composition/startup/static probes, not real dependencies.
app = create_app(
    config={"azure_openai": {}, "mcp": {}},
    root=Path("/app"),
    auth=object(),
    model=object(),
    transport=object(),
    store=SimpleNamespace(backend="container-fixture"),
    prompt_text="Fixture policy",
)
with TestClient(app) as client:
    for path in ("/health", "/ready", "/api/i18n", "/", "/static/js/chat-app.js"):
        assert client.get(path).status_code == 200, path
    assert client.get("/health").json()["version"] == os.environ["APP_VERSION"]
print("Non-root image: offline import, tokenizer, lifespan, probes and static assets passed.")
