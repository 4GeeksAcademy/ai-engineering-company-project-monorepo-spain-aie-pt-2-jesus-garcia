# AGENTS.md — TrackFlow Monorepo

## Inicio de sesión — archivos a leer

Al comenzar cada sesión, leer los siguientes archivos para establecer contexto:

1. `CONTEXT.md` — Briefing completo de la empresa
2. `MILESTONE_1.md`, `MILESTONE_2.md`, `MILESTONE_3.md` — Especificaciones de los hitos
3. `memory-bank/projectbrief.md` — Resumen del proyecto
4. `memory-bank/techContext.md` — Stack, comandos y convenciones
5. `memory-bank/progress.md` — Estado actual y próximos pasos
6. `package.json` y `tsconfig.json` — Configuración del proyecto raíz

## Flujo obligatorio antes de cada commit

1. **Type-check**: `npm run typecheck` (raíz)
2. **Lint**: Si el cambio afecta a `uis/talent-pipeline-tracker/`, ejecutar `npm run lint` allí
3. **Build**: Si el cambio afecta a `uis/talent-pipeline-tracker/`, ejecutar `npm run build` allí
4. **Revisar cambios**: `git status` + `git diff` para verificar que solo se incluye lo deseado
5. **Actualizar memory-bank**: Si el cambio afecta al estado del proyecto, actualizar `memory-bank/progress.md`
6. **Hacer commit**: Solo cuando el usuario lo solicite explícitamente

## Archivos y directorios protegidos

No modificar sin confirmación explícita del desarrollador:

| Ruta | Motivo |
|---|---|
| `agents/` | Lógica de agentes — requiere validación |
| `infra/` | Configuración de infraestructura |
| `workflows/` | Pipelines CI/CD |
| `mcps/` | Configuración de MCP servers |
| `data/` | Datos raw, pipelines, evaluaciones |
| `internal/` | Documentación interna |
| `.gitignore` | Configuración de git |
| `package.json` (raíz) | Dependencias base del monorepo |
| `package-lock.json` | Lockfile de dependencias |
| `tsconfig.json` | Configuración TypeScript global |
| Cualquier `*.key`, `*.pem`, `*secret*`, `.env*` | Secretos y credenciales |
