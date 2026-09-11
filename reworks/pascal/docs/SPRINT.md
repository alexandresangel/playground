# Pascal user stories and commit tasks

Implementation is complete locally; company deployment acceptance is separate. No commits have been made. Suggested commits below are for manual review and grouping.

## User stories

**P1 - Maintainable chat orchestration.** As the AI owner, I can develop the agent in a typed LangGraph loop while retaining original prompts/history, model parameters, per-caller tool selection, results and streaming. Acceptance: JSON/SSE round-limit, model argument, history and usage tests; original-loop differential comparisons; a delta is delivered before the model completes. Implemented and verified offline.

**P2 - Remote contract extraction.** As a Pascal user, I select the existing PDF/trade-type action and receive Capture's result in my existing session and host prefill flow. Acceptance: unchanged frontend, fields/headers/status/body/session contract; real caller validation; one write in Capture; no local extraction or PDF dependency. API and two-container acceptance verified with service doubles; real host prefill remains an environment check.

**P3 - Independent service with company boundaries preserved.** As a deployment owner, I can build and deploy Pascal using the original conventions and one new Capture connection. Acceptance: original company modules and infrastructure preserved, independent installed package/image, original frontend build, documented state/secret/routing requirements, current inventory and tests. Implemented locally; real Azure plan/deploy remains external.

## Commit-sized tasks

| ID / status | Concrete code and purpose | Evidence | Suggested commit |
| --- | --- | --- | --- |
| P-01 Done | `pyproject.toml`, requirements, `asgi.py`, `application.py`: package the existing `commun` modules under their public imports; remove eager factory-module startup. No company-file edits. | Install/import, startup tests, original-file audit, installed Linux ASGI check. | `build(pascal): restore independent package and ASGI entrypoint` |
| P-02 Done | `agent/{graph,service,context,routing,discovery,mcp,charts}.py`, `api/{chat,sessions,schemas}.py`: retain/split existing agent behavior around the shared graph. | `test_chat_graph.py`, `test_api.py`, original schema/route and source tests. | `refactor(pascal): retain chat behavior through LangGraph` |
| P-03 Done | New `integrations/capture.py`, `api/capture.py`; `runtime.py` and `api/health.py`: remove stale compatibility imports, relay metadata/upload/refresh and keep original caller/session contract. | `test_capture_proxy.py`: exact PDF/fields/headers, real auth, statuses, timeout/no retry/no write. Two-container shared-session acceptance. | `feat(pascal): route contract actions to Capture ACA` |
| P-04 Done | `observability/{ai,routing}.py`, `api/middleware.py`, health annotations: restore missing private graph context, eliminate hardcoded quiet/AI path sets, propagate traces. | Content/exception redaction, tracing opt-out, incoming parent trace, quiet prefixed route, live deltas. | `fix(pascal): complete graph tracing and route-owned logging` |
| P-05 Done | Original `frontend/**`, `static/**`, `system_prompt.md`, `VERSION`, config example, Terraform/provider lock restored; Dockerfile, CI/deploy scripts and ignores adapted. `deploy.sh` accepts Capture env values. | Original-byte audit, `npm ci` + build, Linux image and shell syntax checks. | `build(pascal): restore UI and company deployment files` |
| P-06 Done | `tests/**`, `scripts/smoke_api.py`, inventory generator and `docs/**`: portable regressions, original smoke, provenance and exact deployment handoff. | Offline suite; seven strict baseline source-filter expected failures independently reproduced in original. | `test(pascal): cover migration contracts and document cutover` |
| P-07 External - company deployment owner | Existing company helper/runner/Infisical/state: deploy Capture first, set `CAPTURE_URL`, plan/deploy Pascal under its existing app/state. | Review real plan, live smoke with PDF, host mentions/prefill/session and real model/MCP/Blob/telemetry. | Deployment/config repositories owned by the team. |

No deferred local Capture removal remains: the local extraction implementation is absent. Do not turn the explicit PDF action into an invented MCP tool. Source filtering improvements, model/API migration and infrastructure redesign remain outside this migration.
