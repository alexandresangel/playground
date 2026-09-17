# Azure deployment review: edit record

Date: 2026-09-16.

Scope: explain the minimum changes needed to deploy Capture through the company
Terraform repository while preserving the working runtime. Only files under
`ai-capture` were edited. Instructions embedded in `terraform_context.txt` were
treated as context, not executed.

## File inventory

| Operation | File | Reason |
| --- | --- | --- |
| Added | [AZURE_DEPLOYMENT.md](AZURE_DEPLOYMENT.md) | Deployment gap analysis, resource/secret mapping, proposed central Terraform interface, routing, Docker/dev validation, production constraints, and shared Terraform observations. |
| Added | [AZURE_DEPLOYMENT_CHANGES.md](AZURE_DEPLOYMENT_CHANGES.md) | This complete edit inventory and verification record. |
| Modified | [README.md](README.md) | Link to the Azure handoff; replace inaccurate inherited deployment guidance; correct the unsupported CI wheel-build claim and clarify the MCP port example. |

Removed files: none. Renamed files: none. Moved files: none.

No runtime, dependency, test, catalog/prompt, Docker, workflow, or deployment-script
files were changed. No keystores or local configuration were modified. No changes
were made to `pascal`, `diapason-agent-main`, or the supplied Terraform context.

## Planned work versus completed edits

The file-by-file deployment changes in `AZURE_DEPLOYMENT.md` are recommendations
for implementation after the central module/pipeline interface is known. The old
deployment workflow and scripts still exist and still have the documented defects;
this review has not made them deployable or disabled their release trigger.

## Verification

- Inspected the runtime settings, authentication, API paths, prompts, telemetry,
  Docker configuration, CI/deploy workflow, and inherited deployment scripts.
- Checked Azure/Terraform platform guidance against the official sources linked
  in the handoff document.
- Checked the new guide's local file links and JSON example, and the documented
  route/configuration names against the source.
- Compared SHA-256 file inventories before and after the edits to confirm the
  scope above. The supplied workspace has no `.git` metadata for `ai-capture`, so
  this verification uses file hashes rather than a Git diff.
- No test rerun was needed for these documentation-only edits. No Docker image
  was built/run, no Terraform was applied, and no live model/MCP request was made.

The two pre-existing README links to `CONFIG_UV_CI_CHANGES.md` and
`BLOB_STORAGE_REMOVAL.md` point to files absent in this supplied snapshot. They were
left as historical references; no replacement history was invented.

## Follow-up: explain configuration injection and remove local Docker prerequisite

Date: 2026-09-16. User clarification: Docker is unavailable on the work setup;
explain how the Terraform repository deploys Capture and supplies `CHAT_CONFIG`.

| Operation | File | Reason |
| --- | --- | --- |
| Modified | [AZURE_DEPLOYMENT.md](AZURE_DEPLOYMENT.md) | Added a direct source-to-image-to-ACA explanation, local/ACA configuration comparison, recommended whole-JSON Infisical setup, exact pipeline/root/module/ACA value mapping, and the remaining application-repository edits. Replaced the local Docker runbook with a CI build example and dev ACA validation. |
| Modified | [AZURE_DEPLOYMENT_CHANGES.md](AZURE_DEPLOYMENT_CHANGES.md) | Recorded this follow-up and its verification. |

Added, removed, renamed, or moved files in this follow-up: none. No source,
workflow, deploy-script, Dockerfile, or secret changes. No local Docker commands
were run or installation requested. This follow-up remains explanatory; it does
not create the missing central Terraform module or pipeline.

Verification: checked local document links and JSON syntax, rechecked the existing
settings loader and Docker entry point, and compared file hashes to confirm that
only these two documents changed during the follow-up. Platform behavior was
checked against the official sources linked in the guide. No application tests
or deployment commands were run for this documentation-only change.
