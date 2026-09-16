# Capture configuration, uv, CI, and local usage

Date: 2026-09-16

Scope: changes are confined to `ai-capture/`. This records the work after the
separate [Blob Storage removal](BLOB_STORAGE_REMOVAL.md). No deployment, remote CI
run, Azure operation, or change to another repository was performed.

## Behavior and decisions

- `config.example.json` and local `config.json` now contain only `jwt`, `capture`,
  `azure_openai`, and `mcp.default`. Removed the unused Pascal persona/UI and
  timezone blocks, chat tool-round/pricing options, and `docs`/`defthedge` servers.
- The new `capture` block replaces `intelligence_contract` in the configuration
  files. Runtime accepts the old key as a fallback for existing `CHAT_CONFIG`
  deployments; an explicitly supplied `capture` block takes precedence, even if
  empty or disabled. Existing HTTP aliases, JWT roles, and identity headers remain.
- Local JWT settings, extraction parameters, Azure credentials/deployment values,
  and the existing default MCP connection values were preserved. The example
  enables Capture and uses MCP port 8001 to distinguish it from Capture on 8000.
- Runtime dependencies are declared directly in `pyproject.toml`; development
  dependencies use its `dev` group. `uv.lock` locks 74 packages from public PyPI.
  Existing runtime dependency ranges were retained. LangSmith and Starlette are
  explicit dependencies because application code imports them directly. The old
  development `build` dependency is unnecessary because `uv build` handles builds.
- `.python-version` selects Python 3.12. The project requires uv 0.12.15 or newer;
  Docker and CI pin uv 0.12.15. The setuptools backend and existing package layout
  are retained.
- CI uses the existing self-hosted Linux runner labels. It installs the locked
  project with development dependencies, runs the complete test suite under
  `tests/`, and builds a wheel. Removed the nested `run:` shell typo and obsolete
  `test/` paths and ignores. Added read-only repository permissions, a timeout,
  and lockfile-based uv caching. The setup-uv action is pinned to v9.0.0's commit.
- Docker uses uv for the dependency layer and a non-editable production install,
  excluding development dependencies. The local configuration content remains
  bundled. Local secret JSON files, tests, environments, and generated packaging
  artifacts are excluded from the build context.
- Deployment no longer references the missing Pascal frontend or missing
  `test/test_agent_smoke.py` and its requirements-file installer. The existing
  post-deployment health and image-tag checks remain. Deployment app names,
  environment names, Infisical paths, and Terraform resources are unchanged.
- README now provides the requested local setup flow using uv: virtualenv
  creation/activation, dependency installation, tests, configuration, keystore,
  separate server/client terminals, JWT mint/display, Fernet generation, the
  supplied Azure key page, and both canonical and legacy curl examples. It
  corrects `/ai/capture` to `/api/capture` and explains that the Fernet key must
  match the MCP server's key. Obsolete UI, frontend, test, and deployment-smoke
  instructions were removed.

## Modified files

| File | Edit |
| --- | --- |
| `config.example.json` | Keep Capture-only settings, rename the extraction block, enable the example, and separate the example MCP port. |
| `config.json` | Apply the same structural cleanup while preserving active connection/secrets and extraction settings. |
| `pyproject.toml` | Replace requirements-file indirection with runtime dependencies, a dev group, and a minimum uv version. |
| `src/capture/workflow/prompts.py` | Prefer `capture` settings, with a legacy-key fallback. |
| `tests/conftest.py` | Exercise the new configuration key through the API fixture. |
| `tests/test_runtime.py` | Exercise actual startup using the new configuration key. |
| `tests/test_workflow.py` | Exercise extraction settings under the new key. |
| `tests/test_capture_catalog.py` | Add precedence, legacy fallback, and explicit-empty configuration tests. |
| `.github/workflows/ci.yml` | Install with pinned uv, validate the lockfile through sync, run all tests, and build a wheel. |
| `Dockerfile` | Replace pip/requirements installation with locked uv production installation. |
| `.dockerignore` | Correct the test-directory exclusion; exclude all root `config.*.json` files, distributions, and generated metadata; remove obsolete frontend exclusion. |
| `deploy/deploy.sh` | Remove missing frontend build and missing legacy smoke-test/requirements commands; retain health/image checks. |
| `.github/workflows/deploy.yml` | Remove Node/npm setup for the nonexistent frontend. |
| `README.md` | Rewrite current configuration, local setup/usage, CI, Docker, and deployment instructions; retain the storage-removal behavior and link both change records. |
| `src/capture/common/dia_jwt/README.md` | Use `uv sync` and `uv run` for the JWT CLI examples from the project root. |

