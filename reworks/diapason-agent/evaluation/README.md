# Evaluation is two different gates

The offline pytest suite runs the actual graph/API with scripted models and transports. It proves
control-flow, validation, persistence and wire invariants, not model factuality, extraction accuracy
or production latency. Do not report its pass count as a model quality score.

The live harness calls a deployed **approved read-only dev tenant**. It can consume model budget and
invoke tools. It creates sessions, then soft-deletes only those it created; legacy archived data
retention still applies. No live evaluation was run during this rework.

Copy cases.example.json to an ignored local dataset, replace starter questions with approved
representative cases, add approved_by and budget_reference, and fill the required/forbidden tool/text
assertions from known correct answers. Include successful retrieval, unavailable tool, aggregation,
relative business date, cross-language, injection, missing Capture input and multi-turn cases. The
starter file intentionally fails the approval gate; it is not a golden oracle.

Supply the same SMOKE_API_CONFIG keys as scripts/smoke.py and an isolated AGENT_URL. Then run:

```powershell
uv run python scripts/evaluate.py evaluation/approved.local.json --confirm-live-readonly-dev --max-cases 10
```

The stdout report contains case IDs, checks, latency and usage, not answers. Automated substring/tool
checks catch regressions but do not prove factual correctness. A reviewer must score grounding,
numeric accuracy, appropriate refusal, tool selection, locale and usefulness against the expected
facts/sources. Record deployment/prompt version, model deployment, image SHA and reviewer separately.
Compare the same approved dataset against baseline and candidate; adopt quality/cost/p95 thresholds
before a release decision. Store no real customer data or credentials in this repository.
