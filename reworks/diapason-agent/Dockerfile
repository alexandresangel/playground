# Build from this directory after extracting it as a standalone repository.
# Resolved and built on 2026-09-07. Refresh digests through a tested dependency PR.
ARG NODE_IMAGE=node:22-bookworm-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5
ARG PYTHON_IMAGE=python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254
FROM ${NODE_IMAGE} AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.9.0@sha256:8f926a80debadba6f18442030df316c0e2b28d6af62d1292fb44b1c874173dc0 AS uv
FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 TIKTOKEN_CACHE_DIR=/app/tokenizer-cache
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src/ src/
RUN uv sync --locked --no-dev --no-editable \
    && .venv/bin/python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')" \
    && .venv/bin/python -c "import pascal.main"

FROM build AS test
RUN uv sync --locked --extra dev --no-editable
COPY tests/ tests/
COPY scripts/ scripts/
COPY evaluation/ evaluation/
RUN .venv/bin/pytest

FROM ${PYTHON_IMAGE} AS runtime
WORKDIR /app
ARG APP_VERSION=0.1.0
ARG GIT_REVISION=unknown
ENV APP_VERSION=${APP_VERSION} APP_REVISION=${GIT_REVISION} \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=8000 PASCAL_ROOT=/app \
    TIKTOKEN_CACHE_DIR=/app/tokenizer-cache PATH=/app/.venv/bin:$PATH
LABEL org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_REVISION}"
RUN groupadd --gid 10001 pascal && useradd --uid 10001 --gid pascal --no-create-home pascal \
    && mkdir /app/data && chown pascal:pascal /app/data
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/tokenizer-cache /app/tokenizer-cache
COPY static/ static/
COPY --from=frontend /build/static/js/ static/js/
COPY system_prompt.md VERSION ./
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["sh", "-c", "exec uvicorn pascal.main:create_app --factory --host 0.0.0.0 --port ${PORT} --no-access-log --timeout-graceful-shutdown 30"]
