# Pascal / Capture migration result

The two projects are independently installable and buildable. Pascal owns the LangGraph chat agent and unchanged frontend; Capture owns the LangGraph intelligence-contract workflow. Pascal's existing PDF action now calls Capture over HTTP. There is no local extraction fallback in Pascal.

No commits, registry pushes or Azure deployments were performed. The project implementation and offline validation are complete; the company environment still needs the deployment and live acceptance steps described below.

## Verification on 2026-09-11

| Check | Result |
| --- | --- |
| Pascal suite | **90 passed, 7 strict expected failures**. The seven source-filter failures were reproduced against the original source. |
| Capture suite | **54 passed**. |
| Original/protected baseline | **127 files unchanged**, including the original checkout and existing company implementations in both projects. Every `dia_jwt` file remains unchanged. |
| Original helper comparison | 21 agent helpers have equivalent AST after removing explicit runtime relocation; prompt composition's explicit config parameter and content-free MCP telemetry are the reviewed differences. |
| Frontend | Original sources and lockfile preserved byte-for-byte; `npm ci` and `npm run build` succeed. |
| Wheels | Both build successfully; company code and locales are included once under their original public imports. Pascal has no extraction package. |
| Linux containers | Both independent Docker builds succeed. |
| Two-container acceptance | Installed ASGI entry points, actual HTTP relay/direct Capture upload, real fixture PDF through the graph, shared original Blob record/turn helpers, single artifact write, JSON/SSE chat, repeated refresh and caller scope all pass with offline model/MCP/Blob doubles. |
| Deployment files | Bash syntax checks pass for both deploy/config scripts and Capture's moved upload script. HCL/provider-lock and CI YAML syntax parse. Real infrastructure planning requires the existing company helper and environment. |
| Static Python check | No undefined-name/local-reference errors under Ruff F821/F822/F823. |

The working dependency resolution used Python 3.12, LangGraph 1.2.11, FastAPI 0.141.1 and OpenAI 3.13.0. Existing dependency lower bounds and AzureOpenAI configuration conventions are retained; this report records tested versions rather than claiming a new lock policy.

## Requirement audit

| Objective | Delivered evidence |
| --- | --- |
| Independent projects with LangGraph | Separate `pyproject.toml`, requirements, ASGI factories/entry points and Docker contexts. `pascal/src/pascal/agent/graph.py` and `capture/src/capture/workflow/graph.py` execute in the tests and installed images. |
| Move intelligence-contract out of Pascal | `pascal/src/pascal/integrations/capture.py` and `api/capture.py` relay only. No local workflow/prompt loader/compatibility package or `pypdf` dependency. Capture alone executes extraction/resolution. |
| Preserve prompts, parameters, rules, tools, responses and streaming | Original-loop differential tests, exact model/resolver argument checks, real PDF/XML tests, unchanged prompt/frontend assets, schema/route comparisons, live-delta and JSON/SSE API checks. |
| Preserve JWT, tenant/user scope, MCP and storage | No edits to company modules; real JWT/roles/revocation and scope tests; per-caller encrypted MCP context checks; original session/artifact helpers exercised across two containers. |
| Classic UI and explicit Pascal action | Both direct Capture HTTP and the unchanged Pascal upload endpoint are verified. Actual host selection/prefill behavior requires the company host; no frontend or MCP-server redesign was introduced. |
| Missing package/config/infra/deploy material | Restored from the original where applicable. Capture adds one ACA/identity with grants to existing containers; Pascal retains the original app/infrastructure/state conventions. |
| Fix migration mistakes | Broken/stale imports and missing ASGI/private-graph context restored; catalog version collision fixed; moved upload path corrected; duplicate wheel data eliminated. |
| Remove hardcoded logging path lists | HTTP errors omit payload details on all routes. Quiet successful routes declare `@quiet_access`; prefix behavior is tested. No quiet/AI path registry remains. |
| Current user stories and code-sized tasks | Separate [Pascal sprint](pascal/docs/SPRINT.md) and [Capture sprint](capture/docs/SPRINT.md), with implementation versus external acceptance clearly distinguished. |
| Current Python provenance | [Pascal inventory](pascal/docs/PYTHON_INVENTORY.md): 18 new / 20 untouched / 24 reworked. [Capture inventory](capture/docs/PYTHON_INVENTORY.md): 15 new / 15 untouched / 19 reworked. Counts include tests/scripts. The workspace-only `tools/verify_containers.py` is new. |
| Explain remaining deployment work | [Deployment handoff](pascal/docs/DEPLOYMENT.md), also included independently in Capture. |

`Untouched` in the inventories means original-equivalent source text, including copies that already had different line endings/final newlines before this continuation. The baseline audit separately proves those existing copies were not edited during this work.

## Remaining company steps

1. Provide the existing deployment helper/ACA module and environment secrets to the two repositories/runners. Keep Pascal's existing backend state and physical app name.
2. Deploy one Capture ACA with a separate state key, existing-format config/JWT trust, the same session/config containers and working MCP/AzureOpenAI settings. Its identity needs the two Blob grants declared in Capture's infrastructure.
3. Set Pascal's `CAPTURE_URL`; keep the existing extraction feature flag enabled in both apps. Existing UI URLs can use Pascal's relay. If the classic UI should reach Capture directly, update only its host/proxy destination while preserving the current headers and fields.
4. Review the real plans and run the supplied live smokes plus host PDF/trade-type/prefill/session acceptance. Reuse the existing revocation, ingress-timeout and telemetry practices for both apps.

No additional database, model resource, MCP tool registration, queue or graph persistence service is required by this implementation. Live Azure/model/MCP/Blob/host behavior has not been claimed verified by offline doubles.

## Reproduce the workspace container check

Run each project's unit tests from its own directory and environment. Build Pascal's frontend first, then from this workspace root:

```bash
docker build --build-arg APP_VERSION=0.1.0 --build-arg GIT_REVISION=local-verification -t diapason-pascal:local pascal
docker build --build-arg APP_VERSION=0.1.0 --build-arg GIT_REVISION=local-verification -t diapason-capture:local capture
# Use a Python environment with either project's development dependencies.
python tools/verify_containers.py
```

The verifier creates temporary local containers/network and test credentials, mounts the test bootstrap only for this check, and removes the containers/network on exit. It never calls the company environment. `.migration/` holds local audit/build artifacts and is ignored; it is not part of either delivered project.
