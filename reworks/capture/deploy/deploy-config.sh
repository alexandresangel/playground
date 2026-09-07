#!/usr/bin/env bash
# Upload the bundled legacy-compatible catalog/prompts to the shared config container.
set -euo pipefail

[[ $# -eq 1 ]] || { echo "Usage: $0 <dev|test|prod>" >&2; exit 1; }
DEPLOY_ENV="$1"
case "$DEPLOY_ENV" in dev|test|prod) ;; *) exit 1 ;; esac

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PREFIX="skills/intelligence-contract"
CONFIG_JSON="${CONFIG_JSON:-$ROOT/config.json}"
ACCOUNT="${STORAGE_ACCOUNT_NAME:-}"
CONTAINER="${CONFIG_BLOB_CONTAINER:-}"
if [[ (-z "$ACCOUNT" || -z "$CONTAINER") && -f "$CONFIG_JSON" ]]; then
  read -r config_account config_container <<<"$(python3 -c 'import json,sys; s=(json.load(open(sys.argv[1], encoding="utf-8")).get("storage") or {}); print(s.get("account_name") or "", s.get("config_container") or "")' "$CONFIG_JSON")"
  ACCOUNT="${ACCOUNT:-$config_account}"
  CONTAINER="${CONTAINER:-$config_container}"
fi
ACCOUNT="${ACCOUNT:-diapason${DEPLOY_ENV}stor}"
CONTAINER="${CONTAINER:-agent-config}"

az storage blob upload \
  --auth-mode login --account-name "$ACCOUNT" --container-name "$CONTAINER" \
  --name "$PREFIX/catalog.json" --file "$ROOT/config/catalog.json" --overwrite -o none
az storage blob upload-batch \
  --auth-mode login --account-name "$ACCOUNT" --destination "$CONTAINER" \
  --source "$ROOT/config/prompts" --destination-path "$PREFIX/prompts" \
  --pattern "*.txt" --overwrite -o none
echo "Capture catalog uploaded to $ACCOUNT/$CONTAINER/$PREFIX"

