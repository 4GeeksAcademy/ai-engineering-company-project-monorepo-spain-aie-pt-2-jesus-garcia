# Carpeta `scripts`

Esta carpeta contiene **scripts auxiliares** del monorepo: automatizaciones de desarrollo, utilidades de mantenimiento, tareas repetitivas (setup, lint, migraciones, generación de datos, etc.) y tooling interno.

- **Propósito principal**: agrupar herramientas de soporte que no pertenecen a una app/agente/pipeline específico, pero facilitan el trabajo del equipo.
- **Recomendación**: documenta cada script (qué hace, parámetros, requisitos, ejemplos de uso) y procura que sean reproducibles (y seguros) en distintos entornos.

> _Versión en inglés: [README.md](./README.md)._

## `nightly_export.py` — export nocturno de telemetría + disparo del pipeline

Proceso diario en segundo plano: guarda un snapshot del día UTC anterior de
`telemetry_events` en `data/raw/telemetry_<YYYY-MM-DD>.csv` (solo si el archivo
no existe) y después lanza el pipeline de desempeño como subproceso
(`python data/pipelines/pipeline.py run --lookback 1 --json`).

Cada intento es una fila de `job_runs`, y la fila es la fuente de verdad:

```
pending → processing → completed
                    ↘ failed
```

- `pending` se crea **antes** de cualquier trabajo.
- `processing` se confirma **antes** de empezar el export.
- `completed` solo tras exportar y terminar el pipeline con éxito.
- `failed` guarda el diagnóstico en `error_message`.
- Lock vía `processing` (una ejecución por job) e idempotencia vía
  (`job_name`, `target_date`) (una ejecución completada por día).
- Las filas `processing` huérfanas (proceso muerto) se reconcilian a `failed`
  antes de comprobar el lock: un crash nunca bloquea el job para siempre.

### Uso

```bash
python scripts/nightly_export.py                    # ayer (UTC)
TARGET_DATE=2026-10-29 python scripts/nightly_export.py
python scripts/nightly_export.py --target-date 2026-10-29
python scripts/nightly_export.py --dry-run          # muestra el plan sin escribir
python scripts/nightly_export.py --reconcile-only   # solo recupera huérfanos
```

Exit codes: `0` completed / skipped / blocked · `1` failed · `2` error de configuración.

### Variables de entorno

| Variable | Defecto | Significado |
|---|---|---|
| `DATABASE_URL` (o `JOB_DATABASE_URL`) | — | BD donde vive `job_runs` (la misma que la API) |
| `DATABASE_URL_PIPELINE` | `DATABASE_URL` | BD que lee el pipeline |
| `TARGET_DATE` | ayer UTC | Día a exportar (`YYYY-MM-DD`) |
| `JOB_STALE_MINUTES` | `60` | Antigüedad tras la que un `processing` es huérfano |
| `PIPELINE_TIMEOUT_SECONDS` | `1800` | Timeout del subproceso |
| `LOG_LEVEL` | `INFO` | Nivel de log |

### Disparador (cron)

`scripts/crontab` lo ejecuta supercronic dentro del contenedor `scheduler`:

```
CRON_TZ=UTC
15 2 * * * python /app/scripts/nightly_export.py
```

02:15 UTC porque el día UTC ya cerró a las 00:00 y hay margen para la ingesta de
telemetría; granularidad diaria porque `target_date` es diario. El job **no** se
programa dentro de FastAPI (sin APScheduler ni hooks de lifespan).

```bash
docker compose up -d scheduler
docker compose logs -f scheduler
docker compose run --rm -e TARGET_DATE=2026-10-29 scheduler python /app/scripts/nightly_export.py
```

El crontab del host queda solo como alternativa local sin Docker:

```cron
15 2 * * * cd /ruta/al/repo && services/api/venv/bin/python scripts/nightly_export.py
```

### Tests

```bash
services/api/venv/bin/python -m pytest tests/jobs -q
```

### Logs

Una línea por evento, con timestamp UTC, job y estado resultante:

```
2026-10-30T02:15:03Z level=INFO job=nightly_export status=pending target_date=2026-10-29 run_id=42 msg="registro creado antes de empezar el trabajo"
2026-10-30T02:15:04Z level=INFO job=nightly_export status=processing target_date=2026-10-29 run_id=42 msg="trabajo iniciado"
2026-10-30T02:15:22Z level=INFO job=nightly_export status=completed target_date=2026-10-29 run_id=42 rows=1843 pipeline_rc=0 msg="export + pipeline OK"
```
