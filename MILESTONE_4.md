## Hito 4 — AI Engineering Tech · Infraestructura de desarrollo

El equipo de Tecnología ha identificado que el crecimiento del monorepo y la incorporación de agentes de IA requieren una base sólida: normas de desarrollo claras, un banco de memoria del proyecto y habilidades reutilizables para tareas recurrentes. Sin esta infraestructura, cada sesión de desarrollo arranca desde cero y los agentes trabajan sin contexto compartido.

Tu trabajo es construir la capa de *developer experience* y *agent infrastructure* que permita al equipo —humano y artificial— operar de forma consistente, documentada y verificable.

### Estructura de archivos

```
/
├── AGENTS.md                    # Instrucciones de inicio, flujo pre-commit, rutas protegidas
├── memory-bank/
│   ├── projectbrief.md          # Resumen de TrackFlow, departamentos, hitos y estructura
│   ├── techContext.md           # Stack, comandos, configuraciones del monorepo
│   └── progress.md              # Estado actual y próximos pasos
└── .agents/
    ├── rules/
    │   └── talent-tracker-patterns.md   # Regla alwaysApply para Talent Tracker TS/TSX
    └── skills/
        └── validate-commit/
            └── SKILL.md                 # Skill de validación pre-commit
```

### Entregables

| Elemento | Descripción |
|---|---|
| **AGENTS.md** | Define qué archivos leer al inicio de cada sesión, flujo obligatorio pre-commit (typecheck → lint → build → git diff → update memory-bank → commit), y lista de directorios/archivos protegidos que requieren confirmación antes de modificar |
| **memory-bank/projectbrief.md** | Briefing completo: qué es TrackFlow, departamentos y sus necesidades, hitos del proyecto, estructura del monorepo |
| **memory-bank/techContext.md** | Stack tecnológico con versiones (TypeScript 6, Next.js 16, React 19, Tailwind v4), comandos, configuración tsconfig, convenciones de código |
| **memory-bank/progress.md** | Estado de cada hito, últimas decisiones arquitectónicas, próximos pasos priorizados |
| **Regla de desarrollo** | `talent-tracker-patterns.md` con alcance `alwaysApply` sobre `uis/talent-pipeline-tracker/**/*.{ts,tsx}`. Codifica: patrones del API client, estructura de hooks, sincronización de filtros con URL, manejo de 3 estados en listados, uso de `<dialog>` nativo, paleta Tailwind, prohibición de fallos silenciosos |
| **Skill de agente** | `validate-commit/SKILL.md` con objetivo único, inputs documentados (`changed_paths`, `commit_message`, `update_progress`, `skip_checks`) y 5 criterios de aceptación verificables mediante comandos concretos |

### Reglas técnicas

- `AGENTS.md` debe priorizarse como fuente de verdad para el flujo de trabajo del agente.
- `memory-bank/progress.md` debe actualizarse cada vez que un cambio afecte al estado del proyecto.
- La regla de desarrollo debe reflejar fielmente el código existente (no ser genérica).
- La skill debe tener acceptance criteria ejecutables, no subjetivos.
- Los directorios `agents/`, `infra/`, `workflows/`, `mcps/`, `data/`, `internal/` y archivos de configuración raíz deben listarse como protegidos.

### Criterios de aceptación

1. `AGENTS.md` existe en la raíz con: archivos de inicio de sesión, flujo pre-commit de al menos 4 pasos, y tabla de rutas protegidas.
2. `memory-bank/` contiene `projectbrief.md`, `techContext.md` y `progress.md` con contenido específico de TrackFlow.
3. `.agents/rules/` contiene al menos una regla con `description`, `globs`, `alwaysApply` y contenido documentado.
4. `.agents/skills/` contiene al menos una skill con `objective`, `inputs` documentados y `acceptance_criteria` verificables.
5. El contenido de reglas y skills está alineado con los datos, procesos y restricciones de `CONTEXT.md` y los hitos existentes.
