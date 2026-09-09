import json
from pathlib import Path

import httpx
from conftest import FakeMcp, FakeModel, MemoryStore
from fastapi.testclient import TestClient

from pascal.main import create_app
from pascal.sessions.blob_store import BlobSessionStore, _decode, _new_record


def test_blob_missing_record_append_applies_update():
    store = object.__new__(BlobSessionStore)
    store._load = lambda key: (None, None)
    uploaded = []

    class Blob:
        def upload_blob(self, data, **kwargs):
            uploaded.append(_decode(data))

    store._blob = lambda key: Blob()
    create = _new_record("demo/12/7", session_id="session")

    def update(record):
        record["turns"].append({"role": "user", "content": "Do not lose me"})
        return record

    result = store._update("key", update, create=create)
    assert result["turns"][0]["content"] == "Do not lose me"
    assert uploaded == [result]


def test_capture_proxy_keeps_wire_result_and_minimal_receipt(config, headers, auth):
    seen = []
    result = {
        "success": True,
        "trade_type": "loan",
        "view_entity": "loanDeposit",
        "menu_name": "Loan",
        "trade_xml": "<trade/>",
        "extracted_field_count": 4,
        "session_artifacts": {"sensitive": "do not save"},
        "timings_ms": {},
    }

    async def responder(request):
        seen.append(request)
        return httpx.Response(
            200, json=result if request.method == "POST" else {"enabled": True, "trade_types": []}
        )

    config["capture"] = {"enabled": True, "base_url": "https://capture.example"}
    store = MemoryStore()
    client = httpx.AsyncClient(transport=httpx.MockTransport(responder))
    app = create_app(
        config=config,
        auth=auth,
        model=FakeModel(),
        transport=FakeMcp(),
        store=store,
        prompt_text="Pascal",
        capture_client=client,
        root=Path.cwd(),
    )
    with TestClient(app) as api:
        response = api.post(
            "/api/skills/intelligence-contract",
            headers=headers,
            data={"trade_type": "loan", "debug": "false"},
            files={"pdf": ("contract.pdf", b"%PDF-test", "application/pdf")},
        )
        assert response.status_code == 200, response.text
        assert response.json()["trade_xml"] == "<trade/>"
        assert "session_artifacts" not in response.json()
        assert seen[0].headers["Authorization"] == headers["Authorization"]
        assert seen[0].headers["X-Diapason-Mcp-Scope"] == "5"
        assert b"%PDF-test" in seen[0].content
        record = next(iter(store.records.values()))
        assert "<trade/>" not in json.dumps(record)
        assert "do not save" not in json.dumps(record)
        assert store.writes == 1
        receipt = record["turns"][-1]["capture_receipt"]
        assert receipt == {"operation": "capture", "trade_type": "loan", "success": True}
        assert "skill_run" not in record["turns"][-1]


def test_old_private_artifact_field_is_readable_but_not_exposed():
    from pascal.sessions.blob_store import turns_for_client

    old = {"role": "assistant", "content": "Imported", "skill_run": {"artifacts": "PRIVATE"}}
    assert turns_for_client([old]) == [{"role": "assistant", "content": "Imported"}]
    assert "skill_run" in old  # No destructive migration of stored records.


def test_original_grafana_adjacent_field_regex_still_matches(identity):
    import re

    from pascal.compatibility import completion_prefix

    fields = completion_prefix(identity, "session", {"input": 10, "output": 2}, None, "balance", "")
    line = " ".join(f"{key}={json.dumps(value)}" for key, value in fields.items())
    expression = (
        r"customer=(?P<customer>\S+) user=(?P<user>\S+) session=(?P<session>\S+) "
        r"tokens_in=(?P<tokens_in>\S*) tokens_out=(?P<tokens_out>\S*) "
        r"cost_usd=(?P<cost_usd>\S*) tools=(?P<tools>\S*) skills=(?P<skills>\S*)"
    )
    match = re.search(expression, line)
    assert match and match.group("customer") == str(identity.customer_id)
