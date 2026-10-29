# Progress — TrackFlow

## Estado actual

| Hito | Estado | Notas |
|---|---|---|
| MILESTONE_1 — Landing + Formulario | ✅ Completado | `index.html`, `application.html`, `validation.js` |
| MILESTONE_2 — Modelado + Colecciones | ✅ Completado | `src/types/models.ts`, `src/utils/*.ts` |
| MILESTONE_3 — Talent Tracker | 🔄 En progreso | Next.js scaffolding creado, pendiente implementación de componentes |
| MILESTONE_4 — AI Engineering Tech · Infraestructura | ✅ Completado | AGENTS.md, memory-bank, .agents/rules, .agents/skills |
| MILESTONE_5 — API de inventario | 🔄 En progreso | Backend listo (BD dual TinyDB+SQL, ORM, service, router, seed, tests) — UI de inventario en backoffice completada con TDD (Vitest) |
| Pipeline de desempeño — Plan resiliente | 🔄 En progreso | F0–F6 implementadas; G1–G4 implementados y migración aplicada en Supabase. Pendiente cargar mapeo CSV y validación E2E |

## Últimas decisiones

- Proyecto base creado con `create-next-app` en `uis/talent-pipeline-tracker/`
- Tema oscuro, tipografía Space Grotesk
- API URL configurada en `.env.local`
- AGENTS.md raíz creado con flujo pre-commit y directorios protegidos
- Memory bank creado en `/memory-bank/` con projectbrief, techContext, progress
- `.agents/rules/talent-tracker-patterns.md` — regla de desarrollo (alwaysApply sobre `uis/talent-pipeline-tracker/**/*.{ts,tsx}`)
- `.agents/skills/validate-commit/SKILL.md` — skill para validación pre-commit
- `uis/website/` — app Next.js unificada (pública + backoffice)
  - `/` → Landing (hero, stats, timeline, CTA migrados de MILESTONE_1)
  - `/application` → Formulario multi-paso con validación TypeScript
  - `/backoffice` → Welcome screen con sidebar colapsable
  - `/backoffice/business-logic` → Lógica MILESTONE_2 importada desde `src/`
  - `tsconfig.json` con `@repo/*` apuntando a `../../src/` (sin copiar código)
- `analyze.py` — script de análisis CSV para el departamento de Experiencia del cliente
  - Lee `COMPANY.csv` con pandas usando procesamiento por chunks (`chunksize=10_000`)
  - Valida campos obligatorios, formato de email, estados, categorías y puntuaciones
  - Calcula totales válidos/inválidos, totalización por estado y satisfacción media de casos cerrados
  - Ofrece exportación opcional a `results.csv` y `results_invalid.csv`
- `services/api/` — Backend FastAPI para el análisis de incidentes (Experiencia del cliente)
  - `POST /api/incidents/analyze` — acepta CSV como `multipart/form-data`, devuelve resumen JSON
  - `GET /api/incidents/results/export` — devuelve el último análisis como CSV descargable (métricas resumen)
  - Lógica compartida en `app/incidents/analyzer.py` reutilizada por `analyze.py` (single source of truth)
  - Errores mapeados: 400 (vacío/formato incorrecto), 404 (sin análisis previo), 422 (falta campo `file`)
  - Último análisis guardado en memoria (se pierde al reiniciar el proceso)
  - Tests: `pytest` (8 casos en `tests/test_incidents.py`)
  - Ejecución: `uvicorn app.main:app --port 8000` desde `services/api`
  - Respuesta incluye `by_status`, `by_category`, `avg_satisfaction_cerrados` e `invalid_reasons`
- `uis/backoffice/` — App Next.js 16 independiente para el backoffice de operaciones
  - `/` → Página de análisis de incidentes con drag & drop de CSV, métricas generales, desglose por estado y categoría, satisfacción media, avisos de registros inválidos y descarga del último CSV
  - Menú lateral colapsable (Sidebar) con acceso a la página desde el menú de la aplicación
  - `next.config.ts` con rewrite: `/api/incidents/*` → `BACKEND_URL` (`http://localhost:8000` en `.env.local`)
  - `lib/api.ts` (analyzeCsv, fetchExportCsv) y `lib/types.ts` (tipos y etiquetas de razón inválida)
  - Ejecución: `npm run dev` (puerto 3000) desde `uis/backoffice`
- `services/api/` — Sistema de autenticación (User + Profile) con TinyDB
  - `POST /api/auth/login` — Login con JWT (bcrypt passwords)
  - `GET /api/auth/me` — Devuelve email + role + Profile del usuario autenticado
  - `POST /api/users` — Registro público, crea User + Profile
  - `GET /api/users` — Listar usuarios (admin)
  - `GET/PUT/DELETE /api/users/{id}` — CRUD protegido (admin o propio usuario)
  - `GET/PUT /api/profiles/me` — Perfil del usuario autenticado (solo dueño)
  - Modelos Pydantic con `UserRole` enum (admin, manager, user) en `models.py`
  - `app/core/security.py` — bcrypt hashing + JWT creation/validation
  - `app/core/dependencies.py` — `get_current_user` + `require_role()` (con `require_manager` y `require_admin`)
  - `ACCESS_TOKEN_EXPIRE_MINUTES` configurable via `.env`
  - Seed script: `seed_users.py` (crea admin@trackflow.com / admin123)
- `services/api/` — Endpoints protegidos con auth:
  - `suppliers.py` — Todos los endpoints requieren role admin/manager (401 sin token, 403 si role user)
  - `incidents.py` — Todos los endpoints requieren role admin/manager (401 sin token, 403 si role user)
  - Tests actualizados con fixture `auth_headers` que genera token admin + seed automático

## Auth — Login & Register (uis/backoffice)

- `/login` — formulario email + contraseña en `uis/backoffice`. Llama a `POST /api/auth/login`, almacena token en localStorage, redirige a `/`. Muestra error "Credenciales inválidas" en 401.
- `/register` — formulario email + contraseña + confirmar. Llama a `POST /api/users`, luego `POST /api/auth/login`, almacena token y redirige a `/`. Muestra errores de validación a nivel de campo (422/409).
- Layout minimalista centrado (sin Sidebar) con logo TrackFlow + fondo degradado.
- `AuthProvider` en `uis/backoffice/contexts/AuthContext.tsx` — envuelve toda la app desde el root layout.
- En mount: lee token de localStorage, lo valida con `GET /api/auth/me`.
- Rutas protegidas en `(protected)/layout.tsx`: redirige a `/login` si no hay sesión.
- Sidebar tiene botón "Cerrar sesión" con icono de logout.
- Loader animado con logo: capa gris se recorta desde abajo hacia arriba revelando el color (clip-path, 800ms + fade 500ms).
- Rewrites en `next.config.ts` para `/api/auth/*` y `/api/users` hacia el backend.
- `lib/api.ts` añadido `apiRequest<T>()` genérico con soporte para token Bearer.
- `uis/website` revertido a estado original (sin auth).
- Type-check, lint, build — todo OK en ambos proyectos.

## Auth — Conexión Bearer token con endpoints protegidos (uis/backoffice)

- Tras el merge del backend auth en `main`, `suppliers.py` e `incidents.py` exigen token Bearer (`require_manager`, role ≥ manager).
- Todos los helpers de `lib/api.ts` ahora aceptan opcional `token?: string | null` y envían `Authorization: Bearer <token>` cuando se proporciona: `analyzeCsv`, `fetchExportCsv`, `fetchSuppliers`, `fetchSupplier`, `createSupplier`, `updateSupplier`, `deleteSupplier` (helper interno `authHeaders`).
- Los callers pasan el token desde `useAuth()`:
  - `app/(protected)/suppliers/page.tsx` — todas las llamadas CRUD de proveedores.
  - `app/(protected)/page.tsx` — `analyzeCsv`.
  - `components/ExportLink.tsx` — `fetchExportCsv`.
