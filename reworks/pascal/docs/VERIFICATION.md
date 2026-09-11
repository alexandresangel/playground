# Verification record

Validated in the migration workspace on 2026-09-11.

- `python -m pytest -q`: **90 passed, 7 strict expected failures**.
- `python -m build --wheel`: passed. Wheel entries preserve company source bytes and both locale files, with no duplicate company modules or embedded egg-info.
- Independent Linux `docker build`: passed.
- Original/protected baseline: 127 original/company files across the workspace unchanged. Project-specific original source/asset audits pass.
- Bash syntax for deployment/upload scripts, HCL/provider-lock syntax and CI YAML parsing: passed. No undefined Python names under Ruff F821/F822/F823.
- Both live smoke CLIs load and show `--help`; they were not run against the company environment.

The workspace `tools/verify_containers.py` passes with both final installed images. It exercises actual HTTP for direct Capture and Pascal relay, a real fixture PDF through LangGraph, original shared session/artifact helpers with one extraction write, JSON/SSE chat, repeated catalog refresh and caller scope. External Blob/model/MCP services are offline doubles; test credentials are generated locally.

Pascal's original frontend and lockfile pass byte comparison and `npm ci`/build. Its seven source-filter expected failures were reproduced against the original source. Optional source-differential/provenance tests skip after separating the projects from the original checkout; normal functional tests are self-contained.

The tested dependency resolution includes Python 3.12, LangGraph 1.2.11, FastAPI 0.141.1 and OpenAI 3.13.0. Existing requirements/config conventions are retained; these are observed versions, not a new lock policy.

Real Terraform/OpenTofu plan/apply and Azure/model/MCP/Blob/host acceptance require company environment access and the original deployment helper/module, absent from this workspace. See [deployment](DEPLOYMENT.md) for the exact remaining steps and [sprint](SPRINT.md) for commit grouping.
