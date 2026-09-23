# Capture

Stateless PDF-to-trade XML extraction using a LangGraph workflow, Azure OpenAI, and the Diapason MCP `resolveReferences` tool. Capture has no chat UI, stored sessions, token minting, or runtime blob-storage dependency.

## Run and test

```bash
uv sync --all-groups
cp config.example.json config.local.json  # once; configure registry, Azure OpenAI and MCP
uv run --locked pytest -v                # offline; no live credentials required
bash run.sh --reload                     # localhost:8011; HOST/PORT/PYTHON can override defaults
```

The launcher changes to the project root and uses its virtual environment (Linux/macOS or Windows Git Bash). Extra arguments go to Uvicorn. The equivalent direct command is `uv run uvicorn capture.asgi:app --host 0.0.0.0 --port 8011 --reload`.

```bash
curl -s http://localhost:8011/health
curl -s http://localhost:8011/api/health
# With Capture running and credentials configured:
uv run python tests/smoke_capture.py tests/test.api.local.json
```

Create the live test config from `tests/test.api.example.json`. The smoke runner checks health/build identity, M2M auth, prompt refresh, metadata, missing-token rejection, PDF extraction, XML, and correlation. It obtains an M2M token with scope `ai-capture` and a Diapason API token using the configured credentials. Static `capture_jwt_token` and `diapason_api_jwt_token` are also supported. It does not print tokens or extracted XML.

## Configuration

`CHAT_CONFIG` remains the deployment JSON environment variable for compatibility with existing infrastructure. It takes precedence over `config.local.json`, then `config.json`. It does not imply chat behavior. Required blocks are `registry_url`, `capture`, `azure_openai`, and `mcp`; `m2m` contains optional validator settings.

- M2M issuer comes from `registry_url` -> `services.m2m.url`, with `/token` removed. Capture validates RS256 JWTs using JWKS and requires the exact `ai-capture` scope by default. The issuer identifies the token service, not this application; there is no Capture-local hard-coded issuer or PKCS#12 keystore.
- Prompts and `catalog.json` live in `config/`, bundled into the image. Optional `capture.catalog_file` selects another catalog relative to that directory. Catalog and prompt paths cannot escape it. `POST /api/refresh-prompt` reloads local files and clears prompt caches.
- `capture` is canonical. `intelligence_contract` is a compatibility fallback only when `capture` is absent. New configuration should use `capture`.
- `mcp.default.config_key` is the same Fernet key used by the MCP service. Tenant context headers are encrypted into its outbound bearer token. Capture does not reuse its incoming M2M bearer as MCP authentication.

## HTTP contract

All shared header names live in [`src/capture/http_contract.py`](src/capture/http_contract.py).

| Route | Authorization | Purpose |
|---|---|---|
| `GET /health`, `GET /api/health` | Public | `status`, `build_date`, `revision`, runtime `release`, compatible `version` |
| `GET /api/capture` | M2M `ai-capture` | Enabled flag, trade types, prompt version |
| `POST /api/capture` | M2M plus tenant/MCP headers | Multipart `pdf`, `trade_type`; optional `debug`, `session_id` |
| `POST /api/refresh-prompt` | M2M `ai-capture` | Reload catalog and prompts |

Deprecated GET/POST `/api/skills/intelligence-contract` remain aliases with the same behavior. There are no `/api/chat`, `/api/sessions`, or `/api/auth/*` routes.

| Header | Meaning |
|---|---|
| `Authorization: Bearer ...` | Platform M2M access token |
| `X-Diapason-User-Id`, `X-Diapason-Customer-Id` | Required integer identity fields for extraction |
| `X-Diapason-Mcp-Token` | Required Diapason API token |
| `X-Diapason-Mcp-Scope` | Required integer Diapason scope |
| `X-Diapason-Mcp-Base-Url` | Required Diapason API base URL |
| `X-Diapason-Mcp-Protocol-Version` | Optional fallback when MCP config has no protocol version |
| `X-Diapason-Locale` | Shared locale name; currently does not change XML extraction |
| `X-Diapason-Chat-Session` | Opaque correlation ID; never a session-storage key in Capture |
| `traceparent`, `tracestate` | Optional W3C distributed trace context |

For correlation, a nonempty multipart `session_id` takes precedence over the header; otherwise Capture generates a UUID. API responses echo the correlation header, including handled errors. Browser CORS responses expose it to JavaScript. Direct callers may omit all trace headers.

The result contains `success`, `trade_xml`, `view_entity`, `menu_name`, `trade_type`, `extracted_field_count`, `message`, and `warnings`. `tool_trace` is removed from both routes; use OpenTelemetry for timings and tool observability. `debug=true` still explicitly returns extraction/resolver diagnostics, including document-derived content; that content is never added to Capture spans.

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

Capture extracts incoming W3C context and injects the outgoing MCP client span into HTTP headers. The current Diapason MCP implementation already extracts those headers. Pascal can join the trace by injecting context into its Capture request; a UI without instrumentation starts a new Capture trace. Invalid trace headers are ignored by the propagator. No MCP protocol change is required.

Spans record errors without exception text/stack traces, XML, PDF text, prompts, authentication headers, or tool arguments. A resolver `success=false` marks the workflow and Capture request as failed even when the HTTP result is 200. `diapason.*` identity attributes stay for company dashboard compatibility. LangSmith graph tracing remains disabled around document processing.

Your trace-only Jaeger setup remains supported:

```bash
# .env.local
OTEL_SERVICE_NAME=ai-capture-local
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://localhost:4318/v1/traces
OTEL_BSP_SCHEDULE_DELAY=500
```

```bash
uv run --env-file .env.local uvicorn capture.asgi:app --host 0.0.0.0 --port 8011 --reload
# Or: bash run.sh --env-file .env.local --reload
```

Platform deployment can use `OTEL_EXPORTER_OTLP_ENDPOINT` as a base (Capture appends `/v1/traces` and `/v1/logs`), `OTEL_BEARER_TOKEN`, and `OTEL_ORG_ID` (logs). Signal-specific endpoint URLs are used as-is; a traces-only setting does not enable logs. Signal-specific `*_HEADERS` override common `OTEL_EXPORTER_OTLP_HEADERS`, which override platform credentials. Legacy `OTEL_EXPORTER_OTLP_TOKEN` and `OTEL_EXPORTER_OTLP_SCOPE_ORG_ID` remain fallbacks. Endpoint behavior follows the [OpenTelemetry HTTP exporter configuration](https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/).

## Deployment

```bash
bash deploy/deploy.sh dev
SKIP_BUILD=1 IMAGE_TAG=<tested-sha> bash deploy/deploy.sh staging
```

The shared `actions/service-deploy/aca-lib.sh` owns build/push and ACA rollout. Terraform owns the app shell and `CHAT_CONFIG` secret. App/image and Infisical secret path are `ai-capture` and `/ai-capture`. The container keeps port 8000; the deploy script accepts `PORT`. The local launcher defaults to 8011, independently of the agent's 7702 port.

Pushes to `main` and manual dev runs build an image; staging and published releases promote an existing SHA. Deployment concurrency is serialized per environment. `BUILD_DATE` and `GIT_REVISION` are baked into the image, and `RELEASE_TAG` is supplied at runtime (empty in dev/staging). The `VERSION` file/package version is retained for compatibility. Post-deploy checks verify health and image tag, then run `tests/smoke_capture.py` using Infisical `SMOKE_API_CONFIG`, unless smoke is explicitly skipped.

The complete upstream comparison, application decisions, trace assessment, and edit ledger are in [`docs/upstream-sync/README.md`](docs/upstream-sync/README.md).
