"""Wire-level constants retained from the classic Diapason integration."""

LEGACY_CAPTURE_PATH = "/api/skills/intelligence-contract"

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
