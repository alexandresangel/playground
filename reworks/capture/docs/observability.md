# Loki / Tempo observability

Capture uses OTLP/HTTP just like the current agent and MCP services. Existing deployment helpers can
continue to populate:

- `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` (full trace signal URL)
- `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` (full log signal URL, commonly ending `/otlp/v1/logs`)
- `OTEL_EXPORTER_OTLP_ENDPOINT` plus `OTEL_EXPORTER_OTLP_PROTOCOL` as the generic fallback
- `OTEL_EXPORTER_OTLP_HEADERS`, signal-specific `*_HEADERS`, or
  `OTEL_EXPORTER_OTLP_TOKEN`
- `OTEL_EXPORTER_OTLP_SCOPE_ORG_ID`
- `OTEL_RESOURCE_ATTRIBUTES` such as `deployment.environment.name=dev`

`OTEL_SERVICE_NAME` defaults to `capture`. W3C trace context is extracted by FastAPI instrumentation
and injected into the direct Diapason HTTP request.

## Span shape

```text
HTTP POST /api/skills/intelligence-contract
└── capture.validate_input
    └── capture.extract_text
        └── capture.select_prompt
            └── capture.llm_extract
                └── capture.normalize_xml
                    └── capture.resolve_references
                        └── HTTP POST Diapason
                            └── capture.emit_result
```

LangGraph executes the nodes sequentially; the indentation above describes causality, while trace UIs
may show nodes as siblings under the request span. Node attributes are low cardinality: trade type,
view entity, result success, model name, and token counts. Logs include node name, event, duration,
request ID, status, and error class—not contract content.

Suggested alerts: readiness failures, HTTP 5xx rate, resolve failure ratio, end-to-end p95 near 200
seconds, per-node p95 regression, and ACA memory saturation.

