# Capture — delivery and acceptance board

Sprint objective: isolate the legacy intelligence-contract flow as its own Capture ACA, with one
LangGraph behind HTTP/MCP and direct Diapason REST resolution. Preserve extraction behavior,
security, UI result contracts and Loki/Tempo compatibility. Updated 2026-09-07.

Legacy US-001–US-006 map to CAP-US001–CAP-US006 below. Keep the old ID as an alias on existing
tickets, not as a second story; use the CAP- IDs for cross-repository references.

## Tracking rules

Assign people to the accountable roles at planning. Estimates are indicative engineering days.
**Verified local** means implemented with named local evidence, not deployed or product accepted.
**Review** means implementation exists but acceptance evidence is incomplete. **External gate** needs
the named environment, fixtures or decision. **Ready** is future work. Do not mark a whole story Done
while an acceptance criterion is still an external gate.

Each accepted task needs commit/image SHA, dated command/scenario result, reviewer and evidence link.
Use task IDs in commits. No contracts, credentials or personal data in tickets. Pascal work lives in
../diapason-agent/SPRINT.md; reference that board instead of duplicating its status.

## Stories and acceptance criteria

| Story | User story | Acceptance criteria | Status |
|---|---|---|---|
| CAP-US001 | As a classic Diapason user I submit PDF + trade type and obtain the same prefilled view. | AC1 same endpoint/fields/headers/metadata/result; AC2 caller controls trade_type; AC3 approved prompt/catalog parity; AC4 golden PDFs open identical host views. | Review; host acceptance open |
| CAP-US002 | As a maintainer I test/observe Capture stages without duplicated extraction logic. | AC1 seven graph stages; AC2 shared runtime for HTTP/MCP; AC3 runtime-only credentials; AC4 no checkpointer or extraction redesign. | Verified local |
| CAP-US003 | As an operator I remove the internal MCP proxy without changing reference resolution. | AC1 no MCP client; AC2 REST form/XML/parser/retry parity with diapason-mcp-main; AC3 token/scope/trace forwarding; AC4 actual backend output parity. | Review; live backend gate |
| CAP-US004 | As Pascal I invoke Capture with a supplied PDF and explicit trade_type. | AC1 stateless /mcp capture tool; AC2 same JWT/tenant rules; AC3 encoded/decoded size bounds; AC4 real Pascal forwards identity and runs the same graph. | Review; Pascal E2E gate |
| CAP-US005 | As platform operator I deploy and promote Capture independently. | AC1 separate ACA/image/identity/config-reader scope; AC2 runtime-only secrets; AC3 immutable image promotion; AC4 image/plan/revision/probes verified. | External gate |
| CAP-US006 | As operator I correlate Capture in existing Loki/Tempo without contract content. | AC1 same OTLP env/headers; AC2 ingress/downstream W3C; AC3 node spans; AC4 sanitized live trace and correlated log. | Review; collector gate |

## Task ledger

Owners are accountable roles; assign actual people and target sprints before execution.

