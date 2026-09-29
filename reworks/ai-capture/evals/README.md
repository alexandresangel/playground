# Capture evaluation

This layer measures the content produced by Capture. Its Python code lives in the repository-level `evals/` package, outside the deployed `src/capture` application. It is excluded from the application wheel and Docker image. Run it from a repository checkout; the API does not import it or run evaluations on startup.

The ordinary pytest suite verifies software and grader behavior with mocked dependencies. Live content evaluations are explicit commands, separate from the default CI job. The service retains debug metadata such as prompt hashes, model identifiers and token usage so evaluation runs can identify what produced an output; this does not require deploying evaluation code.

The minimum evaluation case is **PDF + selected trade type + expert-reviewed expected XML**. A dataset manifest binds these together. Raw responses and reports are kept separately from approved expectations; no command promotes generated output to ground truth.

## 1. Export one PDF

From the `ai-capture` root, install the existing dependencies with `uv sync --locked --group dev`.

Use the standalone `scripts/capture_pdf.py`. Its configuration, authentication requests, headers and multipart capture request follow the existing `tests/test_integ.py`. The exporter does not import or modify that integration script.

When connected to the target environment, use the same environment configuration as your integration checks. No command-line arguments are required:

```bash
export INTEG_APP_CONFIG="$(cat tests/integ.app.pascal-dev.json)"
export INTEG_PLATFORM_CONFIG="$(cat tests/integ.platform.local.json)"
uv run --locked python scripts/capture_pdf.py
```

This reads `capture_pdf` and `trade_type` from the configuration and writes a fresh directory under `evals/responses/`, named with the PDF stem, UTC timestamp and unique suffix. Alternatively, copy `tests/test.api.example.json` to the gitignored `tests/test.api.json` and configure the caller there. This is the **API caller's config**, not the service's `config.local.json`. Static `capture_jwt_token` and `diapason_api_jwt_token` can be used instead of login credentials.

Configuration precedence matches the integration script: merged `INTEG_PLATFORM_CONFIG` + `INTEG_APP_CONFIG` environment JSON (app values win), then `SMOKE_API_CONFIG`, then an optional positional config file (or its `--config` alias), otherwise `tests/test.api.json`. Selecting a config file does not override these environment JSON values. `ACA_DEPLOY_URL`/`CAPTURE_URL` and individual M2M environment overrides still apply.

Use optional flags to override the configured PDF and trade type. For an evaluation case, choose `--output evals/responses/<case-id>` so offline grading can find the response by case ID:

```bash
uv run --locked python scripts/capture_pdf.py --pdf evals/data/loan-001.pdf --trade-type iamLoan --output evals/responses/loan-001
```

An explicit `--pdf` is relative to the current directory. Configured PDF paths use the integration script's lookup conventions: environment configuration starts from `tests/`; file configuration starts from that file's directory, with the existing repository/tests fallbacks. `--timeout` overrides the default 600-second capture timeout.

The exporter authenticates and calls `POST /api/capture` with `debug=true`. Health, catalog and missing-token smoke checks remain in `tests/test_integ.py`. The output directory must be new:

| File | Contents |
|---|---|
| `response.json` | Original HTTP response body bytes, without reformatting |
| `trade.xml` | Resolved XML returned in `trade_xml` |
| `extracted.xml` | XML sent to reference resolution, after the selected trade type is inserted |
| `model.xml` | XML from the model, before trade-type insertion |
| `model-response.txt` | Original model response, when debug data includes it |
| `run.json` | Input hash, selected type, correlation, status, timing and available model/prompt metadata |

XML/model files exist only when the response provides those values. An HTTP failure is saved too; a non-JSON HTTP body is stored as `response.body`. Existing directories are never overwritten. Exit code **0** means the capture succeeded, **1** means a capture/configuration/export failure, and **2** means invalid command-line arguments. Retain the output artifacts when investigating a failed capture.

Exported artifacts contain document-derived data. `evals/data`, `evals/responses` and `evals/runs` are gitignored; the whole `evals` directory is excluded from the service image.

## 2. Create and review ground truth

Keep the original response, review the PDF and the populated UI fields with a functional expert, then save the approved XML separately. The expected XML must describe the **Capture API boundary**. A final UI export may include defaults, internal IDs, calculated fields or manual corrections that the extractor was never expected to supply. Remove those from extraction expectations or explicitly exclude their paths.

Do not use `config/trade.xml` or an existing `temp_res*.xml` as ground truth without functional review.

Example local layout:

```text
evals/data/
  dataset.json
  loan-001.pdf
  loan-001.expected.xml
  loan-001.extracted.expected.xml   # optional
```

`dataset.json`:

```json
{
  "schema_version": 1,
  "name": "Reviewed loan contracts",
  "version": "1",
  "cases": [
    {
      "id": "loan-001",
      "pdf": "loan-001.pdf",
      "trade_type": "iamLoan",
      "expected_xml": "loan-001.expected.xml",
      "split": "dev",
      "tags": ["loan", "floating", "schedule"],
      "reviewer": "Functional reviewer",
      "notes": "Approved after checking against the PDF",
      "rules": {
        "critical_fields": ["amount1", "currency1", "maturityDate"],
        "ignore_fields": ["valueDate"],
        "reference_mode": "shortname"
      }
    }
  ]
}
```

Paths are relative to the manifest. Each successful case requires `expected_xml`. Optional `expected_extracted_xml` grades `debug.extract.trade_xml` separately; use document names in that reference, and resolved reference identifiers in `expected_xml`. Optional `extracted_rules` overrides the resolved rules for that stage. Dataset-level `rules` supply defaults; case/stage rule keys replace the corresponding defaults, including lists.

For an expected rejected document, omit XML references and provide `"expected_success": false, "expected_status": 400` (or the precisely expected status). A transport failure does not satisfy an expected HTTP rejection. HTTP 200 business failures must explicitly contain `success=false`.

Start with three jointly reviewed cases to settle field semantics, then label the remaining PDFs. Include absent/uncertain fields, multiple layouts and trade families. Reserve a separate `holdout` split for acceptance checks. Reviewer/notes are documentation; the tool does not certify that a person actually reviewed a case.

## 3. Validate or grade offline

These commands do not load API configuration, obtain tokens or make HTTP requests:

```bash
uv run --locked python scripts/evaluate.py validate evals/data/dataset.json
uv run --locked python scripts/evaluate.py score evals/data/dataset.json --responses evals/responses --output evals/runs/reviewed-baseline
```

For exported single-document runs, `--responses` contains `<case-id>/response.json` and `run.json`. It also accepts the output directory of a previous batch evaluation. Input PDF/type hashes and response hashes are checked when recorded. A manually imported `response.json` without `run.json` is allowed, assumes HTTP 200, and is explicitly counted as an **unverified input** in the report. Preserve `run.json` for reproducible measurements.

Try the committed walkthrough without VPN or credentials:

```bash
uv run --locked python scripts/evaluate.py validate evals/example/dataset.json
uv run --locked python scripts/evaluate.py score evals/example/dataset.json --responses evals/example/responses --output evals/runs/offline-example
```

The walkthrough uses a **synthetic response** and only labels the sample PDF's currency and maturity date. A passing walkthrough verifies tooling, not model quality. Other fields are deliberately unscored.

## 4. Run a batch explicitly

Once the service is reachable:

```bash
uv run --locked python scripts/evaluate.py run evals/data/dataset.json --config tests/test.api.json --split dev --repeat 3 --label baseline --output evals/runs/baseline
uv run --locked python scripts/evaluate.py run evals/data/dataset.json --config tests/test.api.json --split dev --repeat 3 --label prompt-v2 --baseline evals/runs/baseline/report.json --output evals/runs/prompt-v2
```

Each attempt makes a fresh API request, persists the capture artifacts, then grades the response. `--tag` filters cases (repeat to require multiple tags), `--split` filters the split, `--timeout` sets the HTTP timeout. No implicit retries or model calls occur in offline grading. API/business failures stay in the report and the batch continues. Invalid datasets are rejected before any request.

Batch requests use [`client.py`](client.py), which manages repeated calls and preserves failures for grading. Unlike the single-PDF exporter's integration-compatible config precedence, an explicit batch `--config` file takes priority over environment JSON. Without that flag, the batch supports the same integration environment JSON and default `tests/test.api.json`. Deployment URL and individual M2M environment overrides still apply.

The batch snapshots the manifest and records hashes of the input PDFs, approved XML and effective rules. Service health/catalog metadata and per-capture model metadata are recorded when available. The service's debug extraction includes a hash of the actual prompt text, model identifier returned by the provider, and token usage. Catalog `prompt_version` alone is not a prompt-content identifier. An older service may omit these new debug fields.

Record the tenant/reference-data version in your experiment label/notes as appropriate. This tool does not snapshot the remote reference database, freeze an Azure deployment, or infer the cost from tokens. The existing API only returns a 2,000-character PDF text preview; the exporter does not claim it contains the full extracted text.

## XML grading rules

The comparator parses XML and compares business fields. Attribute order, indentation and equivalent numeric representations do not matter. Root attributes such as `@gracePeriod` count as fields. Distinct repeated elements retain occurrence indexes; their order is significant. Namespace URIs are preserved, so a different namespace is a structural mismatch.

