import json

import httpx

from capture.adapters.model import CaptureModel


async def test_capture_uses_real_v1_sdk_and_preserves_extraction_messages():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "fixture",
                "object": "chat.completion",
                "created": 0,
                "model": "approved-deployment",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "<trade/>"},
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    model = CaptureModel(
        {
            "azure_openai": {
                "endpoint": "https://azure.example",
                "deployment": "approved-deployment",
                "api_key": "fixture",
                "max_retries": 0,
            }
        },
        http_client=http,
    )
    try:
        result = await model.extract(
            prompt="approved prompt", document_text="PDF TEXT", temperature=0.5
        )
        body = json.loads(requests[0].content)
        assert requests[0].url.path == "/openai/v1/chat/completions"
        assert body["messages"] == [
            {"role": "system", "content": "approved prompt"},
            {
                "role": "user",
                "content": "Extract the trade as Diapason import XML from this document text. "
                "Return XML only.\n\nPDF TEXT",
            },
        ]
        assert body["model"] == "approved-deployment"
        assert body["temperature"] == 0.5
        assert result == {
            "content": "<trade/>",
            "deployment": "approved-deployment",
            "usage": {"input": 10, "output": 5, "total": 15},
        }
    finally:
        await model.close()
    assert http.is_closed
