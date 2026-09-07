# Research and decisions

Research date: 2026-09-07.

## Legacy findings

- The current endpoint is `GET|POST /api/skills/intelligence-contract`; the browser needs the GET to
  fill the selector and POSTs `pdf`, `trade_type`, `debug`, and `session_id`.
- Success is handed to the parent Diapason UI through `dia-agent-open-trade` with view/menu/type/XML.
- Extraction is deterministic except for one Azure OpenAI call. The prompt is selected by trade type,
  and code overwrites `<tradeType shortname>` after model output.
- Reference resolution currently makes a synchronous MCP `resolveReferences` call. The MCP server then
  POSTs form data to `/api/v2/importData/resolveReferences`.
- Authentication has two layers: agent RS256 JWT/tenant headers at ingress and a per-request Diapason
  API token/base URL/scope downstream.
- Existing telemetry exports logs/traces by OTLP/HTTP and propagates W3C trace context.

## External guidance applied

- Azure Container Apps has a 240-second HTTP ingress timeout, which makes keeping the compatibility
  request under that budget important. [ACA ingress overview](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview)
- ACA distinguishes startup, liveness, and readiness probes; a successful HTTP probe returns 2xx/3xx.
  Capture provides separate liveness/readiness endpoints and relies on the shared platform module for
  probe wiring. [ACA health probes](https://learn.microsoft.com/en-us/azure/container-apps/health-probes)
- Microsoft recommends managed identities to avoid app-managed credentials. Capture uses a
  system-assigned identity and least-privilege blob-reader RBAC for prompt configuration.
  [ACA managed identities](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity)
- ACA can reference Key Vault secrets through managed identity. The existing organization flow uses
  Infisical plus ACA secret references; secrets remain references rather than image content.
  [ACA secrets](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets)
- LangGraph’s `StateGraph` is built from typed state, nodes, edges, and compilation; runtime context is
  intended for per-run dependencies. Capture uses runtime context for request credentials/adapters.
  [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
- LangGraph persistence checkpoints state at graph steps. Since this state includes sensitive contract
  content, persistence is intentionally omitted until encryption and retention are designed.
  [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- A mounted Python MCP application needs its session manager entered by the host lifespan. The ASGI
  host does this explicitly and keeps MCP stateless for replica-independent routing.
  [MCP Python SDK ASGI guidance](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/run/asgi.md)
- MCP distinguishes user-controlled prompts/actions from model-controlled tools. `/capture` belongs to
  the UI action path while the `capture` tool is for model-controlled invocation.
  [MCP server primitives](https://modelcontextprotocol.io/specification/2025-11-25/server/index)
- Loki accepts OTLP logs at `/otlp/v1/logs`, and Tempo supports OTLP/HTTP with tenant headers. Capture
  keeps the existing exporter variables and adds signal-specific header support.
  [Loki OTLP](https://grafana.com/docs/loki/latest/send-data/otel/),
  [Tempo OTLP](https://grafana.com/docs/tempo/latest/set-up-for-tracing/instrument-send/set-up-collector/otel-collector/)

## Decisions

1. Name the project, ACA, service, logs, and MCP tool `capture`; retain “intelligence-contract” only on
   the classic wire path/catalog prefix.
2. Use one graph behind HTTP and MCP; no subagent and no duplicate business implementation.
3. Keep the current synchronous response in Sprint 1 to avoid UX/backend changes.
4. Call Diapason REST directly using adapted `diapason-mcp-main` logic; Capture has no MCP client.
5. Do not persist graph state or chat artifacts.
6. Keep current prompt/extraction behavior; proposed accuracy changes require evaluation first.

