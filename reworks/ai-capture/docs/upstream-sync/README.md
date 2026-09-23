# Agent-to-Capture synchronization audit

Date: 2026-09-23. All repository edits are confined to `ai-capture`.

## Comparison scope

Compared the `diapason-agent-main` filesystem snapshot (no Git metadata) with tracked file contents from `ai-agent` at `de30b7e` plus its working tree. Capture started at `3599ae4`. Text comparisons normalize CRLF/LF; binary files are compared by bytes. Excluded generated/environment directories: `.git`, `.venv`, `__pycache__`, `.pytest_cache`, `node_modules`, and runtime `data`. Ignored local configuration/secrets and generated assets are not treated as upstream source changes.

The upstream working tree had three pre-existing executable-mode-only differences: `run.sh`, `deploy/deploy.sh`, and `test/test_smoke.py` (100755 -> 100644 on this Windows checkout). Their contents match HEAD. They were inspected but not modified. The old snapshot cannot provide trustworthy historical Git modes.

**40 changed source paths:** 19 modified, 6 added, 15 removed. There are no additional content changes in the compared source set.

The recent changes are predominantly M2M/registry authentication, deployment/build identity, file-based prompt loading, OTLP configuration, and agent UI integration. Extraction algorithms, XML field logic, catalogs and prompt text did not change upstream. Neither `mcp_context.py` nor `mcp_rpc.py` changed in that comparison: the new Capture tracing work below addresses the requested observability improvements, not an unported upstream MCP change. The requirements file, dashboards, localization bundles, chat/session store and blob client also have no upstream content changes.

## Every upstream file and application decision

Paths in the first column are relative to the original/upgraded agent repos. Line counts describe upstream edits, not Capture edits.

