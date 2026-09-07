# Pascal — Diapason company agent

Standalone rework of the company chat, using LangGraph for the core agent loop. All files here can be
extracted into a separate repository; there are no Python imports from the legacy parent or Capture.
The HTTP/UI/security/session boundaries remain compatible. No live service has been changed.

The agent has one graph: model → validated tools → model → final response. JSON and SSE share that
graph and the same persistence lifecycle. No graph checkpointer is enabled: the existing scoped Blob
transcripts remain the memory source of truth. Capture is a separate HTTP/MCP service, not a prompt
skill or an extraction module inside Pascal.

## Run locally

Use Python 3.12+ and uv. From this directory:

```powershell
uv sync --locked --extra dev
uv run --locked --extra dev pytest
uv run --locked --extra dev ruff check src tests scripts
uv run --locked --extra dev ruff format --check src tests scripts
uv run --locked --extra dev mypy
```

For the real app, supply `CHAT_CONFIG` JSON or a local ignored `config.json`, using
`config.example.json` as the shape. Supply the existing PKCS#12 via `JWT_KEYSTORE_P12_B64` or
`jwt_keystore.p12` and its password in config. Blob authentication stays DefaultAzureCredential
with the existing CLI fallback; use approved development credentials. Tests use explicit doubles,
never a production fallback to in-memory sessions.

```powershell
uv run uvicorn pascal.main:create_app --factory --host 127.0.0.1 --port 8000
```

Build the unchanged-layout frontend with `npm ci` then `npm run build` from `frontend`.
The UI still uses the existing host-provided token/config handshake. `/capture` and `@capture` enter
the existing PDF/trade-type composer when Capture is enabled; the old token remains an alias.
No credential should be put into a URL or committed to the repository.

## Boundaries

- `src/pascal/agent`: state, graph, prompt snapshot, context/cost limits, turn lifecycle.
- `src/pascal/adapters`: async Azure model and stateless MCP HTTP, existing Blob connection logic.
- `src/pascal/tools`: tenant-scoped catalogue, deterministic routing, audience and source adapters.
- `src/pascal/security`, `sessions`: preserved JWT/Fernet and Blob boundary behavior.
- `src/pascal/api`: compatible chat/session/system routes and the Capture composer proxy.
- `src/pascal/observability`: existing Loki/Tempo OTLP configuration and content-free events.

`/health` is process liveness; `/ready` means startup completed, not that every external dependency is
reachable. Session/auth administration endpoints and `/api/chat`, `/api/chat/stream`, `/api/mcp/tools`
retain their paths. The old chart fields remain present but null: the fabricated sample chart is gone.

See [SPRINT.md](SPRINT.md) for task ownership and verification, [NEXT_STEPS.md](NEXT_STEPS.md) for
explicitly deferred platform/product work, and the `docs` directory for architecture and contracts.
Local tests are not a production-readiness certificate; release gates are separate on the board.
The dated [verification report](docs/verification.md) distinguishes executable local evidence from
the connected CI, Azure, host-UI and real-model checks still needed before rollout.
