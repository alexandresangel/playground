"""Offline container fixture: real ASGI/JWT/graphs with bundled config and model doubles.

Mounted only by the migration container check. Never copied into the runtime image.
"""

import importlib
from types import SimpleNamespace as NS

from capture.workflow import graph


class Model:
    def __init__(self):
        self.chat = NS(completions=NS(create=self.create))
    def close(self): pass
    def create(self, **kwargs):
        text = '<trade><tradeType shortname="wrong"/><amount>123</amount></trade>'
        usage = NS(prompt_tokens=10, completion_tokens=4, total_tokens=14)
        if kwargs.get("stream"):
            class Stream:
                def __iter__(self):
                    yield NS(choices=[NS(delta=NS(content=text, tool_calls=[]))], usage=None)
                    yield NS(choices=[], usage=usage)
                def close(self): pass
            return Stream()
        return NS(choices=[NS(message=NS(content=text, tool_calls=[]))], usage=usage)


runtime_module = importlib.import_module("capture.runtime")
runtime_module.AzureOpenAI = lambda **kwargs: Model()


def resolve(server, name, arguments, **kwargs):
    assert name == "resolveReferences"
    assert arguments["view_entity"] == "loanDeposit"
    assert 'shortname="iamLoan"' in arguments["trade_xml"]
    return {"success": True, "trade_xml": arguments["trade_xml"], "warnings": []}
graph.mcp_call_tool_json = resolve

# Exercise the actual installed entry point and runtime assembly.
app = importlib.import_module("capture.asgi").app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)