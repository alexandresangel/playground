"""Capture-specific HTTP fixtures, not an LLM or a general MCP server."""
import json
import xml.etree.ElementTree as ET

from cryptography.fernet import Fernet, InvalidToken
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from tools.configuration import load_offline, project_path, scenario, state_dir


def create_app():
    config = load_offline()
    app = FastAPI(title="Capture offline dependencies")

    def save_request(name, body):
        folder = state_dir(config) / "requests"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{name}.json").write_text(json.dumps(body, indent=2), encoding="utf-8")

    @app.get("/health")
    def health():
        return {"status": "ok", "mode": "offline-fixtures"}

    @app.post("/openai/deployments/{deployment}/chat/completions")
    async def completion(deployment: str, request: Request):
        if request.headers.get("api-key") != config["azure_openai"]["api_key"]:
            raise HTTPException(401, "Wrong offline API key")
        if deployment != config["azure_openai"]["deployment"]:
            raise HTTPException(404, "Unknown offline deployment")
        body = await request.json()
        save_request("llm", body)
        fixture = scenario(config)["llm"]
        status = int(fixture.get("http_status", 200))
        if status != 200:
            return JSONResponse({"error": {"message": "Configured offline LLM failure", "type": "offline"}}, status_code=status)
        content = fixture.get("content")
        if content is None:
            content = project_path(fixture["response_file"]).read_text(encoding="utf-8")
        return {
            "id": "offline-completion", "object": "chat.completion", "created": 0,
            "model": deployment,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": fixture.get("usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
        }

    @app.post("/mcp")
    async def mcp(request: Request):
        bearer = request.headers.get("Authorization", "").removeprefix("Bearer ")
        try:
            tenant = json.loads(Fernet(config["mcp"]["default"]["config_key"]).decrypt(bearer.encode()))
            if not tenant.get("api_token") or not tenant.get("base_url") or not isinstance(tenant.get("scope"), int):
                raise ValueError("Incomplete tenant")
        except (InvalidToken, ValueError, TypeError, AttributeError) as exc:
            raise HTTPException(401, "Invalid offline Fernet bearer") from exc
        body = await request.json()
        save_request("mcp", body)  # No Authorization header or decrypted credentials.
        fixture = scenario(config)["mcp"]
        status = int(fixture.get("http_status", 200))
        if status != 200:
            return JSONResponse({"detail": "Configured offline MCP HTTP failure"}, status_code=status)
        params = body.get("params", {})
        if body.get("method") != "tools/call" or params.get("name") != "resolveReferences":
            return {"jsonrpc": "2.0", "id": body.get("id"), "error": {"code": -32601, "message": "Only tools/call resolveReferences is implemented"}}
        if fixture.get("is_error"):
            result = {"isError": True, "content": [{"type": "text", "text": "Configured offline tool failure"}]}
        else:
            arguments = params["arguments"]
            root = ET.fromstring(arguments["trade_xml"])
            for element in root.iter():
                ids = fixture.get("reference_ids", {}).get(element.tag.rsplit("}", 1)[-1], {})
                shortname = element.get("shortname")
                if shortname in ids:
                    element.text = str(ids[shortname])
            payload = {
                "success": True, "trade_xml": ET.tostring(root, encoding="unicode"),
                "view_entity": arguments["view_entity"], "message": "", "warnings": [],
                **fixture.get("response", {}),
            }
            result = {"isError": False, "content": [{"type": "text", "text": json.dumps(payload)}]}
        return {"jsonrpc": "2.0", "id": body.get("id"), "result": result}

    return app
