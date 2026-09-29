# ai-capture

FastAPI app: PDF-to-trade-XML extraction, LangGraph workflow, Azure OpenAI, Diapason MCP `resolveReferences` tool. Stateless — no chat UI, no stored sessions, no token minting, no runtime blob-storage dependency.

**Deploy:** Terraform owns the Azure shell (`apps/ai/ai-capture`); GitHub Actions `deploy/deploy.sh` builds/pushes the image and rolls the ACA revision (same pattern as m2m / ai-diapason-mcp / ai-agent). See [service-deploy HOW-IT-WORKS](../actions/service-deploy/HOW-IT-WORKS.md).

| Field | Source |
|-------|--------|
| `build_date` | Docker bake (`BUILD_DATE`) |
| `revision` | git SHA at Docker build (`GIT_REVISION`) |
| `release` | ACA `RELEASE_TAG` (prod release only; else `""`) |
| `version` | `VERSION` file / package version (compatibility) |
| `/health`, `/api/health` | `{"status":"ok","version":"…","build_date":"…","revision":"…","release":"…"}` |

ACA app / image: **`ai-capture`**.

## Configuration

| Where | How |
|-------|-----|
| Local | `config.local.json` (preferred) or `config.json` (both gitignored); copy from `config.example.json` |
| Azure | Terraform-rendered **`CAPTURE_CONFIG`** on ACA (secret `capture-config`; full capture JSON including **`registry_url`**) — not Infisical |

`CAPTURE_CONFIG` takes precedence over `config.local.json`, then `config.json`. Required blocks: `registry_url`, `capture`, `azure_openai`, `mcp`. `capture` is canonical; `intelligence_contract` is a fallback only when `capture` is absent. `mcp.default.config_key`: same Fernet key as the MCP service, encrypts tenant context into its outbound bearer token.

**Baked into the image** (change → rebuild / redeploy):

```
config/catalog.json
config/prompts/*.txt
```

Optional `capture.catalog_file` selects another catalog relative to `config/`; paths can't escape that directory. `POST /api/refresh-prompt` (m2m Bearer, scope **`ai-capture`**) reloads those files from disk.

**Docker image:** no secrets; `CAPTURE_CONFIG` at runtime (must include `registry_url`). No Blob container, no session storage.

## HTTP contract

All shared header names live in [`src/capture/http_contract.py`](src/capture/http_contract.py).

| Route | Authorization | Purpose |
|-------|----------------|---------|
| `GET /health`, `GET /api/health` | Public | `status`, `build_date`, `revision`, runtime `release`, compatible `version` |
| `GET /api/capture` | M2M `ai-capture` | Enabled flag, trade types, prompt version |
| `POST /api/capture` | M2M plus tenant/MCP headers | Multipart `pdf`, `trade_type`; optional `debug`, `session_id` |
| `POST /api/refresh-prompt` | M2M `ai-capture` | Reload catalog and prompts |

Deprecated GET/POST `/api/skills/intelligence-contract` are aliases with the same behavior. No `/api/chat`, `/api/sessions`, or `/api/auth/*` routes.

## Auth

Platform **m2m** access tokens (RS256 via JWKS). Expected **`iss`** / JWKS derived from **`registry_url`** in config → `services.m2m.url` (strip `/token`).

| Token / header | Purpose |
|----------------|---------|
| `Authorization: Bearer` (m2m access token) | API access; must include scope **`ai-capture`**; `iss` must match registry-derived issuer |
| `X-Diapason-User-Id`, `X-Diapason-Customer-Id` | Required identity for extraction |
| `X-Diapason-Mcp-Token` | Required Diapason API token |
| `X-Diapason-Mcp-Scope` | Required Diapason scope |
| `X-Diapason-Mcp-Base-Url` | Required Diapason API base URL |
| `X-Diapason-Mcp-Protocol-Version` | Optional fallback when MCP config has no protocol version |
| `X-Diapason-Locale` | Shared locale name; doesn't change XML extraction |
| `X-Diapason-Chat-Session` | Opaque correlation ID only; not a session key |
| `traceparent`, `tracestate` | Optional W3C trace context |

