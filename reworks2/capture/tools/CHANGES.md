# Complete edit inventory

All authored edits are inside `capture_proposed/capture`. This document supersedes
the inventory for the initial local-development implementation.

## Revision requested: no runtime monkey-patching

The initial `dev/app.py` replaced imported Blob functions and the private settings
cache. That implementation was removed. `dev/storage.py`, the custom filesystem
Blob replacement, was also removed. The remaining tooling moved from `dev/` to
`tools/`; the old command `python -m dev` is no longer supported.

The replacement runs the normal `capture.asgi:app` in a child process with explicit
configuration. Storage calls use the real Azure SDK against Microsoft Azurite.
There are no function replacements, auth dependency overrides or private-cache
writes in the tools or new integration tests. Existing unit-test mocks are unchanged.

## Six existing project files edited in total

| File | Complete change |
|---|---|
| `README.md` | Replaced copied PoC chat/deployment README with Capture setup, connected and offline commands, test instructions and guide/inventory links. Revised local setup to Azurite plus HTTP stubs and normal ASGI execution. |
| `config.example.json` | Enabled intelligence_contract; replaced concrete storage account with a placeholder, empty model key with an explicit placeholder, localhost MCP URL with an ACA placeholder. Removed unused prompt/ui/context blocks, model max_tool_rounds/pricing fields, and docs/defthedge MCP examples. Other keys/values retained; JSON reformatted. No further change in this revision. |
| `.gitignore` | Added default jwt_keystore.p12, .local/, and node_modules/. Existing personal-config patterns retained. |
| `.dockerignore` | Added tests/, tools/, node_modules/, .local/, config.*.json. Replaced the first implementation's dev/ exclusion with tools/. |
| `pyproject.toml` | Registered the integration pytest marker, explaining the local Azurite installation prerequisite. Packaging and dependency definitions unchanged. |
| `src/capture/common/blob_client.py` | Added explicit storage.connection_string support using BlobServiceClient.from_connection_string; optional storage.api_version for that path; reject account-name mismatches. Without a connection string, the existing Azure CLI/managed-identity path is unchanged. This is the only production source file edited. |

## Fourteen added files in the final tree

| File | Purpose / change from the first implementation |
|---|---|
| `tools/__init__.py` | Development utility package; moved from dev/. |
| `tools/__main__.py` | CLI now includes storage and sync-config alongside init/serve/stubs/headers/smoke. Runs ordinary subprocesses; no special patched app factory. |
| `tools/configuration.py` | Explicit offline JSON loading and project-contained paths; validates loopback model/MCP/Blob endpoints and account consistency. Optional path argument enables tests without environment patching. |
| `tools/bootstrap.py` | New: real SDK container/config seeding, local key/VERSION initialization, child environment construction, production ASGI/stub/Azurite commands and process execution. |
| `tools/offline.json` | Dedicated local config. Now selects Azurite using its published development account/key, explicit Blob endpoint and API version 2023-11-03. Scenario path updated to tools/. |
| `tools/stubs.py` | Configurable Azure-style chat-completions and resolveReferences JSON-RPC HTTP fixtures, real Fernet envelope checking, latest request-body captures without headers. Moved and imports updated. |
| `tools/scenario.json` | Configurable model response/status/usage and resolver IDs/status/error/result overrides. Model fixture path updated to tools/. |
| `tools/fixtures/loan.xml` | Same synthetic loan XML, moved unchanged. |
| `tools/smoke.py` | Real HTTP health/metadata/upload client and offline JWT headers or connected headers file. Updated imports; optional explicit config for token generation in tests. |
| `tools/azurite/package.json` | New: private tooling-only npm package pinning Azurite 3.37.0. |
| `tools/azurite/package-lock.json` | New: resolved npm dependency versions/integrity for reproducible npm ci. |
| `tools/README.md` | Moved and updated full connected/offline developer guide; config, authentication, login, Azurite setup/seeding, fixture customization, SDK session inspection, debugging and limitations. |
| `tools/CHANGES.md` | This revised complete inventory. |
| `tests/test_local_integration.py` | Replaces tests/test_offline_dev.py. Eleven cases using separate production Capture, Azurite and stub processes: real extraction/session contract, user scope, auth/revocation/catalog refresh, five failure variants, business-failure reload, real Blob ETags, persistence across restart and config/environment isolation. No monkey-patching. |

Relative to the preceding response, ten dev/ files moved (some revised), two were
removed (app.py/storage.py), bootstrap and the npm manifest/lockfile were added,
and the initial integration test file was replaced. No file from the original
project was deleted. JWT implementation, APIs, LangGraph nodes, extraction logic,
catalog/prompts, requirements and the original 53 tests remain unchanged.

## Generated local artifacts

The existing .venv remains. npm installed tools/azurite/node_modules/ (ignored).
.local contains an offline key, VERSION, revocations, Azurite's persistence files,
request captures, smoke session data inside Azurite, and wheel/build outputs.
Old .local/blobs/ files from the previous filesystem adapter are preserved but
unused by Azurite. Standard build/, .pytest_cache/, __pycache__/ and egg-info
outputs are generated and ignored. Temporary integration state/processes are
cleaned up by tests. No company configuration, keys or access were supplied.

## Verification

- Python 3.12.9, Node 24.13.0, pinned Azurite 3.37.0 on Windows.
- All 64 tests passed: original 53 plus 11 real-process integration cases.
- Live tools storage/init/stubs/serve/smoke path returned HTTP 200, success true,
  9 extracted fields and an original-format session stored via the real Blob SDK.
- Integration tests verify session/key persistence across an actual Capture restart.
- Wheel build passed; its archive contains the new Blob connection support and
  excludes tools, tests and local state. Documentation file links were verified.
- One existing third-party Starlette/AnyIO deprecation warning remains.
- npm audit reports four moderate upstream dependency-tree findings stemming from
  uuid; no high/critical findings. No forced downgrade/override applied. npm tools
  are excluded from the production image and belong in normal dependency review.

Cloud credentials/RBAC, real model accuracy and real Diapason reference mapping
remain unverified without environment access. No image was deployed and deployment
scripts were not changed.

## Documentation revision: Linux runbooks and Azurite recreation

This follow-up changes three documentation files only:

- `README.md`: reorganized into exactly three main sections: project documentation,
  local execution with real cloud services, and local execution with dummy services.
  Includes Linux/Bash setup and commands, every connected configuration field,
  Azure Blob access/uploads, root keystore/JWT, Diapason login/headers, extraction,
  local startup/configuration/inspection and troubleshooting. Added an explicit
  table of maintained npm files versus generated installation/runtime files,
  plus recreation, data reset and intentional dependency-update procedures.
- `tools/README.md`: replaced the duplicate mixed-platform runbook with a short
  index linking to the authoritative Linux sections in the root README.
- `tools/CHANGES.md`: added this precise follow-up inventory and verification record.

No application, test, configuration or dependency code changed in this follow-up.
Verification was rerun: 64 tests passed; npm ci recreated the pinned installation;
the full storage/init/stubs/serve/smoke path returned HTTP 200, success true and
nine extracted fields. The fresh session was read back through the Blob SDK and
contained two turns plus successful extraction artifacts and resolved XML.
README Bash syntax was checked with Ubuntu/WSL; embedded Python/JSON and document
file links were checked too. Complete application execution was verified on the
available Windows host, not on a fully provisioned Linux environment.

Generated artifacts include the recreated ignored node_modules tree, emulator
smoke data/request captures, test caches and `.local/readme-linux-syntax.sh` used
for documentation validation. Verification servers were stopped afterward.
