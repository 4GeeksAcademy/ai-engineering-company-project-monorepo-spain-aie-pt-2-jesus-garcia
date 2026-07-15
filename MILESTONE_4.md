## Hito 4 — AI Engineering Tech · Infraestructura de desarrollo + Frontend

El equipo de Tecnología necesita una base sólida de desarrollo y una presencia web moderna. Por un lado, el monorepo requiere normas claras, un banco de memoria del proyecto y habilidades reutilizables para agentes IA. Por otro, la empresa necesita un sitio web público que refleje su identidad corporativa y un backoffice interno que consuma la lógica de negocio existente.

### Estructura de archivos

```
/
├── AGENTS.md                    # Instrucciones de inicio, flujo pre-commit, rutas protegidas
├── memory-bank/
│   ├── projectbrief.md          # Resumen de TrackFlow, departamentos, hitos y estructura
│   ├── techContext.md           # Stack, comandos, configuraciones del monorepo
│   └── progress.md              # Estado actual y próximos pasos
├── .agents/
│   ├── rules/
│   │   └── talent-tracker-patterns.md   # Regla alwaysApply para Talent Tracker TS/TSX
│   └── skills/
│       └── validate-commit/
│           └── SKILL.md                 # Skill de validación pre-commit
└── uis/website/                 # App Next.js unificada (pública + backoffice)
    ├── app/
    │   ├── layout.tsx           # Root layout (Space Grotesk, bg-slate-950)
    │   ├── (public)/
    │   │   ├── layout.tsx       # Layout público (Header + Footer)
    │   │   ├── page.tsx         # / → Landing (hero, stats, timeline, CTA)
    │   │   └── application/
    │   │       └── page.tsx     # /application → Formulario multi-paso
    │   ├── backoffice/
    │   │   ├── layout.tsx       # Layout con sidebar colapsable
    │   │   ├── page.tsx         # /backoffice → Welcome screen
    │   │   └── business-logic/
    │   │       └── page.tsx     # /backoffice/business-logic → Lógica MILESTONE_2
    │   └── loading.tsx
    ├── components/
    │   ├── Header.tsx, Footer.tsx, SkipLink.tsx
    │   ├── HeroSection.tsx, StatsSection.tsx, TimelineSection.tsx, CTASection.tsx
    │   ├── application/ApplicationForm.tsx
    │   └── backoffice/Sidebar.tsx, WelcomeCards.tsx
    └── tsconfig.json           # @repo/* → ../../src/ (importa sin copiar)
```

### Entregables

| Elemento | Descripción |
|---|---|
| **AGENTS.md** | Define qué archivos leer al inicio de cada sesión, flujo obligatorio pre-commit (typecheck → lint → build → git diff → update memory-bank → commit), y lista de directorios/archivos protegidos |
| **memory-bank/** | `projectbrief.md`, `techContext.md`, `progress.md` con contenido específico de TrackFlow |
| **Regla de desarrollo** | `talent-tracker-patterns.md` — alwaysApply sobre `uis/talent-pipeline-tracker/**/*.{ts,tsx}` |
| **Skill de agente** | `validate-commit/SKILL.md` — validación pre-commit con inputs y acceptance criteria |
| **Web pública (`uis/website/`)** | App Next.js con landing page (hero, stats, timeline, CTA) y formulario de aplicación multi-paso, migrados de MILESTONE_1 con componentes React reutilizables y TypeScript |
| **Backoffice interno** | Rutas `/backoffice` y `/backoffice/business-logic` con layout propio (sidebar colapsable), welcome screen con cards de departamentos, e integración de lógica MILESTONE_2 importada desde `src/` sin copiar |
| **Integración MILESTONE_2** | `tsconfig.json` con path alias `@repo/*` → `../../src/*`. La página business-logic muestra filtros (`filterShipments`, `filterInventory`), agregaciones (`countByCategory`, `sumBy`, `averageBy`, `maxBy`, `minBy`) y datos visibles en tabla |

### Reglas técnicas

- `AGENTS.md` debe priorizarse como fuente de verdad para el flujo de trabajo del agente.
- `memory-bank/progress.md` debe actualizarse cada vez que un cambio afecte al estado del proyecto.
- La regla de desarrollo debe reflejar fielmente el código existente (no ser genérica).
- La skill debe tener acceptance criteria ejecutables, no subjetivos.
- Los directorios `agents/`, `infra/`, `workflows/`, `mcps/`, `data/`, `internal/` y archivos de configuración raíz deben listarse como protegidos.
- La identidad visual de MILESTONE_1 debe preservarse en la web pública (gradientes, paleta naranja/cyan, Space Grotesk).
- El código de negocio MILESTONE_2 debe importarse desde su ubicación original — no copiarse.
- El sidebar del backoffice debe ser colapsable (transición suave).

### Criterios de aceptación

1. `AGENTS.md` existe en la raíz con: archivos de inicio de sesión, flujo pre-commit de al menos 4 pasos, y tabla de rutas protegidas.
2. `memory-bank/` contiene `projectbrief.md`, `techContext.md` y `progress.md` con contenido específico de TrackFlow.
3. `.agents/rules/` contiene al menos una regla con `description`, `globs`, `alwaysApply` y contenido documentado.
4. `.agents/skills/` contiene al menos una skill con `objective`, `inputs` documentados y `acceptance_criteria` verificables.
5. El contenido de reglas y skills está alineado con los datos, procesos y restricciones de `CONTEXT.md` y los hitos existentes.
6. `npm run dev` en `uis/website/` arranca la app con rutas `/`, `/application`, `/backoffice`, `/backoffice/business-logic`.
7. La landing page replica la identidad visual de MILESTONE_1 con componentes React.
8. El backoffice importa desde `src/` (path alias `@repo/`) y muestra resultados de filtros y agregaciones en pantalla.
9. `npm run build` y `npm run lint` pasan sin errores.
