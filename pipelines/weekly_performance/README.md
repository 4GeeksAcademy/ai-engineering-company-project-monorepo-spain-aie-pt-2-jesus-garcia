# `weekly_performance` — Pipeline semanal de desempeño

Implementación del pipeline descrito en
[`docs/pipeline/PIPELINE_2_PLAN.md`](../../docs/pipeline/PIPELINE_2_PLAN.md)
(Fases 0 y 1): lee `telemetry_events` en modo solo lectura, agrega por
`warehouse × client_id × week_start` y escribe en
`reporting.weekly_warehouse_client_performance`.

## Estructura

```
pipelines/weekly_performance/
  settings.py   # env vars y constantes de negocio
  db.py         # engine SQLAlchemy (PostgreSQL en prod, SQLite en tests)
  schema.py     # tablas (portables PostgreSQL/SQLite)
  sql.py        # DDL idempotente y utilidades de esquema
  core.py       # lógica pura: ventana, extract, normalize, aggregate, load
  tasks.py      # tasks de Prefect (retries solo para errores transitorios)
  flow.py       # flow padre + subflow process_week
  cli.py        # ejecución por script (run / backfill)
  tests/        # unitarios, integración SQLite y smoke del flow
```

La lógica de negocio está en `core.py` y no importa Prefect: los tests unitarios
no necesitan servidor. `tasks.py` y `flow.py` son la capa de orquestación.

## Variables de entorno

| Variable | Uso | Default |
|---|---|---|
| `DATABASE_URL_PIPELINE` | BD del pipeline (rol de solo lectura sobre `telemetry_events`) | — |
| `DATABASE_URL` | Fallback local si no existe la anterior | — |
| `PIPELINE_LOOKBACK_WEEKS` | Semanas cerradas a recalcular | `3` |
| `PIPELINE_REPORTING_SCHEMA` | Esquema destino | `reporting` |
| `PIPELINE_OPS_SCHEMA` | Esquema del outbox | `ops` |
| `PIPELINE_INSTRUMENTATION_SINCE` | Fecha desde la que existen quiebres/discrepancias | vacío |

## Ejecución por script

```bash
# desde la raíz del monorepo, con el venv que tenga las deps del pipeline
python -m pipelines.weekly_performance run --lookback 3
python -m pipelines.weekly_performance backfill --week 2026-07-13
python -m pipelines.weekly_performance backfill --week 2026-07-13 \
  --force --reason "evento tardío corregido"
python -m pipelines.weekly_performance run --dry-run --json
```

Códigos de salida: `0` éxito/skip, `1` alguna semana falló, `2` error de
configuración (argparse).

## Ejecución con Prefect

```bash
python -c "from pipelines.weekly_performance.flow import weekly_flow; weekly_flow()"
```

El flow padre procesa la última semana cerrada y el lookback; cada semana es un
subflow aislado. El deployment y el worker self-hosted llegan en la fase de
orquestación.

## Tests

```bash
# SQLite, sin Supabase ni Docker
services/api/venv/bin/python -m pytest pipelines/weekly_performance/tests -q
```

Los tests cubren:

- fronteras de semana ISO (incluido cambio de año);
- normalización, dedupe por `event_id` y cuarentena;
- agregación contra totales conocidos;
- idempotencia del upsert y `reconcile_week`;
- skip por fingerprint y semana congelada;
- gates de calidad;
- smoke del flow de Prefect.

## Decisiones aplicadas

- **D1:** throughput con `count(distinct coalesce(order_id, event_id))`.
- **D2:** un evento de discrepancia por pedido; el pipeline rechaza
  discrepancias sin `order_id`.
- **D6:** `instrumentation_since` limita el gate de cobertura.

## Fuera de alcance (siguientes fases)

- Instrumentación de origen (outbox, `client_id`, `min_stock`, endpoint de
  discrepancias).
- Prefect self-hosted, watchdog, DLQ y congelación operativa completa.
- API `/reporting/*` y backoffice.
