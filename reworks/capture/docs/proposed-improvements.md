# Proposed improvements (not implemented)

The migration intentionally keeps capture logic stable. These items should be separate stories with
golden-contract evaluation and explicit product/security decisions.

1. **Schema-constrained extraction.** Generate validated JSON and serialize deterministic XML instead
   of scraping XML from free text. Pilot one prompt family before changing all seven prompts.
2. **OCR fallback.** Route image-only PDFs through an approved OCR service after malware/content
   scanning; preserve page provenance and measure its false-positive rate.
3. **Asynchronous jobs.** When p95 approaches the ACA request limit, return a job ID and expose status.
   This requires UI work plus encrypted durable storage and a retention policy; do not persist current
   LangGraph state as-is.
4. **Bounded repair.** On a resolver business failure, optionally give the error and prior XML to the
   model for one constrained repair attempt. This changes behavior and cost, so gate it behind evals.
5. **Attachment handles for MCP.** Let Pascal pass a short-lived, tenant-bound opaque handle instead of
   base64. Reject arbitrary URLs to avoid SSRF and confused-deputy problems.
6. **Shared revocation/OAuth.** Replace replica-local revocation JSON with an authoritative store or
   standards-based Entra/OAuth validation before onboarding non-Pascal clients.
7. **Idempotency.** Add a caller-generated key before job/retry support so an interrupted client does
   not pay for duplicate LLM calls.
8. **Safer downstream retry.** The migrated client preserves the old retry-on-any-non-200 behavior.
   Restrict retries to transient statuses/timeouts with jitter after production response semantics are
   characterized.
9. **Golden evaluations and feedback.** Store anonymized expected fields by prompt family and capture
   user corrections from the final Diapason screen through a separately governed feedback channel.

