# Pascal observability

Both applications keep an identical local `observability/telemetry.py` module inside their own
package (see [intentional duplication](reuse.md)): OTLP/HTTP protobuf,
batch logs/spans, periodic metrics and lifespan flush. No LangSmith account or new cloud service is
required. The explicit compatibility mode preserves the existing Loki/Tempo environment contract.

## Routing contract

| Configuration | Behavior |
|---|---|
| OTEL_SERVICE_NAME / OTEL_RESOURCE_ATTRIBUTES | Service/environment resource attributes; keep current deployment naming |
| OTEL_EXPORTER_OTLP_TRACES_ENDPOINT | Full trace URL, passed as-is |
| OTEL_EXPORTER_OTLP_LOGS_ENDPOINT | Full log URL, passed as-is; often Loki /otlp/v1/logs |
| OTEL_EXPORTER_OTLP_METRICS_ENDPOINT | Explicit full metrics receiver URL; the only way to enable metrics export |
| DIAPASON_OTLP_ENDPOINT_MODE=legacy_full_signal | Default: generic OTLP_ENDPOINT is the old full-signal fallback; generic logs also require PROTOCOL |
| DIAPASON_OTLP_ENDPOINT_MODE=standard | Generic base URL gains /v1/traces or /v1/logs; explicit signal URLs still win |
| OTEL_EXPORTER_OTLP_PROTOCOL / signal-specific *_PROTOCOL | Only http/protobuf supported by these exporters |
| OTEL_EXPORTER_OTLP_HEADERS / signal-specific *_HEADERS | URL-decoded headers; a nonempty signal-specific set replaces the generic set |
| OTEL_EXPORTER_OTLP_TOKEN | Legacy Bearer fallback when no explicit headers exist |
| OTEL_EXPORTER_OTLP_SCOPE_ORG_ID | Legacy token fallback adds explicit tenant to all signals; logs default to mcc only |

For an unchanged deployment, keep its exact signal URLs. For a new collector, prefer explicit signal
URLs or consciously select standard mode. Do not silently reinterpret an existing generic URL.
The compatibility mode is intentionally not the standard base-URL default.
[OTLP endpoint specification](https://opentelemetry.io/docs/specs/otel/protocol/exporter/).

Loki stores logs; Tempo stores traces. Neither existing signal URL should be assumed to store metrics.
Have SRE supply a metrics-capable OTLP collector/backend (for example a collector feeding the approved
Prometheus/Mimir platform); provision it in the platform repository, not implicitly in this app.
Metrics stay disabled until the explicit metrics endpoint is set. No backend/dashboard was deployed.

## Metrics

| Instrument | Type/unit | Labels |
|---|---|---|
| diapason.operation.count | Counter / operations | fixed operation name, success/error/cancelled |
| diapason.operation.duration | Histogram / seconds | same |
| diapason.turn.count | Counter / turns (Pascal) | allowlisted terminal status |
| diapason.chat.time_to_first_token | Histogram / seconds (Pascal) | none |
| diapason.model.token.usage | Counter / tokens | input/output, estimated true/false |

These are application metrics, not claims to implement a complete stable GenAI semantic convention.
Azure-reported usage is recorded per response; estimates are marked. Completion metrics count business
status, not just HTTP 200 (an SSE turn may fail after headers). Operation status also works when spans
are unsampled or tracing export is disabled. Use SDK/backend histogram buckets and aggregation that
match measured traffic before adopting SLOs. OTel FastAPI instrumentation may emit its own HTTP
metrics as well; inspect the pinned SDK's names and cardinality in the actual collector.

No customer, user, session, tool arguments, PDF, trade_type or prompt is an application metric label.
Do not insert those into resource attributes either. Resource labels should be service/version/
environment, not unbounded tenant dimensions.
[Python exporter guidance](https://opentelemetry.io/docs/languages/python/exporters/).

## Privacy and correlation scope

FastAPI extracts incoming W3C context. Explicit downstream adapters inject it. Application operation
spans disable automatic exception recording/status descriptions and record only error class/code.
Application log export is restricted to capture./diapason./pascal. operational loggers. No blanket
HTTPX or model instrumentation captures arbitrary downstream URLs or payloads. Inbound header
capture is explicitly disabled/sanitized, even if ambient OTel header settings exist. Graph execution
disables ambient LangSmith content tracing.

This is a controlled application telemetry policy, not universal DLP. FastAPI's HTTP instrumentation
still describes requests; never put tokens or contract data in URLs/query parameters. Upstream proxy
logs, third-party console logs, newly added logger calls and collector transforms require their own
review. Debug HTTP results and stored chat transcripts are not telemetry and retain separate policies.

Both suites run `scripts/telemetry_check.py` in an isolated process against a real loopback OTLP
collector. Tests decode protobuf logs, spans and metrics, check signal paths/auth/tenant headers,
trace/log correlation, expected token values, label boundaries and absence of fixture secrets.
They do not establish the actual corporate collector's routing or retention. Release gate R004 must
inspect one real trace/log pair and the approved metrics backend before rollout.

## Existing Grafana compatibility

The completion serializer retains the original ordered adjacent prefix:
`customer user session tokens_in tokens_out cost_usd tools skills`.
The literal `skills` log field is an external dashboard alias only; application logic has no such
feature. This order matters: the original dashboard generator uses a regex, not arbitrary logfmt
field ordering. A regression test matches the original ordering.

New fields follow that prefix: instance, cached tokens, Blob/backend, terminal status, persisted,
duration, rounds, first-token time, prompt version and trace/span IDs. Query previews are removed.
Dashboard panels requiring query_preview must stop relying on content capture. IDs remain in
access-controlled logs/spans for compatibility, never in metric labels.

`chat.completion` owns model/tool child spans. Local validation failures do not create fake remote
tool calls. Sanitized failed/partial status is visible even if the route returned SSE HTTP 200.
Suggested measures: completed-and-persisted turn fraction, cancellation separately, first-token and
turn p95, model/tool failures, budget exhaustion and any persistence failure. SRE must choose
thresholds and runbooks from dev traffic before creating alerts.
