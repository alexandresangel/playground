# Capture

Capture is a FastAPI service that extracts trade XML from a PDF with Azure OpenAI,
then calls the Diapason MCP server to resolve references. Pascal owns the chat UI
and history. Capture has no Blob Storage dependency or chat-session persistence.

## Local setup

Run these commands from the `ai-capture` root in Bash (Linux/macOS/WSL).
Use Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/)
0.12.15 or newer; CI and Docker pin uv 0.12.15.

Check `uv --version` first and install/upgrade uv using the linked instructions
if necessary. An older uv installation will fail the project's version check.

```bash
# Initialize and activate the virtual environment.
uv venv --python 3.12 .venv
source .venv/bin/activate

# Install Capture and its development dependencies from uv.lock.
uv sync --locked

# Run the offline test suite.
python -m pytest

# Create local configuration if it does not already exist.
test -f config.json || cp config.example.json config.json
```

You can also create the environment with `python3.12 -m venv .venv`, then activate
it and run `uv sync --locked`. Activation is optional when using `uv run`; for
example, `uv run --locked python -m pytest` runs the same tests.

Dependencies are declared in `pyproject.toml`; `uv.lock` records their resolved
versions. There are no `requirements*.txt` files. After an intentional dependency
change, run `uv lock`, `uv sync --locked`, and the tests, then commit both project
metadata and the updated lockfile. Use `uv add PACKAGE` or `uv add --dev PACKAGE`
to add dependencies, and `uv build --wheel` to build the package.

## Configure Capture

Local settings come from the gitignored `config.json`. In ACA, `CHAT_CONFIG`
contains the same JSON and takes precedence over the local file. The example
contains only `jwt`, `capture`, `azure_openai`, and `mcp.default`.

| Setting | Purpose |
| --- | --- |
| `jwt.keystore_password` | Password used to create/read the local PKCS#12 keystore. |
| `jwt.revoked` | Initial JWT revocation entries; normally empty locally. |
| `capture.enabled` | Enable extraction; `true` in the example. |
| `capture.cache_ttl_seconds` | Cache duration for local prompt text. |
| `capture.max_pdf_bytes` | Maximum PDF size; 10 MiB by default. |
| `capture.view_entity` | Fallback entity when the catalog does not specify one. |
| `capture.temperature` | Model temperature for extraction. |
| `azure_openai.endpoint` | Azure OpenAI resource endpoint. |
| `azure_openai.api_key` | Resource API key. |
| `azure_openai.deployment` | Model deployment name in that resource. |
| `azure_openai.api_version` | Azure API version used by the client. |
| `mcp.default.server_url` | URL of the separate Diapason MCP service. |
| `mcp.default.config_key` | Fernet key shared with the MCP service's `MCP_CONFIG_KEY`. |

For existing deployments, `intelligence_contract` remains a fallback for the
`capture` block. If both are present, `capture` takes precedence. Persona/UI
settings, extra MCP servers, chat tool-loop limits, and chat pricing settings are
not part of the Capture configuration.

Capture listens on port **8000** in the examples. Set the MCP URL to your actual
separate MCP service, for example `http://127.0.0.1:8001/mcp` for local use. The
current `config.example.json` placeholder uses port 8000 and must be changed if
Capture occupies that port. Capture does not host `/mcp`.

Generate a Fernet key with:

