# PLAN — Pipeline resiliente de desempeño de negocio

> **Briefing:** [`docs/pipeline/PIPELINE_2.md`](./PIPELINE_2.md) · **Diseño previo:** [`data/pipelines/PIPELINE_DESIGN.md`](../../data/pipelines/PIPELINE_DESIGN.md)
>
> `PIPELINE_2.md` es idéntico a `PIPELINE_1.md`. Este documento **no reemplaza** el
> diseño: lo convierte en un plan de ejecución con foco explícito en resiliencia
> (idempotencia, recuperación, cuarentena y observabilidad).

---

## 0. Decisiones cerradas

Estas seis decisiones se resolvieron antes de empezar la implementación y son
vinculantes para el resto del plan.

| # | Decisión | Elección | Efecto |
|---|---|---|---|
| D1 | Conteo de salida | **Híbrido:** `count(distinct coalesce(order_id, event_id))` | Throughput = pedidos únicos, inmune a reintentos y a eventos sin `order_id` |
| D2 | Numerador de discrepancia | **Un evento por pedido afectado**, emitido desde la capa de inventario; el detalle por SKU queda en SQL | `count(*)` literal y `discrepancy_rate ≤ 1` por construcción |
| D3 | Congelación de semanas | **Congelar tras 2 corridas exitosas posteriores al cierre** + backfill auditado con revisión | `published_weeks` + `weekly_performance_revisions` |
| D4 | Orquestador | **Prefect self-hosted en Docker Compose**, API configurable | Sin dependencia externa en v1; migrable a Cloud cambiando `PREFECT_API_URL` |
| D5 | Ruta del módulo | **`services/api/app/reporting/`** | Mapeo documentado del `services/reporting/` del briefing |
| D6 | Backfill histórico | **Solo inbound/outbound** desde `stock_entry`/`stock_exit` | Quiebres y discrepancias empiezan en `instrumentation_since` |

**Consecuencia de D1 + D2:** el numerador y el denominador cuentan pedidos, no
eventos. La fórmula literal del briefing (`discrepancy_events_count /
outbound_orders_count`) se mantiene porque se garantiza **un evento de discrepancia
por pedido afectado**; el gate G5 queda como red de seguridad.

---

## 1. Objetivo y criterio de éxito

**Objetivo:** implementar el pipeline semanal `warehouse × client_id × week_start`
que produce el *Reporte Semanal de Desempeño por Almacén y Cliente*, de forma que
pueda fallar en cualquier punto y **recuperarse sin perder ni duplicar datos**, sin
publicar KPIs en cero por falta de instrumentación.

Se considera terminado cuando se cumplen estos criterios medibles:

| # | Criterio | Verificación |
|---|---|---|
| R1 | Dos corridas de la misma semana producen filas idénticas salvo `computed_at` | Test de idempotencia (hash de filas) |
| R2 | Un fallo a mitad de `load` no deja filas parciales | Test con kill de conexión + rollback |
| R3 | Un evento malformado no tumba la corrida ni contamina KPIs | Test de cuarentena + gate de rechazo |
| R4 | Un evento tardío dentro del lookback se refleja en la siguiente corrida | Test de tardíos |
| R5 | Dos corridas simultáneas de la misma semana no se pisan | Test con dos procesos + advisory lock |
| R6 | Una corrida zombie se detecta y se marca `failed` | Test del watchdog |
| R7 | Toda corrida deja rastro consultable (filas, fingerprint, calidad, error) | `GET /reporting/pipeline-runs/latest` |
| R8 | Si la fuente no cambió, la corrida se registra como `skipped`, no se recalcula | Test de fingerprint |
| R9 | Una semana sin datos se publica como vacía explícita, nunca con ceros inventados | Gate `empty_week` |
| R10 | Cualquier semana se puede reprocesar con el mismo flujo (sin script paralelo) | Backfill CLI + test E2E |

---

## 2. Punto de partida real del repo

