# PIPELINE_DESIGN — TrackFlow · Pipeline de Desempeño de Negocio

Diseño del pipeline de desempeño de negocio para TrackFlow, construido sobre el
briefing autocontenido [`docs/pipeline/PIPELINE_1.md`](../docs/pipeline/PIPELINE_1.md)
y sobre la telemetría ya implementada en el monorepo.

> **Entregable objetivo:** el "Reporte Semanal de Desempeño por Almacén y
> Cliente" — un consolidado semanal, por almacén y por cliente, de volumen de
> entrada, throughput de salida, frecuencia de quiebre de stock y tasa de
> discrepancia. Es el **único** entregable para el que existe este pipeline.

Los tres atributos que separan un pipeline robusto de uno que "simplemente
funciona" guían todo el diseño:

1. **Idempotencia** — correr el pipeline dos veces sobre los mismos datos produce
   el mismo resultado, sin duplicados ni corrupción.
2. **Observabilidad** — cada corrida deja rastros suficientes para saber qué pasó,
   cuándo y por qué.
3. **Recuperabilidad** — cuando el pipeline falla a mitad de camino, la siguiente
   corrida sabe exactamente dónde retomar.

---

## Fase 1 — Análisis del estado actual

### 1.1 Eventos de telemetría capturados hasta ahora

| Capa | Estado actual |
|---|---|
| Catálogo | 23 `event_type` cerrados: 5 obligatorios de inventario + 18 de oportunidad (auth, navegación, rendimiento, incidencias, errores) |
| Envelope | 10 campos congelados: `event_id`, `timestamp`, `session_id`, `user_id`, `event_type`, `schema_version`, `request_id`, `source`, `app`, `properties` |
| Ingesta | `POST /telemetry/events` con validación parcial por ítem y 5 barreras (consentimiento, limpieza, allowlist, muestreo, entorno) |
| Almacenamiento | Supabase/PostgreSQL, tabla `telemetry_events`, append-only; columnas fijas del envelope + `tags jsonb` con las `properties` filtradas |
| Idempotencia de ingesta | PK `event_id` + `INSERT ... ON CONFLICT (event_id) DO NOTHING` |
| Retención | Sin política; la tabla crece indefinidamente |

**Dónde se almacenan:** en la tabla `telemetry_events` de Supabase (PostgreSQL),
que el backend lee a través de `DATABASE_URL` (SQLModel/sqlalchemy). El modelo
es `TelemetryEventRecord` en `services/api/models.py` (columnas fijas del
envelope + `tags` JSONB). La tabla es **write-only** (eventos inmutables), con
índices sobre `timestamp`, `service`, `session_id` y `(event_type, timestamp)`.

### 1.2 Brecha detectada en la capa de captura

Los eventos de negocio que el backend emite (`inbound_order_created`,
`outbound_order_created`, `outbound_rejected_insufficient_stock`) pasan por
`app/telemetry/emitter.py`, que **solo escribe en el log**; no se persisten en
`telemetry_events`. La tabla contiene hoy, de forma fiable, los eventos que
llegan por HTTP desde el frontend.

Además, los eventos emitidos no incluyen `client_id` ni `product_category`, y
los dos eventos obligatorios restantes (`stock_threshold_triggered`,
`inventory_discrepancy_detected`) no están instrumentados.

### 1.3 Qué responde ya el reporte técnico existente

`GET /telemetry/report` (Pandas, ventana de 7 días, caché de 60 s) responde
preguntas de salud técnica y uso del backoffice, no de negocio:

| Métrica | Pregunta que responde | Audiencia |
|---|---|---|
| `events_per_day` | ¿Qué eventos ocurren y con qué volumen? | Ingeniería |
| `error_rate_by_day` | ¿Los fallos crecen respecto al tráfico? | Ingeniería / operaciones |
| `errors_by_type` | ¿Dónde se concentran los fallos? | Ingeniería |
| `latency_per_day` | ¿Se degrada la latencia de la API? | Ingeniería |
| `auth_failure_rate` | ¿Aumentan los logins fallidos? | Seguridad / ingeniería |

