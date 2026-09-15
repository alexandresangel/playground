"""Configuration belongs to the dev launcher, never the production config loader."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def project_path(value: str) -> Path:
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("Development paths must stay inside the Capture project")
    return path


def load_offline(config_path: str | None = None) -> dict:
    path = project_path(config_path or os.getenv("CAPTURE_DEV_CONFIG", "tools/offline.json"))
    config = json.loads(path.read_text(encoding="utf-8"))
    # An explicitly offline launcher must not silently use company services.
    for url in (config["azure_openai"]["endpoint"], config["mcp"]["default"]["server_url"]):
        parsed = urlsplit(url)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.username or parsed.password:
            raise ValueError("Offline endpoints must use http://127.0.0.1")
    if set(config["mcp"]) != {"default"}:
        raise ValueError("Offline config supports only mcp.default")
    from azure.storage.blob import BlobServiceClient

    with BlobServiceClient.from_connection_string(config["storage"]["connection_string"]) as client:
        parsed = urlsplit(client.url)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1":
            raise ValueError("Offline Blob endpoint must use http://127.0.0.1")
        if client.account_name != config["storage"]["account_name"]:
            raise ValueError("Offline account name does not match the connection string")
    return config


def state_dir(config: dict) -> Path:
    return project_path(config["development"]["state_dir"])


def scenario(config: dict) -> dict:
    return json.loads(project_path(config["development"]["scenario_file"]).read_text(encoding="utf-8"))
