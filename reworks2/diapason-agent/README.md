# Diapason-agent / Pascal

The existing Pascal chat application with a readable LangGraph model/tool loop shared by JSON and SSE.

```text
src/pascal/
  agent/          # graph, service, prompt/history context, tool routing/discovery/calls
  api/            # chat, sessions, auth, health, extraction compatibility, schemas
  observability/  # content-free AI spans and request correlation
  company/        # unchanged JWT, MCP, storage, config, sources, telemetry
  compat/capture/ # existing upload execution until the separate ACA is wired
  runtime.py      # compose the existing company dependencies
  application.py  # assemble FastAPI, static mount and routers
  asgi.py         # five-line Uvicorn entry point
frontend/         # original frontend sources, unchanged
static/           # original host assets, unchanged
tests/            # offline graph, HTTP/SSE, security and company characterization
docs/             # sprint, inventory, omissions and handoff
pyproject.toml
Dockerfile
```

Start in [agent/graph.py](src/pascal/agent/graph.py). `ChatState` and the model/tools/finish nodes own the loop. `service.py` adapts graph results to the existing chat behavior; `context.py` prepares prompts/history; `routing.py`, `discovery.py` and `mcp.py` retain dynamic per-request company tool handling. No planner, global tool catalog, new memory or checkpointing is introduced.

The former large `app.py` is split across `api/`, `agent/`, `observability/` and dependency assembly. All original HTTP routes, auth dependencies, Pydantic schemas, SSE events/headers, session behavior, frontend/static assets, prompts and configuration remain. Required legacy route and session names remain too.

`compat/capture/` is a temporary local extraction implementation, because the original frontend still posts uploads to Pascal. It has the same workflow logic as standalone Capture, with package imports adjusted. Remove it after the company provides cross-service routing and Capture tool exposure. Pascal contains no copy of Capture's catalog/prompt source assets; the existing loader still uses Blob.

## Develop and run

Use Python 3.12+ from this project directory, in its own virtual environment:

```console
python -m pip install -r requirements-dev.txt
python -B -m pytest -q
python -m uvicorn pascal.asgi:app --host 0.0.0.0 --port 8000
```

Supply the existing `CHAT_CONFIG` or root `config.json`, keystore and Blob/model configuration. The launch directory is the service root, where `VERSION`, local config and keystore paths remain. `pyproject.toml` owns dependencies; `requirements.txt` installs this package in editable mode. A regular wheel is also supported: `python -m pip wheel --no-deps . -w dist`.

All runtime Python is physically under `src/pascal/`. The `company/` directory stores unchanged source files; setuptools maps them to their original public module names, including the byte-identical `dia_jwt/` package. No import aliases or runtime path manipulation are used. Install the projects separately because these public company module names intentionally overlap.

`docker build -t <image-name> .` uses this directory alone. The Dockerfile launches `pascal.asgi:app`; existing Python image, port/build metadata and runtime configuration conventions remain. Build the unchanged frontend with its existing `npm ci` / `npm run build` commands when the host needs its generated static bundle.

The single original AzureOpenAI client is retained until the actual deployment's Azure v1 compatibility can be verified. No alternate SDK mode or replacement model is configured. Known original refresh behavior and external integration work are explicit in [handoff](docs/HANDOFF.md).

[Stories and tasks](docs/SPRINT.md) | [Every Python file](docs/PYTHON_INVENTORY.md) | [Original omissions](docs/OMITTED_ORIGINAL_FILES.md)
