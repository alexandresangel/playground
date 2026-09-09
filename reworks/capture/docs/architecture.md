# Capture architecture

Capture is one deterministic extraction workflow, with an HTTP front door and an optional MCP server.
It is not an autonomous agent. All extraction runs through `CaptureRuntime.execute()`.

```text
Classic UI ------- HTTP ------------------------------------+
Pascal composer - Pascal HTTP bridge -- Capture HTTP -------+--> Runtime --> LangGraph
Pascal model ---- MCP capture tool (optional server) --------+                   |
                                                                    direct Diapason REST
```

## Package ownership

| Path under src/capture | Responsibility |
|---|---|
| main.py | Composition and owned resource lifespan; no import-time config/network |
| api/http.py | Existing GET/POST path, multipart validation and public result |
| api/mcp.py | Isolated FastMCP server and tool adapter, lazy-loaded only when enabled |
| workflow/service.py | One execution entry, request resolver, base64 validation, total deadline |
| workflow/{graph,nodes,state,ports}.py | Seven explicit stages, typed state and injected runtime dependencies |
| workflow/extraction.py | Pure PDF/XML helpers retained or mechanically refactored from the original |
| adapters/{catalog,model,azure_openai,blob,diapason}.py | Catalog/prompt loading, model interaction, Azure clients and direct REST |
| auth.py | Original JWT/roles/customer/header trust policy for both front doors |
| compatibility.py | Old wire/config/blob aliases and display-result serialization only |
| observability/{events,telemetry}.py | Capture node events and local OTLP primitives |
| api/guards.py | Request bounds, correlation headers and safe HTTP response defaults |

All production Python lives in `src/capture`. Four folders group real responsibilities: `workflow`
(extraction and orchestration together), `adapters` (external services), `api` (protocol boundaries),
and `observability` (telemetry and events). Small `auth.py`, `compatibility.py`, `config.py` and
`build_info.py` modules stay at the root instead of having one-file wrapper folders. Auth is shared
by both front doors and does not depend on either protocol.

Common primitives are ordinary local files at the same relative paths inside Pascal's package.
There is no second package, generated source, synchronization script or sibling runtime dependency.
See [intentional duplication and maintenance](reuse.md).

## Workflow and retained business behavior

`validate_input -> extract_text -> select_prompt -> llm_extract -> normalize_xml ->
resolve_references -> emit_result`.

The same pypdf text extraction, catalog/prompts, temperature default, XML fence removal, explicit
caller trade-type override, backend resolution and field counting remain. PDF parsing and Blob reads
run off the event loop; Azure calls are asynchronous. No OCR, prompt rewrite, model change, XML repair,
planner or new business fallback was introduced. Equivalent results on real PDFs still require a
golden-corpus comparison; deterministic fixture tests cannot establish model-quality parity.

Credentials/resolver/client live in LangGraph runtime context, not graph state. State contains
sensitive contract text/XML while executing; no checkpointer, chat transcript or artifact store is
enabled. Ambient LangSmith tracing is explicitly disabled. Debug responses retain the original
sensitive detail only when requested; no debug data is added to logs/spans.

The workflow records internal `steps`; only the compatibility serializer emits the existing
`tool_trace/mcp_label` display fields. Direct REST resolution is explicitly marked `direct_http`.
It is not represented as an actual MCP invocation inside the graph.

## HTTP-only and future central MCP

Set `mcp.enabled=false`. Install the base package without the `mcp` extra; neither the module
nor the server lifecycle is imported. The default deployment includes the optional extra so all
three entry paths remain available. Tests exercise the disabled adapter and Docker verifies a base
installation has no MCP dependency.

A future central Diapason MCP server can host the `capture` tool and forward the same trusted
identity/PDF/trade_type to Capture's HTTP route. Then disable/remove the local MCP extra.
No graph, extraction, JWT or public HTTP change is needed. Moving the server is a separate integration
task: agree delegated authentication, payload limits, timeout and trace propagation first.

## Runtime boundary

Capture echoes an optional session ID but never writes Pascal sessions. Pascal owns its minimal
composer receipt. The existing synchronous UX is retained. The total Capture deadline defaults to
210 seconds; parser worker threads cannot be forcibly stopped by asyncio cancellation. The resolver
retains its 120-second request timeout and one non-200 retry, bounded by the total deadline.
ACA documents a 240-second HTTP ingress timeout; load/evaluation must establish adequate headroom.
[ACA ingress](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview).

One Uvicorn worker and replica scaling avoid multiplying large PDFs in a process. Proposed OCR,
durable jobs and extraction improvements remain in [proposed-improvements.md](proposed-improvements.md).
