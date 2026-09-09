# Capture local verification — 2026-09-08

This report supersedes the 2026-09-07 report for the earlier pending rework. The original code remains
current. These are local implementation checks, **not an Azure deployment or real-model/business
acceptance**. All CAP/PAS-R001–R006 release gates remain open for their designated owners.

## Layout follow-up — 2026-09-09

Common primitives now live inside each application's own package, at matching responsibility-based
paths. Source/import/package changes retain behavior. The former manifest-only test was removed;
behavioral tests remain. The E01–E06 evidence below is the September 8 baseline, not a claim that
those exact historical images contain the new layout.

Current follow-up results:

- Windows Python 3.12.9: **44 passed** (3.81s); Linux Python 3.12.14: **44 passed** (2.55s).
  Only the obsolete manifest test was removed. Behavioral adapter, security and telemetry tests remain.
- Ruff check/format, locked dependency compatibility, source distribution and wheel builds passed.
  Wheel Python members match current source, with only the application's own package namespace.
- Five matching local module pairs were checked byte-for-byte; all are identical. This was a one-time
  verification, not a new sync/parity framework. See [reuse](reuse.md).
- Built `capture:layout-test` and `capture:layout-runtime`; the runtime's offline/non-root
  `scripts/container_check.py` passed with `--network none` and a read-only script mount.
  Revision label is `layout-local`. No image was pushed and no cloud deployment was performed.
- The workspace audit passed: all 90 original files and 18 frozen frontend/static files unchanged;
  wheel membership, local documentation links, workflow/HCL syntax and sprint structure checked.
- Obsolete source trees and their bytecode-only/empty directories were removed. Implementations
  remain in the new local paths; no compatibility import shims or common package remains.

## E01 — Python and contract checks

Windows Python 3.12.9 / uv 0.9.0: `uv run --locked --extra dev pytest` passed **45 tests**
(3.82s). Both suites use explicit fixtures and loopback servers, not corporate credentials.
Linux Python 3.12.14 also runs the test stage; final result is recorded below.

- Domain/graph/catalog: retained PDF/XML helpers, caller trade_type, output fields, original catalog and seven prompt byte hashes, node order and protocol-independent layers.
- Direct REST: original form/bearer/scope/list wrapper, success/failure/CDATA, one non-200 retry and failed multiline warning parity.
- Auth/front doors: real local RSA/PKCS#12 JWTs, role/revocation/customer negatives, multipart/classic contract and MCP capture tool input/output.
- Runtime: optional MCP import/lifespan, disabled mode/model ownership, total deadline cancellation, base64/request bounds, no-store/nosniff/request ID and safe unexpected failures.
- Actual OpenAI SDK fixtures: v1 and explicit dated endpoints/auth/deployment; exact Capture extraction messages and usage; no live Azure request.
- Observability: real loopback OTLP protobuf logs/traces/metrics, correlation/headers/cardinality/fixture-secret checks, failed business status even without tracing, no ambient LangSmith content or exception bodies.
- Naming/local code: old feature names confined to compatibility.py; local adapters are behavior-tested.

Scenario coverage is not a measured line-coverage percentage or proof of every production failure.
One upstream Starlette/AnyIO BlockingPortal deprecation warning remains; no application test failure.
The configured Pascal 3.14 CI matrix has not been executed in organization CI for this revision.

## E02 — Quality, reusable code and packages

`ruff check src tests scripts`, `ruff format --check src tests scripts`, `uv pip check`
and `uv build --no-sources` passed. 96 installed packages are compatible.
Capture does not claim a full-project static type checker; typed graph state/ports are supported by runtime/contract tests.

The common-package manifest test was removed with that packaging model. Each application runs its
own local adapter tests. See [intentional duplication](reuse.md). Wheel/source distributions built;
the workspace artifact
audit compares wheel Python members to current source to reject stale removed modules.
Use the complete repository/Docker artifact for runtime non-Python assets.

uv.lock SHA256: `24209abd99f8142e1968d5d200ed41b98d130e483a46eb163135d7ece69efde0`.

## E03 — Containers

Built the Linux test stage and independent non-root runtime. Runtime checks ran with `--network none`
and the read-only `scripts/container_check.py` mount, confirming UID/GID 10001, no baked local
configuration/keystore, offline import/lifespan and health/readiness.
Capture additionally proves base-package import with no MCP installed, HTTP-only disabled-mode startup and catalog assets.
Injected/disabled dependencies isolate packaging; these are not real authenticated-service smoke tests.

Runtime tag: `capture:refinement-runtime`; Docker image ID: `sha256:eb5ff0d0552e1be0a3e9cc7852f6ede7be29680ae6120a8c08c3577c559fdc8d`.
Revision label: `refinements-local`, not a fabricated Git SHA. Nothing was pushed to a registry.
Test-image runs use `docker build --target test`; see deployment.md for reproducible commands.
Linux suite result: **45 passed**, 2.74s.

## E04 — Provenance and frozen boundaries

`docs/provenance.md` inventories retained/refactored/added/removed production sections and operational
files against original sources, including earlier Pascal frontend changes. Capture's catalog plus
seven prompts are byte-identical to their original source manifest.
`reworks/source-baseline.json` records the pre-refinement original and frontend hashes;
`reworks/verify_workspace.py` checks all 90 original files, no original additions/removals, and all
18 frozen frontend/static baseline files. No moderation implementation or original/backend edit.

## E05 — Deployment and document artifacts

Both deployment workflows depend on quality; YAML/HCL/config syntax checks are local only. The
sprint boards now use three stories, explicit Description/Acceptance criteria and 14 technical tasks
with Description/Status each. Local document links and wheel membership are checked by
`reworks/verify_workspace.py`. Linux `bash -n` checks cover the deployment shell scripts.

Metrics endpoint/header variables can be supplied to deploy.sh independently of the private helper:
the endpoint/protocol are app environment values; explicit metrics auth headers become an ACA secret
reference. Supply them through the approved CI secret/config injection; no new secret was provisioned.
Loki/Tempo settings are retained. SRE must inspect the actual resulting environment and signal routing.

## E06 — What remains external

Organization CI execution, private ACA helper/module plan and state ownership, approved secrets/RBAC,
real Azure deployment/client compatibility, corporate MCP/Blob/REST, actual embedded UI/PDF behavior,
real Loki/Tempo/metrics routing, SME model/extraction quality and load/security acceptance remain open.
No Terraform init/validate/plan/apply, secret upload, remote prompt change, production smoke or rollout
is claimed. The read-only evaluation seeds/scripts do not establish a quality score.

The local refinement is ready for engineering review once the final workspace audit is green.
It does not authorize broad rollout or resolve legacy revocation/CORS/distributed-storage risks.
