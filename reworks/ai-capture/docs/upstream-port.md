# Agent upgrade review and Capture port

Compared the supplied `diapason-agent-main/` filesystem snapshot with `ai-agent/`
(including its working tree), then assessed every difference against `ai-capture/`.
The baseline is an unpacked directory without Git history. Upgraded agent HEAD:
`730b9529ad5d4baf86dbd0d6bc2111baa4f8c880`. Capture starting HEAD: `67b08c53e807822860b605c20b619b2c4d0e93ba`.

**35 source/documentation files differ: 4 added, 18 modified, 13 deleted; 58 are unchanged.**
The initial 36-file filesystem count also included ignored `ai-agent/test/test.api.local.json`:
that is private machine configuration, not a feature to copy. Its credential field names
were reviewed; its values are not included in this report or inventory.

The exhaustive [93-file inventory](upstream-file-inventory.csv) includes unchanged files,
LF-normalized SHA-256 hashes, and a Capture decision for every source difference. Excluded:
Git internals, Python/test caches, virtual environments, node_modules, generated static/js,
runtime data, keystores, and private local JSON configuration. This is a comparison of
available snapshots, not a claim about unrecoverable intermediate history.

The two pre-existing `ai-agent` working-tree changes (`deploy/deploy.sh` and
`test/test_agent_smoke.py`) are executable-bit differences only; their contents match HEAD.
Neither source repository nor Pascal was modified. All code changes are in Capture.

## What changed and what was retained

