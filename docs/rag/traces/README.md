# Traces de referencia — agente con tools externas

Dos corridas reales del grafo por defecto, guardadas con
`run_agent(..., trace_dir="docs/rag/traces")`. Sirven como evidencia del
enrutamiento automático y de la trazabilidad de la Parte 2.

## 1. `ticket-tool-demo.json` — tool de tickets

- Pregunta: `¿En qué estado está el ticket 1?`
- `route`: `incident`
- `sources_used`: `["incident_tool"]`
- `node_order`: `receive_question → classify → tool_incident → answer_from_tool`
- `status`: `ok`
- El evento `tool_incident` incluye `tool_status: "ok"` y el registro real
  devuelto por la capa de servicio del gestor de incidencias.
- La respuesta es determinista (no pasa por el LLM): estado, categoría,
  origen, sede y fechas.

Generación: se usó un TinyDB temporal con una incidencia sembrada para no
modificar `services/api/data/suppliers.json`. La tool ejecutó el mismo
`app/services/incident_service.py` que sirve `GET /api/incidents`; no hay datos
simulados ni un dataset paralelo. El usuario de la corrida tenía rol `manager`,
porque la lectura de incidencias exige `require_manager`.

## 2. `rag-policy-demo.json` — RAG

- Pregunta: `¿Cuál es el SLA de un envío estándar dentro del mismo país?`
- `route`: `rag`
- `sources_used`: `["rag"]`
- `node_order`: `receive_question → classify → retrieve → generate`
- `status`: `ok`
- `retrieve` recuperó chunks de `sla-delivery` y `carrier-coverage` desde la
  colección `trackflow_knowledge`; `generate` produjo la respuesta citando el
  SLA de 3 a 5 días hábiles.

Generación: corrida real contra Qdrant y el proveedor LLM configurado en
`services/api/.env`. No se usó ninguna tool.

## 3. `index.jsonl`

Índice de las dos corridas (`run_id`, pregunta, estado, fichero del trace).

## Cómo regenerarlos

```bash
cd services/api
source venv/bin/activate
python - <<'PY'
import tempfile
from pathlib import Path
import database

trace_dir = Path("../../docs/rag/traces")
tmp = Path(tempfile.mkdtemp(prefix="trackflow-trace-"))
database.DB_DIR = str(tmp)
database.DB_PATH = str(tmp / "suppliers.json")

from app.agent.graph import get_agent_graph
from app.agent.runner import run_agent
from database import get_tinydb

db = get_tinydb()
ticket_id = db.table("incidents").insert({
    "title": "Paquete extraviado en aduana",
    "description": "El paquete lleva 10 días retenido en aduana.",
    "origin": "customer",
    "branch": "zaragoza_warehouse",
    "category": "lost_parcel",
    "status": "in_progress",
    "created_at": "2026-11-10T09:00:00+00:00",
    "updated_at": "2026-11-12T15:30:00+00:00",
})
db.close()

graph = get_agent_graph()
run_agent(
    f"¿En qué estado está el ticket {ticket_id}?",
    graph=graph,
    trace_dir=trace_dir,
    thread_id="ticket-tool-demo",
    user={"role": "manager"},
)
run_agent(
    "¿Cuál es el SLA de un envío estándar dentro del mismo país?",
    graph=graph,
    trace_dir=trace_dir,
    thread_id="rag-policy-demo",
)
PY
```

Los evals de enrutamiento equivalentes están en
`tests/pipelines/test_agent_evals.py` y no necesitan red ni base de datos
(inyectan dobles de las tools, el retriever y el generador).