Required on API routes except `GET /health` and `GET /api/health`.

Correlation: nonempty multipart `session_id` wins over the header; otherwise Capture generates a UUID. Responses echo it, including on errors, and expose it to browser CORS clients. Direct callers may omit trace headers entirely.

Result fields: `success`, `trade_xml`, `view_entity`, `menu_name`, `trade_type`, `extracted_field_count`, `message`, `warnings`. `tool_trace` is removed; use OpenTelemetry for tool timings. `debug=true` returns extraction/resolver diagnostics (document-derived content), never added to spans.

## Local run

```bash
uv sync --all-groups
cp config.example.json config.local.json  # once; configure registry_url, azure_openai and mcp
uv run --locked pytest -v                 # offline; no live credentials required
./run.sh --reload                         # PORT=7703 by default
```

The equivalent direct command is `uv run uvicorn capture.asgi:app --host 0.0.0.0 --port 7703 --reload`.

- Health: `curl -s http://localhost:7703/health`
- API health: `curl -s http://localhost:7703/api/health`

### Export and content evaluation

Export one PDF's raw API response and XML with the standalone `scripts/capture_pdf.py`. It follows the configuration, authentication and request format used by `tests/test_integ.py`; the existing integration script remains unchanged. Evaluate reviewed PDF/XML datasets with `scripts/evaluate.py`; `validate` and `score` work entirely offline, while `run` explicitly calls the configured service. See [the evaluation guide](evals/README.md) for configuration, ground truth, examples, repeat runs and baseline reports.

```bash
# Live export: requires a reachable service and its credentials.
export INTEG_APP_CONFIG="$(cat tests/integ.app.pascal-dev.json)"
export INTEG_PLATFORM_CONFIG="$(cat tests/integ.platform.local.json)"
uv run --locked python scripts/capture_pdf.py

# Optional overrides; a case-ID output directory is convenient for evaluation.
uv run --locked python scripts/capture_pdf.py --pdf path/to/contract.pdf --trade-type iamLoan --output evals/responses/loan-001

# Offline grading: uses saved responses without API calls or credentials.
uv run --locked python scripts/evaluate.py score evals/example/dataset.json --responses evals/example/responses --output evals/runs/offline-example
```

Without overrides, the exporter reads the PDF and trade type from the integration config and creates a fresh directory under `evals/responses/`. It authenticates and sends one capture request with `debug=true`. Evaluation code lives in the repository-level `evals/` package, outside `src/capture`, and is excluded from both the application wheel and Docker image.

Run offline software/grader tests on every PR. Run fresh content evaluations from a connected developer machine, or a separate manually triggered/scheduled CI job with access to the service, credentials and reviewed dataset. Use those evaluations for prompt/model/extraction changes and before release; regrading saved responses does not test a new prompt. The current CI runs offline tests; no live content-evaluation job is configured.

### Tests

```bash
uv run --locked pytest -v
```

```bash
# Live integ (server running; not part of deploy):
cp tests/integ.platform.example.json tests/integ.app.example.json …

export INTEG_APP_CONFIG="$(cat tests/integ.app.pascal-dev.json)"
export INTEG_PLATFORM_CONFIG="$(cat tests/integ.platform.local.json)"
uv run --locked python tests/test_integ.py
```

Checks health/build identity, M2M auth, prompt refresh, metadata, missing-token rejection, PDF extraction, XML, correlation. Obtains an M2M token with scope `ai-capture` and a Diapason API token from the configured credentials. Static `capture_jwt_token` and `diapason_api_jwt_token` are also supported.

## Deploy

App image / ACA roll: `bash deploy/deploy.sh <dev|staging|prod>` (Terraform shell must already exist). Catalog/prompt changes ship with the image.

