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
| sqlmodel / sqlalchemy | sqlmodel 0.0.42 | ORM de inventario (MILESTONE_5) — PostgreSQL/Supabase, en tests SQLite |
| psycopg2-binary | 2.9.12 | Driver PostgreSQL del engine SQLModel (fallback: `psycopg[binary]`) |
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
pip install -r requirements.txt # deps: fastapi, uvicorn, bcrypt, jose, pandas, tinydb, sqlmodel, psycopg2-binary...
uvicorn app.main:app --port 8000
```

- Seed opcional (crea admin@trackflow.com / admin123): `python seed_users.py`
- Seed de inventario (SQL, requiere `DATABASE_URL`): `python seed_inventory.py`
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

## Variables de entorno del backend

- `SECRET_KEY`: clave para firmar/verificar tokens JWT.
- `ACCESS_TOKEN_EXPIRE_MINUTES`: validez de los access tokens (por defecto `1440`).
- `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES`: validez del token de restablecimiento (por defecto `30`, rango 15–60).
- `RESEND_API_KEY`: clave de Resend para envío de emails reales. Si NO está configurada, el flujo de reset queda en modo stub (loguea el enlace) para desarrollo.
- `RESEND_FROM`: remitente de los emails (por defecto `onboarding@resend.dev`).
- `FRONTEND_URL`: base del backoffice (por defecto `http://localhost:3000`); se usa para construir el enlace de restablecimiento.
- `DATABASE_URL`: cadena de conexión del engine SQLModel (MILESTONE_5). En producción, la URI del **Transaction pooler** de Supabase (`postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres`). **Vacía** → `engine = None` y las rutas `/inventory` devuelven un 500 explícito *"DATABASE_URL no está configurada"*.
- `SUPABASE_SHARED_POOLER`: en `.env.example` como referencia de la URI del pooler (el código solo lee `DATABASE_URL`).

## Doble base de datos (TinyDB + SQLModel) — `database.py`

`services/api/database.py` es el punto único de ambas conexiones:

- **TinyDB** (auth, proveedores, incidentes): `get_tinydb()` → `TinyDB(data/suppliers.json)`.
- **SQLModel** (inventario): `engine` creado desde `DATABASE_URL` (o `None` si vacía) y `get_db()` que cede una sesión por request:
  ```python
  def get_db():
      with Session(engine) as session:
          yield session
  ```
  Se inyecta con `session: Session = Depends(get_db)`. Nota: el **commit es explícito** (los services hacen `add → commit → refresh`), porque el teardown del `with` ocurre tras serializar la respuesta.
- En tests, `tests/conftest.py` fija `DATABASE_URL="sqlite:///./test_inventory.db"` (antes de importar la app; `load_dotenv` no la sobreescribe) — la suite nunca toca Supabase. Tablas por `SQLModel.metadata.create_all(engine)` en el lifespan de `app/main.py`.

## Configuración de email (Recuperación de contraseña)

Las variables del backend se cargan desde `services/api/.env` (via `python-dotenv` en `app/main.py`). El archivo `.env` NO se commitea (ya ignorado).

- **Modo stub (default):** dejando `RESEND_API_KEY` vacío, el enlace de restablecimiento se imprime por **consola del backend**:
  ```
  [email_service] RESEND_API_KEY no configurada. Enlace de restablecimiento para <email>: http://localhost:3000/reset-password?token=...
  ```
  Copia la URL completa (incluye `token`) y ábrela en el navegador. Este es el "servicio de captura" para desarrollo local (Resend es API HTTP, no SMTP, así que no se puede redirigir a Mailpit/MailHog).
- **Modo test/real (opcional, sin dominio):** rellena `RESEND_API_KEY` con una clave de `resend.com` (Dashboard → API Keys). Con `RESEND_FROM="TrackFlow <onboarding@resend.dev>"` Resend entrega **solo a tu email verificado** en `resend.com` (limitación del modo test sin dominio). Valida el camino real end-to-end.
- **Producción con dominio:** añadir el dominio en Resend + verificación DNS y usar `no-reply@tudominio.com`; ahí sí se puede enviar a cualquier destinatario.

## Convenciones de código

- TypeScript estricto, sin comentarios en código
- Nombres de archivos en camelCase para TS/TSX
- Componentes React en `uis/backoffice/components/`
- Hooks/contextos en `uis/backoffice/contexts/`
- Tipos e interfaces en archivos `types.ts` o `lib/types.ts`
- Lógica frontend-backend: `${BACKEND_URL}/api/*` (rewrite en backoffice) o `NEXT_PUBLIC_API_URL` (website)

## Estructura de directorios protegidos

Ver `AGENTS.md` en la raíz para la lista de archivos/directorios que no deben modificarse sin confirmación.
