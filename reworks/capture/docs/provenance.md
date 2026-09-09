# Capture code provenance — 2026-09-08

Reference is the **original** repository, not the first rework. Original paths below are relative to
`diapason-agent-main`; sibling MCP paths refer to `../diapason-mcp-main`. Reworks are pending.
Nothing was edited in either original application. Run the read-only `reworks/audit_provenance.py`
from the shared workspace to repeat selected AST/asset comparisons.

Classification: **retained** = same bytes or explicitly identified unchanged definitions;
**refactored** = derived behavior with new structure/async/dependency boundaries;
**added** = new implementation. An AST match ignores formatting, not semantic differences.
Tests demonstrate particular contracts, not universal real-model equivalence.

## Production Python inventory

Paths in this table are under `src/capture` unless stated otherwise.

| Current file/section | Classification / original reference | What changed or stayed |
|---|---|---|
| workflow/extraction.py: validate_pdf_bytes, pdf_to_text, _local_tag, extract_xml_from_llm | Retained definitions from skills/intelligence_contract/extract_xml.py | AST-identical; same magic/size/text and XML fence handling |
| workflow/extraction.py: apply_trade_type_shortname | Refactored from the same helper | Local names/docstring changed; same ElementTree traversal/insertion/caller override |
| workflow/extraction.py: count_extracted_fields | Refactored from skills/intelligence_contract/xml_fields.py | Collapses equivalent shortname/name/text branches; no extra counted fields |
| adapters/model.py | Refactored from extract_trade_xml_detail in extract_xml.py | Exact system/user message contract and temperature retained; async local client, usage/lifetime added |
| adapters/catalog.py | Refactored from ic_prompt_loader.py | Instance-owned lock/cache/catalog, injected config, explicit Blob/filesystem backend; same trade-type/prompt mapping and defaults |
| workflow/nodes.py | Refactored from extraction helpers and skills/intelligence_contract/run.py | Stages split into functions; thread-offloaded parsing, internal timings/steps, public debug conditional; no session artifacts |
| workflow/graph.py | Added | Explicit seven-stage LangGraph, no checkpoint, ambient tracing disabled, business failure span status |
| workflow/state.py | Added | Typed state separated from runtime context; no credentials in state |
| workflow/ports.py | Added | Minimal model/resolver protocols, no framework-specific business coupling |
| workflow/service.py | Added orchestration boundary around original behavior | Shared execution for HTTP/MCP, per-request direct resolver, total deadline, PDF base64 bound, owned model close |
| api/http.py | Refactored from original app.py Capture handlers | Same GET/POST path, multipart/result/session-header contract; calls runtime, no chat persistence; safe unexpected-error 502 |
| api/mcp.py | Added server adapter | FastMCP tool validates same JWT/identity then calls runtime; optional/lazy, no client/proxy to backend MCP |
| auth.py | Refactored from dia_jwt/auth.py, dia_jwt/fastapi.py and auth_setup.py | Validation-only subset; same issuer/RS256/roles/customer/revocation policy, configured downstream host controls; no mint/revoke administration copied |
| compatibility.py | Added named boundary for retained external strings | Existing HTTP/blob prefix/header/JWT/config aliases and tool_trace display serializer; graph uses neutral steps |
| config.py | Refactored from settings.py/ic_prompt_loader configuration | CAPTURE_CONFIG preferred, CHAT_CONFIG fallback, explicit settings helpers |
| build_info.py | Added small Capture build identity | APP_VERSION/APP_REVISION from immutable image environment; replaces first rework's mutable build-info file |
| main.py | Added composition root replacing monolithic/import-time wiring | Factory, resource lifespan, ready/health, guards, optional MCP mount |
| observability/events.py | Added | Safe per-node events over local operation spans; no content/exception-body tracing |
| Package __init__.py files | Added package markers/version | No business behavior or old-module re-export shims |

## Intentionally duplicated local modules

These files live under `src/capture`; Pascal has byte-identical copies at matching package-relative
paths. They are ordinary application source, not generated or installed from a common package.
See [intentional duplication](reuse.md) for maintenance expectations.

| Module | Provenance |
|---|---|
| adapters/azure_openai.py | Added common settings/factory; v1 AsyncOpenAI default, explicit dated Azure branch |
| adapters/blob.py | Refactored original blob_client.py; same credential selection, safer errors/read-service cleanup |
| adapters/diapason.py | Refactored sibling diapason_api.py and resolver HTTP path; no MCP import |
| observability/telemetry.py | Refactored original telemetry.py conventions; safe spans, optional routing and metrics |
| api/guards.py | Added ASGI request/response boundary guard |

The resolver retains POST /api/v2/importData/resolveReferences, importService/scope/data form fields,
list wrapping, bearer/scoped identity, non-200 retry once, 120-second request timeout and BasicResponse/
CDATA behavior. It omits unrelated entity/pivot/import tools. Failed multiline warnings retain the
original combined message followed by individual lines; a source comparison caught and corrected
that omission in the first rework. Unexpected transport/SDK bodies are not returned as public errors.

## Assets, tests and deployment

The catalog and seven prompt files under `config` are now **byte-identical** to the originals,
verified against `config/source-manifest.json`. The first rework had added trailing newlines;
this refinement mechanically restored original bytes. Original example trade.xml, config README and
upload.sh are not runtime assets and were not ported; deployment uses its own reviewed config script.

All `tests/*.py`, `scripts/container_check.py`, local exporter tests/scripts and dependency locks
are added validation infrastructure. Some extraction/resolver expectations are derived from the
original tests; runtime code does not import those original files. Docker/CI and deploy/Terraform
artifacts are refactored from the original organization's ACA workflow; independent service naming,
locked/non-root builds and explicit gates are added. Private shared helpers are not vendored.

The original requirements were not a deployment lock, so an exact original production SDK/parser
version is not known from source alone. Capture now records tested dependency versions in uv.lock
(including pypdf 6.18.0 and MCP 1.30.0). Real original/candidate comparisons must record actual runtime
versions; source parity alone does not prove model/parser upgrade parity.

## Removed from the pending reworks

Flat app/asgi/catalog/llm/workflow/runtime/security/diapason/blob/telemetry modules were replaced by the
packages above, without dead import shims. The graph's fake MCP trace metadata and private session
artifact output were removed; public display aliases are produced only at the boundary. There is no
feature runner/registry called a skill. The original source remains available unchanged.

2026-09-09: removed the common package, canonical source/sync script and parity manifests. Their five
implementation files now live directly inside each app. Consolidated Capture's one-file domain,
application, security and compatibility folders; extraction/service/graph now form one `workflow`
folder. This follow-up changes paths/imports/packaging only, not capture behavior.

## What is deliberately not redesigned

No OCR, alternative extraction prompt/model, structured-output migration, XML repair, entity-matching
fallback, import commit or durable job/checkpoint was added. Debug output remains a sensitive existing
contract. Corporate JWT/Blob policy and actual frontend/backend routing still need release acceptance.
See the sprint board and verification report; this provenance is not deployment approval.
