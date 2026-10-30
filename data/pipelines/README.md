# `data/pipelines` folder

This folder groups **all data pipelines in the monorepo** related to the company: ingestion, ETL/ELT, cleaning, transformation, and loading into analytical or production systems.

Each subfolder or file under `data/pipelines/` should represent **one pipeline or job set** (for example `sales-etl`, `telemetry-stream`, `customer-segmentation`) and include the required configuration (scripts, orchestration, connectors, schemas, etc.).

- **Main purpose**: consolidate in one place the data movement and transformation logic that powers the company’s applications and analytics.
- **Recommendation**: document pipelines as you add them—their goal, data sources and sinks, dependencies, and how to run them in development, testing, and production.

## Pipeline de desempeño de negocio

Entrypoint de entrega: [`pipeline.py`](./pipeline.py). La implementación vive en
`pipelines/weekly_performance/` y escribe en `reporting.*` a partir de
`telemetry_events` (solo lectura).

```bash
python data/pipelines/pipeline.py run --lookback 3
python data/pipelines/pipeline.py backfill --week 2026-07-13
python data/pipelines/pipeline.py reconcile-source --days 7
```

Documentación completa: [`pipelines/weekly_performance/README.md`](../../pipelines/weekly_performance/README.md).

> _Spanish version: [README.es.md](./README.es.md)._
