"""Wire-level constants retained from the classic Diapason integration."""

LEGACY_CAPTURE_PATH = "/api/skills/intelligence-contract"


def capture_settings(config: dict) -> dict:
    block = config.get("capture")
    if isinstance(block, dict):
        return block
    previous = config.get("intelligence_contract")
    return previous if isinstance(previous, dict) else {}


def public_result(result: dict) -> dict:
    output = dict(result)
    steps = output.pop("steps", None)
    if steps is not None:
        # These display-field names belong to the existing UI contract, not to
        # Capture's internal workflow or a claim that it called an MCP server.
        output["tool_trace"] = [
            {
                "name": "capture" if step["operation"] == "extract_xml" else "resolveReferences",
                "tool": step["operation"],
                "mcp_label": "Capture" if step["operation"] == "extract_xml" else "Diapason",
                "duration_ms": step["duration_ms"],
                "arguments": step["metadata"],
                **(
                    {"transport": "direct_http"} if step["operation"] == "resolveReferences" else {}
                ),
            }
            for step in steps
        ]
    output.pop("session_artifacts", None)
    output.pop("timings_ms", None)
    return output


USER_ID_HEADER = "X-Diapason-User-Id"
CUSTOMER_ID_HEADER = "X-Diapason-Customer-Id"
CHAT_SESSION_HEADER = "X-Diapason-Chat-Session"
DIAPASON_API_TOKEN_HEADER = "X-Diapason-Mcp-Token"
DIAPASON_SCOPE_HEADER = "X-Diapason-Mcp-Scope"
DIAPASON_BASE_URL_HEADER = "X-Diapason-Mcp-Base-Url"
REQUEST_ID_HEADER = "X-Request-Id"

JWT_KEYSTORE_ENV = "JWT_KEYSTORE_P12_B64"
JWT_KEYSTORE_PATH = "jwt_keystore.p12"
JWT_ISSUER = "diapason-agent"
JWT_REVOCATION_PATH = "data/jwt_revoked.json"

LEGACY_CATALOG_PREFIX = "skills/intelligence-contract"
DEFAULT_CATALOG_BLOB = f"{LEGACY_CATALOG_PREFIX}/catalog.json"