```bash
uv run --locked python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set the same key in `config.json` under `mcp.default.config_key` and in the MCP
server's `MCP_CONFIG_KEY`. If using an existing MCP service, use its existing
shared key; changing only Capture's key will prevent the MCP server from decrypting
requests.

For the company document-analyzer setup, set `azure_openai.endpoint` to
`https://diapason-document-analyzer.openai.azure.com/` and copy **KEY 1** from the
[Azure portal resource keys page](https://portal.azure.com/#@mydiapason.com/resource/subscriptions/55c22f82-5b11-46b0-afce-8e1cd2c422cc/resourceGroups/document-analyzer/providers/Microsoft.CognitiveServices/accounts/document-analyzer/cskeys)
into `azure_openai.api_key`. Also set the actual model deployment name. Keep these
values in local `config.json` or runtime secrets.

### Bundled catalog and prompts

```text
config/catalog.json
config/prompts/*.txt
config/trade.xml
```

The root `config/` directory is copied to `/app/config/` in the image and read
directly. Prompt paths in the catalog are relative to that directory. Edit these
files and rebuild/redeploy the image to update ACA. `POST /api/refresh-prompt`
(with a JWT carrying the `refresh` role) reloads the local catalog and clears the
prompt cache; it does not download new content.

## Create a keystore and start the service

Set `JWT_KEYSTORE_PASSWORD` to the same value as `jwt.keystore_password` in
`config.json`. This environment variable is used by the CLI; the service reads
the password from its JSON configuration.

```bash
export JWT_KEYSTORE_PASSWORD='change-me'
# Run once to create the local keystore.
uv run --locked python -m dia_jwt create-keystore --path jwt_keystore.p12

# Keep this terminal running.
uv run --locked uvicorn capture.asgi:app --host 0.0.0.0 --port 8000
```

With the virtual environment activated, the start command can also be written as
`uvicorn capture.asgi:app --host 0.0.0.0 --port 8000`.

## Mint a token and call Capture

Open a **second terminal** in the project root:

```bash
export JWT_KEYSTORE_PASSWORD='change-me'
TOKEN=$(uv run --locked python -m dia_jwt mint --sub instance:local --role chat --days 1 \
  | awk '/^Authorization: Bearer / { print $3 }')

# Show the token if needed.
echo "$TOKEN"

# These credentials belong to the Diapason API, not the Capture JWT above.
export DIAPASON_API_TOKEN='replace-with-your-Diapason-API-token'
export DIAPASON_BASE_URL='https://your-diapason-host/diapason'

curl --fail-with-body http://localhost:8000/health

curl --fail-with-body -X POST http://localhost:8000/api/capture \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "X-Diapason-User-Id: 1" \
  -H "X-Diapason-Customer-Id: 1" \
  -H "X-Diapason-Mcp-Token: ${DIAPASON_API_TOKEN}" \
  -H "X-Diapason-Mcp-Scope: 1" \
  -H "X-Diapason-Mcp-Base-Url: ${DIAPASON_BASE_URL}" \
  -F "trade_type=iamLoan" \
  -F "pdf=@tests/fixtures/sample-loan-contract.pdf;type=application/pdf" \
  -F "debug=true"
```

The canonical route is **`/api/capture`**; `/ai/capture` is not registered. The
legacy route is still supported:

```bash
curl --fail-with-body -X POST http://localhost:8000/api/skills/intelligence-contract \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "X-Diapason-User-Id: 1" \
  -H "X-Diapason-Customer-Id: 1" \
  -H "X-Diapason-Mcp-Token: ${DIAPASON_API_TOKEN}" \
  -H "X-Diapason-Mcp-Scope: 1" \
  -H "X-Diapason-Mcp-Base-Url: ${DIAPASON_BASE_URL}" \
  -F "trade_type=iamLoan" \
  -F "pdf=@tests/fixtures/sample-loan-contract.pdf;type=application/pdf" \
  -F "debug=true"
```

`GET /api/capture` returns supported trade types and the prompt version, using the
same bearer token. Health endpoints (`/health` and `/api/health`) require no token.
The `chat` JWT role and existing `X-Diapason-*` headers remain for compatibility.
JWT CLI details are in [dia_jwt/README.md](src/capture/common/dia_jwt/README.md).

Optional `session_id` form data takes precedence over `X-Diapason-Chat-Session`.
Capture echoes the supplied ID, or generates a UUID, only for response/trace
correlation. It does not look up sessions or save turns or extraction artifacts.
Authentication and tenant/MCP identity checks still apply.

## CI and Docker

See the [test guide](tests/README.md) for coverage of each Capture graph step,
offline integration tests, fixtures, targeted commands, and known limits.
The [test change record](TEST_CHANGES.md) lists every moved, added, removed,
and edited file in the test rework.

[CI](.github/workflows/ci.yml) uses the existing self-hosted Linux runner, Python
3.12, and pinned uv. It runs `uv sync --locked --group dev` and the complete `tests/`
suite. The current workflow has no wheel or Docker build step. Tests use local
credentials and model/MCP doubles; they
need no Azure API key or live MCP server. The workflow follows the
[uv GitHub Actions integration](https://docs.astral.sh/uv/guides/integration/github/).

The [Dockerfile](Dockerfile) installs only locked production dependencies and a
non-editable Capture package. It uses the bundled `config/`; local environments,
tests, build artifacts, and `config*.json` secrets are excluded from the image.
Runtime secrets remain `CHAT_CONFIG` and `JWT_KEYSTORE_P12_B64`.

## Deployment and observability

See [Azure deployment handoff](AZURE_DEPLOYMENT.md) for the required changes and
the interface to the future company Terraform module `apps/ai/ai-capture`.

The current `deploy/` scripts and deploy workflow are inherited from
`diapason-agent` and are not ready to deploy Capture. They still target the old
app/secret path, provision chat/config Blob resources, and reference removed
frontend and smoke-test files. Replace or disable that deployment path before
using it, including its published-release trigger.

The intended flow is to build/publish the Capture image here and pass its immutable
reference to the company Terraform pipeline, which owns Azure resources and app
configuration. The runtime already accepts `CHAT_CONFIG` and
`JWT_KEYSTORE_P12_B64`; catalog and prompt changes travel with the image. The
shared `ai-services.yml` blob is consumed by Diapason for routing, not by Capture.
The handoff includes Docker/dev checks and the remaining production constraints;
it does not report a completed Azure deployment.

`/health` reports `VERSION` and the revision embedded at image build time.
OpenTelemetry continues to export HTTP and AI spans plus completion outcomes,
identity, and correlation IDs. Completion telemetry contains no document content
or storage links.

## Change records

- [Azure deployment review and edit inventory](AZURE_DEPLOYMENT_CHANGES.md)
- [Configuration, uv, CI, and local usage](CONFIG_UV_CI_CHANGES.md)
- [Blob Storage removal](BLOB_STORAGE_REMOVAL.md)
