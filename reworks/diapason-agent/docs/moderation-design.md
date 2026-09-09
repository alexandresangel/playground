# Moderation and safety layers — design only

No moderation code, API call, model deployment, policy toggle or UX change was added.

Recommendation for a future internal-and-client company assistant: use several narrowly defined
controls, not one model that decides whether everything is safe. The precise categories, thresholds,
appeal path, supported languages and outage behavior need product/security/privacy ownership.

## Proposed placement

| Boundary | Proposed control | Decision owner |
|---|---|---|
| Before accepting input | Existing authentication/tenant authorization, size/rate limits, file validation | Platform/security; deterministic |
| Before a model turn | Content-category screening plus tenant-specific business policy | Product/security; classifier where justified |
| Retrieved documents/tool results | Treat as untrusted data; injection checks and structured extraction | Agent/MCP owners; never promote to system instructions |
| Before a tool call | Schema, permitted action/resource scope, confirmation for consequential changes | Backend authorization + product workflow |
| Before displaying output | Content screening, sensitive-data/DLP checks, grounding/citation/numeric checks | Privacy + product/SMEs |
| After the turn | Minimal policy outcome/version/latency metrics and redacted review samples | Privacy/SRE with approved retention |

Moderation categories are not equivalent to fraud prevention, financial accuracy, confidentiality,
tenant isolation or permission to execute a trade. A benign-looking request can still be unauthorized.
Conversely, a business document mentioning a sensitive category may be legitimate; evaluate false
positives on actual supported business tasks rather than choosing thresholds by intuition.

OpenAI provides a moderation API for content-category screening; category results need application
handling. Its existence does not prove that the same endpoint/model is available under this Azure
deployment or that documents may be sent to another provider.
[OpenAI moderation](https://developers.openai.com/api/docs/guides/moderation).

Azure's configured content filters are a separate platform layer affecting prompts and completions.
Blocked inputs, filtered outputs and filter-unavailable outcomes require deliberate handling and
monitoring; confirm the actual deployment configuration.
[Azure content filtering](https://learn.microsoft.com/en-us/azure/foundry-classic/foundry-models/concepts/content-filter).
Do not add an OpenAI-hosted moderation dependency without data-residency and procurement review.

## Streaming tradeoff

Full-response approval before display requires buffering the answer, increasing time to first visible
text. Streaming first and classifying afterward cannot retract what the user already saw.
Chunk screening adds latency and can miss meaning spanning chunks; it is not equivalent to full-text
approval. Decide by use case: buffered release for externally shared or high-risk answers, versus
approved platform streaming controls for lower-risk interactions. This requires a product/UX decision;
the current SSE behavior was deliberately not changed.

## Practical implementation sequence for later

Define a policy matrix by audience/action, including refusal, clarification, escalation and classifier
outage behavior. Evaluate current Azure filters before adding a second classifier. Build a reviewed
test set covering both locales, legitimate finance documents, injection, cross-tenant access and
sensitive output. Run a privacy-approved shadow evaluation; measure false positives/negatives and
latency. Only then enforce, version policies, define human review and rollback.

A guardrail model is useful as a classifier, never as the source of backend authority. Tool approvals,
limited privileges and treating external material as data remain separate controls.
[OpenAI agent safety guidance](https://developers.openai.com/api/docs/guides/agent-builder-safety).
