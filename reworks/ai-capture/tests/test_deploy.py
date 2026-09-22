"""Run the deployment entry point with a fake service-deploy library; no Azure calls."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.fixture
def deploy_shell(tmp_path):
    git = shutil.which("git")
    git_bash = Path(git).resolve().parent.parent / "bin/bash.exe" if git else None
    if os.name == "nt":
        bash = str(git_bash) if git_bash and git_bash.is_file() else None
    else:
        bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash is required to validate the deploy entry point")
    (tmp_path / "aca-lib.sh").write_text('''
log() { echo "$*"; }
github_registry_init() { echo "registry:$APP_NAME:$IMAGE_NAME:$INFISICAL_SECRET_PATH"; }
service_build_push() { export IMAGE_REF="registry/$IMAGE_NAME:$IMAGE_TAG"; echo "build:$SKIP_BUILD"; }
read_version() { cat "$1/VERSION"; }
azure_login() { echo "azure-login"; }
infisical_init() { export INFISICAL_TOKEN=test; }
otel_aca_append() { echo "otel:$APP_NAME-$DEPLOY_ENV"; }
service_deploy_app() {
  echo "deploy:$1:$3:$4:$RESOURCE_GROUP:$SKIP_ACA_REGISTRY_SET"
  printf -v "$4" '%s' 'https://capture.example/'
  export "$4"
}
wait_aca_health() { echo "health:$1"; }
assert_aca_image_tag() { echo "image:$EXPECTED_REVISION"; }
infisical_export_many() { export SMOKE_API_CONFIG='{}'; }
uv() { echo "smoke:$*"; }
''', encoding="utf-8", newline="\n")
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("INFISICAL_", "SKIP_", "RESOURCE_GROUP", "CAPTURE_URL", "ACA_DEPLOY_"))}
    env.update(ACTIONS_SERVICE_DEPLOY=tmp_path.as_posix(), IMAGE_TAG="test-sha", SKIP_BUILD="0")
    return bash, env


@pytest.mark.parametrize("target,promote", [("dev", "0"), ("staging", "1"), ("prod", "1")])
def test_deploy_targets_capture_and_runs_capture_smoke(deploy_shell, target, promote):
    bash, env = deploy_shell
    env.update(INFISICAL_CLIENT_ID="test", SKIP_BUILD=promote)
    result = subprocess.run([bash, "deploy/deploy.sh", target], env=env,
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "registry:ai-capture:ai-capture:/ai-capture" in result.stdout
    assert f"build:{promote}" in result.stdout
    assert f"deploy:ai-capture:8000:CAPTURE_URL:diapason-{target}:1" in result.stdout
    assert "health:https://capture.example" in result.stdout and "image:test-sha" in result.stdout
    assert "--locked --no-dev python" in result.stdout and "tests/smoke_capture.py" in result.stdout


def test_deploy_without_infisical_still_checks_health(deploy_shell):
    bash, env = deploy_shell
    result = subprocess.run([bash, "deploy/deploy.sh", "dev"], env=env,
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "health:https://capture.example" in result.stdout and "image:test-sha" in result.stdout
    assert "no Infisical" in result.stdout and "smoke:run" not in result.stdout


def test_legacy_test_environment_is_rejected(deploy_shell):
    bash, env = deploy_shell
    result = subprocess.run([bash, "deploy/deploy.sh", "test"], env=env,
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert result.returncode != 0
    assert "registry:" not in result.stdout
