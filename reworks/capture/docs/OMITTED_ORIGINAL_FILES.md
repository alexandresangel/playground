# Original files omitted from Capture

The original checkout is unchanged. See [PYTHON_INVENTORY.md](PYTHON_INVENTORY.md) for every delivered Python file. The extraction part of `app.py` is split into Capture's runtime/API modules.

| Original paths | Disposition |
| --- | --- |
| `frontend/**`, `static/**`, `system_prompt.md`, `prompt_loader.py` | Pascal chat/frontend concerns; Capture does not load a chat system prompt. |
| `source_extract.py`, `tool_audience.py` and chat/mention/chart helpers from `app.py` | Remain in Pascal. Capture executes the original fixed reference-resolution call, not a chat tool selector. |
| `test/test_{assistant_identity,source_extract,tool_audience,tool_route}.py` | Chat tests live in Pascal. |
| `observability/generate_dashboards.py`, `observability/grafana-agent-mcp-{dev,test,prod}.json` | Original Pascal/MCP dashboards restored in Pascal. Capture uses existing OTEL destinations; service filters can include the new app in the company environment. |
| `skills/__init__.py`, `skills/intelligence_contract/__init__.py` | Replaced by the Capture package/workflow namespace; public legacy names are unchanged. |
| `skills/intelligence_contract/entity_match.py`, `test/test_entity_match.py` | Unused by the original executing workflow; omitted without introducing new matching behavior. |
| `skills/intelligence_contract/config/README.md` | Its upstream analyzer/build-catalog files are absent from the supplied original. Current Capture README and deployment docs describe the delivered assets/upload workflow. |
| Original `docs/01-issues-and-risks.md` through `docs/04-intelligence-contract-design.md` | Superseded by current Capture handoff/deployment/sprint/inventory; preserved in the original. |

Previously missing deployment/package/CI files are now delivered, including the original provider lock and config example. Original catalog, XML and prompt source text is present in `config/`; the moved upload script is fixed. Extraction regression tests and fixture PDF are in `tests/`; the adapted extraction-only live smoke and example config are in `scripts/`.

Shared Blob containers/group grants remain owned by Pascal's original infrastructure state. Capture reads them as data sources and owns only its app/identity grants. Runtime data, private config, credentials, build output and state files are not committed or baked into images.
