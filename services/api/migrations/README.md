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

## 0003_dead_letter_tasks.sql

- Tabla `public.dead_letter_tasks`: tareas Celery que agotaron sus reintentos.
- Columnas: `task_id` (único), `task_name`, `attempts`, `max_retries`,
  `error_message`, `created_at`.
- Índice único `ux_dead_letter_tasks_task_id`.

El worker también crea la tabla con `SQLModel.metadata.create_all` al arrancar;
la migración es la vía explícita para entornos donde no se quiera depender de
`create_all`.

## 0004_agent_memory.sql

- Tablas `agent_memory_entries`, `agent_memory_proposals` y `agent_memory_audit`.
- **Store separado del RAG**: no crea ni modifica colecciones de Qdrant ni la
  base de conocimiento (`trackflow_knowledge`).
- Índice único parcial `ux_agent_memory_active_scope`: una sola entrada activa
  por `scope_key`; las correcciones superseden la anterior y conservan versión.
- Índice único parcial `ux_agent_memory_pending_user`: una sola propuesta
  pendiente por usuario.
- Checks de tipo de memoria, alcance y estado.
- `agent_memory_audit` es append-only: propuestas, decisiones, bloqueos,
  expiraciones, supersesiones y retiradas.

Rollback:

```sql
drop table if exists public.agent_memory_audit;
drop table if exists public.agent_memory_proposals;
drop table if exists public.agent_memory_entries;
```

La API crea estas tablas en SQLite/tests con
`app.agent.memory.models.create_agent_memory_tables`; la migración es la vía
explícita para PostgreSQL/Supabase.

```bash
# 1. backup (mismo procedimiento que 0001)
pg_dump "$SUPABASE_DB_URL_DIRECT" \
  --format=custom --no-owner --no-privileges \
  --file="/ruta/segura/supabase-$(date +%Y%m%d-%H%M).dump"
pg_restore --list "/ruta/segura/supabase-....dump" > /dev/null

# 2. aplicar (idempotente)
psql "$SUPABASE_DB_URL_DIRECT" -v ON_ERROR_STOP=1 \
  -f services/api/migrations/0003_dead_letter_tasks.sql

# 3. verificar
psql "$SUPABASE_DB_URL_DIRECT" -c "\d public.dead_letter_tasks"
```

Rollback:

```sql
drop table if exists public.dead_letter_tasks;
```

## 0005_customer_orders.sql

- Tabla `public.customer_order`: propietario y país mínimo de un pedido para
  que el guard del agente rechace consultas de tracking de otra sesión.
- `order_ref` único; índices por `order_ref` y `owner_email`; `country`
  restringido a `US`/`ES`.
- No sustituye al futuro servicio de tracking: es la fuente de autorización
  que usa `app/agent/harness/orders.py`.

Seed de demo:

```bash
cd services/api && source venv/bin/activate
python seed_customer_orders.py --dry-run
python seed_customer_orders.py
```

Rollback:

```sql
drop table if exists public.customer_order;
```

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

## 0006_rfp_intake.sql

- Tablas `public.rfp_ticket`, `public.rfp_metadata` y
  `public.rfp_department_section` para la recepción de RFPs (Hito 9, Parte 1).
- `rfp_ticket` es la fuente de verdad del estado: `analizando`,
  `analisis_completo`, `descartado` y `error` (fallo técnico terminal).
- `rfp_metadata` guarda los metadatos normalizados y las métricas de
  legibilidad/coste; `rfp_department_section` guarda `key_aspects`,
  preguntas abiertas y los campos de borrador/evaluación/aprobación que usarán
  las Partes 2 y 3.
- `rfp_ticket.handoff_payload` + `handoff_status='ready'` son el contrato de
  enrutamiento hacia la Parte 2 (`docs/workflows/RFP_INTAKE_HANDOFF.md`).
- Checks: estados permitidos, `handoff_status` y departamentos canónicos
  (`warehouse`, `lastmile`, `reverse`).
- La API crea las tablas en SQLite/tests con `SQLModel.metadata.create_all`;
  esta migración es la vía explícita para PostgreSQL/Supabase.

Rollback:

```sql
drop table if exists public.rfp_department_section;
drop table if exists public.rfp_metadata;
drop table if exists public.rfp_ticket;
```
