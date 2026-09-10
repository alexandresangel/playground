# Capture and Pascal

Two independent Python projects, with all runtime source under their own `src` package:

| Project | AI entry point | Application |
| --- | --- | --- |
| [Capture](capture/README.md) | `src/capture/workflow/graph.py` | Dedicated intelligence-contract extraction service |
| [Diapason-agent / Pascal](diapason-agent/README.md) | `src/pascal/agent/graph.py` | Existing chat application, shared JSON/SSE agent graph |

Each project has `pyproject.toml`, `src/`, `tests/` and `docs/`. There is no root `app.py` or `workflow_support` package. Pascal's ASGI entry is five lines; route handlers, agent logic, company dependencies and observability have separate modules. Capture contains no Pascal frontend, system prompt, chat loop or session-management API.

Company implementations are byte-identical under `src/<package>/company/`. Packaging preserves public imports such as `dia_jwt`, `settings` and `mcp_context`. The projects need separate environments; neither imports its sibling.

Capture preserves the extraction HTTP/security/storage/MCP contract. Pascal preserves all original routes and frontend files. Until company routing connects the separate ACA, Pascal keeps its existing upload execution under `src/pascal/compat/capture/`. No Capture MCP exposure or cross-service client is invented. Azure v1 compatibility still requires the actual deployment details.

[Scope](SCOPE.md) | [Decisions and dependencies](DECISIONS.md) | [Handoff](HANDOFF.md) | [Verification](VERIFICATION.md) | [Python inventories](PYTHON_INVENTORY.md)

Only `reworks/` was changed. No commits or deployment. `python -B reworks/verify_boundaries.py` audits the original baseline, company copies, retained interfaces and prompt assets; it is read-only and has no runtime role.
