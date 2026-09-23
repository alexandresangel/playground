import json

import build_info


def test_image_build_identity_and_runtime_release(tmp_path, monkeypatch):
    path = tmp_path / "build-info.json"
    path.write_text(json.dumps({"build_date": "2026-09-23T12:00:00Z", "revision": "abc123"}))
    monkeypatch.setattr(build_info, "_BUILD_INFO", path)
    monkeypatch.setenv("RELEASE_TAG", "v1.2.3")
    assert build_info.health() == {
        "status": "ok", "build_date": "2026-09-23T12:00:00Z", "revision": "abc123",
        "version": build_info.load()["version"], "release": "v1.2.3",
    }
    monkeypatch.setenv("RELEASE_TAG", "")
    assert build_info.health()["release"] == ""


def test_legacy_image_and_local_fallback(tmp_path, monkeypatch):
    path = tmp_path / "build-info.json"
    monkeypatch.setattr(build_info, "_BUILD_INFO", path)
    path.write_text('{"version":"0.1.11","revision":"older"}')
    assert build_info.load() == {"version": "0.1.11", "build_date": "0.1.11", "revision": "older"}
    path.unlink()
    version = tmp_path / "VERSION"
    version.write_text("0.2.0")
    monkeypatch.setattr(build_info, "_VERSION_FILE", version)
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.delenv("APP_REVISION", raising=False)
    monkeypatch.setenv("GIT_REVISION", "local")
    monkeypatch.setenv("BUILD_DATE", "today")
    assert build_info.load() == {"version": "0.2.0", "build_date": "today", "revision": "local"}
