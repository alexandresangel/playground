"""Process-level checks: production ASGI app, real Blob SDK/Azurite, HTTP fixtures.

No monkey-patching, dependency overrides, or private cache manipulation.
"""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
from types import SimpleNamespace

import httpx
import pytest
from azure.core import MatchConditions
from azure.core.exceptions import ResourceModifiedError

from tools.bootstrap import azurite_command, blob_service, initialize, offline_environment, server_command, sync_config
from tools.configuration import ROOT, load_offline
from tools.smoke import API, offline_headers
from dia_jwt import JwtAuth

pytestmark = pytest.mark.integration


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_ready(process, check, log_path):
    deadline = time.monotonic() + 30
    last_error = None
    while time.monotonic() < deadline and process.poll() is None:
        try:
            check()
            return
        except Exception as exc:
            last_error = exc
            time.sleep(0.1)
    pytest.fail(f"Local service did not become ready: {last_error}\n{log_path.read_text(errors='replace')[-4000:]}")


@pytest.fixture(scope="module")
def local_stack():
    (ROOT / ".local").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="integration-", dir=ROOT / ".local") as temporary:
        folder = Path(temporary)
        config = json.loads((ROOT / "tools/offline.json").read_text())
        ports = [free_port() for _ in range(3)]
        assert len(set(ports)) == 3
        config["storage"]["connection_string"] = config["storage"]["connection_string"].replace(":10000/", f":{ports[0]}/")
        config["azure_openai"]["endpoint"] = f"http://127.0.0.1:{ports[1]}"
        config["mcp"]["default"]["server_url"] = f"http://127.0.0.1:{ports[1]}/mcp"
        shutil.copytree(ROOT / "config", folder / "config")
        scenario_path = folder / "scenario.json"
        scenario_path.write_text((ROOT / "tools/scenario.json").read_text(), encoding="utf-8")
        config["development"] = {"state_dir": str(folder / "state"), "config_dir": str(folder / "config"), "scenario_file": str(scenario_path)}
        config_path = folder / "offline.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        config = load_offline(str(config_path))
        env = offline_environment(config)
        env["CAPTURE_DEV_CONFIG"] = str(config_path)
        processes, logs = [], []

        def start(command, cwd, name):
            log_path = folder / f"{name}.log"
            stream = log_path.open("w", encoding="utf-8")
            logs.append(stream)
            process = subprocess.Popen(command, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT)
            processes.append(process)
            return process, log_path

        def check_blob():
            with blob_service(config) as service:
                service.get_service_properties()

        def check_http(url):
            with httpx.Client(trust_env=False, timeout=1) as client:
                client.get(url + "/health").raise_for_status()

        try:
            storage, storage_log = start(azurite_command(config), ROOT, "azurite")
            wait_ready(storage, check_blob, storage_log)
            initialize(config)
            stubs, stub_log = start(server_command("stubs", ports[1]), ROOT, "stubs")
            wait_ready(stubs, lambda: check_http(config["azure_openai"]["endpoint"]), stub_log)
            app, app_log = start(server_command("serve", ports[2]), folder / "state", "capture")
            url = f"http://127.0.0.1:{ports[2]}"
            wait_ready(app, lambda: check_http(url), app_log)
            with httpx.Client(base_url=url, trust_env=False, timeout=30) as client:
                yield SimpleNamespace(client=client, config=config, config_path=config_path, folder=folder,
                                      scenario=scenario_path, start=start, app=app, url=url, port=ports[2])
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
            for stream in logs:
                stream.close()


@pytest.fixture
def local(local_stack):
    local_stack.scenario.write_text((ROOT / "tools/scenario.json").read_text(), encoding="utf-8")
    local_stack.headers = offline_headers(local_stack.config)
    return local_stack


def upload(local, **data):
    return local.client.post(API, headers=local.headers, data={"trade_type": "iamLoan", **data},
        files={"pdf": ("loan.pdf", (ROOT / "tests/fixtures/sample-loan-contract.pdf").read_bytes(), "application/pdf")})


def session_record(local, sid):
    with blob_service(local.config) as service:
        return json.loads(service.get_blob_client("chat-sessions", f"offline/7/42/{sid}.json").download_blob().readall())


def change_scenario(local, section, **values):
    data = json.loads(local.scenario.read_text())
    data[section].update(values)
    local.scenario.write_text(json.dumps(data), encoding="utf-8")


