---
name: "validate-commit"
description: "Valida que los cambios cumplen el flujo pre-commit del monorepo TrackFlow (typecheck, lint, build, revisión de cambios, actualización de memory-bank)"
objective: "Ejecutar y verificar el flujo obligatorio de AGENTS.md antes de preparar un commit, asegurando que el código pasa typecheck, lint, build, que solo se incluyen los cambios deseados y que memory-bank/progress.md refleja el estado actual."
inputs:
  - name: "changed_paths"
    type: "string[]"
    description: "Lista de rutas modificadas detectadas por git. Se usa para determinar qué sub-proyectos verificar."
    required: true
  - name: "commit_message"
    type: "string"
    description: "Mensaje de commit opcional. Si se provee y la validación pasa, se crea el commit automáticamente."
    required: false
  - name: "update_progress"
    type: "boolean"
    description: "Si es true, actualiza memory-bank/progress.md con los cambios realizados antes del commit."
    default: true
    required: false
  - name: "skip_checks"
    type: "string[]"
    description: "Lista de verificaciones a omitir (typecheck, lint, build). Útil para cambios triviales (README, docs)."
    required: false
    default: []
acceptance_criteria:
  - "1. `npm run typecheck` se ejecuta en la raíz y pasa sin errores ni warnings de tipo"
  - "2. Si `changed_paths` incluye rutas bajo `uis/talent-pipeline-tracker/`: `npm run lint` y `npm run build` se ejecutan allí y pasan sin errores"
  - "3. Se ejecuta `git status` y `git diff` para verificar que solo se incluyen los cambios deseados (sin node_modules, .next, .env, etc.)"
  - "4. Si el cambio afecta al estado del proyecto (nuevas features, cambios en la arquitectura, hitos): `memory-bank/progress.md` se actualiza reflejando el nuevo estado"
  - "5. Si no se proporcionó `commit_message`: el flujo termina con validación exitosa, sin crear commit. Si se proporcionó y la validación pasa: el commit se crea con ese mensaje"
---
