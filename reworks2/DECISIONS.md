# Decisions and dependency rationale

## Preserve the existing behavior

Source of truth: original `app.py`, `skills/intelligence_contract/run.py`, `extract_xml.py`, `ic_prompt_loader.py`, company modules and frontend. No planner, agent swarm, matching change, OCR, XML repair, new memory, checkpointer or MCP adapter was added.

Pascal's graph is `model -> tools -> model`, ending at `finish`. It receives the existing per-request discovery/filtering result and calls `_invoke_mcp_tool` through its original interface. Discovery stays request-scoped and dynamic; no graph/global tool catalogue exists. Prompts/history/timezone/locale remain composed by the original functions. Model parameters and `max_tool_rounds + 1` behavior remain unchanged, including executing tools requested by the last model round. Graph recursion capacity is derived from that configured limit.

JSON and SSE use the same graph with their original presentation differences preserved: JSON reports only the final answer, SSE emits intermediate content; JSON substitutes text for an empty final completion, SSE does not. SSE retains its broad retry without `stream_options` if initial creation raises. Sources, events, headers, sample charts, session write order and usage/cost handling remain unchanged. SDK streams and per-request clients are closed after use. No async SDK conversion was imposed on the synchronous HTTP/MCP implementation.

Capture's graph is `validate -> extract -> resolve -> result`. It preserves size/header validation before trade-type lookup, the second catalog lookup inside extraction, prompt loading before PDF decoding, synchronous model parameters, XML fence handling and explicit API `trade_type` enforcement, followed by the same `resolveReferences` MCP call with the same 180-second timeout. Resolver success-without-XML handling, warning conversion, debug/session artifacts and response shape remain unchanged. The original unused `entity_match.py` is omitted; no matching was added to the running path.

LangGraph's typed state/nodes are used directly, without LangChain model/tool wrappers. See the official [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api) and [custom streaming documentation](https://docs.langchain.com/oss/python/langgraph/streaming). The default custom stream format is internal only; original SSE objects are emitted at the existing adapter.

## Migration and naming exception

Both projects use `src/<project>/`: `capture` for the workflow service and `pascal` for the chat agent. AI stages live in `workflow/` or `agent/`, HTTP adapters in `api/`, and AI tracing in `observability/`. There is no separate `workflow_support` or shared runtime package. `application.py` assembles routes; the five-line `asgi.py` launches the service. `runtime.py` supplies existing configuration/auth/storage dependencies explicitly instead of relying on a large app module's globals.

The user's follow-up authorizes a cleaner standalone Capture base: Pascal frontend/static, persona/system prompt, chat/discovery/chart features and session CRUD endpoints are omitted from Capture. Extraction still writes the original session artifacts and uses existing locale messages. Capture health returns build health; refresh loads only the Capture catalog. These operational changes are deliberate and documented; the extraction/auth/security/MCP contracts remain preserved. Pascal retains its entire original surface.

