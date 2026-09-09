# Independent Capture ACA deployment

The repository contains deployment artifacts, not a completed Azure deployment. Extract this folder
as its own repository before its nested GitHub workflows can run. The original services are untouched.

## Local build

Use uv 0.9.0, Python 3.12 and uv.lock. The Dockerfile pins Python/uv image digests, checks an HTTP-only
base package without MCP installed, installs the optional MCP extra for the default runtime, and has
a separate test stage. The image runs as UID/GID 10001 with no local secrets baked in.

```powershell
uv sync --locked --extra dev --extra mcp
uv run --locked --extra dev pytest
uv run --locked --extra dev ruff check src tests scripts
uv run --locked --extra dev ruff format --check src tests scripts
docker build --target test -t capture:test-suite .
docker build --build-arg GIT_REVISION=local-verification -t capture:local .
$captureChecks = (Resolve-Path scripts).Path
docker run --rm --network none --mount "type=bind,source=$captureChecks,target=/checks,readonly" --entrypoint python capture:local /checks/container_check.py
```

The offline check uses disabled Capture and injected security to test packaging/lifespan, not actual
Azure or JWT access. The complete repository/image includes catalog assets; the Python wheel alone
does not include the filesystem catalog/config deployment bundle.

## Existing platform conventions

deploy/deploy.sh uses the same organization aca-lib.sh and Infisical/registry flow as the original
agent/MCP project. Platform must supply the private shared helper/module and Azure state configuration.
Infrastructure references the existing ACA environment/storage account, creates a separate Capture
app identity, and grants Storage Blob Data Reader on the existing config container. It does not create
or migrate the Diapason backend. Review the real plan and resource ownership before applying it.

Runtime secrets are CAPTURE_CONFIG and JWT_KEYSTORE_P12_B64, backed by ACA secret references. Preserve
the existing key/issuer/customer/roles/revocation policy. Validate Azure client mode/deployment support,
managed identity RBAC, DNS, ingress trust and downstream allowlists in dev. The default MCP host list
must match the deployed hostname; HTTP-only config sets mcp.enabled=false.

CI checks Python and both container stages; deployment depends on CI. Dev builds a commit image;
test/prod promote an existing approved SHA through the shared helper. Promotion still requires a
recorded successful dev run and registry digest: a local test is not evidence about a registry tag.
No CI run, push, Terraform apply or cloud deployment was performed in this refinement.

deploy/deploy-config.sh overwrites the **shared** existing catalog/prompt blobs. Do not run it as a
routine prerequisite if the platform already manages those prompts. Verify live versions, backup and
obtain the owners' approval before upload; the bundled baseline may not equal today's remote content.

## Runtime validation and rollback

The script requests one to three replicas. Before multi-replica production, address or explicitly
accept replica-local revocations. One Uvicorn worker runs per container. Platform must verify actual
startup/readiness/liveness probes, ingress/exposure, payload limits, graceful termination and egress
against the private ACA module plan; Docker HEALTHCHECK is not proof of ACA probes.

Total capture execution defaults to 210 seconds, inside ACA's documented 240-second ingress window.
Parser threads may outlive cancellation. Measure real PDF/model/backend latency and memory before
tuning concurrency or replicas. Durable jobs would require a separately agreed caller/UX contract.
[ACA ingress](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview).

Exercise classic HTTP, Pascal composer and agent MCP with approved PDF/trade_type and real delegated
identity. Inspect public XML/prefilled UI fields, tenant isolation and Loki/Tempo trace correlation.
Metrics require their own approved receiver; see observability.md. Keep the previous image/revision
available for rollback; there is no data migration/checkpoint to undo. CAP-R001–R006 remain open until
their platform/security/QA/SME evidence is signed off.
