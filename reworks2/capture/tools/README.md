# Local development tools

The [project README](../README.md) is the complete developer runbook, with Linux
commands and three sections:

1. [Project documentation and Python setup](../README.md#1-project-documentation).
2. [Local Capture with real cloud services](../README.md#2-local-execution-with-real-cloud-services): configuration, Azure access, local keystore/JWT, Diapason login and extraction.
3. [Local Capture with dummy services](../README.md#3-local-execution-with-dummy-services): Azurite installation, startup, fixtures, inspection and recreation.

The third section explicitly distinguishes the **committed**
`azurite/package.json` and `azurite/package-lock.json` from generated
`azurite/node_modules/` and `.local/azurite/`. Only the manifest/lockfile and our
tooling/configuration source belong in Git; the generated installation/data do not.

`bootstrap.py` prepares local assets and launches the production ASGI app in a
separate process with explicit configuration. `stubs.py` serves configurable
model/MCP responses; `smoke.py` exercises Capture over HTTP. These utilities use
no runtime monkey-patching and are excluded from the production image/wheel.

See [CHANGES.md](CHANGES.md) for the complete edit inventory and verification record.
