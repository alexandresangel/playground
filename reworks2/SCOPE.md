# Preservation scope (before implementation)

Only `reworks/` may change. The original tree is the characterization oracle; `original-sha256.json` records every original file before implementation. No commits or deployments.

## Immutable company boundaries

Copy `dia_jwt/`, `auth_setup.py`, `mcp_context.py`, `mcp_rpc.py`, `session_store.py`, `blob_client.py`, `settings.py`, `i18n.py`, `build_info.py`, `tool_audience.py`, `source_extract.py`, `prompt_loader.py`, `config.example.json`, `system_prompt.md`, `frontend/`, `static/`, `locales/` byte-for-byte wherever delivered. Keep telemetry bootstrap and destinations. Preserve existing route handlers, auth dependencies, serialization, headers, errors and persistence. Only AI call sites and AI observability in `app.py` may change.

## AI-owned work

Pascal: typed LangGraph model -> tools -> model loop shared by JSON/SSE; preserve their existing differences, prompts, discovery, invocation order, source handling, usage and round limits. Capture: validate -> extraction -> reference resolution -> result, preserving duplicate catalog lookup and error order. Move Python naming from `skills.intelligence_contract` to `capture`. Preserve legacy route/blob/config/storage/telemetry names. Add content-free spans and offline characterization tests. No new matching, model, prompts, memory or orchestration policies.

## Integration blockers and precedence

The original frontend directly posts PDF/trade_type to the agent HTTP extraction route. There is no Capture service call or Capture MCP exposure in this repository. Removing local execution before external routing exists would break an enabled route. The no-break instruction therefore takes precedence: retain a documented temporary local Capture compatibility implementation in Pascal. Capture owns the standalone workflow and source prompt assets; removing Pascal's local compatibility files is a later integration task. No direct REST proxy, new MCP tool or assumed catalog is introduced.

Azure config has only placeholders, so live deployment compatibility cannot be established locally. Preserve the single existing Azure client pending confirmation of v1 support; do not add an alternate client or mode switch. Record the exact v1 handoff from official documentation.

Capture receives the existing extraction, auth, sessions, health, refresh and static/i18n boundaries. Pascal retains every original route. Classic host routing to Capture and automatic tool exposure require external owners; offline tests cannot prove those paths live.

## Follow-up scope: clean source packages and dedicated Capture service

The user subsequently requested all Python source under `src/<project>/`, removal of `workflow_support`, a split of Pascal's large `app.py`, and a fresher Capture base focused on the intelligence-contract AI workflow. That direction supersedes the earlier flat layout and unnecessary copied Pascal service surface in Capture.

Runtime source now lives under `src/capture/` and `src/pascal/`; tests and docs have their own root directories. Original company files move together under `src/<project>/company/`, with all bytes and public imports preserved by packaging. Pascal routes, schemas, frontend/static and config remain. Capture omits Pascal frontend/static, persona/system-prompt setup, chat and session-management routes; extraction still retains its HTTP/auth/MCP/storage behavior. Capture health and refresh are service-specific. New module launch targets are reflected in Docker and README commands.

No company protocol, authorization, storage implementation, frontend source, model, prompt or workflow business behavior is redesigned. Missing ACA routing, automatic Capture MCP exposure and Azure v1 verification remain external work.
