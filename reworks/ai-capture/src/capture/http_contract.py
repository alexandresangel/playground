"""Shared HTTP names for Capture, the Diapason proxy, and MCP.

Wire names stay compatible with existing callers. The chat session header is
an opaque correlation ID only; Capture never creates or reads stored sessions.
"""

AUTHORIZATION_HEADER = "Authorization"
USER_ID_HEADER = "X-Diapason-User-Id"
CUSTOMER_ID_HEADER = "X-Diapason-Customer-Id"
LOCALE_HEADER = "X-Diapason-Locale"
CORRELATION_HEADER = "X-Diapason-Chat-Session"
DIAPASON_API_JWT_HEADER = "X-Diapason-Mcp-Token"
DIAPASON_SCOPE_HEADER = "X-Diapason-Mcp-Scope"
DIAPASON_BASE_URL_HEADER = "X-Diapason-Mcp-Base-Url"
MCP_VERSION_HEADER = "X-Diapason-Mcp-Protocol-Version"
MCP_PROTOCOL_HEADER = "MCP-Protocol-Version"
TRACEPARENT_HEADER = "traceparent"
TRACESTATE_HEADER = "tracestate"

# Browser clients can read the returned correlation ID across origins.
EXPOSED_RESPONSE_HEADERS = [CORRELATION_HEADER]