| ID | Story / AC | Deliverable and completion evidence | Owner | Days | Depends on | Status |
|---|---|---|---|---:|---|---|
| CAP-T001 | US001 AC1 | Contract inventory in docs/integration.md; compare old API schemas/UI open-trade handler. | API + QA | 0.5 | — | Review; host sign-off R003 |
| CAP-T002 | US001 AC3 | Compare all used catalog/prompt assets with legacy. Record allowed filename/line-ending transforms and explain every remaining diff. | Capture eng. | 0.5 | T001 | Review; attach content-diff report |
| CAP-T003 | US001 AC1–2 | Compatibility GET/POST, required PDF/trade_type, same public result. Run tests/test_app.py, test_runtime.py, test_extraction.py. | API eng. | 1 | T001/T002 | Verified local |
| CAP-T004 | US001 AC4 | Golden PDFs per supported type, expected XML/reference fields and UI result. Compare both implementations and obtain SME approval. | QA + treasury SME | 2 | T003/R001 | External gate: fixtures/backend/host |
| CAP-T005 | US002 AC1 | Typed StateGraph: validate, parse, select, extract, normalize, resolve, emit. Run tests/test_workflow.py. | Capture eng. | 1 | T002 | Verified local |
| CAP-T006 | US002 AC2 | Both front doors call CaptureRuntime.execute; inspect call paths and run app/runtime/workflow tests. | Capture eng. | 0.5 | T005 | Verified local |
| CAP-T007 | US002 AC3–4 | No credential state/checkpointer or added extraction repair loop; architecture/security review. | Capture + security | 0.5 | T005 | Verified local |
| CAP-T008 | US003 AC1–2 | Direct resolveReferences adapter from diapason-mcp-main; XML/form/retry checks in tests/test_diapason.py. | Integration eng. | 1 | T001 | Verified local |
| CAP-T009 | US003 AC3 | Per-request token/scope/W3C; inspect outgoing mock request and prove no MCP client imports. | Integration + security | 0.5 | T008 | Verified local |
| CAP-T010 | US003 AC4 | Actual approved dev resolveReferences responses match legacy for golden contracts. | QA + backend owner | 0.5 | T004/T009/R001 | External gate: backend access |
| CAP-T011 | US004 AC1 | FastMCP stateless mount/lifespan/tool schema and public result; app MCP tests. | API eng. | 1 | T006 | Verified local |
| CAP-T012 | US004 AC2–3 | Token/customer/header checks and base64 size/format negatives; app/runtime tests. | Security + API | 1 | T011 | Verified local |
| CAP-T013 | US004 AC4 | Pascal trusted Capture config forwards dynamic identity, other servers do not. Link PAS-T012 and test_mcp.py evidence. | Pascal eng. | 0.5 | T012/PAS-T010 | Review; live R004 remains |
| CAP-T014 | US005 AC1–2 | Non-root Docker, separate Terraform ACA/RBAC and runtime secrets. Static HCL/shell review, then image/plan evidence. | Platform | 1 | T003/T011 | Review; R001 |
| CAP-T015 | US005 AC3 | Dev SHA build; test/prod same-image promotion through shared deployment helpers. Archive CI/image digest. | Platform | 1 | T014 | External gate: organization CI |
| CAP-T016 | US005 AC4 | Verify startup/readiness/liveness/scaling in shared module plan and actual ACA revision, not assumption. | Platform + SRE | 0.5 | T015 | External gate: rendered spec |
| CAP-T017 | US006 AC1–3 | OTLP headers/endpoints/request IDs/node spans. Dedicated exporter/trace assertions and configuration review. | Observability eng. | 1 | T005/T009 | Review; instrumentation exists |
| CAP-T018 | US006 AC4 | One live Pascal→Capture→Diapason trace and Loki log; inspect all fields for PDF/XML/secret leakage. | SRE + security | 0.5 | T017/R001 | External gate: collectors |
| CAP-T019 | All local ACs | Clean lint/tests/wheel/dependency/shell/HCL checks; attach reproducible commands and release SHA. | QA + platform | 0.5 | T003–T018 as applicable | Review; 20 tests rerun, release report pending |
| CAP-T020 | Cross-project | Keep docs/board consistent and assign deferred work; review acceptance evidence, not checkboxes alone. | Tech lead | 0.5 | T001–T019 | Review |

## Release gates

| ID | Required scenario/evidence | Owner | Exact dependency / status |
|---|---|---|---|
| CAP-R001 | Capture image build, Terraform init/validate/plan, approved dev deploy, health/ready/auth smoke. Record image SHA and revision. | Platform + QA | Open: Capture image evidence; external shared module and organization credentials (Pascal's local image build does not close this) |
| CAP-R002 | Golden matrix: all trade types, missing inputs, malformed/oversize/scanned PDF, resolver failure; compare legacy outputs. | QA + SME | External: approved fixtures + dev backend |
| CAP-R003 | Classic UI and Pascal composer open the same prefilled host view via dia-agent-open-trade, same user scope. | Product + UI QA | External: Diapason host; PAS-R003 depends on this |
| CAP-R004 | Real Pascal tool invocation with PDF bytes + explicit type and same identity; missing inputs not invented; cross-tenant denial. | Pascal + QA + security | External: PAS-T012 and approved file flow; PAS-F007 for large files |
| CAP-R005 | Inspect live Loki/Tempo, measure latency/memory and revision drain against agreed thresholds. | SRE | External: R001 + collector access; no SLO claimed yet |
| CAP-R006 | Accept or mitigate revocation, retention and debug limitations before broad rollout. | Product + security | External: explicit risk decision |

## Ready backlog outside extraction parity

| ID | Work | Owner / gate |
|---|---|---|
| CAP-F001 | Shared revocation and retention/redaction, including historic blobs/debug responses | Security/privacy; PAS-F001/F003 |
| CAP-F002 | Opaque authorized PDF handles instead of base64 in model context | Pascal/Capture/UI; PAS-F007 |
| CAP-F003 | Durable jobs if measured latency exceeds ingress budget | Platform/Capture; approved API/UX contract first |
| CAP-F004 | XML schema/repair, OCR, extraction quality/model changes | Capture/SME; separate golden-PDF evaluation |

## Latest local evidence

2026-09-07: .venv/Scripts/python.exe -m pytest from this folder: **20 passed**, one dependency
deprecation warning. Earlier work included wheel/dependency and shell/HCL checks; rerun those against
the release commit. No ACA deployment, golden-contract E2E, host acceptance or live Loki/Tempo
validation is asserted here. Pascal's local forwarding/proxy tests do not close these external gates.