## Added files

| File | Purpose |
| --- | --- |
| `.python-version` | Default local Python version: 3.12. |
| `uv.lock` | Reproducible runtime and development dependency resolution. |
| `CONFIG_UV_CI_CHANGES.md` | This record. |

The local install/build also generated these ignored metadata files (they were
absent at the start of this task):

- `src/capture/common/ai_capture.egg-info/PKG-INFO`
- `src/capture/common/ai_capture.egg-info/SOURCES.txt`
- `src/capture/common/ai_capture.egg-info/dependency_links.txt`
- `src/capture/common/ai_capture.egg-info/requires.txt`
- `src/capture/common/ai_capture.egg-info/top_level.txt`

The new local `.venv/` is left ready for development. Ignored `.validation/` and
`build/` contain downloaded validation tooling/cache, offline test credentials,
the sample app, wheel/build output, and generated files. All remain inside this
repository and are excluded from Git and Docker by the existing/updated rules.
Their file inventory is in [.validation/uv-migration/FILES.md](.validation/uv-migration/FILES.md),
which was also added for this record. No global tool/package installation was
changed; uv 0.12.15 was installed locally under `.validation/` for these checks.

## Removed files

| File | Replacement |
| --- | --- |
| `requirements.txt` | `[project].dependencies` in `pyproject.toml` and `uv.lock`. |
| `requirements-dev.txt` | `[dependency-groups].dev` and `uv sync --locked`. |

No files were moved or renamed. Catalog content, prompts, trade XML, model
extraction logic, resolver requests, and authentication policy were not changed.

## Validation

- `uv lock` and `uv lock --check`: passed, using uv 0.12.15 and Python 3.12.9.
- `uv sync --locked --group dev`: passed in a new `.venv/`.
- `uv run --locked --no-sync python -m pytest`: **59 passed**. Test temporary
  files were directed under `.validation/`; one upstream Starlette/AnyIO
  deprecation warning remains. No live Azure or MCP service was contacted.
- `uv build --wheel`: passed. Inspected the wheel's modules, locale files, direct
  dependencies, and absence of development dependencies in runtime metadata.
- `uv sync --locked --no-dev --no-editable`: passed. Verified the production
  environment has no pytest, uses the installed package, runs the documented
  keystore/mint CLI flow, loads local configuration and bundled prompts, and
  completes an authenticated PDF flow through both documented API routes with
  offline model/MCP doubles. Confirmed `/ai/capture` returns 404. Restored the
  development environment afterward with `uv sync --locked --group dev`.
- Linux production dependency sync with `--python-platform
  x86_64-unknown-linux-gnu --dry-run`: passed. This checks resolution/install
  planning, not Linux execution.
- Parsed CI/deployment YAML, checked CI commands and setup-uv inputs against the
  pinned action, and checked the README's Bash examples and `deploy/deploy.sh`
  with `bash -n`: passed.
- Checked both configuration structures, lockfile registry, Python pin, and
  remaining requirements/frontend/smoke references.
- Actual GitHub CI was not run. The self-hosted runner must support the Node 24
  action runtime and access the configured actions, uv/Python downloads, and
  PyPI. A Docker build was not run because the local Docker daemon is unavailable.
  Terraform and deployment were not run.

Implementation references: [uv GitHub Actions](https://docs.astral.sh/uv/guides/integration/github/),
[uv Docker](https://docs.astral.sh/uv/guides/integration/docker/),
[dependency groups](https://docs.astral.sh/uv/concepts/projects/dependencies/), and
[the pinned setup-uv action inputs](https://raw.githubusercontent.com/astral-sh/setup-uv/c771a70e6277c0a99b617c7a806ffedaca235ff9/action.yml).
