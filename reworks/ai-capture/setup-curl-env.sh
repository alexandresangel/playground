#!/usr/bin/env bash

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo "Run: source ./setup-curl-env.sh" >&2
  exit 1
fi

_capture_setup() {
  local root platform_file app_file registry_url login_response raw_pdf candidate

  root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || return 1
  platform_file="${INTEG_PLATFORM_CONFIG_FILE:-$root/tests/integ.platform.local.json}"
  app_file="${INTEG_APP_CONFIG_FILE:-$root/tests/integ.app.pascal-dev.json}"

  for command_name in curl jq uv; do
    command -v "$command_name" >/dev/null || {
      echo "Missing command: $command_name" >&2
      return 1
    }
  done

  [[ -f "$platform_file" ]] || {
    echo "Config not found: $platform_file" >&2
    return 1
  }
  [[ -f "$app_file" ]] || {
    echo "Config not found: $app_file" >&2
    return 1
  }

  INTEG_PLATFORM_CONFIG="$(<"$platform_file")"
  INTEG_APP_CONFIG="$(<"$app_file")"
  API_CONFIG="$(jq -s '.[0] + .[1]' "$platform_file" "$app_file")" || return 1

  CAPTURE_URL="${CAPTURE_URL:-http://localhost:7703}"
  CAPTURE_URL="${CAPTURE_URL%/}"

  DIAPASON_BASE_URL="$(jq -er '.diapason_base_url' <<<"$API_CONFIG")" || return 1
  DIAPASON_BASE_URL="${DIAPASON_BASE_URL%/}"
  DIAPASON_USER_ID="$(jq -er '.diapason_user_id' <<<"$API_CONFIG")" || return 1
  DIAPASON_CUSTOMER_ID="$(jq -er '.diapason_customer_id' <<<"$API_CONFIG")" || return 1
  DIAPASON_SCOPE="$(jq -er '.diapason_scope' <<<"$API_CONFIG")" || return 1
  TRADE_TYPE="$(jq -er '.trade_type // "iamLoan"' <<<"$API_CONFIG")" || return 1

  M2M_TOKEN="$(jq -r '.capture_jwt_token // empty' <<<"$API_CONFIG")" || return 1
  if [[ -z "$M2M_TOKEN" ]]; then
    M2M_CLIENT_ID="$(jq -er '.m2m_client_id' <<<"$API_CONFIG")" || return 1
    M2M_CLIENT_SECRET="$(jq -er '.m2m_client_secret' <<<"$API_CONFIG")" || return 1
    M2M_TOKEN_URL="$(jq -r '.m2m_token_url // empty' <<<"$API_CONFIG")" || return 1

    if [[ -z "$M2M_TOKEN_URL" ]]; then
      registry_url="$(jq -er '.registry_url' <<<"$API_CONFIG")" || return 1
      M2M_TOKEN_URL="$(
        curl --fail-with-body -sS "$registry_url" |
          jq -er '.services.m2m.url'
      )" || return 1
    fi

    M2M_TOKEN="$(
      curl --fail-with-body -sS "$M2M_TOKEN_URL" \
        --user "$M2M_CLIENT_ID:$M2M_CLIENT_SECRET" \
        -H 'Accept: application/json' \
        --data-urlencode 'grant_type=client_credentials' |
        jq -er '.access_token | select(type == "string" and length > 0)'
    )" || return 1
  fi

  DIAPASON_API_TOKEN="$(jq -r '.diapason_api_jwt_token // empty' <<<"$API_CONFIG")" || return 1
  if [[ -z "$DIAPASON_API_TOKEN" ]]; then
    local diapason_client_id diapason_client_secret

    diapason_client_id="$(
      jq -er '.diapason_client_id // .client_id' <<<"$API_CONFIG"
    )" || return 1
    diapason_client_secret="$(
      jq -er '.diapason_client_secret // .client_secret' <<<"$API_CONFIG"
    )" || return 1

    DIAPASON_API_TOKEN="$(
      curl --fail-with-body -sS "$DIAPASON_BASE_URL/api/login" \
        --data-urlencode 'locale=en_US' \
        --data-urlencode "client_id=$diapason_client_id" \
        --data-urlencode "client_secret=$diapason_client_secret" |
        uv run --locked python -c '
import sys
import xml.etree.ElementTree as ET

root = ET.parse(sys.stdin).getroot()
token = (root.get("apiToken") or root.get("token") or "").strip()
if not token:
    raise SystemExit("Diapason login response has no API token")
print(token)
'
    )" || return 1
  fi

  raw_pdf="$(
    jq -er '.capture_pdf // .intelligence_contract_pdf // "fixtures/sample-loan-contract.pdf"' \
      <<<"$API_CONFIG"
  )" || return 1

  CAPTURE_PDF=""
  for candidate in \
    "$(dirname "$app_file")/$raw_pdf" \
    "$root/$raw_pdf" \
    "$root/tests/$raw_pdf"; do
    if [[ -f "$candidate" ]]; then
      CAPTURE_PDF="$candidate"
      break
    fi
  done

  [[ -n "$CAPTURE_PDF" ]] || {
    echo "PDF not found: $raw_pdf" >&2
    return 1
  }

  export CAPTURE_URL API_CONFIG INTEG_PLATFORM_CONFIG INTEG_APP_CONFIG
  export M2M_CLIENT_ID M2M_CLIENT_SECRET M2M_TOKEN_URL M2M_TOKEN
  export DIAPASON_BASE_URL DIAPASON_USER_ID DIAPASON_CUSTOMER_ID
  export DIAPASON_SCOPE DIAPASON_API_TOKEN TRADE_TYPE CAPTURE_PDF

  echo "Capture environment ready: $CAPTURE_URL"
  echo "PDF: $CAPTURE_PDF"
}

_capture_setup
_capture_setup_status=$?
unset -f _capture_setup
return "$_capture_setup_status"