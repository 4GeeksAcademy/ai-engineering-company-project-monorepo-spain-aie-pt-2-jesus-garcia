# Imagen del scheduler nocturno (contexto de build: raíz del monorepo).
#
#   docker build -f scripts/Dockerfile -t trackflow/scheduler:dev .
#
# Contiene lo necesario para el script (job_runner) y para lanzar el pipeline
# como subproceso (prefect + pandas + sqlalchemy). El cron vive en
# `scripts/crontab` y lo ejecuta supercronic, que hereda el entorno del
# contenedor (a diferencia de `cron` de Debian).

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    TZ=UTC

WORKDIR /app

ARG TARGETARCH
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && case "$TARGETARCH" in \
         arm64) ARCH=arm64 ;; \
         *) ARCH=amd64 ;; \
       esac \
    && curl -fsSLo /usr/local/bin/supercronic \
         "https://github.com/aptible/supercronic/releases/download/v0.2.51/supercronic-linux-${ARCH}" \
    && chmod +x /usr/local/bin/supercronic \
    && apt-get purge -y curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "prefect>=3,<4" \
    "pandas>=2" \
    "SQLAlchemy>=2" \
    "sqlmodel" \
    "psycopg2-binary" \
    "python-dotenv" \
    "httpx"

COPY services/__init__.py ./services/__init__.py
COPY services/job_runner ./services/job_runner
COPY scripts ./scripts
COPY pipelines ./pipelines
COPY data/pipelines ./data/pipelines

# `-passthrough-logs`: la salida del job va directa a `docker compose logs`.
CMD ["supercronic", "-passthrough-logs", "/app/scripts/crontab"]
