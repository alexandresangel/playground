# Capture

Independent Python service for intelligence-contract. LangGraph executes the original sequence: validate PDF → extract trade XML with AzureOpenAI → call the existing MCP `resolveReferences` tool → shape the original result and session artifacts.

Capture owns extraction for both the classic Diapason UI and Pascal's existing `@intelligence-contract` PDF action. It contains no chat agent or Pascal frontend.

## Run locally

Use Python 3.12 or newer and a separate environment from Pascal. Run from this directory.

```bash
python -m venv .venv
# Activate .venv using your shell.
python -m pip install -r requirements-dev.txt
python -m pytest -q
uvicorn capture.asgi:app --host 0.0.0.0 --port 8001
```

Supply the existing company `config.json` or `CHAT_CONFIG`, and `jwt_keystore.p12` or `JWT_KEYSTORE_P12_B64`. Keep the original JWT issuer/password/revocation settings, MCP config, Azure deployment/version/parameters and Blob/session settings. Set the existing `intelligence_contract.enabled` flag to `true`. `config.example.json` is the unchanged original schema; its resource names and credentials are placeholders.

Runtime reads the existing `skills/intelligence-contract/catalog.json` and prompt Blob keys from `storage.config_container`. `config/` holds the original source asset text. Upload those assets separately; there is no local runtime fallback and no Pascal system-prompt initialization.

## HTTP contract

| Endpoint | Behavior |
| --- | --- |
| `GET /api/skills/intelligence-contract` | Existing enabled/trade-types/prompt-version metadata; chat role required. |
| `POST /api/skills/intelligence-contract` | Multipart `pdf`, `trade_type`, optional `debug` and `session_id`; original identity/MCP headers and result. |
| `POST /api/refresh-prompt` | Refresh Capture catalog and clear its prompt cache; existing refresh role required. |
| `/health`, `/api/health` | Build health/version/revision. |
| Existing `/api/auth/*` routes | Same company token administration contract. |

Public URLs, localized messages, tool-trace labels, Blob keys and `skill_run` fields retain their legacy names because they are company interfaces. Internally the workflow is named Capture. Form `session_id` takes precedence over `X-Diapason-Chat-Session`, as before. Capture validates scope, writes one extraction turn with the original artifacts, and returns the session header.

## Layout and verification

| Path | Responsibility |
| --- | --- |
| `src/capture/workflow/` | Typed graph, PDF/XML extraction, prompt cache and field counting. |
| `src/capture/api/` | Extraction/auth adapters, health and middleware. |
| `src/capture/common/` | Unedited company JWT, MCP, settings, Blob/session, locale and telemetry code. |
| `src/capture/observability/` | Content-free workflow spans on the existing provider. |
| `config/` | Original catalog, XML reference and extraction prompts. |
| `tests/` | Offline PDF/model/resolver, refresh, API, JWT/scope and persistence checks. |
| `deploy/`, `.github/` | Dedicated ACA using the existing company helper/environment. |

```bash
python -m build --wheel
docker build -t diapason-capture:local .
python scripts/update_inventory.py --original ../diapason-agent-main
```

The image uses only this directory and starts `capture.asgi:app` on port 8000. Package configuration retains original top-level company imports without modifying `dia_jwt`.

`scripts/smoke_api.py` checks deployed Capture. Supply the existing `SMOKE_API_CONFIG` format, use Capture's URL as `agent_url` (or `AGENT_URL`), and provide a PDF and trade type. `SKIP_IC_SMOKE=1` selects metadata-only checks. Capture's smoke does not call chat/session CRUD. Actual model, MCP, Blob and host acceptance requires the company environment.

See [deployment and routing](docs/DEPLOYMENT.md), [handoff](docs/HANDOFF.md), [user stories and commit tasks](docs/SPRINT.md), [Python inventory](docs/PYTHON_INVENTORY.md), and [omitted original files](docs/OMITTED_ORIGINAL_FILES.md).

Recorded validation: [VERIFICATION.md](docs/VERIFICATION.md).
