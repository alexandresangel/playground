# Pascal as MCP host

Pascal owns the model conversation, caller identity, permitted tools and application resources.
`mcp/host.py:McpHost` owns the HTTP connection pool and creates an explicit server-scoped
`McpClient`. The client uses the official Python SDK's Streamable HTTP transport and ClientSession
for initialize, capability/protocol negotiation, initialized notification, JSON/SSE transport and
teardown. This follows the separation of host, clients and servers in the
[MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture).

## Lifetime and security

Each catalog page or tool operation creates a bounded, initialized client session for exactly one
server and caller context. That operation owns its cookie jar/session headers; the host lends sockets,
not another customer's cookies or bearer. Initialization, execution and teardown share one configured
deadline and coroutine. Clients are closed and the host pool is closed at app shutdown.

This is deliberately an operation-scoped connection policy suited to the current stateless Diapason
server, not a tenant-indexed pool of indefinitely live MCP sessions. The SDK handles stateful servers
during an operation (tested), but no conversational state is retained across separate tool calls.
If a future server requires cross-call session state, add an explicitly owned session lifetime with
eviction, identity binding and shutdown tests; do not claim that feature is implemented.

The host enforces tool visibility/selection and argument schemas before dispatch. Incoming credentials
are never taken from model arguments. Extra servers get configured headers only; trusted Capture
identity forwarding requires an explicit opt-in. Remote schemas cannot trigger network downloads.
Raw and decoded response sizes are bounded; no redirects or automatic tool POST retries.
Read-only annotations optimize scheduling, not permissions.

## Feature disposition versus the original

| Feature | Current disposition |
|---|---|
| Diapason Fernet bearer payload | Retained: base_url, scope, api_token; original security policy |
| Named extra servers/static headers | Retained; dynamic Capture forwarding is opt-in |
| JSON and SSE tool responses | Retained through the actual SDK, not a hand-written SSE parser |
| tools/list pagination/audience/source handling | Retained with TTL/bounds/identity-partitioned cache |
| Qualified names and /server / @tool routing | Retained; ambiguous names fail closed |
| Initialize and protocol/session handling | Added through SDK lifecycle; no forced protocol header |
| Old protocol_version config hint | Removed from application context; SDK negotiates supported versions |
| Legacy manual JSON-RPC client | Replaced; no duplicate protocol stack or credential/cookie globals |
| Notifications required by transport | SDK-managed, not business callbacks |
| Sampling, elicitation, filesystem roots, prompts/resources UI | Not advertised or implemented; no authorization inferred for these capabilities |
| Long-lived stateful conversation with one server | Not supported across operations; requires a separately reviewed lifetime |
| Tool-result caching or mutation retries | Not introduced; unsafe without server-specific contracts |

The current sibling MCP source declares a stateless JSON-response server. Protocol tests run actual
FastMCP servers in all four combinations of stateful/stateless and JSON/SSE, and cover initialize
through teardown. These tests do not establish every future protocol extension or real corporate auth.
