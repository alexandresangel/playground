# Pascal Python inventory

Relative to `diapason-agent-main`, including tests and scripts. `untouched` means identical text after normalizing line endings and the final newline; it does not claim every existing copy has identical bytes. No company module or `dia_jwt` file was edited during this continuation.

**18 new**, **20 untouched**, **24 reworked**.

Regenerate: `python scripts/update_inventory.py --original ../diapason-agent-main`.

| Python file | Status | Original source | Comparison |
| --- | --- | --- | --- |
| `observability/generate_dashboards.py` | untouched | `observability/generate_dashboards.py` | Byte-identical. |
| `scripts/smoke_api.py` | untouched | `test/test_agent_smoke.py` | Byte-identical. |
| `scripts/update_inventory.py` | new | `-` | No original Python file. |
| `src/pascal/__init__.py` | new | `-` | No original Python file. |
| `src/pascal/agent/__init__.py` | new | `-` | No original Python file. |
| `src/pascal/agent/charts.py` | reworked | `app.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `src/pascal/agent/context.py` | reworked | `app.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `src/pascal/agent/discovery.py` | reworked | `app.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `src/pascal/agent/graph.py` | reworked | `app.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `src/pascal/agent/mcp.py` | reworked | `app.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `src/pascal/agent/routing.py` | reworked | `app.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `src/pascal/agent/service.py` | reworked | `app.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `src/pascal/api/__init__.py` | new | `-` | No original Python file. |
| `src/pascal/api/auth.py` | reworked | `app.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `src/pascal/api/capture.py` | reworked | `app.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `src/pascal/api/chat.py` | reworked | `app.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `src/pascal/api/health.py` | reworked | `app.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `src/pascal/api/middleware.py` | reworked | `app.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `src/pascal/api/schemas.py` | reworked | `app.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `src/pascal/api/sessions.py` | reworked | `app.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `src/pascal/application.py` | reworked | `app.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `src/pascal/asgi.py` | new | `-` | No original Python file. |
| `src/pascal/commun/auth_setup.py` | untouched | `auth_setup.py` | Same text; existing line-ending/final-newline differences only. |
| `src/pascal/commun/blob_client.py` | untouched | `blob_client.py` | Same text; existing line-ending/final-newline differences only. |
| `src/pascal/commun/build_info.py` | untouched | `build_info.py` | Same text; existing line-ending/final-newline differences only. |
| `src/pascal/commun/dia_jwt/__init__.py` | untouched | `dia_jwt/__init__.py` | Same text; existing line-ending/final-newline differences only. |
| `src/pascal/commun/dia_jwt/__main__.py` | untouched | `dia_jwt/__main__.py` | Same text; existing line-ending/final-newline differences only. |
| `src/pascal/commun/dia_jwt/auth.py` | untouched | `dia_jwt/auth.py` | Same text; existing line-ending/final-newline differences only. |
| `src/pascal/commun/dia_jwt/cli.py` | untouched | `dia_jwt/cli.py` | Same text; existing line-ending/final-newline differences only. |
| `src/pascal/commun/dia_jwt/fastapi.py` | untouched | `dia_jwt/fastapi.py` | Same text; existing line-ending/final-newline differences only. |
| `src/pascal/commun/i18n.py` | untouched | `i18n.py` | Same text; existing line-ending/final-newline differences only. |
| `src/pascal/commun/mcp_context.py` | untouched | `mcp_context.py` | Same text; existing line-ending/final-newline differences only. |
| `src/pascal/commun/mcp_rpc.py` | untouched | `mcp_rpc.py` | Same text; existing line-ending/final-newline differences only. |
| `src/pascal/commun/prompt_loader.py` | untouched | `prompt_loader.py` | Same text; existing line-ending/final-newline differences only. |
| `src/pascal/commun/session_store.py` | untouched | `session_store.py` | Same text; existing line-ending/final-newline differences only. |
| `src/pascal/commun/settings.py` | untouched | `settings.py` | Same text; existing line-ending/final-newline differences only. |
| `src/pascal/commun/source_extract.py` | untouched | `source_extract.py` | Same text; existing line-ending/final-newline differences only. |
| `src/pascal/commun/telemetry.py` | untouched | `telemetry.py` | Same text; existing line-ending/final-newline differences only. |
| `src/pascal/commun/tool_audience.py` | untouched | `tool_audience.py` | Same text; existing line-ending/final-newline differences only. |
| `src/pascal/integrations/__init__.py` | new | `-` | No original Python file. |
| `src/pascal/integrations/capture.py` | new | `-` | No original Python file. |
| `src/pascal/observability/__init__.py` | new | `-` | No original Python file. |
| `src/pascal/observability/ai.py` | new | `-` | No original Python file. |
| `src/pascal/observability/http.py` | reworked | `app.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `src/pascal/observability/routing.py` | new | `-` | No original Python file. |
| `src/pascal/runtime.py` | reworked | `app.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `tests/conftest.py` | new | `-` | No original Python file. |
| `tests/container_bootstrap.py` | new | `-` | No original Python file. |
| `tests/test_api.py` | new | `-` | No original Python file. |
| `tests/test_assistant_identity.py` | reworked | `test/test_assistant_identity.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `tests/test_capture_proxy.py` | new | `-` | No original Python file. |
| `tests/test_chat_graph.py` | new | `-` | No original Python file. |
| `tests/test_i18n.py` | untouched | `test/test_i18n.py` | Same text; existing line-ending/final-newline differences only. |
| `tests/test_mcp_cluster.py` | reworked | `test/test_mcp_cluster.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `tests/test_observability.py` | new | `-` | No original Python file. |
| `tests/test_original_contracts.py` | new | `-` | No original Python file. |
| `tests/test_runtime.py` | new | `-` | No original Python file. |
| `tests/test_session_summary.py` | reworked | `test/test_session_summary.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `tests/test_source_extract.py` | reworked | `test/test_source_extract.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `tests/test_telemetry_helpers.py` | reworked | `test/test_telemetry_helpers.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `tests/test_tool_audience.py` | reworked | `test/test_tool_audience.py` | Relocated/split implementation, orchestration, or test adaptation. |
| `tests/test_tool_route.py` | reworked | `test/test_tool_route.py` | Relocated/split implementation, orchestration, or test adaptation. |
