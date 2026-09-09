# Integration contracts

This project does not modify the current frontend, Pascal, Tomcat, or the Diapason backend. These are
the contracts for those integrations when their own migration work starts.

## 1. Classic Diapason UI

Keep the current browser behavior and route through the existing same-origin reverse proxy:

1. `GET /api/skills/intelligence-contract` loads `enabled`, `trade_types`, and `prompt_version`.
2. `POST` the selected `trade_type`, PDF, optional `debug=false`, and optional `session_id` to the same
   path.
3. On success, keep emitting the existing parent-window event:

```json
{
  "type": "dia-agent-open-trade",
  "viewEntity": "<response.view_entity>",
  "menuName": "<response.menu_name>",
  "tradeType": "<response.trade_type>",
  "tradeXml": "<response.trade_xml>"
}
```

Tomcat/proxy must forward the agent JWT and all five `X-Diapason-*` identity/API headers. Capture
continues to validate customer binding and uses the Diapason token only for the downstream REST call.

## 2. Pascal user action (`/capture` or `@capture`)

This path is user-controlled and should bypass model routing:

1. Activating `/capture` or selecting `@capture` opens the current composer.
2. The composer explicitly requires a trade type selection and one PDF.
3. Submit to the compatibility HTTP endpoint.
4. Render the existing progress/receipt UI and send `dia-agent-open-trade` unchanged.

The separate pending Pascal rework already includes these command aliases in its existing composer.
Its provenance documents those earlier frontend edits; this refinement leaves the UI frozen.
Pascal's `api/capture_bridge.py` owns the same-origin request and minimal chat receipt, then forwards
HTTP to this service. The original deployed agent has not been changed.

## 3. Pascal model-controlled MCP tool

Register server ID `capture` at `https://<capture-host>/mcp`. The agent must forward, per request:

- `Authorization` with the current Diapason-agent JWT
- `X-Diapason-User-Id`
- `X-Diapason-Customer-Id`
- `X-Diapason-Mcp-Token`
- `X-Diapason-Mcp-Scope`
- `X-Diapason-Mcp-Base-Url`
- W3C `traceparent`/`tracestate`

The current legacy agent supports static headers for extra MCP servers but does not forward these
dynamic tenant headers. The pending `reworks/diapason-agent` now supports explicit
`forward_diapason_identity=true` on the trusted Capture binding. This does not change the original
agent and must not be enabled on untrusted extra servers.

The tool is named `capture` and has two required model arguments:

```json
{
  "trade_type": "iamLoan",
  "pdf_base64": "JVBERi0x...",
  "pdf_filename": "contract.pdf"
}
```

`pdf_filename` is optional and informational. The tool description tells Pascal not to infer a trade
type or call until both required inputs exist. The service validates the decoded PDF again.

Base64 is the compatibility transport for Sprint 1. An opaque, authenticated attachment handle is the
preferred later design because raw base64 increases payload size and should not be placed in the
model’s conversational context.
