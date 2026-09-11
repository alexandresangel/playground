# Capture handoff

Capture is an independent src package and Docker build context dedicated to intelligence-contract. The company implementations under `src/capture/common/` were not edited in this continuation, including every `dia_jwt` file. Existing source copies differ from the original only in line endings/final newlines.

The LangGraph workflow preserves PDF validation before catalog/model work, original extraction messages and temperature, explicit trade type, the single `resolveReferences` call, public/debug output and stored artifacts. The blocking resolver is run in a worker thread without changing its RPC transport, caller context or timeout. The catalog hash helper was renamed to fix its collision with the cached version string; startup followed by repeated refresh now works.

The existing multipart/auth contracts serve both the classic UI and Pascal relay. Capture resolves the scoped session and writes exactly one extraction turn. Public responses omit private session artifacts/timing fields as before; debug output remains explicitly available. The legacy URL, Blob names, localized labels and persisted `skill_run` names are retained intentionally.

There is no Pascal chat/frontend, session CRUD or system-prompt startup. `config/` preserves the original catalog/XML/prompt text. Runtime still loads the existing Blob keys; local assets are not a fallback. `config/upload.sh` now resolves the moved project-root config correctly. `deploy/deploy-config.sh` uploads only Capture's catalog/prompts.

Packaging retains top-level company imports without rewriting them. `application.py` is a side-effect-free factory; `capture.asgi:app` performs production startup from the service root. Use an environment separate from Pascal. The image uses this directory alone.

HTTP logging uses endpoint-owned quiet annotations and content-free errors, with no hardcoded AI path list. Workflow spans use the existing telemetry provider and per-run LangSmith opt-out. No new tracing destination or graph persistence backend is introduced.

Offline tests cover a real PDF, model/extraction rules, resolver results and errors, catalog refresh/cache, HTTP metadata/fields/statuses, real JWT/roles/revocation, caller MCP context, scoped sessions, artifacts, startup and telemetry. Two Linux containers also validate direct Capture and Pascal relay with real HTTP; external Blob/model/resolver services are test doubles. No commits, image pushes or Azure deployment were made.

Capture's infrastructure creates its ACA/identity and two Blob grants in a separate state, and reads the existing shared containers as data sources. No duplicate container/group ownership is introduced. Remaining company work is the environment-specific plan/deploy, same JWT/storage/MCP/model setup, Pascal's URL and real host/service acceptance. See [deployment details](DEPLOYMENT.md), [commit-sized tasks](SPRINT.md) and [complete Python inventory](PYTHON_INVENTORY.md).
