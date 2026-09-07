# Capture

`capture` is the standalone successor to the legacy “intelligence contract” code. It is a
deterministic LangGraph workflow deployed as its own Azure Container App (ACA), with two protocol
front doors over one implementation:

- Classic Diapason and Pascal’s explicit `/capture` or `@capture` action use the compatibility HTTP
  path `GET|POST /api/skills/intelligence-contract`.
- Pascal’s model can call the `capture` MCP tool at `/mcp` after the user has supplied an explicit
  `trade_type` and one PDF.

No existing Diapason UX, agent, or backend files are changed by this rework.

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

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp config.example.json config.json
```

For local prompts, set `capture.catalog_backend` to `filesystem`. Then provide the keystore as
`JWT_KEYSTORE_P12_B64` or `jwt_keystore.p12` and run:

```bash
uvicorn capture.asgi:app --reload --port 8000
pytest
```

Health endpoints are unauthenticated: `/health` is liveness and `/ready` confirms the catalog loaded.

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

The deployment follows the legacy `diapason-agent`/`diapason-mcp` flow: shared `aca-lib.sh`, shared
ACA environment and registry, Terraform-managed app identity/RBAC, Infisical secrets, build-on-dev,
and immutable image promotion to test/prod.

```bash
bash deploy/deploy-config.sh dev
bash deploy/deploy.sh dev
bash deploy/deploy.sh test    # IMAGE_TAG=<tested dev SHA>
```

`CAPTURE_CONFIG` and `JWT_KEYSTORE_P12_B64` are ACA secret references. The system-assigned identity
has read-only access to the existing `agent-config` container. The deployment keeps at least one
replica to avoid putting a PDF/LLM cold start on the synchronous UX path.

## Project documentation

- [`SPRINT.md`](SPRINT.md) — user stories, acceptance criteria, tasks, risks, and decisions
- [`docs/architecture.md`](docs/architecture.md) — boundaries and runtime design
- [`docs/integration.md`](docs/integration.md) — classic UI, Pascal action, and Pascal MCP contracts
- [`docs/security.md`](docs/security.md) — compatibility controls and known follow-ups
- [`docs/observability.md`](docs/observability.md) — Loki/Tempo settings and spans
- [`docs/research.md`](docs/research.md) — legacy findings and current external guidance
- [`docs/proposed-improvements.md`](docs/proposed-improvements.md) — deliberately unimplemented ideas

