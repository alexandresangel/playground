# Python inventories

Every delivered project runtime/test file is classified with its original path and purpose:

- [Capture](capture/docs/PYTHON_INVENTORY.md) and [omissions](capture/docs/OMITTED_ORIGINAL_FILES.md).
- [Pascal](diapason-agent/docs/PYTHON_INVENTORY.md) and [omissions](diapason-agent/docs/OMITTED_ORIGINAL_FILES.md).

`verify_boundaries.py` is **NEW** migration-only, read-only audit tooling (no original equivalent). It checks original-file hashes, company copies, retained route/schema/helper behavior, extraction parity after declared changes, prompt assets and the source layout. It does not copy or synchronize files and neither project depends on it. `original-sha256.json` records all 90 original files.

Ignored verification environments/build outputs/scratch under `reworks` are not project source deliverables.
