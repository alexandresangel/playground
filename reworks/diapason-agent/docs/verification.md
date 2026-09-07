# Local verification and handoff — 2026-09-07

The Pascal core rework is implemented in `reworks/diapason-agent`. This report records local
implementation evidence, not deployment, product acceptance or a live-model quality score. No
cloud resource, remote prompt, backend endpoint, MCP server or legacy source was changed.

## Requirement-to-evidence map

| Requested outcome | Implementation and local evidence | Remaining acceptance |
|---|---|---|
| Clean, simple, modular LangGraph core | One compiled graph in `agent/graph.py`; `ChatService` owns both JSON and SSE; injectable model/MCP/store ports; import and graph/API tests | Maintainer review; no framework-driven memory migration |
| Address the existing audit without redesigning surrounding systems | Every A1–I3 issue mapped in `audit-disposition.md` to a delivered task or separately owned follow-up | External security/storage/product decisions in `NEXT_STEPS.md` |
| Keep current security logic | Preserved JWT issuer/RS256/role/customer/revocation behavior and Fernet payload; real locally generated RSA/PKCS#12 tests; scoped cache/forwarding/cookie-isolation negatives | Actual corporate key/RBAC, trusted integration headers and accepted legacy risks: R002/R006 |
| Keep existing MCP/session/UI boundaries | Stateless JSON/SSE MCP adapter tested against actual SDK server; legacy-shaped Blob adapter/API tests; Capture HTTP result and identity forwarding tests; unchanged layout/event contracts | Real MCP/Blob/Diapason host: R002/R003 |
| Same Loki/Tempo compatibility with improved visibility | Same signal endpoint/env/header semantics; real local OTLP exporter traffic and protobuf decoding; ingress/downstream W3C; safe span/log and ambient-tracing privacy tests | Actual collector routing and trace inspection: R004 |
| Precise user stories/tasks | Six stories, 16 tasks and six separate release gates in Pascal's board; Capture board expanded to six stories, 20 tasks and six gates, with ACs/roles/dependencies/estimates/evidence | Assign people, sprint dates and reviewers; do not equate local verification with acceptance |
| Next steps/future improvements | `NEXT_STEPS.md`: 13 prioritized, owned follow-ups with dependencies and acceptance evidence | Team prioritization and approval |
| Do not edit the legacy project | Final SHA256 comparison: all 90 files outside `reworks` match the pre-work baseline; no added or missing files | Repeat against the team's eventual commit |

Paths to code/tests below are relative to this standalone project's root; implementation modules are
under `src/pascal`. E01–E07 are stable evidence IDs referenced by `SPRINT.md`.

## E01 — Python behavior and boundary regressions

Windows, Python 3.12.9, uv 0.9.0:

```powershell
uv run --locked --extra dev pytest --junitxml=pytest-report.xml
```

Result: **65 passed**, 6.43 seconds. The generated JUnit file is local/ignored; CI uploads its own
report. The same 65 tests passed in the Linux test image under Python 3.12.14, including a second
network-disabled run (4.17 seconds). One upstream Starlette/AnyIO `BlockingPortal` deprecation
warning remains. The final 3.14 matrix has not run; earlier partial suites did, but are not substituted
for that CI gate.

Coverage by test module (scenario coverage, not a measured line-coverage percentage):

- `test_graph.py`: graph loop, invalid/hallucinated tools, sanitized tool failures, budget pruning,
  limits, partial responses and session exclusion.
- `test_lifecycle.py`, `test_additional_guards.py`: disconnect before producer entry, during model/tool
  execution and persistence, shutdown, single append, interrupted-tool receipt, total/model deadlines,
  admission/call/argument/message/output/cost guards, forbidden external schema references, price
  validation, prompt refresh/hash and disabled ambient LangSmith tracing.
- `test_api.py`: JSON/SSE public fields, scoped sessions, JWT roles/customer/revocation and locale.
- `test_mcp.py`: decrypted legacy Fernet payload, stable credential-partitioned cache, no identity
  broadcast, TTL/LRU/dedup, pagination/cycle/page/row bounds, routing, JSON/SSE and cookie isolation.
- `test_mcp_protocol.py`: actual pinned FastMCP SDK's stateless HTTP transport, not only a hand-written
  JSON mock. This is not a claim of support for stateful MCP session protocols.
- `test_model.py`: actual Azure OpenAI SDK with a fixture stream, fragmented tool arguments,
  cached-token usage, explicit temperature/output/retry options. No live Azure request.
- `test_compatibility.py`: missing-record Blob append regression, legacy-shaped records and Capture
  multipart/public XML passthrough with a minimal transcript receipt. No live Blob/backend request.
- `test_observability.py`, `test_exporters.py`: the E05 checks below.

## E02 — Static and package checks

```powershell
uv run --locked --extra dev ruff check src tests scripts
uv run --locked --extra dev ruff format --check src tests scripts
uv run --locked --extra dev mypy
uv pip check
uv build --no-sources
```

All passed: 43 lint/format-targeted files, three mypy-targeted files, 102 compatible installed
packages; wheel and source distribution built. Mypy intentionally checks only `config.py`,
`agent/state.py` and `ports.py`; it is **not full-project static typing**. Compatibility copies are
excluded from Ruff rather than mechanically rewriting security/storage code.

