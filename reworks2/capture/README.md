# Capture

Dedicated intelligence-contract workflow service for its own Azure Container App. The AI path is `validate -> extract XML -> resolve references -> result` in LangGraph.

```text
src/capture/
  workflow/       # graph, PDF/XML extraction, prompt/catalog loader
  api/            # extraction, company auth, health, HTTP middleware/schemas
  observability/  # content-free AI spans and request correlation
  company/        # unchanged JWT, MCP, storage, config, telemetry implementations
  runtime.py      # compose the existing company dependencies
  application.py  # assemble FastAPI and routers
  asgi.py         # five-line Uvicorn entry point
config/           # original catalog, XML and prompt assets for the existing Blob keys
tests/            # offline workflow, contract and security tests
docs/             # sprint, inventory, omissions and handoff
pyproject.toml
Dockerfile
```

Start in [workflow/graph.py](src/capture/workflow/graph.py). `CaptureState` and four named stages make the extraction order explicit. `extract_xml.py` retains the original PDF/model/XML processing; `prompts.py` retains the existing Blob catalog/cache conventions. No OCR, matching, XML repair, new model parameters or checkpointing was added.

Capture contains no Pascal UI, persona/system prompt, chart code, chat loop, tool-discovery UI or session CRUD routes. It still persists extraction turns and artifacts using the existing session interface, and uses existing locales for those messages. This is why storage and locale company files remain. Unused company helper functions are left intact inside byte-preserved files.

The existing GET/POST `/api/skills/intelligence-contract` contract, explicit `trade_type`, auth routes, JWT dependencies, identity forwarding, results and `X-Diapason-Chat-Session` header remain. `/health` and `/api/health` return build health; `/api/refresh-prompt` refreshes only the Capture catalog. These operational endpoints deliberately no longer depend on Pascal's system prompt. Classic/Pascal UI lives in its existing host; external routing to this ACA remains a handoff task.

For a future workflow, use the same separation: business state and stages in `workflow/`, HTTP mapping in `api/`, dependency assembly in `runtime.py`, content-free spans in `observability/`, and offline behavior tests in `tests/`. Add folders only when the workflow needs them. Company interfaces are integration boundaries, not template code to rewrite.

## Develop and run

Use Python 3.12+ from this project directory, in its own virtual environment:

```console
python -m pip install -r requirements-dev.txt
python -B -m pytest -q
python -m uvicorn capture.asgi:app --host 0.0.0.0 --port 8000
```

Supply the existing `CHAT_CONFIG` or root `config.json`, keystore and Blob/model configuration. The launch directory is the service root, where `VERSION`, local config and keystore paths remain. `pyproject.toml` owns dependencies; `requirements.txt` installs this package in editable mode. A regular wheel is also supported: `python -m pip wheel --no-deps . -w dist`.

All runtime Python is physically under `src/capture/`. The `company/` directory stores unchanged source files; setuptools maps them to their original public module names, including the byte-identical `dia_jwt/` package. No import aliases or runtime path manipulation are used. Install the projects separately because these public company module names intentionally overlap.

`docker build -t <image-name> .` uses this directory alone. The Dockerfile launches `capture.asgi:app`; existing Python image, port/build metadata and runtime configuration conventions remain. Local `config/` assets are source material for the existing Blob keys, not an alternate runtime prompt loader.

The single original AzureOpenAI client is retained until the actual deployment's Azure v1 compatibility can be verified. No alternate SDK mode or replacement model is configured. Known original refresh behavior and external integration work are explicit in [handoff](docs/HANDOFF.md).

[Stories and tasks](docs/SPRINT.md) | [Every Python file](docs/PYTHON_INVENTORY.md) | [Original omissions](docs/OMITTED_ORIGINAL_FILES.md)