| Pieza | Estado | Implicación para el plan |
|---|---|---|
| `telemetry_events` (Supabase/PostgreSQL) | ✅ Persistida, append-only, PK `event_id` | Fuente lista; solo lectura |
| `POST /telemetry/events` | ✅ Validación parcial + 5 barreras | Reutilizable; no se toca |
| `app/telemetry/emitter.py` | ⚠️ **Solo escribe en log** | **Bloqueante G1**: sin persistencia no hay pipeline |
| `inbound_order_created` / `outbound_order_created` | ⚠️ Se emiten sin `client_id` | **Bloqueante G2** |
| `stock_threshold_triggered` | ❌ No instrumentado (falta `min_stock`) | **Bloqueante G3** |
| `inventory_discrepancy_detected` | ❌ No instrumentado; `IncidentCreate` no tiene `order_id`/`sku_code`/cantidades | **Bloqueante G4**: se instrumenta en inventario, no en incidencias (D2) |
| `GET /telemetry/report` | ✅ Fuera de alcance | No modificar |
| Prefect | ❌ No instalado | **D4:** self-hosted en Compose; worker aparte, no en `requirements.txt` de la API |
| `reporting.*` | ❌ No existe | Fase 0 |

**Decisión de arranque:** el pipeline se desarrolla y prueba contra datos sembrados
desde el día 1, pero **la corrida de producción falla de forma explícita** mientras
G1–G4 no estén cerrados. Un reporte vacío es aceptable; un reporte con ceros
silenciosos, no.

---

## 3. Principios de resiliencia

1. **Unidad de trabajo = una semana ISO.** Cada semana es independiente,
   repetible y aislable; el fallo de una no invalida las demás.
2. **At-least-once en origen + dedupe determinista en destino.** Nunca
   exactly-once teórico: `event_id` + upsert por clave natural.
3. **La transacción es la frontera.** O se escribe la semana completa o no se
   escribe nada. Nada de escrituras parciales "para ir avanzando".
4. **Fail-fast en datos, fail-soft en orquestación.** Un dato inválido bloquea o
   va a cuarentena; el fallo de una semana no aborta el resto.
5. **Nunca publicar ceros por defecto.** Fuente incompleta ⇒ `failed`/`skipped`
   visible, no un KPI plausible pero falso.
6. **Todo reintento es seguro por construcción.** Si un reintento necesita lógica
   especial, el diseño está mal.
7. **La recuperación es un comando, no una operación manual.** Backfill y replay
   usan el mismo flujo con parámetros explícitos.
8. **Observabilidad por corrida, no por log suelto.** `run_id` atraviesa todas las
   etapas y queda en el ledger.
9. **Origen y evento se comprometen juntos.** Una orden o discrepancia sin su
   evento es un dato perdido; el outbox lo hace imposible.
10. **Lo publicado es inmutable; corregirlo deja rastro.** Una semana congelada
    solo cambia con un backfill explícito y una revisión auditada (D3).
11. **Una discrepancia = un pedido afectado.** La idempotencia por `order_id`
    mantiene la tasa de discrepancia en `[0, 1]` (D2).

---

## 4. Arquitectura objetivo

```
┌──────────────────────────────────────┐
│ inventory_service / API              │
│  orden        + outbox   (1 tx)      │──┐
│  discrepancia + outbox   (1 tx)      │──┤
└──────────────────────────────────────┘  │
                                          ▼
                    ops.telemetry_outbox  (atómico con la orden/discrepancia)
                                          │ relay (SKIP LOCKED, idempotente)
                                          ▼
                    telemetry_events (append-only, RO para el pipeline)
                                          │
                                          ▼
        ┌───────────────────────────────────────────────────┐
        │ Prefect 3.x (self-hosted)                         │
        │ weekly_warehouse_client_performance               │
        │                                                   │
        │ resolve_target_weeks                              │
        │   └─ process_week(W)  [subflow aislado]           │
        │        acquire_week_lock (advisory)               │
        │        check_frozen_week (published_weeks)        │
        │        check_watermark (fingerprint)              │
        │        extract_week      (SQL push-down)          │
        │        normalize_validate (dedupe + cuarentena)   │
        │        aggregate_kpis                             │
        │        quality_gates     (bloqueantes/aviso)      │
        │        load_week         (upsert 1 tx)            │
        │        reconcile_week    (borra obsoletos)        │
        │        record_run + heartbeat                     │
        └───────────────────────────────────────────────────┘
                                          │
                                          ▼
        reporting.weekly_warehouse_client_performance
        reporting.pipeline_runs · pipeline_run_steps
        reporting.weekly_performance_rejects
        reporting.week_watermarks
        reporting.published_weeks · weekly_performance_revisions
                                          │
                                          ▼
        FastAPI /reporting/*  ──►  Backoffice /reporting
```

**Cambios clave frente al diseño previo:**

