# `data/eval` folder

This folder is for **evaluation and validation**: evaluation datasets, golden sets, experiment results, metrics, and artifacts used to measure quality for models, RAG, agents, or pipelines.

- **Main purpose**: centralize evaluation inputs and outputs so improvements stay measurable across project milestones.
- **Recommendation**: document each evaluation set (what it measures, how it was built, success criteria) and avoid sensitive data; use synthetic or anonymized data when needed.

## RAG retrieval eval (MILESTONE 7)

- `test-queries.json` — 12 preguntas que cubren los cuatro documentos de
  `docs/company-knowledge-base/`.
- `evaluate_retrieval.py` — mide Recall@3 con `retrieve()`; falla si < 80%.
  Resultados en `rag-retrieval-results.json`.

```bash
# Con Qdrant levantado
python -m data.eval.evaluate_retrieval --k 3 --min-score 0.35

# Sin Docker: indexa en un Qdrant en memoria antes de evaluar
python -m data.eval.evaluate_retrieval --in-memory --k 3 --min-score 0.35
```

> _Spanish version: [README.es.md](./README.es.md)._
