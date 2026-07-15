# Tech Context — TrackFlow

## Stack tecnológico

| Tecnología | Versión | Ámbito |
|---|---|---|
| TypeScript | ^6.0 (root), ^5 (talent-pipeline-tracker) | Lenguaje principal |
| Next.js | 16.2.9 | Frontend (talent-pipeline-tracker) |
| React | 19.2.4 | Frontend (talent-pipeline-tracker) |
| Tailwind CSS | ^4 | Estilos (talent-pipeline-tracker) |
| ESLint | ^9 | Linting |
| http-server | — | Servidor local para HTML estático |

## Configuración TypeScript (raíz)

- `target: ES2022`, `module: NodeNext`, `moduleResolution: NodeNext`
- `strict: true`, `noEmit: true`
- Cubre `src/**/*.ts`

## Comandos principales

```bash
npm run typecheck          # Type-check de src/ (tsc --noEmit)
npx http-server . -p 3000 # Servir landing page y formulario

# Sub-proyecto: uis/talent-pipeline-tracker
cd uis/talent-pipeline-tracker
npm run dev                # Servidor de desarrollo Next.js
npm run build              # Build de producción
npm run lint               # ESLint
```

## Convenciones de código

- TypeScript estricto, sin comentarios en código
- Nombres de archivos en camelCase para TS/TSX
- Componentes React en `uis/talent-pipeline-tracker/components/`
- Hooks en `uis/talent-pipeline-tracker/hooks/`
- Tipos e interfaces en archivos `types.ts` o `lib/types.ts`
- API base: `NEXT_PUBLIC_API_URL=https://playground.4geeks.com/tracker/api/v1`

## Estructura de directorios protegidos

Ver `AGENTS.md` en la raíz para la lista de archivos/directorios que no deben modificarse sin confirmación.
