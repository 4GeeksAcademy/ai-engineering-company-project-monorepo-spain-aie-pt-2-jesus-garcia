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
- Seed de inventario (SQL, requiere `DATABASE_URL`): `python seed_inventory.py --force` (destructivo; `--dry-run` para previsualizar)
- Benchmark de caché (cold/warm): `DATABASE_URL=sqlite:///./perf_measure.db python bench_cache.py` (tras `seed_perf.py --force`; `--repeats N`, `--json`)
- Usar SIEMPRE `services/api/venv`. El `.venv` raíz no tiene las deps de la API.

### Tareas asíncronas (Redis + Celery)

```bash
# Docker: broker + API + worker + Flower
docker compose up --build -d redis services worker flower
docker compose logs -f worker
docker compose stop worker flower

# Local (desde services/api)
source venv/bin/activate
REDIS_URL=redis://localhost:6379/0 \
INCIDENT_UPLOAD_DIR=/tmp/trackflow/uploads \
celery -A celery_app worker --loglevel=INFO
```

- `POST /api/incidents/analyze` → `202 {"task_id": ...}`; `GET /tasks/{task_id}`
  → estado Celery (`pending`, `started`, `success`, `failure`) y resultado.
- Flower en `http://localhost:5555`.
- DLQ: tabla `dead_letter_tasks` + lista Redis `dlq:trackflow`.
- Reintentos: `max_retries=3` con backoff 5/10/20 s; timeout duro/blando 600/540 s.
- Runbook: `docs/asynchronous/CELERY.md`.

### Docker Compose (método único de ejecución de la plataforma)

```bash
docker compose up --build -d
```

- `uis` → website en `http://localhost:3000`, backoffice en `http://localhost:3001` (puertos intercambiados respecto a la ejecución local previa).
- `services` → API en `http://localhost:8000` (`/health`).
- URLs: backoffice usa `BACKEND_URL=http://services:8000` (rewrites server-side); website usa `NEXT_PUBLIC_API_URL=http://localhost:8000` (llamadas desde el navegador).
- Código fuente en bind-mount (hot reload en ambas apps); `node_modules`/`.next` en named volumes (deps Linux del contenedor).

### Pipeline semanal (`pipelines/weekly_performance`)

```bash
# ejecución por script (requiere DATABASE_URL_PIPELINE)
python -m pipelines.weekly_performance run --lookback 3
python -m pipelines.weekly_performance backfill --week 2026-07-13 --force --reason "..."
python -m pipelines.weekly_performance reconcile-source --days 7 --json

# tests (SQLite; los de PostgreSQL se saltan sin TEST_POSTGRES_URL)
services/api/venv/bin/python -m pytest pipelines/weekly_performance/tests -q
```

- Dependencias propias en `pipelines/weekly_performance/pyproject.toml`; Prefect
  no se añade a `services/api/requirements.txt`.
- Prefect self-hosted opcional: `docker compose --profile prefect up -d`
  (UI/API en `http://localhost:4200`).
- API de reporte: `GET/POST /reporting/*` en `services/reporting/`;
  backoffice en `/reporting` (rewrite `/api/reporting/*`).
- Env: `DATABASE_URL_PIPELINE`, `PREFECT_API_URL`, `PIPELINE_ALERT_WEBHOOK`,
  `PIPELINE_INSTRUMENTATION_SINCE`.
- Migración G1–G4: `services/api/migrations/0001_g1_g4.sql` (aplicar por
  conexión directa 5432 con backup previo; ver `migrations/README.md`).
- Mapeo SKU → cliente/umbral: `python import_sku_mapping.py --file ...`
  (`--dry-run`, `--allow-remote-db`). Columnas nullable hasta que exista el
  mapeo; el pipeline bloquea con `client_mapping_missing`.

### Frontend `uis/backoffice` (puerto 3001 en Docker)

```bash
cd uis/backoffice
npm run dev -- -p 3001   # en Docker lo lanza start.sh; local usar -p 3001
npm run build
npm run lint
```

- Proxya `/api/*` → `BACKEND_URL` (por defecto `http://localhost:8000`) vía `next.config.ts`.

### Frontend `uis/website` (puerto 3000 en Docker)

```bash
cd uis/website
npm run dev   # puerto por defecto 3000
```