1. **Outbox transaccional** (cierre de G1): la orden y su evento se comprometen juntos; el
   relay puede fallar y reintentar sin perder el evento. Cierra G1 sin acoplar la
   latencia de la orden a la escritura de telemetría.
2. **Discrepancia en la capa de inventario** (D2): `POST /inventory/discrepancies`
   escribe la discrepancia SQL y el evento en el mismo outbox. La incidencia pasa
   a ser un efecto secundario opcional; se elimina la ventana TinyDB↔PostgreSQL.
3. **Prefect self-hosted** (D4): servidor + worker en Compose, con
   `PREFECT_API_URL` configurable para migrar a Cloud sin tocar código.
4. **Congelación de semanas** (D3): el flujo comprueba `published_weeks` antes de
   recalcular y solo un backfill explícito puede escribir una revisión.

---

## 5. Plan de ejecución por fases

> Estimación en días-persona de un dev senior. Cada fase termina en un PR
> revisable y con tests verdes.

### Fase 0 — Fundaciones (1–1,5 d)

| # | Tarea | Archivos | Aceptación |
|---|---|---|---|
| 0.1 | Crear `pipelines/weekly_performance/` con paquete, `settings.py` y `README.md` | `pipelines/weekly_performance/*` | Importable; sin dependencias de `services/api` |
| 0.2 | `pyproject.toml` propio (prefect, pandas, sqlalchemy, psycopg, pytest) + imagen Docker | `pipelines/.../pyproject.toml`, `Dockerfile` | `docker build` OK |
| 0.3 | DDL de `reporting.*` (ver §6) + script `sql.py` idempotente | `pipelines/.../sql.py` | `create ... if not exists`; reejecutable |
| 0.4 | Entorno de test: PostgreSQL efímero (testcontainers o SQLite con dialecto adaptado) | `tests/conftest.py` | Suite base corre en CI sin Supabase |
| 0.5 | Semilla determinista de 3 semanas con totales conocidos | `tests/factories.py` | Totales esperados documentados |

**Riesgo:** SQLite no soporta `advisory locks` ni `JSONB`. Los tests de
concurrencia y de upsert **deben** correr contra PostgreSQL real (contenedor).

### Fase 1 — Cerrar brechas de origen (4–5 d) · bloqueante de producción

| # | Tarea | Archivos | Aceptación |
|---|---|---|---|
| 1.1 | `ops.telemetry_outbox` + relay `FOR UPDATE SKIP LOCKED` con reintentos y marca `sent_at` | `services/api/app/telemetry/outbox.py`, `models.py` | Evento no se pierde si el relay cae; test de replay |
| 1.2 | `inventory_service` escribe orden + outbox en **la misma transacción** | `app/services/inventory_service.py` | Test: rollback de la orden ⇒ no hay evento |
| 1.3 | `client_id` en `SKU` (+ migración y backfill de datos existentes) | `models.py`, `seed_inventory.py` | `GET /inventory/products` lo expone; eventos lo llevan |
| 1.4 | `min_stock` por SKU y emisión de `stock_threshold_triggered` al cruzar el umbral | `models.py`, `inventory_service.py` | Test: entrada/salida que cruza el mínimo emite 1 evento |
| 1.5 | **`POST /inventory/discrepancies`**: escribe discrepancia SQL + `inventory_discrepancy_detected` en el mismo outbox, **1 evento por `order_id`** | `app/routes/inventory.py`, `inventory_service.py`, `models.py` | Idempotente por `order_id`; la incidencia `inventory_discrepancy` se crea como efecto secundario opcional |
| 1.6 | Subir `schema_version` a `2.0.0` y allowlist de `client_id`/`order_id`/`incident_id` | `models.py`, `app/telemetry/catalog.py`, `shared/telemetry/*`, `docs/telemetry/event-schemas.json` | Test de paridad catálogo ↔ JSON Schema sigue verde |
| 1.7 | Reconciliación de origen: comparar órdenes SQL vs eventos persistidos por día | `pipelines/.../tasks.py` (task `reconcile_source`) | Discrepancia > 0 ⇒ alerta |

**Nota de diseño (D2 / G4):** `IncidentCreate` solo tiene `title`, `description`,
`origin`, `branch`, `category` y `status`; no hay `order_id`, `sku_code` ni
cantidades, y las incidencias viven en TinyDB mientras la telemetría vive en
PostgreSQL. Emitir desde `incidents_manager` no permitiría construir un evento
válido ni garantizar atomicidad. Por eso la fuente de verdad pasa a ser la capa de
inventario:

