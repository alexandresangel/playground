# Architecture and design decisions

## One explicit workflow

```text
Existing chat UI ── JSON / SSE ── authentication + tenant scope
                                      │
                              ChatService (turn owner)
                               │       │       │
                            prompt   history   catalogue
                               └───────┼───────┘
                                      ▼
                              LangGraph: model
                                  │       ▲
                         validated tools ─┘
                                  │
                       final/partial transcript → existing Blob store

Capture composer ── compatibility HTTP proxy ── separate Capture ACA
Model tool call ── configured Capture MCP binding ── same Capture ACA
```

The diagram describes ownership, not a new backend protocol. The graph has two task nodes plus
start/end; no extra planner, reflection agent, supervisor, vector database, or persistent graph store
is necessary for the current tool-using assistant. Runtime context carries scoped tool bindings and
adapters; graph state carries conversation messages, pending calls and counters. Credentials are
not serialized into state or a checkpointer. Tools may return sensitive data; graph tracing to
LangSmith is explicitly disabled even when ambient tracing environment variables are set.

## ADR-001: LangGraph, with a small application-owned loop

Decision: explicit `StateGraph`, not two manual loops and not an opaque prebuilt agent. The required
policy is small: model call, validated tool execution, repeat within limits, finalize once. This keeps
failure, accounting and transport behavior inspectable while allowing later interrupt/checkpoint
features if product and security approve their semantics.

Microsoft Agent Framework is a legitimate alternative, including workflows and graph orchestration;
the choice is not based on an outdated assertion that it lacks those features. Here LangGraph matches
the requested direction and gives a direct, limited migration path without replacing Azure model,
MCP, session or identity boundaries. A future framework swap should target the graph/service boundary,
not migrate external contracts just to follow framework preferences.

Sources checked 2026-09-07: [LangGraph streaming](https://docs.langchain.com/oss/python/langgraph/streaming),
[Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/),
[MAF workflows](https://learn.microsoft.com/en-us/agent-framework/concepts/workflows/).
These inform the design; the lockfile and executable tests determine the APIs actually used here.

## ADR-002: preserve external memory and security

Blob remains authoritative. Each accepted ordinary chat turn reads history once, runs with a bounded
context, and appends one user/assistant pair. Partial responses are saved on cancellation/timeout while
the process and Blob connection remain available. This is **not crash durability**: no completed write
can be guaranteed after a process kill. Per-process admission and session exclusion do not replace a
distributed lease. Blob CAS/schema and local revocations remain compatibility adapters with their
known limitations listed in `NEXT_STEPS.md`.

JWT verification/mint/revoke code is copied unchanged. The FastAPI dependency adapter receives the
application's configuration instead of implicitly loading a second global config. MCP bearer creation
preserves the Fernet JSON `{base_url, scope, api_token}`. No new authority is inferred from LangGraph,
tool descriptions, read-only annotations, or a model-generated tool call.

## ADR-003: explicit MCP boundary

Pascal is the host; `mcp/host.py` owns a shared connection pool and creates server-scoped clients.
The official MCP SDK owns initialization, protocol negotiation, JSON/SSE transport and teardown.
Clients are operation-scoped for the current stateless Diapason service, with separate cookie/session
state per caller. Stateful transport is tested during an operation, but conversational server state
is not retained across calls. Unsupported capabilities and future lifetime decisions are explicit in
[mcp.md](mcp.md), not hidden behind a partial custom protocol implementation.

Tool schemas are cached, never tool results or cross-request credentials. Cache keys include tenant
scope, server identity/URL and a credential fingerprint. A stable fingerprint prevents random
Fernet ciphertext from defeating caching. Fixed lock stripes deduplicate identical discovery without
an unbounded lock map. Remote cookies are not replayed across requests. Known ambiguous names fail
closed. Unknown natural-language @mentions do not silently become tool routes.

Only explicitly read-only batches run concurrently; other batches retain order. Tool calls are not
retried automatically, because an HTTP failure can happen after a mutation already committed.
Azure model retries are bounded and happen only before a stream is established; partial streams are
not replayed. Tool errors are structured, sanitized data for the next model round, not an exception
that discards the user's turn.

Reference: [official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk), including
its [transport documentation](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/client/transports.md).
The main branch can differ from the pinned 1.x runtime dependency; do not copy its APIs blindly.

## ADR-004: bounded, truthful outputs

No synthetic chart generator exists. The compatibility `chart_spec` and `chart_reason` fields stay
null. An actual chart feature needs verified data/provenance and a reviewed schema, not hard-coded
sample amounts. Tool payloads and context are bounded; truncation is explicitly marked. Exceeding a
context/turn/cost limit produces a partial-response status, not fabricated continuation.

Token estimates use cl100k_base plus serialized framing and a safety reserve. They are operational
estimates, not exact billing for every Azure model. Configure the context ceiling conservatively for
the deployed model. Usage omitted by Azure is labelled estimated. Price estimates require explicitly
configured rates; unknown pricing stays null, never a misleading zero-dollar claim.

## ADR-005: keep the UI, isolate Capture

The embedded chat HTML/CSS/assets and host trade-opening event stay in place. Small integration-only
changes add `/capture` and `@capture` aliases, consume authoritative final SSE text and remove the
unused sample-chart renderer. DOMPurify is patched; see its
[official releases](https://github.com/cure53/DOMPurify/releases).

The old composer URL is an async proxy to Capture. Pascal stores a minimal user/assistant receipt,
not extracted PDF text/XML/debug artifacts. Dynamic tenant-header forwarding to MCP is opt-in for
trusted first-party Capture, not applied to Docs or other external servers. Agent-driven Capture
requires actual PDF bytes and trade type; scalable attachment handles remain a separately owned
integration task, not a model inference from a filename.
