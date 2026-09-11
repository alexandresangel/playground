#!/usr/bin/env bash
# Upload agent config blobs (Capture catalog + extraction prompts) — independent of app deploy.
# Usage: ./deploy/deploy-config.sh <dev|test|prod>
# Needs: az login with Storage Blob Data Contributor (or higher) on the config container.

set -euo pipefail

usage() {
  echo "Usage: $0 <dev|test|prod>" >&2
  exit 1
}

[[ $# -eq 1 ]] || usage
ENV="$1"
case "$ENV" in
  dev|test|prod) ;;
  *) usage ;;
esac

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IC_DIR="$ROOT/config"
IC_PREFIX="skills/intelligence-contract"

# Resolve account/container: env vars > config.<env>.json > config.json > defaults.
CONFIG_JSON="${CONFIG_JSON:-}"
if [[ -z "$CONFIG_JSON" ]]; then
  for cand in "$ROOT/config.${ENV}.json" "$ROOT/config.json"; do
    [[ -f "$cand" ]] && CONFIG_JSON="$cand" && break
  done
fi

ACCOUNT="${STORAGE_ACCOUNT_NAME:-}"
CONTAINER="${CONFIG_BLOB_CONTAINER:-}"
if [[ -z "$ACCOUNT" || -z "$CONTAINER" ]] && [[ -n "${CONFIG_JSON:-}" && -f "$CONFIG_JSON" ]]; then
  read -r _acc _ctr <<< "$(python3 - <<PY
import json
with open("$CONFIG_JSON", encoding="utf-8") as f:
    s = (json.load(f).get("storage") or {})
print(s.get("account_name") or "", s.get("config_container") or "")
PY
)"
  ACCOUNT="${ACCOUNT:-$_acc}"
  CONTAINER="${CONTAINER:-$_ctr}"
fi
ACCOUNT="${ACCOUNT:-diapason${ENV}stor}"
CONTAINER="${CONTAINER:-agent-config}"

[[ -f "$IC_DIR/catalog.json" ]] || {
  echo "error: missing $IC_DIR/catalog.json" >&2
  exit 1
}
[[ -d "$IC_DIR/prompts" ]] || {
  echo "error: missing $IC_DIR/prompts/" >&2
  exit 1
}

echo "==> $ACCOUNT / $CONTAINER  (env=$ENV${CONFIG_JSON:+, config=$CONFIG_JSON})"

echo "==> $IC_PREFIX/catalog.json"
az storage blob upload \
  --auth-mode login \
  --account-name "$ACCOUNT" \
  --container-name "$CONTAINER" \
  --name "$IC_PREFIX/catalog.json" \
  --file "$IC_DIR/catalog.json" \
  --overwrite \
  -o none

echo "==> $IC_PREFIX/prompts/*.txt"
az storage blob upload-batch \
  --auth-mode login \
  --account-name "$ACCOUNT" \
  --destination "$CONTAINER" \
  --source "$IC_DIR/prompts" \
  --destination-path "$IC_PREFIX/prompts" \
  --pattern "*.txt" \
  --overwrite \
  -o none

echo "Done. Reload prompts: POST /api/refresh-prompt (JWT role refresh)"