| Upstream path | Change (+/- lines) | Decision | Reason and Capture mapping |
|---|---|---|---|
| `.dockerignore` | modified (+3/-3) | Already covered | Capture already includes `config/` and excludes local secrets/tests. Agent-only inclusion of `system_prompt.md` is unnecessary. |
| `.github/workflows/ci.yml` | modified (+9/-5) | Keep Capture variant | Upstream makes tests PR-only, scopes permissions, disables persisted checkout credentials, changes checkout/setup-python majors, and renames the smoke exclusion. Capture already has scoped permissions, safe checkout and an offline-only suite; retain main+PR validation, checkout v7 and uv instead of copying the agent runner setup. |
| `.github/workflows/deploy.yml` | modified (+57/-23) | Port missing pieces | Upstream adds main-to-dev deployment, staging promotion, concurrency, scoped permissions, environment-safe shell inputs, release tags, and shared-action auth. Most existed. Added missing push-to-dev GitHub environment selection, per-environment serialization and release-tag propagation. Retain Capture uv tooling; no frontend build. |
| `Dockerfile` | modified (+7/-6) | Adapt | Port BUILD_DATE/build_date and OCI created metadata. Preserve Capture uv lock/install, packaged config directory, port 8000 and version compatibility; agent port 7702 is not a Capture requirement. |
| `README.md` | modified (+59/-85) | Rewrite for Capture | Replace stale agent/Blob/keystore/frontend instructions with Capture setup, M2M, file-based config, HTTP contract, tracing, smoke and deployment docs. |
| `VERSION` | removed (+0/-1) | Retain intentionally | Agent removed semver build identity. Capture still uses this file/package version for OpenAPI and existing health clients; add upstream identity fields without removing it. |
| `app.py` | modified (+19/-57) | Already covered + adapt health | Upstream switches JWT roles/Identity to M2M, removes token administration, passes base_dir to file prompt loaders, adds build_date/release and safe optional token health reporting. Capture already had M2M, no token administration and file loaders; port build identity through `common/build_info.py`. Keep minimal public health and Capture routes; no agent persona/session diagnostics. |
| `auth_m2m.py` | added (+387/-0) | Already covered | JWKS RS256, registry issuer, exact scope, rotation/cache/stale handling, client_id identity and tenant headers already ported. Preserve ai-capture scope and Capture's existing zero-clock-skew fix; centralize header defaults only. |
| `auth_setup.py` | modified (+15/-76) | Already covered | Keystore, hard-coded ISSUER, revocation-file setup and admin role wiring already removed. No new issuer rename needed: the issuer is the platform M2M URL. |
| `build_info.py` | modified (+16/-10) | Adapt | Add baked build_date, GIT_REVISION fallback and runtime release; accept older build-info files. Preserve compatible version field. |
| `config.example.json` | modified (+7/-11) | Already covered | Registry and M2M replace jwt/keystore settings; Capture already has canonical capture config, no storage or agent prompt/persona blocks, and ai-capture scope. Agent cost-format change is nonfunctional. |
| `deploy/deploy-config.sh` | removed (+0/-95) | Already absent | Blob-config upload removed upstream; Capture bundles config files and has no upload script. |
| `deploy/deploy.sh` | modified (+39/-69) | Port missing pieces | Upstream delegates infrastructure/secrets to shared ACA helpers, uses staging, removes blob uploads/pruning/version expectations, passes PORT/RELEASE_TAG and runs M2M smoke. Most existed. Remove obsolete read_version call, pass release/port, retain health checks even when smoke is skipped, and supply the previously missing Capture smoke runner. |
| `deploy/infra.tf` | removed (+0/-181) | Already absent | Upstream moved infrastructure ownership outside service repo. Capture already follows the shared infrastructure model. |
| `dia_jwt/README.md` | removed (+0/-21) | Already absent | Local JWT keystore documentation removed; document platform M2M in Capture README. |
| `dia_jwt/__init__.py` | removed (+0/-3) | Already absent | Local token library superseded by auth_m2m. |
| `dia_jwt/__main__.py` | removed (+0/-4) | Already absent | Local token CLI no longer applicable. |
| `dia_jwt/auth.py` | removed (+0/-200) | Already absent | Local signing/revocation logic superseded by platform M2M. |
| `dia_jwt/cli.py` | removed (+0/-55) | Already absent | No local keystore/token administration in Capture. |
| `dia_jwt/fastapi.py` | removed (+0/-98) | Already absent | Role-based dependencies already replaced with Capture M2M dependencies. |
| `docs/01-issues-and-risks.md` | removed (+0/-509) | Do not copy | Removed agent architecture notes are not Capture runtime behavior. |
| `docs/02-roadmap-1-month.md` | removed (+0/-195) | Do not copy | Removed agent roadmap is outside this extraction-service update. |
| `docs/03-target-architecture.md` | removed (+0/-342) | Do not copy | Removed agent target architecture is superseded by Capture design and this audit. |
| `docs/04-intelligence-contract-design.md` | removed (+0/-322) | Do not copy | Removed legacy skill-design document should not reintroduce agent naming/architecture. |
| `frontend/src/boot.js` | modified (+0/-9) | Agent only | Removes embedded JSON config parsing; Capture has no frontend boot script. |
| `frontend/src/chat-app.js` | modified (+24/-22) | Agent only | Changes proxy prefix to /ai/agent, takes identity from proxy headers, adds logo retries and updates M2M error instructions. No Capture UI/proxy to edit; HTTP headers remain compatible for future integration. |
| `ic_prompt_loader.py` | modified (+52/-53) | Already covered + small port | Blob reads replaced with local image/repo catalog/prompts, containment checks, base_dir, refresh/cache source tracking. Capture already had these with config/ and prompt_path; add optional capture.catalog_file. Do not restore skills directory or blob-name prefixes. |
| `prompt_loader.py` | modified (+15/-47) | Agent only | System prompt moved from Blob to local file with containment checks. Capture only uses extraction prompts; it has no agent system prompt. |
| `registry_client.py` | added (+76/-0) | Already covered | Registry JSON fetching, services.m2m.url validation and error handling match upstream (only trailing-newline difference). |
| `run.sh` | added (+16/-0) | Add Capture version | Root-relative virtualenv launcher, HOST/PORT overrides and exec. Capture entry point, local port 8011, Windows Git Bash virtualenv support, PYTHON override and forwarded Uvicorn options. |
| `settings.py` | modified (+10/-2) | Already covered | config.local.json preference and required registry_url already present. Keep CHAT_CONFIG deployment compatibility. |
| `skills/intelligence_contract/config/README.md` | modified (+9/-19) | Adapt documentation | Upstream explains image/repo prompts instead of blob upload; root Capture README now documents config/ and reload behavior. |
| `skills/intelligence_contract/config/upload.sh` | removed (+0/-51) | Already absent | No Capture blob prompt uploads to remove. |
| `static/agent/agent-widget.js` | modified (+15/-1) | Agent only | Cold-start logo loading retry/backoff does not apply to Capture. |
| `telemetry.py` | modified (+48/-85) | Port compatibly | Add OTEL_BEARER_TOKEN/OTEL_ORG_ID and base endpoint signal paths. Unlike a literal upstream copy, retain signal-specific endpoints/headers, legacy auth env fallbacks and trace-only Jaeger operation. Normalize Capture logging/scope and remove unused tool/skill CSV helpers. |
| `test/test.api.example.json` | modified (+3/-1) | Already covered | Capture live example already uses registry and M2M credentials, capture_url/capture_pdf, and Diapason credentials; no legacy agent JWT needed. |
| `test/test_agent_smoke.py` | removed (+0/-620) | Replace by Capture smoke | Old JWT/chat/session smoke removed upstream. Capture had no corresponding live runner despite deploy referencing one; add dedicated stateless checks. |
| `test/test_auth_m2m.py` | added (+238/-0) | Already covered | Existing Capture tests exercise imported JWKS/issuer/scope/cache/rotation behavior and Capture-specific cases; do not duplicate agent tests. |
| `test/test_registry_client.py` | added (+63/-0) | Already covered | Existing registry tests cover these newly upstream-added helpers. |
| `test/test_smoke.py` | added (+732/-0) | Adapt relevant checks | Port platform M2M token acquisition (Basic client auth), registry discovery, Diapason login, build/release checks and extraction into tests/smoke_capture.py. Request ai-capture explicitly as in the user workflow. Keep env URL/config overrides and test locally with mocked transports; omit agent chat, source/tool listing and session mutations. |

