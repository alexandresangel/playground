# Capture

TODO: write this README for Capture project

FastAPI extraction service using Azure OpenAI and MCP. Capture reads its bundled configuration locally and does not persist documents, extraction results, or chat history; Pascal owns chat persistence.

**Deploy:** [service-deploy README](../actions/service-deploy/README.md) — GHE registry → Azure Container Apps via `deploy/deploy.sh`.

| Field | Source |
|-------|--------|
| `version` | `VERSION` (semver, bump on release) |
| `revision` | git SHA at Docker build (`IMAGE_TAG`) |
| `/health` | `{"status":"ok","version":"…","revision":"…"}` |

ACA app / image: **`diapason-agent`**.

## UI

Rhapsody loads `agent-widget.js` in the top bar (`#dia-agent-slot`). Tomcat **`DiapasonAgentChatProxyServlet`** proxies `/agent/*` to this service, injects **`Authorization: Bearer`** (instance chat JWT) and `X-Diapason-*` headers. The browser never receives the chat JWT.

Static assets: `static/index.html` (full chat), `static/agent/agent-widget.js` (launcher + iframe). Strings: `locales/en_us.json`, `locales/fr_fr.json` via `GET /api/i18n`.

## Configuration

| Where | How |
|-------|-----|
| Local | `config.json` (gitignored; copy `config.example.json`); keystore via `jwt_keystore.p12` or `JWT_KEYSTORE_P12_B64` |
| Azure | Secrets **`CHAT_CONFIG`** + **`JWT_KEYSTORE_P12_B64`** from Infisical |

Keys: `jwt`, `azure_openai`, `context`, `mcp`, `ui`, `intelligence_contract` — see `config.example.json`.

**Bundled extraction configuration:**

```text
config/catalog.json
config/prompts/*.txt
config/trade.xml
```

The root `config/` directory is included in the Docker image at `/app/config/`.
The catalog and its relative prompt paths are read directly from this directory.
There is no storage account setting, remote catalog path, upload step, or storage permission requirement for Capture.
The existing `intelligence_contract` settings block and API aliases remain for compatibility.

Edit `config/` and rebuild/redeploy the image to change configuration in ACA.
`POST /api/refresh-prompt` (JWT role **`refresh`**) rereads the local catalog and clears the prompt cache; it cannot update files baked into a deployed image.

**Docker image:** `config/` contains extraction content; secrets still arrive through `CHAT_CONFIG` + `JWT_KEYSTORE_P12_B64` at runtime. The root `config.json` is excluded from the image.

**Session correlation:** `session_id` in the form takes precedence over `X-Diapason-Chat-Session`.
Capture echoes the supplied ID, or generates a UUID when neither is supplied, solely for response/trace correlation.
It does not look up sessions, validate ownership of these IDs, or save turns or artifacts.
Authentication and tenant/MCP identity checks still apply. Pascal owns session history and authorization.
Extraction details and tool traces now call the relative local prompt reference `prompt_path`.

## Auth

| Token / header | Purpose |
|----------------|---------|
| `Authorization: Bearer` (chat JWT) | Chat API (`chat` role) |
| `X-Diapason-Mcp-Token` | Diapason API JWT → Fernet MCP bearer |
| `X-Diapason-Mcp-Scope`, `X-Diapason-Mcp-Base-Url` | Tenant context in MCP bearer |
| `X-Diapason-User-Id`, `X-Diapason-Customer-Id` | Caller identity and trace scope |
| `X-Diapason-Locale` | UI strings |
| `X-Diapason-Chat-Session` | Pascal correlation ID (no Capture session storage) |

Required on API routes except `GET /health`, `GET /api/health`, and `GET /api/i18n`. Details: [`dia_jwt/README.md`](dia_jwt/README.md).

## Local run

UI assets: `frontend/` (esbuild; marked, dompurify, vega) → `static/js/` (gitignored). Build before uvicorn; `deploy/deploy.sh` runs the same step.

```bash
source /phantom/mcc/configs/env/nodejs
cd frontend && npm ci && npm run build
cp config.example.json config.json   # edit azure_openai, mcp; enable intelligence_contract; extraction content is in config/
python3 -m dia_jwt create-keystore --path jwt_keystore.p12
# optional: export JWT_KEYSTORE_P12_B64="$(base64 -w0 jwt_keystore.p12)"  # else app reads jwt_keystore.p12
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

- Health: `curl http://localhost:8000/health`
- API health: `curl http://localhost:8000/api/health`

### Tests

```bash
pip install pytest
pytest test/ -v \
  --ignore=test/test_agent_smoke.py \
  --ignore=test/test_tool_route.py \
  --ignore=test/test_source_extract.py
# ignored: legacy live API/app-import tests; source_extract locale filter drift

# Live API (server running):
cp test/test.api.example.json test/test.api.json   # edit agent_url / jwt / diapason_*
python test/test_agent_smoke.py
# or: AGENT_URL=https://… python test/test_agent_smoke.py
```

