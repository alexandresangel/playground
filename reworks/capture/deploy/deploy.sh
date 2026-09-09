#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 <dev|test|prod> [plan]" >&2
  exit 1
}

[[ $# -eq 1 || $# -eq 2 ]] || usage
DEPLOY_ENV="$1"
case "$DEPLOY_ENV" in dev|test|prod) ;; *) usage ;; esac
[[ $# -eq 2 && "$2" != plan ]] && usage
[[ "${2:-}" == plan ]] && export TERRAFORM_PLAN=1

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
: "${INFISICAL_CLIENT_ID:?set INFISICAL_*, Azure, and registry environment variables}"
export DEPLOY_ENV

source "${ACTIONS_SERVICE_DEPLOY:-$ROOT/../actions/service-deploy}/aca-lib.sh"

export INFISICAL_SECRET_PATH=/capture IMAGE_NAME=capture TARGET_PORT=8000
export APP_NAME="${APP_NAME:-$IMAGE_NAME}"

deploy_init
infisical_init
infisical_export_many CAPTURE_CONFIG JWT_KEYSTORE_P12_B64
infisical_export_many_at "${INFISICAL_SHARED_SECRET_PATH:-/}" GHCR_TOKEN
infisical_export_many_optional_at "${INFISICAL_SHARED_SECRET_PATH:-/}" GHCR_USERNAME
registry_prepare

STORAGE_ACCOUNT_NAME="${STORAGE_ACCOUNT_NAME:-$(jq -r '.storage.account_name // empty' <<<"$CAPTURE_CONFIG")}"
CONFIG_BLOB_CONTAINER="${CONFIG_BLOB_CONTAINER:-$(jq -r '.storage.config_container // "agent-config"' <<<"$CAPTURE_CONFIG")}"
[[ -n "$STORAGE_ACCOUNT_NAME" ]] || {
  echo "error: set storage.account_name in CAPTURE_CONFIG or STORAGE_ACCOUNT_NAME" >&2
  exit 1
}
export STORAGE_ACCOUNT_NAME

terraform_ensure_infra "$ROOT/deploy" \
  -var="storage_account_name=$STORAGE_ACCOUNT_NAME" \
  -var="config_blob_container=$CONFIG_BLOB_CONTAINER"

[[ "${TERRAFORM_PLAN:-}" == 1 ]] && { log "plan only — done"; exit 0; }

service_build_push "$ROOT/Dockerfile" "$ROOT"
export EXPECTED_VERSION="$(read_version "$ROOT")" EXPECTED_REVISION="$IMAGE_TAG"

ACA_DEPLOY_SECRETS=(
  capture-config="$CAPTURE_CONFIG"
  jwt-keystore-p12-b64="$JWT_KEYSTORE_P12_B64"
)
ACA_DEPLOY_ENV_VARS=(
  PORT="$TARGET_PORT"
  OTEL_SERVICE_NAME=capture
  CAPTURE_CONFIG=secretref:capture-config
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

service_deploy_app "$APP_NAME" "$IMAGE_REF" "$TARGET_PORT" CAPTURE_URL
unset ACA_DEPLOY_SECRETS ACA_DEPLOY_ENV_VARS

# Capture has long CPU/network work and should not cold-start on the user's synchronous request.
_az containerapp update \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --min-replicas "${CAPTURE_MIN_REPLICAS:-1}" \
  --max-replicas "${CAPTURE_MAX_REPLICAS:-3}" \
  -o none

if [[ "$DEPLOY_ENV" == dev ]]; then
  registry_prune_dev "$IMAGE_NAME" 3
fi

export CAPTURE_URL="${CAPTURE_URL%/}"
[[ "${SKIP_SMOKE:-}" == 1 ]] && { log "SKIP_SMOKE=1 — done"; exit 0; }

wait_aca_health "$CAPTURE_URL"
assert_aca_image_tag
log "smoke Capture $CAPTURE_URL"
curl --fail --silent --show-error "$CAPTURE_URL/health" >/dev/null
curl --fail --silent --show-error "$CAPTURE_URL/ready" >/dev/null
log "smoke passed"
