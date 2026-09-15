"""Prepare real Azurite blobs and a separate runtime directory; no patching."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import urlsplit

from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import BlobServiceClient

from tools.configuration import ROOT, project_path, state_dir


def blob_service(config):
    storage = config["storage"]
    return BlobServiceClient.from_connection_string(
        storage["connection_string"], api_version=storage["api_version"],
        connection_timeout=3, read_timeout=5, retry_total=0, use_env_settings=False,
    )


def sync_config(config):
    """Publish local catalog/prompts to the emulator, using the real Blob SDK."""
    source = project_path(config["development"]["config_dir"])
    with blob_service(config) as service:
        for name in (config["storage"]["chat_container"], config["storage"]["config_container"]):
            try:
                service.create_container(name)
            except ResourceExistsError:
                pass
        container = service.get_container_client(config["storage"]["config_container"])
        container.upload_blob(config["intelligence_contract"]["catalog_blob"], (source / "catalog.json").read_bytes(), overwrite=True)
        for prompt in (source / "prompts").glob("*.txt"):
            container.upload_blob(f"skills/intelligence-contract/prompts/{prompt.name}", prompt.read_bytes(), overwrite=True)


def initialize(config):
    from dia_jwt import JwtAuth

    folder = state_dir(config)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "jwt_keystore.p12"
    if not path.exists():
        JwtAuth.create_keystore(path, config["jwt"]["keystore_password"])
    else:
        JwtAuth(path, config["jwt"]["keystore_password"])
    shutil.copyfile(ROOT / "VERSION", folder / "VERSION")
    sync_config(config)


def offline_environment(config):
    """Return child-process environment. Never modify the caller's environment."""
    env = {k: v for k, v in os.environ.items()
           if k not in {"CHAT_CONFIG", "JWT_KEYSTORE_P12_B64"}
           and k.upper() not in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"}
           and not k.startswith(("OTEL_", "LANGSMITH_", "LANGCHAIN_"))}
    env["CHAT_CONFIG"] = json.dumps(config)
    env["NO_PROXY"] = "127.0.0.1,localhost"
    return env


def server_command(kind, port, *, reload=False):
    target = "capture.asgi:app" if kind == "serve" else "tools.stubs:create_app"
    command = [sys.executable, "-m", "uvicorn", target, "--host", "127.0.0.1", "--port", str(port), "--app-dir", str(ROOT)]
    if kind == "stubs":
        command.append("--factory")
    if reload:
        command.extend(["--reload", "--reload-dir", str(ROOT / ("src" if kind == "serve" else "tools"))])
    return command


def azurite_command(config):
    node = shutil.which("node")
    entry = ROOT / "tools/azurite/node_modules/azurite/dist/src/blob/main.js"
    if not node or not entry.is_file():
        raise RuntimeError("Install Node.js and run npm ci --prefix tools/azurite first")
    with blob_service(config) as client:
        port = urlsplit(client.url).port or 80
    return [node, str(entry), "--blobHost", "127.0.0.1", "--blobPort", str(port),
            "--location", str(state_dir(config) / "azurite"), "--disableTelemetry", "--silent"]


def run_process(command, *, cwd: Path, env: dict):
    process = subprocess.Popen(command, cwd=cwd, env=env)
    try:
        return process.wait()
    except KeyboardInterrupt:
        try:
            return process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            return process.wait(timeout=5)
