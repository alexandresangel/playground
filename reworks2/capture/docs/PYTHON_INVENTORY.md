# Capture Python inventory

Every delivered runtime/test Python file is listed (45 files). Paths are relative to this project; original paths are relative to the untouched original repository. **UNTOUCHED** means byte-identical even when its outer location changed. **REWORKED** means original logic was relocated/adapted. **NEW** means no original file equivalent. Ignored build, virtualenv, bytecode and test artifacts are not source deliverables.

All runtime code is under `src/capture/`. Company files keep their original installed public names through setuptools; `dia_jwt` internals are untouched. Root `app.py` is replaced by the mapped package modules below. No original repository file was removed or changed.

| Delivered file | Classification | Original path | Reason |
| --- | --- | --- | --- |
| `src/capture/__init__.py` | **NEW** | - | New package namespace; no runtime initialization. |
| `src/capture/api/__init__.py` | **NEW** | - | New package namespace; no runtime initialization. |
| `src/capture/api/auth.py` | **REWORKED** | `app.py` | Split the original application into focused modules with explicit runtime dependencies. |
| `src/capture/api/extraction.py` | **REWORKED** | `app.py` | Split the original application into focused modules with explicit runtime dependencies. |
| `src/capture/api/health.py` | **REWORKED** | `app.py` | Dedicated Capture build health and catalog refresh; removes Pascal system-prompt dependency. |
| `src/capture/api/middleware.py` | **REWORKED** | `app.py` | Split the original application into focused modules with explicit runtime dependencies. |
| `src/capture/api/schemas.py` | **REWORKED** | `app.py` | Split the original application into focused modules with explicit runtime dependencies. |
| `src/capture/application.py` | **REWORKED** | `app.py` | Split the original application into focused modules with explicit runtime dependencies. |
| `src/capture/asgi.py` | **REWORKED** | `app.py` | Split the original application into focused modules with explicit runtime dependencies. |
| `src/capture/company/auth_setup.py` | **UNTOUCHED** | `auth_setup.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/capture/company/blob_client.py` | **UNTOUCHED** | `blob_client.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/capture/company/build_info.py` | **UNTOUCHED** | `build_info.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/capture/company/dia_jwt/__init__.py` | **UNTOUCHED** | `dia_jwt/__init__.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/capture/company/dia_jwt/__main__.py` | **UNTOUCHED** | `dia_jwt/__main__.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/capture/company/dia_jwt/auth.py` | **UNTOUCHED** | `dia_jwt/auth.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/capture/company/dia_jwt/cli.py` | **UNTOUCHED** | `dia_jwt/cli.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/capture/company/dia_jwt/fastapi.py` | **UNTOUCHED** | `dia_jwt/fastapi.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/capture/company/i18n.py` | **UNTOUCHED** | `i18n.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/capture/company/mcp_context.py` | **UNTOUCHED** | `mcp_context.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/capture/company/mcp_rpc.py` | **UNTOUCHED** | `mcp_rpc.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/capture/company/session_store.py` | **UNTOUCHED** | `session_store.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/capture/company/settings.py` | **UNTOUCHED** | `settings.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/capture/company/telemetry.py` | **UNTOUCHED** | `telemetry.py` | Company source bytes and public imports preserved; only outer source location changes. |
| `src/capture/observability/__init__.py` | **NEW** | - | New package namespace; no runtime initialization. |
| `src/capture/observability/ai.py` | **NEW** | - | Small content-free AI span helper and per-run LangSmith tracing opt-out. |
| `src/capture/observability/http.py` | **REWORKED** | `app.py` | AI-owned content-free tracing/correlation separated from application assembly. |
| `src/capture/runtime.py` | **REWORKED** | `app.py` | Split the original application into focused modules with explicit runtime dependencies. |
| `src/capture/workflow/__init__.py` | **NEW** | - | Original extraction/catalog/XML helper relocated; internal naming and AI tracing adapted. |
| `src/capture/workflow/extract_xml.py` | **REWORKED** | `skills/intelligence_contract/extract_xml.py` | Original extraction/catalog/XML helper relocated; internal naming and AI tracing adapted. |
| `src/capture/workflow/graph.py` | **REWORKED** | `skills/intelligence_contract/run.py` | Original extraction sequence expressed in LangGraph. |
| `src/capture/workflow/prompts.py` | **REWORKED** | `ic_prompt_loader.py` | Original extraction/catalog/XML helper relocated; internal naming and AI tracing adapted. |
| `src/capture/workflow/xml_fields.py` | **REWORKED** | `skills/intelligence_contract/xml_fields.py` | Original extraction/catalog/XML helper relocated; internal naming and AI tracing adapted. |
| `tests/conftest.py` | **NEW** | - | Focused offline behavior/contract test. |
| `tests/test_ai_observability.py` | **NEW** | - | Focused offline behavior/contract test. |
| `tests/test_application_runtime.py` | **NEW** | - | Focused offline behavior/contract test. |
| `tests/test_capture_workflow.py` | **NEW** | - | Focused offline behavior/contract test. |
| `tests/test_extract_trade_type.py` | **REWORKED** | `test/test_extract_trade_type.py` | Original characterization test, with package import/asset paths adapted where required. |
| `tests/test_http_contract.py` | **NEW** | - | Focused offline behavior/contract test. |
| `tests/test_i18n.py` | **REWORKED** | `test/test_i18n.py` | Original characterization test, with package import/asset paths adapted where required. |
| `tests/test_ic_catalog.py` | **REWORKED** | `test/test_ic_catalog.py` | Original characterization test, with package import/asset paths adapted where required. |
| `tests/test_mcp_cluster.py` | **REWORKED** | `test/test_mcp_cluster.py` | Original characterization test, with package import/asset paths adapted where required. |
| `tests/test_mcp_transport.py` | **NEW** | - | Focused offline behavior/contract test. |
| `tests/test_session_summary.py` | **REWORKED** | `test/test_session_summary.py` | Original characterization test, with package import/asset paths adapted where required. |
| `tests/test_telemetry_helpers.py` | **REWORKED** | `test/test_telemetry_helpers.py` | Original characterization test, with package import/asset paths adapted where required. |
| `tests/test_xml_fields.py` | **REWORKED** | `test/test_xml_fields.py` | Original characterization test, with package import/asset paths adapted where required. |

See [omitted original files](OMITTED_ORIGINAL_FILES.md) for material with no delivered equivalent.
