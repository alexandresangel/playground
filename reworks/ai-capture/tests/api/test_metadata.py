"""Metadata, health, refresh authorization, and the stateless service surface."""

import pytest

from capture.workflow import prompts


@pytest.mark.parametrize("path", ["/api/capture", "/api/skills/intelligence-contract"])
def test_metadata_requires_only_bearer_and_reports_bundled_catalog(service, path):
    response = service.client.get(path, headers={"Authorization": service.headers["Authorization"]})
    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "trade_types": prompts.capture_trade_types(),
        "prompt_version": prompts.capture_prompt_version(),
    }
    assert service.client.get(path).status_code == 401


@pytest.mark.parametrize(
    "path", ["/", "/api/chat", "/api/sessions", "/static/index.html", "/ai/capture"]
)
def test_chat_frontend_and_noncanonical_routes_are_absent(service, path):
    assert service.client.get(path).status_code == 404


@pytest.mark.parametrize("path", ["/health", "/api/health"])
def test_health_is_public(service, path):
    response = service.client.get(path)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_refresh_endpoint_uses_runtime_root_and_clears_cache(service, local_config, monkeypatch):
    service.runtime.base_dir = local_config.parent
    monkeypatch.chdir(local_config.parent.parent)
    token = service.runtime.auth.mint(sub="instance:demo", roles=["refresh"])
    headers = {"Authorization": "Bearer " + token["access_token"]}
    assert service.client.post("/api/refresh-prompt", headers=service.headers).status_code == 401
    response = service.client.post("/api/refresh-prompt", headers=headers)
    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "version": "local-1",
        "source": str(local_config / "catalog.json"),
    }
    assert prompts.get_prompt_text({}, "prompts/extract.txt") == "Extract the contract"
    (local_config / "prompts/extract.txt").write_text("Updated extraction", encoding="utf-8")
    assert prompts.get_prompt_text({}, "prompts/extract.txt") == "Extract the contract"
    assert service.client.post("/api/refresh-prompt", headers=headers).status_code == 200
    assert prompts.get_prompt_text({}, "prompts/extract.txt") == "Updated extraction"