- `POST /inventory/discrepancies` recibe `order_id`, `sku_id`, `warehouse`,
  `system_quantity` y `physical_quantity`.
- La discrepancia y el evento se escriben en **la misma transacción** (outbox).
- La idempotencia es por `order_id`: si ya existe un evento de discrepancia para
  ese pedido, no se emite otro. Así `count(eventos) == count(pedidos afectados)`.
- Si un pedido tiene discrepancias en varios SKU, el detalle queda en la tabla SQL
  y **se emite un único evento agregado** por pedido (el KPI es a nivel de pedido).
- La incidencia se crea después, de forma opcional, enlazada por `incident_id`.

**Backfill histórico (D6):** solo `inbound`/`outbound` desde
`stock_entry`/`stock_exit`, usando el `client_id` **actual** del SKU (no hay foto
histórica). Quiebres y discrepancias empiezan en `instrumentation_since`, que se
expone en `GET /reporting/pipeline-runs/latest` y se documenta en el README; el
contrato del endpoint semanal se mantiene exacto. No se reconstruyen
discrepancias desde incidencias (texto libre ⇒ falsos positivos).

### Fase 2 — Núcleo del pipeline (3 d)

| # | Tarea | Aceptación |
|---|---|---|
| 2.1 | `resolve_target_weeks`: última semana ISO cerrada + lookback configurable | Tests de borde: domingo 23:59:59Z, lunes 00:00Z, cambio de año |
| 2.2 | `extract_week`: SQL con push-down de `event_type` y rango `[W, W+7d)` | Test verifica que no escanea la tabla completa |
| 2.3 | `normalize_validate`: trim/lower, cast de `quantity`, dedupe por `event_id`, separación válidos/rechazos | DataFrame válido + lista de rechazos con motivo |
| 2.4 | `aggregate_kpis`: group by + `count(distinct coalesce(order_id, event_id))` (D1) + `discrepancy_rate` con división segura | Contraste contra implementación Python de referencia; test que fija "pedidos únicos, no eventos" |
| 2.5 | `load_week`: `INSERT ... ON CONFLICT (warehouse, client_id, week_start) DO UPDATE` en 1 tx | Idempotencia byte a byte |
| 2.6 | `reconcile_week`: borra combinaciones que ya no existen para esa semana | Test con evento eliminado/reprocesado |
| 2.7 | `record_run`: ledger + `source_fingerprint` | `skipped` si no cambió y la anterior fue `success` |

### Fase 3 — Resiliencia activa (3–4 d)

| # | Mecanismo | Implementación | Test |
|---|---|---|---|
| 3.1 | Aislamiento por semana | Subflow con `return_state=True`; el padre no aborta en la primera falla | Una semana rota, dos OK |
| 3.2 | Lock de concurrencia | `pg_advisory_xact_lock(hashtext('weekly-perf:'||week))` + work pool limit 1 | Dos corridas simultáneas |
| 3.3 | Reintentos selectivos | `retries=3`, backoff `[30,120,300]` + jitter, **solo** errores transitorios | Fallo determinista no reintenta |
| 3.4 | Watchdog de zombies | `status='running'` + `heartbeat_at` > 2 h ⇒ `failed` | Test con heartbeat viejo |
| 3.5 | Cuarentena / DLQ | `weekly_performance_rejects` con `reason`, `payload`, `run_id` | Replay selectivo por `run_id` |
| 3.6 | Circuit breaker de fuente | Si `extract` falla 3× seguidas, la corrida se aborta con `source_unavailable` | Test con conexión caída |
| 3.7 | Backfill CLI (D6) | `python -m pipelines.weekly_performance backfill --week 2026-07-13`, solo inbound/outbound y `triggered_by='backfill'` | Mismo resultado que la corrida programada |
| 3.8 | Degradación en lectura | La API sirve el último snapshot bueno con `stale: true` si la última corrida falló | Test de API con ledger en `failed` |
| 3.9 | Congelación de semanas (D3) | `check_frozen_week`: se marca `frozen` tras 2 corridas exitosas posteriores al cierre (W+2); una semana congelada no se recalcula; `backfill --force --reason` escribe una revisión en `weekly_performance_revisions` | Test: sin `--force` no escribe; con `--force` deja revisión y auditoría |

