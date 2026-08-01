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

## Siguientes pasos

- [ ] Implementar componente `SidePanel` y `CandidateDetail` completo
- [ ] Implementar ruta dinámica `/candidates/[id]`
- [ ] Añadir paginación en `CandidateList`
- [ ] Implementar `ConfirmDialog` para eliminación
- [ ] Pruebas end-to-end del flujo completo
- [ ] Añadir autenticación al backoffice
- [ ] Conectar formulario de aplicación con API real