Es un reporte **operacional-técnico**: sin dimensión de cliente, sin agrupación
por almacén, sin semanas ISO y sin persistencia de resultados (se calcula al
vuelo y se cachea; no es auditable como entregable de negocio).

### 1.4 La pregunta de TrackFlow que sigue sin responder

> **¿Cómo está rindiendo cada almacén para cada cliente, semana a semana, en
> volumen de entrada, throughput de salida, quiebres de stock y precisión de
> inventario?**

El reporte técnico no puede responderla porque le faltan cinco piezas:

1. **Dimensión cliente:** `client_id` no existe en el modelo `SKU` ni en los
   eventos emitidos.
2. **Dimensión almacén agregada:** `warehouse` viaja en `tags`, pero ninguna
   métrica del reporte agrupa por almacén.
3. **Grano semanal:** el reporte es diario y sobre una ventana móvil de 7 días;
   no hay semanas ISO cerradas.
4. **KPIs de negocio:** volumen, throughput, quiebres y discrepancia no son
   métricas de latencia/errores.
5. **Historia persistida:** no hay tabla de resultados semanales; el CEO no puede
   comparar semanas ni auditar qué números vio.

Esta pregunta **sí requiere un pipeline dedicado**: necesita una fuente distinta,
granularidad distinta (semana ISO cerrada), agregación distinta (cliente ×
almacén), una tabla de resultados persistida y una trayectoria de corridas
auditable.

### 1.5 Brechas de origen que bloquean el pipeline

| # | Brecha | Impacto | Corrección propuesta |
|---|---|---|---|
| G1 | Los eventos backend solo se loguean | El pipeline vería cero eventos de inventario | Persistir el evento en la misma transacción de la orden (o outbox transaccional) |
| G2 | `SKU` no tiene `client_id` ni `product_category` | Imposible cumplir el grano `warehouse × client_id` | Migración ORM + `schema_version` 2.0.0 + allowlist |
| G3 | No existe `min_stock` por SKU | `stock_threshold_triggered` nunca se emite | Configurar umbral y emitir al cruzar el mínimo |
| G4 | `inventory_discrepancy_detected` no se emite | La tasa de discrepancia siempre sería 0 | Emitir al crear incidencia `category=inventory_discrepancy`, con cantidades y `order_id` |
| G5 | Sin histórico de esos eventos | No hay backfill de quiebres/discrepancias | Backfill solo de inbound/outbound desde `stock_entry`/`stock_exit`; el resto empieza en la fecha de instrumentación |
| G6 | `schema_version` no distingue eventos con cliente | Mezclar eventos viejos y nuevos corrompe los KPIs | Filtrar por versión; eventos sin `client_id` van a cuarentena, no se descartan en silencio |

**Decisión:** el pipeline se puede construir y probar ya con datos sembrados,
pero la corrida de producción debe **fallar explícitamente** si G1–G4 no están
resueltos. No se publica un reporte con KPIs en cero por falta de
instrumentación.

---

## Fase 2 — Diseño del pipeline

### 2.1 Contrato de negocio

| Elemento | Definición |
|---|---|
| Entregable | Reporte Semanal de Desempeño por Almacén y Cliente |
| Audiencia | Thomas (CEO) y Ana (Head of Warehouse Operations) |
| Frecuencia | Semanal, lunes por la mañana |
| Grano | 1 fila por `warehouse × client_id × week_start` |
| Semana | ISO, lunes 00:00 UTC a domingo 23:59:59 UTC |
| Fuente | `telemetry_events`, solo lectura, 4 `event_type` |
| Destino | `reporting.weekly_warehouse_client_performance` |
| Nunca escribe | `telemetry_events` |

### 2.2 KPIs

| KPI | Cálculo | Evento que lo alimenta |
|---|---|---|
| `inbound_units_count` — Volumen de entrada | `sum(quantity)` de `inbound_order_created` | `inbound_order_created` |
| `outbound_orders_count` — Throughput de salida | conteo de `outbound_order_created` | `outbound_order_created` |
| `stockout_events_count` — Quiebre de stock | conteo de `stock_threshold_triggered` | `stock_threshold_triggered` |
| `discrepancy_events_count` — apoyo | conteo de `inventory_discrepancy_detected` | `inventory_discrepancy_detected` |
| `discrepancy_rate` — Tasa de discrepancia | `discrepancy_events_count / outbound_orders_count` (0 si no hubo pedidos) | ambos |

