# Diapason-agent / Pascal sprint

## Technical user stories

**P1 - Readable agent loop.** As a data scientist, I can follow model -> tools -> model decisions in typed graph state. Acceptance: unchanged prompt/history/deployment/temperature, request-scoped discovery/filtering, sequential tools, allowed-name enforcement and configured round behavior; JSON/SSE share the graph while preserving their existing differences. Implemented; differential tests execute original functions for comparison.

**P2 - Preserve user/host contracts.** As a chat user, I retain routes, headers, event order, sources, charts, session history and usage. Acceptance: all original routes/model schemas and company files remain; real JWT roles/revocations and user/customer/session isolation are tested; MCP auth/transport are unchanged. Implemented offline. Original frontend and local upload behavior remain until the cross-service cutover.

**P3 - Observable workflow without content export.** As the AI owner, I can inspect correlated model/tool/workflow spans and numeric usage without conversation or payload exposure. Acceptance: existing provider/destinations, content-free stage attributes and errors, no extra backend/metrics receiver/checkpointer, and live delta delivery before model completion. Implemented and tested offline.

## Commit-sized tasks

Code/test completion is separate from live integration acceptance. No commits were made.

| ID / status | Exact files/functions and purpose | Verification | Suggested commit message |
| --- | --- | --- | --- |
| P-01 Done | `src/pascal/company/**`, frontend/static/locales/config/system prompt: preserve company files and public imports. | Original-byte audit, real JWT/MCP tests, installed wheel imports. | `chore(pascal): package unchanged company boundaries under src` |
| P-02 Done | `src/pascal/agent/graph.py::{ChatState,create_chat_graph,run_chat,stream_chat}`: shared model/tool loop. | 20 original-loop comparisons; live deltas, stream close/retry/usage and configured limits. | `refactor(pascal): share LangGraph chat orchestration` |
| P-03 Done | `src/pascal/agent/{service,context,routing,discovery,mcp,charts}.py`: split orchestration, prompts/history and existing tool behavior. | Original helper AST comparisons and actual JSON/SSE/history/usage tests. | `refactor(pascal): split agent responsibilities out of app` |
| P-04 Done | `src/pascal/api/*.py`, `application.py`, `runtime.py`, `asgi.py`: route modules and explicit dependencies replace root app globals. | All original routes/dependency signatures/schemas audited; startup config/prompt loaders tested. | `refactor(pascal): assemble the existing API from focused modules` |
| P-05 Done with migration exception | `src/pascal/compat/capture/*.py`, `api/capture.py`: preserve current upload until company routing exists. | Workflow equality after import normalization, extraction HTTP/security tests. | `refactor(pascal): isolate temporary Capture compatibility` |
| P-06 Done | `src/pascal/observability/{ai,http}.py`, AI stage call sites: content-free telemetry on the existing provider. | Parent trace/tokens/error redaction/LangSmith opt-out tests. | `feat(pascal): organize content-free agent tracing` |
| P-07 Done | `pyproject.toml`, requirements, Dockerfile, `tests/**`, README and `docs/**`: independent install and handoff. | Full tests, wheel install smoke, inventory and original-source audit. | `chore(pascal): deliver the src package and verification` |
| P-08 Deferred - deployment details | `src/pascal/runtime.py::build_azure_client`: sole constructor to Azure v1 after same deployment is verified. | Live JSON/SSE/tools/model parity. | `refactor(pascal): use the confirmed Azure v1 endpoint` |
| P-09 Deferred - external integration | Remove `src/pascal/compat/capture/` after company routing/MCP exposure is ready. | Classic upload, explicit Pascal action, automatic tool path and existing identity/session semantics. | `refactor(pascal): remove local Capture after company cutover` |

Original catalog-refresh/source-filter behavior and other proposed business improvements remain separate follow-up work.
