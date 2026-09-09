# Company-agent core review — 2026-09-08

Scope: original app.py and helpers compared with the pending Pascal implementation, including actual
graph, model, MCP, session, streaming and compatibility tests. This is a local engineering review,
not a claim of production readiness or a scored model evaluation.

## Decisions and evidence

| Concern | Decision / implementation | Evidence and limitation |
|---|---|---|
| One agent behavior for JSON and SSE | ChatService owns a single two-node StateGraph and one finalization path | graph/API/lifecycle tests; no duplicate agent loop |
| Understandable DS/MLE structure | model -> validated tools -> model, no speculative planner/supervisor | graph.py and injectable ports/context; no persistent checkpoint |
| Prompt and memory | Stable prompt snapshot/hash, locale/time suffix, whole-turn history pruning | prompt/budget tests; Blob remains authoritative |
| Model transport | Local AsyncOpenAI v1 factory; explicit dated compatibility only | actual SDK request/fragmented stream fixtures; deployment support is a live gate |
| Hallucinated or unsafe calls | Only bound tools dispatch; object/schema/argument/call/round limits; no schema downloads | invalid-call tests, external ref/dynamicRef/recursiveRef negatives |
| Side effects | Unannotated/mutating calls stay sequential; no MCP mutation retries | scheduling/interruption tests; a disconnected mutation may have committed |
| Admission and cancellation | Total/model deadlines, bounded SSE queue, owned producer, graceful shutdown | cancellation-before-start, partial stream/tool/write and timeout tests |
| Persistence | One awaited append attempt; shield disconnect during write; truthful persisted flag | missing-record/ETag-shaped fixtures; no guarantee after process kill |
| Usage and costs | Per-round usage; cached input accounted, missing usage labelled estimate, unknown rates null | budget/model tests; estimates are not billing invoices |
| Tool/data failures | Sanitized structured errors, explicit incomplete status, no invented chart values | failure/privacy and null-chart compatibility tests |
| Observability | Safe spans and real logs/traces/metrics exporters, tenant IDs excluded from metric labels | exporter protobuf tests; real Loki/Tempo inspection still required |
| Capture separation | Composer bridge performs HTTP only; no extraction in Pascal | bridge/receipt tests; MCP path remains a separate explicit tool |
| Context privacy | No content-bearing LangSmith exports; no default model/HTTPX auto-instrumentation | ambient tracing and span/log tests; gateway/URL hygiene remains platform-owned |

The review fixed missing standard MCP initialization, strengthened schema reference blocking,
restored the exact ordered completion-log prefix expected by the original Grafana regex, isolated
obsolete private receipt aliases, and marked failed/cancelled turn spans as errors.
See provenance for changes made before this refinement, including frontend integration edits.

## Why the Capture bridge is still needed

The file is now `api/capture_bridge.py` to make its role explicit. The existing composer calls
Pascal's same-origin URL and expects Pascal to own the chat session and receipt. Hosting extraction
in a separate ACA does not change that browser contract. The bridge authenticates the current route,
forwards the multipart request/identity/trace context to Capture, passes the public result back,
and records only a minimal receipt through ChatService.

Removing it now would require a frontend/gateway change and a decision about receipt ownership.
It is not an extra extraction implementation or an MCP proxy. If the platform later routes the
browser directly to Capture and provides receipt ownership elsewhere, the bridge can be removed.

## Remaining company/multi-client risks

Security compatibility is not a modern-security certification. Original replica-local revocations,
fail-open unreadable revocation files, trusted identity headers, credentialed wildcard CORS and
caller-selected backend destinations need explicit platform/security acceptance. Per-process session
exclusion does not coordinate replicas. Blob writes/worker threads are not forcibly cancellable.
No checkpoint guarantees durable replay of tools; ambiguous mutations must not be blindly retried.

Large PDF base64 in an agent context is impractical: use the current composer, and plan opaque
authorized attachment handles before scaling agent-initiated Capture. Production quality needs
golden tasks, prompt-injection/authorization cases, numeric/source scoring, load and failure drills.
A model-based moderation policy is a separate design decision, not implemented by this review.
See [moderation-design.md](moderation-design.md) and [NEXT_STEPS.md](../NEXT_STEPS.md).