- Llama a la API directamente desde el navegador usando `NEXT_PUBLIC_API_URL` (`uis/website/.env`). Su `next.config.ts` NO tiene rewrites.
- CORS: `ALLOWED_ORIGINS` ya incluye `:3000`, `:3001` y `:5173` en `services/api/app/main.py`.

### Ejecutar API + backoffice + website simultáneamente (local, sin Docker)

```bash
# Terminal 1 — API
cd services/api && source venv/bin/activate && uvicorn app.main:app --port 8000
# Terminal 2 — backoffice (puerto 3001)
cd uis/backoffice && npm run dev -- -p 3001
# Terminal 3 — website (puerto 3000)
cd uis/website && npm run dev
```

`uis/backoffice` y `uis/website` son ambas Next.js y requieren puertos distintos (3001 / 3000). El backend en 8000 no entra en conflicto.

## Variables de entorno del backend

- `SECRET_KEY`: clave para firmar/verificar tokens JWT.
- `ACCESS_TOKEN_EXPIRE_MINUTES`: validez de los access tokens (por defecto `1440`).
- `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES`: validez del token de restablecimiento (por defecto `30`, rango 15–60).
- `RESEND_API_KEY`: clave de Resend para envío de emails reales. Si NO está configurada, el flujo de reset queda en modo stub (loguea el enlace) para desarrollo.
- `RESEND_FROM`: remitente de los emails (por defecto `onboarding@resend.dev`).
- `FRONTEND_URL`: base del backoffice (por defecto `http://localhost:3001` en Docker); se usa para construir el enlace de restablecimiento.
- `DATABASE_URL`: cadena de conexión del engine SQLModel (MILESTONE_5). En producción, la URI del **Transaction pooler** de Supabase (`postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres`). **Vacía** → `engine = None` y las rutas `/inventory` devuelven un 500 explícito *"DATABASE_URL no está configurada"*.
- `SUPABASE_SHARED_POOLER`: en `.env.example` como referencia de la URI del pooler (el código solo lee `DATABASE_URL`).
- `REDIS_URL`: broker y result backend de Celery (`redis://redis:6379/0` en Docker, `redis://localhost:6379/0` en local).
- `INCIDENT_UPLOAD_DIR`: volumen compartido API/worker para los CSV encolados (`/uploads` en Docker).
- `CELERY_TASK_TIME_LIMIT` / `CELERY_TASK_SOFT_TIME_LIMIT`: timeout duro/blando por intento (600/540 s por defecto).
- `CELERY_RETRY_BACKOFF_SECONDS`: base del backoff exponencial (5 s por defecto).
- `AGENT_TRACE_DIR`: directorio de traces JSON del agente (vacío → `data/eval/agent-traces`).
- `AGENT_INCIDENT_TOOL_TIMEOUT_SECONDS` / `AGENT_INVENTORY_TOOL_TIMEOUT_SECONDS`: timeout numérico de las tools de tickets/inventario (default `3` s). Si expira, el agente responde con un fallback honesto.

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

## RAG — Base de conocimiento (MILESTONE 7)

- Qdrant: servicio `qdrant` en `docker-compose.yml` (`qdrant/qdrant:v1.20.1`,
  `:6333`, volumen `qdrant-data`). Colección `trackflow_knowledge`, vectores
  de 1024 dimensiones y distancia coseno.
- Indexación: `data/process/rag_index.py` (`setup`, `embed`,
  `load_source_documents`, `chunk_document`). `setup()` usa clean-and-reload +
  UUID5 deterministas para ser idempotente.
- Consulta: `data/pipelines/rag.py` (`retrieve`, `generate_answer`, `query`).
  `query()` compone `retrieve()` + `generate_answer()`.
- Endpoint: `POST /knowledge/query` (`services/api/app/routes/knowledge.py`),
  autenticado, respuesta `{"answer": "..."}`.
- UI: `uis/backoffice/app/(protected)/knowledge/page.tsx` + rewrite
  `/api/knowledge/*` y entrada “Asistente comercial” en el sidebar.
- Config en `services/api/.env` (plantilla en `services/api/.env.example`):
  `LLM_BASE_URL`, `LLM_API_KEY`, `EMBEDDING_MODEL`, `GENERATION_MODEL`,
  `EMBEDDING_DIM`, `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION`,
  `RAG_TOP_K`, `RAG_MIN_SCORE`.