No hay dimensión de moneda: el entregable es operacional (volumen y precisión).

### 2.3 Arquitectura

```
telemetry_events (Supabase, solo lectura)
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│ Prefect flow: weekly_warehouse_client_performance       │
│                                                         │
│  resolve_target_weeks                                   │
│        │                                                │
│        ├── process_week(W)  ── subflow aislado          │
│        │     ├── acquire_week_lock                      │
│        │     ├── extract_week        (SQL push-down)    │
│        │     ├── normalize_validate  (tags → columnas)  │
│        │     ├── aggregate_kpis      (group by)         │
│        │     ├── quality_gates       (bloqueantes)      │
│        │     ├── load_week           (upsert atómico)   │
│        │     ├── reconcile_week      (borra obsoletos)  │
│        │     └── record_run          (ledger)           │
│        └── ... W-1, W-2 (lookback)                      │
└─────────────────────────────────────────────────────────┘
        │
        ▼
reporting.weekly_warehouse_client_performance
reporting.pipeline_runs
reporting.weekly_performance_rejects
        │
        ▼
FastAPI /reporting/*  ──►  Backoffice /reporting
```

### 2.4 Etapas

| Etapa | Qué hace | Salida | Falla si… |
|---|---|---|---|
| `resolve_target_weeks` | Calcula la última semana cerrada y las `lookback_weeks` a recomputar | Lista de `week_start` | Fecha inválida o rango > 12 semanas |
| `extract_week` | Lee solo las 4 tipologías en `[week_start, week_start+7d)` | DataFrame crudo | Error de conexión / timeout |
| `normalize_validate` | Normaliza `warehouse`, `client_id`, `quantity`; deduplica por `event_id`; separa inválidos | Válidos + rechazos | Tasa de rechazo > umbral |
| `aggregate_kpis` | Agrupa por almacén y cliente; calcula los 5 campos | DataFrame agregado | Columnas faltantes |
| `quality_gates` | Valida rangos, nulos, negativos, tasa y anomalías | `QualityReport` | Gate bloqueante |
| `load_week` | Upsert en una transacción | Filas escritas | Error SQL → rollback |
| `reconcile_week` | Elimina combinaciones que ya no existen para esa semana | 0 obsoletos | Error SQL → rollback |
| `record_run` | Escribe el ledger de la corrida | `run_id` | — |

### 2.5 Modelo de datos

```sql
create schema if not exists reporting;

create table reporting.weekly_warehouse_client_performance (
  id uuid primary key default gen_random_uuid(),
  warehouse text not null,
  client_id text not null,
  week_start date not null,
  inbound_units_count integer not null default 0,
  outbound_orders_count integer not null default 0,
  stockout_events_count integer not null default 0,
  discrepancy_events_count integer not null default 0,
  discrepancy_rate numeric not null default 0,
  computed_at timestamptz not null default now(),
  unique (warehouse, client_id, week_start),
  check (extract(isodow from week_start) = 1),
  check (inbound_units_count >= 0),
  check (outbound_orders_count >= 0),
  check (stockout_events_count >= 0),
  check (discrepancy_events_count >= 0),
  check (discrepancy_rate >= 0 and discrepancy_rate <= 1)
);

create table reporting.pipeline_runs (
  run_id uuid primary key default gen_random_uuid(),
  pipeline_name text not null,
  flow_run_id text,
  week_start date,
  status text not null check (status in ('running','success','failed','skipped')),
  triggered_by text not null,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  rows_extracted integer not null default 0,
  rows_valid integer not null default 0,
  rows_rejected integer not null default 0,
  rows_written integer not null default 0,
  source_fingerprint text,
  quality_status text,
  error_message text,
  code_version text
);

create index ix_pipeline_runs_started
  on reporting.pipeline_runs (pipeline_name, started_at desc);

create table reporting.weekly_performance_rejects (
  id bigserial primary key,
  run_id uuid references reporting.pipeline_runs(run_id),
  event_id uuid,
  week_start date,
  reason text not null,
  payload jsonb not null,
  created_at timestamptz not null default now()
);
```

