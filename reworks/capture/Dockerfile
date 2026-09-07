FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    OTEL_SERVICE_NAME=capture

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system --gid 10001 capture \
    && adduser --system --uid 10001 --ingroup capture --home /app capture

COPY pyproject.toml requirements.txt README.md ./
COPY src ./src
COPY config ./config
RUN pip install --no-cache-dir . \
    && mkdir -p /app/data \
    && chown -R capture:capture /app

ARG APP_VERSION=0.0.0
ARG GIT_REVISION=unknown
RUN printf '%s\n' "{\"version\":\"${APP_VERSION}\",\"revision\":\"${GIT_REVISION}\"}" \
    > /app/build-info.json \
    && chown capture:capture /app/build-info.json

LABEL org.opencontainers.image.version="${APP_VERSION}"
LABEL org.opencontainers.image.revision="${GIT_REVISION}"

USER 10001:10001
EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn capture.asgi:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]

