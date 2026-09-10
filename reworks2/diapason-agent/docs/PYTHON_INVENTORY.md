# Pascal Python inventory

Every delivered runtime/test Python file is listed (60 files). Paths are relative to this project; original paths are relative to the untouched original repository. **UNTOUCHED** means byte-identical even when its outer location changed. **REWORKED** means original logic was relocated/adapted. **NEW** means no original file equivalent. Ignored build, virtualenv, bytecode and test artifacts are not source deliverables.

All runtime code is under `src/pascal/`. Company files keep their original installed public names through setuptools; `dia_jwt` internals are untouched. Root `app.py` is replaced by the mapped package modules below. No original repository file was removed or changed.

| Delivered file | Classification | Original path | Reason |
| --- | --- | --- | --- |
| `src/pascal/__init__.py` | **NEW** | - | New package namespace; no runtime initialization. |
| `src/pascal/agent/__init__.py` | **NEW** | - | New package namespace; no runtime initialization. |
| `src/pascal/agent/charts.py` | **REWORKED** | `app.py` | Split the original application into focused modules with explicit runtime dependencies. |
| `src/pascal/agent/context.py` | **REWORKED** | `app.py` | Split the original application into focused modules with explicit runtime dependencies. |
| `src/pascal/agent/discovery.py` | **REWORKED** | `app.py` | Split the original application into focused modules with explicit runtime dependencies. |
| `src/pascal/agent/graph.py` | **REWORKED** | `app.py` | Original JSON/SSE model/tool orchestration expressed as a shared typed LangGraph flow. |
| `src/pascal/agent/mcp.py` | **REWORKED** | `app.py` | Split the original application into focused modules with explicit runtime dependencies. |
| `src/pascal/agent/routing.py` | **REWORKED** | `app.py` | Split the original application into focused modules with explicit runtime dependencies. |
| `src/pascal/agent/service.py` | **REWORKED** | `app.py` | Split the original application into focused modules with explicit runtime dependencies. |
| `src/pascal/api/__init__.py` | **NEW** | - | New package namespace; no runtime initialization. |
| `src/pascal/api/auth.py` | **REWORKED** | `app.py` | Split the original application into focused modules with explicit runtime dependencies. |
| `src/pascal/api/capture.py` | **REWORKED** | `app.py` | Split the original application into focused modules with explicit runtime dependencies. |
| `src/pascal/api/chat.py` | **REWORKED** | `app.py` | Split the original application into focused modules with explicit runtime dependencies. |
| `src/pascal/api/health.py` | **REWORKED** | `app.py` | Split the original application into focused modules with explicit runtime dependencies. |
| `src/pascal/api/middleware.py` | **REWORKED** | `app.py` | Split the original application into focused modules with explicit runtime dependencies. |
| `src/pascal/api/schemas.py` | **REWORKED** | `app.py` | Split the original application into focused modules with explicit runtime dependencies. |
| `src/pascal/api/sessions.py` | **REWORKED** | `app.py` | Split the original application into focused modules with explicit runtime dependencies. |
| `src/pascal/application.py` | **REWORKED** | `app.py` | Split the original application into focused modules with explicit runtime dependencies. |
| `src/pascal/asgi.py` | **REWORKED** | `app.py` | Split the original application into focused modules with explicit runtime dependencies. |
| `src/pascal/company/auth_setup.py` | **UNTOUCHED** | `auth_setup.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/pascal/company/blob_client.py` | **UNTOUCHED** | `blob_client.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/pascal/company/build_info.py` | **UNTOUCHED** | `build_info.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/pascal/company/dia_jwt/__init__.py` | **UNTOUCHED** | `dia_jwt/__init__.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/pascal/company/dia_jwt/__main__.py` | **UNTOUCHED** | `dia_jwt/__main__.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/pascal/company/dia_jwt/auth.py` | **UNTOUCHED** | `dia_jwt/auth.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/pascal/company/dia_jwt/cli.py` | **UNTOUCHED** | `dia_jwt/cli.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/pascal/company/dia_jwt/fastapi.py` | **UNTOUCHED** | `dia_jwt/fastapi.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/pascal/company/i18n.py` | **UNTOUCHED** | `i18n.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/pascal/company/mcp_context.py` | **UNTOUCHED** | `mcp_context.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/pascal/company/mcp_rpc.py` | **UNTOUCHED** | `mcp_rpc.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/pascal/company/prompt_loader.py` | **UNTOUCHED** | `prompt_loader.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/pascal/company/session_store.py` | **UNTOUCHED** | `session_store.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/pascal/company/settings.py` | **UNTOUCHED** | `settings.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/pascal/company/source_extract.py` | **UNTOUCHED** | `source_extract.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/pascal/company/telemetry.py` | **UNTOUCHED** | `telemetry.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/pascal/company/tool_audience.py` | **UNTOUCHED** | `tool_audience.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/pascal/compat/__init__.py` | **NEW** | - | New package namespace; no runtime initialization. |
| `src/pascal/compat/capture/__init__.py` | **NEW** | - | Original extraction/catalog/XML helper relocated; internal naming and AI tracing adapted. |
| `src/pascal/compat/capture/extract_xml.py` | **REWORKED** | `skills/intelligence_contract/extract_xml.py` | Original extraction/catalog/XML helper relocated; internal naming and AI tracing adapted. |
| `src/pascal/compat/capture/graph.py` | **REWORKED** | `skills/intelligence_contract/run.py` | Original extraction sequence expressed in LangGraph. |
| `src/pascal/compat/capture/prompts.py` | **REWORKED** | `ic_prompt_loader.py` | Original extraction/catalog/XML helper relocated; internal naming and AI tracing adapted. |
| `src/pascal/compat/capture/xml_fields.py` | **REWORKED** | `skills/intelligence_contract/xml_fields.py` | Original extraction/catalog/XML helper relocated; internal naming and AI tracing adapted. |
| `src/pascal/observability/__init__.py` | **NEW** | - | New package namespace; no runtime initialization. |
| `src/pascal/observability/ai.py` | **NEW** | - | Small content-free AI span helper and per-run LangSmith tracing opt-out. |
| `src/pascal/observability/http.py` | **REWORKED** | `app.py` | AI-owned content-free tracing/correlation separated from application assembly. |
| `src/pascal/runtime.py` | **REWORKED** | `app.py` | Split the original application into focused modules with explicit runtime dependencies. |
| `tests/conftest.py` | **NEW** | - | Focused offline behavior/contract test. |
| `tests/test_ai_observability.py` | **NEW** | - | Focused offline behavior/contract test. |
| `tests/test_application_runtime.py` | **NEW** | - | Focused offline behavior/contract test. |
| `tests/test_assistant_identity.py` | **REWORKED** | `test/test_assistant_identity.py` | Original characterization test, with package import/asset paths adapted where required. |
| `tests/test_chat_workflow.py` | **NEW** | - | Focused offline behavior/contract test. |
| `tests/test_http_contract.py` | **NEW** | - | Focused offline behavior/contract test. |
| `tests/test_i18n.py` | **REWORKED** | `test/test_i18n.py` | Original characterization test, with package import/asset paths adapted where required. |
| `tests/test_mcp_cluster.py` | **REWORKED** | `test/test_mcp_cluster.py` | Original characterization test, with package import/asset paths adapted where required. |
| `tests/test_mcp_transport.py` | **NEW** | - | Focused offline behavior/contract test. |
| `tests/test_session_summary.py` | **REWORKED** | `test/test_session_summary.py` | Original characterization test, with package import/asset paths adapted where required. |
| `tests/test_source_extract.py` | **REWORKED** | `test/test_source_extract.py` | Original characterization test, with package import/asset paths adapted where required. |
| `tests/test_telemetry_helpers.py` | **REWORKED** | `test/test_telemetry_helpers.py` | Original characterization test, with package import/asset paths adapted where required. |
| `tests/test_tool_audience.py` | **REWORKED** | `test/test_tool_audience.py` | Original characterization test, with package import/asset paths adapted where required. |
| `tests/test_tool_route.py` | **REWORKED** | `test/test_tool_route.py` | Original characterization test, with package import/asset paths adapted where required. |

See [omitted original files](OMITTED_ORIGINAL_FILES.md) for material with no delivered equivalent.
