# Tareas asíncronas — Redis + Celery

## Arquitectura

```
Cliente ──POST /api/incidents/analyze──► API (productor)
                                          │ guarda el CSV en un volumen
                                          │ compartido y encola {path, filename}
                                          ▼
                                        Redis (broker + result backend)
                                          │
                                          ▼
                                        Worker Celery (consumidor)
                                          │ lee el CSV, ejecuta pandas
                                          ▼
                                        GET /tasks/{task_id}
```

- La API y el worker son **procesos distintos**. El worker no vive dentro de
  FastAPI.
- El mensaje solo lleva la **ruta** del CSV, nunca el contenido.
- `task_acks_late=True` confirma el mensaje al terminar; si el worker muere, el
  mensaje vuelve a la cola.
- Cada intento tiene timeout duro/blando (`CELERY_TASK_TIME_LIMIT` /
  `CELERY_TASK_SOFT_TIME_LIMIT`).

## Ciclo de una tarea

1. `POST /api/incidents/analyze` valida cabecera y codificación (barato),
   guarda `INCIDENT_UPLOAD_DIR/{task_id}.csv` de forma atómica y encola.
2. Devuelve `202 {"task_id": "..."}` inmediatamente.
3. El worker ejecuta `incidents.analyze_csv` y registra en log
   `task_id`, `attempt`, `status` y `duration_ms`.
4. `GET /tasks/{task_id}` devuelve:
   ```json
   {"task_id": "...", "status": "pending|started|success|failure", "result": null}
   ```
   Con `success`, `result` es el resumen del análisis; con `failure` es el
   mensaje de error.
5. Al terminar con éxito, el worker borra el CSV.

## Reintentos y Dead Letter Queue

- `max_retries=3` (1 ejecución + 3 reintentos).
- Backoff exponencial: `CELERY_RETRY_BACKOFF_SECONDS * 2**retries` → 5 s, 10 s,
  20 s por defecto.
- Si se agotan los reintentos:
  - se inserta una fila en `dead_letter_tasks` (`task_id`, `task_name`,
    `attempts`, `max_retries`, `error_message`, `created_at`);
  - se hace `RPUSH dlq:trackflow` con el mismo contenido en JSON;
  - se conserva el CSV para diagnóstico.

El CSV de una tarea fallida no se borra: queda en el volumen `task-uploads`.

## Operación

### Docker

```bash
docker compose up --build -d redis services worker flower
docker compose ps
docker compose logs -f worker
```

- API: `http://localhost:8000`
- Flower: `http://localhost:5555`
- Redis: `localhost:6379`

Parar worker y monitor sin tumbar Redis:

```bash
docker compose stop worker flower
```

### Local

```bash
cd services/api
source venv/bin/activate
REDIS_URL=redis://localhost:6379/0 \
INCIDENT_UPLOAD_DIR=/tmp/trackflow/uploads \
celery -A celery_app worker --loglevel=INFO
```

API:

```bash
cd services/api
source venv/bin/activate
uvicorn app.main:app --port 8000
```

### Flower

```bash
celery -A celery_app flower --port=5555
```

## Comprobar la DLQ

```bash
# Lista Redis (vista operativa)
redis-cli LRANGE dlq:trackflow 0 -1

# Registro durable (PostgreSQL/Supabase)
psql "$DATABASE_URL" -c "select * from dead_letter_tasks order by created_at desc;"
```

Para forzar un fallo controlado en desarrollo:

```bash
docker compose exec worker python -c "
from app.tasks.incidents import analyze_incidents_csv
analyze_incidents_csv.apply_async(kwargs={'path': '/no-existe.csv', 'filename': 'x.csv'})
"
```

Tras ~35 s (5 + 10 + 20) la tarea aparecerá en la DLQ con `attempts=4`.

## Migración

`services/api/migrations/0003_dead_letter_tasks.sql` crea la tabla en
PostgreSQL/Supabase. En SQLite (tests) y en el arranque del worker se crea con
`SQLModel.metadata.create_all`.

## Tests

```bash
cd services/api && source venv/bin/activate && python -m pytest -q
cd uis/backoffice && npm test
```
