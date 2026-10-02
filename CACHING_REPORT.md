# CACHING_REPORT — Optimización de rendimiento (Caché)

> Auditoría y aplicación de caché de respuestas en `services/api` (FastAPI) + optimizaciones de render en `uis/backoffice`.
> Método: seeder de carga realista → medición con middleware de timing → caché en memoria con TTL → medición *after*.

## Contexto y objetivo

Antes de tocar nada se verificó que con el dataset inicial (15 suppliers, 95 incidents, 1 user, 4 SKUs, 9 órdenes) casi todo responde rápido y la caché no aporta señal medible. Por eso el primer paso fue **inflar las tablas con datos realistas** (nombres, fechas, precios, sedes, categorías, FKs coherentes) para que filtros, joins y agregados cuesten de verdad.

## Volúmenes

| Tabla | Antes | Después (seed_perf default) |
|---|---|---|
| suppliers (TinyDB) | 15 | 400 |
| incidents (TinyDB) | 95 | 5.000 |
| users (TinyDB) | 1 | 200 |
| sku (Postgres/SQL) | 4 | 150 |
| órdenes (stock_entry + stock_exit) | 9 | 20.000 (8.000 inbound / 12.000 outbound) |

Seeder: `python seed_perf.py` (determinista, `Random(42)`, idempotente; flags `--scale` y por tabla).
> Nota: inventario (PostgreSQL/SQLModel) se midió contra SQLite local (`DATABASE_URL=sqlite:///./perf_measure.db`) para no tocar Supabase. Los tiempos de agregados/joins SQL son representativos del mismo plan de ejecución relacional; en Postgres remoto los absolutos pueden variar por red, pero la ratio cold→warm se mantiene.

## Método de medición

- Middleware HTTP de timing (`app.main`): loguea `{method} {path} → {status} | {ms}`.
- Medición programática (TestClient + `time.perf_counter`): **cold** = `cache.clear()` y una petición (≈ coste precaché, que es el coste normal de la operación) · **warm** = petición siguiente con caché caliente · mínimo de 3 cadencias.

## Evaluación coste × frecuencia × estabilidad (antes de cachear)

| Endpoint | Coste real | Frecuencia | Estabilidad | ¿Caché? |
|---|---|---|---|---|
| `GET /inventory/products` | Alto — N×2 agregados SQL por SKU (`compute_stock_by_warehouse`) | Alta (carga `/inventory`) | Cambia en cada inbound/outbound | ✅ TTL 15s + invalidación |
| `GET /inventory/orders` | Muy alto — 2 tablas + join + resolución de emails | Alta | Cambia en cada orden | ✅ TTL 15s + invalidación |
| `GET /api/suppliers` (+filtros) | Medio — scan TinyDB 400 docs | Alta | Datos casi estáticos | ✅ TTL 300s + invalidación CRUD |
| `GET /api/suppliers/{id}` | Medio | Media | Idem | ✅ TTL 300s |
| `GET /api/incidents` (+filtros) | Medio — scan 5.000 docs | Alta | Cambia en create/status | ✅ TTL 30s + invalidación |
| `GET /api/incidents/summary` | Medio — agregación 5.000 docs | Alta | Idem | ✅ TTL 30s |
| `GET /api/incidents/{id}` | Medio | Media | Idem | ✅ TTL 30s |
| Auth (`get_current_user` en cada request) | Medio — scan TinyDB 200 users **por request** | Máxima (todos los endpoints protegidos) | Cambia en role/email/edit | ✅ TTL 5s + invalidación |
| `GET /api/auth/me`, `/profiles/me` | Bajo, por-usuario | Alta | — | ❌ correctitud (401/403) |
| `GET /api/users` (admin) | Bajo | Baja | — | ❌ |
| `POST · PATCH · PUT · DELETE` | — | — | — | ❌ nunca |
| `GET /api/incidents/results/export` | Alto (pandas) | Baja | Último análisis ya en memoria | ❌ ya cacheado en `service` |
| `GET /health` | Trivial | — | — | ❌ |

## Implementación