`pipeline_runs` es la fuente de `GET /reporting/pipeline-runs/latest`: Prefect es
el orquestador, pero la API no depende de la UI de Prefect para responder.

El constraint `unique (warehouse, client_id, week_start)` es en el que se apoya
la **idempotencia de carga** (upsert), tal como exige el briefing.

### 2.6 Lógica de cálculo

```sql
with src as (
  select distinct on (event_id)
         event_id, event_type, timestamp, tags
  from telemetry_events
  where event_type = any($1)
    and timestamp >= $2
    and timestamp <  $3
  order by event_id
),
norm as (
  select event_id, event_type,
         lower(trim(tags->>'warehouse')) as warehouse,
         lower(trim(tags->>'client_id')) as client_id,
         (tags->>'quantity')::numeric    as quantity
  from src
),
valid as (
  select * from norm
  where warehouse in ('los_angeles','zaragoza')
    and client_id is not null and client_id <> ''
    and quantity is not null and quantity >= 0
)
select
  warehouse,
  client_id,
  coalesce(sum(quantity) filter (where event_type = 'inbound_order_created'), 0) as inbound_units_count,
  count(*) filter (where event_type = 'outbound_order_created')                  as outbound_orders_count,
  count(*) filter (where event_type = 'stock_threshold_triggered')               as stockout_events_count,
  count(*) filter (where event_type = 'inventory_discrepancy_detected')          as discrepancy_events_count
from valid
group by warehouse, client_id;
```

`discrepancy_rate` se calcula en la capa de aplicación:

```python
rate = round(discrepancy_events / outbound_orders, 6) if outbound_orders else 0.0
```

**Semántica de conteo (decisión a validar):** el briefing pide "conteo de
`outbound_order_created`". Hoy el emisor produce un evento por orden, así que
`count(*)` es correcto. Si una orden pudiera emitir varias líneas, habría que
pasar a `count(distinct tags->>'order_id')` y ajustar el denominador de la tasa.
El pipeline incluye un gate de calidad que detecta `order_id` duplicado dentro de
la semana.

**Limitación conocida de la tasa:** el evento de discrepancia no lleva `order_id`,
por lo que la tasa es `eventos de discrepancia / pedidos de salida`, no "pedidos
afectados / pedidos". Para `schema_version` 2.0.0 se propone añadir `order_id` al
evento de discrepancia.

### 2.7 Ventana temporal y datos tardíos

- La corrida del lunes calcula la **última semana ISO cerrada**.
- Recalcula también las **2 semanas anteriores** (`lookback_weeks = 3`) para
  absorber eventos que llegaron tarde.
- Un evento que llega después de la ventana de lookback exige un **backfill
  manual** por semana.
- `computed_at` indica la frescura del snapshot. Si se decide congelar semanas
  publicadas, se añade una tabla de publicaciones y el flujo deja de recomputar
  semanas congeladas; sin congelación, el upsert actualiza la fila y el consumidor
  ve el nuevo `computed_at`.

### 2.8 Puertas de calidad

| Gate | Tipo | Regla | Acción |
|---|---|---|---|
| G1 | Bloqueante | `warehouse` y `client_id` presentes y válidos | Rechazo a cuarentena |
| G2 | Bloqueante | `quantity` numérica y ≥ 0 | Rechazo a cuarentena |
| G3 | Bloqueante | Sin duplicados `(warehouse, client_id, week_start)` | Falla el load |
| G4 | Bloqueante | `0 ≤ discrepancy_rate ≤ 1` | Falla la corrida |
| G5 | Bloqueante | Conteos enteros y no negativos | Falla la corrida |
| G6 | Advertencia | Variación semanal de volumen > ±50 % | Se registra y notifica |
| G7 | Advertencia | Caída de combinaciones activas > 30 % | Se registra y notifica |
| G8 | Advertencia | Tasa de rechazo > 1 % | Se registra; > 5 % bloquea |
| G9 | Advertencia | Semana sin eventos | Se marca `empty_week`, no se inventan filas |
| G10 | Advertencia | Frescura de la fuente > 24 h | Se notifica |

