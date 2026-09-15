"""A small real-HTTP client usable against offline or connected Capture."""
import json
from pathlib import Path

import httpx

from tools.configuration import ROOT, load_offline, state_dir

API = "/api/skills/intelligence-contract"


def offline_headers(config=None):
    from dia_jwt import JwtAuth

    config = config if config is not None else load_offline()
    auth = JwtAuth(state_dir(config) / "jwt_keystore.p12", config["jwt"]["keystore_password"], issuer="diapason-agent")
    token = auth.mint(sub="instance:offline", roles=["chat", "refresh"], customer_id=7, ttl_seconds=3600)
    return {
        "Authorization": "Bearer " + token["access_token"],
        "X-Diapason-User-Id": "42", "X-Diapason-Customer-Id": "7",
        "X-Diapason-Mcp-Token": "offline-api-token", "X-Diapason-Mcp-Scope": "3",
        "X-Diapason-Mcp-Base-Url": "http://127.0.0.1:8011/unused-diapason",
        "X-Diapason-Locale": "en_US",
    }


def run(*, url, headers_file=None, pdf=None, trade_type="iamLoan", debug=False, session_id=None):
    headers = json.loads(Path(headers_file).read_text(encoding="utf-8")) if headers_file else offline_headers()
    with httpx.Client(base_url=url, headers=headers, timeout=240, trust_env=bool(headers_file)) as client:
        health = client.get("/health")
        health.raise_for_status()
        metadata = client.get(API)
        metadata.raise_for_status()
        print("Health:", health.json()["status"], "| trade types:", len(metadata.json()["trade_types"]))
        data = {"trade_type": trade_type, "debug": str(debug).lower()}
        if session_id:
            data["session_id"] = session_id
        path = Path(pdf) if pdf else ROOT / "tests/fixtures/sample-loan-contract.pdf"
        with path.open("rb") as document:
            response = client.post(API, data=data, files={"pdf": (path.name, document, "application/pdf")})
        print("HTTP:", response.status_code)
        print("Session:", response.headers.get("X-Diapason-Chat-Session", ""))
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
        response.raise_for_status()
        if not response.json().get("success"):
            raise SystemExit("Capture returned success=false")
