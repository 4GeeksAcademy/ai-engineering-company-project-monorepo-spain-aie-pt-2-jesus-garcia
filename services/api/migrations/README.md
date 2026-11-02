# Migraciones SQL — TrackFlow API

Migraciones aditivas e idempotentes. Se aplican **después de un backup** y por
conexión directa o session pooler (puerto 5432), nunca por el transaction pooler
(6543).

## 0001_g1_g4.sql

- G1: `ops.telemetry_outbox`.
- G2: `sku.client_id` (nullable hasta que exista el mapeo).
- G3: `sku.min_stock` (nullable; `0` es un umbral explícito).
- G4: `inventory_discrepancy` + snapshot `client_id` en `stock_entry`/`stock_exit`.

## 0002_job_runs.sql

- Tabla `public.job_runs`: ciclo de vida de los procesos en segundo plano
  (`pending` → `processing` → `completed` | `failed`).
- Índice `ix_job_runs_job_target` en (`job_name`, `target_date`) para las
  consultas de idempotencia.
- Índices parciales únicos que refuerzan en BD el lock (`ux_job_runs_processing`,
  un solo `processing` por job) y la idempotencia (`ux_job_runs_completed`, un
  solo `completed` por job y día).
- `ck_job_runs_status` restringe los valores permitidos.

No se fusiona con `reporting.pipeline_runs`: capas distintas (intento de disparo
diario vs. ejecución semanal del pipeline).

## Aplicar en producción

```bash
# 1. backup
pg_dump "$SUPABASE_DB_URL_DIRECT" \
  --format=custom --no-owner --no-privileges \
  --file="/ruta/segura/supabase-$(date +%Y%m%d-%H%M).dump"

# 2. verificar backup
pg_restore --list "/ruta/segura/supabase-....dump" > /dev/null

# 3. aplicar en transacción (el SQL ya incluye begin/commit)
psql "$SUPABASE_DB_URL_DIRECT" -v ON_ERROR_STOP=1 \
  -f services/api/migrations/0001_g1_g4.sql

# 4. verificar
psql "$SUPABASE_DB_URL_DIRECT" -c "\d public.sku"
psql "$SUPABASE_DB_URL_DIRECT" -c "\d public.inventory_discrepancy"
```

## Aplicar 0002 (job_runs)

```bash
# 1. backup (mismo procedimiento que 0001)
pg_dump "$SUPABASE_DB_URL_DIRECT" \
  --format=custom --no-owner --no-privileges \
  --file="/ruta/segura/supabase-$(date +%Y%m%d-%H%M).dump"
pg_restore --list "/ruta/segura/supabase-....dump" > /dev/null

# 2. aplicar (idempotente: se puede repetir)
psql "$SUPABASE_DB_URL_DIRECT" -v ON_ERROR_STOP=1 \
  -f services/api/migrations/0002_job_runs.sql

# 3. verificar
psql "$SUPABASE_DB_URL_DIRECT" -c "\d public.job_runs"
psql "$SUPABASE_DB_URL_DIRECT" -c "select indexname from pg_indexes where tablename = 'job_runs';"
```

Rollback de 0002 (solo si es imprescindible):

```sql
drop table if exists public.job_runs;
```

## Rollback

La migración es aditiva. Para revertir (solo si es imprescindible):

```sql
drop table if exists public.inventory_discrepancy;
alter table public.sku drop column if exists min_stock;
alter table public.sku drop column if exists client_id;
alter table public.stock_entry drop column if exists client_id;
alter table public.stock_exit drop column if exists client_id;
-- ops.telemetry_outbox se conserva: es infraestructura del outbox.
```

## Mapeo SKU → cliente / min_stock

No forma parte de la migración. Cuando exista:

```bash
python services/api/import_sku_mapping.py \
  --file services/api/data/sku_mapping.csv \
  --dry-run
python services/api/import_sku_mapping.py \
  --file services/api/data/sku_mapping.csv \
  --allow-remote-db
```

Después, fijar `PIPELINE_INSTRUMENTATION_SINCE` y ejecutar el backfill de las
semanas afectadas.
