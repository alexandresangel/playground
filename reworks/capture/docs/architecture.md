# Architecture

Capture is a workflow service, not a skill or subagent. The sequence is fixed and the user/caller
selects the trade type.

```text
Classic Diapason UI ── HTTP compatibility route ──┐
Pascal /capture UI ─── HTTP compatibility route ──┼── CaptureRuntime ── LangGraph
Pascal model ───────── MCP capture tool ──────────┘         │
                                                            └── Diapason REST API
```

## Boundaries

- One process and ACA expose FastAPI plus stateless MCP Streamable HTTP.
- `CaptureRuntime.execute()` is the only use-case entry in application code.
- LangGraph runtime context carries the catalog, LLM adapter, and request-specific resolver. Secrets
  are not part of mutable graph state.
- The graph is compiled without a checkpointer. A future durable/job design must encrypt state and
  define retention before storing PDF text, model output, or XML.
- Prompt configuration remains in the shared private `agent-config` blob container under the legacy
  `skills/intelligence-contract` prefix during migration. The project also bundles an identical
  filesystem copy for local tests and disaster recovery.

## Compatibility HTTP surface

There is one business path, `GET|POST /api/skills/intelligence-contract`. `GET` is metadata for the
existing selector; `POST` is the capture operation. The old name remains only as a wire-compatibility
constraint. New code, service names, logs, and the MCP tool use “capture”.

The service does not write chat sessions. If the caller supplies a session ID it is echoed, but the
agent/Tomcat integration remains responsible for chat history. This prevents Capture from coupling to
the agent’s storage schema and avoids persisting contract artifacts in chat blobs.

## Synchronous decision

The current UX waits for one response and immediately sends the returned XML to the parent window.
Changing to a job API would require UI/backend changes, so Sprint 1 stays synchronous. Azure Container
Apps documents a 240-second HTTP ingress request timeout; the direct resolver timeout remains 120
seconds to leave headroom. Node latency is measured so an asynchronous job migration can be justified
with production data rather than assumed.

## Scaling

MCP is stateless and the workflow has no process-local job state, so requests can land on any replica.
Minimum replicas default to one to avoid a user-visible cold start; maximum replicas default to three
and should be tuned from latency, CPU, memory, and downstream capacity. A single Uvicorn worker is
intentional: replica-level scaling avoids multiplying large in-memory PDF/LLM operations inside one
container.

