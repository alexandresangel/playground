# Security model

## Preserved controls

- Caller JWT: RS256, same PKCS#12 material, required `iss=diapason-agent`, required `iat`/`exp`, and
  accepted role intersection `chat|admin`.
- Revocation: the same `jti` and `sub` JSON checks are applied.
- Tenant identity: integer user/customer headers are required on capture operations. If the JWT has a
  `customer_id`, it must equal the header.
- Diapason authorization: API token, base URL, and integer scope are required per capture request.
  They are not accepted as MCP tool arguments and are not exposed to the model.
- PDF: decoded size limit, `%PDF-` magic check, and no file persistence. MIME is not trusted because
  legacy callers do not all send it consistently.
- Egress: HTTPS is required by default. `allowed_diapason_hosts` can enforce an environment-specific
  hostname allowlist to reduce SSRF exposure; local HTTP is an explicit opt-in.
- Container: non-root UID/GID 10001 and no secrets in the image.

## Sensitive-data rules

- Never log PDF bytes/text, model content, source/resolved XML, bearer tokens, or the full downstream
  URL.
- No LangGraph checkpointer is configured.
- Public responses omit `session_artifacts` and timings, matching the legacy boundary. `debug=true`
  remains compatible and can return sensitive intermediate data to an authenticated caller; keep it
  false in production UI calls and restrict its operational use.
- The service does not persist chat history or contract artifacts.

## Known compatibility debt

The legacy revocation file is process-local. Reproducing it in a multi-replica ACA preserves request
semantics but not coherent revocation propagation. Before enabling more than one replica for broad
production load, move revocations to a shared authoritative store or replace the custom JWT with the
organization’s Entra/OAuth resource-server setup. This is deliberately a follow-up security change,
not silently mixed into the extraction migration.

MCP HTTP authorization is compatibility-first: it validates the same agent-issued JWT on every
request. The MCP specification’s OAuth protected-resource metadata should become the long-term public
integration contract if clients outside Pascal are added.

## Deployment checklist

- Store `CAPTURE_CONFIG`, the PKCS#12 base64, and OTLP credentials in Infisical/ACA secret references.
- Restrict ingress at the platform/reverse proxy where possible; `/health` and `/ready` are the only
  intentionally unauthenticated application routes.
- Set an explicit production `mcp.allowed_hosts` list and `capture.allowed_diapason_hosts` list.
- Grant the managed identity only `Storage Blob Data Reader` on the config container.
- Rotate Azure OpenAI API keys and the signing keystore through the existing secret process.
- Confirm request-body limits and rate limits at the gateway before direct external exposure.
