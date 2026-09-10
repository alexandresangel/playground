# Capture handoff

This directory is an independent source/container context. From its root, run `python -m pip install -r requirements-dev.txt`, `python -B -m pytest -q`, then `uvicorn capture.asgi:app --host 0.0.0.0 --port 8000` with the existing company configuration. `docker build -t <image-name> .` uses this directory alone. No image deployment or live environment validation is included.

Capture serves the existing multipart extraction and auth contracts. Health endpoints return build health; refresh loads only the Capture catalog. It contains no Pascal frontend, session CRUD, chat loop or system-prompt startup. Extraction still writes original session artifacts and uses the unchanged localized messages. The classic UI belongs to its existing host.

The original catalog, prompt and XML assets in `config/` retain their bytes. Runtime reads the existing Blob keys, including the external `skills/intelligence-contract/` prefix. Local assets are not a fallback prompt source.

Company implementations under `src/capture/company/` are byte-identical. Setuptools retains public imports such as `dia_jwt` and `mcp_context`. The service root remains the location for local config, VERSION and keystore data. Use separate environments for Capture and Pascal. Keep JWT issuer/roles/revocation, tenant/user/instance binding, identity/credential headers, MCP scoping/transport and Blob/session schemas unchanged.

## External integration still needed

| Entry path | Delivered | Company-owned next step |
| --- | --- | --- |
| Classic Diapason UI | Existing extraction HTTP/security/result contract | Route the host/proxy to Capture with current headers and identity/session scope. |
| Pascal explicit slash/@ action | Existing token/upload/pre-filled UI behavior; local compatibility execution retained in Pascal | Connect the same contract to Capture and preserve PDF selection, explicit trade type, active session and host prefill. No new slash alias is invented. |
| Pascal automatic tool invocation | Dynamic per-user MCP discovery/call loop | Expose Capture through the existing company MCP server and define authorized PDF/trade-type inputs. No such exposure/upload-reference contract is supplied here. |

No direct REST replacement, new MCP SDK or new global tool catalog is introduced. Cross-service entry paths are not claimed validated.

The sole original AzureOpenAI client remains in `src/capture/runtime.py::build_azure_client`. Actual deployment details are missing. Verify the same deployment's Azure v1 chat/tool/stream/temperature support before replacing the sole constructor with OpenAI configured for the resource's `/openai/v1/` endpoint. No fallback client/mode or replacement model is provided. See [Microsoft v1 guidance](https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle).

Keep existing OTEL settings and Loki/Tempo destinations. New AI spans carry duration/outcome/tokens with existing correlation; no prompt/PDF/XML/graph state/tool payload or exception text is exported. Automatic LangSmith tracing is disabled per run. Runtime container checks follow [Microsoft container guidance](https://learn.microsoft.com/en-us/azure/container-apps/containers) and existing company conventions.

Known original behavior is characterized, not silently fixed: the catalog version name collision causes subsequent refresh to fail; Pascal's seven original source-locale assertions remain strict expected failures. Optional original-source differential cases skip when copied outside this migration workspace. Standalone tests still cover workflow and interface behavior. Live model/MCP/Blob/host/ACA acceptance remains with the integration owners.
