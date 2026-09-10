# Verification

Verified locally on 2026-09-10 with Python 3.12.9. Changes remain under `reworks/`; the original directory is not a Git checkout. No commits or deployment were made.

| Check | Result |
| --- | --- |
| Capture: `python -B -m pytest -q` from its project directory | **54 passed**. [Report](verification/capture-tests.txt). |
| Pascal: same command from its project directory | **68 passed, 7 strict expected failures**. [Report](verification/diapason-agent-tests.txt). |
| `python -B reworks/verify_boundaries.py` | **PASS**: all 90 original files unchanged; delivered company bytes, retained routes/schemas/helpers, source layouts, compatibility workflow and nine Capture assets verified. [Report](verification/boundary-audit.txt). |
| Fresh wheel builds and independent installed-package checks | **PASS**: both ASGI modules, public company imports, byte-exact JWT/locales, health and applicable host endpoints loaded without sibling/source paths. [Details](verification/packaging-check.txt). |
| `python -m pip check` | **No broken requirements found**. [Report](verification/dependency-check.txt). |
| Compile delivered Python without bytecode writes | **PASS**: 45 Capture files, 60 Pascal files and the migration verifier. [Report](verification/compile-audit.txt). |

Installed versions are recorded in [verification-environment.txt](verification-environment.txt). Runtime dependency names/lower bounds are retained from the original plus the scoped graph/tracing dependencies; no broad dependency requirement upgrade was made. Each suite emits one third-party Starlette/AnyIO deprecation warning.

## Behavior coverage

- Pascal: 20 differential cases execute the original model/tool loop and compare results/events, model arguments, mutated history, discovery and tool calls. Scenarios cover empty/plain/multiple/malformed/disallowed/error/round-limit behavior. Other tests cover live delta delivery, stream cleanup/retry/usage, HTTP JSON/SSE headers/events, scoped persistence and history.
- Capture: four full original-result comparisons plus validation/error precedence, real PDF text extraction, XML handling, catalog fallback, model parameters, resolver arguments and timeout, artifacts/debug/result fields and explicit trade type.
- Security/interfaces: real signed company JWTs, roles, revocation, customer mismatch, per-user session lookup, credential forwarding/decryption and the existing stateless dynamic MCP transport. Startup tests verify root config/auth paths, Capture-only catalog startup and retained Pascal prompt startup.
- Source audit: every original file is hashed, including detection of additions/deletions outside `reworks`. Company modules and complete `dia_jwt`/locale trees retain their bytes; Pascal frontend/static/config/system prompt are exact. AST comparisons account only for declared package/runtime relocation and AI telemetry/client-close additions. Capture's final telemetry call differs; its extraction business adapter remains equivalent.
- Observability: in-memory exporter tests verify parent correlation, numeric usage, duration/outcome and absence of sensitive content/exception events. Per-run LangSmith tracing is disabled even when enabled by the environment. Company telemetry bootstrap/destinations remain unchanged.

## Deliberate scope and remaining limits

Capture is now a dedicated workflow service. It omits Pascal frontend/static, system-prompt initialization, chat/tool-list UI and session CRUD. Extraction retains its existing HTTP/auth/MCP/session-artifact contract. Capture health exposes build status and refresh loads only its catalog; these operational changes follow the user's request for a fresh Capture base. Pascal retains all original routes.

Seven original source-locale assertions conflict with the unchanged source-extraction implementation. Those exact original cases remain strict expected failures; they are not newly suppressed regressions. The original catalog version function/name collision is also characterized as a later-refresh `TypeError`, not silently fixed. Optional comparisons against original source skip outside this migration workspace; standalone behavior tests remain available.

The two projects build independently, but full cross-service integration is deferred: Pascal retains `src/pascal/compat/capture/` until company routing and Capture MCP exposure exist. There is no new direct REST proxy or invented upload reference contract. The sole original AzureOpenAI client remains because the actual deployment's Azure v1 compatibility is unknown.

No live Azure model, Blob account, company MCP server, classic/Pascal host, Docker image execution, ACA rollout or Loki/Tempo query was tested. Offline checks cannot guarantee nondeterministic model output or deployed integration. [Handoff](HANDOFF.md) records the external acceptance work; [decisions](DECISIONS.md) explain dependencies and preservation exceptions.
