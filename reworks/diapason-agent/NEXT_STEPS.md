# Next steps and future improvements

Priority is sequencing, not a promise to change neighboring systems in this rework. Owners are roles
to assign at planning. Complete PAS-R001–R006 in `SPRINT.md` before broad rollout.

| ID | Priority / owner | Work and reason | Dependencies / acceptance evidence |
|---|---|---|---|
| PAS-F001 | P1 / Security + platform | Replace replica-local JWT revocations with an authoritative shared store or existing corporate gateway. Preserve issuer/claims during migration. | Threat model and migration decision; revoke then verify denial across two replicas and revisions; tested outage policy. |
| PAS-F002 | P1 / Storage team | Durable per-session turn IDs, compare-and-swap/lease ownership, interruption status and idempotent writes across replicas. Current turn shielding cannot survive process kill. | Versioned compatible record migration; simultaneous-turn/delete/crash tests; no duplicate or resurrected turns. |
| PAS-F003 | P1 / Privacy + product | Define retention and redaction for chat/tool traces, Capture debug data and historic contract artifacts. Existing blobs are untouched. | Approved classification/retention schedule, backfill plan, deletion evidence and access review. |
| PAS-F004 | P1 / QA + product | Build an approved golden question set for internals and clients, both locales, real tools, missing data, injection attempts and finance aggregation. | R002; named expected facts/sources/tool scopes, human sign-off, baseline and regression thresholds. No synthetic tests presented as model-quality proof. |
| PAS-F005 | P2 / Storage team | Index session summaries and paginate listing; remove one-download-per-session and global synchronous write lock. | Retain session API or add compatible pagination; load-test latency, ETag contention and storage transaction cost. |
| PAS-F006 | P2 / MCP owners | Agree read-only annotations, safe retry/idempotency keys, bounded results and central MCP placement for Capture. SDK lifecycle is now implemented; add a longer-lived owned client only if a server needs state across separate operations. | Server contract tests; no retry of ambiguous mutations; identity-bound session eviction/teardown and central Capture HTTP delegation tested. |
| PAS-F007 | P2 / Product + Capture + UI | Opaque authorized attachment handles for agent-initiated Capture. Do not place multi-megabyte PDF base64 into the model context. Require explicit trade_type and user-provided file. | Attachment authorization, expiry, size/retention policy, tool-runtime injection, open-trade event contract and two-tenant E2E tests. Current composer works separately; this is not silently inferred from a filename. |
| PAS-F008 | P2 / Capture team | Long-running Capture jobs with durable result retrieval if measured latency exceeds ingress budget; OCR, XML validation/repair and extraction improvements separately evaluated. | Capture golden PDFs, extraction parity preserved, UX/backend agreement before async job contract. See Capture proposed improvements. |
| PAS-F009 | P2 / SRE | Turn measurements into agreed SLOs and provision alerts/dashboards in the platform repository. | R004/R005; traffic baseline, burn-rate rules, synthetic failure drills, runbook links and assigned pager. |
| PAS-F010 | P2 / Security + UI | Replace wildcard credentialed CORS only after inventorying approved Diapason embedding origins; review postMessage origins and source-link URL policy. | Host/browser integration suite; cross-origin negative tests; no silent UI break. |
| PAS-F011 | P2 / Agent team | Deployment-specific tokenizer/output parameter support and model evaluation. Reasoning deployments may need max_completion_tokens and no temperature. | Approved Azure deployment/version, transport fixtures and live cost/quality baseline before switching configuration. |
| PAS-F012 | P3 / Product + agent | Grounded charts from verified tool data, not sample series or unrestricted generated Vega programs. | Explicit typed chart/data contract, provenance, numeric equality tests, accessibility and security review. |
| PAS-F013 | P3 / Agent + localization | Move language instructions to reviewed locale resources when adding locales. Keep bundled en_us/fr_fr behavior for now. | Translation owner and locale-specific eval cases; remove stale language branches after parity tests. |
| PAS-F014 | P1 before external clients / Product + security + privacy | Decide and evaluate layered input/output moderation, DLP, tool approvals and streaming release policy. No moderation code was added. | Approved policy/test corpus, Azure filter configuration, data-residency review, false-positive/negative measurements and outage behavior; see docs/moderation-design.md. |
| PAS-F015 | P2 / SRE | Connect the new optional OTLP metrics export to an approved metrics-capable receiver/backend. Do not point it at Loki or Tempo signal URLs. | Correct signal auth/tenant routing, bounded labels, real measurements and owned alerts; local protobuf tests alone do not provision a backend. |

## Suggested rollout

First extract this folder into its own repository and run the quality workflow. Then build once and
deploy the immutable image to an isolated dev revision with the existing integration contracts.
Validate real JWTs, Blob, MCP, Capture and trace correlation there. Have product/QA score an approved
sample of real tasks, and measure p95 latency/cost before choosing SLOs or model changes. Promote the
same tested image to test/prod only after the release gates are signed off. Keep rollback to the prior
revision; this rework performs no destructive Blob migration.

LangGraph does not itself solve authorization, shared revocation, distributed persistence, reliable
financial facts, or model quality. Those remain explicit boundaries with their own owners and evidence.
