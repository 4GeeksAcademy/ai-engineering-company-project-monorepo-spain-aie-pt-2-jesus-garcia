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

## Errores HTTP

| Código | Situación |
|---|---|
| 400 | Falta `file`, archivo vacío, o formato incorrecto (CSV inválido / columnas faltantes) |
| 404 | No hay análisis previo al intentar exportar |

## Tests

```bash
pytest -q
```