---

## Fase 3 — Resiliencia e idempotencia

### 3.1 Cinco capas de idempotencia

1. **Origen:** `event_id` es PK; el `SELECT` deduplica por `event_id` aunque la
   ingesta ya lo haga.
2. **Ventana determinista:** `week_start` se calcula desde el timestamp del
   evento, nunca desde `now()`. Correr dos veces la misma semana produce el mismo
   conjunto de entrada.
3. **Carga transaccional:** un `INSERT ... ON CONFLICT (warehouse, client_id,
   week_start) DO UPDATE` dentro de una transacción por semana.
4. **Concurrencia:** `pg_advisory_xact_lock(hashtext('weekly-perf:' ||
   week_start))` + límite de concurrencia de Prefect. Dos ejecuciones
   simultáneas de la misma semana no se pisan.
5. **Replay:** mismo flujo, mismos parámetros, mismas filas. El
   `source_fingerprint` (`count`, `max(received_at)`, `max(timestamp)`) permite
   saltar la corrida si la fuente no cambió y la anterior fue exitosa, registrando
   un `skipped` explícito.

### 3.2 Matriz de fallos

| Fallo | Detección | Efecto | Recuperación |
|---|---|---|---|
| Base de datos caída en extract | Excepción de conexión | No hay escrituras | Retry 3× con backoff; la siguiente corrida reintenta la semana |
| Evento malformado | Validación | Se rechaza solo ese evento | Cuarentena + gate de tasa de rechazo |
| Duplicado | `event_id` repetido | Se colapsa a uno | Sin efecto en KPIs |
| Caída a mitad de load | Error SQL | Rollback completo | Reejecutar la semana; el upsert es seguro |
| Worker de Prefect muere | Estado del flow run | Semana incompleta | Reintento manual o automático; el lock se libera con la conexión |
| Evento tardío | `received_at` posterior | Reporte desactualizado | Lookback de 3 semanas + backfill manual |
| Deriva de esquema | `client_id` ausente | KPI en cero silencioso | Gate bloqueante + cuarentena, nunca publicar ceros |
| Semana ISO en cambio de año | Tests de borde | Semana incorrecta | Cálculo con `date_trunc('week')` y tests de diciembre/enero |
| Notificación falla | Error del canal | Datos ya comprometidos | Se marca advertencia; se reintenta la notificación |
| Corrida zombie | `status='running'` > 2 h | Bloquea la UI | Watchdog que la marca `failed` |
| Prefect API caída en disparo manual | Timeout de la API | No arranca la corrida | `503`; la programación semanal sigue activa |

### 3.3 Recuperabilidad

El principio es: **cada semana es una unidad de trabajo independiente y
repetible**.

- El flujo padre procesa todas las semanas y **no aborta en la primera falla**:
  usa `return_state=True` para aislar el error, continúa con las demás y falla al
  final si alguna quedó mal.
- El staging se etiqueta con `run_id`; si el load falla, el staging queda
  disponible para reintentar sin volver a extraer.
- El ledger `pipeline_runs` es la memoria operativa: la siguiente corrida consulta
  la última corrida exitosa por semana y sabe qué recomputar.
- El backfill usa el mismo flujo con `week_start` explícito; no hay un script
  paralelo que pueda divergir.

### 3.4 Observabilidad

| Señal | Dónde | Para qué |
|---|---|---|
| `run_id`, `week_start`, etapa, duración | Logs JSON | Depurar una corrida concreta |
| Filas extraídas / válidas / rechazadas / escritas | `pipeline_runs` | Saber si el resultado es creíble |
| `source_fingerprint` | `pipeline_runs` | Explicar por qué se saltó o recalculó |
| `quality_status` | `pipeline_runs` | Distinguir éxito limpio de éxito con advertencias |
| Frescura (`now() - max(received_at)`) | Métrica de la corrida | Detectar ingesta detenida |
| Estado del flow | Prefect UI + API | Ver reintentos y trazas |
| Artefacto Markdown con el resumen | Prefect | Evidencia legible para Ana/Thomas |

