# Capture: remove application Blob Storage

Date: 2026-09-16

Scope: all edits are inside `ai-capture/`. This change removes Capture's
configuration and chat-session storage dependencies. It does not perform the
remaining Agent-to-Capture renaming or change the extraction prompts, catalog,
XML template, model behavior, MCP resolver contract, or authentication policy.

## Resulting behavior

- Startup reads `<service root>/config/catalog.json`. Catalog prompt references
  resolve under the same local `config/` directory, using UTF-8. Absolute prompt
  paths and paths escaping that directory are rejected.
- Docker explicitly copies `config/` to `/app/config/`. The Docker ignore rules
  include configuration content, including Markdown prompts. The root
  `config.json` remains excluded; runtime secrets still use `CHAT_CONFIG` and
  `JWT_KEYSTORE_P12_B64`.
- Prompt caching and catalog version calculation remain. The refresh endpoint
  rereads the local catalog and clears the cache. ACA configuration changes need
  an image rebuild and deployment; refresh does not fetch remote content.
- Capture no longer creates, looks up, or writes sessions, chat turns, or
  extraction artifacts. It has no replacement database, file store, or in-memory
  session store. Pascal owns chat persistence.
- The form `session_id` and `X-Diapason-Chat-Session` header remain correlation
  inputs. A nonblank form value takes precedence, then the header, then a new
  UUID. The response echoes the ID. IDs no longer require a Capture session or
  produce an unknown-session 404. They do not authorize access to stored data.
  Existing JWT, customer, user, and MCP checks remain.
- The internal `session_artifacts` bundle is removed. Existing public extraction
  fields, debug output, and tool traces remain, with the prompt reference renamed
  from `prompt_blob` to `prompt_path` in extraction details and tool arguments.
- Completion telemetry keeps identity, correlation, and outcome attributes but
  no longer creates storage paths or URLs. Existing OpenTelemetry export and JWT
  revocation handling are unchanged.

## Modified files

| File | Edit |
| --- | --- |
| `.dockerignore` | Remove obsolete skill-config exclusions; explicitly include root `config/` content; exclude retained validation/build artifacts. |
| `.gitignore` | Exclude the retained `.validation/` directory (the existing `build/` exclusion remains). |
| `Dockerfile` | Explicitly copy root `config/` into the runtime image. |
| `config.example.json` | Remove `prompt.system_prompt_blob`, `sessions`, `storage`, and `intelligence_contract.catalog_blob`; retain other settings. |
| `config.json` | Apply the same removal to the existing local configuration, preserving other values and its line endings. |
| `requirements.txt` | Remove `azure-storage-blob` and its now-unused authentication dependency `azure-identity`. |
| `pyproject.toml` | Remove deleted `blob_client` and `session_store` modules from packaging. |
| `deploy/deploy.sh` | Remove application storage-account/container settings, required-value check, and Terraform arguments. |
| `deploy/infra.tf` | Remove application storage variables, storage-account lookup, two container resources, six storage role assignments, legacy storage move blocks, storage scopes, and the explicit identity request used for storage. |
| `src/capture/workflow/prompts.py` | Replace remote catalog/prompt reads with local files rooted at the service directory; retain catalog mapping, versioning, cache, and refresh behavior. |
| `src/capture/workflow/extract_xml.py` | Consume and return the local `prompt_path` reference. |
| `src/capture/workflow/graph.py` | Use `prompt_path` in tool traces; remove the persistence-only artifact bundle. |
| `src/capture/runtime.py` | Remove session-store initialization, runtime field, lookup/error helpers, and the locale helper used only to compose stored turns; pass the service root to the catalog loader. |
| `src/capture/api/extraction.py` | Remove session lookup/write operations and stored chat-message composition; retain correlation IDs and response/client-cleanup behavior. |
| `src/capture/api/health.py` | Pass the runtime's service root when refreshing local configuration. |
| `src/capture/observability/http.py` | Stop adding session-storage paths and URLs to spans. |
| `src/capture/common/telemetry.py` | Remove the storage-path and URL helpers. |
| `tests/conftest.py` | Remove the session-store test double; construct a runtime without persistence. |
| `tests/container_bootstrap.py` | Remove local storage doubles; use bundled config with the existing offline model/MCP doubles. |
| `tests/test_api.py` | Replace persistence/lookup assertions with stateless extraction and correlation-ID checks, covering both API routes. |
| `tests/test_capture_catalog.py` | Assert `prompt_path` instead of `prompt_blob`. |
| `tests/test_runtime.py` | Test actual startup with local catalog/prompts, no storage settings, and a different working directory. |
| `tests/test_workflow.py` | Read real local prompts; test file-backed cache refresh; replace artifact-persistence assertions. |
| `tests/test_observability.py` | Verify completion correlation attributes contain no storage links. |
| `tests/test_telemetry_helpers.py` | Remove storage URL coverage; retain cost, preview, and CSV tests. |
| `README.md` | Replace storage/upload instructions with bundled configuration, stateless correlation, deployment, and telemetry behavior; link this record. |

