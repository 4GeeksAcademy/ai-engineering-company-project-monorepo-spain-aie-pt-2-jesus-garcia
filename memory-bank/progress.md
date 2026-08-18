# Progress — TrackFlow

## Estado actual

| Hito | Estado | Notas |
|---|---|---|
| MILESTONE_1 — Landing + Formulario | ✅ Completado | `index.html`, `application.html`, `validation.js` |
| MILESTONE_2 — Modelado + Colecciones | ✅ Completado | `src/types/models.ts`, `src/utils/*.ts` |
| MILESTONE_3 — Talent Tracker | 🔄 En progreso | Next.js scaffolding creado, pendiente implementación de componentes |
| MILESTONE_4 — AI Engineering Tech · Infraestructura | ✅ Completado | AGENTS.md, memory-bank, .agents/rules, .agents/skills |

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

## Siguientes pasos

- [ ] Implementar componente `SidePanel` y `CandidateDetail` completo
- [ ] Implementar ruta dinámica `/candidates/[id]`
- [ ] Añadir paginación en `CandidateList`
- [ ] Pruebas end-to-end del flujo completo
- [ ] Conectar formulario de aplicación con API real