Alertas mínimas: corrida fallida, gate bloqueante, tasa de rechazo alta, semana
sin datos, fuente con más de 24 h de retraso.

---

## Fase 4 — Mapeo a Prefect

Se usa **Prefect 3.x**. Prefect no se añade a `services/api/requirements.txt`: la
API solo habla con la API REST de Prefect usando `httpx`, que ya está en el
proyecto. El pipeline tiene su propia imagen y sus propias dependencias.

### 4.1 Árbol de flows

```
weekly_warehouse_client_performance          (flow padre, programado)
├── resolve_target_weeks                     (task)
├── process_week(W)                          (subflow, una por semana)
│   ├── acquire_week_lock                    (task)
│   ├── extract_week                         (task, retries)
│   ├── normalize_validate                   (task)
│   ├── aggregate_kpis                       (task)
│   ├── quality_gates                        (task)
│   ├── load_week                            (task, transacción)
│   ├── reconcile_week                       (task)
│   ├── record_run                           (task)
│   └── notify_summary                       (task)
└── finalize_run_summary                     (task)
```

### 4.2 Mapeo requisito → primitiva

| Requisito | Prefect |
|---|---|
| Programación semanal | Deployment con `schedules: cron: "0 8 * * 1", timezone: "UTC"` |
| Aislamiento por semana | Subflow `process_week` con `return_state=True` |
| Reintentos transitorios | `@task(retries=3, retry_delay_seconds=[30,120,300])` |
| No reintentar fallos deterministas | Validación y quality gates sin retries |
| Idempotencia | Upsert SQL + advisory lock + `cache_key_fn` por `(week_start, fingerprint)` |
| Concurrencia | Work pool con límite 1 + `concurrency("weekly-perf-{week}")` |
| Secretos | Bloque `Secret` para `DATABASE_URL_PIPELINE` y `PREFECT_API_KEY` |
| Observabilidad | Prefect UI + `create_markdown_artifact` + espejo en `pipeline_runs` |
| Disparo manual | `run_deployment(...)` desde FastAPI |
| Backfill | Parámetro `week_start` / `lookback_weeks` del mismo flow |

### 4.3 Esqueleto

```python
# pipelines/weekly_performance/flow.py
from datetime import date, timedelta
from prefect import flow, task
from prefect.states import Failed

@task(retries=3, retry_delay_seconds=[30, 120, 300], retry_jitter_factor=0.1)
def extract_week(week_start: date) -> pd.DataFrame: ...

@task
def normalize_validate(df, week_start, run_id): ...

@task
def aggregate_kpis(df) -> pd.DataFrame: ...

@task
def quality_gates(df, week_start) -> QualityReport: ...

@task(retries=2)
def load_week(df, week_start, run_id) -> int: ...

@flow(name="process-week")
def process_week(week_start: date) -> WeekResult:
    acquire_week_lock(week_start)
    raw = extract_week(week_start)
    staged = normalize_validate(raw, week_start, run_id)
    kpis = aggregate_kpis(staged.valid)
    quality = quality_gates(kpis, week_start)
    if not quality.passed:
        record_run(status="failed", quality_status=quality.summary)
        raise ValueError(quality.summary)
    written = load_week(kpis, week_start, run_id)
    reconcile_week(week_start, kpis)
    record_run(status="success", rows_written=written)
    return WeekResult(...)

@flow(name="weekly-warehouse-client-performance")
def weekly_flow(lookback_weeks: int = 3):
    weeks = resolve_target_weeks(lookback_weeks)
    states = [process_week.with_options(return_state=True)(w) for w in weeks]
    if any(isinstance(s, Failed) for s in states):
        raise RuntimeError("Una o más semanas fallaron")
```

### 4.4 Deployment

```yaml
# pipelines/weekly_performance/prefect.yaml
deployments:
  - name: weekly-prod
    entrypoint: pipelines/weekly_performance/flow.py:weekly_flow
    work_pool:
      name: trackflow-pool
      work_queue_name: default
    schedules:
      - cron: "0 8 * * 1"
        timezone: "UTC"
        active: true
    parameters:
      lookback_weeks: 3
    tags: [reporting, weekly, business]
```

