# Pascal — sprint board

Updated 2026-09-09. The original project is still current; this rework is pending migration.
Three stories separate Python migration, deployment/integration and later business validation.
Tasks marked **local implementation verified** are not a claim of deployment or business acceptance.
Named people, dates and estimates are deliberately left for team planning.

Layout follow-up (2026-09-09): common code is duplicated inside each app at matching responsibility-based
paths. Removed the shared package/sync/manifests and flattened one-file compatibility wrappers;
Capture also groups extraction and orchestration in one workflow folder. See [reuse](docs/reuse.md).
Local implementation is complete; verification evidence is in [verification](docs/verification.md).

## US1 — Python migration

### Description

Replace the PoC chat loops with one readable company-agent Python/LangGraph runtime, retaining the existing UI/API, scoped session and identity contracts. Make model/tool behavior testable and reusable for future DS/MLE work.

### Acceptance criteria

- JSON and SSE use one model/tools graph and one owned turn/persistence lifecycle.
- Tool visibility, routing, schema validation, budgets, cancellation and partial-response behavior have executable regression tests.
- Pascal is an MCP host with explicit SDK clients; identity, cookies, initialization and teardown are scoped and documented.
- Azure/Blob/HTTP/OTLP primitives are identical to Capture; no extraction runtime or obsolete internal feature runner remains.
- Original security/session contracts and unavoidable wire aliases are documented, including deliberate additive receipt metadata.
- No frontend/static edits are made in this refinement; earlier changes are disclosed. Real company-task quality remains PAS-R005.

### PAS-M01 — Map current chat behavior and retained boundaries

Description: Trace original JSON/SSE loops, JWT/Fernet, session storage, prompt/routing/source helpers and host UI contracts. Record retained/refactored/added code and earlier frontend changes; do not alter frontend assets.

Status: local implementation verified; see `docs/verification.md` and `docs/provenance.md`.

### PAS-M02 — Implement the single agent runtime

Description: Build model/tools StateGraph, typed state/context and ChatService admission/deadline/streaming/finalization ownership. Preserve the existing memory store; implement whole-turn context, call/round/output/cost bounds.

Status: local implementation verified; see `docs/verification.md` and `docs/provenance.md`.

### PAS-M03 — Implement model and MCP host/client adapters

Description: Reuse the Azure factory, assemble fragmented SDK streams, and use official MCP initialization/negotiation/JSON-SSE lifecycles. Retain qualified tools, paged scoped catalogs and Fernet payload; prevent cross-caller cookie/credential reuse.

Status: local implementation verified; see `docs/verification.md` and `docs/provenance.md`.

### PAS-M04 — Isolate application compatibility and Capture bridge

Description: Keep HTTP/session/locale/security contracts, route the composer to the independent Capture HTTP service, persist a minimal receipt, and confine old wire/storage names to compatibility. No Capture business logic or new UI is introduced.

Status: local implementation verified; see `docs/verification.md` and `docs/provenance.md`.

### PAS-M05 — Review and test company-agent failure semantics

Description: Exercise invalid tools/schemas, limits, partial streams, tool errors, shutdown/disconnect, single append, source/usage and privacy cases. Write the core-review and MCP feature-disposition notes; model quality belongs to US3.

Status: local implementation verified; see `docs/verification.md` and `docs/provenance.md`.

### PAS-M06 — Document reusable patterns and moderation design

Description: Publish architecture/provenance/common-module guidance and explain why the bridge remains. Answer moderation input/output/tool/streaming questions as design only, without implementing a moderation layer.

Status: local implementation verified; see `docs/verification.md` and `docs/provenance.md`.

## US2 — Independent deployment and platform integration

### Description

Package Pascal as an independently buildable ACA service using the organization's existing
registry, shared deployment helpers, secrets/identity conventions and Loki/Tempo servers.
Keep backend and end-user integration contracts unchanged.

### Acceptance criteria

- A locked, non-root image builds and passes Linux/offline startup tests without baked credentials.
- The repository CI gates image deployment; promotion reuses the tested immutable artifact.
- Platform reviews the actual Terraform state/module plan, managed identity/RBAC, secrets, ingress,
  probes and timeout configuration before applying it.
