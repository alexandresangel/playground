# Build from this directory; no neighboring project or secret files are needed.
ARG PYTHON_IMAGE=python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254
FROM ghcr.io/astral-sh/uv:0.9.0@sha256:8f926a80debadba6f18442030df316c0e2b28d6af62d1292fb44b1c874173dc0 AS uv
FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src/ src/
# Base application imports without installing the optional MCP server.
RUN uv sync --locked --no-dev --no-editable \
    && .venv/bin/python -c "import importlib.util; import capture.main; assert importlib.util.find_spec('mcp') is None"
RUN uv sync --locked --no-dev --extra mcp --no-editable

FROM build AS test
RUN uv sync --locked --extra dev --extra mcp --no-editable
COPY tests/ tests/
COPY scripts/ scripts/
COPY config/ config/
RUN .venv/bin/pytest

FROM ${PYTHON_IMAGE} AS runtime
WORKDIR /app
ARG APP_VERSION=0.1.0
ARG GIT_REVISION=unknown
ENV APP_VERSION=${APP_VERSION} APP_REVISION=${GIT_REVISION} \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=8000 CAPTURE_ROOT=/app \
    OTEL_SERVICE_NAME=capture PATH=/app/.venv/bin:$PATH
LABEL org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_REVISION}"
RUN groupadd --gid 10001 capture && useradd --uid 10001 --gid capture --no-create-home capture \
    && mkdir /app/data && chown capture:capture /app/data
COPY --from=build /app/.venv /app/.venv
COPY config/ config/
COPY VERSION ./
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["sh", "-c", "exec uvicorn capture.main:create_app --factory --host 0.0.0.0 --port ${PORT} --no-access-log --timeout-graceful-shutdown 30"]
