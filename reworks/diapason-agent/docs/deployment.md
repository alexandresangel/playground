# Build and deploy Pascal independently

Run from this project root after extracting it into its own repository. Nothing here changes the
legacy deployment. The provided workflow paths are relative to that future repository root; workflows
nested in this parent project's reworks directory will not automatically run in GitHub Actions.

## Local gates

Use uv 0.9.0 with uv.lock (Python 3.12 runtime, 3.12/3.14 CI matrix). requirements.lock is a generated
pip-compatible runtime export for the existing deployment smoke helper. Refresh it whenever uv.lock
changes. Runtime dependencies and build backend are locked; Docker base images are digest-pinned.
The Docker build produces the frontend itself with npm ci and fails if bundling fails.

```powershell
uv sync --locked --extra dev
uv run --locked --extra dev ruff check src tests scripts
uv run --locked --extra dev ruff format --check src tests scripts
uv run --locked --extra dev mypy
uv run --locked --extra dev pytest
uv pip check
uv run --locked --extra dev python scripts/validate_artifacts.py
uv build --no-sources
docker build --build-arg GIT_REVISION=local-verification -t pascal-rework:local .
```

The image runs UID/GID 10001, contains no config.json or PKCS#12 key, and writes only runtime data
under /app/data by default. Its tokenizer data is preloaded so context budgeting does not require a
new outbound download at startup. scripts/container_check.py can be mounted read-only at /checks and
run with Docker --network none to check non-root execution, offline import/tokenizer, injected
lifespan, probes and static assets. Those injected startup checks do not prove live Azure access.

## Existing platform integration

deploy/deploy.sh retains the organization service-deploy/Infisical conventions and
INFISICAL_SECRET_PATH=/diapason-agent, IMAGE_NAME=diapason-agent, TARGET_PORT=8000. It expects the
shared aca-lib.sh through ACTIONS_SERVICE_DEPLOY (or the documented neighboring checkout) and the
shared Terraform module under deploy/.terraform-modules/aca_app. These private dependencies are not
vendored or replaced. Platform must provide them and review the rendered plan.

Runtime secrets remain CHAT_CONFIG and JWT_KEYSTORE_P12_B64. Keep the existing issuer/key/customer
rules, storage account/containers and managed identity roles. Configure Azure chat deployment,
MCP defaults/extras and the same OTLP collector environment variables. Capture extraction config is
now in its service; set capture.enabled/base_url in Pascal only for the composer proxy.

The existing service name is retained for compatibility. **Do not apply a fresh Terraform state over
the existing app/containers**. Platform must either use the existing state for an approved migration,
import the owned resources, or parameterize an isolated dev app/state before first application. The
shared storage containers must not be accidentally re-created or reassigned by a second state.

The quality workflow gates deployment. Dev builds the commit SHA; test/prod promote an existing
immutable SHA image through the shared helper. Record the successful dev quality run/image digest
before promoting. GitHub environment approvals and organization-pinned action revisions remain
platform policy; the private shared actions cannot be verified locally.

## Health, limits and rollback

/health is liveness; /ready is initialized readiness. Platform must verify startup/liveness/readiness
probes and request/termination timeouts in the **actual shared ACA module plan**. Docker HEALTHCHECK
does not automatically prove ACA probe configuration. The agent turn deadline includes preparation
and graph/external-work execution. Transcript finalization follows it, within the surrounding
platform's termination budget; this is not a guarantee after forced process termination.

Keep old tokens/Blob schema throughout a canary. Compare representative approved dev conversations,
session round-trips, Capture host events and traces before promotion. Roll back to the prior immutable
revision if errors/latency/quality regress. No data migration is required to roll back. Before multiple
replicas, address or explicitly accept replica-local revocation and cross-replica turn ordering risks.

scripts/smoke.py reads legacy SMOKE_API_CONFIG fields and AGENT_URL. It checks health/readiness,
configured MCP catalogues, scoped sessions and deterministic JSON/SSE commands, then archives only
its own session. It does not prove model quality; use the separately approved evaluation workflow.
