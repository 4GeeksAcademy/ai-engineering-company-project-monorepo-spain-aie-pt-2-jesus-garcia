# TrackFlow Incidents API

Servicio backend para el análisis de incidentes del departamento de **Experiencia del cliente**.

## Objetivo

- **`POST /api/incidents/analyze`** — Recibe un CSV (`multipart/form-data`, campo `file`), ejecuta la
  validación y el análisis de incidentes y devuelve el resumen en JSON.
- **`GET /api/incidents/results/export`** — Devuelve el último análisis en formato CSV descargable
  (métricas resumen).

La lógica de validación/análisis es compartida con el script CLI `analyze.py` (raíz del monorepo)
a través del módulo `app/incidents/analyzer.py`.

## Requisitos

Python 3.12+ y `pandas`. Las dependencias se listan en `requirements.txt`.

## Instalación

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

> El entorno virtual del backend vive en `services/api/venv/` — usar SIEMPRE este (el `.venv` raíz del monorepo no tiene las deps de la API).

## Ejecución

```bash
uvicorn app.main:app --reload --port 8000
```

Documentación interactiva: `http://localhost:8000/docs`.

## Uso

```bash
# Analizar un CSV
curl -F "file=@COMPANY.csv" http://localhost:8000/api/incidents/analyze

# Exportar el último análisis en CSV
curl http://localhost:8000/api/incidents/results/export -o results.csv
```

## Inventario: cliente, umbral y discrepancias

- `SKU.client_id` y `SKU.min_stock` son **nullable**: `NULL` significa “pendiente
  de mapeo” / “umbral no configurado”. El pipeline manda esos eventos a
  cuarentena y no publica ceros.
- `POST /inventory/discrepancies` registra el detalle SQL y emite un único evento
  `inventory_discrepancy_detected` por `order_id` (manager/admin).
- Las órdenes y discrepancias escriben su evento en `ops.telemetry_outbox` en la
  misma transacción; el relay del pipeline lo mueve a `telemetry_events`.
- Mapeo masivo por CSV:

```bash
python import_sku_mapping.py --file data/sku_mapping.csv --dry-run
python import_sku_mapping.py --file data/sku_mapping.csv --allow-remote-db
```

Formato: `sku_code,client_id,min_stock` (ver
`data/sku_mapping.example.csv`). Migración: `migrations/0001_g1_g4.sql`.

## Reporting (desempeño semanal)

Módulo `app/reporting/` — solo lectura sobre el esquema `reporting` que escribe
el pipeline (`pipelines/weekly_performance`). Requiere rol `manager`/`admin`.

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/reporting/weekly-warehouse-client-performance?week_start=YYYY-MM-DD` | Reporte de la semana (por defecto, la última calculada) |
| GET | `/reporting/pipeline-runs/latest` | Estado y metadata de la última corrida |
| POST | `/reporting/pipeline-runs` | Dispara una corrida manual (`202`; `409` si hay una en curso; `503` si Prefect no responde) |

`PREFECT_API_URL` (por defecto `http://localhost:4200/api`) apunta al servidor
Prefect self-hosted o a Prefect Cloud.

## Errores HTTP

| Código | Situación |
|---|---|
| 400 | Falta `file`, archivo vacío, o formato incorrecto (CSV inválido / columnas faltantes) |
| 404 | No hay análisis previo al intentar exportar |

## Tests

```bash
pytest -q
```
