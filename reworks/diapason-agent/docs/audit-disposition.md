# Disposition of the legacy audit

Reference: `../../../docs/01-issues-and-risks.md` in the original repository. This table separates
core changes from external redesign; implementation claims must
be read with the verification status of the associated task in `../SPRINT.md`.

| Issues | Treatment in this rework | Task / remaining ownership |
|---|---|---|
| A1, A2, A3 | Package boundaries and one explicit graph/service for both chat modes | PAS-T001/T002 |
| A4 | JWT verification is independent; app-specific identity/MCP wiring remains an adapter, not a marketed library | PAS-T010 |
| A5 | Sample-chart/dead fallback code not ported | PAS-T005 |
| B1 | No fabricated chart data, null compatibility fields, no unused Vega renderer | PAS-T005; grounded charts PAS-F012 |
| B2 | Tool exceptions/errors become sanitized tool results; final/partial transcript retained | PAS-T003/T004 |
| B3 | Disconnect cancels graph and awaits shielded transcript append; no crash-durability claim | PAS-T004; distributed durability PAS-F002 |
| B4 | Capture is external; async HTTP proxy, no synchronous extraction in API handler | PAS-T012 |
| B5 | Unknown @ prose allowed; explicit unavailable/ambiguous routes fail closed | PAS-T006 |
| B6 | Missing-record append applies mutation before initial upload | PAS-T011 |
| B7 | User-visible partial/persistence failure status; remote errors sanitized; compatibility storage internals retained | PAS-T003/T004; storage redesign PAS-F002/F005 |
| B8 | Async Azure timeout and bounded SDK retries; total turn deadline. Mutating tool calls deliberately not retried | PAS-T008; idempotent tool policy PAS-F006 |
| C1 | Token-limited tool results with visible truncation | PAS-T007 |
| C2 | No repeated tool-description summary; one catalogue reused per preparation | PAS-T009 |
| C3 | Whole old turns pruned against token budget before each model round | PAS-T007 |
| C4 | Stable system prefix; locale/time at the current-turn suffix. Cache savings measured, not guaranteed | PAS-T015; actual hit-rate PAS-R005 |
| C5 | Existing Blob history remains authoritative; no stale distributed session cache introduced | PAS-F002/F005 |
| D1 | One TTL/LRU discovery per scoped credential/server partition; pagination bounded | PAS-T009 |
| D2, D3 | Legacy summary-list cost and global Blob-write lock explicitly retained | PAS-F005 |
| D4 | Async model/MCP execution; synchronous storage runs off-loop; admission bounds | PAS-T008 |
| D5 | Bounded parallel execution only for fully read-only batches; otherwise ordered | PAS-T009 |
| E1, E3, E4 | Correlation IDs, model/tool/round spans and modern GenAI attributes alongside legacy log fields | PAS-T013 |
| E2 | FastAPI instrumentation plus concise application spans; explicit OTLP bootstrap retained for existing header conventions | PAS-T013 |
| E5 | Proposed measurement/alert runbook; actual SLO adoption/provisioning stays with SRE | PAS-F009, PAS-R004 |
| E6 | Query preview and tool payloads absent from application logs/spans; no LangSmith content export | PAS-T013 |
| F1 | Atomic snapshot + stable effective-policy hash, explicit layers in prompt module | PAS-T015 |
| F2 | Offline behavior regressions plus opt-in real-model evaluation workflow; no invented quality score | PAS-T015, PAS-R005/F004 |
| F3 | Existing locale logic/bundles retained; move instructions to resources when adding locales | PAS-F013 |
| F4 | Conversational local default; configured Blob prompt remains authoritative and is not rewritten remotely | PAS-T015; product must approve/redeploy new prompt |
| F5 | Chat temperature configurable; Capture's extraction temperature stays in Capture | PAS-T015 |
| G1 | Capture is a service, not an agent skill; legacy route name is an adapter only | PAS-T012 |
| G2, G3 | No extraction redesign in Pascal | Capture team's proposed improvements / PAS-F008 |
| G4 | New composer receipts omit extraction artifacts; historic data untouched | PAS-T012; retention PAS-F003 |
| G5 | Async network call removes loop blocking, but synchronous end-to-end request still has ingress latency constraints | PAS-F008 |
| G6 | Capture owns debug policy; do not silently change its existing client contract here | Capture + privacy owners; PAS-F003 |
| H1, H2, H3 | Locked build and quality workflow; local lint/type/test/build evidence distinct from deployed CI | PAS-T014/PAS-R001 |
| H4 | ASGI lifespan composition | PAS-T001 |
| I1, I2, I3 | No unapproved neighboring security/retention migration | PAS-F001/F003/F010 |
