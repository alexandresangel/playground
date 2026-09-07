"""Explicit live dev smoke. Uses the legacy SMOKE_API_CONFIG keys; prints no payloads."""

import json
import os
import xml.etree.ElementTree as ET

import httpx


def settings():
    cfg = json.loads(os.environ["SMOKE_API_CONFIG"])
    cfg["agent_url"] = os.getenv("AGENT_URL") or cfg["agent_url"]
    return cfg


def headers(cfg, client):
    token = cfg.get("diapason_api_jwt_token")
    if not token:
        response = client.post(
            cfg["diapason_base_url"].rstrip("/") + "/api/login",
            data={
                "client_id": cfg["diapason_client_id"],
                "client_secret": cfg["diapason_client_secret"],
                "locale": "en_US",
            },
        )
        if response.status_code != 200:
            raise RuntimeError("Diapason login failed")
        document = ET.fromstring(response.text)
        token = document.attrib.get("apiToken") or document.attrib.get("token")
        if not token:
            raise RuntimeError("Diapason login returned no token")
    return {
        "Authorization": "Bearer " + cfg["agent_jwt_token"],
        "X-Diapason-User-Id": str(cfg["diapason_user_id"]),
        "X-Diapason-Customer-Id": str(cfg["diapason_customer_id"]),
        "X-Diapason-Mcp-Token": token,
        "X-Diapason-Mcp-Scope": str(cfg["diapason_scope"]),
        "X-Diapason-Mcp-Base-Url": cfg["diapason_base_url"],
    }


def check(response):
    if response.status_code != 200:
        raise RuntimeError(f"Smoke HTTP status {response.status_code}")
    return response.json()


def main():
    cfg = settings()
    base = cfg["agent_url"].rstrip("/")
    with httpx.Client(timeout=230, follow_redirects=False) as client:
        check(client.get(base + "/health"))
        check(client.get(base + "/ready"))
        auth = headers(cfg, client)
        listing = check(client.get(base + "/api/mcp/tools", headers=auth))
        if not listing["servers"] or not all(server["ok"] for server in listing["servers"]):
            raise RuntimeError("At least one configured MCP catalogue is unavailable")
        created = check(client.post(base + "/api/sessions", headers=auth))
        sid = created["session_id"]
        try:
            # Deterministic command verifies lifecycle/storage without unapproved tool mutations.
            answer = check(
                client.post(
                    base + "/api/chat", headers=auth, json={"session_id": sid, "message": "/help"}
                )
            )
            if not answer.get("persisted") or answer.get("status") != "completed":
                raise RuntimeError("Smoke turn did not persist")
            detail = check(client.get(base + "/api/sessions/" + sid, headers=auth))
            if len(detail["turns"]) != 2:
                raise RuntimeError("Smoke transcript mismatch")
            response = client.post(
                base + "/api/chat/stream",
                headers=auth,
                json={"session_id": sid, "message": "/help"},
            )
            if response.status_code != 200 or "data: [DONE]" not in response.text:
                raise RuntimeError("Smoke SSE failed")
        finally:
            # Only archive the session created by this smoke invocation.
            check(client.delete(base + "/api/sessions/" + sid, headers=auth))
    print("Health, scoped MCP catalogue, session, JSON and SSE smoke passed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit(
            f"Smoke failed ({type(exc).__name__}); inspect correlated server telemetry."
        ) from None
