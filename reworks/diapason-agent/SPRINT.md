# Pascal core rework — delivery board

Scope: the standalone project in `reworks/diapason-agent`. No legacy backend, identity-provider,
MCP-server, or Blob-schema migration. Capture extraction remains in the sibling service.
Baseline audit: `../../docs/01-issues-and-risks.md`. Board updated 2026-09-07.

## How the team uses this board

Owners below are accountable **roles**, not assigned people. Assign a person and a target sprint at
planning. Estimates are engineering days, not commitments. Keep task IDs in commits and test reports.
`Verified local` means implemented with the named local evidence; it does not mean deployed or
product-accepted. `In progress` means implementation or verification remains. `Ready` is actionable
future work; `External gate` needs the specified environment, fixture, or decision. A story is accepted
only when all its acceptance criteria are demonstrated. Do not count external gates as completed.

For every task moved to accepted, attach: commit/image SHA, command or scenario, dated result, reviewer,
and evidence location. Reopen it on a regression. No real tokens, contracts, or customer data in tickets.

Handoff: all 16 tasks have implemented deliverables and local evidence; T012's visual/host acceptance
and T014's connected CI execution remain open and explicitly separated below. Stories are **ready for team
review**, not product-accepted. Start with the six release gates before selecting future enhancements.
See [the verification report](docs/verification.md) for commands, test scope and limitations.

## User stories and acceptance criteria

| Story | User value | Acceptance criteria | Audit coverage |
|---|---|---|---|
| PAS-US01 | As a maintainer I can change Pascal's reasoning without modifying HTTP, authentication, or storage code. | AC1 one compiled model/tools LangGraph; AC2 JSON and SSE use it; AC3 import needs no secrets/network; AC4 dependencies are injectable. | A1–A4, A5, A3, H4 |
| PAS-US02 | As a user I keep a truthful, recoverable conversation when dependencies fail. | AC1 tool failures become model-visible errors; AC2 unknown/invalid tools never execute; AC3 disconnect/timeout saves partial response once; AC4 failed persistence is explicit; AC5 no sample financial charts. | B1–B3, B5–B8 |
| PAS-US03 | As an operator I can bound each turn's resource use. | AC1 whole-turn history pruning; AC2 tool argument/result limits; AC3 tool-round/call/output/timeout/concurrency caps; AC4 optional estimated price guard with configured rates; AC5 tenant-isolated TTL catalogue. | C1–C4, D1, D4–D5 |
| PAS-US04 | As an existing client I can retain my tokens, sessions, tools, and embedded chat. | AC1 JWT issuer/roles/customer enforcement unchanged; AC2 Fernet payload and headers unchanged; AC3 old session API and Blob records readable; AC4 existing UI event/endpoint contracts retained. | A4, B4, B6, G1 |
| PAS-US05 | As an operator I can correlate Pascal with downstream services in Loki/Tempo without exporting conversation content. | AC1 existing OTLP env names and tenant headers; AC2 W3C trace chain; AC3 request/completion/model/tool spans; AC4 legacy log fields + trace IDs; AC5 no query/tool payload/credentials in logs or spans. | E1–E4, E6 |
| PAS-US06 | As a team I can review and release a tested agent. | AC1 reproducible dependency resolution; AC2 offline failure/contract regression suite; AC3 CI tests before release; AC4 versioned prompt and evaluation entry point; AC5 operational/architecture/next-step docs. | F1–F5, H1–H4 |

## Implementation tasks