def test_production_asgi_graph_real_http_and_blob_sessions(local):
    response = upload(local, debug="true")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["success"] and result["extracted_field_count"] == 9
    assert '<tradeType shortname="iamLoan">763</tradeType>' in result["trade_xml"]
    assert [entry["tool"] for entry in result["tool_trace"]] == ["extract_xml", "resolveReferences"]
    assert "session_artifacts" not in result
    sid = response.headers["X-Diapason-Chat-Session"]
    record = session_record(local, sid)
    assert record["scope"] == "offline/7/42" and len(record["turns"]) == 2
    artifacts = record["turns"][1]["skill_run"]["artifacts"]
    assert artifacts["resolved_trade_xml"] == result["trade_xml"]
    assert '<tradeType shortname="iamLoan" />' in artifacts["source_trade_xml"]
    request = json.loads((local.folder / "state/requests/llm.json").read_text())
    assert request["messages"][0]["content"] == (ROOT / "config/prompts/mltLoan.txt").read_bytes().decode("utf-8")
    assert result["debug"]["extract"]["pdf_text_preview"] in request["messages"][1]["content"]
    assert upload(local, session_id=sid).status_code == 200
    assert len(session_record(local, sid)["turns"]) == 4
    changed_headers = {**local.headers, "X-Diapason-User-Id": "99"}
    response = local.client.post(API, headers=changed_headers, data={"trade_type": "iamLoan", "session_id": sid}, files={"pdf": ("loan.pdf", b"%PDF-no-read")})
    assert response.status_code == 404


def test_auth_catalog_refresh_and_revocation(local):
    assert local.client.get(API, headers={"Authorization": "Bearer bad"}).status_code == 401
    catalog_path = local.folder / "config/catalog.json"
    catalog = json.loads(catalog_path.read_text())
    catalog["version"] = "edited-emulator"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    sync_config(local.config)
    assert local.client.post("/api/refresh-prompt", headers=local.headers).status_code == 200
    assert local.client.get(API, headers=local.headers).json()["prompt_version"] == "edited-emulator"
    auth = JwtAuth(local.folder / "state/jwt_keystore.p12", local.config["jwt"]["keystore_password"])
    token = auth.mint(sub="instance:offline", roles=["admin"])
    claims = auth.validate(local.headers["Authorization"].removeprefix("Bearer "))
    response = local.client.post("/api/auth/revoke", json={"jti": claims["jti"]}, headers={"Authorization": "Bearer " + token["access_token"]})
    assert response.status_code == 200
    assert local.client.get(API, headers=local.headers).status_code == 401


@pytest.mark.parametrize("section,values,status", [
    ("llm", {"content": "not XML"}, 400),
    ("llm", {"content": ""}, 502),
    ("llm", {"http_status": 401}, 500),
    ("mcp", {"is_error": True}, 502),
    ("mcp", {"http_status": 503}, 502),
])
def test_configurable_dependency_failures(local, section, values, status):
    change_scenario(local, section, **values)
    response = upload(local)
    assert response.status_code == status, response.text


def test_business_failure_and_scenario_reload(local):
    change_scenario(local, "mcp", response={"success": False, "trade_xml": "", "message": "Unknown entity", "warnings": ["Manual review"]})
    response = upload(local)
    assert response.status_code == 200 and response.json()["success"] is False
    assert response.json()["warnings"] == ["Manual review"]
    assert session_record(local, response.headers["X-Diapason-Chat-Session"])["turns"][1]["skill_run"]["success"] is False
    change_scenario(local, "mcp", response={"success": True})
    assert upload(local).json()["success"] is True


def test_blob_etags_use_real_sdk_and_emulator(local):
    with blob_service(local.config) as service:
        blob = service.get_blob_client("chat-sessions", "integration/etag.txt")
        blob.upload_blob(b"first", overwrite=True)
        etag = blob.get_blob_properties().etag
        blob.upload_blob(b"second", overwrite=True, etag=etag, match_condition=MatchConditions.IfNotModified)
        with pytest.raises(ResourceModifiedError):
            blob.upload_blob(b"stale", overwrite=True, etag=etag, match_condition=MatchConditions.IfNotModified)
        blob.delete_blob()


def test_capture_restart_preserves_session_and_key(local):
    response = upload(local)
    sid = response.headers["X-Diapason-Chat-Session"]
    key = (local.folder / "state/jwt_keystore.p12").read_bytes()
    local.app.terminate()
    local.app.wait(timeout=10)
    initialize(local.config)
    assert (local.folder / "state/jwt_keystore.p12").read_bytes() == key
    local.app, log = local.start(server_command("serve", local.port), local.folder / "state", "capture-restart")
    wait_ready(local.app, lambda: local.client.get("/health").raise_for_status(), log)
    assert upload(local, session_id=sid).status_code == 200
    assert len(session_record(local, sid)["turns"]) == 4


def test_emulator_guards_and_no_parent_environment_mutation(local):
    original = dict(os.environ)
    env = offline_environment(local.config)
    assert dict(os.environ) == original
    assert json.loads(env["CHAT_CONFIG"])["storage"]["account_name"] == "devstoreaccount1"
    path = local.folder / "invalid.json"
    config = json.loads(local.config_path.read_text())
    config["storage"]["connection_string"] = config["storage"]["connection_string"].replace("127.0.0.1", "company.example")
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="127.0.0.1"):
        load_offline(str(path))
