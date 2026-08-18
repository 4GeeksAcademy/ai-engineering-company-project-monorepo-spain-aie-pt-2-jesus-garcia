# Tech Context — TrackFlow

## Stack tecnológico

| Tecnología | Versión | Ámbito |
|---|---|---|
| TypeScript | ^6.0 (root), ^5 (backoffice) | Lenguaje principal frontend |
| Next.js | 16.2.9 | Frontend (`uis/backoffice`, `uis/website`) |
| React | 19.2.4 | Frontend (`uis/backoffice`, `uis/website`) |
| Tailwind CSS | ^4 | Estilos (frontend) |
| ESLint | ^9 | Linting |
| FastAPI + uvicorn | — | Backend API (`services/api`) |
| Python | 3.14 | Backend API (`services/api/venv`) |
| TinyDB | — | Base de datos (usuarios, proveedores) |
| pandas / bcrypt / python-jose | — | Análisis CSV / auth (bcrypt + JWT) |

## Configuración TypeScript (raíz)

- `target: ES2022`, `module: NodeNext`, `moduleResolution: NodeNext`
- `strict: true`, `noEmit: true`
- Cubre `src/**/*.ts`

## Comandos principales

### Backend API (`services/api`, puerto 8000)

```bash
cd services/api
source venv/bin/activate        # venv propio del backend (NO el `.venv` raíz)
pip install -r requirements.txt # deps: fastapi, uvicorn, bcrypt, jose, pandas, tinydb...
uvicorn app.main:app --port 8000
```

- Seed opcional (crea admin@trackflow.com / admin123): `python seed_users.py`
- Usar SIEMPRE `services/api/venv`. El `.venv` raíz no tiene las deps de la API.

### Frontend `uis/backoffice` (puerto 3000)

```bash
cd uis/backoffice
npm run dev      # http://localhost:3000
npm run build
npm run lint
```

- Proxya `/api/*` → `BACKEND_URL` (por defecto `http://localhost:8000`) vía `next.config.ts`.

### Frontend `uis/website` (puerto por defecto 3000 — cambia el puerto)

```bash
cd uis/website
npm run dev -- -p 3001   # evitar conflicto de puerto con uis/backoffice
```

- Llama a la API directamente desde el navegador usando `NEXT_PUBLIC_API_URL` (`uis/website/.env`). Su `next.config.ts` NO tiene rewrites.
- CORS: el backend solo permite `http://localhost:3000` (y `:5173`) en `ALLOWED_ORIGINS`. Si `uis/website` corre en `3001`, hay que añadir ese origen en `services/api/app/main.py`.

### Ejecutar API + backoffice + website simultáneamente

```bash
# Terminal 1 — API
cd services/api && source venv/bin/activate && uvicorn app.main:app --port 8000
# Terminal 2 — backoffice (puerto 3000)
cd uis/backoffice && npm run dev
# Terminal 3 — website (puerto 3001)
cd uis/website && npm run dev -- -p 3001
```

`uis/backoffice` y `uis/website` son ambas Next.js y requieren puertos distintos (3000 / 3001). El backend en 8000 no entra en conflicto.

## Convenciones de código

- TypeScript estricto, sin comentarios en código
- Nombres de archivos en camelCase para TS/TSX
- Componentes React en `uis/backoffice/components/`
- Hooks/contextos en `uis/backoffice/contexts/`
- Tipos e interfaces en archivos `types.ts` o `lib/types.ts`
- Lógica frontend-backend: `${BACKEND_URL}/api/*` (rewrite en backoffice) o `NEXT_PUBLIC_API_URL` (website)

## Estructura de directorios protegidos

Ver `AGENTS.md` en la raíz para la lista de archivos/directorios que no deben modificarse sin confirmación.
