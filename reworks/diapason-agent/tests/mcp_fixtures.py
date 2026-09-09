"""Protocol-shaped responses for low-level negative tests; SDK servers cover integration."""

import json

import httpx


def initialization_response(request):
    if request.method != "POST":
        return httpx.Response(405)
    body = json.loads(request.content)
    if body["method"] == "initialize":
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {
                    "protocolVersion": body["params"]["protocolVersion"],
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fixture", "version": "1"},
                },
            },
        )
    if body["method"].startswith("notifications/"):
        return httpx.Response(202)
    return None
