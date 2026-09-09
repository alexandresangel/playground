# Capture — sprint board

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

Migrate contract capture to one maintainable Python/LangGraph workflow while retaining the original extraction outcomes, security rules and caller contracts. Keep business code separate from protocols and reusable infrastructure.

### Acceptance criteria

- HTTP and MCP call the same seven-stage workflow; no MCP client or duplicate extraction is present.
- Original catalog/prompts, PDF/XML transformations, caller-selected trade_type and direct resolver form/result semantics are retained; deterministic fixtures pass.
- Package boundaries, reusable Azure/Blob/REST code and retained/refactored/added sections are documented.
- JWT roles, issuer, revocation/customer binding and identity forwarding remain compatible; old aliases are isolated.
- Real-document equivalence is demonstrated by CAP-R005 before migration acceptance (still open).

### CAP-M01 — Map the original extraction contracts

Description: Trace the original runner, PDF/XML helpers, catalog and sibling MCP resolver; record provenance and a field-level interface inventory. This task specifies parity, it does not rewrite the graph.

Status: local implementation verified; see `docs/verification.md` and `docs/provenance.md`.

### CAP-M02 — Group extraction and execution in one workflow

Description: Move the seven existing stages into explicit LangGraph nodes/state/context, keep pure transformations in workflow/extraction.py, and put timeout/lifecycle ownership in workflow/service.py. Preserve prompts and extraction decisions.

Status: local implementation verified; see `docs/verification.md` and `docs/provenance.md`.

### CAP-M03 — Extract reusable model, Blob and direct REST adapters

Description: Use the local Azure v1 client with explicit dated compatibility, retain Blob credential selection, and port only the resolver REST/form/parser behavior. Keep identical common files at matching paths in both app packages; document manual maintenance without a shared package or sync script.

Status: local implementation verified; see `docs/verification.md` and `docs/provenance.md`.

### CAP-M04 — Implement independent HTTP and optional MCP front doors

Description: Keep multipart metadata/capture contracts, map internal steps to existing display fields, share identity validation, and make FastMCP lazy/optional. Document relocation to a central MCP server without changing the workflow.

Status: local implementation verified; see `docs/verification.md` and `docs/provenance.md`.

### CAP-M05 — Verify deterministic behavior, isolation and failures

Description: Run extraction/catalog/form/auth/runtime/SDK tests, HTTP-only imports, deadlines, payload bounds, public error privacy, no ambient LangSmith export, and local adapter behavior. Real-model scoring belongs to US3.

Status: local implementation verified; see `docs/verification.md` and `docs/provenance.md`.

### CAP-M06 — Document the migration for maintainers

Description: Maintain architecture, provenance, compatibility/security, client-mode and MCP relocation explanations. Propose extraction improvements separately; do not implement OCR/prompt repair in this migration.

Status: local implementation verified; see `docs/verification.md` and `docs/provenance.md`.

## US2 — Independent deployment and platform integration

### Description

Package Capture as an independently buildable ACA service using the organization's existing
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
- CAP-R001 through R004 and R006 are signed off. These external gates remain open.

### CAP-D01 — Build a reproducible runtime artifact

Description: Lock Python/build dependencies and base image digests, package standalone sources/assets, test a non-root image and verify offline probes. This task owns the image, not Azure resources.

Status: Local image/test work; final evidence in verification report.

### CAP-D02 — Prepare ACA infrastructure and deployment workflow

Description: Adapt the legacy shared helper/Terraform conventions, independent app identity and immutable promotion. Verify local syntax; platform must review state ownership and execute the real plan/apply.

Status: Artifacts prepared; actual provision/deploy pending R001.

### CAP-D03 — Configure runtime trust, secrets and permissions

Description: Map existing JWT/key/config secrets, managed identity Blob roles, Azure deployment endpoint/client mode, trusted downstream URLs and network/probe settings. Do not change security policy implicitly.

Status: Documented; corporate credentials/RBAC and risk sign-off pending R002/R006.

### CAP-D04 — Integrate callers and neighboring services

Description: Validate classic/composer HTTP and Capture MCP routes, required per-request identity/PDF/trade_type, session receipt ownership and unchanged host open-trade event. No backend/frontend edits in this task.

Status: Fixture contracts verified; real host/services pending R002/R003.

### CAP-D05 — Implement and validate observability

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

### CAP-V01 — Define the evaluation corpus and scoring

Description: Select approved PDFs across trade types, record original extraction/resolution outputs, compare structured business fields/XML and review warnings. Do not treat mock PDF text or nondeterministic exact XML equality as a business-quality metric.

Status: pending SME/data access; R005.

### CAP-V02 — Execute target-environment integration and resilience checks

Description: Use approved keys/services to test both tenants, real Blob/MCP/backend access, all three Capture entry paths, trace correlation, timeouts, disconnects and representative concurrency. Record expected versus actual results and deployment digest.

Status: pending platform/QA environment; R002–R004/R006.

### CAP-V03 — Review canary evidence and promote or roll back

Description: Agree acceptance thresholds with product/SRE, deploy an isolated/canary revision, review regressions and promote the same tested image only after approval. Preserve the prior revision and current data contracts for rollback.

Status: pending all release gates; no cloud deployment performed by this refinement.

## Release gates (stable IDs)

| Gate | Acceptance evidence | Owner to assign | State |
|---|---|---|---|
| CAP-R001 | Organization CI, approved infrastructure/state plan, immutable image and dev revision | Platform | Open |
| CAP-R002 | Corporate JWT/roles, tenant isolation, real Blob/model/MCP/REST access | Security + integration | Open |
| CAP-R003 | Real Diapason embedding/composer and prefilled trade-open behavior | QA + UI/backend owners | Open |
| CAP-R004 | Same trace in Tempo and log in Loki; correct metrics receiver/labels and privacy | SRE | Open |
| CAP-R005 | SME-approved golden baseline/candidate scoring and performance thresholds | DS/MLE + product | Open |
| CAP-R006 | Explicit acceptance/remediation of legacy revocation, CORS, storage and trust risks | Security + platform | Open |

Earlier six-story/file-oriented boards are superseded. Prior audit/task references are historical;
release gate IDs above and future-work IDs in the relevant follow-up document remain stable.
