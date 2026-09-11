# Pascal handoff

Pascal is an independent src package and Docker build context. The original company modules under `src/pascal/commun/` were not edited in this continuation, including every `dia_jwt` file. Existing copies differ from the original only in line endings/final newlines. Frontend/static sources, system prompt, configuration example, Terraform infrastructure and provider lock are copied byte-for-byte from the original.

The agent uses the existing LangGraph model/tool loop for both JSON and live SSE. Tests compare its output, model arguments and message mutations with the original loop. Model deployment/version/temperature, tool-round behavior, caller-specific MCP discovery and original session contracts remain.

The previously missing `api/capture.py` is now a relay to Capture's ACA. There is no local extraction code, Capture prompt cache, `compat` package or PDF dependency in Pascal. The existing metadata, PDF upload and refresh routes preserve the frontend contract. Set `CAPTURE_URL`; the optional `CAPTURE_TIMEOUT_S` is 600 seconds by default. Forwarded uploads are not retried or persisted by Pascal.

Packaging maps the original top-level company imports to the existing source locations, without modifying those files. `application.py` exposes a side-effect-free app factory; `asgi.py` owns startup from the service root. Use separate Python environments for Pascal and Capture. No source or Docker dependency on the sibling project is required.

HTTP access logging no longer has `_QUIET_ACCESS_PATHS` or `_AI_HTTP_PATHS`. All HTTP error logs omit payload/exception details while returning the original error body to the caller. Quiet successful endpoints declare `@quiet_access` beside their routes; router prefixes are tested. Graph spans retain the existing provider and disable automatic LangSmith tracing per run. Incoming trace context is propagated across the relay.

Offline verification covers original schemas/routes, chat/history/usage, real JWT/roles/revocation and user/customer scope, dynamic tools, exact PDF forwarding, remote errors/timeouts, no duplicate persistence, startup, telemetry and package imports. Linux container acceptance also exercises the actual ASGI entry point, direct Capture and Pascal relay with real HTTP and shared test Blob records. External model, resolver and Blob services are doubles in that check.

Seven source-filter expectations remain strict expected failures, reproduced against the original code. Other inherited behavior (sample charts, broad streaming retry, local revocation-file lifecycle) remains unchanged. No commits, image pushes or cloud deployments were made.

The remaining company-owned work is concrete: deploy one Capture ACA with the same trust/storage/MCP/model configuration, set Pascal's relay URL, preserve the existing state/host interfaces, and run real environment acceptance. See [deployment details](DEPLOYMENT.md), [commit-sized tasks](SPRINT.md) and [complete Python inventory](PYTHON_INVENTORY.md).
