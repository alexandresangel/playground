# Capture test rework

Scope: tests, test configuration, and documentation in `ai-capture` only.
Application code, dependencies, deployment configuration, and sibling projects
are outside this change. The starting suite passed: **59 tests** on Python 3.12.9.
This checkout has no `.git` directory; a before/after SHA-256 inventory is used
to verify the edit scope.

## Result

The suite now has **216 passing cases**, organized by graph step, API,
configuration, integrations, and observability. The original useful regression
checks were carried forward; extra cases exercise boundary conditions, failures,
concurrency, MCP response formats, and the complete offline request path.

All collected tests use pytest functions and fixtures. Catalog class-level state
mutation and per-test `asyncio.run` were replaced with isolated fixtures and
`pytest.mark.asyncio`. Standard-library `Mock`/`AsyncMock` are retained for call
assertions and async doubles because pytest has no built-in equivalent. No new
project dependency or lockfile change was needed.

The detailed behavior map and commands are in [tests/README.md](tests/README.md).

## File inventory

Paths are relative to `ai-capture`. Every destination below was reviewed and
formatted. A move means the original path was removed; useful assertions were
retained and extended at the destination rather than maintaining duplicate tests.

### Edited in place

| File | Edit |
| --- | --- |
| `README.md` | Added links to the test guide and this inventory in the CI section. |
| `tests/conftest.py` | Kept real JWT/ASGI service setup; added fresh per-test catalog/cache, bundled PDF, temporary config, and workflow fixtures; reject accidental HTTPX network calls and disable automatic LangSmith tracing. |

### Moved and reworked

| Original path | New path | Change |
| --- | --- | --- |
| `tests/test_api.py` | `tests/api/test_extraction.py` | Canonical route is the default; keep deprecated alias checks; extend form/auth/error/correlation/client-cleanup assertions. Metadata/surface checks moved to `test_metadata.py`. |
| `tests/test_capture_catalog.py` | `tests/configuration/test_catalog.py` | Replace `unittest.TestCase` and `setUpClass` mutation with parameterized pytest cases; cover all prompt families and supported catalog formats. Settings precedence moved to `test_capture_settings.py`. |
| `tests/test_local_config.py` | `tests/configuration/test_prompts.py` | Preserve file/path validation; add deterministic TTL, refresh/version, and failed-refresh checks. Shared config fixture moved to root conftest; refresh endpoint test moved to `test_metadata.py`. |
| `tests/test_runtime.py` | `tests/configuration/test_runtime.py` | Preserve startup and Azure constructor checks; add incomplete/trimmed config cases; restore build-info/logging globals and avoid replacing pytest logging handlers. |
| `tests/test_extract_trade_type.py` | `tests/workflow/test_trade_type.py` | Preserve replacement/insertion cases; add namespaces, case variation, identifier cleanup, and invalid input. Replace obsolete IC terminology. |
| `tests/test_xml_fields.py` | `tests/workflow/test_field_count.py` | Preserve populated-element case; add root/container exclusion, attribute precedence, zero/false values, namespace, empty and malformed XML cases. |
| `tests/test_mcp_cluster.py` | `tests/integrations/test_mcp_context.py` | Focus on Capture's default Diapason server, real encrypted caller credentials, protocol precedence, and config failures. Remove unused tool-routing/extra-server helper checks and manual runner. |
| `tests/test_observability.py` | `tests/observability/test_spans.py` | Preserve redaction, incoming trace parent, identity and tracing checks; add real workflow/completion span hierarchy, usage/outcomes, worker tracing suppression, and privacy checks. Exporter cleanup is a pytest fixture. |
| `tests/test_telemetry_helpers.py` | `tests/observability/test_usage.py` | Retain completion-usage normalization; extend supported usage shapes and missing values. Remove unused chat preview/cost/usage-merging/tool/skill CSV checks and manual runner. |

### Added

| File | Purpose and origin |
| --- | --- |
| `TEST_CHANGES.md` | This complete edit inventory, verification record, and scope explanation. |
| `tests/README.md` | Workflow diagram, behavior matrix, fixture boundaries, commands, and known limits. |
| `tests/api/test_metadata.py` | Metadata, health, absent chat routes, and refresh-role/cache tests consolidated from the old API/local-config modules. |
| `tests/configuration/test_capture_settings.py` | Settings compatibility cases split out of the old catalog module and extended. |
| `tests/workflow/test_graph.py` | Original real PDF-to-XML contract plus explicit node order and concurrent-state independence. |
| `tests/workflow/test_step_validate.py` | Original invalid-PDF cases plus size boundary, trade-type rejection and routing fallback precedence. |
| `tests/workflow/test_step_extract.py` | Original invalid-model-output cases plus real synthetic PDF cases, extraction failures, full-text/preview distinction, and XML response normalization. |
| `tests/workflow/test_step_resolve.py` | Resolver call/trace contract for different product families and exception propagation. |
| `tests/workflow/test_step_result.py` | Original resolver-failure cases plus complete output shape, resolved-field count, warnings/messages, debug and timing behavior. |
| `tests/integrations/conftest.py` | Shared HTTPX MockTransport installer for real MCP protocol tests. |
| `tests/integrations/test_mcp_rpc.py` | Exercise real MCP JSON-RPC serialization/parsing and transport/tool errors through a local HTTP transport. |
| `tests/integrations/test_capture_service.py` | Exercise real multipart API/JWT/Fernet/graph/PDF/XML/MCP protocol together, including failure statuses and Azure cleanup. |

### Removed or split