### Fase 4 — Calidad y reconciliación de datos (2 d)

| Gate | Tipo | Regla | Acción |
|---|---|---|---|
| G1 | Bloqueante | `warehouse ∈ {los_angeles, zaragoza}` | Cuarentena del evento |
| G2 | Bloqueante | `client_id` no vacío | Cuarentena |
| G3 | Bloqueante | `quantity` numérica y ≥ 0 | Cuarentena |
| G4 | Bloqueante | Sin duplicados `(warehouse, client_id, week)` | Falla el load |
| G5 | Bloqueante | `0 ≤ discrepancy_rate ≤ 1` y conteos enteros ≥ 0 (red de seguridad de D2) | Falla la corrida |
| G6 | Bloqueante | Cobertura de instrumentación **desde `instrumentation_since`**: si `stockout`/`discrepancy` = 0 en todas las filas ⇒ `instrumentation_missing` | Falla (no publica ceros) |
| G7 | Aviso | Variación de volumen > ±50 % vs semana anterior | `quality_status=warning` + alerta |
| G8 | Aviso | Caída de combinaciones activas > 30 % | `quality_status=warning` + alerta |
| G9 | Aviso | Tasa de rechazo > 1 % (bloquea > 5 %) | Alerta / fallo |
| G10 | Aviso | Semana sin eventos | `empty_week` explícito |
| G11 | Aviso | Frescura de fuente > 24 h | Alerta |
| G12 | Aviso | `order_id` duplicado en la semana | Alerta (defensivo: el conteo D1 ya deduplica) |
| G13 | Bloqueante | Semana en `published_weeks` sin `--force` | `skipped: frozen` (no se recalcula) |

Además: tarea `reconcile_source` diaria que compara el conteo de órdenes de
inventario con el conteo de eventos del día; cualquier diferencia abre incidencia.

### Fase 5 — Orquestación y operación (2–3 d)

| # | Tarea | Aceptación |
|---|---|---|
| 5.1 | Prefect **self-hosted** (D4): servicio `prefect` + worker `prefect-worker` en Compose, con `PREFECT_API_URL` y `PREFECT_API_DATABASE_CONNECTION_URL` configurables | `docker compose up` levanta servidor y worker; el flow se ejecuta en el worker, no en la API |
| 5.2 | Deployment `weekly-prod` (cron `0 8 * * 1`, UTC) + work pool `trackflow-pool` con concurrencia 1 | Visible en Prefect UI; dos flows no solapan |
| 5.3 | Secretos (`DATABASE_URL_PIPELINE`, `PREFECT_API_KEY`) y migración a Cloud documentada | Nada hardcodeado; cambiar solo URL/clave permite usar Prefect Cloud |
| 5.4 | Alertas: corrida fallida, gate bloqueante, rechazo alto, semana vacía, fuente > 24 h | Notificación recibida en canal de prueba |
| 5.5 | `RUNBOOK.md` con 6 procedimientos: fallo de corrida, semana vacía, rechazo masivo, backfill, replay de cuarentena, lock colgado | Cada procedimiento probado en local |
| 5.6 | Artefacto Markdown por corrida | Legible por Ana/Thomas sin abrir Prefect |
| 5.7 | Healthcheck del servidor Prefect + política `restart: unless-stopped` | Un reinicio del servidor no pierde el deployment ni deja el worker huérfano |

### Fase 6 — API y backoffice (2–3 d)

| # | Tarea | Aceptación |
|---|---|---|
| 6.1 | `services/api/app/reporting/` (D5) con `router.py`, `schemas.py`, `service.py`, `prefect_client.py`; README con el mapeo desde el `services/reporting/` del briefing | No toca `telemetry/analysis.py`; el contrato HTTP es idéntico |
| 6.2 | `GET /reporting/weekly-warehouse-client-performance` | Contrato exacto del briefing; `404` sin datos; caché 60 s |
| 6.3 | `GET /reporting/pipeline-runs/latest` | Ledger, no Prefect; caché 5 s |
| 6.4 | `POST /reporting/pipeline-runs` | `202` con `run_id`; `409` si hay corrida en curso; `503` si Prefect no responde |
| 6.5 | `require_manager` en los 3 endpoints | `401`/`403` testeados |
| 6.6 | Ruta `/reporting` en backoffice: selector de semana, tabla, estado del pipeline, botón "Ejecutar ahora" con polling | Vitest + build |
| 6.7 | Rewrite `/api/reporting/:path*` y entrada en `Sidebar` | Funciona vía Docker |

