# Progress — TrackFlow

## Estado actual

| Hito | Estado | Notas |
|---|---|---|
| MILESTONE_1 — Landing + Formulario | ✅ Completado | `index.html`, `application.html`, `validation.js` |
| MILESTONE_2 — Modelado + Colecciones | ✅ Completado | `src/types/models.ts`, `src/utils/*.ts` |
| MILESTONE_3 — Talent Tracker | 🔄 En progreso | Next.js scaffolding creado, pendiente implementación de componentes |
| MILESTONE_4 — AI Engineering Tech · Infraestructura | ✅ Completado | AGENTS.md, memory-bank, .agents/rules, .agents/skills |
| MILESTONE_5 — API de inventario | 🔄 En progreso | Backend listo (BD dual TinyDB+SQL, ORM, service, router, seed, tests) — pendiente frontend/UI |

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

## Siguientes pasos

- [ ] UI de inventario en `uis/backoffice` (pantalla de productos/stock y registro de órdenes inbound/outbound)
- [ ] Conectar frontend a rutas `/inventory` (Bearer token) y reflejar `current_stock`/`current_stock_by_warehouse`
- [ ] Implementar componente `SidePanel` y `CandidateDetail` completo
- [ ] Implementar ruta dinámica `/candidates/[id]`
- [ ] Añadir paginación en `CandidateList`
- [ ] Pruebas end-to-end del flujo completo
- [ ] Conectar formulario de aplicación con API real