- `LLM_BASE_URL` se normaliza (`normalize_llm_base_url`): tolera `/`, `/v1` y
  `/litellm`; las llamadas son `{base}/v1/embeddings` y
  `{base}/v1/chat/completions`, con el modelo en el body JSON. `join_url()` y
  `build_model_url()` garantizan una sola barra.
- Comandos:
  ```bash
  docker compose up -d qdrant
  python -m data.process.rag_index --dry-run
  python -m data.process.rag_index
  python -m data.eval.evaluate_retrieval --k 3 --min-score 0.35
  python -m pytest tests/pipelines/test_rag.py -q
  ```
- Diseño: `docs/rag/rag-design.md`. Eval: `data/eval/test-queries.json`
  (12 preguntas, Recall@3 ≥ 80%).

## Agente RAG con LangGraph (MILESTONE 8)

- Grafo en `services/api/app/agent/`: `state.py` (`AgentState`), `nodes.py`
  (`receive_question`, `retrieve`, `generate`, `no_context`, `fail`),
  `graph.py` (aristas condicionales, validación estructural, compilación con
  `InMemorySaver`), `tracing.py` (traces JSON) y `runner.py` (`run_agent`).
- Reutiliza `data/pipelines/rag.py`: `retrieve()` en el nodo `retrieve` y
  `generate_answer(question, context)` en `generate`. `query()` monolítico no
  se usa en el grafo.
- Endpoint `POST /agent/query` → `{"answer", "run_id"}` (422 pregunta inválida,
  502 fallo interno). `/knowledge/query` sigue existiendo.
- Traces: `data/eval/agent-traces/{run_id}.json` + `index.jsonl`;
  `AGENT_TRACE_DIR` permite cambiarlo. Se leen con `AgentTrace.load*` y el
  estado con `get_run_state(run_id)`.
- Checkpointer `InMemorySaver` con `thread_id = run_id`; un snapshot por
  transición, también serializado en el trace.
- Dependencia `langgraph>=1.2.21` en `services/api/requirements.txt` y
  `services/api/pyproject.toml`.
- Comandos:
  ```bash
  uv run pytest tests/pipelines/test_agent_evals.py -q
  uv run pytest tests/pipelines/test_rag.py tests/pipelines/test_agent_evals.py -q
  uv run python scripts/record_agent_traces.py   # regenerar fixtures (live)
  ```
- Diseño: `docs/rag/agent-design.md`. Fixtures:
  `tests/pipelines/fixtures/agent_traces/`.

## Agente — tools de lectura en tiempo real (MILESTONE 8, parte 2)

- `services/api/app/agent/tools/` — `contracts.py` (Pydantic), `execution.py`
  (timeout con `ThreadPoolExecutor`), `incidents.py` e `inventory.py`.
- `incident_lookup` lee de `app/services/incident_service.py` (misma capa que
  `GET /api/incidents`); `inventory_lookup` de
  `inventory_service.list_skus_with_stock` (misma capa que
  `GET /inventory/products`). Ambas son de solo lectura, in-process y con
  timeout/fallback.
- `app/agent/router.py` — clasificador determinista (`rag`, `incident`,
  `inventory`, `incident+rag`, `inventory+rag`).
- El trace añade `route` y `sources_used`; los eventos de tool muestran
  `tool_status` y `fallback`.
- La tool de tickets aplica `require_manager` (como la ruta REST); el rol viaja
  en el estado, no el token.
- Comandos:
  ```bash
  uv run pytest tests/pipelines/test_agent_evals.py -q
  cd services/api && source venv/bin/activate && pytest tests/test_agent_tools.py -q
  ```

## Configuración de email (Recuperación de contraseña)

Las variables del backend se cargan desde `services/api/.env` (via `python-dotenv` en `app/main.py`). El archivo `.env` NO se commitea (ya ignorado).

- **Modo stub (default):** dejando `RESEND_API_KEY` vacío, el enlace de restablecimiento se imprime por **consola del backend**:
  ```
  [email_service] RESEND_API_KEY no configurada. Enlace de restablecimiento para <email>: http://localhost:3000/reset-password?token=...
  ```
  Copia la URL completa (incluye `token`) y ábrela en el navegador. Este es el "servicio de captura" para desarrollo local (Resend es API HTTP, no SMTP, así que no se puede redirigir a Mailpit/MailHog).