### Fase 7 — Endurecimiento (2 d)

| # | Tarea |
|---|---|
| 7.1 | Tests de caos: matar worker a mitad de `load`, cortar conexión, duplicar lote, evento venenoso, reloj desfasado |
| 7.2 | Test de carga: 1 M eventos/semana (objetivo < 60 s de pipeline, < 2 GB RAM) |
| 7.3 | Property-based tests (`hypothesis`) para semana ISO y agregación |
| 7.4 | Revisión de seguridad: rol RO sobre `telemetry_events`, RW solo en `reporting` |
| 7.5 | Actualizar `memory-bank/progress.md`, `techContext.md` y `data/pipelines/README` |

---

## 6. Modelo de datos (adiciones al diseño)

```sql
create schema if not exists reporting;

-- Resultado (sin cambios respecto al briefing)
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
  check (discrepancy_rate between 0 and 1)
);

-- Ledger de corridas
create table reporting.pipeline_runs (
  run_id uuid primary key default gen_random_uuid(),
  pipeline_name text not null,
  flow_run_id text,
  week_start date,
  status text not null check (status in ('running','success','failed','skipped')),
  triggered_by text not null,
  started_at timestamptz not null default now(),
  heartbeat_at timestamptz,
  finished_at timestamptz,
  rows_extracted integer not null default 0,
  rows_valid integer not null default 0,
  rows_rejected integer not null default 0,
  rows_written integer not null default 0,
  source_fingerprint text,
  quality_status text,
  error_message text,
  code_version text,
  instrumentation_since date
);

create unique index ux_pipeline_runs_active_week
  on reporting.pipeline_runs (pipeline_name, week_start)
  where status = 'running';

create index ix_pipeline_runs_started
  on reporting.pipeline_runs (pipeline_name, started_at desc);

-- Trazabilidad por etapa (duración, intento, error)
create table reporting.pipeline_run_steps (
  id bigserial primary key,
  run_id uuid not null references reporting.pipeline_runs(run_id) on delete cascade,
  step text not null,
  attempt integer not null default 1,
  status text not null check (status in ('started','success','failed','skipped')),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  detail jsonb
);

-- Cuarentena / DLQ
create table reporting.weekly_performance_rejects (
  id bigserial primary key,
  run_id uuid references reporting.pipeline_runs(run_id),
  event_id uuid,
  week_start date,
  reason text not null,
  payload jsonb not null,
  replayed_at timestamptz,
  created_at timestamptz not null default now()
);

-- Watermark por semana: permite skip y auditoría
create table reporting.week_watermarks (
  week_start date primary key,
  last_run_id uuid references reporting.pipeline_runs(run_id),
  source_fingerprint text not null,
  rows_written integer not null default 0,
  computed_at timestamptz not null default now()
);

-- Congelación de semanas ya publicadas (D3)
create table reporting.published_weeks (
  week_start date primary key,
  published_at timestamptz not null default now(),
  published_by text not null,
  frozen boolean not null default true
);

-- Snapshot inmutable cuando un backfill fuerza una semana congelada (D3)
create table reporting.weekly_performance_revisions (
  id bigserial primary key,
  week_start date not null,
  run_id uuid not null references reporting.pipeline_runs(run_id),
  reason text not null,
  forced_by text not null,
  snapshot jsonb not null,
  created_at timestamptz not null default now()
);

create index ix_revisions_week
  on reporting.weekly_performance_revisions (week_start, created_at desc);

-- Outbox transaccional (en el esquema operativo de la API)
create schema if not exists ops;
create table ops.telemetry_outbox (
  id bigserial primary key,
  event_id uuid not null unique,
  payload jsonb not null,
  created_at timestamptz not null default now(),
  sent_at timestamptz,
  attempts integer not null default 0,
  last_error text
);

create index ix_outbox_pending on ops.telemetry_outbox (id) where sent_at is null;
```

`pipeline_runs` es la fuente de `GET /reporting/pipeline-runs/latest`; la API no
depende de la disponibilidad de Prefect para responder.

---

## 7. Matriz de fallos (ampliada)

