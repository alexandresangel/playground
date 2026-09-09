# Intentional duplication and source layout

Decision: 2026-09-09. Common code is kept as ordinary local source in each application, not as a
shared package or generated copy. Capture has one package, `src/capture`; Pascal has one package,
`src/pascal`. Each app builds/tests independently, with no dependency on its sibling or this workspace.

## Matching paths

The following five files are intentionally byte-identical across the two apps at this revision.
Paths are relative to each application's package root:

| Path in both packages | Responsibility |
|---|---|
| adapters/azure_openai.py | Azure client configuration, authentication and client ownership |
| adapters/blob.py | Blob credentials and read-service helpers |
| adapters/diapason.py | Direct Diapason REST resolution and response parsing |
| api/guards.py | ASGI payload limits and response/correlation headers |
| observability/telemetry.py | OTLP logs, traces, metrics and safe operation spans |

For example, import `capture.observability.telemetry` in Capture and
`pascal.observability.telemetry` in Pascal. There is no additional integration namespace.
Pascal retains the REST helper for reuse but does not invoke it to bypass its MCP tools.
Capture still calls the REST resolver directly and never calls an MCP tool.

## Maintaining copies

When changing one of these files, review its counterpart and apply the same common change manually.
Run each application's adapter/telemetry and full regression tests. Record intentional divergence
here if requirements ever differ. There is no canonical copy, sync script, generated-file warning,
hash manifest, cross-repository test requirement or release coupling. Normal app dependency locks
and Capture's original prompt/catalog provenance manifest are unrelated and remain in place.

Model-message adapters, business graphs, event fields, authentication policy, prompts and session
storage remain app-specific; similar names alone do not imply those files must be identical.
Telemetry scope names, signal settings and public contracts remain stable for Loki/Tempo compatibility.

## Folder rule

Group related work, not every architectural label. Capture uses four folders: `workflow` combines
extraction helpers, graph nodes/state/ports and execution service; `adapters` groups external clients;
`api` groups HTTP/MCP and guards; `observability` groups event definitions and telemetry.
Its small `auth.py`, `compatibility.py`, `config.py` and `build_info.py` stay at the root.
Pascal keeps its meaningful multi-module agent, MCP, tools and security groups; its single
compatibility module likewise stays at the root. No one-file folder is created solely to name a layer.
