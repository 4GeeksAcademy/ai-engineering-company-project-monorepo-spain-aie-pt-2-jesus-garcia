# `services/reporting` — API de desempeño semanal

Módulo de solo lectura sobre el esquema `reporting` que escribe el pipeline
([`data/pipelines/pipeline.py`](../../data/pipelines/pipeline.py)). Se importa
desde la API como `services.reporting` (la raíz del monorepo está en
`PYTHONPATH`).

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/reporting/weekly-warehouse-client-performance?week_start=YYYY-MM-DD` | Semana solicitada o la última calculada |
| GET | `/reporting/pipeline-runs/latest` | Estado y metadata de la última corrida |
| POST | `/reporting/pipeline-runs` | Dispara una corrida manual (`202`; `409` si hay una en curso; `503` si Prefect no responde) |

Todos requieren rol `manager`/`admin`.

## Estructura

```
services/reporting/
  router.py          # endpoints FastAPI
  schemas.py         # response models
  service.py         # consultas SQL de solo lectura
  prefect_client.py  # httpx contra la API de Prefect
```

## Variables

- `PREFECT_API_URL` — servidor Prefect self-hosted o Cloud.
- `PREFECT_API_KEY` — opcional.