- Authenticated integration and existing UI/host behavior pass in the target environment.
- Logs and traces correlate in the existing Loki/Tempo servers; metrics reach an explicitly approved
  metrics receiver, not a Loki/Tempo URL.
- PAS-R001 through R004 and R006 are signed off. These external gates remain open.

### PAS-D01 — Build a reproducible runtime artifact

Description: Lock Python/build dependencies and base image digests, package standalone sources/assets, test a non-root image and verify offline probes. This task owns the image, not Azure resources.

Status: Local image/test work; final evidence in verification report.

### PAS-D02 — Prepare ACA infrastructure and deployment workflow

Description: Adapt the legacy shared helper/Terraform conventions, independent app identity and immutable promotion. Verify local syntax; platform must review state ownership and execute the real plan/apply.

Status: Artifacts prepared; actual provision/deploy pending R001.

### PAS-D03 — Configure runtime trust, secrets and permissions

Description: Map existing JWT/key/config secrets, managed identity Blob roles, Azure deployment endpoint/client mode, trusted downstream URLs and network/probe settings. Do not change security policy implicitly.

Status: Documented; corporate credentials/RBAC and risk sign-off pending R002/R006.

### PAS-D04 — Integrate callers and neighboring services

Description: Validate classic/composer HTTP and Capture MCP routes, required per-request identity/PDF/trade_type, session receipt ownership and unchanged host open-trade event. No backend/frontend edits in this task.

Status: Fixture contracts verified; real host/services pending R002/R003.

### PAS-D05 — Implement and validate observability

Description: Use matching local observability/telemetry.py modules for OTLP HTTP logs/traces/metrics, safe error spans, bounded metric labels and W3C propagation. Preserve full legacy signal URLs and explicitly configure the metrics receiver. Verify with local protobuf collector; then inspect actual Loki/Tempo and metrics routing.

Status: Local exporter tests verified; target-server inspection pending R004.

## US3 — Business validation and controlled rollout (later)

### Description

Demonstrate that the pending migration works on approved real business inputs and at expected load,
then decide whether it can replace the current implementation. Fixture success is not this acceptance.

### Acceptance criteria

- SMEs approve representative inputs and expected outcomes, including failures and both user audiences.
- Baseline and candidate runs use recorded prompt/model/config versions and no unexplained regressions.
- Load/failure/security checks establish acceptable latency, cost, isolation and recovery.
- Every release gate below has evidence and an assigned approver before broad promotion.

### PAS-V01 — Define the evaluation corpus and scoring

Description: Approve representative company questions, both locales, tools, missing data, sensitive requests and injection cases. Score answer facts, numeric accuracy, sources, tool scope, refusal/clarification and latency/cost against the original.

Status: pending SME/data access; R005.

### PAS-V02 — Execute target-environment integration and resilience checks

Description: Use approved keys/services to test both tenants, real Blob/MCP/backend access, JSON/SSE/session and Capture composer paths, trace correlation, timeouts, disconnects and representative concurrency. Record expected versus actual results and deployment digest.

Status: pending platform/QA environment; R002–R004/R006.

### PAS-V03 — Review canary evidence and promote or roll back

Description: Agree acceptance thresholds with product/SRE, deploy an isolated/canary revision, review regressions and promote the same tested image only after approval. Preserve the prior revision and current data contracts for rollback.

Status: pending all release gates; no cloud deployment performed by this refinement.

## Release gates (stable IDs)

| Gate | Acceptance evidence | Owner to assign | State |
|---|---|---|---|
| PAS-R001 | Organization CI, approved infrastructure/state plan, immutable image and dev revision | Platform | Open |
| PAS-R002 | Corporate JWT/roles, tenant isolation, real Blob/model/MCP/REST access | Security + integration | Open |
| PAS-R003 | Real Diapason embedding/composer and prefilled trade-open behavior | QA + UI/backend owners | Open |
| PAS-R004 | Same trace in Tempo and log in Loki; correct metrics receiver/labels and privacy | SRE | Open |
| PAS-R005 | SME-approved golden baseline/candidate scoring and performance thresholds | DS/MLE + product | Open |
| PAS-R006 | Explicit acceptance/remediation of legacy revocation, CORS, storage and trust risks | Security + platform | Open |

Earlier six-story/file-oriented boards are superseded. Prior audit/task references are historical;
release gate IDs above and future-work IDs in the relevant follow-up document remain stable.
