# Progress — TrackFlow

## Estado actual

| Hito | Estado | Notas |
|---|---|---|
| MILESTONE_1 — Landing + Formulario | ✅ Completado | `index.html`, `application.html`, `validation.js` |
| MILESTONE_2 — Modelado + Colecciones | ✅ Completado | `src/types/models.ts`, `src/utils/*.ts` |
| MILESTONE_3 — Talent Tracker | 🔄 En progreso | Next.js scaffolding creado, pendiente implementación de componentes |

## Últimas decisiones

- Proyecto base creado con `create-next-app` en `uis/talent-pipeline-tracker/`
- Tema oscuro, tipografía Space Grotesk
- API URL configurada en `.env.local`
- AGENTS.md raíz creado con flujo pre-commit y directorios protegidos
- Memory bank creado en `/memory-bank/` con projectbrief, techContext, progress
- `.agents/rules/talent-tracker-patterns.md` — regla de desarrollo (alwaysApply sobre `uis/talent-pipeline-tracker/**/*.{ts,tsx}`)
- `.agents/skills/validate-commit/SKILL.md` — skill para validación pre-commit

## Siguientes pasos

- [ ] Implementar componente `SidePanel` y `CandidateDetail` completo
- [ ] Implementar ruta dinámica `/candidates/[id]`
- [ ] Añadir paginación en `CandidateList`
- [ ] Implementar `ConfirmDialog` para eliminación
- [ ] Pruebas end-to-end del flujo completo
