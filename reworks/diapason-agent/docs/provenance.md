# Pascal code provenance — 2026-09-08

The original repository remains the implementation reference; all reworks are pending. Paths in the
reference column are relative to the original root. The read-only `reworks/audit_provenance.py`
compares selected file bytes and top-level AST definitions. Package markers are new scaffolding.
Retained behavior does not imply every refactored file is byte-identical.

## Production Python inventory

Current paths are under `src/pascal` unless stated otherwise.

| Current file/section | Classification / original reference | Disposition |
|---|---|---|
| security/jwt.py | Retained, byte-identical to dia_jwt/auth.py | Full JwtAuth/token validation/mint/revoke implementation |
| security/deps.py | Refactored from dia_jwt/fastapi.py | Identity and instance parser AST-identical; injected config in jwt_deps; package imports updated |
| security/setup.py | Refactored from auth_setup.py | Revocation normalization/init/build definitions AST-identical; app factory configure_auth boundary changed |
| tools/audience.py | Retained, byte-identical to tool_audience.py | Technical/audience/mention filtering |
| tools/sources.py | Retained definitions from source_extract.py | All 17 top-level functions AST-identical; import path changed |
| tools/context.py | Refactored from mcp_context.py | Fernet encryption/header/name helpers retained; scoped credential fingerprint and opt-in Capture headers added; old protocol/unused aliases removed |
| tools/registry.py | Refactored from app.py discovery/catalog logic | Async paged bounded TTL/LRU catalog, scoped cache keys, dedup and bound definitions |
| tools/routing.py | Refactored from app.py command/mention routing | Deterministic selection, ambiguity failures, unknown @ treated as prose; direct commands isolated |
| sessions/blob_store.py | Refactored from session_store.py | Existing Blob paths/schema/ETag/delete/list/CAS structure retained; changes detailed below |
| i18n/__init__.py | Retained, byte-identical to i18n.py | Locale normalization/translation/instruction functions |
| i18n/locales/*.json | Retained locale contract copies | Old ic.* strings remain to match the frozen frontend; no feature framework implied |
| build_info.py | Refactored from build_info.py | health definition retained; load supports package/container environment identity |
| config.py | Refactored from settings.py plus added AgentLimits | Explicit config input and validated context/model/tool/admission limits |
| adapters/model.py | Refactored from original app.py Azure calls | Local SDK factory, async stream/tool fragments/usage, explicit retries/timeouts/close; no model version upgrade |
| agent/graph.py | Added graph replacing both manual app.py agent loops | Model/tools nodes, scoped dispatch, bounded rounds/context/results, safe tool failures; one behavior for JSON/SSE |
| agent/service.py | Added turn owner replacing handler-owned execution | Preparation/admission/session exclusion, producer/queue/deadline, partial status and one finalization path |
| agent/state.py | Added | Typed graph state and turn/model/tool/result data structures; runtime resources outside state |
| agent/budget.py | Added over original ad-hoc truncation | Whole-turn pruning/token and cost bounds, transparent estimates |
| agent/prompt.py | Refactored from prompt_loader.py and app.py prompt assembly | Snapshot/hash/refresh, local Blob read, stable prefix then locale/time, no duplicated tool schema summary |
| ports.py | Added | Small injectable model/MCP/store interfaces for tests and future adapters |
| mcp/host.py | Added, replaces mcp_rpc.py/first rework custom client | Pool owner and explicit server-scoped client creation |
| mcp/client.py | Added SDK integration | Initialize/negotiate/notify/execute/teardown via official SDK, operation-scoped client/session |
| mcp/transport.py | Added HTTP safety/ownership boundary | Borrowed sockets, isolated cookies, bounded raw/decoded body, ambiguous JSON-RPC error rejection |
| api/chat.py | Refactored from app.py JSON/SSE endpoints | Both delegate to ChatService; same wire events/paths/session header |
| api/sessions.py | Refactored from app.py session routes | Same contracts; synchronous store work off-loop |
| api/system.py | Refactored from app.py health/i18n/admin/prompt/MCP routes | Preserved auth/locale interfaces; readiness added; compatibility health alias isolated |
| api/capture_bridge.py | Refactored from original Capture HTTP handlers | HTTP to independent ACA, no extraction; minimal receipt through ChatService |
| compatibility.py | Added boundary for retained external names | Old URL/health field/private-record filter and ordered Grafana log prefix |
| observability/events.py | Refactored from telemetry.py/app.py completion events | Content-free outcome/cost/token fields, exact legacy prefix then additive metrics/correlation |
| main.py | Added composition/lifespan replacing app.py startup globals | Own clients/graph/store/prompts/routers; no import-time credentials/network |
| Package __init__.py files | Added markers | No old-path re-export modules |

## Retained session code versus deliberate changes

AST-identical top-level helpers include _now, _session_key, _deleted_session_key, _new_record,
_record_matches_scope, _normalize_usage, _llm_turns, _has_assistant_response, _summary, _encode,
_decode and create_session_store. BlobSessionStore remains derived, not an unchanged copy.

Changed sections: initial missing-record update now applies the pending append; tool-trace
normalization permits a sanitized error code; source extraction imports move; turns_for_client uses
a named compatibility filter; the old artifact-heavy private normalizer is replaced by a minimal
`capture_receipt` containing operation/trade_type/success. New records may contain this **additive
optional metadata**. Existing records are read without rewriting/backfilling their old private
`skill_run` field, which is stripped from public output. Core conversation fields and scope stay
compatible. Global sync write lock, ETag policy, list cost and crash/cross-replica limitations remain.

## Duplicated local modules, tests and operational files

Inside `src/pascal`, `adapters/azure_openai.py` (v1/dated factory), `adapters/blob.py` (original
credential helper), `adapters/diapason.py` (sibling project's direct resolver),
`observability/telemetry.py` (legacy-compatible OTLP and metrics) and `api/guards.py` (ASGI guards)
are byte-identical copies of Capture's files at matching relative paths. Pascal does not use the
REST resolver to bypass MCP tools. There is no common package, canonical source, generator or sync
manifest. See [intentional duplication and maintenance](reuse.md).

All test modules and scripts are added validation/support infrastructure, with selected original
expectations reused. evaluation/ is a seed harness/corpus, not a completed real-model assessment.
system_prompt.md is a new conversational local default; the existing configured Blob prompt remains
authoritative and was not changed remotely. Docker/locks/CI/deploy/Terraform were adapted from the
original service workflow, with standalone packaging, non-root builds and validation gates added.

## Earlier frontend/static changes — no new edits in this refinement

The prior pending Pascal work changed these files compared with the original; they were **not**
silently reverted or extended during this refinement:

| File | Earlier change |
|---|---|
| frontend/src/chat-app.js | Capture mention token/aliases; /capture and @capture enter existing composer; final SSE answer_markdown becomes authoritative; sample Vega rendering removed |
| frontend/src/vendor.js | Removed Vega import/global; marked and DOMPurify remain |
| frontend/package.json | DOMPurify 3.1.6 -> 3.4.15; removed Vega/Embed/Lite; pinned esbuild 0.25.12 |
| frontend/package-lock.json | Regenerated for those dependency changes |
| static/js/{boot.js,chat-app.js,vendor.bundle.js} | Generated build outputs added in the prior work; original source tree had no corresponding files |

frontend/build.mjs and frontend/src/boot.js match the original bytes. static/index.html and all five
static/agent widget/CSS/image files match the originals. No layout/CSS/host event contract change
was introduced. Old IC_SKILL_TOKEN/composer function and ic.* localization names remain inside the
**frozen frontend**, not Python application logic. Removing them would itself be a frontend edit.
Ignored local cache files are not source changes or shipped artifacts.

The 18-file frontend/static baseline for this refinement remained unchanged in the hash audit.
Docker builds frontend assets inside the image only; it does not edit the workspace files.
Real embedded browser/host behavior still requires QA acceptance.

## Removed or not ported

The old in-process Capture runner/extraction/entity matching, synchronous custom MCP RPC parser,
duplicate JSON/SSE agent loops, hard-coded chart/fallback data and unused configuration aliases are
not in the new runtime. The first rework's adapters/mcp.py was replaced by the explicit MCP package; the bootstrap module
was replaced by observability/telemetry.py. On 2026-09-09 the common integration package was removed:
its implementations now live in adapters, api and observability under src/pascal, without shims.
The one-file compatibility folder was flattened to compatibility.py. No runtime policy changed.
api/capture.py was renamed to capture_bridge.py, not removed as a capability.

Only compatibility.py retains Python occurrences of the obsolete feature name:
old URL, old health field, private historic storage key and dashboard log field. A naming regression
test enforces that boundary. This does not mean those external contracts were migrated.

MCP capabilities not advertised, cross-operation session limits and authentication decisions are in
[mcp.md](mcp.md). [core-review.md](core-review.md) documents the company-agent audit;
[moderation-design.md](moderation-design.md) is design only. No moderation implementation or
neighboring system migration was added.
