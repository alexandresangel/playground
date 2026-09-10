# Capture sprint

## Technical user stories

**C1 - Deterministic extraction.** As a data scientist, I can inspect the original PDF-to-XML sequence as explicit graph stages. Acceptance: PDF checks precede catalog checks; prompt load precedes PDF decoding; original prompt/model parameters and explicit trade type are retained; only the original reference-resolution call runs; result/debug/session artifacts match the original. Implemented; covered by workflow and original-result parity tests.

**C2 - Independent company-compatible service.** As an integration owner, I can package Capture alone and call the established extraction contract. Acceptance: existing JWT roles/binding, multipart fields, errors, response/session header, catalog keys and MCP forwarding remain; Docker context has no parent imports; Capture contains only extraction and its required company boundaries. Packaging and offline contract checks implemented; live host routing and model access are external acceptance.

**C3 - Content-free AI observability.** As a workflow owner, I can see stage latency, outcome and available model token usage in existing traces. Acceptance: original telemetry bootstrap/destinations stay intact; child spans retain correlation; no graph/prompt/PDF/XML/tool/credential content is exported; automatic graph tracing is disabled. Implemented and exporter-tested offline.

## Commit-sized tasks

Code/test completion is separate from live integration acceptance. No commits were made.

| ID / status | Exact files/functions and purpose | Verification | Suggested commit message |
| --- | --- | --- | --- |
| C-01 Done | `src/capture/company/**`: byte-preserved JWT/MCP/storage/config/telemetry and locales; package existing public imports. | Source hashes, real-JWT security tests and installed-wheel import checks. | `chore(capture): package unchanged company boundaries under src` |
| C-02 Done | `src/capture/workflow/{graph,extract_xml,prompts,xml_fields}.py`, `config/**`: typed extraction stages and original assets. | PDF/XML/validation/model/resolver tests, original result comparisons and nine asset hashes. | `refactor(capture): organize the deterministic extraction workflow` |
| C-03 Done | `src/capture/api/{extraction,auth,health,middleware,schemas}.py`, `application.py`, `runtime.py`, `asgi.py`: dedicated workflow service, no Pascal startup/UI/session CRUD. | HTTP auth/scope/headers/errors/artifacts; startup without system prompt; normalized extraction AST. | `refactor(capture): isolate the workflow service and HTTP adapters` |
| C-04 Done | `src/capture/observability/{ai,http}.py`, model/workflow span call sites: content-free correlated AI traces. | In-memory exporter tests, token/outcome/duration assertions, redaction and tracing opt-out. | `feat(capture): keep workflow tracing inside the Capture package` |
| C-05 Done | `pyproject.toml`, requirements, Dockerfile, `tests/**`, README and `docs/**`: standalone package and clear handoff. | Full tests, fresh wheel build/install smoke, original/asset audit and inventory. | `chore(capture): deliver a clean src project and handoff` |
| C-06 Deferred - deployment details | `src/capture/runtime.py::build_azure_client`: replace the sole original constructor after same-deployment v1 compatibility is verified. | Real extraction model/temperature/credential parity. | `refactor(capture): use the confirmed Azure v1 endpoint` |
| C-07 Deferred - external owner | Company host/proxy/MCP files absent here: connect classic UI, Pascal explicit action and authorized automatic tool path. | Three deployed paths with PDF/trade type, identity/session and host prefill preserved. | Company integration repository decides. |

Original catalog-refresh/source-filter behavior and other proposed business improvements remain separate follow-up work.
