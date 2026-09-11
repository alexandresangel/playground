# Deployment and routing

The minimum cutover adds **one Capture Container App**. Pascal can replace the existing `diapason-agent` deployment while retaining its URL, identity, Terraform/OpenTofu state and storage ownership. No new model resource, MCP server, storage account/container, database, queue, vector store or graph checkpointer is required by this implementation.

## What stays the same

- `CHAT_CONFIG`, `JWT_KEYSTORE_P12_B64`, the `diapason-agent` JWT issuer, existing roles and all `X-Diapason-*` contracts.
- AzureOpenAI resource, deployment, API version, credentials and model parameters. Azure v1 migration is not part of this task.
- Custom stateless MCP transport: per-request `tools/list`, qualified names, encrypted per-caller Diapason context, direct `tools/call`, timeouts and response decoding. No MCP SDK or shared global tool catalog was added.
- Blob session keys `instance/customer/user/session.json`, record/artifact formats, existing containers and prompt Blob names. Local `config/` extraction assets retain their source text.
- Pascal frontend and system prompt. Its physical app/image names intentionally remain `diapason-agent` to avoid replacing company infrastructure merely to rename the source project.
- Existing deployment helper, Azure login actions, Infisical, registry, dev-build/test-prod-promotion flow and telemetry destinations.

## New settings and resources

| Item | Value / owner action |
| --- | --- |
| Capture ACA | New app/image `capture`, same existing ACA environment and resource group. Its own system-assigned managed identity. |
| Capture Blob grants | Contributor on the existing chat container; Reader on the existing config container. Capture Terraform declares these two grants and reads existing containers as data sources. |
| Capture secrets | New Infisical service path `/capture`: existing-format `CHAT_CONFIG`, `JWT_KEYSTORE_P12_B64`, and `SMOKE_API_CONFIG` for live acceptance. Shared registry credentials keep their existing `/` path. |
| Pascal relay | Set `CAPTURE_URL` to Capture's base URL (no `/api/...` suffix). Optional `CAPTURE_TIMEOUT_S` defaults to 600 seconds, matching the original extraction smoke timeout. The deployment script reads these optional values from Pascal's existing Infisical service path `/diapason-agent`, or accepts them in its environment. |
| Feature flag | Existing `intelligence_contract.enabled=true` in both configurations. No new configuration schema or storage/auth key is introduced. |
| Capture state | A separate Terraform/OpenTofu backend key. Do not point Capture at Pascal's existing state. Confirm the company helper's service-specific backend naming when reviewing the first plan. |

Capture needs the same JWT trust material and revocation policy as the caller's existing service, the same `storage.account_name` and `storage.chat_container`, and the same relevant MCP configuration. This lets Capture validate the original bearer and resolve an active Pascal session. `dia_jwt` remains unedited. Its revocation files remain local to each app/replica, as in the original; revocation administration/seed rollout must cover both apps according to the company's existing process. No cross-service revocation synchronization was invented.