**Horario:** lunes 08:00 UTC = 09:00 en Madrid y 00:00/01:00 en Los Ángeles. Es
el único horario que cae en "lunes por la mañana" en ambas sedes. Si se prefiere
la mañana de Los Ángeles, habría que moverlo a ~15:00 UTC y Madrid lo vería por
la tarde; es una decisión de negocio.

### 4.5 Estructura del pipeline

```
pipelines/weekly_performance/
  flow.py            # flows padre y subflow
  tasks.py           # tareas de extract/normalize/aggregate/load
  sql.py             # DDL y consultas
  quality.py         # gates de calidad
  settings.py        # env vars y constantes
  prefect.yaml       # deployments y schedules
  Dockerfile         # imagen con prefect + pandas + sqlalchemy
  tests/             # unitarios, integración e idempotencia
```

### 4.6 Pruebas

| Nivel | Qué se prueba |
|---|---|
| Unitarias | Fronteras de semana ISO (`domingo 23:59:59Z` vs `lunes 00:00Z`), cambio de año, `client_id` nulo, `quantity` negativa, división por cero |
| Unitarias de agregación | Comparar el resultado SQL con una implementación Python de referencia sobre datos aleatorios |
| Integración | Upsert real en PostgreSQL, `ON CONFLICT`, JSONB, advisory lock, rollback |
| Idempotencia | Ejecutar dos veces la misma semana y comparar la tabla byte a byte (salvo `computed_at`) |
| Tardíos | Insertar un evento después de la primera corrida y verificar que el lookback actualiza la semana |
| Flow | `prefect_test_harness` para el flujo completo con base efímera |
| E2E | Sembrar 3 semanas con totales conocidos, correr el flujo, validar el reporte y el ledger |

---

## Fase 5 — Integración con la aplicación (solo diseño)

### 5.1 Módulo backend

En este repo no existe `services/telemetry/`; el equivalente es
`services/api/app/telemetry/`. Para mantener la separación funcional sin romper
el monolito FastAPI:

```
services/api/app/reporting/
  __init__.py
  router.py          # endpoints /reporting/*
  schemas.py         # response models
  service.py         # consultas SQL de lectura
  prefect_client.py  # httpx contra la API de Prefect
```

Si se exige literalmente `services/reporting/`, se crea ese paquete y se importa
desde la app; el contrato no cambia. El pipeline Prefect vive aparte, en
`pipelines/weekly_performance/`.

`app/main.py` registra el router nuevo y **no toca** `app/telemetry/analysis.py`
ni `GET /telemetry/report` (fuera de alcance, como exige el briefing).

### 5.2 Endpoints

| Método | Ruta | Auth | Respuesta |
|---|---|---|---|
| `GET` | `/reporting/weekly-warehouse-client-performance?week_start=YYYY-MM-DD` | `require_manager` | Semana solicitada o la última disponible |
| `GET` | `/reporting/pipeline-runs/latest` | `require_manager` | Última corrida con estado y metadata |
| `POST` | `/reporting/pipeline-runs` | `require_manager` | `202` con `run_id` y `flow_run_id` |

```json
// GET /reporting/weekly-warehouse-client-performance
{
  "week_start": "2026-07-13",
  "entries": [
    {
      "warehouse": "los_angeles",
      "client_id": "fashion-co",
      "inbound_units_count": 4200,
      "outbound_orders_count": 980,
      "stockout_events_count": 3,
      "discrepancy_events_count": 2,
      "discrepancy_rate": 0.002041
    }
  ]
}
```

```json
// GET /reporting/pipeline-runs/latest
{
  "run_id": "…",
  "status": "success",
  "week_start": "2026-07-13",
  "started_at": "2026-07-20T08:00:03Z",
  "finished_at": "2026-07-20T08:00:41Z",
  "rows_extracted": 18432,
  "rows_rejected": 0,
  "rows_written": 14,
  "quality_status": "passed",
  "error_message": null
}
```

```json
// POST /reporting/pipeline-runs  (body opcional)
{ "week_start": "2026-07-06", "lookback_weeks": 1 }
```

