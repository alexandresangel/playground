# Capture: local development on Windows with WSL

This guide sets up **a new developer computer**, using Windows, WSL 2, Ubuntu 24.04 LTS, Python 3.12, and VS Code. It does not depend on the virtual environments or files installed on the computer where the migration was performed.

You will run Capture on your own computer and edit/debug its Python code without pushing a commit or deploying to Azure. For real extractions, Capture will connect to the company's existing **dev** Azure and Diapason services.

The instructions describe the current implementation in `capture/`. Company URLs, secrets, tenant IDs, and permissions must come from your team: the repository contains placeholders, not a working dev configuration.

Follow sections 1–12 in order for the first setup. Sections 13–18 cover development and troubleshooting. Navigation:

- [Company values to obtain](#2-gather-the-company-specific-values)
- [Install WSL](#3-install-wsl-and-ubuntu) and [install Python dependencies](#5-create-captures-python-environment)
- [Run offline tests](#6-run-the-offline-tests-first)
- [Azure sign-in](#7-install-and-sign-in-to-azure-cli-inside-wsl) and [runtime parameters](#8-configure-the-local-capture-runtime)
- [Start the API](#10-start-the-local-api), [configure requests](#11-configure-a-client-to-call-authenticated-endpoints), and [test an extraction](#12-run-metadata-checks-then-a-full-extraction)
- [Debug in VS Code](#13-edit-and-debug-with-vs-code) and [edit prompts](#14-develop-prompts-and-change-model-parameters)
- [Daily commands](#15-the-normal-daily-loop) and [troubleshooting](#17-troubleshooting-by-symptom)

## 1. Understand what runs where

```text
Your Windows computer
  Windows: VS Code window and browser
  WSL / Ubuntu:
    Python virtual environment
    Capture API at http://127.0.0.1:8001
      -> Azure dev Blob Storage: catalog, prompts, sessions/artifacts
      -> Azure dev OpenAI deployment: document text -> trade XML
      -> Company dev MCP server: resolveReferences
           -> Diapason dev instance, using the request's user context
```

| Development mode | Available without company credentials? | What it validates |
| --- | --- | --- |
| Offline automated tests | Yes, after installing dependencies | Python logic, graph behavior, API contracts, JWT/scope handling, and persistence behavior with test dependencies. |
| Local API with real dev dependencies | No | Actual PDF extraction, Azure model access, Blob access, MCP reference resolution, and session writes. |
| Application deployed in Azure dev | No | The deployed image, Azure identity, secrets, networking, and company UI integration. |

Capture is an API service; it does not include Pascal's chat frontend. Docker, Terraform/OpenTofu, deployment scripts, and a local MCP server are **not required** for the main path in this guide. There is no additional database or LangGraph server to start.

An offline test passing does not mean the real service can start without configuration. The normal runtime still needs JWT and storage configuration; with Capture enabled it also loads its catalog from Blob during startup. There is no built-in local filesystem replacement for runtime Blob storage or runtime prompt loading.

## 2. Gather the company-specific values

You can complete sections 3–6 while waiting for these. Obtain the following through the team's normal onboarding/secrets process before section 7.

| Item | What to obtain / why it is needed |
| --- | --- |
| Source code | The current Capture repository URL and branch, or the parent repository containing `capture/`. |
| Azure account | Your company sign-in, dev tenant ID, and dev subscription ID. |
| Dev network access | Required VPN, private DNS, proxy, or certificate setup, including access from **inside WSL**. |
| Runtime configuration | A working dev `config.json` matching this service's existing schema. |
| JWT keystore | The dev `jwt_keystore.p12` file and matching `jwt.keystore_password`, or the equivalent base64 secret. |
| Capture API token | A valid dev JWT with `chat` role (or `admin`), trusted by that keystore. The existing issuer is `diapason-agent`, including in Capture. |
| Azure OpenAI | Dev resource endpoint, API key, deployment name, and API version compatible with the existing code. |
| Blob Storage | Dev account name and existing session/config container names. |
| Blob permissions | Your local signed-in identity needs **Storage Blob Data Reader** on the config container and **Storage Blob Data Contributor** on the session container. Prompt editing also needs write access to its chosen config container. |
| MCP connection | Dev MCP URL and the matching `mcp.default.config_key` Fernet key used by that MCP server. |
| Diapason request context | Dev instance base URL, Diapason API token, integer scope, integer user ID, and integer customer ID for a consistent test identity. Alternatively, the smoke script can obtain the Diapason API token using company client credentials. |
| Test input | A text-based PDF and a trade type valid for the target Diapason dev instance. A small fixture is included, but its entities may not match that instance. |

The **Capture API JWT** and **Diapason API token** are different credentials. Azure sign-in supplies neither of them. The MCP Fernet key is also separate from both the JWT keystore password and the Azure OpenAI key.

Azure resource management access alone does not imply Blob data access. Ask for the data roles above on the intended dev containers. [Microsoft: authorize Blob access with Azure CLI](https://learn.microsoft.com/en-us/azure/storage/blobs/authorize-data-operations-cli)

Use dev identities and data throughout this guide. Local integration requests make real model calls and can create sessions/artifacts in the configured dev storage.

## 3. Install WSL and Ubuntu

### 3.1 Install from Windows

Open **Windows Terminal / PowerShell as Administrator**. This is a Windows terminal, not an Ubuntu terminal.

```powershell
wsl --install -d Ubuntu-24.04
```

Restart Windows if prompted. Open **Ubuntu 24.04** from the Start menu and create a Linux username and password. This Linux password is used for `sudo`; no characters appear while you type it.

Back in Windows PowerShell, check:

```powershell
wsl --list --verbose
```

Expected: `Ubuntu-24.04` appears with `VERSION` equal to `2`. If that distribution already exists, use it rather than installing another copy. If it is version 1, convert it:

```powershell
wsl --set-version Ubuntu-24.04 2
```

If installation is blocked by company device policy or virtualization settings, your workstation administrator must enable it. [Microsoft: install WSL](https://learn.microsoft.com/en-us/windows/wsl/install)

### 3.2 Install Linux tools

**All following `bash` blocks run in Ubuntu/WSL**, unless another shell is explicitly named. Do not paste Bash commands into PowerShell.

```bash
sudo apt update
sudo apt install -y git curl ca-certificates python3.12 python3.12-venv python3-pip
python3.12 --version
git --version
```

Expected: Python `3.12.x`. The project declares Python `>=3.12`; using 3.12 provides a consistent starting point with the migration validation.

Keep your working files under the Linux home directory, for example `~/projects/capture`. A Windows file such as `C:\Users\Alice\Downloads\config.json` is accessible from WSL as `/mnt/c/Users/Alice/Downloads/config.json`. Linux paths and filename capitalization matter.

## 4. Obtain a clean checkout

Run in WSL:

```bash
mkdir -p ~/projects
cd ~/projects
```

Choose **one** of the following layouts. Replace the example URL with the actual company Git URL. Do not copy someone else's `.venv`, `build/`, or installed packages.

**If Capture is a standalone repository:**

```bash
git -c core.autocrlf=input clone 'REPLACE_WITH_CAPTURE_GIT_URL' capture
cd ~/projects/capture
```

**If your repository contains a `capture/` subdirectory:**

```bash
git -c core.autocrlf=input clone 'REPLACE_WITH_PARENT_GIT_URL' diapason
cd ~/projects/diapason/capture
```

Use the branch your team specifies (`git switch your-branch-name` after replacing the name). Set a convenient path variable after entering the actual Capture directory:

```bash
export CAPTURE_ROOT="$PWD"
pwd
ls pyproject.toml requirements-dev.txt VERSION src/capture/asgi.py
```

Expected: all four files exist. If they do not, you are in the wrong directory or have the wrong checkout. Throughout this guide, **Capture root** means this directory, containing `pyproject.toml` and `VERSION`.

`CAPTURE_ROOT` is only a convenience variable for your shell; the application does not read it. It disappears when you close the terminal. In a new terminal, `cd` to your actual checkout and set it again.

If your team provides a source archive instead, extract a clean copy under `~/projects`, enter its Capture directory, and perform the same file check. Git commands in this guide apply only to Git checkouts.

## 5. Create Capture's Python environment

From Capture root in WSL:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m pip check
python -c 'import sys, capture; print(sys.executable); print(capture.__file__)'
```

Expected:

- The interpreter path ends in `capture/.venv/bin/python` (under your actual checkout).
- The Capture module resolves to your checkout's `src/capture/` directory.
- `pip check` reports no broken requirements.

`requirements-dev.txt` installs runtime dependencies, test/build tools, and the project in **editable mode** (`-e .`). Editing Python files therefore changes what this environment imports without reinstalling the project each time. Rerun the install command if dependencies or packaging change.

Each new terminal needs `source .venv/bin/activate`. A Windows `.venv/Scripts/python.exe` cannot be reused as a Linux virtual environment. Give Pascal its own environment if you later run both services; both packages preserve some original top-level company module names.

Dependencies currently use version ranges rather than a fully pinned lock file. A fresh install can resolve newer versions than a previous machine. If installation or tests regress, record `python --version` and `python -m pip freeze` for diagnosis and compare with the team's validated environment.

## 6. Run the offline tests first

From Capture root with `.venv` active:

```bash
python -m pytest -q
```

No Azure login, running server, `config.json`, JWT keystore, or live MCP is needed for this suite. It supplies test dependencies. The migration baseline recorded **54 passing Capture tests**; the count may change as development continues.

To work on a smaller area:

```bash
python -m pytest tests/test_workflow.py -q
python -m pytest tests/test_extract_trade_type.py tests/test_xml_fields.py -q
python -m pytest tests/test_api.py -q
```

Use `python -m pytest --collect-only -q` to list tests, or add `-x -vv` to stop at the first failure with more detail. Fix installation/import failures before trying the live service.

**Checkpoint:** you can already work on Python logic and offline tests without Azure access or a deployment.

## 7. Install and sign in to Azure CLI inside WSL

Install the Linux CLI using Microsoft's installer:

```bash
curl -fsSL https://aka.ms/InstallAzureCLIDeb -o /tmp/capture-install-azure-cli.sh
sudo bash /tmp/capture-install-azure-cli.sh
az version
command -v az
```

Expected: `az` resolves to a Linux executable, normally `/usr/bin/az`. Installing/signing in to Azure CLI only on Windows is not the setup used here. [Microsoft: Azure CLI Linux installation](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli-linux?pivots=apt&view=azure-cli-latest)

Replace both placeholders with values supplied by the team:

```bash
az login --tenant 'REPLACE_WITH_DEV_TENANT_ID'
az account set --subscription 'REPLACE_WITH_DEV_SUBSCRIPTION_ID'
az account show --query '{subscription:name, subscriptionId:id, tenantId:tenantId}' -o table
```

If the browser cannot open from WSL, use:

```bash
az login --tenant 'REPLACE_WITH_DEV_TENANT_ID' --use-device-code
```

Follow the displayed sign-in instructions, then run `az account set` again. If your company disallows device-code authentication, use its supported sign-in method.

The local Blob client tries `AzureCliCredential` first, then `DefaultAzureCredential` with environment credentials excluded. Your dev account therefore needs the Blob permissions from section 2. The Azure Container App's managed identity is a different identity; local success does not validate that deployed identity. [Microsoft: local Python authentication](https://learn.microsoft.com/en-us/azure/developer/python/sdk/authentication/local-development-dev-accounts)

The current model client separately reads an **API key from `config.json`**. `az login` does not replace that key. Likewise, assigning a storage account name in a shell variable does not change the account configured in the application.

## 8. Configure the local Capture runtime

### 8.1 Place the two private files

Recommended beginner setup: keep these files in Capture root:

```text
capture/
  config.json          <- actual dev runtime configuration
  jwt_keystore.p12     <- matching dev keystore
  pyproject.toml
  VERSION
  .venv/
  src/
```

For example, if the team delivered them into your Windows Downloads folder, replace `YOUR_WINDOWS_USERNAME` and the filenames as needed:

```bash
cd "$CAPTURE_ROOT"
cp '/mnt/c/Users/YOUR_WINDOWS_USERNAME/Downloads/capture-dev-config.json' config.json
cp '/mnt/c/Users/YOUR_WINDOWS_USERNAME/Downloads/jwt_keystore.p12' jwt_keystore.p12
chmod 600 config.json jwt_keystore.p12
```

If you must prepare the JSON yourself, start with `cp config.example.json config.json` **only when you do not already have a real `config.json`**, then replace the placeholders using the table below. The example's resource names and empty keys are not usable credentials.

These files are ignored by Capture's `.gitignore`. In a Git checkout, verify this before committing anything:

```bash
git check-ignore config.json jwt_keystore.p12 scripts/test.api.json
```

Expected: all three paths are listed. Do not force-add these files to Git.

### 8.2 Runtime parameter reference

These are **JSON properties**, not automatically recognized environment variable names.

| Property | Value / meaning |
| --- | --- |
| `jwt.keystore_password` | Actual password for the supplied PKCS#12 keystore. Required. |
| `jwt.revoked` | Keep the company dev revocation seed. It initializes local `data/jwt_revoked.json` if absent; later config edits do not overwrite an existing revocation file. |
| `storage.account_name` | Actual dev storage account **name**, without a URL suffix. Required. |
| `storage.chat_container` | Existing dev session/artifact container; default `chat-sessions`. This receives writes during extraction. |
| `storage.config_container` | Existing dev catalog/prompt container; default `agent-config`. |
| `intelligence_contract.enabled` | Set to JSON boolean **`true`**, not the string `"true"`. The checked-in example is disabled. |
| `intelligence_contract.catalog_blob` | Normally `skills/intelligence-contract/catalog.json`, the existing Blob object path. |
| `intelligence_contract.cache_ttl_seconds` | Prompt text cache lifetime; default `300` seconds, minimum `1`. Catalog refresh is separate. |
| `intelligence_contract.max_pdf_bytes` | Maximum PDF size in bytes; default `10485760` (10 MiB). |
| `intelligence_contract.temperature` | Model sampling parameter; default `0.5`. Start with the team's validated value/model combination. |
| `intelligence_contract.view_entity` | Fallback target entity, normally `loanDeposit`; catalog entries can supply their own entity/menu. |
| `azure_openai.endpoint` | Resource endpoint, for example `https://YOUR-DEV-RESOURCE.openai.azure.com`. Use the supplied endpoint, not a full chat-completions request URL. |
| `azure_openai.api_key` | Key for that dev resource. Required for real extraction in the current implementation. |
| `azure_openai.deployment` | Azure deployment name, which may differ from the underlying model name. Required. |
| `azure_openai.api_version` | Keep the working company version; code defaults to `2024-10-21` if omitted/empty. Do not change APIs as part of workstation setup. |
| `mcp.default.server_url` | Reachable dev MCP endpoint, including its configured path such as `/mcp`. The example's localhost address is not a remote dev server. |
| `mcp.default.config_key` | Fernet key matching `MCP_CONFIG_KEY` on that MCP server. Do not generate an unrelated replacement. |
| `mcp.default.label` | Display label, normally `Diapason`. |
| `mcp.default.protocol_version` | Optional existing company override; otherwise request header/default behavior is preserved (`2024-11-05` by default). |
| `sessions.max_turns` | Existing session retention setting; default `30`. Keep the company value initially. |

The original schema also includes Pascal-specific settings such as `ui`, `prompt.system_prompt_blob`, and chat-oriented model settings such as `max_tool_rounds`. Preserve the supplied schema, but those are not switches for Capture's extraction prompt or graph. Capture reads its catalog and extraction prompts from `intelligence_contract` plus `storage`.

### 8.3 Configuration precedence and environment variables

For the file-based path in this guide, run this in the terminal that will start Capture:

```bash
unset CHAT_CONFIG JWT_KEYSTORE_P12_B64
python -m json.tool config.json > /dev/null
```

Expected: no JSON error and no secret values printed. Restart the service after changing configuration.

| Environment variable | Behavior |
| --- | --- |
| `CHAT_CONFIG` | Nonempty value must be the **complete JSON text**, not a filename. Takes precedence over `config.json`. |
| `JWT_KEYSTORE_P12_B64` | Base64 contents of the PKCS#12 file. Takes precedence over `jwt_keystore.p12`. Password still comes from `jwt.keystore_password`. |
| `APP_VERSION`, `APP_REVISION` | Optional build metadata overrides. Leave unset for the normal local setup; health uses `VERSION` and the default revision. |
| `OTEL_*` | Optional company telemetry configuration. No remote telemetry collector is needed for the basic local setup; leave exporter endpoints unset and use terminal logs. |
| `SMOKE_API_CONFIG` | Complete JSON configuration for the **smoke client**, not the service. Overrides the smoke JSON file. |
| `AGENT_URL` | Smoke client's target URL override; use `http://127.0.0.1:8001` for Capture locally. The legacy name does not mean Pascal is required. |
| `SKIP_IC_SMOKE` | Set to `1` on a smoke invocation to skip the extraction POST. It does not disable extraction in the service. |
| `CAPTURE_URL` | Read by **Pascal**, not Capture. Only needed when connecting Pascal to Capture. |

Alternative to local runtime files, if your team uses environment injection:

```bash
export CHAT_CONFIG="$(cat /path/to/private/capture-dev-config.json)"
export JWT_KEYSTORE_P12_B64="$(base64 -w 0 /path/to/private/jwt_keystore.p12)"
```

Replace the two paths. Use either this approach or the file-based instructions consistently. Capture does **not** automatically load a `.env` file. Changing `CHAT_CONFIG` in another terminal does not update an already running process. Do not copy Azure managed-identity endpoint variables or deployment credentials into your local shell.

## 9. Verify Blob access and prompt availability

Connect the company VPN if required. From Capture root, with `.venv` active and the file-based configuration selected:

```bash
python - <<'PY'
from pathlib import Path
from settings import load_config
from blob_client import connect_blob
from capture.workflow.prompts import (
    init_capture_prompts, capture_trade_types,
    get_trade_type_config, get_prompt_text,
)

cfg = load_config(Path.cwd())
storage = cfg['storage']
for key, default in [('chat_container', 'chat-sessions'),
                     ('config_container', 'agent-config')]:
    name = storage.get(key) or default
    _, container, credential = connect_blob(storage['account_name'], name)
    container.get_container_properties()
    print(f'OK: {name}; credential={credential}')

meta = init_capture_prompts(cfg)
types = capture_trade_types()
assert types, 'The catalog has no trade types'
print('Catalog version:', meta['version'])
print('Available trade types:', ', '.join(types))
for prompt in {get_trade_type_config(tt)['prompt_blob'] for tt in types}:
    assert get_prompt_text(cfg, prompt).strip()
print('OK: catalog and referenced trade-type prompts are readable')
PY
```

This checks container access, the catalog, and prompts without calling a model or writing a session. It does **not** prove that you have write permission; a successful full extraction later checks persistence.

The normal Blob layout is:

```text
<storage.config_container>/
  skills/intelligence-contract/catalog.json
  skills/intelligence-contract/prompts/mltLoan.txt
  skills/intelligence-contract/prompts/...
```

If it fails, resolve the reported storage permissions, network access, or missing assets before starting the service. Catalog names such as `mltLoan` are exact identifiers, not translated UI labels. Section 14 explains uploading prompt edits; uploading is unnecessary if the dev assets already exist.

## 10. Start the local API

In **WSL terminal A**, from Capture root:

```bash
cd "$CAPTURE_ROOT"
source .venv/bin/activate
python -m uvicorn capture.asgi:app --host 127.0.0.1 --port 8001 --reload
```

Leave this terminal running. Expected: Uvicorn reports startup complete and listens on `http://127.0.0.1:8001`. A traceback before startup completes means you must fix that error before testing requests.

| Command argument | Why it is present |
| --- | --- |
| `python -m uvicorn` | Uses the active virtual environment's server. |
| `capture.asgi:app` | Imports Capture's actual ASGI entry point. |
| `--host 127.0.0.1` | Binds to local loopback for this development workflow. |
| `--port 8001` | Avoids the port conventionally used by Pascal (`8000`). |
| `--reload` | Restarts when watched Python source files change. |

Always launch from Capture root: the entry point uses the **current working directory** for `config.json`, the keystore, and `VERSION`. Changing a JSON file or a Blob prompt is not the same as changing a watched Python file; use the restart/refresh instructions below.

In **WSL terminal B**, check health:

```bash
curl --fail-with-body --silent --show-error http://127.0.0.1:8001/api/health
```

Expected: HTTP 200 with JSON containing `"status":"ok"` and build information. Health is unauthenticated, but the application still needs to initialize successfully before it can respond. Health success alone does not validate the model or MCP.

In a Windows browser you can normally open:

- `http://localhost:8001/api/health`
- `http://localhost:8001/docs` — generated API documentation, not a Capture product frontend.

Windows can normally access WSL services through localhost. If browser access fails, test with WSL `curl` first to distinguish service failure from Windows/WSL forwarding. [Microsoft: WSL networking](https://learn.microsoft.com/en-us/windows/wsl/networking)

Use **Ctrl+C** in terminal A to stop Capture. Restart using the same command.

## 11. Configure a client to call authenticated endpoints

The service's `config.json` describes its dependencies. A separate private **`scripts/test.api.json`** describes the identity and input used by the smoke client.

In terminal B, enter your Capture checkout, activate `.venv`, and create/open that file in your editor. Use this JSON as a starting point and replace every `REPLACE_...` value and the example numeric IDs:

```json
{
  "agent_url": "http://127.0.0.1:8001",
  "agent_jwt_token": "REPLACE_WITH_CAPTURE_DEV_CHAT_JWT_WITHOUT_BEARER_PREFIX",
  "diapason_api_jwt_token": "REPLACE_WITH_DIAPASON_DEV_API_TOKEN_WITHOUT_BEARER_PREFIX",
  "diapason_base_url": "https://REPLACE_WITH_DIAPASON_DEV_INSTANCE_BASE_URL",
  "diapason_scope": 1,
  "diapason_user_id": 123,
  "diapason_customer_id": 456,
  "trade_type": "mltLoan",
  "intelligence_contract_pdf": "tests/fixtures/sample-loan-contract.pdf"
}
```

`1`, `123`, and `456` are examples, not valid company test identities. If the Capture JWT includes a `customer_id`, it must match the customer ID supplied here. Use the exact dev instance base URL supplied by your team, including any application context path. This is distinct from `mcp.default.server_url`.

`mltLoan` is in the checked-in catalog; verify it appears in the **live dev catalog** from section 9 and exists for your dev instance. The fixture is useful for a first request, but successful reference resolution may require a team-provided sample matching actual dev entities. For another PDF, use a WSL path such as `/home/alice/test-documents/loan.pdf`, not `C:\...`. Do not use `~` in the JSON path; the smoke script does not expand it.

If your team supplies Diapason client credentials, replace the `diapason_api_jwt_token` field with `diapason_client_id` and `diapason_client_secret`. The smoke script then POSTs to `{diapason_base_url}/api/login` and reads the returned API token. This obtains the **Diapason** token only; `agent_jwt_token` is still required. If both client credentials and a static token are supplied, the script uses the login flow.

```bash
chmod 600 scripts/test.api.json
python -m json.tool scripts/test.api.json > /dev/null
unset SMOKE_API_CONFIG
```

Do not rely on an example smoke file being present: the complete starting shape is above. The real path used below is `scripts/test.api.json`, regardless of any old `test/` path wording in the script's help text.

### Headers and form fields used by Capture

The smoke script sets these for you. This table also applies to Postman, an HTTP client, or a company UI calling the service:

| Request part | Value |
| --- | --- |
| `Authorization` header | `Bearer <Capture API JWT>`; `chat` or `admin` role for metadata/extraction. |
| `X-Diapason-User-Id` header | Integer test user ID; required for extraction. |
| `X-Diapason-Customer-Id` header | Integer test customer ID; required for extraction. |
| `X-Diapason-Mcp-Token` header | Diapason API token, without a `Bearer ` prefix; required for extraction. |
| `X-Diapason-Mcp-Scope` header | Integer Diapason scope; required for extraction. |
| `X-Diapason-Mcp-Base-Url` header | Diapason instance base URL; required for extraction. |
| `X-Diapason-Mcp-Protocol-Version` header | Optional company protocol version override, when no config override is set. Usually leave it absent. |
| Multipart `pdf` | Actual PDF file, not its path as a text field. |
| Multipart `trade_type` | Exact catalog trade type identifier. |
| Multipart `debug` | Optional string `true`/`false`; default `false`. |
| Multipart `session_id` | Optional existing session in this identity's scope. Omit for the first request. |
| `X-Diapason-Chat-Session` header | Alternative existing session ID. Nonempty form `session_id` takes precedence. |

Extraction is `POST /api/skills/intelligence-contract`. It uses **multipart form data**, not a JSON request body. Let your HTTP client set the multipart boundary; do not manually set a bare `Content-Type: multipart/form-data` header.

## 12. Run metadata checks, then a full extraction

Keep terminal A's API server running. Run the following in terminal B from Capture root with `.venv` active.

### 12.1 Metadata-only smoke

```bash
AGENT_URL=http://127.0.0.1:8001 SKIP_IC_SMOKE=1 \
  python scripts/smoke_api.py scripts/test.api.json
```

Expected: successful health and metadata checks, a list of trade types, and `All checks passed.` No extraction POST is sent. **The script still resolves/checks the Diapason API token configuration**, and can call `/api/login` if client credentials are configured, even in this mode.

### 12.2 Real PDF extraction

```bash
unset SKIP_IC_SMOKE
AGENT_URL=http://127.0.0.1:8001 \
  python scripts/smoke_api.py scripts/test.api.json
```

This calls Azure OpenAI, calls the company's `resolveReferences` MCP tool, and writes the extraction turn/artifacts into the configured Blob session store. Omitted session IDs create a session, so repeating this smoke can create additional dev sessions. Do not automatically retry a failed POST without considering whether an earlier attempt already wrote its result.

Expected: the script checks HTTP 200, `success=true`, a nonempty resolved `trade_xml`, and the requested trade type in the source XML. It finishes with `All checks passed.` An HTTP 200 with `success=false` is a workflow failure, not a successful extraction.

The current smoke script **always enables extraction debug output** to inspect source XML. Setting `intelligence_contract_debug=false` does not turn it off in this script. Its output can include document-derived text/XML, so use suitable dev samples and keep output private. Its extraction request timeout is 600 seconds; the workflow's MCP resolution call has its own 180-second timeout.

### 12.3 Optional: one request without debug output

For this example, `scripts/test.api.json` must contain a valid static `diapason_api_jwt_token`; this snippet does not perform the alternative client-credential login. Run from Capture root with `.venv` active:

```bash
python - <<'PY'
import json
from pathlib import Path
import httpx

cfg = json.loads(Path('scripts/test.api.json').read_text(encoding='utf-8'))
headers = {
    'Authorization': 'Bearer ' + cfg['agent_jwt_token'],
    'X-Diapason-User-Id': str(cfg['diapason_user_id']),
    'X-Diapason-Customer-Id': str(cfg['diapason_customer_id']),
    'X-Diapason-Mcp-Token': cfg['diapason_api_jwt_token'],
    'X-Diapason-Mcp-Scope': str(cfg['diapason_scope']),
    'X-Diapason-Mcp-Base-Url': cfg['diapason_base_url'],
}
pdf = Path(cfg['intelligence_contract_pdf'])
with httpx.Client(timeout=600.0) as client, pdf.open('rb') as stream:
    response = client.post(
        'http://127.0.0.1:8001/api/skills/intelligence-contract',
        headers=headers,
        data={'trade_type': cfg['trade_type'], 'debug': 'false'},
        files={'pdf': (pdf.name, stream, 'application/pdf')},
    )
print('HTTP status:', response.status_code)
response.raise_for_status()
result = response.json()
print('Session:', response.headers.get('X-Diapason-Chat-Session'))
print('Success:', result.get('success'))
print('Extracted fields:', result.get('extracted_field_count'))
assert result.get('success'), 'Inspect the response locally for message/warnings'
assert result.get('trade_xml'), 'Missing resolved XML'
PY
```

This prints a summary rather than the document/XML. The response's `X-Diapason-Chat-Session` identifies the persisted session. To append a later request to that session, add its value as form `session_id` while retaining the same identity scope. A random or differently scoped session ID produces a 404. Capture does not expose Pascal's session CRUD endpoints.

## 13. Edit and debug with VS Code

### 13.1 Open the WSL project

Install **VS Code on Windows** and its Microsoft **WSL** extension. From Capture root in WSL:

```bash
code .
```

Confirm the window indicates a WSL connection. Install the Microsoft **Python** and **Python Debugger** extensions in that WSL environment when prompted. Use **Python: Select Interpreter** from the command palette and select `${workspaceFolder}/.venv/bin/python`.

Open **Capture root itself** as the VS Code folder for the launch configuration below. Opening the parent repository would give `${workspaceFolder}` a different meaning. [VS Code: developing in WSL](https://code.visualstudio.com/docs/remote/wsl)

### 13.2 Add a local debugger configuration

Create `.vscode/launch.json` in your own checkout with:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Capture local API",
      "type": "debugpy",
      "request": "launch",
      "module": "uvicorn",
      "python": "${workspaceFolder}/.venv/bin/python",
      "cwd": "${workspaceFolder}",
      "args": [
        "capture.asgi:app",
        "--host", "127.0.0.1",
        "--port", "8001"
      ],
      "console": "integratedTerminal",
      "justMyCode": true,
      "env": {
        "CHAT_CONFIG": "",
        "JWT_KEYSTORE_P12_B64": ""
      }
    }
  ]
}
```

This intentionally uses the file-based runtime configuration and a single process. It is ignored by the project's `.gitignore`. If your team requires environment-only secrets, adapt the empty overrides to its debugger secret-injection method instead of using this file-based configuration.

Stop the ordinary Uvicorn process with Ctrl+C first, otherwise port `8001` is already occupied. Put a breakpoint in `src/capture/workflow/graph.py`, select **Capture local API**, and press **F5**. Send a request from terminal B. The debugger should stop in your code. Press F10 to step over a line, F11 to step into a function, or F5 to continue. Restart the debug session after editing code; this launch configuration does not enable reload. [VS Code: Python debugging](https://code.visualstudio.com/docs/python/debugging)

If you pause too long, the requesting client can time out. For offline logic debugging you can also place breakpoints in tests and use VS Code's Python test explorer.

### 13.3 Where to make AI/workflow changes

| File/directory, relative to Capture root | Purpose |
| --- | --- |
| `src/capture/workflow/graph.py` | LangGraph nodes and execution order: validate, extract, resolve, result. |
| `src/capture/workflow/extract_xml.py` | PDF text extraction, model request, XML cleanup, explicit trade-type injection. |
| `src/capture/workflow/prompts.py` | Blob catalog lookup and prompt cache. |
| `src/capture/workflow/xml_fields.py` | Field-counting helpers. |
| `config/catalog.json`, `config/prompts/` | Version-controlled prompt/catalog source assets; see section 14. |
| `tests/test_workflow.py`, `tests/test_extract_trade_type.py`, `tests/test_xml_fields.py` | Starting points for offline workflow regression checks. |
| `src/capture/api/extraction.py` | HTTP adapter and extraction session/artifact persistence. |
| `src/capture/common/` | Preserved company interfaces: authentication, settings, custom MCP transport, Blob/session contracts, and telemetry. |

For AI work, start in `workflow/` and its tests. Keep the existing company JWT, user/customer scope, custom MCP context, and storage contracts intact. The selected `trade_type` is explicit input; the current extraction code injects it into XML rather than asking the model to choose it.

## 14. Develop prompts and change model parameters

### 14.1 Python/model parameter changes

Edit `intelligence_contract.temperature` or the relevant validated `azure_openai` settings in your private `config.json`, then **stop and restart Capture**. These settings are loaded into the runtime; they are not re-read on every request. The current code sends `temperature` on its chat-completions request, so use a compatible deployment and parameter value.

### 14.2 Prompt changes require a Blob update

Editing `config/prompts/mltLoan.txt` locally **does not change the prompt used by the running service**. These local files are upload sources. A process restart also cannot make an unuploaded local edit appear in Blob.

For independent prompt experiments, have the team provide a **developer-specific config container in the dev storage account**, with read/write access. Set only your local `storage.config_container` to that container. It must contain the complete catalog and referenced prompts using the normal paths. Your session container can remain the chosen dev session container.

This uses existing configuration; no Python change is required. Simply moving the catalog under a different Blob prefix is not equivalent isolation: relative prompt paths are still resolved under the fixed `skills/intelligence-contract/` prefix.

Once your chosen container exists:

1. Confirm that `config.json` points to that developer config container. If you intentionally use the shared dev config container, coordinate the edit with the team because its other consumers can read your changes.
2. Edit `config/catalog.json` and/or the intended files in `config/prompts/`.
3. Run the following **from Capture root in WSL**. The first command shows only the upload destination; inspect it before running the second.

```bash
python - <<'PY'
import json
from pathlib import Path
cfg = json.loads(Path('config.json').read_text(encoding='utf-8'))
storage = cfg['storage']
print('Upload account:', storage['account_name'])
print('Upload container:', storage.get('config_container') or 'agent-config')
print('Upload prefix: skills/intelligence-contract/')
PY
```

```bash
bash config/upload.sh "$PWD/config.json"
```

The upload script reads the specified JSON file, **not `CHAT_CONFIG`**. It uploads the catalog and all `.txt` prompt files from this checkout with overwrite enabled. It does not create a container, deploy Python code, or upload `trade.xml`. If you use environment-based runtime config, make sure the upload file describes the same intended storage destination.

4. Restart local Capture to reload the catalog and clear its prompt cache.
5. Repeat the metadata and extraction checks using the same representative input.

Alternatively, with a token carrying the **`refresh` role**, refresh a running local process:

```bash
read -r -s -p 'Dev refresh JWT (without Bearer prefix): ' CAPTURE_REFRESH_TOKEN
printf '\n'
curl --fail-with-body --silent --show-error \
  -X POST http://127.0.0.1:8001/api/refresh-prompt \
  -H "Authorization: Bearer $CAPTURE_REFRESH_TOKEN"
unset CAPTURE_REFRESH_TOKEN
```

A `chat` token is insufficient, and `admin` alone does not replace the explicit refresh role in this dependency. Refresh reloads the catalog and clears prompt text cache; it does **not** upload files or reload `config.json`. Prompt text entries otherwise expire after the configured TTL, but the catalog itself needs refresh/restart. Changing text alone need not change the metadata version: the current catalog declares an explicit `version` value.

## 15. The normal daily loop

Once setup is complete, open Ubuntu, enter your actual checkout, and activate the environment. For the standalone layout:

```bash
cd ~/projects/capture
export CAPTURE_ROOT="$PWD"
source .venv/bin/activate
python -m pytest -q
```

For real integration work, connect VPN, check `az account show`, and sign in again if needed. With the recommended file configuration:

```bash
unset CHAT_CONFIG JWT_KEYSTORE_P12_B64
python -m uvicorn capture.asgi:app --host 127.0.0.1 --port 8001 --reload
```

Use a second terminal for smoke requests. Edit Python, run the relevant tests, and recheck a representative extraction when model/workflow behavior changes. Restart after JSON changes; upload then refresh/restart after prompt changes. Use Ctrl+C to stop the server and `deactivate` to leave the virtual environment.

Before sharing your changes, inspect `git status --short` and `git diff`, run the appropriate tests, and optionally validate packaging:

```bash
python -m build --wheel
```

Do not include private config, keystores, tokens, PDFs, or extraction output in commits. You can push when your changes are ready for review; no push or deployment is required for the edit/test loop itself.

## 16. Optional: connect local Pascal

Capture can be developed directly using its API without Pascal. To validate Pascal's PDF action as well, configure Pascal separately with the same dev JWT trust and compatible session storage, install its own environment, and run both processes in the **same WSL distribution**.

In Pascal's own directory and environment:

```bash
export CAPTURE_URL=http://127.0.0.1:8001
python -m uvicorn pascal.asgi:app --host 127.0.0.1 --port 8000 --reload
```

Pascal also needs its existing `intelligence_contract.enabled=true` and normal company configuration. Pascal's frontend/company host flow still needs the normal authentication/bootstrap context. Setting `CAPTURE_URL` only establishes the backend destination; it does not configure those UI credentials.

A deployed Azure dev Pascal cannot use `http://127.0.0.1:8001` to reach your laptop: that address means its own environment. Likewise, `127.0.0.1` inside a Docker container means that container. Use the direct local API path first; use the team's integration environment for deployed host-to-service routing.

## 17. Troubleshooting by symptom

| Symptom | Check / next step |
| --- | --- |
| `python3.12: command not found` | Confirm you opened Ubuntu 24.04 and completed the Linux package installation. |
| `externally-managed-environment` during pip install | Activate `.venv` and use `python -m pip`; do not install project dependencies into Ubuntu's system Python. |
| `ModuleNotFoundError: capture` or company modules | Run from Capture root, activate its `.venv`, and rerun `python -m pip install -r requirements-dev.txt`. Check `python -c 'import sys; print(sys.executable)'`. |
| Missing `config.json`, `VERSION`, or keystore | Check `pwd`. Launch from Capture root, not `src/` or the parent repository. |
| JSON parsing failure | Run `python -m json.tool config.json > /dev/null`; JSON requires double quotes, no comments, and no trailing commas. Check whether `CHAT_CONFIG` overrides the file. |
| Config edits have no effect | Check environment precedence and restart Capture. Python reload is not a general JSON/secret reload mechanism. |
| Keystore load/password failure | Use a matching dev PKCS#12 file/password; check whether `JWT_KEYSTORE_P12_B64` overrides the file. |
| Azure CLI credential unavailable | Install and sign in to `az` inside WSL. Check `command -v az` and `az account show`. |
| Blob 401/403 | Check signed-in tenant/account, Blob **data** roles on the correct containers, role propagation, and storage network restrictions. VPN does not grant RBAC rights. |
| Catalog/prompt Blob missing | Check account, config container, exact Blob names/case, and uploaded assets. Local `config/` files are not runtime fallback. |
| DNS failure, timeout, or connection refused to a company service | Confirm VPN and connectivity **from WSL**, and ensure config does not still point at the example localhost MCP server. |
| TLS certificate error | Use the company's CA/proxy setup for WSL/Python. Do not work around it by disabling certificate verification. |
| `Address already in use` | Stop the other local server/debugger. Run `ss -ltnp 'sport = :8001'` in WSL to inspect the listener, or choose another port and update client URLs. |
| Health works in WSL but not Windows | Investigate WSL localhost forwarding, VPN, proxy, and firewall behavior; keep WSL curl as the first diagnostic. |
| `/` returns 404 | Expected: Capture has no product homepage. Use `/api/health`, `/docs`, or its API endpoints. |
| Metadata/extraction returns 404 disabled | Set JSON `intelligence_contract.enabled` to `true` and restart. |
| Authentication 401 or missing-bearer error | Check the Capture API token, expiry, issuer/trust, roles, and local revocation data. An Azure login token or Diapason API token is not a substitute. |
| 403 `customer_id mismatch` | Use a request customer ID matching the Capture JWT claim and the intended dev identity. |
| 400 missing MCP/user/customer header | Supply all extraction context headers from section 11. Metadata needs less context than a full extraction. |
| 422 on extraction | Send multipart fields named exactly `pdf` and `trade_type`; do not send a JSON body or a text-only file path. |
| `Azure OpenAI is not configured` (503) | Fill in `azure_openai.endpoint`, `api_key`, and `deployment`; restart. |
| Azure model authentication/deployment/parameter error | Check endpoint/key pairing, actual deployment name, API version, and model support for the configured temperature. `az login` does not fix the API key. |
| `Could not extract text from PDF` | Start with a PDF containing selectable text. The current implementation uses `pypdf` text extraction and has no OCR path for image-only scans. |
| PDF exceeds maximum size | Check `intelligence_contract.max_pdf_bytes`; begin with a small representative PDF. |
| 502, MCP error, or `success=false` | Inspect local response/debug details: MCP key/URL, Diapason token expiry, scope, permissions, entity names, and trade-type support. A synthetic fixture can reference entities absent from dev. |
| Session 404 | Omit session ID to create a new one, or use an existing session belonging to the exact same identity scope. |
| Smoke unexpectedly targets Azure | Use the explicit `AGENT_URL=http://127.0.0.1:8001` prefix shown above. Check `SMOKE_API_CONFIG` precedence and the client JSON. |
| Smoke has no extraction output | Check `SKIP_IC_SMOKE`, the PDF path, and the script output; a metadata-only pass is not a full extraction pass. |
| Smoke health version mismatch | Remove unintended `APP_VERSION` overrides and confirm the client points to the local checkout's server. |
| New prompt text is not used | Verify upload destination, upload the edited file, and refresh/restart. Refreshing before uploading cannot load local edits. |
| Breakpoints do not trigger | Open the WSL checkout, select its Linux interpreter, stop the reload server, use the debugger configuration, and send a request that reaches the node. |
| `upload.sh` reports `\r` / `^M` errors | The shell script has Windows CRLF endings. Save it with LF in VS Code, then rerun it in Bash. WSL Git with `core.autocrlf=input` avoids this for normal checkouts. |

For VPN/DNS problems, company-specific network setup may be required. WSL supports networking options such as mirrored networking and DNS tunneling, but do not assume a Windows-only VPN test proves WSL connectivity. [Microsoft: WSL networking and VPN compatibility](https://learn.microsoft.com/en-us/windows/wsl/networking)

## 18. What still needs Azure dev deployment

Deploy once you need to validate the actual Container App image, managed identity, configured secrets, service-to-service ingress, environment networking, or the company UI's deployed integration. Those properties are not proven by local execution under your own Azure account.

For Python/LangGraph iteration, use the local tests and local API first. Then use the existing dev → test → prod process for release validation.

### Setup completion checklist

- [ ] The WSL virtual environment imports this checkout and offline tests pass.
- [ ] WSL Azure CLI is signed into the intended dev tenant/subscription.
- [ ] Runtime configuration and JWT keystore are present and private.
- [ ] The Blob preflight reads the catalog and all referenced trade-type prompts.
- [ ] Local `/api/health` returns 200.
- [ ] Authenticated metadata lists the expected trade types.
- [ ] A representative real PDF extraction succeeds, returns XML, and persists its session.
- [ ] A breakpoint triggers in the local Capture workflow.
- [ ] You know whether your prompt upload destination is personal or shared.

This document was checked against the repository's current entry points, configuration readers, API handlers, prompt loader, and smoke script. Its embedded JSON and Python heredocs were syntax-checked, and Capture's offline suite passed again (54 tests) using the existing Windows environment. This is not a fresh WSL acceptance run: provisioning a new Windows/WSL machine and accessing company dev resources must still be verified on that machine with its actual credentials and network access.