| Fallo | Detección | Efecto | Recuperación | Automático |
|---|---|---|---|---|
| BD caída en `extract` | Excepción de conexión | Sin escrituras | Retry 3× + backoff; siguiente corrida reintenta | ✅ |
| Evento malformado | Validación | Se rechaza solo ese evento | Cuarentena + replay | ✅ |
| Duplicado de evento | PK `event_id` / dedupe | Se colapsa | Sin efecto | ✅ |
| Caída a mitad de `load` | Error SQL | Rollback total | Reejecutar semana | ✅ |
| Worker muere | Heartbeat > 2 h | Semana incompleta | Watchdog marca `failed` + reintento | ✅ |
| Lock colgado | `pg_locks` + watchdog | Semana bloqueada | Matar sesión + reintento | ⚠️ manual |
| Evento tardío | `received_at` posterior | Reporte desactualizado | Lookback 3 semanas | ✅ |
| Fuera del lookback | Watermark | Semana obsoleta | Backfill CLI | ⚠️ manual |
| Deriva de esquema | Gate G2/G6 | KPI en cero silencioso | Bloqueo + cuarentena | ✅ |
| Semana ISO en cambio de año | Tests de borde | Semana incorrecta | `date_trunc('week')` + tests | ✅ |
| Outbox atascado | `pending` > N minutos | Eventos no visibles | Relay reintenta; alerta | ✅ |
| Discrepancia sin `order_id` | Validación de `/inventory/discrepancies` | `400`; no se emite | Corregir payload; nunca entra al pipeline | ✅ |
| Incidencia no creada tras la discrepancia | Reconciliación | Evento ya persistido; falta el ticket | Reintento idempotente por `order_id` | ⚠️ semi |
| Prefect server caído | Healthcheck / timeout | No se programan ni disparan flows | `503` en la API; `restart: unless-stopped` | ✅ |
| Semana congelada recalculada | `published_weeks` + gate G13 | Cambia lo que vio el CEO | Bloqueo salvo `backfill --force` con revisión | ✅ |
| Notificación falla | Error de canal | Datos ya comprometidos | Reintento de notificación | ✅ |

---

## 8. Estrategia de pruebas

| Nivel | Herramienta | Qué cubre |
|---|---|---|
| Unitarias | pytest | Semana ISO, normalización, agregación, tasa, gates |
| Property-based | hypothesis | Agregación SQL vs Python, monotonía, rangos |
| Integración | pytest + PostgreSQL (contenedor) | Upsert, JSONB, advisory lock, rollback, outbox |
| Idempotencia | pytest | Dos corridas ⇒ hash de filas idéntico |
| Discrepancias | pytest | 1 evento por `order_id`; reintento no duplica; tasa ≤ 1 |
| Congelación | pytest | Semana congelada no se recalcula sin `--force`; `--force` deja revisión |
| Tardíos / backfill | pytest | Evento posterior al cierre ⇒ lookback actualiza |
| Caos | pytest + docker | Kill worker, drop de conexión, duplicados, payload venenoso |
| Flow | `prefect_test_harness` | Árbol completo con BD efímera |
| E2E | pytest + TestClient | Semilla 3 semanas → flow → API → totales |
| Contrato | pytest | `response_model`, códigos 401/403/404/409/503 |
| Frontend | Vitest | Selector de semana, tabla, polling, estados vacíos |
| Carga | script + dataset sintético | 1 M eventos/semana, latencia y memoria |

**Puerta de calidad del PR:** suite completa verde + cobertura ≥ 80 % en
`pipelines/weekly_performance` y en `app/reporting`.

---

## 9. Observabilidad y alertas

| Señal | Dónde | Umbral / alerta |
|---|---|---|
| `run_id`, `week_start`, etapa, duración | logs JSON + `pipeline_run_steps` | — |
| Filas extraídas/válidas/rechazadas/escritas | `pipeline_runs` | rechazo > 1 % (aviso), > 5 % (crítico) |
| `source_fingerprint` | `pipeline_runs` | Explica `skipped` |
| `quality_status` | `pipeline_runs` | `warning` ⇒ aviso; `failed` ⇒ crítico |
| Frescura `now() - max(received_at)` | métrica de corrida | > 24 h ⇒ crítico |
| Outbox pendiente | `ops.telemetry_outbox` | > 15 min ⇒ crítico |
| Corrida `running` > 2 h | watchdog | crítico |
| Semana vacía | gate G10 | aviso (esperado solo si no hay actividad) |
| Semana congelada / backfill forzado | `published_weeks` + `weekly_performance_revisions` | aviso informativo con `reason` y `forced_by` |
| Duración del flow | Prefect | > 10 min ⇒ aviso |

