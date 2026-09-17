"""Local configuration and refresh behavior without external storage."""

import json
from pathlib import Path

import pytest

from capture.workflow import prompts


def test_all_bundled_catalog_prompts_are_readable():
    project = Path(__file__).resolve().parents[2]
    prompts.init_capture_prompts({}, project)
    catalog = json.loads((project / "config/catalog.json").read_text(encoding="utf-8"))
    paths = set(catalog["prompts"])
    if catalog.get("default_prompt"):
        paths.add(catalog["default_prompt"])
    for path in paths:
        assert prompts.get_prompt_text({}, path).strip()


@pytest.mark.parametrize(
    "contents,error",
    [("[]", "JSON object"), ("", "Empty Capture config"), (None, "Cannot read Capture config")],
)
def test_invalid_or_missing_catalog_fails_locally(local_config, contents, error):
    catalog = local_config / "catalog.json"
    if contents is None:
        catalog.unlink()
    else:
        catalog.write_text(contents, encoding="utf-8")
    with pytest.raises(RuntimeError, match=error):
        prompts.init_capture_prompts({}, local_config.parent)


@pytest.mark.parametrize(
    "contents,error", [("", "Empty Capture config"), (None, "Cannot read Capture config")]
)
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


def test_refresh_reloads_catalog_metadata_and_invalidates_prompt_cache(local_config):
    first = prompts.init_capture_prompts({}, local_config.parent)
    assert first == {"ok": True, "version": "local-1", "source": str(local_config / "catalog.json")}
    assert prompts.get_prompt_text({}, "prompts/extract.txt") == "Extract the contract"
    (local_config / "prompts/extract.txt").write_text("Updated extraction", encoding="utf-8")
    (local_config / "catalog.json").write_text(
        json.dumps(
            {
                "version": "local-2",
                "prompts": {"prompts/extract.txt": ["new-loan"]},
            }
        ),
        encoding="utf-8",
    )
    assert prompts.get_prompt_text({}, "prompts/extract.txt") == "Extract the contract"
    refreshed = prompts.refresh_capture_prompts({}, local_config.parent)
    assert refreshed["version"] == prompts.capture_prompt_version() == "local-2"
    assert refreshed["source"] == prompts.capture_prompt_source() == first["source"]
    assert prompts.capture_trade_types() == ["new-loan"]
    assert prompts.get_prompt_text({}, "prompts/extract.txt") == "Updated extraction"


@pytest.mark.parametrize("ttl,seconds", [(10, 10), (0, 1), (-5, 1), ("invalid", 300), (None, 300)])
def test_prompt_cache_expires_at_configured_deadline(local_config, monkeypatch, ttl, seconds):
    from types import SimpleNamespace

    clock = SimpleNamespace(now=1000)
    monkeypatch.setattr(prompts, "time", SimpleNamespace(time=lambda: clock.now))
    config = {"capture": {"cache_ttl_seconds": ttl}}
    prompts.init_capture_prompts(config, local_config.parent)
    assert prompts.get_prompt_text(config, "prompts/extract.txt") == "Extract the contract"
    (local_config / "prompts/extract.txt").write_text("Updated extraction", encoding="utf-8")
    clock.now += seconds - 0.01
    assert prompts.get_prompt_text(config, "prompts/extract.txt") == "Extract the contract"
    clock.now = 1000 + seconds
    assert prompts.get_prompt_text(config, "prompts/extract.txt") == "Updated extraction"


def test_version_without_explicit_label_is_stable_and_changes_with_catalog(local_config):
    path = local_config / "catalog.json"
    path.write_text('{"prompts": {"prompts/extract.txt": ["loan"]}}', encoding="utf-8")
    first = prompts.init_capture_prompts({}, local_config.parent)["version"]
    assert len(first) == 12
    assert prompts.refresh_capture_prompts({}, local_config.parent)["version"] == first
    path.write_text('{"prompts": {"prompts/extract.txt": ["deposit"]}}', encoding="utf-8")
    assert prompts.refresh_capture_prompts({}, local_config.parent)["version"] != first


def test_failed_refresh_keeps_previous_catalog_and_cached_prompt(local_config):
    first = prompts.init_capture_prompts({}, local_config.parent)
    cached = prompts.get_prompt_text({}, "prompts/extract.txt")
    (local_config / "catalog.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        prompts.refresh_capture_prompts({}, local_config.parent)
    assert prompts.capture_prompt_version() == first["version"]
    assert prompts.capture_trade_types() == ["loan"]
    assert prompts.get_prompt_text({}, "prompts/extract.txt") == cached


def test_blank_prompt_path_is_rejected():
    with pytest.raises(ValueError, match="prompt_path is required"):
        prompts.get_prompt_text({}, "  ")
