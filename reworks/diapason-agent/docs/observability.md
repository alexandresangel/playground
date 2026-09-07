# Loki / Tempo operations

Pascal continues to export OTLP over HTTP to the existing collectors. No LangSmith account or second
telemetry backend is required. Application spans and logs omit prompts, queries, tool arguments and
results, PDFs, XML and request credentials. The logger records only exception class names, never raw
remote exception messages. The shared graph explicitly disables LangSmith tracing for this reason.

## Environment contract

| Variable | Behavior |
|---|---|
| OTEL_SERVICE_NAME | Set by existing deploy helper, normally `diapason-agent-{environment}`; local fallback `diapason_agent` |
| OTEL_EXPORTER_OTLP_TRACES_ENDPOINT | Full trace signal URL, passed as-is to the HTTP exporter |
| OTEL_EXPORTER_OTLP_LOGS_ENDPOINT | Full Loki/collector log signal URL, often ending `/otlp/v1/logs` |
| OTEL_EXPORTER_OTLP_ENDPOINT | Existing generic full-signal fallback; not automatically suffixed |
| OTEL_EXPORTER_OTLP_PROTOCOL | Required for generic logs fallback, as in legacy deployment |
| OTEL_EXPORTER_OTLP_HEADERS | Comma-separated headers; URL-decoded values |
| OTEL_EXPORTER_OTLP_TRACES_HEADERS / LOGS_HEADERS | Signal-specific headers override generic headers |
| OTEL_EXPORTER_OTLP_TOKEN | Used as Bearer authorization when explicit headers are absent |
| OTEL_EXPORTER_OTLP_SCOPE_ORG_ID | Loki tenant; `mcc` fallback for logs. Applied to traces when explicitly set |
| OTEL_RESOURCE_ATTRIBUTES | Existing service/environment labels; do not include customer data |

Supply the **same endpoint values** used by the deployed legacy agent. The generic URL behavior is
intentionally compatible rather than silently reinterpreting it as an OTLP base URL. Exporters batch
and flush at lifespan exit; provider shutdown also runs at process exit. Health probes do not call
Azure/MCP/Blob, avoiding probe storms during a dependency outage.

## Trace and log correlation

FastAPI instrumentation extracts W3C `traceparent`. `chat.completion` owns `chat.model` per round and
`chat.tool` per actual tool call. The explicit MCP/Capture adapters inject the active W3C context into
downstream requests without logging headers. Tools failing locally validation do not create a fake
remote-call span. There is no blanket HTTP client instrumentation that would capture credential-bearing
URLs from arbitrary tool configuration.

The `chat done` log keeps customer/user/instance/session, tokens_in/tokens_out, cost_usd, tools, skills
and blob fields. Added fields include trace_id/span_id, status, persisted, rounds, ttft_ms, duration_ms,
cached_tokens and prompt_version. Session IDs and tenant IDs are log fields/span attributes, not metric
labels. Query preview is removed. Costs are null without configured Azure prices; token estimates are
not billing records. Existing dashboards that depended on query_preview must remove that column.

## Proposed SLO/alert starting point (requires SRE approval)

Measure for a week in dev/test, then agree thresholds with product; do not call these adopted SLOs.

- Availability: fraction of accepted turns with `status=completed` and `persisted=true`. Track
  cancelled user turns separately; count dependency failures, not just HTTP 5xx (SSE already has 200).
- Latency: p50/p95 first token and completed-turn duration, split by tool family/environment, not user.
- Reliability: any `persistence_failed` should alert promptly; rising model/tool failure ratios should
  page only with sustained traffic and an agreed burn-rate policy.
- Resource: turns reaching limits, cache/discovery failures, process memory and replica saturation.
- Capture: end-to-end p95 approaching the ingress budget requires the Capture job design discussion.

Example Loki exploration (adapt label mapping to the current collector):

```logql
{service_name="diapason-agent-dev"} |= "chat done" | logfmt | status="persistence_failed"
{service_name="diapason-agent-dev"} |= "chat done" | logfmt | trace_id="<trace id>"
```

For a persistence failure: locate the trace, check scoped Blob RBAC/reachability, avoid blind user
retries if a tool may have mutated data, and recover the receipt from approved operational evidence.
For an MCP failure: identify the server/tool span, verify its current protocol/auth/config without
printing tokens, check the server's trace, and retry only with an understood idempotency policy.

Release check PAS-R004: exercise one real turn through Diapason MCP and Capture, open the same trace
in Tempo, find its completion log in Loki, inspect exporter auth/tenant routing, and verify no content
or credentials appear. Local exporter/trace assertions are necessary but do not replace this gate.
