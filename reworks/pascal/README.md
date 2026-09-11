# Pascal

Independent Python project for the Diapason chat agent. LangGraph coordinates the existing AzureOpenAI model and the company's dynamic, stateless MCP calls. The original frontend, prompts, request/response schemas, authentication and session formats are preserved.

The existing `@intelligence-contract` PDF action calls the same Pascal HTTP endpoint. Pascal forwards that request to the separate Capture service. Pascal contains no PDF extraction, contract prompt loader, local Capture compatibility package, or `pypdf` dependency.

## Run locally

Use Python 3.12 or newer and a separate environment for each project. Run from this directory, not its parent. Package configuration deliberately retains the original top-level imports (`dia_jwt`, `settings`, `mcp_context`, etc.).

```bash
python -m venv .venv
# Activate .venv using your shell.
python -m pip install -r requirements-dev.txt
python -m pytest -q
cd frontend
npm ci
npm run build
cd ..
uvicorn pascal.asgi:app --host 0.0.0.0 --port 8000
```

Before starting, supply the existing company `config.json` or `CHAT_CONFIG`, and `jwt_keystore.p12` or `JWT_KEYSTORE_P12_B64`. JWT configuration, storage access, system-prompt Blob, Azure deployment/version/parameters and MCP settings work as before. `config.example.json` preserves the original schema and placeholder values; it is not a working environment configuration.

For the PDF action, retain `intelligence_contract.enabled=true` and set `CAPTURE_URL` to Capture's service base URL. Optional `CAPTURE_TIMEOUT_S` defaults to 600 seconds. This is the only new runtime connection. Capture must trust the same JWT and use the same session storage. See [deployment and routing](docs/DEPLOYMENT.md).

## Layout

| Path | Responsibility |
| --- | --- |
| `src/pascal/agent/graph.py` | Shared model → tools → model graph for JSON and SSE. |
| `src/pascal/agent/` | Original history/prompt context, mentions, per-caller tool discovery and MCP invocation. |
| `src/pascal/api/` | Existing routes and schemas; `capture.py` relays the upload contract. |
| `src/pascal/integrations/capture.py` | Capture connection, forwarded headers and error handling. |
| `src/pascal/commun/` | Unedited company JWT, settings, MCP, Blob/session, locale and telemetry code. |
| `src/pascal/observability/` | Content-free graph spans and HTTP logging on the existing provider. |
| `frontend/`, `static/` | Original Pascal UI. npm builds `static/js/`. |
| `tests/` | Offline graph, API, authentication, relay and persistence tests. |
| `deploy/`, `.github/` | Existing deployment conventions adapted to this project. |

## Build and verify

```bash
python -m build --wheel
docker build -t diapason-pascal:local .
python scripts/update_inventory.py --original ../diapason-agent-main
```

The Docker context is this directory alone. The image installs the package and starts `pascal.asgi:app`; it does not import Capture or a parent checkout. Build the frontend before the image, as in the original deployment.

Seven strict expected failures in `test_source_extract.py` also fail against the original source. They remain visible without changing company source filtering. Optional differential/provenance tests skip when the original checkout is absent; the other tests are standalone.

`scripts/smoke_api.py` is the original live API check, outside pytest collection. Supply `SMOKE_API_CONFIG` or a private `scripts/test.api.json`. The existing `intelligence_contract_pdf` field can point to `tests/fixtures/sample-loan-contract.pdf` to check Capture through Pascal. This check requires company services and writes test sessions.

See [handoff](docs/HANDOFF.md), [user stories and commit tasks](docs/SPRINT.md), [Python inventory](docs/PYTHON_INVENTORY.md), and [omitted original files](docs/OMITTED_ORIGINAL_FILES.md).

Recorded validation: [VERIFICATION.md](docs/VERIFICATION.md).