1. **M2M authentication replaces local JWT issuance.** Ported upstream RS256/JWKS
   validation, registry-derived issuer, exact space-delimited scope checks, client_id
   identity, bounded JWKS caching, unknown-key rotation retry and startup warmup.
   Removed the entire `dia_jwt` source/package, token mint/revoke endpoints and schemas,
   `require_admin`, and runtime/deploy keystore dependencies. Capture defaults to
   `ai-capture`, configurable through `m2m.required_scope`. A deliberately configured
   `ai-agent` override supports a transition with existing clients. The internal
   dependency is named `require_capture`; refresh uses the same M2M scope as upstream.
   The HTTP client closes on application shutdown and catalog startup failure; a zero
   clock-skew setting is honored (upstream's `or 60` accidentally replaced zero).
2. **Registry discovery and local config precedence.** Ported `registry_client.py`
   and `CHAT_CONFIG > config.local.json > config.json`. Runtime requires `registry_url`
   in JSON and discovers `services.m2m.url`, not a separate REGISTRY_URL environment
   setting. Only the smoke utility accepts the upstream environment overrides.
3. **Prompts move out of Blob into the image.** Already implemented in Capture as
   `config/catalog.json` and `config/prompts/`, including safe relative paths, versioning,
   caching and refresh. Kept this implementation. The upstream optional `catalog_file`
   and legacy blob-prefix adapter were not needed for Capture's existing fixed layout.
   The upstream chat `system_prompt_file` option has no Capture counterpart.
4. **Deployment moves to a platform-owned Terraform shell.** Adapted deployment to
   app/image `ai-capture`, Infisical `/ai-capture`, `CAPTURE_URL`, `dev/staging/prod`, registry
   token auth and optional OTEL seeding. Removed the obsolete agent Terraform/blob
   resources, their now-unused Capture lock file, and blob upload script. Removed
   frontend build calls and nonexistent requirements/test paths from deployment.
   Capture smoke runs through the existing locked uv project. Health/image checks run
   even when API smoke is disabled. No infrastructure was applied and no image deployed.
5. **CI and release configuration.** Applied minimal token permissions, disabled persisted
   checkout credentials, supplied GITHUB_TOKEN for registry publishing, and moved shell
   inputs into environment variables. Retained Capture's uv install and current action
   versions instead of upstream's checkout/setup action downgrades. Retained push CI and
   manual dev deployment; automatic deployment on every main push is a release-policy
   change not required for this port. Staging promotion and published-release production
   promotion follow upstream. The obsolete `test` environment name is no longer accepted.
6. **Smoke tests use M2M and the proxy's Diapason login flow.** Added Capture-only smoke:
   Basic client_credentials without a requested scope, registry or explicit token URL,
   static access-token fallback, environment overrides, Diapason credential aliases,
   health/build identity, authenticated catalog, and optional PDF extraction. It preserves
   statelessness and correlation checks and never imports a trade. Chat, sessions and
   tool-list checks were intentionally excluded because Capture does not expose them.
7. **Frontend/proxy upgrades stay with the agent/Pascal.** `/ai/agent` routing, removal
   of embedded browser config/tenant IDs, M2M troubleshooting text and logo retries are
   listed below for future Pascal work. No frontend was reintroduced into Capture.
8. **Documentation and obsolete design files.** Replaced Capture's stale agent README
   with operating instructions for this service. Upstream removed four historical agent
   design documents; none existed in Capture and none needed porting.

The extraction algorithm, catalog/prompts, MCP context/RPC, locales, telemetry helpers,
Azure model settings and requirements are unchanged between the two supplied agent
snapshots. In particular `pypdf>=6.16.1`, the Dependabot setup and the dependency upgrades
seen in agent history were already present in this baseline. No dependency/uv.lock changes
were needed. Capture's LangGraph workflow, privacy controls, stateless behavior and legacy
HTTP aliases remain intact. Upstream still uses Blob for chat sessions: it removed Blob
**configuration**, not all Blob storage. Capture already has neither runtime storage path.
Unused historical blob/session helper source files were left alone; they are not packaged
or imported by the Capture service.

## File-by-file decisions

Paths in the first column are relative to the two agent snapshots. Capture runtime
counterparts live under `src/capture/`, shared modules under `src/capture/common/`,
and tests under `tests/`.

| Upstream file | Decision | Capture treatment |
|---|---|---|
| `.dockerignore` | Already present / adapted | Capture already bundles config/ and excludes secrets; remove old keystore-runtime wording. |
| `.github/workflows/ci.yml` | Partially applied | Scoped permissions and persist-credentials=false; retain Capture uv/locked install, push CI and existing action versions. |
| `.github/workflows/deploy.yml` | Adapted | ai-capture identity; staging promotion; safe env-fed shell values; scoped package permissions; GITHUB_TOKEN; uv smoke. Keep existing manual dev trigger and checkout version. |
| `Dockerfile` | Already present / adapted | Capture catalog/prompts already bundled with uv; update runtime auth comment, retain Capture entry point. |
| `README.md` | Adapted | Replace stale agent/blob/JWT instructions with actual Capture API, M2M, config and deployment instructions. |
| `app.py` | Adapted | Wire M2M identity/dependencies in Capture runtime and extraction; remove local token administration. File-backed refresh already present; retain simple public Capture health. |
| `auth_m2m.py` | Applied / adapted | New common auth_m2m module; default ai-capture scope; require_capture dependency; zero clock skew honored; close client on shutdown/startup failure. |
| `auth_setup.py` | Applied | Replace local-keystore setup with the upstream M2M adapter. |
| `config.example.json` | Adapted | Add registry_url and M2M config, remove jwt; keep Capture-only settings and no storage/chat/UI. |
| `deploy/deploy-config.sh` | Applied removal | Remove obsolete blob-upload script; config ships in image. |
| `deploy/deploy.sh` | Adapted | External Terraform model, ai-capture image/app/secret path, staging, registry auth and OTEL; Capture smoke via uv; no frontend/requirements.txt; always health/image checks. |
| `deploy/infra.tf` | Applied removal | Remove legacy agent/blob/keystore infrastructure; platform must provision Capture shell separately. Remove Capture obsolete Terraform lock too. |
| `dia_jwt/README.md` | Applied removal | Remove old auth package documentation. |
| `dia_jwt/__init__.py` | Applied removal | Remove old auth package exports and packaging entry. |
| `dia_jwt/__main__.py` | Applied removal | Remove local JWT CLI entry point. |
| `dia_jwt/auth.py` | Applied removal | Remove keystore signing, local token minting and revocation. |
| `dia_jwt/cli.py` | Applied removal | Remove local keystore/token commands. |
| `dia_jwt/fastapi.py` | Applied removal | Replace role/customer-bound dependencies with M2M client identity and trusted proxy headers. |
| `docs/01-issues-and-risks.md` | Not applicable | Deleted upstream historical agent review; absent from Capture, no runtime change to port. |
| `docs/02-roadmap-1-month.md` | Not applicable | Deleted upstream historical agent roadmap; absent from Capture. |
| `docs/03-target-architecture.md` | Not applicable | Deleted upstream agent target design; preserve independent Capture architecture. |
| `docs/04-intelligence-contract-design.md` | Not applicable | Deleted upstream historical IC design; preserve implemented Capture workflow. |
| `frontend/src/boot.js` | Deferred to Pascal | Remove embedded config parsing upstream; Capture has no chat frontend. |
| `frontend/src/chat-app.js` | Deferred to Pascal | /ai/agent proxy prefix, proxy-supplied IDs, logo retry and M2M auth error message are agent UI changes. |
| `ic_prompt_loader.py` | Already present | Capture config/ loader already supplies file reads, root confinement, content version, cache and refresh. Do not add legacy blob-prefix or catalog_file override. |
| `prompt_loader.py` | Not applicable | Chat system-prompt file/override loader has no equivalent in standalone Capture; extraction prompts already local. |
| `registry_client.py` | Applied | Copy registry/services.json discovery and M2M token URL lookup into packaged common modules. |
| `settings.py` | Applied | CHAT_CONFIG > config.local.json > config.json; require registry_url in JSON, no runtime REGISTRY_URL fallback. |
| `skills/intelligence_contract/config/README.md` | Adapted | Image-bundled prompt instructions documented for Capture config/ in its README. |
| `skills/intelligence_contract/config/upload.sh` | Already absent | Capture has no skill upload script; remove its remaining deploy-config.sh counterpart. |
| `static/agent/agent-widget.js` | Deferred to Pascal | Logo cold-start retry belongs to the chat widget; no Capture frontend. |
| `test/test.api.example.json` | Adapted | Add tests/test.api.example.json for capture_url, M2M credentials, PDF extraction and Diapason context. |
| `test/test_agent_smoke.py` | Adapted | Add Capture-only smoke with Basic client_credentials, registry/token URL, env overrides, static token option, Diapason login aliases and real extraction; no chat/session checks. |
| `test/test_auth_m2m.py` | Applied / extended | Port signed RSA/JWKS tests for Capture; add rotation, required claims, scope override and zero-skew coverage. |
| `test/test_registry_client.py` | Applied | Port registry discovery tests; add startup/config/API/real-HTTP coverage in Capture tests. |

## Configuration and rollout boundary

- Grant the intended M2M caller `ai-capture`, or explicitly configure the transitional
  `m2m.required_scope: ai-agent`. Existing legacy role-based JWTs are intentionally no
  longer accepted. There is no local revocation list or admin token API.
- As in upstream, client_id identifies the M2M caller while user/customer/MCP context
  comes from trusted proxy headers. The old JWT customer_id equality check no longer
  applies. Metadata/refresh require only the M2M token; extraction also requires context.
- Put `registry_url` in deployed CHAT_CONFIG and update the platform's Capture ACA shell,
  image-pull setup, secrets, GitHub environment names and M2M grants before deploying.
  No platform infrastructure project or shared service-deploy library is included in
  this workspace; their provisioning remains outside this repository change.
- The ignored local `ai-capture/config.json` now has the `registry_url` from the existing
  agent local config so the new loader can start. Other local values were preserved;
  unused local keystore/revocation files were not deleted and are not used or packaged.
  No private credentials were copied into tracked files.
- The legacy extraction route remains a compatibility alias. Changes to Pascal's proxy
  path, client credentials or scope grants are documented here for later work only.

## Validation

- Baseline: **59 tests passed** before changes.
- Final: **105 tests passed** with `uv run --locked --no-sync python -m pytest -q`
  against a non-editable install. One existing Starlette/AnyIO deprecation warning;
  no failures. Includes upstream JWT/JWKS and registry tests, real signed-token API
  checks, config precedence, key rotation, stale/cold cache,
  startup and cleanup, existing workflow/privacy/MCP tests and deployment shell checks.
- A separate real local HTTP process runs the installed Capture service, discovers a
  local registry/JWKS, receives a client_credentials token and executes PDF extraction
  with model and MCP doubles through the real API and LangGraph workflow.
- Built the distribution wheel and installed Capture non-editably to verify the packaged
  imports, including the new auth/registry modules and absence of dia_jwt.
- Workflow YAML and embedded Bash, deploy script syntax, example JSON and
  `git diff --check` passed. Dependency versions and `uv.lock` remain unchanged.
- Deployment checks use a stub shared library for dev/staging/prod, smoke invocation,
  health checks without Infisical and rejection of the old test environment. They do not
  claim validation of Azure or the unavailable external deployment library.
- Live platform M2M verification was attempted using the existing local settings but
  could not complete due to **ReadTimeout**. No successful live Azure OpenAI/MCP smoke
  run is claimed. Docker image build/run was unavailable because the Docker daemon is
  not running. No release, remote deployment or Pascal change was performed.