Company implementations, including the complete `dia_jwt` folder, remain byte-identical under `src/<project>/company/`. Only the outer source location changes. Setuptools maps these files back to their original public module/package names so company imports remain unchanged. `company/` is a source grouping, not a new integration package. Explicit package lists/data prevent duplicate copies of company code entering wheels. See [setuptools package discovery](https://setuptools.pypa.io/en/stable/userguide/package_discovery.html) and [pyproject configuration](https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html). Wheel installation was checked independently for each project, including adjacent locale data and public JWT imports.

The launch command is now `uvicorn capture.asgi:app` or `uvicorn pascal.asgi:app`, from the corresponding project root. That directory remains the base for company config/keystore/VERSION and Pascal static files. Docker commands follow the new module target; image/port/build metadata conventions stay intact.

The original frontend posts multipart PDF/trade_type directly to `/api/skills/intelligence-contract` on Pascal. No separate Capture caller, upload resource protocol or registered Capture MCP tool exists in the original. Pascal therefore retains the original upload implementation under `src/pascal/compat/capture/` until external routing exists. Standalone Capture owns `src/capture/workflow/` and nine source assets under `config/`. The two workflow copies differ only in package imports; the small `observability/ai.py` helper is byte-identical in both projects. There is no synchronization script or cross-project dependency. Pascal has no local prompt assets: both loaders use the existing legacy Blob keys.

Retained compatibility strings are deliberate: HTTP path and generated operation IDs (including `intelligence_contract_skill`), `intelligence_contract` config/health keys, `skills/intelligence-contract/` Blob keys, `@intelligence-contract`, response/tool labels, `skill_run`/`skill` session fields, locale keys, and existing telemetry field names. `session_store.py`, `telemetry.py`, frontend/static/locales retain their legacy identifiers byte-for-byte. Renaming these requires the other owners and would break existing consumers. No claim is made that those external strings disappear.

## Azure SDK decision: blocked by missing deployment evidence

Only placeholder endpoint/deployment details exist in `config.example.json`; no live compatibility check is possible here. The single original `AzureOpenAI` constructor, dated `api_version`, configured deployment, key handling and request parameters are preserved. There is no second client, automatic SDK fallback or client-mode flag. This is a documented exception to the preferred v1 migration, under the no-break priority.

Microsoft documents [OpenAI with Azure v1](https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle): use the existing resource endpoint with `/openai/v1/` as `base_url`, keep the deployment name as `model`, and remove the dated API-version argument. The [official OpenAI SDK guidance](https://developers.openai.com/api/docs/libraries) confirms the Python SDK; neither source proves a private deployment/gateway's compatibility. Do not replace Chat Completions with Responses, change the model, alter temperatures or silently switch endpoints.

Next SDK task, after environment-owner confirmation: replace the sole constructor with `OpenAI(api_key=existing_key, base_url=existing_resource_endpoint + '/openai/v1/')`; test tool calls, streamed usage and Capture temperature against the same deployment. Any endpoint/gateway/service change stays with the platform owner. No missing model value was invented.

## Observability

`telemetry.py` is byte-identical, so provider bootstrap, OTLP configuration, correlation and Loki/Tempo destinations remain intact. New fixed-name `ai.pascal.*` and `ai.capture.*` spans contain duration, success/error outcome and available numeric usage only. Capture business failures also set `ai.result_success=false`; exception messages/stack events are not recorded by AI spans. Existing chat query-preview fields now contain `[redacted]`, and extraction failure logs no longer include XML. Payload-bearing AI-route error logs are redacted while HTTP error responses are unchanged. MCP transport is untouched; only the existing agent call span/log's exception telemetry is content-free.

LangGraph can otherwise emit inputs/state through automatic LangSmith tracing. Each run uses `tracing_context(enabled=False)` plus empty explicit callbacks, documented by [LangSmith's tracing control](https://docs.langchain.com/langsmith/trace-without-env-vars). No LangSmith client/exporter or additional backend is configured. No metrics exporter/receiver is assumed. Sensitive artifacts remain only in the already-required response/session contracts, not the new telemetry. Company non-AI request logging is unchanged and outside this audit's AI telemetry scope.

## Direct versus transitive dependencies

Original runtime dependencies and lower bounds are retained in each `pyproject.toml`; no broad requirement upgrades were made. The original repository supplied no lockfile, so the recorded fresh test environment is evidence, not a claim about deployed package versions.

| Dependency | Kind and reason |
| --- | --- |
| `langgraph>=1.0,<2` | New direct runtime dependency: typed state, conditional loop and custom streaming. |
| `langsmith>=0.1.95,<1` | Direct import solely for per-run disabling of payload tracing; already pulled transitively by LangGraph. |
| `openai` | Existing direct runtime SDK; sole original Azure client retained pending v1 verification. |
| `opentelemetry-api` | Existing direct API used by AI spans; original SDK/exporters/bootstrap unchanged. |
| `pypdf` | Existing direct Capture PDF extraction; still needed in Pascal's temporary compatibility path. |
| `setuptools>=68` | Build-only backend for editable installs and wheels; not a runtime framework. |
| `pytest>=8,<9` | Development-only offline tests. |
| `tzdata` on Windows | Development-only timezone database for unchanged `ZoneInfo` code on this test host. |
| LangChain core, LangGraph checkpoint/prebuilt/SDK, serializers, HTTP helpers | Transitive requirements of LangGraph; no prebuilt agent, checkpointing, hosted graph server or MCP SDK used. |
| FastAPI, Uvicorn, Pydantic, multipart, HTTPX, PyJWT, cryptography, Azure Blob/identity, remaining OTEL packages | Existing direct company/interface dependencies, unchanged requirement lines. |

## Known original defects kept separate

1. Seven original `test_source_extract.py` assertions conflict with current locale filtering. Both file and implementation are byte-identical; exact cases are strict expected failures in Pascal's test configuration. New graph tests verify the actual source behavior rather than changing it.
2. `ic_prompt_loader.py` assigns a string to the same `_catalog_version` name used by its hash function. Initial load succeeds; a later refresh fails with `TypeError`. `src/capture/workflow/prompts.py` (and Pascal compatibility copy) preserves this behavior; a characterization test documents it. A separate behavior fix should use distinct names, then verify reload/cache semantics.
3. SSE broad retry, synchronous MCP work in the async extraction path, catalog fallback for unknown nonempty trade types, and post-`done` session persistence are existing behavior, not new policies. Improvements require separate behavior changes.
