# Build context: raíz del monorepo
#   docker build -f pipelines/weekly_performance/Dockerfile \
#     -t trackflow/weekly-performance:dev .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN pip install --no-cache-dir \
    "prefect>=3,<4" \
    "pandas>=2" \
    "SQLAlchemy>=2" \
    "psycopg2-binary" \
    "python-dotenv" \
    "httpx"

COPY pipelines ./pipelines
COPY pipelines/weekly_performance/prefect.yaml ./prefect.yaml

# El worker de Prefect se lanza aparte; este CMD permite ejecutar por script.
CMD ["python", "-m", "pipelines.weekly_performance", "run"]
