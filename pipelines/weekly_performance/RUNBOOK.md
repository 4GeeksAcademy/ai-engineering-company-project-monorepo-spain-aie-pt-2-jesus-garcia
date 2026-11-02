# RUNBOOK — Pipeline semanal de desempeño

Procedimientos operativos. Todos los comandos se ejecutan desde la raíz del
monorepo con el entorno del pipeline (`DATABASE_URL_PIPELINE` configurada).

## 1. Una corrida falló

```bash
# Ver el estado y el error
python -m pipelines.weekly_performance run --week 2026-07-13 --json

# Si el fallo fue transitorio, reintentar
python -m pipelines.weekly_performance backfill --week 2026-07-13
```

Revisar `reporting.pipeline_runs` (`status`, `error_message`) y
`reporting.pipeline_run_steps` para localizar la etapa que falló.

## 2. Semana vacía (`empty_week`)

Es normal si no hubo actividad. Si debería haber datos:

1. Comprobar que `telemetry_events` tiene los 4 `event_type` de esa semana.
2. Ejecutar la reconciliación de origen:

```bash
python -m pipelines.weekly_performance reconcile-source --days 14 --json
```

3. Si hay órdenes sin eventos, revisar el relay del outbox:

```bash
python -m pipelines.weekly_performance relay --batch-size 500 --json
```

## 3. Tasa de rechazo alta

```bash
python -m pipelines.weekly_performance backfill --week 2026-07-13 --json
```

- `> 1 %`: advertencia; revisar `weekly_performance_rejects.reason`.
- `> 5 %` y muestra ≥ 50 filas: bloqueante. Corregir la fuente antes de
  reintentar; no forzar la publicación.

## 4. Backfill de una semana congelada

```bash
python -m pipelines.weekly_performance backfill --week 2026-07-13 \
  --force --reason "evento tardío validado por Ana"
```

Esto guarda un snapshot en `reporting.weekly_performance_revisions` con el
estado anterior, el motivo y quién lo forzó.

## 5. Replay de cuarentena

```bash
python -m pipelines.weekly_performance replay --run-id <uuid>
```

Reprocesa la semana de esa corrida y marca los rechazos como rejugados. Si los
eventos siguen inválidos, volverán a cuarentena: corregir el origen primero.

## 6. Lock colgado

El advisory lock se libera al cerrar la conexión. Si un worker murió y el lock
sigue tomado:

```sql
-- identificar la sesión
select pid, state, query from pg_stat_activity
where query like '%pg_try_advisory_lock%';

-- terminarla (con cuidado)
select pg_terminate_backend(<pid>);
```

Después, el watchdog marca la corrida zombie como `failed`:

```bash
python -m pipelines.weekly_performance watchdog --json
```

## 7. Circuit breaker abierto

Tras 3 fallos consecutivos de `extract`, el pipeline bloquea nuevas corridas con
`source_unavailable`. Cuando la fuente esté recuperada:

```bash
python -m pipelines.weekly_performance backfill --week 2026-07-13 \
  --force --reason "fuente recuperada"
```

## 8. Prefect server caído

```bash
docker compose --profile prefect up -d prefect-server prefect-init prefect-deploy prefect-worker
```

El worker reintenta la conexión. La API de reporte sigue sirviendo el último
snapshot (`stale: true` si la última corrida falló).

## 9. Alertas

Configurar `PIPELINE_ALERT_WEBHOOK` con un webhook compatible con Slack/Teams
(campo `text`). Sin webhook, las alertas solo quedan en el log.
