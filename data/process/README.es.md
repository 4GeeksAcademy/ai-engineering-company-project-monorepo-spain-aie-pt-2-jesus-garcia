# Carpeta `data/process`

Esta carpeta contiene **datos procesados/intermedios** y/o artefactos derivados de los pipelines (por ejemplo: datasets limpios, features, agregados, tablas intermedias o resultados de transformaciones).

- **Propósito principal**: separar claramente los datos “raw” de los datos listos para análisis/modelado/consumo por apps.
- **Recomendación**: documenta qué pipeline genera cada artefacto, su esquema, periodicidad, y cómo se valida su calidad (checks, constraints, tests de datos).

## RAG — Indexación de la base de conocimiento (MILESTONE 7)

- `rag_config.py` — configuración compartida (Qdrant, modelos de 4Geeks, rutas, tamaños de chunk y umbral).
- `rag_index.py` — `load_source_documents()`, `chunk_document()`, `embed()` y `setup()`. Indexa los cuatro documentos de `docs/company-knowledge-base/` en la colección Qdrant `trackflow_knowledge`.
- Idempotencia: `setup()` borra y recrea la colección (clean-and-reload) y usa UUID5 deterministas.

```bash
python -m data.process.rag_index --dry-run   # solo chunking, sin red
python -m data.process.rag_index             # indexa en Qdrant
```

Diseño: [`docs/rag/rag-design.md`](../../docs/rag/rag-design.md).
