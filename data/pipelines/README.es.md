# Carpeta `data/pipelines`

Esta carpeta agrupa **todos los pipelines de datos del monorepo** relacionados con la compañía: procesos de ingesta, ETL/ELT, limpieza, transformación y carga hacia sistemas analíticos o de producción.

Cada subcarpeta o archivo dentro de `data/pipelines/` debe representar **un pipeline o conjunto de jobs** (por ejemplo `sales-etl`, `telemetry-stream`, `customer-segmentation`) e incluir la configuración necesaria (scripts, orquestación, conectores, esquemas, etc.).

- **Propósito principal**: unificar en un único lugar la lógica de movimiento y transformación de datos que soporta las aplicaciones y analíticas de la compañía.
- **Recomendación**: documenta aquí los pipelines que vayas añadiendo, describiendo su objetivo, orígenes/destinos de datos, dependencias y cómo ejecutarlos en desarrollo, pruebas y producción.

## Pipeline RAG (MILESTONE 7)

Entrypoint de consulta: [`rag.py`](./rag.py). Expone `retrieve()`, `generate_answer()` y `query()`; el endpoint `POST /knowledge/query` importa `query()` sin duplicar lógica.

```bash
python -m data.eval.evaluate_retrieval --k 3 --min-score 0.35
```

Diseño: [`docs/rag/rag-design.md`](../../docs/rag/rag-design.md).
