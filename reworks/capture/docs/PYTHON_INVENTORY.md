# Capture Python inventory

Relative to `diapason-agent-main`, including tests and scripts. `untouched` means identical text after normalizing line endings and the final newline; it does not claim every existing copy has identical bytes. No company module or `dia_jwt` file was edited during this continuation.

**15 new**, **15 untouched**, **19 reworked**.

Regenerate: `python scripts/update_inventory.py --original ../diapason-agent-main`.

| Python file | Status | Original source | Comparison |
| --- | --- | --- | --- |
| `scripts/smoke_api.py` | reworked | `test/test_agent_smoke.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `scripts/update_inventory.py` | new | `-` | No original Python file. |
| `src/capture/__init__.py` | new | `-` | No original Python file. |
| `src/capture/api/__init__.py` | new | `-` | No original Python file. |
| `src/capture/api/auth.py` | reworked | `app.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `src/capture/api/extraction.py` | reworked | `app.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `src/capture/api/health.py` | reworked | `app.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `src/capture/api/middleware.py` | reworked | `app.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `src/capture/api/schemas.py` | reworked | `app.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `src/capture/application.py` | reworked | `app.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `src/capture/asgi.py` | new | `-` | No original Python file. |
| `src/capture/common/auth_setup.py` | untouched | `auth_setup.py` | Same text; existing line-ending/final-newline differences only. |
| `src/capture/common/blob_client.py` | untouched | `blob_client.py` | Same text; existing line-ending/final-newline differences only. |
| `src/capture/common/build_info.py` | untouched | `build_info.py` | Same text; existing line-ending/final-newline differences only. |
| `src/capture/common/dia_jwt/__init__.py` | untouched | `dia_jwt/__init__.py` | Same text; existing line-ending/final-newline differences only. |
| `src/capture/common/dia_jwt/__main__.py` | untouched | `dia_jwt/__main__.py` | Same text; existing line-ending/final-newline differences only. |
| `src/capture/common/dia_jwt/auth.py` | untouched | `dia_jwt/auth.py` | Same text; existing line-ending/final-newline differences only. |
| `src/capture/common/dia_jwt/cli.py` | untouched | `dia_jwt/cli.py` | Same text; existing line-ending/final-newline differences only. |
| `src/capture/common/dia_jwt/fastapi.py` | untouched | `dia_jwt/fastapi.py` | Same text; existing line-ending/final-newline differences only. |
| `src/capture/common/i18n.py` | untouched | `i18n.py` | Same text; existing line-ending/final-newline differences only. |
| `src/capture/common/mcp_context.py` | untouched | `mcp_context.py` | Same text; existing line-ending/final-newline differences only. |
| `src/capture/common/mcp_rpc.py` | untouched | `mcp_rpc.py` | Same text; existing line-ending/final-newline differences only. |
| `src/capture/common/session_store.py` | untouched | `session_store.py` | Same text; existing line-ending/final-newline differences only. |
| `src/capture/common/settings.py` | untouched | `settings.py` | Same text; existing line-ending/final-newline differences only. |
| `src/capture/common/telemetry.py` | untouched | `telemetry.py` | Same text; existing line-ending/final-newline differences only. |
| `src/capture/observability/__init__.py` | new | `-` | No original Python file. |
| `src/capture/observability/ai.py` | new | `-` | No original Python file. |
| `src/capture/observability/http.py` | reworked | `app.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `src/capture/observability/routing.py` | new | `-` | No original Python file. |
| `src/capture/runtime.py` | reworked | `app.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `src/capture/workflow/__init__.py` | new | `-` | No original Python file. |
| `src/capture/workflow/extract_xml.py` | reworked | `skills/intelligence_contract/extract_xml.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `src/capture/workflow/graph.py` | reworked | `skills/intelligence_contract/run.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `src/capture/workflow/prompts.py` | reworked | `ic_prompt_loader.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `src/capture/workflow/xml_fields.py` | reworked | `skills/intelligence_contract/xml_fields.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `tests/conftest.py` | new | `-` | No original Python file. |
| `tests/container_bootstrap.py` | new | `-` | No original Python file. |
| `tests/test_api.py` | new | `-` | No original Python file. |
| `tests/test_extract_trade_type.py` | reworked | `test/test_extract_trade_type.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `tests/test_i18n.py` | untouched | `test/test_i18n.py` | Same text; existing line-ending/final-newline differences only. |
| `tests/test_ic_catalog.py` | reworked | `test/test_ic_catalog.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `tests/test_mcp_cluster.py` | reworked | `test/test_mcp_cluster.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `tests/test_observability.py` | new | `-` | No original Python file. |
| `tests/test_original_contracts.py` | new | `-` | No original Python file. |
| `tests/test_runtime.py` | new | `-` | No original Python file. |
| `tests/test_session_summary.py` | reworked | `test/test_session_summary.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `tests/test_telemetry_helpers.py` | reworked | `test/test_telemetry_helpers.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `tests/test_workflow.py` | new | `-` | No original Python file. |
| `tests/test_xml_fields.py` | reworked | `test/test_xml_fields.py` | Relocated/split implementation, orchestration, or test adaptation. |
