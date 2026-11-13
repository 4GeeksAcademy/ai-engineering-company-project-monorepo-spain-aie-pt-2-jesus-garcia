# `data/process` folder

This folder contains **processed/intermediate data** and/or artifacts produced by pipelines (for example: clean datasets, features, aggregates, intermediate tables, or transformation outputs).

- **Main purpose**: clearly separate “raw” data from data ready for analysis, modeling, or app consumption.
- **Recommendation**: document which pipeline produces each artifact, its schema, refresh cadence, and how quality is validated (checks, constraints, data tests).

## RAG — Indexación de la base de conocimiento (MILESTONE 7)

- `rag_config.py` — configuración compartida (Qdrant, modelos de 4Geeks, rutas,
  tamaños de chunk y umbral).
- `rag_index.py` — `load_source_documents()`, `chunk_document()`, `embed()` y
  `setup()`. Indexa los cuatro documentos de `docs/company-knowledge-base/` en
  la colección Qdrant `trackflow_knowledge`.
- Idempotencia: `setup()` borra y recrea la colección (clean-and-reload) y usa
  UUID5 deterministas.

```bash
python -m data.process.rag_index --dry-run   # solo chunking, sin red
python -m data.process.rag_index             # indexa en Qdrant
```

Documentación de diseño: [`docs/rag/rag-design.md`](../../docs/rag/rag-design.md).

> _Spanish version: [README.es.md](./README.es.md)._
