# Capture

- [1. Project documentation](#1-project-documentation)
- [2. Local execution with real cloud services](#2-local-execution-with-real-cloud-services)
- [3. Local execution with dummy services](#3-local-execution-with-dummy-services)

All setup commands and shell comments below target **Linux with Bash**. Run them
from `capture_proposed/capture` unless another working directory is stated.

## 1. Project documentation

### Purpose and behavior

Capture is the PDF-to-trade extraction API extracted from `diapason-agent-main`.
It is consumed by the company UI or Pascal. It has no chat frontend or session
CRUD API. The original HTTP paths, `intelligence_contract` configuration key,
JWT issuer/roles, MCP bearer format and session records are retained.

The FastAPI entry point is `capture.asgi:app`. A LangGraph workflow executes:

1. Validate the PDF and choose the catalog entry for the requested trade type.
2. Extract document text with `pypdf`, load the prompt and call chat completions.
3. Parse the model XML and enforce the requested trade type.
4. Call MCP `resolveReferences` to resolve Diapason references.
5. Shape the result and persist the session and extraction artifacts in Blob Storage.

There is one model call followed by one resolver call; there is no agent tool
selection loop. PDFs must contain extractable text: image-only scans need OCR
upstream. Reference resolution does not create a trade in Diapason; the consuming
UI/agent handles subsequent import.

### Repository layout

| Path | Responsibility |
|---|---|
| `src/capture/api/` | HTTP routes, authentication dependencies and responses |
| `src/capture/workflow/` | LangGraph, PDF/XML extraction and prompt/catalog loading |
| `src/capture/common/` | Preserved JWT, configuration, Blob, MCP and session helpers |
| `src/capture/observability/` | Logging and tracing helpers |
| `config/catalog.json`, `config/prompts/` | Maintained catalog and prompt sources; uploaded to Blob |
| `config.example.json` | Committed template for connected configuration |
| `tests/` | Existing unit tests and real-process local integration tests |
| `tools/` | Local launchers, HTTP stubs, dummy configuration and fixtures |
| `tools/azurite/` | Maintained npm manifest/lockfile plus generated Azurite installation |
| `.local/` | Generated local keys, emulator data and request captures; not committed |

The project uses a `src` layout. Install it with the supplied development
requirements; editable installation makes source edits visible without copying
modules or adding `PYTHONPATH` workarounds. Tooling is excluded from the production
wheel and Docker build context. The local launcher uses normal subprocesses and
explicit configuration, with no runtime monkey-patching.

### Common Python setup

Install Python 3.12 with venv/pip support using your team's Linux tooling. Python
3.12 matches the Docker image; the package declares Python >=3.12. `curl` is used
for the HTTP examples. Initial dependency installation requires network access or
a prepared package cache.

```bash
# From the parent workspace, enter the Capture repository.
cd capture_proposed/capture
python3.12 --version
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip check
```

Use `.venv/bin/python` in every terminal; activation is optional. Continue with
section 2 for real services, or section 3 for fully local services. Node.js/Azurite
is needed only for the latter and for integration tests.

### API contract

| Route | Authentication / purpose |
|---|---|
| `GET /health`, `GET /api/health` | Public build/process health; no downstream dependency probe |
| `GET /api/skills/intelligence-contract` | Capture JWT with `chat` or `admin`; trade types and catalog version |
| `POST /api/skills/intelligence-contract` | Capture JWT plus identity/MCP headers; multipart PDF extraction |
| `POST /api/refresh-prompt` | JWT with `refresh`; reload catalog and clear prompt cache |
| `POST /api/auth/tokens`, `POST /api/auth/revoke` | JWT with `admin`; original token management APIs |
| `GET /docs`, `GET /openapi.json` | API schema; not all manually consumed identity/MCP headers are declared |

Extraction accepts multipart fields `pdf`, `trade_type`, optional `debug`, and
optional `session_id`. The response includes `success`, `trade_xml`, trade/entity
information, field count, warnings and tool trace. `X-Diapason-Chat-Session` in the
response identifies the persisted session. Sending `debug=true` also returns
document previews and intermediate model/resolver data.

The session ID can also be supplied in the request header
`X-Diapason-Chat-Session`; the form field takes precedence. Reuse is allowed only
within the same identity scope. A resolver business failure can return HTTP 200
with `success: false`; check the body, not just the status code.

### Tests and verification status

```bash
# Python-only unit suite: no cloud access or running services required.
.venv/bin/python -m pytest -m 'not integration' -q

# After installing Azurite as described in section 3, run everything.
.venv/bin/python -m pytest -q

# Run only the local integration tests.
.venv/bin/python -m pytest -m integration -v
```

Integration tests start and stop their own production Capture, Azurite and stub
processes on free loopback ports. They use temporary project-local state and no
monkey-patching. They cover PDF extraction, SDK/MCP HTTP calls, authentication,
catalog refresh, error scenarios, Blob ETags and session persistence across an
actual Capture restart. Existing unit tests retain their original mocks.

**Verified on 2026-09-15:** all **64 tests passed** (53 unit + 11 integration).
A separate live CLI PDF upload returned HTTP 200, `success: true`, nine extracted
fields and a persisted session after recreating the npm installation with `npm ci`.
Execution was verified on the available Windows host; the instructions here target
Linux. Real Azure/Diapason connections and model accuracy could not be verified
without company URLs and credentials. One third-party Starlette/AnyIO deprecation
warning remains.

Deployment scripts retain assumptions from the original PoC and were not revised
as part of local development setup. Review their service/environment paths before
deploying this extracted service. [The edit inventory](tools/CHANGES.md) records
all changes made for development support.

## 2. Local execution with real cloud services

### Step 1: complete Python setup and obtain access

Complete the common Python setup in section 1. Install Azure CLI using your team's
Linux installation procedure. Node.js, Azurite and the dummy servers are not
needed for this mode.

Obtain the following from the environment owner:

| Dependency | Values / access needed |
|---|---|
| Azure OpenAI | Resource endpoint, API key, deployment name and compatible API version. Deployment must support chat completions and the configured `temperature`. |
| Azure Blob | Account/container names and network access. Your identity needs Blob Data Reader on the config container and Blob Data Contributor on sessions. |
| Diapason MCP ACA | HTTPS endpoint ending `/mcp`, network/VPN access and the same Fernet key as that server's `MCP_CONFIG_KEY`. |
| Diapason tenant | Application base URL without `/api`, integer scope, and API token or client credentials to obtain one. |
| Capture JWT | Company PKCS#12/password if existing UI/Pascal JWTs must work, or permission/access to use a separate local key and locally minted test JWTs. |

The MCP endpoint and Diapason application URL are different: Capture calls MCP;
MCP uses the Diapason URL carried inside the encrypted bearer to call the tenant.

### Step 2: create and edit `config.json`

```bash
# Preserve an existing personal configuration.
test -f config.json || cp config.example.json config.json

# Use the root config file and local keystore for this connected process.
unset CHAT_CONFIG JWT_KEYSTORE_P12_B64
```

Edit root `config.json` with your actual values. In particular,
**the Azure OpenAI endpoint goes in `azure_openai.endpoint`**, and its API key,
deployment and version go in that same block. Configuration is cached: restart
the app after changing it.

| Configuration field | Meaning / expected value |
|---|---|
| `jwt.keystore_password` | Password of root `jwt_keystore.p12`; runtime reads this JSON field. |
| `jwt.revoked.jtis`, `jwt.revoked.subs` | Normally empty objects. Seed revocation state only if its file does not already exist. |
| `sessions.max_turns` | Number of retained user/assistant pairs per session; default 30. |
| `storage.account_name` | Account name only, not a URL or connection string. |
| `storage.chat_container` | Session container, normally `chat-sessions`. |
| `storage.config_container` | Catalog/prompt container, normally `agent-config`. |
| `intelligence_contract.enabled` | Must be JSON `true` to enable Capture. |
| `intelligence_contract.catalog_blob` | Normally `skills/intelligence-contract/catalog.json`. |
| `intelligence_contract.cache_ttl_seconds` | Prompt-text cache lifetime; catalog is loaded at startup/refresh. |
| `intelligence_contract.max_pdf_bytes` | Validation limit, normally 10485760 bytes (10 MiB). |
| `intelligence_contract.view_entity` | Fallback resolver entity, normally `loanDeposit`; catalog entry takes precedence. |
| `intelligence_contract.temperature` | Sent directly to the model, normally 0.5. |
| `azure_openai.endpoint` | Resource base URL such as `https://<resource>.openai.azure.com`; omit deployment/completions path. |
| `azure_openai.api_key` | Azure OpenAI API key; this code does not use Azure CLI authentication for the model. |
| `azure_openai.deployment` | Azure deployment name, which can differ from the model family name. |
| `azure_openai.api_version` | Supported deployment API version; example retains `2024-10-21`. |
| `mcp.default.label` | Name displayed in the tool trace. |
| `mcp.default.server_url` | Real MCP ACA endpoint, e.g. `https://<app>.azurecontainerapps.io/mcp`. |
| `mcp.default.config_key` | Exact Fernet key matching that MCP server; not a Capture JWT or Diapason API token. |

Optional `mcp.default.protocol_version` defaults to `2024-11-05` or the request's
`X-Diapason-Mcp-Protocol-Version`. Use your environment's compatible value.
The graph only calls the default MCP server. No `system_prompt.md`, chat persona,
frontend build or model tool-loop setting is required by Capture.

**Leave `storage.connection_string` and `storage.api_version` absent for the
existing Azure identity authentication path.** The explicit connection-string
path is used by the local emulator in section 3; its account must match
`storage.account_name`, and its optional API version applies only to that path.

`CHAT_CONFIG`, if set, is the full inline JSON object and overrides `config.json`;
it is not a filename. `JWT_KEYSTORE_P12_B64` overrides the keystore file. The
application does not automatically load `.env` files. Root `config.json` and
keystores are gitignored and must not be committed.

```bash
# Check JSON syntax without printing credentials.
.venv/bin/python -m json.tool config.json >/dev/null
```

### Step 3: authenticate to Azure Blob and check config blobs

```bash
az login
az account set --subscription '<subscription-id>'

export STORAGE_ACCOUNT_NAME="$(.venv/bin/python -c 'import json; print(json.load(open("config.json"))["storage"]["account_name"])')"
export CONFIG_CONTAINER="$(.venv/bin/python -c 'import json; print(json.load(open("config.json"))["storage"]["config_container"])')"
export SESSION_CONTAINER="$(.venv/bin/python -c 'import json; print(json.load(open("config.json"))["storage"]["chat_container"])')"
export CATALOG_BLOB="$(.venv/bin/python -c 'import json; print(json.load(open("config.json"))["intelligence_contract"]["catalog_blob"])')"

az storage container show --auth-mode login \
  --account-name "$STORAGE_ACCOUNT_NAME" --name "$SESSION_CONTAINER"
az storage blob show --auth-mode login \
  --account-name "$STORAGE_ACCOUNT_NAME" --container-name "$CONFIG_CONTAINER" \
  --name "$CATALOG_BLOB"
```

Containers must exist with the correct RBAC. Locally, Blob authentication tries
`AzureCliCredential` first, then `DefaultAzureCredential` with environment
credentials excluded. In Azure it uses the managed-identity credential path.
Deploy service-principal environment variables alone are not the intended local
Blob login method.

If the correct catalog/prompts already exist, skip uploading. To upload your
local changes, you also need Blob Data Contributor on the config container.
These commands overwrite the named blobs, so use your intended development
container:

```bash
az storage blob upload --auth-mode login \
  --account-name "$STORAGE_ACCOUNT_NAME" --container-name "$CONFIG_CONTAINER" \
  --name "$CATALOG_BLOB" --file config/catalog.json --overwrite
az storage blob upload-batch --auth-mode login \
  --account-name "$STORAGE_ACCOUNT_NAME" --destination "$CONFIG_CONTAINER" \
  --destination-path skills/intelligence-contract/prompts \
  --source config/prompts --pattern '*.txt' --overwrite
```

Relative prompt entries in the catalog resolve under `skills/intelligence-contract/`,
even when you choose a different catalog blob path. Catalog trade types and existing
spellings are preserved; unknown types use `default_prompt` when it exists.
Use these explicit upload commands rather than inherited PoC upload-script paths.

### Step 4: provide the local Capture keystore and mint a JWT

For existing UI/Pascal tokens, obtain their matching keystore and place it at
**`./jwt_keystore.p12`**, with its password in `config.json.jwt.keystore_password`.
A newly generated key cannot validate tokens signed by a different company key.

For an independent local test client, create a separate key only if one is absent:

```bash
umask 077
export JWT_KEYSTORE_PASSWORD="$(.venv/bin/python -c 'import json; print(json.load(open("config.json"))["jwt"]["keystore_password"])')"

if [ ! -f jwt_keystore.p12 ]; then
  .venv/bin/python -m dia_jwt create-keystore --path jwt_keystore.p12
fi

.venv/bin/python -m dia_jwt mint --path jwt_keystore.p12 \
  --sub instance:local --role chat --role refresh --customer-id 7 --seconds 3600
unset JWT_KEYSTORE_PASSWORD
```

Copy the emitted `access_token` into your request headers file in the next step.
The CLI password environment variable must match the JSON password; runtime itself
reads the JSON field. Signing remains RS256 with issuer `diapason-agent`.
Extraction requires `chat` or `admin`; prompt refresh explicitly requires `refresh`.
Admin alone does not grant refresh.

Revocations persist at `data/jwt_revoked.json`. A JWT customer claim must match
`X-Diapason-Customer-Id`. Session paths derive from JWT subject, customer and user;
`instance:local`, customer 7, user 42 produces `local/7/42/<session-id>.json`.
See [the unchanged JWT helper documentation](src/capture/common/dia_jwt/README.md).

### Step 5: prepare Capture and Diapason request headers

Create `tools/headers.local.json` in your editor using this structure and your
actual values. It is gitignored. The Capture JWT and Diapason API token are two
different credentials:

```json
{
  "Authorization": "Bearer <Capture access_token from step 4>",
  "X-Diapason-User-Id": "42",
  "X-Diapason-Customer-Id": "7",
  "X-Diapason-Mcp-Token": "<Diapason API token without a Bearer prefix>",
  "X-Diapason-Mcp-Scope": "<integer Diapason scope>",
  "X-Diapason-Mcp-Base-Url": "https://<diapason-host>/<application-context>",
  "X-Diapason-Locale": "en_US"
}
```

All headers except locale are required for extraction. The Diapason base URL
must not end in `/api`. Capture encrypts `{base_url, scope, api_token}` using
`mcp.default.config_key` and sends that Fernet bearer to MCP. Capture does not
log in to Diapason itself. UI/Pascal callers must forward equivalent headers.

If you already have a valid Diapason token, skip the following login example.
Otherwise, the original PoC smoke uses client-credentials form login and reads an
XML token attribute. This equivalent fills the token in your existing headers
file without printing it:

```bash
read -r -p 'Diapason client ID: ' DIAPASON_CLIENT_ID
read -r -s -p 'Diapason client secret: ' DIAPASON_CLIENT_SECRET
printf '\n'
export DIAPASON_CLIENT_ID DIAPASON_CLIENT_SECRET
chmod 600 tools/headers.local.json

.venv/bin/python - <<'PY'
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET
import httpx

path = Path('tools/headers.local.json')
headers = json.loads(path.read_text())
base = headers['X-Diapason-Mcp-Base-Url'].rstrip('/')
response = httpx.post(base + '/api/login', data={
    'client_id': os.environ['DIAPASON_CLIENT_ID'],
    'client_secret': os.environ['DIAPASON_CLIENT_SECRET'],
    'locale': 'en_US',
}, timeout=60)
response.raise_for_status()
root = ET.fromstring(response.text)
token = root.get('apiToken') or root.get('token')
if not token:
    raise SystemExit('Diapason login returned no API token')
headers['X-Diapason-Mcp-Token'] = token
path.write_text(json.dumps(headers, indent=2))
print('Updated the Diapason token in the private headers file.')
PY

unset DIAPASON_CLIENT_SECRET DIAPASON_CLIENT_ID
```

Use credentials for the intended environment. An existing MCP server requires
its existing Fernet key; generating an unrelated new key will not authenticate.

### Step 6: start Capture and perform a real extraction

In terminal A, from the project root:

```bash
unset CHAT_CONFIG JWT_KEYSTORE_P12_B64
.venv/bin/python -m uvicorn capture.asgi:app \
  --host 127.0.0.1 --port 8010 --reload
```

In terminal B, from the same project root:

```bash
curl -fsS http://127.0.0.1:8010/health
.venv/bin/python -m tools smoke \
  --url http://127.0.0.1:8010 \
  --headers tools/headers.local.json \
  --pdf tests/fixtures/sample-loan-contract.pdf --trade-type iamLoan
```

The smoke checks health and metadata, uploads the PDF and prints the result plus
session ID. It exits nonzero for HTTP errors or `success: false`. Add `--debug`
for model/XML details, `--pdf /path/to/your.pdf` for another document, or
`--session-id <returned-id>` to append to an existing session in the same scope.
Successful dummy fixtures do not predict the result of this real model/tenant run.

API schema: <http://127.0.0.1:8010/docs>. Use the smoke client for a complete
authenticated upload; Swagger does not declare every identity/MCP header.

### Step 7: iterate on prompts, code and configuration

Code changes reload with `--reload`. Config or keystore changes require restart.
After uploading edited catalog/prompts, refresh using a JWT with the refresh role:

```bash
CAPTURE_AUTH="$(.venv/bin/python -c 'import json; print(json.load(open("tools/headers.local.json"))["Authorization"])')"
curl -fsS -X POST http://127.0.0.1:8010/api/refresh-prompt \
  -H "Authorization: $CAPTURE_AUTH"
unset CAPTURE_AUTH
```

Refresh reloads the catalog and clears the prompt cache. Prompt text otherwise
expires at the configured TTL. An explicit catalog version changes only when you
edit that version field. Stop the server with Ctrl+C when finished.

| Failure | Check |
|---|---|
| Startup Blob error | Azure login, data-plane RBAC, account/container, network and presence of catalog blobs |
| 401/403 | JWT signature, expiry, issuer, role, revocation and matching customer ID |
| 400 missing headers | All identity/MCP headers and integer IDs/scope |
| 404 | Feature enabled? Supplied session known and owned by the caller? |
| 503 model configuration | Nonempty endpoint/key/deployment; placeholders cannot authenticate |
| 400 PDF/XML | Text PDF, size/header and parseable model XML |
| 502 MCP | MCP `/mcp` URL, Fernet key, Diapason token/base URL/scope; graph resolver timeout is 180 seconds |
| HTTP 200 with success=false | Resolver business failure; inspect message, warnings and XML |

## 3. Local execution with dummy services

### Step 1: understand the local dependencies and install prerequisites

Complete the common Python setup in section 1. Install **Node.js 22+ and npm for
Linux** using your team's tooling. No Azure CLI login, Azure account, real model
endpoint, Diapason access or Docker daemon is required in this mode.

| Component | Local implementation |
|---|---|
| Capture | The same production `capture.asgi:app`, port 8010 |
| Azure OpenAI | Configurable chat-completions HTTP stub, port 8011 |
| MCP | Configurable `resolveReferences` JSON-RPC HTTP stub, port 8011 |
| Azure Blob | Microsoft Azurite Blob emulator, port 10000, accessed with the real SDK |
| Capture JWT | Real RS256 JWT using a separate generated local keystore |

```bash
node --version
npm --version
npm ci --prefix tools/azurite --include=dev --ignore-scripts
```

This installs pinned Azurite 3.37.0 locally. Package installation needs network
access or a cache; running the installed local stack does not. The setup does not
install Azurite globally. Azurite telemetry is disabled and all services bind to
loopback. The local config rejects remote model, MCP and Blob endpoints.

### Step 2: know what the Azurite directories contain

**The npm installation and the emulator's data are separate.**

| Path | Created by | Commit / maintain? | How to recreate |
|---|---|---|---|
| `tools/azurite/package.json` | Project-maintained manifest | **Commit.** Maintain the chosen Azurite version. | Restore from the repository if deleted. |
| `tools/azurite/package-lock.json` | npm dependency resolution | **Commit.** Maintain with intentional dependency updates. | Restore from the repository for the same versions; `npm ci` does not recreate a missing lockfile. |
| `tools/azurite/node_modules/` | `npm ci` | **Do not commit or edit.** Upstream emulator/dependency code, gitignored. | Run the install command in step 1. |
| `.local/azurite/` | Starting `python -m tools storage` | **Do not commit.** Generated Blob contents and emulator metadata, gitignored. | Start storage, then run init to recreate containers/catalog/prompts. Old sessions are not recreated. |
| `.local/jwt_keystore.p12` | `python -m tools init` | **Do not commit.** Generated local private key. | Init creates a new key if missing; previously minted tokens then stop working. |
| `.local/VERSION` | `python -m tools init` | **Do not commit.** Copied build version for local runtime. | Run init again. |
| `.local/data/jwt_revoked.json` | Capture startup | **Do not commit.** Local revocation state. | Startup creates it if missing; previous revocations are not restored. |
| `.local/requests/` | Calls to the dummy HTTP endpoints | **Do not commit.** Latest prompt/PDF text and MCP arguments. | Run smoke again. |

The maintained code is in `tools/bootstrap.py`, `tools/stubs.py` and the other
small project utilities, plus the JSON/XML fixtures. The Azurite implementation
inside `node_modules/` is maintained upstream by Microsoft, not copied into our
application source. Both generated trees are excluded from Git and the production
image. Do not delete the two maintained npm files to reset the emulator.

### Step 3: start storage and the dummy endpoints

Open separate terminals in the project root. Keep each server running.

```bash
# Terminal A: start Azurite; it creates .local/azurite/ automatically.
.venv/bin/python -m tools storage
```

```bash
# Terminal B: start the configurable model and MCP HTTP endpoints.
.venv/bin/python -m tools stubs
```

The maintained local configuration is [tools/offline.json](tools/offline.json).
It contains loopback URLs, public emulator account/key values and dummy model/MCP
credentials. These are not company secrets. Storage uses an explicit connection
string and API version `2023-11-03`; emulator API-version validation remains enabled.

### Step 4: initialize local assets and start Capture

After Azurite is listening, run in terminal C:

```bash
# Create or preserve the local signing key and upload the real catalog/prompts.
.venv/bin/python -m tools init

# Start the normal Capture ASGI app using explicit local configuration.
.venv/bin/python -m tools serve --reload
```

Init creates the session/config containers if absent, uploads the catalog and
prompts from `config/`, preserves an existing local key and copies VERSION. It can
be run again; catalog/prompt blobs are overwritten with current source files.

The launcher starts Capture with `.local/` as the runtime directory and supplies
the selected JSON as `CHAT_CONFIG` to the child process. It removes inherited
connected keystore, proxy and telemetry exporter settings from that child's
environment. It does not mutate the parent's environment or application objects.
Connected root `config.json`, `jwt_keystore.p12` and revocation files are separate.

### Step 5: run the complete PDF extraction

In terminal D, from the project root:

```bash
curl -fsS http://127.0.0.1:8010/health
.venv/bin/python -m tools smoke --debug
```

The default smoke uses `tests/fixtures/sample-loan-contract.pdf`, trade type
`iamLoan`, a fresh one-hour Capture JWT, and dummy identity/MCP headers. Expected:

- HTTP 200 and `success: true`.
- XML containing `<tradeType shortname="iamLoan">763</tradeType>` and nine fields.
- Two trace entries: `extract_xml` and `resolveReferences`.
- A session ID and persisted session artifacts in Azurite `chat-sessions`.

This is a complete local pipeline: PDF parsing, actual prompt loading from Blob,
real OpenAI SDK request, XML handling, MCP HTTP call and Blob session persistence.
**The LLM stub returns fixed configurable XML; it does not infer values from the
PDF.** Success proves the pipeline works, not that the dummy result matches the
document or that a prompt is accurate. Real extraction quality and reference
mapping must be checked using section 2.

```bash
# Use another text PDF or reuse an existing session in the same identity scope.
.venv/bin/python -m tools smoke --pdf /path/to/contract.pdf --trade-type iamLoan
.venv/bin/python -m tools smoke --session-id '<returned-session-id>'

# Print fresh local request headers if using another HTTP client.
.venv/bin/python -m tools headers
```

The HTTP stubs save the latest request bodies at `.local/requests/llm.json` and
`.local/requests/mcp.json`. They omit authentication headers, but include document
text and XML. `--debug` responses expose intermediate data too; use synthetic
documents for examples you intend to share.

### Step 6: customize dummy responses and configuration

| Setting | Behavior |
|---|---|
| `tools/scenario.json` → `llm.response_file` | XML fixture returned by the model; initially `tools/fixtures/loan.xml` |
| Optional `llm.content` | Literal response overriding the file; supports empty, malformed or fenced XML |
| `llm.http_status`, `llm.usage` | Synthetic model HTTP status and token counts |
| `mcp.reference_ids` | Synthetic IDs keyed by XML tag and shortname; unmapped references remain unchanged |
| `mcp.response` | Overrides resolver success, XML, message, warnings or view_entity |
| `mcp.is_error`, `mcp.http_status` | MCP tool error or HTTP failure |
| `tools/offline.json` → `development.state_dir` | Generated state directory, default `.local` |
| `development.config_dir` | Catalog/prompt source directory uploaded by init/sync-config, default `config` |
| `development.scenario_file` | Selected scenario file |

The scenario and model response file are reread on every stub request. Edit them
and rerun smoke without restarting. Example experiments:

- Set `mcp.response` to `{"success": false, "trade_xml": "", "message": "Unknown counterparty", "warnings": ["Manual review"]}`: HTTP 200, success=false, persisted business failure.
- Set `mcp.is_error` to true or its HTTP status to 503: Capture returns HTTP 502.
- Set `llm.content` to `"not XML"`: HTTP 400; set it to `""`: HTTP 502.

Reset overrides for the happy path. Model HTTP errors retain existing SDK/API
behavior, typically HTTP 500 for SDK errors; SDK retries may delay 429/5xx cases.
The MCP stub only implements `tools/call resolveReferences`, not general MCP
discovery, handshake or SSE. The loan fixture does not represent every instrument;
add appropriate XML/scenarios when developing other trade types.

For personal configuration/scenario copies:

```bash
test -f tools/offline.local.json || cp tools/offline.json tools/offline.local.json
test -f tools/scenario.local.json || cp tools/scenario.json tools/scenario.local.json

# Edit the copied config to use tools/scenario.local.json, then set this in every terminal.
export CAPTURE_DEV_CONFIG=tools/offline.local.json
```

Paths in these files are relative to the Capture root and must remain inside the
project. Configuration edits require restart. If changing stub port 8011, update
both model/MCP URLs and use `tools stubs --port <port>`. For Capture, use
`tools serve --port <port>` and pass `--url` to smoke. Azurite's port is read from
the Blob endpoint in the connection string. Set `CAPTURE_DEV_CONFIG` consistently
in storage, init, stubs, serve, smoke and inspection terminals.

### Step 7: develop prompts and inspect persisted sessions

The prompt/catalog files in `config/` are maintained sources. After editing them,
upload to Azurite and refresh Capture:

```bash
.venv/bin/python -m tools sync-config
CAPTURE_AUTH="$(.venv/bin/python -m tools headers | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["Authorization"])')"
curl -fsS -X POST http://127.0.0.1:8010/api/refresh-prompt \
  -H "Authorization: $CAPTURE_AUTH"
unset CAPTURE_AUTH
```

Azurite's disk files are storage internals, not a directory of readable session
JSON. Inspect sessions through the real Blob SDK (or Azure Storage Explorer
connected to the emulator):

```bash
export CAPTURE_SESSION_ID='<session-id-from-smoke>'
.venv/bin/python - <<'PY'
import json
import os
from tools.configuration import load_offline
from tools.bootstrap import blob_service

config = load_offline()
name = 'offline/7/42/' + os.environ['CAPTURE_SESSION_ID'] + '.json'
with blob_service(config) as client:
    blob = client.get_blob_client(config['storage']['chat_container'], name)
    print(json.dumps(json.loads(blob.download_blob().readall()), indent=2))
PY
unset CAPTURE_SESSION_ID
```

The default identity is `instance:offline`, customer 7, user 42. Assistant turns
retain `skill_run.artifacts`, source/resolved XML and timings. Sessions survive
restarts. Old `.local/blobs/` files from the superseded filesystem adapter are
unused by Azurite and were left intact.

For IDE debugging, choose `.venv` and run Python module `uvicorn`, arguments
`capture.asgi:app --host 127.0.0.1 --port 8010`, working directory `.local`, with
`CHAT_CONFIG` set to the full local JSON and `JWT_KEYSTORE_P12_B64` unset in that
debug process. Run init first, keep Azurite/stubs running, and omit reload for
breakpoints. Useful files: `workflow/graph.py`, `workflow/extract_xml.py`, and
`api/extraction.py` under `src/capture/`.

### Step 8: stop, recreate or update the local environment

Stop Capture, stubs and Azurite with Ctrl+C in their terminals. On normal restart,
the emulator reuses `.local/azurite/`; init is unnecessary unless you need to
create assets or upload config again.

To **recreate the npm installation** after deleting `node_modules/`, with servers
stopped, use the existing committed manifest and lockfile:

```bash
npm ci --prefix tools/azurite --include=dev --ignore-scripts
```

If you deleted the maintained manifest/lockfile too, restore them from your
repository first. Do not generate a new lockfile if the goal is the identical
environment. `npm ci` recreates dependencies; it does not recreate missing source
files or recover emulator sessions.

```bash
# In a Git checkout, restore accidentally deleted files that were already committed.
git restore --source=HEAD -- tools/azurite/package.json tools/azurite/package-lock.json
npm ci --prefix tools/azurite --include=dev --ignore-scripts
```

To **start with fresh Blob data**, stop all local servers first. From the Capture
root, the following deliberately removes only the default emulator's data,
including its local sessions; it preserves the local signing key:

```bash
# Destructive to local emulator data only; first verify the project root.
test -f tools/azurite/package.json && test -f tools/offline.json && rm -rf -- .local/azurite

# Terminal A: recreates the emulator data directory.
.venv/bin/python -m tools storage
```

In other terminals, start stubs, run init to recreate containers/config blobs,
and start Capture as in steps 3–4. If you configured a different state directory,
use its `azurite/` subdirectory instead after verifying that path. Deleting data
cannot recover previous sessions; deleting the signing key additionally invalidates
previous local JWTs. Neither is required for routine development.

For an **intentional Azurite version update**, edit the exact version in
`tools/azurite/package.json`, regenerate the lockfile, run the integration suite,
and commit both maintained npm files:

```bash
# Run after editing the desired version in package.json, with local services stopped.
npm install --prefix tools/azurite --include=dev --ignore-scripts
.venv/bin/python -m pytest -m integration -v
npm audit --prefix tools/azurite
```

The current upstream npm tree reports four moderate findings stemming from `uuid`,
with no high/critical findings at verification. The emulator is development-only
and excluded from the production image; retain these findings in normal dependency
review. No forced downgrade or incompatible override was applied.

| Local issue | What to do |
|---|---|
| Azurite executable missing | Check Linux Node.js 22+ and rerun npm ci from step 1 |
| Init connection refused | Start storage first and check the connection-string Blob port |
| Missing key/VERSION | Run init after storage starts, then use tools serve |
| Prompt changes invisible | Run sync-config, then refresh/restart Capture |
| Port already used | Stop the other process or change all related URLs/ports consistently |
| Metadata works, extraction fails | Check all three dependency endpoints, PDF content and scenario overrides |

Azurite exercises the storage protocol and SDK, but not real Azure RBAC or every
cloud behavior. Use section 2 to verify the actual environment before relying on
cloud connectivity or model/reference accuracy.