## Capture contract and compatibility decisions

- Canonical service/package/config/API names are `ai-capture`, `capture`, and `/api/capture`. Active logger and trace scope names are `capture`. Endpoint function names and disabled-service messages use Capture.
- `capture/http_contract.py` owns identity, MCP, locale, correlation, and W3C header names. Authentication, extraction, middleware, locale helpers, MCP helpers and the live smoke runner import it. No external header was renamed. Existing imports of MCP/locale constants still work because those modules import the same names.
- `CHAT_CONFIG` stays: it is the shared deployment secret name. No `CAPTURE_CONFIG` migration is needed. `DEFAULT_REQUIRED_SCOPE` was already `ai-capture`. `auth_setup.py` already delegates to M2M; the old `ISSUER = "diapason-agent"` no longer exists in Capture.
- The only active `intelligence_contract` uses retained are the read-only configuration fallback and deprecated GET/POST route aliases. They preserve the user's existing calls and are tested. Canonical config wins even when explicitly empty/disabled.
- `tool_trace` and internal timing arrays are removed from workflow state/results; the public response also strips legacy copies defensively. This applies to the deprecated route too. Consumers expecting `tool_trace` must migrate to OTEL. Extraction XML, resolver arguments, prompts, temperature, business success handling and debug data remain unchanged.
- `X-Diapason-Chat-Session` remains an opaque correlation ID; it does not access chat/session storage. Multipart ID precedence remains. CORS exposes the header to browser JavaScript. Missing or invalid W3C context still allows normal requests.
- Build health now adds `build_date` and `release`; `revision` stays and `version` is retained. Docker stamps build identity; release is supplied when promoting, so staging/prod can share an image. Capture container/deploy port stays 8000 by default and launcher defaults to 8011; agent port 7702 is unrelated.
- Legacy, unused `common/blob_client.py` and `common/session_store.py` remain untouched to avoid unrelated deletions. They are not imported by the Capture application and are not included in its explicit wheel modules. The old `tool_trace` helpers still visible in the unused session-store source are not part of Capture execution. Unused persona/cost/locale utilities are also left alone except for the removed tool/skill CSV helpers.

## Assessment of the supplied trace

The trace already correlates its seven spans and measures the useful workflow stages. HTTP total is about **2,638 ms**; workflow **2,423 ms**; model **2,088 ms** (about 79% of request duration); reference-resolution tool **240 ms**. Roughly 215 ms sits outside the workflow. The trace alone cannot identify that overhead, and it does not justify changing the extraction architecture or model.

The 151-microsecond `capture.completion` span only measures result bookkeeping. The HTTP span is incorrectly marked INTERNAL, instrumentation scopes mix agent/AI names, model metadata and outgoing RPC identity are absent, and HTTP exceptions/business failures are not consistently reflected in span status. The lack of another MCP process in this export does **not** prove missing propagation: the old client already injected HTTP context and the sibling MCP server already extracts it in `_ExtractTraceContextHTTP`. MCP must export its spans to the same backend for them to appear.