`app/core/cache.py` — `TTLCache` thread-safe (dict + `RLock`): `get/set(ttl)/delete/delete_prefix/clear/stats`. Helper `cached(cache, key, ttl, compute)`. Caché por proceso (un worker uvicorn); con multi-worker haría falta Redis (limitación documentada).

| Dominio | Prefijo | TTL | Claves |
|---|---|---|---|
| Inventario | `inventory:` | 15s | `products`, `product:{id}`, `orders` |
| Suppliers | `suppliers:` | 300s | `list:{country|category|status|search}`, `detail:{id}` |
| Incidents | `incidents:` | 30s | `summary`, `list:{status|origin|branch|category}`, `detail:{id}` |
| Auth | `auth:` | 5s | `user:{id}` |

## Resultados medidos (volúmenes de la tabla anterior)

Tiempos en ms (mínimo de 3 cadencias; cold ≈ coste sin caché, warm ≈ con caché caliente):

| Endpoint | Cold (≈ antes) | Warm (después) | Δ |
|---|---:|---:|---:|
| `GET /api/suppliers` | 26,6 | 1,4 | **−95 %** |
| `GET /api/suppliers?country=USA` | 24,8 | 1,3 | −95 % |
| `GET /api/incidents` | 38,2 | 4,7 | −88 % |
| `GET /api/incidents?status=open` | 29,3 | 1,9 | −94 % |
| `GET /api/incidents/summary` | 28,7 | 1,1 | −96 % |
| `GET /api/incidents/1` | 26,3 | 1,1 | −96 % |
| `GET /inventory/products` | 261,5 | 1,3 | **−99,5 %** |
| `GET /inventory/products/1` | 15,3 | 1,2 | −92 % |
| `GET /inventory/orders` | 306,1 | 26,5 | **−91 %** |
| `GET /api/auth/me` | 25,5 | 14,8 | −42 %¹ |

¹ `/auth/me` warm sigue leyendo el perfil fresco (diseño); el ahorro es el scan de la tabla `users` (caché de auth). Con 200 users el escaneo costaba ~10 ms por request.

**Hit-rate** (2 requests a `/api/suppliers`): 2 hits / 2 misses, `size=2` (`auth:user:*` + `suppliers:list:*`), hit-rate 0,5 — el segundo request ya no toca TinyDB ni la lista.

## Matriz de invalidación

| Escritura | Invalida |
|---|---|
| `POST /inventory/products`, `POST /inventory/orders/inbound`, `POST /inventory/orders/outbound` | prefijo `inventory:` |
| `POST/PUT/DELETE /api/suppliers...` | prefijo `suppliers:` |
| `POST /api/incidents` | prefijo `incidents:` |
| `PATCH /api/incidents/{id}/status` (solo transición válida) | prefijo `incidents:` |
| `PUT /api/users/{id}`, `DELETE /api/users/{id}` | `auth:user:{id}` |

La invalidación solo ocurre si la escritura es exitosa (un outbound con stock insuficiente o una transición inválida **no** invalidan — verificado por tests).

## Frontend (`uis/backoffice`)

- `/inventory`: `useMemo` para `products`/`orders`/`totals`/`stockByWarehouse`/`visibleProducts` (el filtro por almacén no recalcula en cada render).
- `next/dynamic` (`ssr:false`) para modales pesados que solo se cargan al abrirse: `ProductForm`, `OrderForm`, `IncidentForm`, `StatusFlowModal`, `SupplierForm` → menos JS en la carga inicial.
- Validación: lint 0 warnings · Vitest 32 passed · build OK.

## Limitaciones y siguientes pasos

- Caché en memoria ≠ compartida: con **multi-worker** cada worker tiene su copia (correcto pero duplicado); para escalar horizontal → **Redis** (mismo API: `get/set/delete_prefix`).
- `GET /inventory/orders` warm (26 ms) sigue dominado por la **serialización JSON de 20.000 items**. Mejora opcional: paginar el historial o cachear el JSON serializado.
- `GET /api/incidents` warm (4,7 ms) igual por serialización de 5.000 items; candidato a paginación.