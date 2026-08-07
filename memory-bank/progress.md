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
  - `POST /api/users` — Registro público, crea User + Profile
  - `GET /api/users` — Listar usuarios (admin)
  - `GET/PUT/DELETE /api/users/{id}` — CRUD protegido (admin o propio usuario)
  - `GET/PUT /api/profiles/me` — Perfil del usuario autenticado (solo dueño)
  - Modelos Pydantic con `UserRole` enum (admin, manager, user) en `models.py`
  - `app/core/security.py` — bcrypt hashing + JWT creation/validation
  - `app/core/dependencies.py` — `get_current_user` via Bearer token
  - Seed script: `seed_users.py` (crea admin@trackflow.com / admin123)

## Siguientes pasos

- [ ] Implementar componente `SidePanel` y `CandidateDetail` completo
- [ ] Implementar ruta dinámica `/candidates/[id]`
- [ ] Añadir paginación en `CandidateList`
- [ ] Implementar `ConfirmDialog` para eliminación
- [ ] Pruebas end-to-end del flujo completo
- [ ] Conectar autenticación al backoffice (login UI + token storage)
- [ ] Conectar formulario de aplicación con API real