Applied fixes:

1. `http.request` is SERVER; it records current HTTP attributes plus legacy method/status aliases, matched route and response/correlation. 5xx/unhandled failures get ERROR status without private exception details.
2. `capture.request` surrounds extraction and contains identity/correlation/result attributes, replacing the bookkeeping-only completion span.
3. Stage spans share the `capture` scope. Model is CLIENT with deployment name, operation/provider and usage. Resolve stage is named `ai.capture.resolve`.
4. `mcp.request` is CLIENT around the actual JSON-RPC HTTP call, with method, tool name, server ID/hostname and HTTP status. Propagation happens inside it, including across `asyncio.to_thread`, so downstream MCP is its child. HTTP/RPC/tool errors and timeouts have content-free error status.
5. Business `success=false` marks workflow/request failure without changing the HTTP business-result contract. Tokens, documents, prompts, XML, tool arguments, full URLs and exception messages are not added to spans. LangSmith document tracing remains disabled.

Expected tree:

```text
optional Pascal/UI caller span
  http.request [SERVER]
    capture.request
      ai.capture.workflow
        ai.capture.validate
        ai.capture.extract
          ai.capture.model [CLIENT]
        ai.capture.resolve
          mcp.request [CLIENT]
            downstream MCP spans (if exported)
```

