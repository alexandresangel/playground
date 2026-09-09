# Capture

`capture` is the standalone successor to the legacy “intelligence contract” code. It is a
deterministic LangGraph workflow packaged for its own Azure Container App (ACA), with two protocol
front doors over one implementation:

- Classic Diapason and Pascal’s explicit `/capture` or `@capture` action use the compatibility HTTP
  path `GET|POST /api/skills/intelligence-contract`.
- Pascal’s model can call the `capture` MCP tool at `/mcp` after the user has supplied an explicit
  `trade_type` and one PDF.

No original Diapason UX, agent, or backend files are changed. No cloud deployment has been performed.
The separate Pascal rework has earlier integration-only frontend changes documented in its provenance;
this refinement makes no frontend/static edits.

## What is preserved

- The bundled catalog, seven legacy prompt files, default temperature (`0.5`), PDF text extraction,
  free-form XML extraction, caller-controlled `trade_type`, and public response fields.
- RS256 validation from the same PKCS#12 key, issuer `diapason-agent`, accepted roles `chat|admin`,
  revocation checks, user/customer headers, and JWT `customer_id` matching.
- Per-request `X-Diapason-Mcp-Token`, `X-Diapason-Mcp-Scope`, and
  `X-Diapason-Mcp-Base-Url`. The names remain for compatibility; Capture uses them to call the
  Diapason REST endpoint directly and does not call an MCP server.
- OTLP/HTTP export variables used by the existing Loki/Tempo deployment.

## Workflow

```text
validate_input -> extract_text -> select_prompt -> llm_extract
               -> normalize_xml -> resolve_references -> emit_result
```

`resolve_references` calls
`POST {X-Diapason-Mcp-Base-Url}/api/v2/importData/resolveReferences` directly. Request credentials
are passed as LangGraph runtime context, not persisted in graph state. The graph intentionally has no
checkpointer because its state contains contract text and XML.

## Run locally

Requirements: Python 3.12, a compatible PKCS#12 key, and either Azure CLI access to the prompt blob
container or the bundled filesystem catalog.

```powershell
uv sync --locked --extra dev --extra mcp
uv run --locked --extra dev pytest
uv run --locked --extra dev ruff check src tests scripts
```

For local prompts, set `capture.catalog_backend` to `filesystem`. Then provide the keystore as
`JWT_KEYSTORE_P12_B64` or `jwt_keystore.p12` and run:

```bash
uv run uvicorn capture.main:create_app --factory --port 8000 --no-access-log
```

Health endpoints are unauthenticated: `/health` is liveness and `/ready` confirms the catalog loaded.

Use `config.example.json` as the shape for `CAPTURE_CONFIG` or ignored local `config.json`.
Azure defaults to the local `AsyncOpenAI` v1 client; an older dated endpoint requires explicit
`api_mode=azure_dated` and `api_version`. Set `mcp.enabled=false` for HTTP-only operation; the base
package can be installed without the optional `mcp` extra. See [architecture](docs/architecture.md).

## HTTP contract

`POST /api/skills/intelligence-contract` remains multipart form data:

- `pdf`: required PDF upload
- `trade_type`: required string selected by the user/caller
- `debug`: optional legacy boolean string
- `session_id`: optional; echoed in `X-Diapason-Chat-Session` when supplied

Required headers are `Authorization: Bearer <agent JWT>`, `X-Diapason-User-Id`,
`X-Diapason-Customer-Id`, `X-Diapason-Mcp-Token`, `X-Diapason-Mcp-Scope`, and
`X-Diapason-Mcp-Base-Url`.

`GET` on the same path returns the trade types used by the existing composer. See
[`docs/integration.md`](docs/integration.md) for all three invocation paths.

## Deployment

The prepared deployment artifacts follow the legacy `diapason-agent`/`diapason-mcp` flow: shared `aca-lib.sh`, shared
ACA environment and registry, Terraform-managed app identity/RBAC, Infisical secrets, build-on-dev,
and immutable image promotion to test/prod. Platform must approve state ownership, secrets/RBAC,
actual probes/network settings and the private helper before executing the commands below.

```bash
bash deploy/deploy-config.sh dev
bash deploy/deploy.sh dev
bash deploy/deploy.sh test    # IMAGE_TAG=<tested dev SHA>
```

`CAPTURE_CONFIG` and `JWT_KEYSTORE_P12_B64` are ACA secret references. The system-assigned identity
has read-only access to the existing `agent-config` container. The deployment keeps at least one
replica to avoid putting a PDF/LLM cold start on the synchronous UX path.

## Source layout

All Python implementation lives in `src/capture`: `workflow` contains extraction and orchestration,
`adapters` owns external clients, `api` exposes HTTP/MCP, and `observability` owns telemetry/events.
Small auth/config/compatibility modules stay at the root. Common files are intentionally duplicated
inside Pascal at matching paths; see [reuse and maintenance](docs/reuse.md).

## Project documentation

- [`SPRINT.md`](SPRINT.md) — user stories, acceptance criteria, tasks, risks, and decisions
- [`docs/architecture.md`](docs/architecture.md) — boundaries and runtime design
- [`docs/integration.md`](docs/integration.md) — classic UI, Pascal action, and Pascal MCP contracts
- [`docs/security.md`](docs/security.md) — compatibility controls and known follow-ups
- [`docs/observability.md`](docs/observability.md) — Loki/Tempo settings and spans
- [`docs/research.md`](docs/research.md) — legacy findings and current external guidance
- [`docs/proposed-improvements.md`](docs/proposed-improvements.md) — deliberately unimplemented ideas
- [`docs/provenance.md`](docs/provenance.md) — retained, refactored, added and removed code
- [`docs/verification.md`](docs/verification.md) — current local evidence and external gates
- [`docs/deployment.md`](docs/deployment.md) — locked image, platform prerequisites and safe rollout
