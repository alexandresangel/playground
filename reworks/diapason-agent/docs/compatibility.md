# Compatibility contract

This rework changes Pascal's core and its own deployment package, not Diapason backend endpoints.
No token migration or storage backfill runs on startup.

| Boundary | Kept | Deliberate difference / qualification |
|---|---|---|
| JWT | RS256 PKCS#12, issuer `diapason-agent`, exp/iat validation, same mint/revoke behavior | Configuration injected; no new identity provider |
| Roles | chat or admin for chat; admin for mint/revoke; refresh specifically for refresh | Admin alone still does not grant refresh |
| Tenant | X-Diapason-User-Id, X-Diapason-Customer-Id; claim customer mismatch rejected | Same parsing and instance-sub normalization |
| Diapason MCP | token/scope/base-url request headers → Fernet bearer; named extras/static headers | Async pooled transport; explicit optional Capture identity forwarding |
| Tool visibility | technical tools hidden, naming/qualified tools, mention exclusions | Ambiguous routes fail closed; unknown @ is ordinary prose |
| JSON chat | POST /api/chat; message, session_id, client_timezone; answer_markdown, tool_trace, sources, mode | Additive usage/status/persisted fields; chart fields null |
| SSE chat | POST /api/chat/stream; data JSON delta/status/tool/sources/done then [DONE] | Keepalives; done after persistence; explicit partial/error status |
| Session header | X-Diapason-Chat-Session | Read from body or header; response retained |
| Sessions | same list/create/detail/delete paths and required field shapes; instance/customer/user prefix | Storage offloaded to worker threads; missing-record append bug fixed; optional sanitized tool-error code retained |
| Blob | existing records, max_turns, ETag writes, soft-delete archive | No graph checkpoint/Redis/vector store; per-process concurrent-turn rejection |
| Prompt | config Blob system_prompt.md and refresh role; local fallback only when no account configured | Snapshot hash, no duplicate MCP schema summary; new local default is conversational |
| Locale | X-Diapason-Locale, /api/i18n query override, en_us/fr_fr bundles | Locale/time context after stable system prefix |
| Health | /health and /api/health shapes/version/environment conventions | /ready added; no downstream fan-out on probe |
| Capture | old GET/POST /api/skills/intelligence-contract multipart contract and open-trade result/event | Proxy to `capture.base_url`; minimal session receipt; no extraction inside agent |
| Observability | same OTLP HTTP endpoints/tokens/tenant headers; same service naming supplied by deployment | More child spans, content-free log fields and correlation IDs |

The `intelligence_contract` extraction configuration is no longer used by Pascal. Set
`capture.enabled/base_url` for the composer and separately enable the named MCP server if desired.
Its extraction catalog/prompts/rates belong to Capture. The original URL stays solely for UI
compatibility. Do not enable `forward_diapason_identity` for untrusted servers: it sends the existing
agent JWT and the Diapason API token to that configured destination.

JWT revocations remain replica-local and malformed/unreadable revocation files retain the legacy
fail-open behavior. Wildcard credentialed CORS remains the compatibility default. Tenant headers and
base URLs still rely on the surrounding trusted integration. These are documented risks, not newly
endorsed security designs; see PAS-F001/F003/F010 before expanding deployment.

The new core never grants permissions based on tool annotations. Current backend authorization still
applies to every call. The caller's scoped tool selection is enforced before dispatch; credentials
come only from the request/config adapters, never model arguments.

Blob's existing usage normalizer still persists input/output/total tokens and cost. Optional
cached/estimated usage details are available on the current response and telemetry, not a new historic
record schema. The added optional tool-trace `error` contains a short allowlisted-format code, never
an exception body; older records without it remain readable.