```bash
bash deploy/deploy.sh dev
SKIP_BUILD=1 IMAGE_TAG=<tested-sha> bash deploy/deploy.sh staging
```

Requires Azure + GHE registry env (CI or source a local file). Infisical is optional for telemetry configuration.

| Secret / env | Required | Notes |
|--------------|----------|-------|
| `CAPTURE_CONFIG` | yes (TF → ACA `capture-config`) | Full capture JSON including required **`registry_url`** (openai, mcp, …). Do **not** rely on a separate `REGISTRY_URL` env. Not in Infisical. |
| `INTEG_PLATFORM_CONFIG` | for integ Action | GitHub Environment secret (TF). Shape: `tests/integ.platform.example.json` (capture/registry/m2m). |
| `INTEG_APP_CONFIG` | for integ Action | GitHub Environment secret (**manual**). Shape: `tests/integ.app.example.json` (Diapason + Capture PDF/trade type). |
| `GITHUB_TOKEN` | yes | Image push / pull |
| `OTEL_*` | TF bootstrap + `otel_aca_append` | Path A: Infisical `/platform` endpoint/org; bearer secret on ACA |
| `RELEASE_TAG` | prod release only | Set on ACA; appears in `/health.release` |

Pushes to `main` and manual dev runs build an image; staging and published releases promote an existing SHA. `BUILD_DATE` and `GIT_REVISION` are baked into the image; `RELEASE_TAG` is supplied at runtime (empty in dev/staging).

## Traces and logs

Logger and instrumentation scope: `capture` (child loggers `capture.workflow` and `capture.mcp`). Default service name: `ai-capture`, override with `OTEL_SERVICE_NAME`.

```text
caller span (optional)
  http.request [SERVER]
    capture.request [identity, correlation, result; covers extraction]
      ai.capture.workflow
        ai.capture.validate
        ai.capture.extract
          ai.capture.model [CLIENT; model name and token usage]
        ai.capture.resolve
          mcp.request [CLIENT; method, tool, server ID/host, HTTP status]
            MCP service spans (when its exporter is enabled)
```

Capture extracts incoming W3C context and injects the outgoing MCP client span into HTTP headers; the Diapason MCP implementation already extracts them. Pascal can join the trace by injecting context into its request; an uninstrumented UI just starts a new trace. Invalid trace headers are ignored. No MCP protocol change required.

Spans record errors without exception text/stack traces, XML, PDF text, prompts, auth headers, or tool arguments. A resolver `success=false` marks the workflow and request failed even on HTTP 200. `diapason.*` identity attributes stay for dashboard compatibility. LangSmith graph tracing stays disabled around document processing.

`OTEL_EXPORTER_OTLP_ENDPOINT` is the base (Capture appends `/v1/traces` and `/v1/logs`), plus `OTEL_BEARER_TOKEN` and `OTEL_ORG_ID` (logs). Signal-specific endpoint URLs are used as-is — a traces-only setting doesn't enable logs. Signal-specific `*_HEADERS` override common `OTEL_EXPORTER_OTLP_HEADERS`, which override platform credentials. Legacy `OTEL_EXPORTER_OTLP_TOKEN` / `OTEL_EXPORTER_OTLP_SCOPE_ORG_ID` remain fallbacks. See [OpenTelemetry OTLP exporter configuration](https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/).

To verify traces, logs, and metrics locally:

```bash
docker run -d \
  --name otel-lgtm \
  -p 3000:3000 \
  -p 4317:4317 \
  -p 4318:4318 \
  docker.io/grafana/otel-lgtm:latest
```
Grafana UI: http://localhost:3000 (User: admin / Password: admin)

```bash
# .env.local
OTEL_SERVICE_NAME=ai-capture-local
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
OTEL_BSP_SCHEDULE_DELAY=500
```

```bash
uv run --env-file .env.local uvicorn capture.asgi:app --host 0.0.0.0 --port 7703 --reload
# Or: bash run.sh --env-file .env.local --reload
```