Pascal can propagate `traceparent`/`tracestate` in its HTTP call to Capture. The current MCP HTTP transport needs no `_meta` extension or protocol-version change. A direct UI call without tracing starts a new trace; malformed trace headers are ignored. These behaviors are verified through the real ASGI/graph/RPC stack with transport/model doubles. Span kinds follow the [OpenTelemetry tracing API](https://opentelemetry.io/docs/specs/otel/trace/api/#spankind), and context handling uses the standard [OpenTelemetry propagators](https://opentelemetry.io/docs/specs/otel/context/api-propagators/).

The exporter accepts the new platform base URL/token/org variables while retaining signal-specific endpoint/header precedence and old auth aliases. Trace-only Jaeger settings stay trace-only. Base URL path construction follows [OTLP exporter configuration](https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/); legacy full signal URLs in the common variable are also normalized for compatibility.

## Validation

- Baseline: `uv sync --all-groups`, then `uv run --locked pytest -q`: **90 passed**.
- Updated offline suite: **111 passed**, one pre-existing Starlette/AnyIO deprecation warning. Includes real M2M/JWKS behavior, canonical/deprecated API routes, browser correlation, custom catalog containment, build identity, smoke transport tests, workflow/model/MCP trace hierarchy, malformed/missing incoming context, HTTP/RPC/tool/timeout redaction and business failures.
- Actual OTLP HTTP export to a local receiver: trace-only mode exported `/v1/traces` without logs; platform mode exported traces and logs using bearer auth and the logs tenant header.
- `uv build --wheel`: successful; new shared contract is included, and imports were verified from an isolated wheel install. No dependency or lockfile changes required.
- `git diff --check HEAD`: clean.
- Bash syntax validation for launcher/deploy and `bash run.sh --help`: successful. Deploy target resolver executed with mocked environment for push/dev/staging/release; blank staging tag and draft release correctly rejected.
- Live local Uvicorn using existing local config: startup, `/health`, `/api/health`, real registry/M2M token acquisition, prompt refresh, catalog and missing-token rejection succeeded. Diapason `/api/login` returned HTTP 200 **without `apiToken` or `token`**, confirmed in an isolated follow-up request. Live extraction could not proceed; no claim of a live Azure/MCP extraction pass is made. Credentials and document content were not printed.
- Docker CLI exists but the Docker Desktop Linux engine is unavailable; container build/run not verified. No deployment was performed. The external shared deployment library is not present in this workspace, so ACA/shared-library execution remains an integration check for CI.

## Edit ledger

Every final source/document edit is listed below. No existing source files were deleted or moved. No edits were made in the source agent, original snapshot, or MCP repositories. The four pre-existing untracked `temp_res*` files and local configs were preserved.

| Capture path | Edit | Purpose |
|---|---|---|
| `.gitattributes` | Added | Added LF policy for shell scripts so Windows checkouts remain runnable on Linux. |
| `.github/workflows/deploy.yml` | Modified | Fixed push/dev environment binding; added deployment concurrency and runtime release tag. |
| `Dockerfile` | Modified | Added build date/OCI created metadata; preserve compatible version with VERSION fallback and Capture port/install layout. |
| `README.md` | Modified | Replaced obsolete agent instructions with current Capture contract, setup, tracing, smoke and deployment documentation. |
| `deploy/deploy.sh` | Modified | Pass PORT/RELEASE_TAG; removed obsolete shared read_version call; preserve revision check and health checks. |
| `docs/upstream-sync/README.md` | Added | Added exhaustive 40-path upstream decision matrix, compatibility/trace assessment, validation and this edit ledger. |
| `run.sh` | Added | Added executable Capture launcher with root-relative venv, HOST/PORT/PYTHON support and forwarded Uvicorn flags. Only this new file is staged to record Git executable mode 100755. |
| `src/capture/api/extraction.py` | Modified | Canonical internal endpoint names/messages; consume shared headers; drop legacy trace fields; wrap extraction in capture.request span with error/result/correlation. |
| `src/capture/api/middleware.py` | Modified | Shared headers, generated/echoed correlation, SERVER spans, matched route/current HTTP attrs and redacted errors. |
| `src/capture/application.py` | Modified | Expose the shared correlation header to browser JavaScript through CORS. |
| `src/capture/common/auth_m2m.py` | Modified | Use shared identity header defaults; authentication behavior and ai-capture scope unchanged. |
| `src/capture/common/build_info.py` | Modified | Compatible version plus upstream build_date/revision/release metadata and old-image fallback. |
| `src/capture/common/i18n.py` | Modified | Import shared locale header; normalize module description. |
| `src/capture/common/mcp_context.py` | Modified | Import shared MCP/auth headers; normalize MCP logger name. |
| `src/capture/common/mcp_rpc.py` | Modified | Shared protocol header and content-free CLIENT RPC spans; inject context inside the span; mark transport/RPC/tool failures. |
| `src/capture/common/telemetry.py` | Modified | Capture defaults, platform endpoint/auth compatibility, signal-specific header precedence; remove obsolete tool/skill CSV functions. |
| `src/capture/http_contract.py` | Added | Added the centralized HTTP header contract and exposed correlation response header list. |
| `src/capture/observability/ai.py` | Modified | Capture scope; configurable span kind/attributes; safe error type and failed-outcome status. |
| `src/capture/observability/http.py` | Modified | Capture logger and business failure status on the enclosing request span. |
| `src/capture/runtime.py` | Modified | Normalize active logger and tracer names to capture. |
| `src/capture/workflow/extract_xml.py` | Modified | CLIENT model span with provider/operation/deployment metadata; keep extraction/prompt/model arguments unchanged. |
| `src/capture/workflow/graph.py` | Modified | Remove tool_trace/timing state and output; normalize stage/logger names; flag business failure in workflow span. |
| `src/capture/workflow/prompts.py` | Modified | Document legacy config fallback and support contained optional catalog_file. |
| `tests/smoke_capture.py` | Added | Added opt-in live/deployment smoke runner with M2M/Diapason auth, health/build checks, extraction, XML and correlation checks; safe failure diagnostics. |
| `tests/test_api.py` | Modified | Assert no tool_trace on either route; verify browser CORS and error correlation. |
| `tests/test_build_info.py` | Added | Added current/legacy image identity, local fallback and runtime release tests. |
| `tests/test_capture_catalog.py` | Modified | Added custom catalog and path-escape regression coverage. |
| `tests/test_observability.py` | Modified | Normalize logger expectation; add RPC/HTTP/timeout/tool failure redaction/status coverage. |
| `tests/test_smoke_capture.py` | Added | Added mocked end-to-end smoke flow, config/env precedence and wrong-revision rejection tests. |
| `tests/test_telemetry_config.py` | Added | Added platform/legacy auth, endpoint/header precedence, traces-only mode and service identity tests. |
| `tests/test_telemetry_helpers.py` | Modified | Removed tests for deleted legacy tool/skill CSV helpers; retained other helper tests. |
| `tests/test_workflow.py` | Modified | Remove legacy output expectations; verify complete HTTP/workflow/model/RPC trace tree, worker-thread propagation and failed business results. |

Generated local validation artifacts are ignored: `.venv/`, `build/`, `dist/ai_capture-0.1.11-py3-none-any.whl`, package `.egg-info`, Python/pytest caches and `logs/upstream-sync-live.log` / `logs/deploy-check/`. These are not source changes. The temporary raw upstream comparison JSON was removed after generating this Markdown inventory. No user result/config files were removed.
