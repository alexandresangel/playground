#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 <dev|test|prod> [plan]" >&2
  exit 1
}

[[ $# -eq 1 || $# -eq 2 ]] || usage
ENV="$1"
case "$ENV" in
  dev|test|prod) ;;
  *) usage ;;
esac
[[ $# -eq 2 && "$2" != plan ]] && usage
[[ "${2:-}" == plan ]] && export TERRAFORM_PLAN=1

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -z "${INFISICAL_CLIENT_ID:-}" ]]; then
  echo "error: set INFISICAL_*, Azure, and registry env (CI or source your local env file first)" >&2
  exit 1
fi

export DEPLOY_ENV="$ENV"

source "${ACTIONS_SERVICE_DEPLOY:-$ROOT/../actions/service-deploy}/aca-lib.sh"

export INFISICAL_SECRET_PATH=/diapason-agent IMAGE_NAME=diapason-agent TARGET_PORT=8000
export APP_NAME="${APP_NAME:-$IMAGE_NAME}"

deploy_init
infisical_init
infisical_export_many CHAT_CONFIG JWT_KEYSTORE_P12_B64
# Registry PAT is shared across services (Infisical path "/").
infisical_export_many_at "${INFISICAL_SHARED_SECRET_PATH:-/}" GHCR_TOKEN
infisical_export_many_optional_at "${INFISICAL_SHARED_SECRET_PATH:-/}" GHCR_USERNAME
registry_prepare

STORAGE_ACCOUNT_NAME="${STORAGE_ACCOUNT_NAME:-$(jq -r '.storage.account_name // empty' <<<"$CHAT_CONFIG")}"
CHAT_BLOB_CONTAINER="${CHAT_BLOB_CONTAINER:-$(jq -r '.storage.chat_container // "chat-sessions"' <<<"$CHAT_CONFIG")}"
CONFIG_BLOB_CONTAINER="${CONFIG_BLOB_CONTAINER:-$(jq -r '.storage.config_container // "agent-config"' <<<"$CHAT_CONFIG")}"
[[ -n "$STORAGE_ACCOUNT_NAME" ]] || {
  echo "error: set STORAGE_ACCOUNT_NAME or CHAT_CONFIG.storage.account_name for terraform" >&2
  exit 1
}
export STORAGE_ACCOUNT_NAME
terraform_ensure_infra "$ROOT/deploy" \
  -var="storage_account_name=$STORAGE_ACCOUNT_NAME" \
  -var="chat_blob_container=$CHAT_BLOB_CONTAINER" \
  -var="config_blob_container=$CONFIG_BLOB_CONTAINER"

[[ "${TERRAFORM_PLAN:-}" == 1 ]] && { log "plan only — done"; exit 0; }

if [[ "${SKIP_BUILD:-}" != 1 ]]; then
  log "frontend build → static/js/"
  (
    cd "$ROOT/frontend"
    npm ci
    npm run build
  )
  [[ -f "$ROOT/static/js/vendor.bundle.js" && -f "$ROOT/static/js/chat-app.js" && -f "$ROOT/static/js/boot.js" ]] \
    || { echo "error: frontend build missing static/js/*.js" >&2; exit 1; }
fi

# SKIP_BUILD=1 → promote existing IMAGE_TAG (registry_require_image); else build & push.
service_build_push "$ROOT/Dockerfile" "$ROOT"
export EXPECTED_VERSION="$(read_version "$ROOT")" EXPECTED_REVISION="$IMAGE_TAG"

ACA_DEPLOY_SECRETS=(
  chat-config="$CHAT_CONFIG"
  jwt-keystore-p12-b64="$JWT_KEYSTORE_P12_B64"
)
ACA_DEPLOY_ENV_VARS=(
  PORT="$TARGET_PORT"
  CHAT_CONFIG=secretref:chat-config
  JWT_KEYSTORE_P12_B64=secretref:jwt-keystore-p12-b64
)
otel_aca_append

# Optional metrics signal, independent of the private helper's Loki/Tempo defaults.
if [[ -n "${OTEL_EXPORTER_OTLP_METRICS_ENDPOINT:-}" ]]; then
  ACA_DEPLOY_ENV_VARS+=(
    OTEL_EXPORTER_OTLP_METRICS_ENDPOINT="$OTEL_EXPORTER_OTLP_METRICS_ENDPOINT"
    OTEL_EXPORTER_OTLP_METRICS_PROTOCOL=http/protobuf
  )
  if [[ -n "${OTEL_EXPORTER_OTLP_METRICS_HEADERS:-}" ]]; then
    ACA_DEPLOY_SECRETS+=(otel-metrics-headers="$OTEL_EXPORTER_OTLP_METRICS_HEADERS")
    ACA_DEPLOY_ENV_VARS+=(OTEL_EXPORTER_OTLP_METRICS_HEADERS=secretref:otel-metrics-headers)
  fi
fi
if [[ -n "${DIAPASON_OTLP_ENDPOINT_MODE:-}" ]]; then
  ACA_DEPLOY_ENV_VARS+=(DIAPASON_OTLP_ENDPOINT_MODE="$DIAPASON_OTLP_ENDPOINT_MODE")
fi

service_deploy_app "$APP_NAME" "$IMAGE_REF" "$TARGET_PORT" AGENT_URL
unset ACA_DEPLOY_SECRETS ACA_DEPLOY_ENV_VARS

if [[ "$DEPLOY_ENV" == dev ]]; then
  registry_prune_dev "$IMAGE_NAME" 3
fi

export AGENT_URL="${AGENT_URL%/}"

if [[ "${SKIP_SMOKE:-}" == 1 ]]; then
  log "SKIP_SMOKE=1 — done"
  exit 0
fi

wait_aca_health "$AGENT_URL"
assert_aca_image_tag
infisical_export_many SMOKE_API_CONFIG
log "smoke API $AGENT_URL"
with_python_venv "$ROOT" "$ROOT/requirements.txt" scripts/smoke.py
log "smoke passed"
