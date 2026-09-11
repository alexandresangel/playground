"""Offline container fixture: real ASGI/JWT/graphs with local Blob and model doubles.

Mounted only by the migration container check. Never copied into the runtime image.
"""

import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace as NS

from azure.core.exceptions import ResourceNotFoundError

SERVICE = os.environ["TEST_SERVICE"]
STATE = Path("/test-state")


class LocalBlob:
    def __init__(self, key):
        self.path = STATE / "blobs" / key

    def download_blob(self):
        if not self.path.is_file():
            raise ResourceNotFoundError("test blob missing")
        return NS(readall=self.path.read_bytes, properties=None)

    def upload_blob(self, data, **kwargs):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(data)

    def delete_blob(self):
        self.path.unlink()


class LocalContainer:
    def create_container(self): pass
    def get_blob_client(self, key): return LocalBlob(key)
    def list_blobs(self, name_starts_with):
        root = STATE / "blobs"
        return [NS(name=p.relative_to(root).as_posix()) for p in root.rglob("*.json") if p.relative_to(root).as_posix().startswith(name_starts_with)]


def read_prompt(account, container, key):
    if key == "system_prompt.md":
        return "Original system prompt fixture"
    if key.endswith("catalog.json"):
        return json.dumps({"version": "offline-1", "default_view_entity": "loanDeposit", "prompts": {"prompts/mltLoan.txt": ["iamLoan"]}})
    return "Extract the exact trade type requested."


class Model:
    def __init__(self):
        self.chat = NS(completions=NS(create=self.create))
    def close(self): pass
    def create(self, **kwargs):
        if SERVICE == "capture":
            text = '<trade><tradeType shortname="wrong"/><amount>123</amount></trade>'
        else:
            text = "Bonjour from Pascal"
        usage = NS(prompt_tokens=10, completion_tokens=4, total_tokens=14)
        if kwargs.get("stream"):
            class Stream:
                def __iter__(self):
                    yield NS(choices=[NS(delta=NS(content=text, tool_calls=[]))], usage=None)
                    yield NS(choices=[], usage=usage)
                def close(self): pass
            return Stream()
        return NS(choices=[NS(message=NS(content=text, tool_calls=[]))], usage=usage)


import blob_client
import session_store
blob_client.read_blob_text = read_prompt
session_store.connect_blob = lambda *args: (None, LocalContainer(), "offline-double")
runtime_module = importlib.import_module(f"{SERVICE}.runtime")
runtime_module.AzureOpenAI = lambda **kwargs: Model()

if SERVICE == "capture":
    from capture.workflow import graph
    def resolve(server, name, arguments, **kwargs):
        assert name == "resolveReferences"
        assert arguments["view_entity"] == "loanDeposit"
        assert 'shortname="iamLoan"' in arguments["trade_xml"]
        return {"success": True, "trade_xml": arguments["trade_xml"], "warnings": []}
    graph.mcp_call_tool_json = resolve
else:
    from pascal.agent import discovery, mcp
    discovery._mcp_request = mcp._mcp_request = lambda *args, **kwargs: {"tools": []}

# Exercise the actual installed entry point and runtime assembly.
app = importlib.import_module(f"{SERVICE}.asgi").app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
