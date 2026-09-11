# Capture user stories and commit tasks

Implementation is complete locally; real company deployment acceptance is separate. No commits have been made. Suggested commits are for manual review and grouping.

## User stories

**C1 - Dedicated, deterministic extraction.** As the AI owner, I can extend an explicit LangGraph PDF-to-XML workflow with the original prompts, temperature, explicit trade type and resolver contract intact. Acceptance: validation order, real PDF parsing, exact model/resolver parameters, public/debug/artifact output, failures and repeated catalog refresh. Implemented and verified offline.

**C2 - Both company entry paths.** As a classic UI or Pascal user, I submit the selected PDF/type with my existing identity/session and receive the same extraction result. Acceptance: unchanged multipart/JWT/MCP/scope/session contract and one persisted extraction turn. Direct HTTP and two-container Pascal relay verified with service doubles; actual host/model/MCP/Blob acceptance is external.

**C3 - Independent ACA service.** As a deployment owner, I can build Capture alone and deploy one new app into the existing environment without duplicating shared storage. Acceptance: installed package/image, no Pascal startup/frontend, unchanged company files, scoped Blob grants, separate state, split prompt upload, tests and current inventory. Implemented locally; company plan/deploy is external.

## Commit-sized tasks

| ID / status | Concrete code and purpose | Evidence | Suggested commit |
| --- | --- | --- | --- |
| C-01 Done | `pyproject.toml`, requirements, `asgi.py`, `application.py`: independent src package, original public imports, startup separated from factory import. `common/**` remains unedited. | Import/install, original-file audit, startup and installed Linux ASGI checks. | `build(capture): complete standalone package and ASGI startup` |
| C-02 Done | `workflow/{graph,extract_xml,prompts,xml_fields}.py`: retain original extraction sequence; fix catalog version helper collision; run existing blocking resolver off the event loop. | `test_workflow.py`, original XML/catalog tests, two refreshes, real PDF and exact tool arguments. | `fix(capture): finish LangGraph extraction and catalog refresh` |
| C-03 Done | `api/{extraction,auth,health,middleware,schemas}.py`, `runtime.py`: dedicated original-contract adapters, caller scope and single artifact write; no Pascal system prompt/chat/UI. | `test_api.py`, real JWT/revocation/MCP context, active/cross-user sessions, status/cleanup and artifacts. | `refactor(capture): preserve extraction HTTP and session contracts` |
| C-04 Done | `observability/{ai,routing}.py`, middleware/health: restore private graph tracing context, remove path sets, record content-free telemetry and incoming trace parent. | In-memory exporter, tracing opt-out, redaction, prefixed quiet endpoint tests. | `fix(capture): complete content-free workflow tracing` |
| C-05 Done | Dockerfile, `.github/**`, `deploy/**`, config example, provider lock and ignores: company ACA conventions adapted to Capture, shared containers become data sources, only new app identity grants; prompt-only upload and moved `config/upload.sh` path. | Standalone Linux image, shell syntax, HCL parsing; original asset/config comparison. | `build(capture): add ACA deployment using existing company resources` |
| C-06 Done | `tests/**`, `scripts/smoke_api.py`, inventory generator, README and `docs/**`: workflow/service regressions and extraction-only live smoke. | Full offline suite; two-container direct/relay/shared-artifact acceptance. | `test(capture): verify extraction service and document rollout` |
| C-07 External - company deployment owner | Company helper, `/capture` secrets and GitHub environments, separate backend key, same JWT/storage/MCP/model config; new ACA and two role assignments. | Real reviewed plan/deploy, direct PDF smoke, Pascal relay, classic host prefill and real service/telemetry checks. | Deployment/config repositories owned by the team. |

Original unused `entity_match.py` is not executed or introduced. External `skills/intelligence-contract` names remain compatibility contracts. No model/API migration, new MCP exposure or storage redesign is required.