| Rule | Behavior |
|---|---|
| `critical_fields` | Selected fields must be correct; report critical failures separately |
| `ignore_fields` | Explicitly exclude fields/subtrees, such as UI-only defaults |
| `include_fields` | Optional partial evaluation; only selected fields/subtrees are scored |
| `numeric_fields` | Additional numeric fields to normalize with Decimal |
| `date_fields` | Additional ISO date/timestamp fields to normalize |
| `boolean_fields` | Additional boolean fields to normalize |
| `tolerances` | Optional absolute numeric tolerances by field path; default is exact |
| `reference_mode` | `shortname` (default) compares the shortname, or name if no shortname, while ignoring its internal-ID text; `strict` also compares the ID |
| `fail_on_unexpected` | Defaults to true; unexpected populated fields cause failure |

Selectors are relative to the root: `amount1`, `currency1/@shortname`, `@gracePeriod`. An element selector such as `cpty` selects its attributes and subtree. Unindexed selectors also match repeated instances. Critical/include selectors must match expected populated fields; critical fields cannot be hidden by exclusions. Unknown rule names and invalid selectors are rejected.

Standard amount/rate/date/boolean fields have built-in normalization; see [`xml_compare.py`](xml_compare.py) for the exact list. Numeric values use exact Decimal comparisons unless a field-specific tolerance is approved. Dates normalize equivalent timestamps to UTC without dropping time; date-only values mean midnight UTC and timestamps without a timezone are assumed UTC. Missing and zero remain different. Empty elements do not increase accuracy. Serialization attributes `class` and `customDictionaryName` are ignored by default.

Entity matching is exact, not fuzzy. A correct raw name and a resolved shortname require **separate stage references**. Using shortnames intentionally ignores environment-specific numeric IDs; use strict mode in a frozen tenant when ID correctness matters. Do not set `include_fields` or `ignore_fields` to hide errors merely to raise scores.

## Reports, baselines and continuous verification

Each run produces:

- `report.html`: readable summary and field differences, usable without a server.
- `report.json`: complete machine-readable results, per-stage metrics, per-trade-type summaries and provenance.
- `fields.csv`: every graded field, with expected/actual values and criticality.
- `dataset.json`: the manifest as used, plus content hashes in the report; original documents remain in your dataset store.
- `cases/<id>/run-001/...`: original artifacts for live runs.

Precision = correct / predicted populated fields. Recall = correct / expected populated fields. A wrong value counts against both. Missing or malformed output contributes missing expected fields instead of disappearing from the denominator. Precision with no predictions is undefined (`null`); consult recall and case failures too. Negative cases have behavior scores only. The report also shows critical failures, documents passing every repetition, unstable pass/fail results and median capture latency. Field counts/metrics cover only the configured grading scope.

Exit code **0** means all selected case attempts meet the approved expectations; **1** means a content/API failure or incompatible/regressed baseline; **2** means invalid input/configuration or an output-path problem. This deliberately starts with a strict gate. A high average score does not override a failing case.

Baseline comparison requires the same dataset/content/rules, case selection, attempts and stages, and a completed prior report. It lists per-case/per-field regressions and improvements, so improvements elsewhere cannot conceal a regression. A changed label or PDF changes the fingerprint. Keep ground truth changes reviewed and separate from prompt experiments. Interrupted live runs retain a partial `report.json` marked incomplete and cannot be used as baselines.

### Where and when to run evaluation

| Execution | Where | When and what it verifies |
|---|---|---|
| `pytest` | Developer machine and the existing CI | Every PR; software, XML graders and HTTP behavior with mocked dependencies, without live model calls |
| `evaluate.py validate` / `score` | Developer machine or offline CI with the dataset and saved responses | Dataset checks and reproducible grading of existing outputs; no API configuration or connectivity required |
| `evaluate.py run` | Developer machine connected to the target environment | Generate fresh outputs for prompt/model/extraction changes, compare candidates and check the held-out set before release |
| Separate live evaluation job | Manually triggered or scheduled CI runner with service connectivity, protected credentials and dataset access | Repeat the same fresh-output evaluation independently of deployment and ordinary PR checks |
| UI acceptance review | Diapason UI with a functional reviewer | Validate field population, defaults, correction effort and saving, especially before release |

**Regrading saved responses does not evaluate a new prompt or model.** It verifies the grader or recalculates results for outputs already generated. A quality comparison requires fresh outputs from the candidate service revision using the same reviewed dataset, grading rules and reference-data environment.

The current CI runs the offline suite, including evaluator and mocked-client tests. No live content-evaluation job has been configured. Add a separate job when a suitable connected runner and reviewed dataset are available; keep its reports as CI artifacts. Evaluations run against the service from outside its production container and never as part of API startup. With no VPN connection, use only offline validation, saved-response grading and tests.