| ID | Story / AC | Deliverable and exact completion check | Owner | Est. | Depends on | Status / evidence |
|---|---|---|---|---:|---|---|
| PAS-T001 | US01 AC1–4 | Extract composition root, typed graph state/context, model/MCP/storage ports. Import `pascal.main` with CHAT_CONFIG unset succeeds. | Agent eng. | 1 | — | Verified local: Docker build import, offline container check; `test_graph.py`, `test_api.py`; E01/E03 |
| PAS-T002 | US01 AC1–2 | Implement single model→tools→model graph. Assert graph nodes and identical final JSON/SSE fields. | Agent eng. | 1 | T001 | Verified local: `tests/test_graph.py`, `tests/test_api.py` |
| PAS-T003 | US02 AC1–2 | Validate tool names/JSON/schema; reject external schema references; recover from remote errors without leaking body. | Agent eng. | 1 | T002 | Verified local: `test_graph.py`, `test_additional_guards.py`; E01 |
| PAS-T004 | US02 AC3–4 | Own turn task, cancel graph, shield/await one Blob append, expose persistence failure. Test disconnect before producer starts, during generation and write, plus shutdown and interrupted tool receipts. | Agent eng. | 1.5 | T002 | Verified local: `test_lifecycle.py`, `test_graph.py`, `test_additional_guards.py`; E01; process-kill durability deferred F002 |
| PAS-T005 | US02 AC5 | Remove fabricated sample-chart branch. Assert chart_spec is null; no chart generator/renderer bundled. | Agent + UI eng. | 0.5 | T002 | Verified local: graph/API assertions, frontend build |
| PAS-T006 | US02 AC2 | Deterministic /help, /tools, /docs and scoped @ routing; ordinary unknown @ is prose, ambiguous known route fails closed. | Agent eng. | 0.5 | T003 | Verified local: `test_mcp.py`, `test_api.py`; E01 |
| PAS-T007 | US03 AC1–2 | Budget outgoing messages and schemas each round; prune whole old turns; bound result text. | Agent eng. | 1 | T002 | Verified local: context/pruning/truncation tests |
| PAS-T008 | US03 AC3–4 | Enforce round/call/output/time/active-turn limits and optional price guard; test configuration validation and each limit family. | Agent eng. | 1 | T007 | Verified local: `test_graph.py`, `test_lifecycle.py`, `test_additional_guards.py`, `test_model.py`; E01 |
| PAS-T009 | US03 AC5 | Cache tool schemas by scope/server/credential fingerprint; TTL/LRU, paginated discovery, safe read-only parallelism. | Agent eng. | 1 | T003 | Verified local: `test_mcp.py` (dedup/TTL/LRU/isolation/pages/cycles/bounds), `test_lifecycle.py` (parallelism); E01 |
| PAS-T010 | US04 AC1–2 | Preserve JWT/Fernet adapters with config injection; verify roles/customer/revocation plus decrypted MCP bearer parity. | Security + agent | 1 | T001 | Verified local: `test_api.py`, `test_mcp.py`; real corporate key remains R002 |
| PAS-T011 | US04 AC3 | Preserve required Blob fields/API; fix missing-record append omission and retain an optional sanitized tool-error code. Test legacy-shaped record round-trip. | Agent eng. | 0.5 | T001 | Verified local: `test_compatibility.py`, `test_api.py`, interrupted-tool test; real Blob/RBAC remains R002 |
| PAS-T012 | US04 AC4 | Keep copied embedded UI; proxy composer HTTP to Capture; opt-in per-server dynamic identity forwarding; preserve open-trade event. | Agent + UI eng. | 1 | T010 | Implementation and wire checks verified locally: `test_compatibility.py`, `test_mcp.py`, E04; visual/host acceptance open R003 (no browser connected) |
| PAS-T013 | US05 AC1–5 | OTLP bootstrap, privacy-safe spans/logs, trace propagation; collector/exporter and parentage tests. | Observability eng. | 1 | T002 | Verified local: `test_observability.py`, `test_exporters.py`, ambient LangSmith test; E05; actual collectors R004 |
| PAS-T014 | US06 AC1–3 | uv lock, non-root multi-stage Docker, CI lint/type/tests/UI build, immutable deployment promotion. | Platform eng. | 1 | T001 | Local packaging, Linux tests/runtime and configuration verified: E02/E03/E04/E06; connected CI and private platform execution open R001/R002 |
| PAS-T015 | US06 AC4 | Stable prompt snapshot/hash, explicit temperature, deterministic evaluation cases + opt-in real-model harness. | Agent + QA | 1 | T002 | Verified local: prompt refresh/hash tests, actual SDK fixture, 10 seed cases and guarded `scripts/evaluate.py`; E01; model quality remains R005 |
| PAS-T016 | US06 AC5 | README, architecture/compatibility, audit disposition, observability runbook, next steps, precise Capture board. | Tech lead | 1 | T001–T015 | Verified local: documents present, requirement/evidence map in `docs/verification.md`; team review/sign-off still required |

## Release acceptance gates (not claimed complete by local development)

| ID | Gate and evidence required | Owner | Dependency | Status |
|---|---|---|---|---|
| PAS-R001 | Run connected organization CI including Linux image/tests, dependency audit, import and health. Archive report with immutable image SHA and review promotion provenance. | Platform | T014 | External gate: organization CI; local Docker/Linux checks passed E03 |
| PAS-R002 | Dev ACA with actual config/key and Blob RBAC: existing JWT, list/read/write/delete session, every configured MCP server and both chat modes. No production data. | Platform + QA | R001 | External gate: dev credentials/environment |
| PAS-R003 | Side-by-side embedded chat and Capture: upload approved PDF, choose trade type, same prefilled trade view; /capture and @capture enter existing composer. | Product + QA | R002, CAP-R003 | External gate: Diapason host and golden PDF |
| PAS-R004 | Inspect a dev trace and correlated Loki completion log; ensure content/headers absent. Exercise tool timeout, disconnect and revision drain. | SRE | R002, T013 | External gate: collector access |
| PAS-R005 | Run approved representative questions in both locales, score factuality/tool selection/refusal/grounding and compare against baseline. Sign off quality and p95/cost thresholds. | Product + QA | R002, T015 | External gate: approved dataset and model budget |
| PAS-R006 | Confirm acceptance of replica-local revocation and Blob concurrency limits, or complete follow-ups before multi-replica rollout. | Security + platform | R002 | External gate: risk decision; see NEXT_STEPS.md |

## Verification log

2026-09-07: final local commands, 65-test Windows/Linux suites, image check, exporter test, packaging,
frontend audit, Capture's 20-test regression and legacy SHA256 comparison are recorded in
[docs/verification.md](docs/verification.md). E01–E07 in the task table refer to that report.
One upstream Starlette/AnyIO deprecation warning remains. No live model-quality score, cloud
deployment, browser visual acceptance or production-readiness certification is claimed.
