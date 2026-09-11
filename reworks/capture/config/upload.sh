#!/usr/bin/env bash
# Upload IC catalog + prompts to agent-config under skills/intelligence-contract/.

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_JSON="${1:-$(cd "$DIR/.." && pwd)/config.json}"
DEST_PREFIX="skills/intelligence-contract"

[[ -f "$CONFIG_JSON" ]] || {
  echo "error: config not found: $CONFIG_JSON" >&2
  exit 1
}

read -r ACCOUNT CONTAINER <<< "$(python3 - <<PY
import json
with open("$CONFIG_JSON", encoding="utf-8") as f:
    cfg = json.load(f)
storage = cfg.get("storage") or {}
print(
    storage.get("account_name", ""),
    storage.get("config_container") or "agent-config",
)
PY
)"

[[ -n "$ACCOUNT" ]] || {
  echo "error: storage.account_name missing in $CONFIG_JSON" >&2
  exit 1
}

echo "Uploading $DIR → $ACCOUNT/$CONTAINER/$DEST_PREFIX/ ..."
az storage blob upload-batch \
  --auth-mode login \
  --account-name "$ACCOUNT" \
  --destination "$CONTAINER" \
  --source "$DIR" \
  --destination-path "$DEST_PREFIX" \
  --pattern "catalog.json" \
  --overwrite

az storage blob upload-batch \
  --auth-mode login \
  --account-name "$ACCOUNT" \
  --destination "$CONTAINER" \
  --source "$DIR/prompts" \
  --destination-path "$DEST_PREFIX/prompts" \
  --pattern "*.txt" \
  --overwrite

echo "Done. Refresh Capture: POST /api/refresh-prompt"