An ACA managed identity can access Azure services through role assignments; see [Microsoft's managed-identity documentation](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity). Capture uses [the provider's existing-container data source](https://registry.terraform.io/providers/hashicorp/azurerm/4.67.0/docs/data-sources/storage_container), so it does not take over container/group-grant ownership from Pascal.

## Deployment sequence

1. Keep Pascal's original backend state and `APP_NAME=diapason-agent`. Keep the existing group/container resources in that state. The Pascal `infra.tf` and provider lock file are copied unchanged.
2. Make the existing `diapason/actions/service-deploy` helper available to each repository/runner, as in the original service. `ACTIONS_SERVICE_DEPLOY` may select its local checkout. It supplies `aca-lib.sh`, the ACA module, backend initialization, registry, secrets and health helpers. This dependency is not included in the supplied workspace.
3. Provision Capture's `/capture` secrets and GitHub environments/permissions using the existing company process. Reuse the working config values for JWT, storage, MCP and AzureOpenAI; enable extraction. The new deployment workflow does not need Node.
4. From Capture, run `bash deploy/deploy.sh dev plan` with the normal company deployment environment. Review for the new Capture app/identity and its two grants only; existing storage/container/group resources must not be recreated or removed. Verify a separate Capture state key. Then deploy with `bash deploy/deploy.sh dev`.
5. The current catalog/prompts can stay in Blob unchanged. If uploading them, run Capture's `bash deploy/deploy-config.sh dev`; it writes only the existing catalog/prompt keys. Pascal's corresponding script uploads only `system_prompt.md`. Refresh through Pascal after both apps are available, or call each refresh endpoint with a refresh-role JWT.
6. Set Pascal's `CAPTURE_URL` to the deployed Capture URL, retain its existing configuration, and run Pascal's plan/deploy using the existing backend. Its deployment fails early if extraction is enabled without a Capture URL. The pipeline builds the original frontend and then the Pascal package image.
7. Run the live smokes and host acceptance below. Promote each tested image using the existing test/prod workflow; keep a compatible Capture deployment available before promoting Pascal.

These are ready-to-use project files, not an assertion that an Azure plan/apply has run. The supplied workspace has no company helper/module checkout, Azure CLI credentials, Infisical configuration or host deployment. Those are the remaining environment-owned prerequisites.

## Entry paths and unchanged wire contract

| Entry | Routing |
| --- | --- |
| Existing Pascal slash/@ UI action | Existing UI - Pascal `GET/POST /api/skills/intelligence-contract` - configured Capture ACA. No frontend edit or new slash alias is required. |
| Classic Diapason UI | Capture serves the same multipart endpoint directly. An existing host using the Pascal URL can also keep that URL and use its relay. If direct Capture routing is desired, change only the host/proxy destination and preserve the current bearer, identity/MCP headers, PDF/trade-type fields and response header. |
| Ordinary agent tools | Existing dynamic per-caller MCP discovery/calls remain in Pascal. Capture is not registered as an invented MCP tool. The explicit PDF action needs no MCP-server change; Capture still calls the existing `resolveReferences`. |

Pascal forwards the original Authorization bearer, user/customer IDs, locale, active session header, and the four existing MCP context/protocol headers. Form fields/PDF bytes are retained. Capture revalidates the caller and owns the single session write. Pascal relays the status, body and session header; it has no local extraction fallback and does not retry the upload. A network failure yields 502, a client timeout 504, and missing routing configuration 503.

Preserve access from Pascal and whichever host serves the classic UI when choosing Capture ingress. Do not assume an internal-only app is reachable from a host outside its ACA environment. Use the company's existing network/ingress convention. Microsoft documents [default HTTP ingress's 240-second request timeout](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview). Increasing `CAPTURE_TIMEOUT_S` does not change that infrastructure limit; retain or verify the working environment's ingress timeouts for the original long-running PDF workflow. No premium-ingress purchase or async API redesign is required or performed here.

## Acceptance and rollback

- Local checks cover installed Linux services, real JWT validation, a real fixture PDF through LangGraph, caller-scoped MCP context, session artifact compatibility, JSON/SSE chat, direct Capture and Pascal relay, and repeated refresh. Blob, model and resolver endpoints are offline test doubles.
- Live Capture: run `python scripts/smoke_api.py` with the existing-format smoke config and Capture as `AGENT_URL`. Set `intelligence_contract_pdf` and `trade_type`; `SKIP_IC_SMOKE=1` deliberately limits the check to health/metadata.
- Live Pascal: run its original `scripts/smoke_api.py`; include the extraction PDF to verify the relay. Confirm frontend mentions, selected PDF/type, success/error text, prefill behavior and session history in the actual host. Verify real model/MCP/Blob access and existing OTEL dashboards.
- For rollback, use the existing pipeline to restore the previous Pascal image at the same app/URL/state. Shared prompt keys and session formats have not changed. Do not destroy shared storage or its existing state. Capture can remain deployed while the company decides its rollback policy.