The Python wheel contains the package and locale bundles. Deploy the complete repository/Docker
artifact for the static UI and runtime prompt; the wheel alone is not the complete web distribution.

## E03 — Linux images and offline runtime

```powershell
docker build --target test -t pascal-rework:test .
docker run --rm --network none --entrypoint /app/.venv/bin/pytest pascal-rework:test
docker build --build-arg GIT_REVISION=local-verification -t pascal-rework:local .
$pascalChecks = (Resolve-Path scripts).Path
docker run --rm --network none --mount "type=bind,source=$pascalChecks,target=/checks,readonly" --entrypoint python pascal-rework:local /checks/container_check.py
```

Both images built successfully. The runtime check passed: UID/GID **10001:10001**, no baked local
config/key, offline tokenizer/import, injected lifespan startup, `/health`, `/ready`, `/api/i18n`,
index and JavaScript assets. Test doubles isolate startup from external credentials; this is not a
real authenticated application smoke. Docker HEALTHCHECK is not proof of ACA probe configuration.

Local runtime image ID (manifest list reported by Docker):
`sha256:61f28c052f7800e3d17232f9105532dc7b9b83f2c51464f6f86c06e05767245e`.
Revision label: `local-verification`, not a fabricated Git SHA. No registry push occurred. Record the
actual commit and registry digest after extraction/CI. Runtime `uv.lock` SHA256:
`02c1823280ede59028f99e7502edf542553e4477a378b5501b441c742507c771`.

## E04 — Frontend checks and explicit visual limitation

From `frontend`: `npm ci`, `npm run build`, `npm audit --audit-level=moderate`,
`node --check src/chat-app.js` and `node --check src/boot.js` all passed. npm reported **zero
vulnerabilities** on this date; this is not a perpetual security guarantee. The vendor bundle is
62.5 KiB after removing unused sample-chart code and patching DOMPurify.

Copied HTML/CSS/image assets and the `dia-agent-open-trade` payload were inspected for parity.
Integration edits only add Capture command aliases, consume canonical final SSE text and remove
fabricated chart rendering. HTTP asset delivery passed in E03. The browser skill found **no connected
browser**, so no screenshots, visual interaction or real host trade-opening acceptance is claimed.
Keep PAS-R003/CAP-R003 open until QA checks the actual embedding with approved PDFs.

## E05 — Observability interoperability

`test_exporters.py` runs `scripts/telemetry_check.py` in an isolated process against an actual
loopback HTTP collector. OTLP protobuf logs and spans arrived at the configured full signal URLs,
with expected Bearer/tenant headers and a matching log/model-span trace ID. No real token or remote
collector was used. Separate tests verify ingress W3C parentage, downstream propagation, suppressed
ambient HTTP header capture, no raw error message in spans/logs, and disabled LangSmith tracing.
These validate the adapter; PAS-R004 still requires a real Tempo/Loki inspection.

## E06 — Deployment/configuration artifacts

`uv run --locked --extra dev python scripts/validate_artifacts.py` passed: Terraform HCL, workflow
YAML and configuration/evaluation/npm JSON parsed; deploy depends on quality. Git Bash `bash -n
deploy/deploy.sh` passed. The quality workflow contains Linux tests/builds and frontend audit; it
has **not run in organization CI**. Nested workflows are inactive until this folder is a repository.

Terraform init/validate/plan and ACA deployment were not executed: the private shared module/helper,
state ownership and organization credentials require platform coordination. Reuse/import existing
state or provision an isolated dev app; never apply fresh state over existing app/storage resources.
The live smoke and read-only evaluation scripts are delivered but intentionally not executed.
The ten seed evaluation cases are a starting point, not an SME-approved golden dataset.

## E07 — Capture regression and legacy preservation

From sibling `capture`, `.venv/Scripts/python.exe -m pytest`: **20 passed** (2.53 seconds), with the
same upstream deprecation warning. Only Capture's `SPRINT.md` was changed for this Pascal task.
The final legacy hash audit found 90 unchanged files outside `reworks`, zero additions and zero
removals. Existing backend/MCP/security sources remain untouched.

## Verification incidents and recovery

Initial formatting configuration accidentally included the new virtualenv and uv hardlinked cached
packages. It was corrected to `extend-exclude` plus explicit source/test/script targets. Only named,
regenerable uv package-cache entries were cleared, and the locked environment was reinstalled with
copy mode; both projects' final suites passed afterward. No user source was deleted. A concurrent
Docker test-image export encountered a missing cache snapshot after tests passed; a sequential
retry and subsequent offline test-image run succeeded. No broad Docker prune was performed.

## Release decision

Ready for engineering review and isolated dev integration, **not broad rollout**. The six release
gates in `SPRINT.md` remain open for organization CI, actual JWT/Blob/MCP configuration, Diapason
host/PDF interaction, real collectors, model-quality evaluation and legacy-risk acceptance. Shared
revocation, distributed persistence, retention/CORS policy and attachment handles are explicitly
owned future work, not silently changed in this core rework.