| File/check | Reason |
| --- | --- |
| `tests/test_workflow.py` | Split into `tests/workflow/test_graph.py` and the four `test_step_*.py` modules. Prompt refresh coverage consolidated in `tests/configuration/test_prompts.py`; fixture moved to conftest. No parallel legacy workflow suite remains. |
| `tests/test_i18n.py` | Tested old chat composer/sidebar/disclaimer translations. No Capture application path imports `i18n`; these assertions did not protect Capture's extraction workflow. Application locale files were left untouched. |
| Old MCP tool-name qualification and extra `docs` server tests | Capture calls `resolveReferences` directly on `cluster.diapason`; chat tool routing is outside this service's workflow. Default-server header/encryption coverage was retained and strengthened. |
| Chat telemetry preview, price, merge and CSV assertions | Capture consumes `usage_from_completion` and its own content-free spans, not these chat-agent helpers. Those source functions were not changed. |

The nine moved modules' old paths are also removed, as shown in the move table.
The inventory comparison reports **21 added paths, 11 removed paths, and 2 edited
paths**; the added/removed totals include moves and splits, not just net-new work.

### Preserved

No edits to `src/`, bundled catalog/prompts, the PDF fixture, `pyproject.toml`,
`uv.lock`, `.github/workflows/`, deployment files, local secrets, or sibling repos.
`tests/container_bootstrap.py` remains unchanged because the deployment handoff
still references it for manual container verification; it is not a collected test.

## Verification

Local environment: Windows, Python 3.12.9, pytest 9.1.1, pytest-asyncio 1.4.0,
and the existing locked application dependencies. The available uv 0.9.0
successfully ran the locked sync; CI's separately pinned uv was not changed.
CI itself and Docker/deployment were not executed from this checkout.

| Check | Result |
| --- | --- |
| Original suite, before edits | 59 passed. |
| Expanded suite | 216 passed; no skips or expected failures. |
| Branch-coverage run | 216 passed; report below. |
| Shuffled collection, seed `20260917` | 216 passed, checking independence from catalog/cache mutation and test order. |
| Ruff syntax/import/error checks (`E4,E7,E9,F`) | Passed. |
| Ruff formatting check, 100-column target | Passed for the reworked suite. |
| Before/after SHA-256 inventory | Changes limited to the paths listed above. Original application/config/dependency files match their baseline hashes. |

The same third-party Starlette/AnyIO deprecation warning appears in both the
baseline and final suite. It was not hidden with warning filters.

Commands used for the main checks (after activating `.venv`; optionally install
the inspection tools with `uv pip install coverage ruff`):

```bash
python -m pytest -q --basetemp=.pytest-tmp
python -m coverage run --branch --source=capture.workflow,capture.api.extraction,capture.observability,mcp_rpc -m pytest -q --basetemp=.pytest-tmp
python -m coverage report -m
ruff check tests --select E4,E7,E9,F --exclude tests/container_bootstrap.py
ruff format --check tests --line-length 100 --exclude tests/container_bootstrap.py
```

For the order check, pytest was invoked with a temporary in-memory collection
plugin whose `pytest_collection_modifyitems` uses
`random.Random(20260917).shuffle(items)`. No plugin was added to project settings.

Coverage and Ruff were installed only in the local verification environment;
they are optional inspection tools, not new required dev dependencies. Normal
CI still needs only the existing locked dev group. No coverage threshold was
added merely to enforce a number.

### Measured coverage

`Cover` is coverage.py's combined statement/branch figure with `--branch`.
This measurement targets the extraction path, not the entire inherited common
library. Counts show what the percentages include.

| Source | Statements executed | Branch destinations measured | Cover |
| --- | ---: | ---: | ---: |
| `capture/api/extraction.py` | 53/53 | 6 | 100% |
| `capture/workflow/graph.py` | 86/86 | 14 | 99% |
| `capture/workflow/extract_xml.py` | 71/72 | 22 | 99% |
| `capture/workflow/xml_fields.py` | 23/23 | 12 | 100% |
| `capture/workflow/prompts.py` | 178/181 | 50 | 98% |
| `capture/common/mcp_rpc.py` | 104/107 | 40 | 94% |
| `capture/observability/ai.py` | 32/32 | 10 | 93% |
| `capture/observability/http.py` | 32/35 | 20 | 85% |
| **Targeted total** | **579/589** | **174** | **96%** |

Every executable statement in the graph and upload handler is exercised. The
uncovered extraction statement is the unused `extract_trade_xml` convenience
wrapper; the graph uses `extract_trade_xml_detail`. Remaining gaps include
unused config/helper branches and defensive telemetry/transport fallbacks.
Coverage does not imply live model correctness or exhaustive input validation.

## Existing behavior documented, not changed

The corrupt-PDF test confirms parsing stops before external calls. Some `pypdf`
exceptions are outside the API's `ValueError`/`RuntimeError` mapping and may
surface as HTTP 500; this remains an application follow-up. Result shaping also
trusts nonempty resolver XML rather than validating a business schema. These
limits, debug-output content, and default-prompt fallback semantics are explained
in the test guide rather than silently changing working application behavior.

## Local verification artifacts

Created a local ignored `.venv/` to run the locked dependencies, plus optional
coverage/Ruff tools. Pytest bytecode/cache and `.coverage` are ignored generated
artifacts, not source edits. The coverage JSON report is under `.venv/`.
Repository-local uv cache, temporary test keys/configs/PDF data, Ruff cache, and
generated editable-build `*.egg-info` were moved under
`.venv/verification-artifacts/` after verification, keeping them out of the source
tree. Automatic cleanup review blocked a recursive-delete command, so these
generated artifacts were retained in the ignored environment instead. No
application catalog, prompt, or existing PDF fixture was rewritten.
