#!/usr/bin/env bash
# Build/push (or promote) image, then roll ACA. TF owns shell + secrets.
set -euo pipefail

usage() { echo "Usage: $0 <dev|staging|prod>" >&2; exit 1; }
[[ $# -eq 1 ]] || usage
case "$1" in
  dev|staging|prod) ;;
  *) usage ;;
esac

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "${ACTIONS_SERVICE_DEPLOY:-$ROOT/../actions/service-deploy}/aca-lib.sh"

export APP_NAME=ai-capture
export INFISICAL_SECRET_PATH=/ai-capture
export IMAGE_NAME="$APP_NAME"
export DEPLOY_ENV="$1"
export RESOURCE_GROUP="${RESOURCE_GROUP:-diapason-${DEPLOY_ENV}}"
export SKIP_ACA_REGISTRY_SET=1

github_registry_init

service_build_push "$ROOT/Dockerfile" "$ROOT"
export EXPECTED_VERSION="$(read_version "$ROOT")" EXPECTED_REVISION="$IMAGE_TAG"

azure_login

ACA_DEPLOY_ENV_VARS=()
ACA_DEPLOY_SECRETS=()
if [[ -n "${INFISICAL_CLIENT_ID:-}" ]]; then
  infisical_init
  otel_aca_append
fi
export ACA_DEPLOY_ENV_VARS ACA_DEPLOY_SECRETS
service_deploy_app "$APP_NAME" "$IMAGE_REF" 8000 CAPTURE_URL
unset ACA_DEPLOY_ENV_VARS ACA_DEPLOY_SECRETS
log "deployed $IMAGE_REF → ${ACA_DEPLOY_URL:-}"

export CAPTURE_URL="${CAPTURE_URL:-${ACA_DEPLOY_URL:-}}"
export CAPTURE_URL="${CAPTURE_URL%/}"
wait_aca_health "$CAPTURE_URL"
assert_aca_image_tag

[[ "${SKIP_SMOKE:-}" == 1 ]] && { log "SKIP_SMOKE=1 — done"; exit 0; }
[[ -n "${INFISICAL_CLIENT_ID:-}" ]] || { log "no Infisical — skip smoke"; exit 0; }

[[ -n "${INFISICAL_TOKEN:-}" ]] || infisical_init
infisical_export_many SMOKE_API_CONFIG
: "${SMOKE_API_CONFIG:?set SMOKE_API_CONFIG in Infisical ${INFISICAL_SECRET_PATH:-/${APP_NAME}} (or SKIP_SMOKE=1)}"
log "smoke API $CAPTURE_URL"
uv run --project "$ROOT" --locked --no-dev python "$ROOT/tests/smoke_capture.py"
log "smoke passed"
