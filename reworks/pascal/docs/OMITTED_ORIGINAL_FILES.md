# Original files omitted from Pascal

The original checkout is unchanged. All original Python provenance is listed in [PYTHON_INVENTORY.md](PYTHON_INVENTORY.md). The former `app.py` is split into runtime, API and agent modules; this is relocation, not a missing application.

| Original paths | Disposition |
| --- | --- |
| `ic_prompt_loader.py`, `skills/intelligence_contract/{run,extract_xml,xml_fields}.py` | Workflow implementation belongs exclusively to Capture. Pascal retains only its HTTP relay. |
| `skills/intelligence_contract/config/**` | Source assets live in Capture's `config/`; external Blob keys are unchanged. Pascal's config deploy uploads only the system prompt. |
| `skills/__init__.py`, `skills/intelligence_contract/__init__.py` | Old internal package namespaces removed. Legacy HTTP/storage labels remain. |
| `skills/intelligence_contract/entity_match.py`, `test/test_entity_match.py` | Unused by the working original execution path; no new matching behavior introduced. |
| `test/test_{extract_trade_type,ic_catalog,xml_fields}.py` | Ported to Capture's `tests/`, where extraction now lives. |
| Original `docs/01-issues-and-risks.md` through `docs/04-intelligence-contract-design.md` | Superseded here by the current handoff, deployment instructions, sprint and inventory; retained in the original. |

Previously missing material now restored: `.github/**`, Docker/ignore/build/package files, `deploy/**` including the original provider lock, `frontend/**` including its original lockfile, `static/**`, original dashboards/generator, config example, system prompt, VERSION, `data/.gitkeep`, regression tests, sample PDF and live smoke/example under `scripts/`.

Generated `static/js/`, local virtual environments, wheel/build output, private config/keystores and Terraform state are not source deliverables. CI builds the frontend before the image.
