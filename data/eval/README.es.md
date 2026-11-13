# Carpeta `data/eval`

Esta carpeta está orientada a **evaluación y validación**: datasets de evaluación, “golden sets”, resultados de experimentos, métricas, y artefactos usados para medir calidad de modelos, RAG, agentes o pipelines.

- **Propósito principal**: centralizar los insumos y salidas de evaluación para asegurar mejoras medibles a lo largo de los hitos del proyecto.
- **Recomendación**: documenta cada set de evaluación (qué mide, cómo se construyó, criterios de éxito) y evita incluir datos sensibles; si es necesario, usa datos sintéticos o anonimizados.

## Eval de retrieval RAG (MILESTONE 7)

- `test-queries.json` — 12 preguntas que cubren los cuatro documentos de `docs/company-knowledge-base/`.
- `evaluate_retrieval.py` — mide Recall@3 con `retrieve()`; falla si < 80%. Resultados en `rag-retrieval-results.json`.

```bash
# Con Qdrant levantado
python -m data.eval.evaluate_retrieval --k 3 --min-score 0.35

# Sin Docker: indexa en un Qdrant en memoria antes de evaluar
python -m data.eval.evaluate_retrieval --in-memory --k 3 --min-score 0.35
```
