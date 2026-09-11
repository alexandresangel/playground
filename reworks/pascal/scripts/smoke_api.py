#!/usr/bin/env python3
"""
Integration checks against a running Diapason Agent (chat) API.

Two JWTs:
  - agent_jwt_token       → Authorization Bearer (access agent API)
  - diapason_api_jwt_token → X-Diapason-Mcp-Token (Tomcat/test; agent encrypts for MCP)
  - diapason_scope → X-Diapason-Mcp-Scope
  - diapason_base_url → X-Diapason-Mcp-Base-Url
  - diapason_user_id / diapason_customer_id → X-Diapason-User-Id / Customer-Id

Optional intelligence contract (IC):
  - trade_type, intelligence_contract_pdf
  - intelligence_contract_debug (optional)

Config: test.api.json, path arg, or env SMOKE_API_CONFIG (JSON).
Deploy sets AGENT_URL (overrides agent_url). MCP URL is in agent CHAT_CONFIG.

Diapason API auth (pick one):
  - diapason_api_jwt_token — static JWT (expires), or
  - diapason_client_id + diapason_client_secret — smoke calls POST {base}/api/login

  python test/test_agent_smoke.py
  python test/test_agent_smoke.py path/to/other.api.json
  SMOKE_API_CONFIG='{…}' AGENT_URL=https://… python test/test_agent_smoke.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict

import httpx

CONFIG_NAME = "test.api.json"
_config_path: Path = Path(__file__).with_name(CONFIG_NAME)
_ENV_SMOKE_CONFIG = "SMOKE_API_CONFIG"
DIAPASON_API_JWT_HEADER = "X-Diapason-Mcp-Token"
DIAPASON_SCOPE_HEADER = "X-Diapason-Mcp-Scope"
DIAPASON_BASE_URL_HEADER = "X-Diapason-Mcp-Base-Url"
TIMEOUT_S = 60.0
IC_TIMEOUT_S = 600.0


def _load_config(config_path: Path | None = None) -> Dict[str, Any]:
    global _config_path
    env_raw = (os.environ.get(_ENV_SMOKE_CONFIG) or "").strip()
    if env_raw:
        _config_path = Path(f"<env:{_ENV_SMOKE_CONFIG}>")
        try:
            data = json.loads(env_raw)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid JSON in {_ENV_SMOKE_CONFIG}: {exc}") from exc
    else:
        _config_path = config_path or Path(__file__).with_name(CONFIG_NAME)
        if not _config_path.is_file():
            raise SystemExit(
                f"Missing {_config_path} (or set {_ENV_SMOKE_CONFIG}). "
                "Copy test.api.example.json and set agent_url + agent_jwt_token."
            )
        data = json.loads(_config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("smoke config must be a JSON object.")
    # Deploy overrides agent_url to the just-deployed ACA URL.
    agent_url = (os.environ.get("AGENT_URL") or "").strip()
    if agent_url:
        data["agent_url"] = agent_url.rstrip("/")
    return data


def _require_str(cfg: Dict[str, Any], key: str) -> str:
    val = str(cfg.get(key, "") or "").strip()
    if not val:
        raise SystemExit(f"{_config_path.name}: missing or empty '{key}'.")
    return val


def _base_url(cfg: Dict[str, Any]) -> str:
    return _require_str(cfg, "agent_url").rstrip("/")


def _ensure_diapason_api_token(cfg: Dict[str, Any], client: httpx.Client) -> None:
    """Fill cfg['diapason_api_jwt_token'] via /login when credentials are set."""
    existing = str(cfg.get("diapason_api_jwt_token", "") or "").strip()
    client_id = str(cfg.get("diapason_client_id", "") or "").strip()
    client_secret = str(cfg.get("diapason_client_secret", "") or "").strip()
    if existing and not (client_id and client_secret):
        return
    if not (client_id and client_secret):
        if existing:
            return
        raise SystemExit(
            f"{_config_path.name}: set diapason_api_jwt_token, or "
            "diapason_client_id + diapason_client_secret (smoke will POST /api/login)"
        )

    base = _require_str(cfg, "diapason_base_url").rstrip("/")
    login_url = f"{base}/api/login"
    print(f"→ POST {login_url} (client_id={client_id!r})", flush=True)
    r = client.post(
        login_url,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "locale": "en_US",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=TIMEOUT_S,
    )
    if r.status_code != 200:
        raise SystemExit(f"Diapason /login: HTTP {r.status_code}\n{r.text[:500]}")
    try:
        root = ET.fromstring(r.text)
    except ET.ParseError as exc:
        raise SystemExit(f"Diapason /login: invalid XML: {exc}\n{r.text[:500]}") from exc
    token = (root.attrib.get("apiToken") or root.attrib.get("token") or "").strip()
    if not token:
        raise SystemExit(f"Diapason /login: no apiToken in response\n{r.text[:500]}")
    cfg["diapason_api_jwt_token"] = token
    print("OK  Diapason /login (apiToken for MCP)", flush=True)


def _int_field(cfg: Dict[str, Any], key: str) -> int:
    try:
        return int(cfg[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"{_config_path.name}: '{key}' must be an integer.") from exc


def _auth_headers(
    cfg: Dict[str, Any], *, diapason_api_jwt_token: str = "", diapason_scope: int | None = None
) -> Dict[str, str]:
    headers = {
        "Authorization": f"Bearer {_require_str(cfg, 'agent_jwt_token')}",
        "X-Diapason-User-Id": str(_int_field(cfg, "diapason_user_id")),
        "X-Diapason-Customer-Id": str(_int_field(cfg, "diapason_customer_id")),
        "Accept": "application/json",
    }
    if diapason_api_jwt_token:
        headers[DIAPASON_API_JWT_HEADER] = diapason_api_jwt_token
        scope = diapason_scope if diapason_scope is not None else _int_field(cfg, "diapason_scope")
        headers[DIAPASON_SCOPE_HEADER] = str(scope)
        headers[DIAPASON_BASE_URL_HEADER] = _require_str(cfg, "diapason_base_url").rstrip("/")
    return headers


def _truncate(text: str, max_len: int = 72) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _print_mcp_tools_report(data: Dict[str, Any]) -> None:
    servers = data.get("servers") or []
    flat = data.get("tools") or []
    ok_count = sum(1 for s in servers if isinstance(s, dict) and s.get("ok"))
    print(
        "OK  GET /api/mcp/tools",
        f"servers={len(servers)}",
        f"ok={ok_count}",
        f"tools={len(flat)}",
    )
    for entry in servers:
        if not isinstance(entry, dict):
            continue
        server_id = str(entry.get("server_id", "") or "?")
        label = str(entry.get("label", "") or server_id)
        url = str(entry.get("server_url", "") or "")
        if entry.get("ok"):
            server_tools = entry.get("tools") or []
            print(f"\n  [{server_id}] {label}")
            if url:
                print(f"      {url}")
            print(f"      {len(server_tools)} tool(s):")
            for tool in server_tools:
                if not isinstance(tool, dict):
                    continue
                name = str(tool.get("name", "") or "").strip()
                native = str(tool.get("native_name", "") or "").strip()
                desc = _truncate(str(tool.get("description", "") or ""))
                if native and native != name:
                    print(f"        • {name}  (native: {native})")
                else:
                    print(f"        • {name}")
                if desc:
                    print(f"          {desc}")
        else:
            err = str(entry.get("error", "") or "unknown error")
            print(f"\n  [{server_id}] {label} — FAILED")
            if url:
                print(f"      {url}")
            print(f"      error: {err}")
    print()


def _chat_version_from_source() -> str:
    path = Path(__file__).resolve().parents[1] / "VERSION"
    if not path.is_file():
        raise SystemExit("VERSION not found in repo root")
    return path.read_text(encoding="utf-8").strip()


def _check(name: str, response: httpx.Response, expected: int = 200) -> Dict[str, Any]:
    if response.status_code != expected:
        body = response.text[:500]
        raise SystemExit(f"{name}: HTTP {response.status_code} (expected {expected})\n{body}")
    try:
        return response.json()
    except json.JSONDecodeError:
        return {"raw": response.text}


def test_health(client: httpx.Client, cfg: Dict[str, Any]) -> None:
    expected_version = _chat_version_from_source()
    r = client.get(f"{_base_url(cfg)}/api/health", headers=_auth_headers(cfg))
    data = _check("GET /api/health", r)
    assert data.get("status") == "ok", data
    cv = data.get("chat_version")
    if cv != expected_version:
        raise SystemExit(
            f"GET /api/health: chat_version {cv!r} != VERSION file "
            f"({expected_version!r}); redeploy agent if testing a remote URL"
        )
    print(
        "OK  GET /api/health",
        f"sessions_backend={data.get('sessions_backend')}",
        f"chat_version={cv!r}",
    )


def test_mcp_tools(client: httpx.Client, cfg: Dict[str, Any]) -> None:
    headers = _auth_headers(
        cfg, diapason_api_jwt_token=_require_str(cfg, "diapason_api_jwt_token")
    )
    r = client.get(f"{_base_url(cfg)}/api/mcp/tools", headers=headers, timeout=TIMEOUT_S)
    data = _check("GET /api/mcp/tools", r)
    servers = data.get("servers")
    tools = data.get("tools")
    if not isinstance(servers, list):
        raise SystemExit("GET /api/mcp/tools: missing or invalid 'servers' array")
    if not isinstance(tools, list):
        raise SystemExit("GET /api/mcp/tools: missing or invalid 'tools' array")
    if not servers:
        raise SystemExit("GET /api/mcp/tools: expected at least one MCP server entry")

    ok_count = 0
    flat_from_servers = 0
    default_entry: Dict[str, Any] | None = None
    for entry in servers:
        if not isinstance(entry, dict):
            raise SystemExit("GET /api/mcp/tools: server entry must be an object")
        for key in ("server_id", "label", "server_url", "ok"):
            if key not in entry:
                raise SystemExit(f"GET /api/mcp/tools: server missing {key!r}")
        if str(entry.get("server_id", "") or "") == "default":
            default_entry = entry
        if entry.get("ok"):
            ok_count += 1
            server_tools = entry.get("tools")
            if not isinstance(server_tools, list):
                raise SystemExit("GET /api/mcp/tools: server.tools must be an array when ok=true")
            flat_from_servers += len(server_tools)
            for tool in server_tools:
                if not isinstance(tool, dict):
                    raise SystemExit("GET /api/mcp/tools: tool entry must be an object")
                for key in ("name", "native_name", "mcp_server", "mcp_label"):
                    if not str(tool.get(key, "") or "").strip():
                        raise SystemExit(f"GET /api/mcp/tools: tool missing {key!r}")

    if ok_count == 0:
        errors = [
            f"{e.get('server_id')}: {e.get('error')}"
            for e in servers
            if isinstance(e, dict) and e.get("error")
        ]
        raise SystemExit(
            "GET /api/mcp/tools: no MCP server returned tools "
            f"(errors: {'; '.join(errors) or 'unknown'})"
        )
    if len(tools) != flat_from_servers:
        raise SystemExit(
            f"GET /api/mcp/tools: flat tools length {len(tools)} "
            f"!= sum of server tools {flat_from_servers}"
        )
    if default_entry is None:
        raise SystemExit("GET /api/mcp/tools: missing required 'default' MCP server entry")
    if not default_entry.get("ok"):
        err = str(default_entry.get("error", "") or "unknown error")
        raise SystemExit(f"GET /api/mcp/tools: default MCP server unavailable ({err})")
    default_tools = default_entry.get("tools")
    if not isinstance(default_tools, list) or not default_tools:
        raise SystemExit("GET /api/mcp/tools: default MCP server returned no tools")
    _print_mcp_tools_report(data)


def test_sessions(client: httpx.Client, cfg: Dict[str, Any]) -> str:
    headers = _auth_headers(
        cfg, diapason_api_jwt_token=_require_str(cfg, "diapason_api_jwt_token")
    )
    r = client.get(f"{_base_url(cfg)}/api/sessions", headers=headers)
    _check("GET /api/sessions", r)
    print("OK  GET /api/sessions")

    r = client.post(f"{_base_url(cfg)}/api/sessions", headers=headers)
    created = _check("POST /api/sessions", r)
    session_id = str(created.get("session_id", "")).strip()
    if not session_id:
        raise SystemExit("POST /api/sessions: missing session_id")
    print("OK  POST /api/sessions", f"session_id={session_id}")

    r = client.get(f"{_base_url(cfg)}/api/sessions/{session_id}", headers=headers)
    _check(f"GET /api/sessions/{session_id}", r)
    print(f"OK  GET /api/sessions/{session_id}")
    return session_id


def test_delete_session(client: httpx.Client, cfg: Dict[str, Any], session_id: str) -> None:
    headers = _auth_headers(
        cfg, diapason_api_jwt_token=_require_str(cfg, "diapason_api_jwt_token")
    )
    r = client.delete(f"{_base_url(cfg)}/api/sessions/{session_id}", headers=headers)
    _check(f"DELETE /api/sessions/{session_id}", r)
    print(f"OK  DELETE /api/sessions/{session_id}")

    r = client.get(f"{_base_url(cfg)}/api/sessions/{session_id}", headers=headers)
    if r.status_code != 404:
        raise SystemExit(
            f"GET /api/sessions/{session_id} after delete: expected 404, got {r.status_code}"
        )
    print(f"OK  GET /api/sessions/{session_id} -> 404 after delete")


def test_chat(client: httpx.Client, cfg: Dict[str, Any], session_id: str) -> None:
    headers = {
        **_auth_headers(
            cfg, diapason_api_jwt_token=_require_str(cfg, "diapason_api_jwt_token")
        ),
        "Content-Type": "application/json",
    }
    body = {
        "message": "Reply with one short sentence only.",
        "session_id": session_id,
        "client_timezone": "UTC",
    }
    r = client.post(f"{_base_url(cfg)}/api/chat", headers=headers, json=body, timeout=TIMEOUT_S)
    data = _check("POST /api/chat", r)
    answer = str(data.get("answer_markdown", "") or "").strip()
    if not answer:
        raise SystemExit("POST /api/chat: empty answer_markdown")
    print("OK  POST /api/chat", f"mode={data.get('mode')}", f"answer={answer[:120]!r}...")


def _trade_type_markers(trade_type: str) -> tuple[str, ...]:
    return (
        f'shortname="{trade_type}"',
        f"shortname='{trade_type}'",
        f">{trade_type}<",
    )


def _xml_has_trade_type(trade_xml: str, trade_type: str) -> bool:
    return any(m in trade_xml for m in _trade_type_markers(trade_type))


def _ic_source_trade_xml(data: Dict[str, Any]) -> str:
    debug = data.get("debug")
    if isinstance(debug, dict):
        extract = debug.get("extract") or {}
        if isinstance(extract, dict):
            source = str(extract.get("trade_xml") or "").strip()
            if source:
                return source
        req = debug.get("resolve_references_request") or {}
        if isinstance(req, dict):
            source = str(req.get("trade_xml") or "").strip()
            if source:
                return source
    return ""


def _print_ic_debug(data: Dict[str, Any]) -> None:
    debug = data.get("debug")
    if not isinstance(debug, dict):
        return
    print("\n--- debug ---")
    extract = debug.get("extract") or {}
    if extract.get("llm_response"):
        print("\n[llm_response]")
        print(extract["llm_response"])
    if extract.get("trade_xml_raw"):
        print("\n[xml_from_llm]")
        print(extract["trade_xml_raw"])
    if extract.get("trade_xml"):
        print("\n[xml_with_trade_type_injected]")
        print(extract["trade_xml"])
    resolve = debug.get("resolve_references")
    if resolve is not None:
        print("\n[resolve_references_result]")
        print(json.dumps(resolve, indent=2, ensure_ascii=False))
    req = debug.get("resolve_references_request") or {}
    if req.get("trade_xml"):
        print("\n[xml_sent_to_resolve]")
        print(req["trade_xml"])


def _ic_pdf_path(cfg: Dict[str, Any]) -> Path | None:
    raw = str(cfg.get("intelligence_contract_pdf", "") or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if path.is_file():
        return path
    # Relative to repo root (works in Actions checkout).
    root = Path(__file__).resolve().parent.parent
    cand = (root / raw).resolve()
    if cand.is_file():
        return cand
    # Relative to test/.
    cand = (Path(__file__).resolve().parent / raw).resolve()
    return cand if cand.is_file() else None


def test_intelligence_contract_metadata(
    client: httpx.Client, cfg: Dict[str, Any]
) -> Dict[str, Any] | None:
    """GET /api/skills/intelligence-contract — IC skill metadata (trade types, prompt version)."""
    base = _base_url(cfg)
    headers = _auth_headers(cfg)
    name = "GET /api/skills/intelligence-contract"

    health = _check(
        "GET /api/health",
        client.get(f"{base}/api/health", headers=_auth_headers(cfg)),
    )
    ic_enabled = bool(health.get("intelligence_contract_enabled"))

    r = client.get(f"{base}/api/skills/intelligence-contract", headers=headers)
    if not ic_enabled:
        if r.status_code != 404:
            raise SystemExit(
                f"{name}: expected 404 when intelligence_contract_enabled=false, got {r.status_code}"
            )
        print(f"OK  {name} -> 404 (IC disabled)")
        return None

    data = _check(name, r)
    allowed_keys = {"enabled", "trade_types", "prompt_version"}
    extra = set(data.keys()) - allowed_keys
    if extra:
        raise SystemExit(f"{name}: unexpected fields {sorted(extra)!r}")
    if data.get("prompt_source") is not None:
        raise SystemExit(f"{name}: must not expose prompt_source")
    if data.get("enabled") is not True:
        raise SystemExit(f"{name}: enabled must be true when IC is on, got {data.get('enabled')!r}")

    trade_types = data.get("trade_types")
    if not isinstance(trade_types, list) or not trade_types:
        raise SystemExit(f"{name}: trade_types must be a non-empty array")
    for tt in trade_types:
        if not isinstance(tt, str) or not tt.strip():
            raise SystemExit(f"{name}: invalid trade_type entry {tt!r}")

    prompt_version = str(data.get("prompt_version", "") or "").strip()
    if not prompt_version:
        raise SystemExit(f"{name}: missing prompt_version")

    print(
        f"OK  {name}",
        f"trade_types={len(trade_types)}",
        f"prompt_version={prompt_version!r}",
    )
    for tt in trade_types:
        print(f"  • {tt}")
    return data


def test_intelligence_contract(
    client: httpx.Client, cfg: Dict[str, Any], meta: Dict[str, Any]
) -> None:
    if (os.environ.get("SKIP_IC_SMOKE") or "").strip().lower() in ("1", "true", "yes"):
        print("SKIP IC POST (SKIP_IC_SMOKE=1); catalog GET already ran")
        return

    pdf_path = _ic_pdf_path(cfg)
    if pdf_path is None:
        raw = str(cfg.get("intelligence_contract_pdf", "") or "").strip()
        if raw:
            raise SystemExit(f"Missing intelligence_contract_pdf file: {raw}")
        print("SKIP intelligence contract (set intelligence_contract_pdf in test.api.json)")
        return

    trade_type = _require_str(cfg, "trade_type")
    debug = True  # always on for IC: need source XML to verify trade_type
    headers = _auth_headers(
        cfg, diapason_api_jwt_token=_require_str(cfg, "diapason_api_jwt_token")
    )
    base = _base_url(cfg)
    print(
        f"→ POST /api/skills/intelligence-contract pdf={pdf_path} "
        f"trade_type={trade_type!r} timeout={IC_TIMEOUT_S:.0f}s",
        flush=True,
    )

    trade_types = meta.get("trade_types")
    if trade_type not in trade_types:
        raise SystemExit(
            f"trade_type {trade_type!r} not in catalog trade_types ({len(trade_types)} types)"
        )

    form = {"trade_type": trade_type, "debug": "true" if debug else "false"}
    try:
        with pdf_path.open("rb") as fh:
            r = client.post(
                f"{base}/api/skills/intelligence-contract",
                headers=headers,
                files={"pdf": (pdf_path.name, fh, "application/pdf")},
                data=form,
                timeout=IC_TIMEOUT_S,
            )
    except httpx.TimeoutException as exc:
        raise SystemExit(
            f"POST /api/skills/intelligence-contract timed out after {IC_TIMEOUT_S:.0f}s "
            f"({exc!r}). Default ACA ingress often closes idle HTTP ~240s; LLM extract + "
            f"resolveReferences can exceed that. Raise env premium-ingress request-idle-timeout, "
            f"or set SKIP_IC_SMOKE=1 to skip this step only."
        ) from exc
    except httpx.HTTPError as exc:
        raise SystemExit(f"POST /api/skills/intelligence-contract failed: {exc!r}") from exc
    data = _check("POST /api/skills/intelligence-contract", r)
    print("OK  POST /api/skills/intelligence-contract", f"success={data.get('success')}")
    if data.get("warnings"):
        print("  warnings:", data.get("warnings"))
    if debug:
        _print_ic_debug(data)

    trade_xml = str(data.get("trade_xml") or "").strip()
    if not data.get("success") or not trade_xml:
        if not debug:
            print("Tip: set intelligence_contract_debug=true in config for llm/resolve details.")
        raise SystemExit(
            f"IC resolveReferences failed: success={data.get('success')!r} "
            f"message={data.get('message')!r} warnings={data.get('warnings')!r}"
        )
    source_trade_xml = _ic_source_trade_xml(data)
    print(
        f"  view_entity={data.get('view_entity')!r} trade_type={trade_type!r} "
        f"trade_xml_len={len(trade_xml)} source_trade_xml_len={len(source_trade_xml)}"
    )

    # resolveReferences maps tradeType shortname to a numeric id in element text.
    if not source_trade_xml:
        raise SystemExit("IC debug response missing source trade_xml (extract.trade_xml)")
    if not _xml_has_trade_type(source_trade_xml, trade_type):
        print("\n--- source trade_xml (sent to resolveReferences) ---")
        print(source_trade_xml)
        print("\n--- resolved trade_xml ---")
        print(trade_xml)
        raise SystemExit(
            f"source trade_xml does not contain trade_type {trade_type!r} "
            f"(expected one of {_trade_type_markers(trade_type)!r})"
        )
    print(f"  OK  trade_type {trade_type!r} present in source trade_xml")

    if not re.search(r"<tradeType\b", trade_xml, re.IGNORECASE):
        print("\n--- resolved trade_xml ---")
        print(trade_xml)
        raise SystemExit("resolved trade_xml has no <tradeType> element")

    print("\n--- source trade_xml (first 1500 chars) ---")
    print(source_trade_xml[:1500])
    print("\n--- resolved trade_xml (first 1500 chars) ---")
    print(trade_xml[:1500])


def main() -> None:
    parser = argparse.ArgumentParser(description="Integration checks for Diapason Agent API.")
    parser.add_argument(
        "config",
        nargs="?",
        default=None,
        help=f"API test config JSON (default: test/{CONFIG_NAME})",
    )
    args = parser.parse_args()

    config_path = Path(args.config) if args.config else None
    cfg = _load_config(config_path)
    base = _base_url(cfg)
    print(f"Testing {base} (config: {_config_path}) ...")

    pdf_raw = str(cfg.get("intelligence_contract_pdf", "") or "").strip()
    client_timeout = IC_TIMEOUT_S if pdf_raw else TIMEOUT_S
    with httpx.Client(timeout=client_timeout) as client:
        test_health(client, cfg)
        _ensure_diapason_api_token(cfg, client)
        test_mcp_tools(client, cfg)
        session_id = test_sessions(client, cfg)
        test_chat(client, cfg, session_id)
        test_delete_session(client, cfg, session_id)
        meta = test_intelligence_contract_metadata(client, cfg)
        if pdf_raw and meta is not None:
            test_intelligence_contract(client, cfg, meta)
        elif pdf_raw and meta is None:
            print("SKIP IC POST (skill disabled on server)")

    print("All checks passed.")


if __name__ == "__main__":
    try:
        main()
    except httpx.HTTPError as exc:
        print(f"HTTP error: {exc}", file=sys.stderr)
        sys.exit(1)