- Registro crea role `user`, por lo que un usuario recién registrado recibe 403 en suppliers/incidents (diseño intencional; admin/manager acceden).
- `feature/auth-frontend` rebaseado sobre `origin/main` (incluye merge de auth #7).

## UI — ConfirmDialog reutilizable (uis/backoffice)

- Nuevo `components/ui/ConfirmDialog.tsx` reutilizable (overlay oscuro + panel slate). Props: `open`, `title`, `message`, `confirmLabel`, `cancelLabel`, `loading`, `danger`, `onConfirm`, `onCancel`. Estilo `danger` (rose) para acciones destructivas, por defecto cyan.
- `SupplierForm.tsx`: al guardar valida primero y muestra ConfirmDialog → confirmar ejecuta `onSubmit` (vía estado `pendingSubmit`).
- `Sidebar.tsx`: el botón "Cerrar sesión" abre ConfirmDialog (`danger`) antes de llamar a `logout()`. `AuthContext.logout()` sin cambios.
- `suppliers/page.tsx`: modal de eliminación inline refactorizado a `ConfirmDialog`.
- Type-check (raíz), lint y build (`uis/backoffice`) — todo OK.

## Auth — Recuperación y cambio de contraseña (services/api)

- `POST /api/auth/forgot-password` — busca por email; respuesta genérica (202) para no filtrar si el email existe; si existe y está activo genera reset-token (`type=password_reset`, duración `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES` por defecto 30) y envía enlace construido con `FRONTEND_URL` (por defecto `http://localhost:3000`, backoffice).
- `POST /api/auth/reset-password` — valida firma + exp + `type=="password_reset"` + token NO anterior a `password_changed_at` del usuario; hashea la nueva y actualiza `hashed_password` + `password_changed_at` (invalida el token y todos los emitidos antes).
- `POST /api/auth/change-password` — autenticado (`get_current_user`); verifica la contraseña actual, hashea la nueva y actualiza `hashed_password` + `password_changed_at`.
- Invalidación por estado en servidor: campo `password_changed_at` en el documento del usuario; se rechaza cualquier token-reset con `iat` anterior a ese momento. No se expone en el response `User`.
- `app/email_service.py` (nuevo) — Resend real si `RESEND_API_KEY` configurada; en desarrollo sin credenciales loguea el enlace (stub) para no romper el flujo.
- Env nuevas: `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES`, `RESEND_API_KEY`, `RESEND_FROM`, `FRONTEND_URL`. Dep `resend` añadida al venv y a `requirements.txt`.
- Config de email: `python-dotenv` + `load_dotenv()` en `app/main.py`; env se cargan de `services/api/.env` (ignorado por git). Sin `RESEND_API_KEY` → stub por consola (captura dev); con clave → modo test de Resend (envío a email verificado propio, sin dominio). Documentado en `techContext.md`.
- Tests: `pytest` (10 OK) y typecheck raíz OK.

## Auth — Frontend recuperación y cambio de contraseña (uis/backoffice)

- `/forgot-password` + `components/auth/ForgotPasswordForm.tsx` — email; muestra SIEMPRE mensaje genérico tras el envío (ignora errores) para evitar enumeración. API devuelve 202. Link en `/login` ("¿Olvidaste tu contraseña?").
- `/reset-password` + `components/auth/ResetPasswordForm.tsx` — página server awaiteando `searchParams` (Next 16) pasa `initialToken`; campos nueva + confirmar con validación de coincidencia; envía `{token,new_password}`; token inválido falla al enviar ("el enlace no es válido o ha expirado"); éxito → `router.push("/login")`.
- `/account/change-password` (bajo layout protegido) + `components/auth/ChangePasswordForm.tsx` — actual + nueva + confirmación; valida coincidencia; envía con Bearer (`useAuth().token`); 400 → "La contraseña actual es incorrecta"; éxito → mensaje y `router.push("/")`.
- `lib/auth-api.ts` — `forgotPasswordRequest`, `resetPasswordRequest`, `changePasswordRequest` (con token).
- `components/Sidebar.tsx` — link "Cambiar contraseña" junto a "Cerrar sesión".
- Rutas nuevas en build: `/forgot-password`, `/reset-password` (ƒ dinámica), `/account/change-password`. Type-check (raíz), lint y build (`uis/backoffice`) — todo OK.

## Gestor de Incidencias Centralizado (feature/incident-manager)

Feature completa (backend + frontend) para registrar y trazar incidencias operativas de TrackFlow (paquetes perdidos, fallos de carrier, discrepancia de inventario, devoluciones, etc.).

`docs/CONTEXT_centralized_incident_manager.md` define el dominio: sedes (`central`, `la_warehouse`, `la_office`, `zaragoza_warehouse`, `zaragoza_office`), categorías (9), estados (`open`, `in_progress`, `resolved`, `discarded`), orígenes (`customer`, `branch`, `internal`) y transiciones de estado.

### Backend (`services/api`)
- `models.py` — constantes del dominio (`INCIDENT_ORIGINS`, `INCIDENT_BRANCHES`, `INCIDENT_CATEGORIES`, `INCIDENT_STATUSES`, `INCIDENT_STATUS_TRANSITIONS`, `FINAL_INCIDENT_STATUSES`) y modelos Pydantic `Incident`, `IncidentCreate`, `IncidentStatusUpdate`, `IncidentSummary`. Los enum se validan a mano (400), no vía field_validator (evita 422).
- `seed_incidents.py` — seed determinista idempotente (trunca tabla `incidents` y la repuebla) que produce los **95** registros esperados: `open` 29 / `resolved` 52 / `discarded` 14; categorías `lost_parcel` 14 / `carrier_issue` 45 / `delivery_failure` 19 / `returns_issue` 17. `origin: "customer"`.
- `app/api/incidents_manager.py` — router CRUD bajo `/api/incidents` (comparte prefijo con el analizador existente sin colisión de rutas):
  - `POST /api/incidents` → crea (status default `open`); 400 descriptivo si falta campo o valor no permitido.
  - `GET /api/incidents` → lista con filtros `status`, `origin`, `branch`, `category`; `[]` con BD vacía.
  - `GET /api/incidents/{id}` → 404 si no existe.
  - `PATCH /api/incidents/{id}/status` → valida transición; `resolved`/`discarded` finales; inválida → 400.
  - `GET /api/incidents/summary` → agregados por `status`/`category`/`origin`/`branch`.
  - Todo protegido con `require_manager` (admin/manager). Ruta `/summary` declarada antes de `/{id}`.
- `app/main.py` — registra `incidents_manager_router` y añade handler global de excepción → **500** `{detail: "Internal Server Error"}`.
- Tests: `tests/test_incident_manager.py` (25 casos; fixture `_clean_incidents` trunca la tabla). Suites: **34 passed**.

**Máquina de estados (actualizada)** — `INCIDENT_STATUS_TRANSITIONS` / `FINAL_INCIDENT_STATUSES`:
`open → {in_progress, discarded}`, `in_progress → {resolved, discarded, open}`, `resolved → {in_progress}`, `discarded → {}`. Solo `discarded` es final (`resolved` puede volver a `in_progress`).

### Frontend (`uis/backoffice`)
- `lib/types.ts` — tipos `Incident`, `IncidentCreate`, `IncidentStatusUpdate`, `IncidentSummary` + mapas de etiquetas (`INCIDENT_STATUSES`, `INCIDENT_CATEGORIES`, `INCIDENT_ORIGINS`, `INCIDENT_BRANCHES`, `INCIDENT_STATUS_ORDER`) + `INCIDENT_TRANSITIONS` y helper `nextStatuses()` (mismo mapa que backend).
- `lib/api.ts` — helpers `fetchIncidents`, `fetchIncident`, `createIncident`, `updateIncidentStatus`, `fetchIncidentSummary` (Bearer token).
- `app/(protected)/incidents/page.tsx` — dashboard: 4 tarjetas de resumen por estado, filtros (status/origen/sede/categoría), tabla con badge de estado, botón "Cambiar estado" que abre el modal de flujo, y "+ Nueva incidencia".
- `components/incidents/StatusFlowModal.tsx` — modal esquemático de transición: muestra los 4 estados (Abierto → En curso → Resuelto | Descartado) con conectores; solo pulsables los estados de transición válida según `nextStatuses()`; el estado actual se destaca; al seleccionar destino se pide confirmación (`ConfirmDialog`) antes del `PATCH`.
- `components/incidents/IncidentForm.tsx` — modal de creación (solo create; la API sin actualizar campos) con selects grandes para uso táctil y confirmación.
- `components/Sidebar.tsx` — entrada "Gestor de incidencias" → `/incidents`.

Type-check (raíz), lint y build (`uis/backoffice`) OK. Ruta `/incidents` añadida al build.

## Test suite de autenticación + TESTING.md (services/api)

- Refactor estructural de `app/api/` → `app/routes/` + `app/services/`:
  - `app/routes/auth.py` (login, forgot/reset/change-password, `/auth/me`), `users.py` (registro + CRUD), `profiles.py` (`/profiles/me`), más los routers preexistentes movidos: `suppliers.py`, `incidents.py`, `incidents_manager.py`. `app/api/` eliminado.
  - `app/services/user_service.py` — capa de servicios del dominio usuario (register/authenticate/CRUD/profile/password flows). `core/dependencies.py` y `core/security.py` intactos.
  - URLs exactamente idénticas; `app/main.py` registra los routers `app.routes.*`.
- `pyproject.toml` nuevo (deps + `[dependency-groups].dev` + `[tool.pytest.ini_options]`); `requirements.txt` conserva el flujo pip/venv y añade `pytest-cov`.
- Tests nuevos por concern de auth en `tests/`: `test_register.py` (19), `test_login.py` (15), `test_token.py` (6), `test_profiles.py` (5). Cada endpoint con casos happy / edge / failure y asserts de lógica de negocio.
- `conftest.py`: `SECRET_KEY` determinista para tests, fixture autouse `_clean_db` (trunca `users`, `profiles`, `incidents` + siembra admin) y fixtures `register_user`, `user_token`, `user_headers`.
- Bug detectado al correr la suite: la tabla TinyDB `profiles` no se limpiaba entre tests → datos contaminados en 5 casos; resuelto con `_clean_db`. Documentado en TESTING.md (§5).
- Resultado: **79 passed**; cobertura total `app` **83 %**, módulo de auth ≥ 93 % (rúbrica pide ≥ 70 %).
- `TESTING.md` creado en `services/api/` (cómo ejecutar, qué cubre cada suite, plan de casos y por qué, snapshot de cobertura, hallazgo con IA). Frontends: jest en backoffice / website sin tests → bonus/no aplica ahora.

## Inventario (services/api) — MILESTONE_5

Backend del módulo de inventario con **doble conexión a BD**: TinyDB sigue siendo fuente de verdad de auth; Supabase/PostgreSQL (SQLModel) para inventario.

- `database.py` — punto único de ambas conexiones: `get_tinydb()` (data/suppliers.json) y SQLModel `engine` desde `DATABASE_URL` + `get_db()` generador (`with Session(engine)`). `load_dotenv()` al import. Deps nuevas: `sqlmodel`, `psycopg2-binary`. `DATABASE_URL=` vacía en `.env.example` (y `SUPABASE_SHARED_POOLER` como referencia del Transaction pooler).
- `models.py` — ORM `SKU` (`sku`), `StockEntry` (`stock_entry`), `StockExit` (`stock_exit`): FK `sku_id → sku.id`, `quantity: int`, `user_uuid: str` sin FK, relación `product`, sin columna `current_stock` (siempre calculado).
- `schemas.py` (nuevo) — `SKUCreate/SKURead` (con `current_stock` y `current_stock_by_warehouse`), `StockEntry/ExitCreate/Read`, `InventoryOrderItem` (item combinado de `GET /orders`). Endpoints mapean ORM → schema explícitamente.
- `app/services/inventory_service.py` — `WAREHOUSES = ("los_angeles", "zaragoza")`, `compute_stock(session, sku_id, warehouse)` con `func.coalesce(func.sum(...))`, `compute_stock_by_warehouse`, y `create_inbound/create_outbound` con validaciones antes de `session.add`: `quantity>0`, warehouse válido, SKU existe (**404**) y **check-then-write** de outbound (400 "Stock insuficiente…" sin escritura).
- `app/routes/inventory.py` — `APIRouter(prefix="/inventory")`: `GET /products`, `GET /products/{id}`, `POST /products`, `POST /orders/inbound`, `POST /orders/outbound`, `GET /orders` (con `selectinload` para evitar N+1). Escrituras exigen `require_manager`; lecturas solo `get_current_user`. `user_uuid` = id del usuario autenticado.
- `app/main.py` — incluye `inventory_router` y **lifespan** con `SQLModel.metadata.create_all(engine)` (solo si `engine` no es None).
- `seed_inventory.py` (nuevo) — seed determinista e idempotente (truncate + repoblado): 4 SKUs de sneakers y 5 entradas + 4 salidas fijas; `CLT-SNK-W-42` → stock neto **47** en Los Ángeles (coincide con la muestra del milestone). `user_uuid` fijo.
- Tests: `tests/test_inventory.py` (15 casos; fixture autouse `_clean_inventory` trunca `stock_exit/stock_entry/sku` vía sesión SQLModel). Suites: **94 passed**; cobertura total `app` **85 %**, auth ≥ 93 %, inventario ≥ 97 %.

### Decisiones de diseño (MILESTONE_5)

- **Rename `get_db()` → `get_tinydb()`**: el getter de TinyDB se renombró en `database.py`. `get_db` ahora es el generador SQLModel (`with Session(engine)`) que se inyecta por request. Todos los imports/llamadas legacy (routes de suppliers/incidents/auth, seeds, tests) usan `get_tinydb()`.
- **SQLite en tests**: `tests/conftest.py` fija `DATABASE_URL = "sqlite:///./test_inventory.db"` **antes** de importar `app.main`. Como `load_dotenv()` no sobreescribe variables ya definidas (`override=False`), los tests corren contra un fichero sqlite local y **nunca tocan Supabase**. `test_inventory.db` es artefacto borrable tras cada corrida.
- **Driver fallback**: se usa `psycopg2-binary` para el engine PostgreSQL; si faltara wheel para el Python del entorno, el fallback documentado es `psycopg[binary]` (mismo `DATABASE_URL`).
- **`current_stock` siempre calculado** desde las órdenes (inbound − outbound por almacén), nunca almacenado en `sku`. Outbound excedente → `400` con check-then-write (sin insert).

## UI de inventario (uis/backoffice) — MILESTONE_5 (TDD con Vitest)

Frontend de la página `/inventory` construido con **TDD (red → verde)** con Vitest + Testing Library. Se montó por primera vez infraestructura de tests en el backoffice (`vitest`, `@vitejs/plugin-react`, `jsdom`, `@testing-library/react`, `user-event`, `jest-dom`).

- Scripts nuevos: `test` (`vitest run`) y `test:watch`. Config en `vitest.config.ts` (jsdom + alias `@`→`.` + setup `vitest.setup.ts` con jest-dom).
- Commits por pieza (uno por unidad, cada uno con red→verde):
  - Infraestructura de tests + smoke test.
  - `lib/types.ts` — `SKU`, `SKUCreate`, `InventoryOrderCreate`, `InventoryOrderItem`, `WAREHOUSE_LABELS`, `INVENTORY_ORDER_TYPES`, `computeInventoryTotals` (total SKUs + stock por almacén).
  - `lib/api.ts` — `fetchInventoryProducts`, `fetchInventoryProduct`, `createInventoryProduct`, `fetchInventoryOrders`, `createInboundOrder`, `createOutboundOrder`. Outbound 400 **propaga el `detail` del backend** (`ApiRequestError.detail`), no `friendlyError` genérico.
  - `components/inventory/ProductForm.tsx` — modal alta de producto (name, sku_code, warehouse) validado + ConfirmDialog.
  - `components/inventory/OrderForm.tsx` — modal de órdenes inbound/outbound (sku_id, quantity, warehouse); inbound se envía directo, outbound pide ConfirmDialog; en error muestra el `detail` del backend (requisito clave del milestone).
  - `app/(protected)/inventory/page.tsx` — cabecera "Inventario", `MetricCard`/`BreakdownCard` (SKUs totales, stock total, desglose por almacén), filtro por almacén, tabla de productos con badges de stock y accions Entrada/Salida, historial de órdenes con `user_uuid`. Botones de crear/ordenar solo para admin/manager (`user.role`).
  - Wiring — rewrite `/api/inventory/:path*` en `next.config.ts` y entrada "Inventario" en `Sidebar`.
- **29 tests** en verde en `uis/backoffice` (`npm test`); typecheck raíz, lint y build OK. Ruta `/inventory` presente en el build.
- Las pruebas mockean `fetch`/`useAuth`/`lib/api`; **no requieren** Supabase ni backend corriendo.

## Contenedorización (Docker Compose)

Plataforma completa orquestada con Docker Compose y red Docker (`monorepo-dev`); los servicios se referencian por **nombre de servicio Docker** (server-side) y por puerto de host (client-side).

- `uis/Dockerfile` — `node:22-alpine`; instala deps de `website` y `backoffice` por separado (`npm ci` + clean); `CMD` ejecuta `start.sh` que lanza **website en 3000** y **backoffice en 3001** (`next dev -- -p ...`). Cambio de puertos: el backoffice pasa de 3000 → 3001 y el website de 3001 → 3000 (alineado con la referencia).
- `uis/start.sh` (nuevo) — arranca ambas apps en background y hace `wait`.
- `uis/.dockerignore` — `node_modules`, `.next`, `.env*`, `*.log`.
- `services/Dockerfile` — `uv` (multi-stage desde `ghcr.io/astral-sh/uv`) + `python:3.14-slim`; `uv pip install --system -r requirements.txt`; workdir `/app` ← `api/`; `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`.
- `services/.dockerignore` — `venv`, `__pycache__`, `*.pyc`, `.env*`, `tests`, `*.log`.
- `docker-compose.yml` (raíz) — servicios `uis` (3000:3000, 3001:3001) y `services` (8000:8000); `env_file: .env`; bind-mount de código fuente (`./uis/website`, `./uis/backoffice`, `./services/api`) y **named volumes** para `node_modules`/`.next` de ambas apps (deps Linux del contenedor; no depende del `node_modules` del host macOS). Docker es el **único método de ejecución** de la plataforma.
- URLs: `BACKEND_URL=http://services:8000` (server-side, backoffice) y `NEXT_PUBLIC_API_URL=http://localhost:8000` (client-side, website — el navegador no resuelve `services`). Mismo `.env` raíz en ambos contenedores.
- `.env` (raíz, gitignored por `.gitignore` existente) + `.env.example` (committeado): fusionan las variables de API + frontends + variables de servicio. `FRONTEND_URL` → `http://localhost:3001` (el flujo de reset vive en backoffice).
- `services/api/app/email_service.py` — default de `FRONTEND_URL` actualizado a `localhost:3001`.
- Validado: `docker compose up --build` desde la raíz; `:3000` web → "TrackFlow | Logística de última milla", `:3001` → "Backoffice | TrackFlow", `:8000/health` → ok; `services:8000` resoluble desde el contenedor `uis`; proxy `/api/auth/me` del backoffice responde 401 con detail del backend (rewrite `BACKEND_URL` funcionando).

## Serialization Audit (backend + frontend coordinado)

Auditoría y endurecimiento de serialización del backend. Documento de referencia: `docs/SERIALIZATION_AUDIT.md`.

### Backend (`services/api`)
- Todos los endpoints JSON declaran `response_model` explícito:
  - `MessageResponse` en forgot/reset/change-password; `HealthResponse` en `/health`.
- Optimización de payloads de listado (nuevos DTOs en `models.py`):
  - `GET /api/suppliers` → `list[SupplierListItem]` (drop `notes`, `service_zone`, `updated_at`).
  - `GET /api/incidents` → `list[IncidentListItem]` (`description` → `description_excerpt` ~120 chars; el detalle queda intacto).
- `GET /inventory/orders` → `InventoryOrderItem.user_email` (resuelto contra TinyDB users; fallback `""`) en lugar de `user_uuid` crudo.
- `get_current_user` devuelve whitelist segura (`id, email, is_active, role, created_at`) — ya no mete `hashed_password`/`password_changed_at` en el contexto del request.
- Nuevo `tests/test_response_contract.py` (5 casos) como regresión del mínimo: toda ruta JSON con `response_model`, ningún response_model expone passwords/hash, whitelist de `get_current_user`, payloads slim de suppliers/incidents. Excepciones explícitas: DELETE 204 y export CSV (file-download).
- Suites: **99 passed** (94 + 5 nuevos).

### Frontend (`uis/backoffice` — cambios coordinados)
- `lib/types.ts`: `SupplierListItem`, `IncidentListItem` (`description_excerpt`), `InventoryOrderItem.user_email`.
- `lib/api.ts`: `fetchSuppliers` → `SupplierListItem[]`, `fetchIncidents` → `IncidentListItem[]`.
- Suppliers: master-detail — el listado usa `SupplierListItem`; `handleEdit` hace `fetchSupplier(id)` (detail) antes de abrir el modal.
- Incidents: la tabla usa `description_excerpt`; `StatusFlowModal` tipa `IncidentListItem`.
- Inventory: la columna de órdenes muestra `user_email`.
- Tests Vitest: **32 passed** (fixtures `user_uuid` → `user_email`). Typecheck raíz, lint y build OK.

## Fix Turbopack monorepo — Docker (uis)

Problema en dev Docker: panic de Turbopack `Failed to write app endpoint /(auth)/login` y `/(public)/page` con `Caused by: - Next.js package not found` (dos panics separados, uno por app), acompañado de loop de reload en :3000 y :3001. Aparecía por primera vez tras purgar los volúmenes `.next` (caché previa enmascaraba el fallo).

**Causa raíz:** ambos `next.config.ts` fijan `turbopack.root = ../../` (→ `/uis`), y en `/uis` no hay `node_modules/next` (las deps viven en `/uis/website/node_modules` y `/uis/backoffice/node_modules`). Al reconstruir desde caché limpia, Turbopack no puede resolver `next` para su *server import map* → `Next.js version: 0.0.0` → panic. Agravante: website `next@16.2.10` vs backoffice `next@16.2.9` compartiendo el mismo root.

**Fix aplicado:**
- Backoffice alineado a `next@16.2.10` / `eslint-config-next@16.2.10` (igual a website) + `package-lock.json` sincronizado.
- `uis/Dockerfile`: bridge de resolución `mkdir -p /uis/node_modules && ln -s /uis/website/node_modules/next /uis/node_modules/next` tras el `npm ci`.
- **Solución efectiva para dev:** `next dev --webpack` en `uis/website/package.json` y `uis/backoffice/package.json` (scripts `dev`). Webpack ignora `turbopack.root` y resuelve `next` desde el `node_modules` de cada app; `@shared/*` y `@repo/*` resuelven por tsconfig `paths` y Tailwind `@source` no depende del bundler.
- Por qué no bastó el bridge para Turbopack: resolvió el panic de backoffice, pero la web seguía en `FATAL` (`get_next_server_import_map → Next.js package not found`, `Next.js version: 0.0.0`, endpoint `/(public)/page`) — el *server import map* de Turbopack no resuelve `next` desde el root compartido aunque exista el symlink. Bug conocido de Turbopack en monorepo sin workspaces (ver vercel/next.js #92540 y afines). Se mantienen el bridge y la versión alineada como higiene (si un futuro Next.js corrige el import-map, revertir `--webpack`).
- Procedimiento de deployment: `docker compose down` → borrar los 4 volúmenes `ui-node-*`/`ui-next-*` → `docker compose up --build -d`. Tras cambiar los `dev` scripts (bind-mount), basta `docker compose restart uis`.

**Verificado:** ambas apps `✓ Ready` en 16.2.10 (webpack) sin panics; `:3000` web y `:3001` backoffice 200 en `/` y `/login` estables (sin bucle de reload); `:8000/health` ok; `/docs` y `/openapi.json` sirven los contratos nuevos. E2E login admin + `GET /api/suppliers` (claves slim) y `GET /api/incidents` (`description_excerpt`). Lint, 32 tests Vitest, typecheck raíz y build backoffice OK. Nota menor en build webpack: warning `images.qualities` (pre-existente en la rama de auditoría Lighthouse).

## Fix privacidad — correos de operadores en el listado de órdenes

`GET /inventory/orders` exponía el `user_email` de todos los operadores a cualquier usuario autenticado (solo dependía de `get_current_user`). Ajuste de acceso (opción elegida: preservar el dato de auditoría solo para roles privilegiados):

- **Backend** (`services/api/app/routes/inventory.py`): `GET /inventory/orders` pasa de `get_current_user` a `require_manager` → `role user` recibe **403**. Nuevo test `test_get_orders_with_user_role_returns_403` en `test_inventory.py`.
- **Frontend** (`uis/backoffice/app/(protected)/inventory/page.tsx`): la sección "Órdenes registradas" solo se renderiza para `isManager`; `fetchInventoryOrders` se llama de forma condicional (evita el 403 que rompía el `Promise.all`). Test nuevo: un `role user` no ve la sección ni dispara el fetch.
- **Docs**: `docs/SERIALIZATION_AUDIT.md` anota el endpoint como manager/admin-only.

## Siguientes pasos

- [ ] Verificación E2E del flujo completo de inventario contra el backend real (logeado como admin/manager)
- [ ] Implementar componente `SidePanel` y `CandidateDetail` completo
- [ ] Implementar ruta dinámica `/candidates/[id]`
- [ ] Añadir paginación en `CandidateList`
- [ ] Pruebas end-to-end del flujo completo
- [ ] Conectar formulario de aplicación con API real

## Auditoría de rendimiento (Lighthouse, ambos frontends)

- Para el audit se detuvo el stack Docker (`docker compose stop`) y se corrieron builds de producción locales: website :3000, backoffice :3001, backend uvicorn :8000 (con docker compose start se restaura el entorno dev).
- `scripts/perf-audit/` — runner reproducible con **Chrome real** + Lighthouse 12.3 (programático): login admin → inyecta `trackflow_token` en localStorage para las rutas protegidas (`disableStorageReset`), emulación desktop/mobile, guarda PNG + JSON.gz + HTML.
- `audit/before/` y `audit/after/`: 5 URLs/modos (website home desktop+mobile, /application, backoffice /incidents e /inventory).
- `AUDIT.md` (raíz) — scores baseline, causes raíz, refactor candidates y log de skills. `REPORT.md` (raíz) — delta antes/después.
- Baseline: web 100/100/100/100 (LCP desktop 0.30 s); backoffice Performance 100 pero **A11y 91 (incidents) / 94 (inventory)**.
- Fixes aplicados:
  - Hero: `next/image` con `priority` + `sizes` + `quality` (resuelve `lcp-lazy-loaded`); LCP home desktop 0.30 → 0.20 s.
  - Assets re-comprimidos con `sips`: `logo.png` 213→46 KB (ambas apps), `truck-hero.jpg` 326→186 KB (mismos filenames, cero-cambio de código).
  - Contraste AA (textos → `text-slate-300`, CTAs → `bg-cyan-700`), `aria-label` en 4 selects de `/incidents`, `BreakdownCard` h3→h2.
  - **`hooks/useAsyncData.ts`** (nuevo): Custom Hook que extrae el patrón `data/loading/error`+`useEffect` duplicado en inventory/incidents/suppliers; integrado en `/inventory` (doble fetch paralelo).
  - **`shared/components/LoadingSpinner.ts`** (nuevo, código compartido raíz `@shared/*`): reemplaza el spinner duplicado entre `website/app/loading.tsx` y `backoffice/(protected)/layout.tsx`.
  - Config: `turbopack.root` → raíz del monorepo en ambos `next.config.ts`; `@source` Tailwind v4 hacia `shared/` en ambos `globals.css`; tsconfigs mapean `react` → `@types` locales (Turbopack no transpila `.tsx` fuera de la raíz de app).
- Resultado `after`: **5/5 ejecuciones 100/100/100/100** (A11y incidents 91→100, inventory 94→100). Validation: typecheck raíz OK, lint+build ambos OK, 32 tests Vitest OK.

## Optimización de rendimiento — Caché (C1–C8)

Optimización de rendimiento con caché de respuestas (backend) + render (frontend). Documento de referencia: `CACHING_REPORT.md`.

### C1 — Seeder de carga realista (`services/api/seed_perf.py`)
- Crea datos coherentes y variados para la auditoría (determinista `Random(42)`, idempotente). Volúmenes objetivo moderados: **400 suppliers / 5.000 incidents / 200 users + perfiles (TinyDB)** y **150 SKUs / 20.000 órdenes (SQL)**; el usuario #1 es admin con password `admin123`.
- Flags `--scale N` y overrides por tabla (`--suppliers`, `--incidents`, `--users`, `--skus`, `--orders`).
- **Guard destructivo** (`services/api/seed_guard.py`): todos los seeders que truncan/borran (`seed_perf.py`, `seed.py`, `seed_incidents.py`, `seed_inventory.py`) exigen `--force`/`--reset`; `--dry-run` muestra el plan sin escribir y `--allow-remote-db` (o `TRACKFLOW_ALLOW_REMOTE_SEED=1`) autoriza una `DATABASE_URL` remota. Sin flag, abortan con exit code 2 antes de tocar datos.
- Inventario requiere `DATABASE_URL`; si falta, lo omite con aviso. Para no tocar Supabase se puede override local: `DATABASE_URL=sqlite:///./perf_measure.db`.

### C2 — Infraestructura de caché (`app/core/cache.py`)
- `TTLCache` thread-safe (`RLock`): `get/set(ttl)/delete/delete_prefix/clear/stats`, instancia global `cache` y helper `cached(cache, key, ttl, compute)` (no rompe con valores falsy).
- `tests/conftest.py`: fixture autouse `_clear_cache` (limpia antes/después de cada test). `tests/test_cache.py` (9 casos).

### C3 — Caché inventario (`app/routes/inventory.py`, TTL 15s)
- `GET /products`, `GET /products/{id}`, `GET /orders` cacheados bajo `inventory:`. Invalidación de prefijo en `POST /products`, `/orders/inbound`, `/orders/outbound` (solo escritura exitosa). Tests de caché en `test_inventory.py` (19 casos).

### C4 — Caché suppliers (`app/routes/suppliers.py`, TTL 300s)
- `GET /suppliers` clave `suppliers:list:{json(filtros)}` (helper `filter_cache_key`, JSON con orden fijo → inequívoca aunque un valor contenga `|`), `GET /suppliers/{id}` clave `suppliers:detail:{id}`. Invalidación prefijo en `POST/PUT/DELETE`. `tests/test_suppliers.py` (5 casos).

### C5 — Caché incidents (`app/routes/incidents_manager.py`, TTL 30s)
- `GET /summary`, `GET /incidents` (clave `incidents:list:{json(filtros)}` vía `filter_cache_key`), `GET /incidents/{id}` bajo `incidents:`. Invalidación prefijo en `POST` y `PATCH /{id}/status` **solo si la transición es válida**. `tests/test_incident_manager.py` (29 casos).

### C6 — Caché de autenticación (`app/core/dependencies.py`, TTL 5s)
- `get_current_user` cachea el doc del usuario por `id` (`auth:user:{id}`, TTL 5s) → se aplica a todos los endpoints protegidos (evita el scan TinyDB de la tabla users por request).
- `invalidate_user_cache(id)` en `PUT/DELETE /api/users/{id}`. Tradeoff documentado: un cambio de role/desactivación tarda ≤5s en notarse. `tests/test_auth_cache.py` (4 casos).

### C7 — Frontend perf (`uis/backoffice`)
- `/inventory`: `useMemo` para products/orders/totals/stockByWarehouse/visibleProducts.
- `next/dynamic({ssr:false})` para `ProductForm`, `OrderForm`, `IncidentForm`, `StatusFlowModal`, `SupplierForm` (carga solo al abrir el modal).
- Lint 0 warnings · Vitest 32 passed · build OK.

### C8 — Reporte (`CACHING_REPORT.md`) + benchmark reproducible
- Benchmark reproducible: **`services/api/bench_cache.py`** (`TestClient` + `time.perf_counter`; cold = `cache.clear()`+petición, warm = petición siguiente, mínimo de `--repeats` cadencias, por defecto 3; imprime volúmenes leídos y admite `--json`). Comando: `DATABASE_URL=sqlite:///./perf_measure.db python bench_cache.py` (tras `seed_perf.py --force`).
- Medidas reales con los volúmenes anteriores (SQLite local para inventario): `GET /inventory/products` 261,5→1,3 ms (−99,5 %), `GET /inventory/orders` 306,1→26,5 ms (−91 %), suppliers −95 %, incidents/summary −96 %, auth scan −42 %. Matriz de invalidación, TTLs, hit-rate y limitaciones (caché en memoria = 1 worker; paginar/serializar-JSON para listas de 20k).
- Suites: **120 passed** en `services/api` (inc. 30 tests nuevos de caché) · typecheck raíz OK.

## Telemetría — Plan y esquemas de eventos (`docs/telemetry/`)

Entregable de diseño (solo documentación, sin instrumentación en runtime):

- `docs/telemetry/telemetry-plan.md` — Plan de Telemetría en inglés:
  - **Fase 1**: flujo de inventario mapeado end-to-end (login → `/auth/me` → `/inventory` → `OrderForm` → validación → `ConfirmDialog` → `POST /orders/{inbound|outbound}` → `inventory_service` → commit → `reload`), ≥5 puntos de instrumentación con anclaje `file:line`, más secciones de auth, rendimiento, errores frontend y navegación. Golden rule por evento.
  - **Fase 2**: Event Envelope estándar (`event_id`, `timestamp`, `session_id`, `user_id`, `event_type`, `schema_version`, `request_id`, `source`, `app`, `properties`) y catálogo de 17 eventos con allowlist de `properties`.
  - **Fase 3**: clasificación stream/batch por urgencia, estrategias throttle/debounce para eventos de alta frecuencia (`page_view`, `api_response_time`) y riesgos/exclusiones de privacidad y coste.
  - **Gaps documentados**: el modelo `SKU` no tiene `client_id` ni `product_category`; no existe `min_stock`; no hay endpoint de edición directa de stock (el evento se define como guarda); las discrepancias se anclan a incidencias `inventory_discrepancy`.
- `docs/telemetry/event-schemas.json` — JSON Schema 2020-12 con `envelope` + `definitions` + 17 `events`; cada evento declara `source`, `processing`, `golden_rule`, `required_properties` y `allowlist` (`additionalProperties: false`). Validado con `JSON.parse` y comprobación de los 5 eventos obligatorios.

### Ampliación — catálogo de incidencias + clasificación obligatorio/oportunidad

Ampliación del entregable de telemetría (inglés) sobre la base anterior:

- Catálogo reorganizado en los dos grupos que pide el brief: **obligatorio** (`obligatorio`, las 5 métricas de inventario del contexto) y **oportunidad identificada** (`oportunidad identificada`, exploración propia: auth, rendimiento, navegación e incidencias).
- **Flujo de incidencias instrumentado** (§4.8) con anclajes `file:line`: `incident_form_opened` (`incidents/page.tsx:146`), `incident_created` / `incident_validation_failed` (`incidents_manager.py:194`/`:40`), `incident_status_change_opened` (`incidents/page.tsx:264` → `StatusFlowModal.tsx`), `incident_status_changed` (`StatusFlowModal.tsx:99` → `incidents_manager.py:223`) y `incident_transition_rejected` (`incidents_manager.py:244-254`).
- `event-schemas.json` → **23 eventos** (17 + 6 de incidencias); nuevas `definitions` `incident_category|status|branch|origin` (enums tomados de `services/api/models.py`); `envelope.event_type` enum y `version` 1.1.0.
- Throttle/dedupe añadido para `incident_validation_failed` / `incident_transition_rejected` (ventana 60 s por firma) además de `page_view` / `api_response_time`.
- §6.3 gana una subsección **"Considered and discarded events"** (p. ej. texto completo de la incidencia por PII, snapshot periódico de stock por coste/derivable, heatmaps) junto a las exclusiones de datos ya existentes.

## Telemetría — Captura en runtime (Fase 1 · 2 · 3)

Implementación de la capa de captura sobre el plan de telemetría. El **envelope queda congelado** (10 campos); `environment` y `consent` viajan como **metadatos de transporte** (headers + query params), no en el body.

### Fase 1 — Colector backend (`services/api`)
- `models.py` — enums `TelemetrySource`, `TelemetryApp`, `TelemetryWarehouse` (`los_angeles`/`zaragoza`), `TelemetryEventType` (23) + modelo Pydantic `TelemetryEvent` (valida `event_id` UUIDv4, `timestamp` ISO-8601, `session_id` no vacío, `schema_version` semver y enums cerrados).
- `schemas.py` — `TelemetryBatch {events}`, `TelemetryIngestResponse {received}`.
- `app/routes/telemetry.py` — `POST /telemetry/events` (sin auth; acepta eventos pre-login): registra en log el nº recibido + contador por `event_type`, y devuelve `200 {"received": N}`. Registrado en `main.py`.
- `TELEMETRY_ENDPOINT` leída por el backend (logueada en lifespan, sin uso en runtime todavía).
- Tests: `tests/test_telemetry.py` (13).

### Fase 2 — Servicio de telemetría frontend (`uis/backoffice`)
- `src/services/telemetry.ts` — **única función pública de tracking `track(eventType, properties)`**; inyecta el envelope automáticamente (`event_id`, `timestamp`, `session_id`, `user_id`, `schema_version`, `request_id`, `source:"frontend"`, `app:"backoffice"`).
- Cola local; **batch a 20 eventos o debounce 10 s**; **`navigator.sendBeacon` en `visibilitychange` (oculto)**; **reintentos 3× con backoff exponencial** y descarte del lote al agotar.
- `AuthContext` conecta la sesión (`startTelemetrySession` en login/registro, `setTelemetryUserId`, `clearTelemetrySession` en logout). `contexts/TelemetryProvider.tsx` registra el listener de ciclo de vida y monta el banner.
- `next.config.ts` — rewrite `/api/telemetry/:path*` → `${backend}/telemetry/:path*`.
- Env (`.env.local` + `.env.example` raíz + `docker-compose.yml`): `NEXT_PUBLIC_TELEMETRY_ENDPOINT=/api/telemetry/events`, `NEXT_PUBLIC_TELEMETRY_SAMPLE_RATE=1.0`, `NEXT_PUBLIC_TELEMETRY_ENABLED=false`.

### Fase 3 — Cinco barreras de seguridad (frontend + backend, defense in depth)
Pipeline en `track()`: `consent → sanitize → allowlist → sampling → enqueue → environment-gate → transport`.
- **Consentimiento**: `src/telemetry/consent.ts` + `components/telemetry/ConsentBanner.tsx`; solo bloquea eventos **analíticos** (`requiresConsent`), los de seguridad/operativos se emiten igual.
- **Limpieza**: `src/telemetry/sanitize.ts` y `app/telemetry/sanitize.py` (redactan email/teléfono/URL/JWT, eliminan claves sensibles, truncan a 300).
- **Lista blanca**: `src/telemetry/allowlist.ts` y `app/telemetry/barriers.py` (`filter_properties`).
- **Muestreo**: `src/telemetry/sampling.ts` determinista por `(session_id, event_type)`, solo eventos de alta frecuencia; 100% por defecto con override `NEXT_PUBLIC_TELEMETRY_SAMPLE_RATE`.
- **Separación de entornos**: `src/telemetry/environment.ts` (solo envía en producción salvo `NEXT_PUBLIC_TELEMETRY_ENABLED=true`); el colector descarta `development`/`test` salvo `TELEMETRY_ALLOW_NON_PRODUCTION=1`.
- **Metadatos de transporte**: `fetch` envía `X-Telemetry-Environment` / `X-Telemetry-Consent` / `X-Telemetry-App-Version`; `sendBeacon` (sin headers) los añade como query params.
- **Fuente única**: `shared/telemetry/schema.ts` + `shared/telemetry/catalog.ts`; espejo `services/api/app/telemetry/catalog.py` con test de paridad contra `docs/telemetry/event-schemas.json` (`tests/test_telemetry_catalog.py`).
- Tests nuevos: `uis/backoffice/src/services/__tests__/telemetry.test.ts` (18), `services/api/tests/test_telemetry_barriers.py` (11), `tests/test_telemetry_catalog.py` (6).

### Instrumentación de eventos (capa de captura)

- **Frontend (`uis/backoffice`)**: `hooks/usePageView.ts` (`page_view`); `AuthContext` (`session_started`, `session_expired`, `login_succeeded`); `LoginForm` (`login_failed`); `OrderForm` (`order_form_opened`, `order_form_abandoned`); `incidents/page.tsx` (`incident_form_opened`, `incident_status_change_opened`); `TelemetryProvider` (`frontend_error_uncaught` vía `window.onerror` / `unhandledrejection`).
- **Backend (`services/api`)**: `app/telemetry/emitter.py` (envelope + log); `inventory_service` emite **`inbound_order_created`**, **`outbound_order_created`** (obligatorios) y `outbound_rejected_insufficient_stock`. Logging de runtime habilitado con `logging.basicConfig(level=LOG_LEVEL)` en `app/main.py`.
- **Gaps documentados** (prerrequisitos inexistentes): `stock_threshold_triggered` (falta `min_stock` por SKU), `direct_stock_edit_rejected` (no hay endpoint de edición directa), `inventory_discrepancy_detected` (requiere datos de producto en la auditoría); eventos backend de incidencias y `api_response_time` quedan para la instrumentación server-side.
- Tests: `services/api/tests/test_inventory_telemetry.py` (3) verifica la emisión de los eventos de inventario.
- Verificado: `pytest` **160 passed**; Vitest **51 passed**; root typecheck, lint y build (`uis/backoffice`) OK.

## Telemetría — Almacenamiento real de eventos (stub → endpoint de ingesta)

El stub del colector se sustituye por el endpoint real que valida, persiste y reporta. **El frontend no cambia**: misma URL, mismo body, y `transport.ts` solo comprueba `response.ok`.

### Contrato y validación parcial

- `TelemetryBatch` acepta `events: list[Any]` en crudo; el body completo solo devuelve **422** si `events` no es una lista (o falta: `{}` → ceros).
- Cada elemento se valida con `TelemetryEvent.model_validate` dentro de un `try/except ValidationError`: un evento inválido suma a `rejected` y el resto del lote continúa.
- `TelemetryIngestResponse` pasa a `{received, stored, rejected}` (`received == stored + rejected`). El frontend ignora las claves nuevas.
- El contrato Pydantic valida el **envelope**, no los `required_properties` del catálogo (documentado; si se exigieran hoy se rechazarían los eventos de inventario que aún no emiten `client_id`/`product_category`).
- Log de rechazo desglosado: `invalid` (por campo), `environment`, `consent` y `duplicates`.

### Persistencia en Supabase (bulk insert)

- `models.py` — `TelemetryEventRecord` (`telemetry_events`): `event_id uuid` PK, `timestamp`/`received_at` `timestamptz`, `event_type`, `service` (derivado de `app`), `session_id`, `user_id`, `schema_version`, `request_id`, `source` y `tags jsonb`.
- `tags` guarda solo las `properties` que pasan sanitización + allowlist. El envelope nunca se serializa como un único JSON.
- `app/telemetry/ingest.py` (nuevo) — parseo por ítem, dedupe intra-lote por `event_id`, mapeo a columnas y **un único** `INSERT ... ON CONFLICT (event_id) DO NOTHING` (executemany) + un `commit()`. El `on_conflict` se elige por dialecto (`postgresql`/`sqlite`).
- Idempotencia: reintentar el mismo lote no duplica filas; se reporta `stored: 0`.
- `received_at` lo pone la BD con `now()` (no viaja en el INSERT); `timestamp` siempre viene del evento y se normaliza a UTC.
- `user_id`/`request_id` vacíos o con espacios se normalizan a `NULL`.
- `app/telemetry/barriers.py` — nuevo `apply_barriers()` que devuelve los eventos aceptados; `process_events()` se conserva como wrapper para los tests previos.
- `app/routes/telemetry.py` — handler real con `Depends(get_db)`; sin cambios de URL ni de auth.
- Tabla creada/alineada en Supabase (ya existente): PK, `NOT NULL`, `tags` default `'{}'::jsonb`, checks e índices (`timestamp`, `service`, `session_id`, `(event_type, timestamp)`).

### Tests y verificación

- `tests/test_telemetry_storage.py` (18 casos): columnas fijas + `tags` filtradas, `service` desde `app`, lote mixto, ítems no-objeto, 422 de envelope, PII redactada, `{}` en `tags`, duplicados intra-lote y entre peticiones, **una sola sentencia INSERT para 20 eventos** (listener de SQLAlchemy), normalización de vacíos, gates de entorno/consentimiento.
- `test_telemetry.py` y `test_telemetry_barriers.py` actualizados al nuevo contrato (los 422 por evento pasan a rechazo parcial).
- Verificado contra Supabase real en transacción con rollback: `rowcount = 1` para dos filas con el mismo `event_id`, `tags` JSONB correcto y `received_at` rellenado por `now()`.
- Suites: **178 passed** en `services/api`. Frontend intacto (sin cambios en `uis/` ni `shared/`).

## Telemetría — Reporte técnico operativo (Phase 4) + dashboard

`telemetry_events` se transforma en métricas **técnicas/operativas** con Pandas y se expone en `GET /telemetry/report`. No hay KPIs de negocio (ventas, conversión, ingresos): volumen, errores, latencia y autenticación.

### Backend (`services/api`)

- `app/telemetry/analysis.py` (nuevo) — pipeline por métrica: **load** (SQL con push-down de `event_type IN (...)` y `timestamp >= start` / `< end`) → **refine** (tags + columnas derivadas) → `pd.to_datetime(..., utc=True)` → `date` (`YYYY-MM-DD`) → `groupby` → agregación → `list[dict]`.
  - `fetch_events()` devuelve solo `event_type`, `timestamp`, `tags`; nunca escanea la tabla completa.
  - 5 funciones puras `(session, start_date, end_date)`:
    - `events_per_day` — ¿qué eventos ocurren y con qué volumen? (`groupby date + event_type`, count).
    - `error_rate_by_day` — ¿los fallos crecen respecto al tráfico? (`is_failure` sobre `FAILURE_EVENT_TYPES`, `error_count/event_count`).
    - `errors_by_type` — ¿dónde se concentran los fallos? (`date + event_type`, count).
    - `latency_per_day` — ¿se degrada la latencia? (`api_response_time.tags.duration_ms` → media, p50, p95, muestras).
    - `auth_failure_rate` — ¿aumentan los logins fallidos? (`login_failed/(login_failed+login_succeeded)`, `[0,1]`).
  - Sin bucles por fila para agregar; periodo vacío → `[]`.
  - `FAILURE_EVENT_TYPES`: `direct_stock_edit_rejected`, `stock_validation_failed`, `outbound_rejected_insufficient_stock`, `login_failed`, `incident_validation_failed`, `incident_transition_rejected`, `frontend_error_uncaught`.
- `schemas.py` — `TelemetryPeriod` (alias `from`/`to`) y `TelemetryReportResponse` (`period`, `metrics`).
- `app/routes/telemetry.py` — `GET /telemetry/report` público, params opcionales `start_date`/`end_date` (ISO 8601 UTC). Defaults: últimos 7 días (`now` truncado a minuto para que el default también cachee). `start >= end` → 400. Caché en memoria `telemetry:report:<start>:<end>` con TTL **60 s** reutilizando `app/core/cache.py`; en hit no se ejecuta Pandas.
- `tests/test_telemetry_report.py` (14 casos): agrupaciones por fecha, error rate, errores por tipo, latencia/p95, auth failure rate, conversión UTC antes de agrupar, periodo vacío, push-down SQL (`EVENT_TYPE IN` + `TIMESTAMP >=`), `end` exclusivo, defaults de 7 días, 400 y cache hit (spy sobre `build_metrics`).

### Frontend (`uis/backoffice`)

- `lib/types.ts` — `TelemetryReport`, filas de las 5 métricas y `computeTelemetrySummary()` (totales y tasas ponderadas por sus denominadores).
- `lib/api.ts` — `fetchTelemetryReport({ start_date, end_date })` contra `/api/telemetry/report` (rewrite existente; endpoint público).
- `app/(protected)/telemetry/page.tsx` — rango de fechas (por defecto últimos 7 días), `period.from`/`period.to`, tarjetas resumen y tablas con barras CSS para eventos por día, tasa de error, errores por tipo, latencia y fallos de login. Estado vacío cuando no hay eventos.
- `components/Sidebar.tsx` — entrada “Telemetría” → `/telemetry`.
- Tests: `lib/__tests__/api.test.ts`, `lib/__tests__/types.test.ts` y `app/(protected)/telemetry/page.test.tsx` (periodo, resumen, 5 secciones, cambio de rango, vacío y error con reintento).

### Verificación

- `pytest` en `services/api`: **192 passed** (178 + 14 nuevos).
- `uis/backoffice`: **59 tests Vitest**, lint y build OK; ruta `/telemetry` en el build.
- Tipo-check raíz (`npm run typecheck`) OK.
- Contra Supabase real (`2026-10-25T00:00:00Z` → `2026-10-26T00:00:00Z`, 27 eventos): la respuesta incluye las 5 métricas; cold ≈ 443 ms, warm ≈ 3 ms (caché 60 s).

## Backoffice — Paginación de tablas y sidebar fija

Dos mejoras de UI en `uis/backoffice` (solo frontend, sin cambios de API).

### Sidebar siempre visible

- `app/(protected)/layout.tsx` — shell `flex h-dvh overflow-hidden`: el scroll pasa a `<main className="flex-1 overflow-y-auto">`. Antes (`min-h-screen` + `overflow-auto`) el `<aside>` crecía con el contenido y el bloque inferior del sidebar (“Cerrar sesión”) quedaba fuera del viewport en páginas largas.
- `components/Sidebar.tsx` — `aside` con `h-full shrink-0`; `nav` con `flex-1 overflow-y-auto` (si el menú crece, scrollea solo esa zona); bloque de usuario/logout con `mt-auto shrink-0`.

### Paginación reutilizable (cliente)

- `hooks/usePagination.ts` (nuevo) — `usePagination(items, { initialPageSize = 25, resetKey })`: `page`, `setPage`, `pageSize`, `setPageSize` (vuelve a página 1), `total`, `totalPages`, `pageItems`, `start`, `end`. Ajusta el estado durante el render para acotar la página si la lista se acorta y para resetear a 1 cuando cambia `resetKey` (filtros).
- `components/ui/Pagination.tsx` (nuevo) — texto “Mostrando X–Y de Z <sustantivo>”, anterior/siguiente, números con elipsis (`aria-current="page"`), selector 10/25/50 (oculto si `total <= 10`), navegación oculta con una sola página. `scrollTargetRef` lleva la tabla a la vista al cambiar de página.
- Aplicado a las 5 tablas: `suppliers` (reset por país/estado/categoría/búsqueda), `incidents` (reset por los 4 filtros), `inventory` (productos con reset por almacén, e historial de órdenes, cada uno con su propia paginación) y `telemetry` (`PagedSection` genérica con paginación independiente por métrica, reset al cambiar el rango de fechas).
- Contenedores de tabla: `overflow-x-auto` + `scroll-mt-6` (scroll horizontal en pantallas estrechas en lugar de deformar el layout).

### Verificación

- `uis/backoffice`: **73 tests Vitest** (14 nuevos: `hooks/usePagination.test.ts` 7, `components/ui/Pagination.test.tsx` 6, integración de paginación en `inventory/page.test.tsx` 1), lint y build OK; typecheck raíz OK.
- Comprobado contra el stack Docker real (admin, :3001): `/incidents` 95 registros → 25 por página (“Mostrando 1–25 de 95” → “26–50”), `aside` = altura del viewport y “Cerrar sesión” visible con `<main>` scrolleado al final; `/inventory` 25 de 28 órdenes; `/suppliers` 15 de 15 y `/telemetry` paginada por sección.
- Pendiente/futuro: paginación **server-side** (`limit`/`offset` + `total`) para no descargar listados completos (hoy `GET /suppliers`, `/incidents`, `/inventory/products` y `/inventory/orders` devuelven todo).

## Pipeline de desempeño de negocio — Plan resiliente (PIPELINE_2)

Entregable de **diseño/planificación** (sin código de pipeline todavía). El briefing
`docs/pipeline/PIPELINE_2.md` es idéntico a `PIPELINE_1.md`; se interpreta como una
segunda iteración centrada en resiliencia sobre el diseño previo
(`data/pipelines/PIPELINE_DESIGN.md`).

- `docs/pipeline/PIPELINE_2_PLAN.md` (nuevo) — plan de ejecución en 8 fases
  (F0 fundaciones → F7 endurecimiento), con criterios medibles R1–R10, matriz de
  fallos, 13 quality gates, modelo de datos ampliado, observabilidad/SLO, 11 PRs
  secuenciados y estimación de **18–22 días-persona**.
- **Brechas de origen identificadas** (bloqueantes de producción): `emitter.py`
  solo escribe en log; `SKU` no tiene `client_id`; no existe `min_stock`;
  `inventory_discrepancy_detected` no está instrumentado y `IncidentCreate` no
  tiene campos estructurados (`order_id`, `sku_code`, cantidades).
- **Decisiones cerradas:**
  - **D1** — throughput con `count(distinct coalesce(order_id, event_id))`
    (pedidos únicos, inmune a reintentos).
  - **D2** — un evento de discrepancia por pedido afectado, emitido desde
    `POST /inventory/discrepancies` (discrepancia SQL + outbox en la misma
    transacción); la incidencia queda como efecto secundario opcional.
  - **D3** — congelar semanas tras 2 corridas exitosas (W+2); backfill explícito
    con `--force --reason` y snapshot en `weekly_performance_revisions`.
  - **D4** — Prefect self-hosted en Docker Compose (servidor + worker); migrable
    a Cloud cambiando `PREFECT_API_URL`.
  - **D5** — módulo en `services/api/app/reporting/` (mapeo documentado desde el
    `services/reporting/` del briefing).
  - **D6** — backfill solo inbound/outbound desde `stock_entry`/`stock_exit`;
    quiebres y discrepancias empiezan en `instrumentation_since`.
- **Pendiente (P1):** ubicación de la UI de discrepancias — recomendado un botón
  "Registrar discrepancia" en `/inventory` (la incidencia se crea como efecto
  secundario).
- **Siguiente paso:** Fase 0 — esqueleto `pipelines/weekly_performance/`, DDL de
  `reporting.*` y PostgreSQL efímero para tests.

## Pipeline de desempeño — F0 + F1 implementadas (`pipelines/weekly_performance/`)

Implementación del esqueleto y del núcleo flows/tasks contra datos sembrados.
Todavía **no** hay instrumentación de origen: el pipeline lee `telemetry_events`
tal cual y en producción seguirá fallando el gate de cobertura hasta cerrar
G1–G4.

### Estructura y modelo

- `settings.py` — `DATABASE_URL_PIPELINE` (fallback `DATABASE_URL`), lookback,
  esquemas `reporting`/`ops`, `PIPELINE_INSTRUMENTATION_SINCE`, eventos y
  almacenes.
- `db.py` — engine SQLAlchemy con `pool_pre_ping`, UTC en PostgreSQL y caché
  limpiable para tests.
- `schema.py` — tablas portables PostgreSQL/SQLite: `weekly_warehouse_client_performance`,
  `pipeline_runs`, `pipeline_run_steps`, `weekly_performance_rejects`,
  `week_watermarks`, `published_weeks`, `weekly_performance_revisions`,
  `telemetry_events` (solo lectura) y `ops.telemetry_outbox`.
- `sql.py` — DDL idempotente (`CREATE SCHEMA IF NOT EXISTS`, `create_all`) y
  helpers para tests.
- `core.py` — lógica pura sin Prefect: `resolve_target_weeks`, `extract_week`
  (push-down SQL), `normalize_validate` (dedupe por `event_id` + cuarentena),
  `aggregate_kpis` (D1: `count(distinct coalesce(order_id, event_id))`),
  `evaluate_quality` (G1–G6, G9, G12), `load_week` (upsert atómico),
  `reconcile_week`, ledger, watermarks, congelación y `execute_week`.
- `tasks.py` — tasks de Prefect; `extract` con 3 reintentos y backoff, `load` y
  `reconcile` con 2.
- `flow.py` — `process_week` (subflow) y `weekly_flow` (padre; una semana rota
  no aborta las demás).
- `cli.py` / `__main__.py` — `run` y `backfill` con `--week`, `--lookback`,
  `--force --reason`, `--dry-run`, `--json`.
- `pyproject.toml`, `Dockerfile` (contexto raíz) y `README.md`.

### Verificación

- `services/api/venv/bin/python -m pytest pipelines/weekly_performance/tests -q`
  → **26 passed**. Cubre fronteras ISO (incluido cambio de año), normalización y
  cuarentena, agregación contra totales conocidos, idempotencia del upsert,
  skip por fingerprint, congelación, reconciliación, gates, acumulación de 3
  semanas y smoke del flow.
- E2E manual con SQLite sembrado:
  `python -m pipelines.weekly_performance backfill --week 2026-07-06 --json`
  → `success`, 10 extraídas / 10 válidas / 2 escritas; segunda corrida
  `skipped` por fingerprint. Totales: LA 150/3/1/1 (rate 0.333333), ZG 70/2/0/0.
- Regresión API: `services/api` → **192 passed** (Prefect instalado solo en el
  venv local, no se añadió a `requirements.txt`).
- `compileall` OK. Sin cambios en frontends.

### Pendiente

- Cerrar G1–G4 (outbox, `client_id`, `min_stock`, `POST /inventory/discrepancies`).
- F2 resiliencia (advisory lock, watchdog, DLQ, circuit breaker, congelación
  operativa), F3 idempotencia avanzada, F4 backfill histórico, F5 Prefect
  self-hosted + deployment, F6 API `/reporting/*` y backoffice.

## Pipeline de desempeño — F2 + F3 implementadas (resiliencia e idempotencia)

### Resiliencia (F2)

- `locks.py` — advisory lock de sesión por `(pipeline, week_start)`
  (`pg_try_advisory_lock` / `pg_advisory_unlock`); no-op en SQLite. El lock se
  mantiene durante toda la corrida y se libera al cerrar la conexión si el
  worker muere.
- `execute_week` ahora: marca zombies → adquiere lock → comprueba circuit
  breaker → arranca la corrida. Una semana bloqueada devuelve `skipped: locked`.
- `mark_zombie_runs` — watchdog: `running` con `heartbeat_at` > 2 h ⇒ `failed`;
  `record_step` renueva el heartbeat en cada etapa.
- `source_is_tripped` — circuit breaker: 3 fallos consecutivos de `extract` ⇒
  `source_unavailable`; `--force` lo salta para permitir recuperación manual.
- `replay_rejects` + CLI `replay --run-id` — reprocesa la semana y marca los
  rechazos como rejugados.
- `freeze_week`, `maybe_freeze_week` y `snapshot_week` — auto-freeze tras 2
  corridas exitosas posteriores al cierre; al forzar una semana congelada se
  guarda una revisión inmutable con `reason` y `forced_by`.
- `tasks.py` — `retry_condition_fn`: solo reintenta `OperationalError`,
  `DBAPIError` con conexión invalidada, `TimeoutError` y `ConnectionError`.
- `prefect.yaml` — deployment base; el work pool se crea con
  `--concurrency-limit 1` (segunda barrera además del advisory lock).
- CLI nueva: `replay`, `relay`, `freeze`, `watchdog`.

### Idempotencia (F3)

- Dedupe por `event_id` en `normalize_validate` (además de la PK de origen).
- Semana calculada desde el `timestamp` del evento, nunca desde `now()`.
- Upsert por `(warehouse, client_id, week_start)` + `reconcile_week`.
- `week_watermarks` + fingerprint ⇒ `skipped: fingerprint_unchanged`.
- `outbox.py` — relay `FOR UPDATE SKIP LOCKED` (PostgreSQL) con
  `ON CONFLICT (event_id) DO NOTHING`; reintentar no duplica y los pendientes
  quedan para la siguiente pasada.
- Discrepancias: una por `order_id` (D2), tasa ≤ 1.

### Verificación

- `pytest pipelines/weekly_performance/tests` → **39 passed, 3 skipped**
  (los 3 de PostgreSQL se saltan sin `TEST_POSTGRES_URL`).
- Con PostgreSQL 16 real (contenedor efímero, `TEST_POSTGRES_URL`):
  **3 passed** — UUID, JSONB, upsert, advisory lock exclusivo y relay
  idempotente verificados.
- `npm run typecheck` OK y `compileall` OK.
- API sin cambios; sigue en **192 passed**.

### Pendiente

- F5 Prefect self-hosted + worker + alertas.
- F6 API `/reporting/*`, backoffice y lectura degradada (`stale`).
- Instrumentación de origen G1–G4 (sigue siendo el bloqueante de producción).

## Pipeline de desempeño — F4 implementada (calidad y reconciliación)

- **G7** — variación de volumen > ±50 % vs semana anterior ⇒ `warning`.
- **G8** — caída de combinaciones activas > 30 % ⇒ `warning`.
- **G11** — frescura de fuente > 24 h ⇒ `warning`; solo se evalúa en la última
  semana cerrada (en backfill histórico la antigüedad es esperada).
- `previous_week_kpis()` lee los KPIs persistidos de `W-1` para G7/G8.
- `source_freshness_hours()` calcula la antigüedad del `received_at` más reciente.
- `reconcile_source()` compara por día `stock_entry`/`stock_exit` con los eventos
  `inbound_order_created`/`outbound_order_created`; devuelve deltas y `ok`.
- `reconcile_source_task` + `source_reconciliation_flow` (cron diario 07:00 UTC)
  y CLI `reconcile-source --days 7`.
- `schema.py` añade vistas de solo lectura de `stock_entry`/`stock_exit`;
  `sql.create_inventory_tables()` solo se usa en tests.
- Tests nuevos en `tests/test_data_quality.py` (G7, G8, G11, W-1 y
  reconciliación con/sin eventos faltantes).

### Verificación F4

- `pytest pipelines/weekly_performance/tests` → **45 passed, 3 skipped**.
- `compileall` y `git diff --check` OK.

## Pipeline de desempeño — F5 implementada (orquestación y operación)

- `docker-compose.yml` — perfil opcional `prefect` con:
  - `prefect-server` (UI/API en `:4200`, SQLite en volumen `prefect-data`,
    healthcheck y `restart: unless-stopped`);
  - `prefect-init` (crea el work pool `trackflow-pool`);
  - `prefect-deploy` (despliega `prefect.yaml` con concurrencia 1);
  - `prefect-worker` (imagen del pipeline, `DATABASE_URL_PIPELINE` y alertas).
- `prefect.yaml` — deployments `weekly-prod` (lunes 08:00 UTC) y
  `source-reconciliation-daily` (07:00 UTC), `concurrency_limit: 1`.
- `alerts.py` — `send_alert()` con `PIPELINE_ALERT_WEBHOOK`; se invoca en fallo
  de quality gate, excepción, advertencia, circuit breaker y fuente bloqueada.
  Sin webhook solo loguea; nunca tumba el pipeline.
- `flow.py` — artefacto Markdown por corrida (`create_markdown_artifact`) solo
  dentro de un flow run real.
- `RUNBOOK.md` — 9 procedimientos (corrida fallida, semana vacía, rechazo
  masivo, backfill congelado, replay, lock colgado, circuit breaker, Prefect
  caído, alertas).
- `Dockerfile` — instala `httpx` y copia `prefect.yaml` al root de la imagen.
- Imports de `flow.py`/`tasks.py` pasan a absolutos para que Prefect pueda
  cargar el entrypoint por ruta de archivo.

### Verificación F5

- `pytest pipelines/weekly_performance/tests` → **46 passed, 3 skipped**.
- `docker compose --profile prefect config` OK.
- `prefect deploy --all` parsea `prefect.yaml` y carga `weekly-prod` (falla solo
  porque el work pool no existe en el servidor temporal, como se espera).
- `compileall` y `git diff --check` OK.

## Pipeline de desempeño — F6 implementada (API y backoffice)

### Backend (`services/api`)

- `app/reporting/` nuevo:
  - `schemas.py` — `WeeklyPerformanceEntry`, `WeeklyPerformanceResponse`
    (incluye `frozen`, `stale`, `computed_at`), `PipelineRunLatest`,
    `PipelineRunTriggerRequest/Response`.
  - `service.py` — consultas de solo lectura sobre `reporting.*` con
    prefijo de esquema según dialecto; `ReportNotFound` para 404;
    `has_running_run()` para 409.
  - `prefect_client.py` — `httpx` contra `PREFECT_API_URL`; busca el deployment
    `weekly-prod`, crea el flow run y traduce fallos a `PrefectUnavailable`
    (503). Soporta `PREFECT_API_KEY`.
  - `router.py` — 3 endpoints con `require_manager` y caché en memoria
    (`GET` semanal 60 s, `latest` 5 s).
- `main.py` registra `reporting_router`.
- `services/api/README.md` documenta el módulo.
- `tests/test_reporting.py` (12 casos): auth 401/403, última semana, filtro por
  semana, `frozen`/`stale`, 404, `latest`, 409, 503, 202 y caché.

### Frontend (`uis/backoffice`)

- `lib/types.ts` — tipos de reporting y `computeWeeklyTotals()` (tasa ponderada).
- `lib/api.ts` — `fetchWeeklyPerformance`, `fetchLatestPipelineRun`,
  `triggerPipelineRun`.
- `app/(protected)/reporting/page.tsx` — selector de semana, tarjetas de
  totales, tabla por almacén/cliente, estado de la última corrida, badges
  `frozen`/`stale`, botón "Ejecutar ahora" con `ConfirmDialog` y polling cada
  5 s mientras la corrida está `running`.
- `components/Sidebar.tsx` — entrada "Desempeño" → `/reporting`.
- `next.config.ts` — rewrite `/api/reporting/:path*` → `BACKEND_URL/reporting/:path*`.
- `app/(protected)/reporting/page.test.tsx` (5 casos): resumen/tabla, estado del
  pipeline, estado vacío, disparo manual y filtro por semana.

### Verificación F6

- `services/api` → **204 passed** (192 previos + 12 de reporting).
- `uis/backoffice` → **78 tests Vitest** (73 + 5), `npm run lint` y
  `npm run build` OK; ruta `/reporting` en el build.
- `npm run typecheck` raíz OK.
- Servicio de reporting validado contra PostgreSQL real (esquema `reporting`,
  `date`/`timestamptz` y `Session` SQLModel).

## Pipeline de desempeño — G1–G4 (instrumentación de origen)

### Esquema y migración

- `services/api/migrations/0001_g1_g4.sql` (aditiva e idempotente):
  - G1: `ops.telemetry_outbox` (ya existía; `if not exists`).
  - G2: `sku.client_id` **nullable** (pendiente de mapeo).
  - G3: `sku.min_stock` **nullable** (`NULL` = no configurado; `0` = umbral cero).
  - G4: `inventory_discrepancy` + `client_id` snapshot en `stock_entry`/`stock_exit`.
- **Migración aplicada en producción (Supabase)** con backup previo:
  - backup custom `pg_dump` (PostgreSQL 17.4 client) verificado con
    `pg_restore --list`; 323 KiB.
  - aplicada por conexión directa (`db.<ref>.supabase.co:5432`), no por el
    transaction pooler 6543.
  - verificado: `sku` tiene `client_id`/`min_stock`; existen
    `inventory_discrepancy` y `ops.telemetry_outbox`; 12 SKUs sin mapeo (esperado).
- `migrations/README.md` documenta backup, aplicación y rollback.

### Código

- `app/telemetry/emitter.py` — `build_event()` (sin persistir) + `log_event()`.
- `app/telemetry/outbox.py` — tabla `ops.telemetry_outbox` (PostgreSQL) /
  tabla plana (SQLite), `enqueue_event()` y `create_outbox_table()`.
- `inventory_service.py` — orden + evento en la misma transacción; snapshot de
  `client_id`; `stock_threshold_triggered` al cruzar `min_stock`;
  `create_discrepancy()` con un evento por `order_id`.
- `app/routes/inventory.py` — `POST /inventory/discrepancies`; `SKURead` expone
  `client_id` y `min_stock`.
- `models.py` — `SKU.client_id/min_stock`, snapshot en órdenes y
  `InventoryDiscrepancy`; `schema_version` 2.0.0.
- Catálogo y `docs/telemetry/event-schemas.json` — `order_id` requerido para
  discrepancias y `manual_audit` en `detection_source`.
- `import_sku_mapping.py` — CSV `sku_code,client_id,min_stock` con `--dry-run`,
  `--allow-remote-db`, validación y resumen; ejemplo en
  `data/sku_mapping.example.csv`.
- Pipeline: gate `client_mapping_missing` cuando todos los rechazos son
  `missing_client_id`; aviso `configuration_gaps:client=X,min_stock=Y`.

### Verificación G1–G4

- `services/api` → **213 passed** (208 previos + 5 del importador).
- `pipelines/weekly_performance` → **50 passed, 3 skipped**.
- API validada contra PostgreSQL 17 real: inbound + discrepancia escriben en
  `ops.telemetry_outbox` con JSONB y `client_id`.
- Migración validada primero en PostgreSQL 17 efímero y luego aplicada a
  Supabase producción.
- Pendiente: cargar el CSV real cuando exista, fijar
  `PIPELINE_INSTRUMENTATION_SINCE` y ejecutar backfill; desplegar el código API
  con la nueva versión.