## Deploy

App image / ACA: `./deploy/deploy.sh <dev|test|prod>` (see below).

**Content** (catalog and prompts): edit `config/`, then rebuild and deploy the app image. Configuration travels with the image when promoting between environments.

```bash
./deploy/deploy.sh <dev|test|prod>
```

Requires env vars already set (CI or source a local file yourself). Exits if `RESOURCE_GROUP` / Infisical creds are missing.

```bash
source ../../research/gh/config/diapason-agent/dev.local.sh   # example local file
az login --service-principal \
  -u "$AZURE_CLIENT_ID" -p "$AZURE_CLIENT_SECRET" --tenant "$AZURE_TENANT_ID"
az account set --subscription "$AZURE_SUBSCRIPTION_ID"
./deploy/deploy.sh dev
```

Infisical path: `/diapason-agent` (env slug = argument):

| Secret | Required | Notes |
|--------|----------|--------|
| `CHAT_CONFIG` | yes | Runtime JSON from `config.example.json`; no storage settings |
| `SMOKE_API_CONFIG` | yes (unless `SKIP_SMOKE=1`) | Same shape as `test/test.api.example.json`. Prefer `diapason_client_id` + `diapason_client_secret` (smoke calls `{diapason_base_url}/api/login`); or static `diapason_api_jwt_token`. `agent_url` overridden by deploy via `AGENT_URL`. |
| `JWT_KEYSTORE_P12_B64` | yes | base64 PKCS#12; ACA secret → env (not in the image). Password in `CHAT_CONFIG.jwt.keystore_password`. Per-env keystores OK. |
| `GHCR_TOKEN` | yes | Shared at Infisical `/` (same as other services) |
| `OTEL_EXPORTER_OTLP_*` | for Loki/Tempo | Shared at Infisical `/` — see [service-deploy OTEL](../actions/service-deploy/README.md#opentelemetry-shared--with-ghcr) |

Deploy calls `otel_aca_append` → ACA `OTEL_SERVICE_NAME=diapason-agent-{dev\|test\|prod}`. Local (`dev.local.sh`): `DEPLOY_ENV=len` → `OTEL_SERVICE_NAME=${APP_NAME}-${DEPLOY_ENV}`.

Post-deploy smoke (unless `SKIP_SMOKE=1`): `/health` + image tag + `test/test_agent_smoke.py` (MCP tools, sessions, chat, IC).
### OpenTelemetry

When `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` / traces endpoints are set, the app exports stdlib logs to Loki and HTTP `/api/*` spans to Tempo. Outbound MCP calls inject W3C `traceparent` so MCP `mcp.tools.call` spans share the same TraceID.

**Capture completion** (span `capture.completion` + one Loki line):

| Signal | Fields |
|--------|--------|
| Correlation | `diapason.customer_id`, `enduser.id`, `diapason.session_id`, `diapason.scope` |
| Outcome | `ai.result_success` |
| Model usage | `gen_ai.usage.*_tokens` on the model span |

No storage URLs or document content are added to completion telemetry. Logs and traces continue through the existing OpenTelemetry provider.

```text
Capture completed success=True
```

```bash
source ../../research/gh/config/diapason-agent/dev.local.sh
# DEPLOY_ENV=len → OTEL_SERVICE_NAME=diapason-agent-len
uvicorn app:app --host 0.0.0.0 --port 8000
```

Grafana Loki: `{service_name="diapason-agent-len"}` (local) or `{service_name="diapason-agent-dev"}` (ACA).

**Dashboards** (import into folder `Diapason / Agent`): [`observability/grafana-agent-mcp-dev.json`](observability/grafana-agent-mcp-dev.json), [`…-test.json`](observability/grafana-agent-mcp-test.json), [`…-prod.json`](observability/grafana-agent-mcp-prod.json). Datasource UIDs: `loki`, `tempo`. Regenerate: `python observability/generate_dashboards.py`.

TraceQL (dev):

```traceql
{resource.service.name="diapason-agent-dev" && name="chat.completion"}
```

GitHub **Deploy** (`.github/workflows/deploy.yml`):

- **dev** (`workflow_dispatch`) — build & push image tagged with the commit SHA, deploy ACA `dev`
- **test** (`workflow_dispatch` + `image_tag`) — promote that SHA (no rebuild); use the SHA from a successful dev run
- **prod** — publish a GitHub Release on the same commit; workflow promotes `github.sha`

Local: `./deploy/deploy.sh dev` (build). Promote: `SKIP_BUILD=1 IMAGE_TAG=<sha> ./deploy/deploy.sh test`.

Redeploy Tomcat after servlet changes (`DiapasonAgentChatProxyServlet`).

## Storage-removal change record

See [BLOB_STORAGE_REMOVAL.md](BLOB_STORAGE_REMOVAL.md) for the complete file inventory, validation results, and existing Terraform-state considerations. The shared Azure Terraform backend is deployment bookkeeping, not Capture document/configuration/session storage; it is unchanged.
