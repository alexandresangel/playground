import json

import httpx

from pascal.adapters.model import AzureModel
from pascal.config import AgentLimits


async def test_real_azure_sdk_stream_fragments_usage_and_options():
    received = []

    async def responder(request):
        received.append(json.loads(request.content))
        chunks = [
            {"choices": [{"index": 0, "delta": {"content": "Checking "}, "finish_reason": None}]},
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "balance", "arguments": '{"account":'},
                                }
                            ]
                        },
                        "finish_reason": None,
                    }
                ]
            },
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {"tool_calls": [{"index": 0, "function": {"arguments": '"A"}'}}]},
                        "finish_reason": "tool_calls",
                    }
                ]
            },
            {
                "choices": [],
                "usage": {
                    "prompt_tokens": 50,
                    "completion_tokens": 10,
                    "total_tokens": 60,
                    "prompt_tokens_details": {"cached_tokens": 20},
                },
            },
        ]
        payload = "".join(
            "data: "
            + json.dumps(
                {
                    "id": "completion",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "test",
                    **chunk,
                }
            )
            + "\n\n"
            for chunk in chunks
        )
        return httpx.Response(
            200, text=payload + "data: [DONE]\n\n", headers={"content-type": "text/event-stream"}
        )

    config = {
        "endpoint": "https://azure.example",
        "api_key": "test",
        "deployment": "test",
        "temperature": 0.1,
    }
    adapter = AzureModel(
        config,
        AgentLimits(),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(responder)),
    )
    deltas = []

    async def delta(content):
        deltas.append(content)

    reply = await adapter.complete([{"role": "user", "content": "Balance?"}], [], 256, delta)
    assert deltas == ["Checking "]
    assert reply.tool_calls[0].name == "balance"
    assert reply.tool_calls[0].arguments == '{"account":"A"}'
    assert reply.usage == {"input": 50, "output": 10, "total": 60, "cached_input": 20}
    assert received[0]["max_tokens"] == 256
    assert received[0]["temperature"] == 0.1
    assert received[0]["stream_options"] == {"include_usage": True}
    await adapter.close()
