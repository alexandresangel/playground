FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /bin/uv

WORKDIR /app

ARG APP_VERSION=0.0.0
ARG GIT_REVISION=unknown

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV UV_PYTHON_DOWNLOADS=0
ENV PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project --no-cache

# Runtime secrets: CHAT_CONFIG + JWT_KEYSTORE_P12_B64 (not baked into the image).
COPY . .
# Bundle the complete catalog/prompts directory for direct reads in ACA.
COPY config/ ./config/
RUN uv sync --locked --no-dev --no-editable --no-cache
RUN mkdir -p data
RUN printf '%s\n' "{\"version\":\"${APP_VERSION}\",\"revision\":\"${GIT_REVISION}\"}" \
    > /app/build-info.json

LABEL org.opencontainers.image.version="${APP_VERSION}"
LABEL org.opencontainers.image.revision="${GIT_REVISION}"

EXPOSE 8000

ENV PYTHONUNBUFFERED=1
ENV PORT=8000

CMD ["sh", "-c", "exec uvicorn capture.asgi:app --host 0.0.0.0 --port ${PORT}"]