Errores: `409` si ya hay una corrida en curso para esa semana, `503` si Prefect
no responde, `404` si no hay reportes disponibles, `403` para roles sin permiso.

**Caché:** `GET` semanal con TTL 60 s (mismo patrón que `telemetry:report`);
`latest` con TTL 5 s. La lectura usa SQL directo, no Pandas: el pipeline ya dejó
los datos pre-agregados.

### 5.3 Frontend (backoffice)

- Ruta nueva `/reporting` dentro de `(protected)`.
- `components/reporting/`: `WeekSelector`, `PerformanceTable`, `PipelineStatusCard`, `RunNowButton`.
- `lib/api.ts`: `fetchWeeklyPerformance`, `fetchLatestPipelineRun`, `triggerPipelineRun`.
- `lib/types.ts`: tipos y `computeWeeklyTotals` (totales y tasa ponderada).
- `Sidebar`: entrada "Desempeño".
- `next.config.ts`: rewrite `/api/reporting/:path*` → `BACKEND_URL/reporting/:path*`.
- Reutiliza `MetricCard`, `BreakdownCard`, `ConfirmDialog` y `useAsyncData`.
- La tabla muestra una fila por almacén/cliente y un filtro por almacén.
- El botón "Ejecutar ahora" pide confirmación y hace polling de
  `pipeline-runs/latest` cada 5 s mientras el estado sea `running`.
- Estados vacíos: "Aún no hay semanas calculadas" y "Sin actividad para esta semana".

### 5.4 Secuencia

```
Backoffice ──GET /api/reporting/weekly...──► FastAPI ──SELECT──► reporting table
Backoffice ──POST /api/reporting/pipeline-runs──► FastAPI ──httpx──► Prefect API
                                                              │
                                                              ▼
                                                   work pool → flow
                                                              │
                                                              ▼
                                            Supabase: reporting.* + telemetry_events (RO)
Backoffice ──GET /api/reporting/pipeline-runs/latest──► FastAPI ──SELECT──► pipeline_runs
```

### 5.5 Seguridad

- El pipeline usa un rol de BD con `SELECT` solo sobre `telemetry_events` y
  `INSERT/UPDATE/DELETE` sobre `reporting`. Nunca `UPDATE/DELETE` sobre
  `telemetry_events`.
- La API usa un rol de solo lectura sobre `reporting`.
- `POST /reporting/pipeline-runs` queda auditado en `pipeline_runs.triggered_by`.
- No se exponen eventos crudos ni `tags`; solo agregados por cliente/almacén.
- El reporte no contiene PII de consumidor final.

---

## Guardarraíles de alcance

- Este pipeline lee `telemetry_events` en **modo solo lectura**; nunca escribe de
  vuelta ahí.
- `services/telemetry/analysis.py` (equivalente en este repo:
  `services/api/app/telemetry/analysis.py`) y `GET /telemetry/report` quedan
  **fuera del alcance** de este hito, sin modificar.
- El endpoint de reporte se expone en un módulo nuevo y separado de telemetría
  (`app/reporting/`); no hay cambios de URL de las APIs existentes.
- Para la v1 se usan **solo** los cuatro eventos obligatorios; no se amplía el
  alcance a eventos de oportunidad.

---

## Decisiones abiertas antes de implementar

1. **Conteo de salida:** `count(*)` de eventos (literal del briefing) o
   `count(distinct order_id)`. Recomendado: literal en v1 con gate de duplicados.
2. **Numerador de discrepancia:** conteo de eventos o pedidos afectados. Requiere
   añadir `order_id` al evento; recomendado en `schema_version` 2.0.0.
3. **Congelación de semanas publicadas:** permitir que el lookback actualice una
   semana ya vista por Thomas, o congelarla tras la publicación. Recomendado:
   congelar a las 2 semanas y exigir backfill explícito.
4. **Prefect Cloud vs self-hosted:** afecta a secretos, red y coste.
5. **Ruta literal `services/reporting/`:** confirmar si el rubric la exige o si
   vale `services/api/app/reporting/`.
6. **Alcance del backfill:** solo inbound/outbound desde `stock_entry`/`stock_exit`,
   o también intentar reconstruir clientes históricos.