- **Modo test/real (opcional, sin dominio):** rellena `RESEND_API_KEY` con una clave de `resend.com` (Dashboard → API Keys). Con `RESEND_FROM="TrackFlow <onboarding@resend.dev>"` Resend entrega **solo a tu email verificado** en `resend.com` (limitación del modo test sin dominio). Valida el camino real end-to-end.
- **Producción con dominio:** añadir el dominio en Resend + verificación DNS y usar `no-reply@tudominio.com`; ahí sí se puede enviar a cualquier destinatario.

## MCP Server y agente (OAuth 2.1 + langchain-mcp-adapters)

- Servidor: `mcps/trackflow-mcp/` (FastMCP + `mcpauth==0.2.0b1`, puerto **8001**).
- Transporte: Streamable HTTP en `/mcp`; PRM público en
  `/.well-known/oauth-protected-resource/mcp`; `/health` público.
- Auth: resource server con issuer OIDC (Auth0), `audience`/`resource` =
  `MCP_RESOURCE_URL` (incluye `/mcp`) y gate `mcp:read`; scopes finos
  `mcp:read`/`mcp:write`.
- Tools: `query_incidents`, `get_incident_summary`, `create_incident`,
  `update_incident_status`, `query_inventory` y `adjust_inventory_stock`
  (guard que siempre rechaza con `INVENTORY_READ_ONLY`).
- API real: el MCP usa una cuenta de servicio `manager`
  (`mcp-service@trackflow.com`, seed en `services/api/seed_mcp_service.py`).
  Variables: `TRACKFLOW_API_BASE_URL`, `TRACKFLOW_API_EMAIL/PASSWORD` o
  `TRACKFLOW_API_TOKEN`.
- Agente: `services/api/app/agent/tools/mcp_client.py` +
  `mcp_auth.py`; `MCPSettings` lee `MCP_SERVER_URL`, `MCP_OAUTH_*` y
  `AGENT_MCP_TIMEOUT_SECONDS=10`. El agente solo recibe `mcp:read`.
- Dependencias: `mcp>=1.24,<2` (no 2.x: rompe `langchain-mcp-adapters`),
  `langchain-mcp-adapters>=0.3.1,<0.4`, `mcpauth==0.2.0b1` (la 0.1.1 no tiene
  resource-server/PRM).

```bash
# Servidor MCP
cd mcps/trackflow-mcp
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn trackflow_mcp.server:app --host 0.0.0.0 --port 8001
.venv/bin/pytest -q

# Smoke con token M2M o bearer estático
python scripts/mcp_smoke.py --token "$TOKEN"
python scripts/mcp_smoke.py --write   # crea y mueve una incidencia real

# API local para el MCP (SQLite, sin tocar Supabase)
cd services/api
DATABASE_URL=sqlite:///./dev.db venv/bin/uvicorn app.main:app --port 8002
DATABASE_URL=sqlite:///./dev.db venv/bin/python seed_inventory.py --force
MCP_SERVICE_PASSWORD=... venv/bin/python seed_mcp_service.py
```

- En Docker Compose el servicio `mcp` publica `8001:8001` y usa
  `TRACKFLOW_API_BASE_URL=http://services:8000`; el agente usa
  `MCP_SERVER_URL=http://mcp:8001/mcp`.
- Codespaces: `gh codespace ports visibility 8001:public` y
  `MCP_RESOURCE_URL=https://<codespace>-8001.app.github.dev/mcp`.
- Documentación: `mcps/trackflow-mcp/README.md`,
  `mcps/trackflow-mcp/VALIDATION.md`, `docs/mcp/README.md`.

## Convenciones de código

- TypeScript estricto, sin comentarios en código
- Nombres de archivos en camelCase para TS/TSX
- Componentes React en `uis/backoffice/components/`
- Hooks/contextos en `uis/backoffice/contexts/`
- Tipos e interfaces en archivos `types.ts` o `lib/types.ts`
- Lógica frontend-backend: `${BACKEND_URL}/api/*` (rewrite en backoffice) o `NEXT_PUBLIC_API_URL` (website)

## Estructura de directorios protegidos

Ver `AGENTS.md` en la raíz para la lista de archivos/directorios que no deben modificarse sin confirmación.
