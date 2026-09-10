# Minimal ACA and integration handoff

Each project is an independent source and Docker context with `pyproject.toml`, `src/`, `tests/`, `docs/`, `requirements*.txt`, `Dockerfile` and `VERSION`. No runtime import references the sibling or parent project. The Python 3.12 image, port 8000/`PORT`, build arguments and build metadata remain. Docker launches `capture.asgi:app` or `pascal.asgi:app` from `/app`.

Run local Uvicorn from the selected project root so existing local configuration/keystore/VERSION paths resolve there. Install each project in its own environment; public company module names intentionally overlap. Wheel builds and isolated installed-import/ASGI checks pass. Container/ACA execution has not been exercised.

Use the existing `CHAT_CONFIG` / root `config.json` and `JWT_KEYSTORE_P12_B64` / keystore conventions. Preserve issuer `diapason-agent`, roles, revocations, identity headers, Blob scopes/containers and encrypted MCP forwarding. `src/<package>/company/` is a physical source grouping; installed public imports remain `dia_jwt`, `settings`, `mcp_context`, etc. Internal `dia_jwt` files and all company module contents remain byte-identical.

Capture is a dedicated workflow service: its GET/POST `/api/skills/intelligence-contract` and auth contracts remain, while `/health` and `/api/health` expose build health and `/api/refresh-prompt` refreshes only Capture's catalog. It has no Pascal UI/static, i18n API, session CRUD or system-prompt dependency. Extraction still persists session turns/artifacts with the existing company storage interface. Pascal retains all original endpoints and frontend/static files; build its existing frontend bundle before Docker when required by the host.

Capture's `config/` contains the original nine prompt/catalog/XML source assets. They are excluded from the container and remain published to the original Blob keys by company release conventions. No local-file loader or new upload script is introduced. No Terraform, CI, secret, RBAC or deployment changes are included.

ACA containers must listen on the configured ingress target port; supply runtime settings through the existing managed configuration. The platform owner should retain existing health checks and termination behavior using [Microsoft's container guidance](https://learn.microsoft.com/en-us/azure/container-apps/containers). Pass through the existing OTEL environment to the same Loki/Tempo destinations and choose the service resource name through existing conventions. No metrics endpoint is added.

## Entry paths and actual status

| Intended path | What exists here | External work still needed |
| --- | --- | --- |
| Classic Diapason UI -> existing extraction HTTP contract | Capture serves the original multipart GET/POST path, auth dependencies, responses and session header. Offline contract tests pass. | Point the established company host/proxy at the Capture ACA with unchanged auth/headers/session scope. The classic host code is not in this repository, so live wiring is unverified. |
| Pascal explicit slash/@ action, selected PDF + trade type, prefilled UI | Original frontend token, file picker, request and response handling are untouched. Pascal retains its local Capture compatibility route to keep this working. | Route that same contract to Capture using the company integration layer, preserve active-session linkage and prefilled host UI. Slash aliases beyond the existing frontend are not invented. |
| Pascal invokes Capture as a tool | Pascal's existing dynamic, per-user MCP discovery/filtering/call loop is preserved and can call whatever tools that server exposes. | Company must expose Capture through its existing MCP implementation and define how an authorized selected PDF and explicit trade type are passed. No such tool/upload reference contract is present here. This path is not claimed working. |

After those owners deliver routing and MCP exposure, verify the three paths with real identities and the unchanged model, then remove Pascal's temporary `src/pascal/compat/capture/` implementation and its no-longer-used extraction dependency. Do not replace the MCP proxy with direct REST or add a global tool catalogue in this repository.

## Live acceptance owned by integration/platform teams

- Confirm the actual Azure deployment/model and v1 compatibility before the sole SDK-constructor migration; keep Chat Completions/tool/temperature behavior.
- Build/run each standalone image with existing configuration, check `/health`, authenticate using current JWTs, and confirm revocation and tenant/user/instance binding in the deployed setup.
- Confirm Blob catalog/prompt bytes at their existing keys, session read/write behavior and reference-resolution calls for known sample PDFs/trade types.
- Check JSON/SSE history, sources, usage, Capture UI prefill and trace correlation in the existing environment; confirm no prompt/PDF/XML/tool payload in AI telemetry.

These checks are handoff requirements, not locally completed integration claims. No access, secret, RBAC or infrastructure change is requested by this refactor.
