"""Local configuration and refresh behavior without external storage."""

import json
from pathlib import Path

import pytest

from capture.workflow import prompts


@pytest.fixture
def local_config(tmp_path, monkeypatch):
    root = tmp_path / "config"
    (root / "prompts").mkdir(parents=True)
    (root / "catalog.json").write_text(json.dumps({
        "version": "local-1", "prompts": {"prompts/extract.txt": ["loan"]},
    }), encoding="utf-8")
    (root / "prompts/extract.txt").write_text("Extract the contract", encoding="utf-8")
    for name in ("_config_dir", "_catalog", "_catalog_version", "_catalog_source"):
        monkeypatch.setattr(prompts, name, getattr(prompts, name))
    monkeypatch.setattr(prompts, "_prompt_cache", {})
    return root


def test_all_bundled_catalog_prompts_are_readable(local_config):
    project = Path(__file__).resolve().parents[1]
    prompts.init_capture_prompts({}, project)
    catalog = json.loads((project / "config/catalog.json").read_text(encoding="utf-8"))
    paths = set(catalog["prompts"])
    if catalog.get("default_prompt"):
        paths.add(catalog["default_prompt"])
    for path in paths:
        assert prompts.get_prompt_text({}, path).strip()


@pytest.mark.parametrize("contents,error", [("[]", "JSON object"), ("", "Empty Capture config"), (None, "Cannot read Capture config")])
def test_invalid_or_missing_catalog_fails_locally(local_config, contents, error):
    catalog = local_config / "catalog.json"
    if contents is None:
        catalog.unlink()
    else:
        catalog.write_text(contents, encoding="utf-8")
    with pytest.raises(RuntimeError, match=error):
        prompts.init_capture_prompts({}, local_config.parent)


@pytest.mark.parametrize("contents,error", [("", "Empty Capture config"), (None, "Cannot read Capture config")])
def test_invalid_or_missing_prompt_fails_locally(local_config, contents, error):
    prompts.init_capture_prompts({}, local_config.parent)
    prompt = local_config / "prompts/extract.txt"
    if contents is None:
        prompt.unlink()
    else:
        prompt.write_text(contents, encoding="utf-8")
    with pytest.raises(RuntimeError, match=error):
        prompts.get_prompt_text({}, "prompts/extract.txt")


def test_prompt_paths_cannot_escape_config(local_config):
    prompts.init_capture_prompts({}, local_config.parent)
    for path in ("../config.json", str(local_config / "prompts/extract.txt")):
        with pytest.raises(ValueError, match="relative to the Capture config directory"):
            prompts.get_prompt_text({}, path)


def test_refresh_endpoint_uses_runtime_root_and_clears_cache(service, local_config, monkeypatch):
    service.runtime.base_dir = local_config.parent
    monkeypatch.chdir(local_config.parent.parent)
    headers = {"Authorization": service.headers["Authorization"]}
    wrong_scope = {"Authorization": "Bearer " + service.mint_token(scope="ai-agent")}
    assert service.client.post("/api/refresh-prompt", headers=wrong_scope).status_code == 401
    response = service.client.post("/api/refresh-prompt", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"ok": True, "version": "local-1", "source": str(local_config / "catalog.json")}
    assert prompts.get_prompt_text({}, "prompts/extract.txt") == "Extract the contract"
    (local_config / "prompts/extract.txt").write_text("Updated extraction", encoding="utf-8")
    assert prompts.get_prompt_text({}, "prompts/extract.txt") == "Extract the contract"
    assert service.client.post("/api/refresh-prompt", headers=headers).status_code == 200
    assert prompts.get_prompt_text({}, "prompts/extract.txt") == "Updated extraction"