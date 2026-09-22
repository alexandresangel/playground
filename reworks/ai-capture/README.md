# Capture

Independent, stateless PDF-to-trade-XML extraction service built with FastAPI and LangGraph.
Capture replaces the former intelligence-contract skill. It extracts XML with Azure OpenAI
and resolves references through Diapason MCP. It does not store sessions/documents or import trades.

The complete upstream review is in [docs/upstream-port.md](docs/upstream-port.md), with a
[file inventory](docs/upstream-file-inventory.csv) covering the supplied agent snapshots.

## Local run

From this repository root (Python 3.12+, uv):

```bash
cp config.example.json config.local.json
# Set registry_url, azure_openai and mcp.default.
uv sync --locked --group dev
uv run --locked uvicorn capture.asgi:app --host 0.0.0.0 --port 8011
```

Configuration precedence: `CHAT_CONFIG` JSON > `config.local.json` > `config.json`.
`registry_url` is required in that JSON; a separate `REGISTRY_URL` environment variable
is not a runtime substitute. Registry discovery happens at startup.

Catalog and prompts live in `config/catalog.json` and `config/prompts/` and are bundled
in the Docker image. Changes ship with an image rebuild. `POST /api/refresh-prompt`
reloads the current files and clears the prompt cache. No Azure Blob account is required.

## Authentication and API

Capture validates platform **M2M** Bearer access tokens using **RS256 and JWKS**.
The issuer is derived from `registry_url` -> `services.m2m.url` (removing `/token`);
the default JWKS endpoint is `/.well-known/jwks.json` on that issuer.
Tokens need `exp`, `iat`, `iss`, `client_id` and the exact **`ai-capture`** scope.
The service does not mint/revoke tokens and no longer uses `dia_jwt` or a PKCS#12 keystore.

Provision the calling M2M client with `ai-capture`. For an explicit transition using
existing agent clients, `m2m.required_scope` can be set to `ai-agent`; the default remains
`ai-capture`. The same required scope authorizes extraction metadata and prompt refresh.
Use `m2m.allow_http: true` only for a local HTTP issuer. Other optional M2M settings are
`jwks_url`, `jwks_cache_seconds` (600), `jwks_max_stale_seconds` (3600) and
`clock_skew_seconds` (60; zero is supported). Unknown key IDs trigger a refresh;
a bounded last-good JWKS cache tolerates temporary outages. A cold/unusable cache rejects tokens.

| Route | Authentication | Purpose |
|---|---|---|
| `GET /health`, `GET /api/health` | Public | Status, version, revision |
| `GET /api/capture` | M2M | Supported trade types and prompt version |
| `POST /api/capture` | M2M + tenant/MCP headers | Multipart `pdf`, `trade_type`; optional `debug`, `session_id` |
| `POST /api/refresh-prompt` | M2M | Reload bundled catalog/prompts |

The deprecated `/api/skills/intelligence-contract` GET/POST aliases remain available.
The independent Capture API and its existing response shape are unchanged.

POST extraction requires these headers in addition to `Authorization: Bearer <access_token>`:

| Header | Purpose |
|---|---|
| `X-Diapason-User-Id`, `X-Diapason-Customer-Id` | Integer tenant/user identifiers supplied by the trusted caller/proxy |
| `X-Diapason-Mcp-Token` | Diapason API token encrypted into the MCP bearer |
| `X-Diapason-Mcp-Scope`, `X-Diapason-Mcp-Base-Url` | Diapason context for MCP |
| `X-Diapason-Locale` | Optional locale |
| `X-Diapason-Chat-Session` | Optional correlation ID, echoed back; no session persistence |

M2M identifies the calling client, not an end-user tenant. As in `ai-agent`, the trusted
proxy supplies tenant headers; Capture no longer binds them to a legacy JWT customer claim.

## Tests

```bash
uv sync --locked --group dev
uv run --locked --no-sync python -m pytest -q
```

Tests run offline with signed RSA tokens, mocked registry/JWKS, model and MCP responses,
and a separate local HTTP service process. The deployment tests stub the shared deploy
library and make no Azure calls. The real smoke runner is deliberately not collected by pytest:

```bash
cp tests/test.api.example.json tests/test.api.json
# Set the Capture URL, M2M credentials and Diapason credentials.
uv run --locked python tests/smoke_capture.py
```

Smoke accepts `SMOKE_API_CONFIG` JSON instead of a file. `CAPTURE_URL` overrides
`capture_url`; M2M client credentials use HTTP Basic client_credentials with no requested
scope, matching AIProxy. A static `capture_access_token` is also supported. Set
`m2m_token_url` or `registry_url` for token discovery. Smoke-only environment overrides:
`M2M_CLIENT_ID`, `M2M_CLIENT_SECRET`, `M2M_TOKEN_URL`, `REGISTRY_URL`.

With `capture_pdf` set, smoke calls Azure OpenAI and MCP and checks the resolved XML and
correlation ID. Relative PDF paths are resolved beside the smoke config (under `tests/`
for `SMOKE_API_CONFIG`). Omit `capture_pdf` to check only health, auth and catalog.

## Deployment

```bash
bash deploy/deploy.sh dev
SKIP_BUILD=1 IMAGE_TAG=<dev-commit-sha> bash deploy/deploy.sh staging
```

App/image: **`ai-capture`**. Environments: **dev / staging / prod**. The workflow retains
manual dev deployment, promotes a supplied SHA to staging, and promotes a published
release commit to prod. It does not introduce automatic deployment on push.

The platform Terraform project must provision Capture's ACA shell, image-pull credentials
and `CHAT_CONFIG` secret first, following the agent's external-Terraform model. These
resources are not created by this repository. The shared `aca-lib.sh` must be available
at `../actions/service-deploy` or `ACTIONS_SERVICE_DEPLOY`; Azure and registry credentials
are required. `RESOURCE_GROUP` defaults to `diapason-<environment>`.

Only `CHAT_CONFIG` is needed for runtime configuration; no JWT keystore or Blob secrets.
Infisical path `/ai-capture` provides `SMOKE_API_CONFIG` when smoke is enabled. Shared
OpenTelemetry settings are re-seeded through the deploy library when Infisical is
configured; the service name is `ai-capture-<environment>`. Health and deployed-image
checks still run when API smoke is skipped (`SKIP_SMOKE=1` or no Infisical credentials).
The deployment runner needs uv for the Capture smoke check; GitHub Actions sets it up.

The Docker image uses `uv.lock`, includes the Capture catalog/prompts and starts
`capture.asgi:app` on `PORT` (default 8000). Build metadata comes from `VERSION` and the
`APP_VERSION`/`GIT_REVISION` build arguments. Configuration, local test credentials and
old local keystores are excluded from the image.