The wheel build also regenerated these pre-existing, ignored metadata files so
they no longer reference the removed dependencies, modules, or session tests:

| File | Edit |
| --- | --- |
| `src/capture/common/ai_capture.egg-info/PKG-INFO` | Regenerate dependency metadata. |
| `src/capture/common/ai_capture.egg-info/requires.txt` | Regenerate dependency list. |
| `src/capture/common/ai_capture.egg-info/SOURCES.txt` | Regenerate source/test inventory. |
| `src/capture/common/ai_capture.egg-info/top_level.txt` | Regenerate top-level module list. |

## Added files

| File | Purpose |
| --- | --- |
| `tests/test_local_config.py` | Cover bundled prompt readability, missing/empty/invalid local files, path containment, and authenticated refresh/cache invalidation. |
| `BLOB_STORAGE_REMOVAL.md` | This change record. |
| `.validation/FILES.md` | Complete file inventory for the retained validation/build artifacts described below. |

## Removed files

| File | Reason |
| --- | --- |
| `src/capture/common/blob_client.py` | Azure Blob client is no longer used. |
| `src/capture/common/session_store.py` | Capture no longer persists chat sessions. |
| `config/upload.sh` | Configuration is shipped in the image. |
| `deploy/deploy-config.sh` | Separate configuration upload is obsolete. |
| `tests/test_session_summary.py` | Tests only the removed persistence implementation. |
| `src/capture/common/__pycache__/blob_client.cpython-312.pyc` | Remove pre-existing compiled storage code. |
| `src/capture/common/__pycache__/session_store.cpython-312.pyc` | Remove pre-existing compiled session code. |
| `tests/__pycache__/test_session_summary.cpython-312-pytest-9.1.1.pyc` | Remove compiled tests for deleted code. |

No files were moved or renamed. `config/catalog.json`, all files under
`config/prompts/`, and `config/trade.xml` are unchanged.

## Deployment boundary

The shared `azurerm` Terraform backend remains unchanged. It stores deployment
state; it is not accessed by the Capture application. Migrating the organization's
Terraform backend or shared deployment helper is outside this application-storage
removal and would require changes beyond this repository.

No Azure resources, existing containers, or Terraform state were changed during
this work. Before applying against any existing state, inspect the plan: removing
managed container resources from configuration can schedule their deletion. If
that state contains Pascal/shared containers, transfer or detach their ownership
from Capture's state before applying; retain the containers and their data.
Do not apply this change using Pascal's deployment state.

Inherited application naming, frontend build references, smoke-script references,
and unrelated README sections were left in place to keep this change scoped.

## Validation

- Python 3.12 test suite: **56 passed**. Tests used local doubles for model/MCP
  calls; no live extraction services were contacted.
- `python -m build --wheel --no-isolation`: passed. Inspected the wheel to confirm
  the deleted storage modules and Azure storage/identity dependencies are absent.
- Installed the wheel into an isolated directory inside this repository. Ran the
  real ASGI startup with bundled config and test JWT credentials, local catalog
  metadata/refresh, and authenticated sample-PDF extraction through both API
  routes. Model/MCP calls used the existing offline bootstrap doubles. Passed.
- The installed-package check blocked legacy storage and Azure storage/identity
  imports and observed no import attempts. A before/after file snapshot confirmed
  the requests did not write files. Auth initialization remains unchanged.
- `bash -n deploy/deploy.sh`: passed.
- Searched source, configuration, deployment scripts, and dependency metadata for
  remaining application storage references; none remain outside this historical
  record and explanatory documentation.
- A Docker build/run was not performed because the local Docker daemon is not
  running. Terraform plan/apply was not performed: Terraform and the shared
  deployment helper/module are unavailable in this checkout. No deployment was
  attempted.

Validation created `.validation/` dependencies, test credentials, the built wheel,
package installation, logs, and app files, plus the generated `build/` directory.
Both directories remain because automatic approval review rejected their deletion
with the reason "blocked by policy", including a retry using verified absolute
paths. Both are excluded from Git and Docker. Their complete file inventory is
recorded in [.validation/FILES.md](.validation/FILES.md); these are generated
validation artifacts, not application additions. No global packages were installed,
and all temporary files were confined to this repository.