**SLO propuesto:** el reporte del lunes está disponible antes de las 09:00 UTC y
el pipeline tiene éxito en ≥ 99 % de las semanas, con recuperación automática en
≥ 80 % de los fallos transitorios.

---

## 10. Seguridad y permisos

- Pipeline: rol de BD con `SELECT` sobre `telemetry_events` y
  `INSERT/UPDATE/DELETE` sobre `reporting`. **Nunca** `UPDATE/DELETE` sobre
  `telemetry_events`.
- Relay del outbox: rol propio con `SELECT/UPDATE` sobre `ops.telemetry_outbox`
  e `INSERT` sobre `telemetry_events`; sin acceso a `reporting`.
- API: rol de solo lectura sobre `reporting`; `POST` auditado en
  `pipeline_runs.triggered_by`.
- Sin PII de consumidor final; solo agregados por almacén/cliente.
- Secretos en bloques de Prefect; `.env.example` documenta las claves sin valores.

---

## 11. Secuencia de PRs

| PR | Contenido | Depende de |
|---|---|---|
| 1 | Fase 0: esqueleto, DDL, test harness | — |
| 2 | Outbox + relay + instrumentación de órdenes (1.1–1.2) | 1 |
| 3 | `client_id`, `min_stock`, `POST /inventory/discrepancies` + outbox (1.3–1.5) | 2 |
| 4 | `schema_version` 2.0.0 + catálogo/allowlist (1.6) | 3 |
| 5 | Núcleo extract/normalize/aggregate/load/reconcile (2.1–2.7) | 1 |
| 6 | Resiliencia: locks, retries, watchdog, DLQ, backfill y congelación (3.1–3.9) | 5 |
| 7 | Gates de calidad + reconciliación de origen (Fase 4) | 5 |
| 8 | Prefect self-hosted + deployment, alertas, RUNBOOK (Fase 5) | 6, 7 |
| 9 | API `/reporting/*` + tests de contrato (6.1–6.5) | 5 |
| 10 | Backoffice `/reporting` + Vitest (6.6–6.7) | 9 |
| 11 | Caos, carga, property-based, docs finales (Fase 7) | todos |

**Total estimado:** 18–22 días-persona (≈ 4 semanas de un dev, menos si el
outbox y la instrumentación se paralelizan con el núcleo).

---

## 12. Decisiones cerradas y pendientes

Las 6 decisiones de §0 están cerradas y no se reabren sin un cambio de alcance
documentado. Queda **una sub-decisión menor** de implementación:

| # | Sub-decisión | Opciones | Recomendación |
|---|---|---|---|
| P1 | Dónde se registra una discrepancia en la UI | (a) botón "Registrar discrepancia" en `/inventory`; (b) campos estructurados en el formulario de `/incidents` | **(a)**: es donde están el pedido y el SKU; la incidencia se crea como efecto secundario opcional |

Notas de trazabilidad:

- **D1** se implementa en la consulta de agregación; no cambia el contrato de la API.
- **D2** sustituye la tarea 1.5 original (emisión desde incidencias) por
  `POST /inventory/discrepancies`.
- **D3** añade `published_weeks.frozen` y `weekly_performance_revisions`; el gate
  G13 bloquea el recálculo no autorizado.
- **D4** añade dos servicios a Compose (`prefect`, `prefect-worker`); la API solo
  usa `httpx` contra `PREFECT_API_URL`.
- **D5** mantiene el contrato HTTP del briefing; solo cambia la ubicación física
  del módulo.
- **D6** deja `instrumentation_since` visible en el ledger y limita el backfill a
  inbound/outbound.

---

## 13. Checklist de arranque (primera semana)

- [ ] Resolver P1 (UI de discrepancias: `/inventory` recomendado).
- [ ] Crear `pipelines/weekly_performance/` y el PostgreSQL efímero de tests.
- [ ] Implementar `ops.telemetry_outbox` + relay + test de replay.
- [ ] Migrar `SKU.client_id` y `min_stock` con backfill controlado.
- [ ] Implementar `POST /inventory/discrepancies` con evento en el mismo outbox.
- [ ] Levantar Prefect self-hosted en Compose y registrar el deployment.
- [ ] Implementar `process_week` end-to-end contra datos sembrados.
- [ ] Demostrar R1 (idempotencia) y R2 (rollback) en CI.
