# Refinements — requirement and verification ledger

Requested 2026-09-08. Both reworks remain pending migrations; the original repository and
`../diapason-mcp-main` are the current implementation references. Only `reworks` is writable for
this task. No frontend/static edits or moderation implementation in this refinement.

## Required outcomes

| ID | Requirement | Current implementation/evidence | State |
|---|---|---|---|
| REF-01 | Capture has a clear MLE-oriented package layout with one unchanged business workflow | Layer/import tests; extraction/catalog parity; architecture doc | Locally verified |
| REF-02 | Reusable Azure OpenAI client follows verified current guidance in both apps | Matching local module copies; actual SDK fixture tests for v1 and explicit dated compatibility | Locally verified |
| REF-03 | Common Blob/telemetry/integration primitives use the same reusable code | Intentional local duplication at matching paths, documented manual maintenance, standalone builds | Locally verified |
| REF-04 | Direct Diapason REST adapter is identifiable/reusable and preserves current resolution behavior | Original MCP source comparison, XML/form/retry/identity tests, reuse guide | Locally verified |
| REF-05 | Capture MCP server is isolated and removable without changing its HTTP workflow | HTTP-only startup test, MCP-enabled equivalence and relocation guide | Locally verified |
| REF-06 | Pascal is an MCP host with explicit clients/server lifetimes and preserved useful features | Official SDK integration; identity/session isolation; routing/catalog/lifecycle tests; feature disposition | Locally verified |
| REF-07 | Re-review Pascal core for correctness, simplicity and company-agent use | Written core review plus targeted regression tests/fixes | Locally verified |
| REF-08 | Explain/isolate the Capture HTTP bridge; remove nonexistent internal skill concepts | Naming guard, old wire/storage alias inventory, no extraction in Pascal | Locally verified |
| REF-09 | Standards-based logs/traces/metrics without breaking Loki/Tempo routing | Real local OTLP signals, correlation/privacy/cardinality tests, collector/backend configuration doc | Locally verified |
| REF-10 | Dedicated provenance docs identify retained/refactored/added/removed code and earlier frontend changes | Source-level inventory with hashes/diffs against original; frontend frozen this turn | Locally verified |
| REF-11 | Answer moderation design question without code changes | Cited design-only note covering internal/client input/output and streaming/tool boundaries | Locally verified |
| REF-12 | Replace story/task format with fewer technical MLE stories | Each app: migration, deployment/integration, and deferred validation; story title/description/AC; task title/description | Locally verified |
| REF-13 | Complete local verification and preserve original sources | Both suites/lint/builds/containers, original hash audit, precise remaining live gates | Locally verified |

## Working decisions

- Keep small integration primitives as ordinary, intentionally duplicated files within each app.
  Matching responsibility-based paths make reuse visible; changes are reviewed and applied manually
  to both copies. No shared package, generator, synchronization script or manifest. Business graphs,
  prompts and session policy remain application-specific. See capture/docs/reuse.md.
- Preserve old public wire/storage names only in named compatibility boundaries where removing them
  would require the frontend/backend migration explicitly excluded by this request. No skill framework,
  registry, runner or new skill terminology in application logic.
- Metrics export requires an explicitly configured metrics-capable receiver. Do not send metrics to
  a Loki or Tempo signal URL, provision a backend, or claim dashboards exist.
- Real-model/golden-PDF evaluation and Azure rollout are tracked as external acceptance work, not
  silently reported as completed by fixture tests.

## Baseline

2026-09-08: captured SHA256 for all 90 original files outside `reworks`. 

## Layout follow-up — 2026-09-09

The user requested local duplication rather than a shared integration package. All Capture Python
now lives under src/capture with four responsibility folders: workflow, adapters, api and
observability. Single-file auth/compatibility wrappers are flattened. Pascal retains its meaningful
multi-module folders and the same relative paths for the five common files. The old canonical
source, sync script and manifests are removed. Runtime behavior and frozen boundaries are unchanged.
Per-app verification reports record this follow-up; September 8 evidence below is historical.

Follow-up verified: Capture 44/Pascal 88 tests pass on Windows and Linux; five local module pairs
are byte-identical. Ruff, dependency checks, wheel/source builds and offline non-root runtime
checks pass. Pascal's three-file mypy scope passes. The workspace audit confirms all original and
frozen frontend files unchanged. Only the obsolete shared-manifest test was removed from each suite.
Obsolete source trees, sync/manifests and bytecode-only empty wrappers are removed.

## Completion evidence — 2026-09-08

- Capture: 45 tests pass on Windows/Python 3.12.9 and Linux/Python 3.12.14.
- Pascal: 89 tests pass on both platforms, including four actual SDK MCP server modes.
- Both: Ruff check/format, compatible locked environments, wheel/source builds, standalone Linux test
  images, non-root network-disabled runtime checks and real local OTLP logs/traces/metrics pass.
- Historical September 8 check: the then-packaged common modules matched. The September 9 layout
  supersedes that packaging with five identical local implementation files in each application. Capture's original catalog and seven prompt bytes match their source manifest.
- Pascal mypy covers its declared three-file scope only. Organization CI and its 3.14 matrix are not
  claimed as executed for this revision.
- `verify_workspace.py`: 90 original files unchanged, no additions/removals outside reworks; all 18
  frozen frontend/static baseline files unchanged; current wheel Python members, workflow/HCL syntax,
  three-story/14-task boards and local documentation links checked.
- `capture/docs/provenance.md` and `diapason-agent/docs/provenance.md`: complete production Python
  inventory and retained/refactored/added/removed sections; earlier frontend changes explicitly disclosed.
- `diapason-agent/docs/core-review.md`, `mcp.md` and `moderation-design.md`: core review, SDK host/client
  feature decisions, bridge rationale and design-only moderation answer.

The local refinement request is delivered; **migration/rollout is still pending**. Release gates
CAP/PAS-R001–R006 remain open for real corporate credentials/services, private infrastructure/state
review, actual Diapason embedding, collector/metrics receiver inspection, approved golden-model/PDF
quality and legacy-risk acceptance. No remote app, backend, secret, prompt or cloud resource was changed.
Per-application verification reports supersede the older September 7 evidence.
