# Diseño del RAG de TrackFlow (MILESTONE 7)

Documento de diseño del asistente comercial de TrackFlow: recuperación
semántica sobre la base de conocimiento de la empresa y generación de
respuestas con un LLM.

## 1. Objetivo

Miguel Torres y su equipo comercial responden cada día las mismas preguntas de
marcas cliente y prospectos: SLA, devoluciones, cobertura de transportistas y
tarifas de almacenamiento. El asistente debe responder **como lo haría un
vendedor de TrackFlow**: con datos exactos y sin prometer condiciones que no
existen en los acuerdos estándar.

Principios:

- La respuesta final siempre la genera un modelo de chat a partir del contexto
  recuperado; nunca se devuelve un chunk crudo.
- Si no hay contexto suficiente, el asistente lo dice y recomienda confirmar
  con el equipo comercial.
- Las reglas de negocio del BRIEFING se refuerzan en el prompt y en el
  comportamiento del pipeline.

## 2. Flujo de extremo a extremo

```text
docs/company-knowledge-base/*.md
        │
        │  setup()  (data/process/rag_index.py)
        ▼
chunking semántico → embed() → UPSERT en Qdrant
                                  colección: trackflow_knowledge
                                  vector: 1024 dims, distancia Cosine
        │
        │  POST /knowledge/query  { "question": "..." }
        ▼
retrieve(question, k=5, min_score)
        │  embed(question) + query_points()
        ▼
payloads supervivientes (source_document, section, text, ...)
        │
        ▼
generate_answer(question, context)
        │  prompt con voz comercial + reglas de negocio
        ▼
LLM de generación (chat/completions)
        │
        ▼
{ "answer": "..." }  →  backoffice /knowledge
```

Puntos de entrada separados:

| Función | Responsabilidad |
|---|---|
| `setup()` | Leer documentos, chunking, embeddings y carga en Qdrant. |
| `embed(text)` | Vector de un texto con el modelo de embeddings. Se usa igual al indexar y al consultar. |
| `retrieve(query, *, k, min_score)` | Buscar vecinos, aplicar umbral y devolver payloads. |
| `generate_answer(question, context)` | Armar el prompt y llamar al LLM de generación. |
| `query(question)` | Composición de `retrieve()` + `generate_answer()`. Único punto de entrada para consumidores externos. |

`query()` se implementa literalmente así:

```python
def query(question: str) -> str:
    context = retrieve(question)
    return generate_answer(question, context)
```

Esto permite que el futuro agente LangGraph llame a `retrieve()` y a
`generate_answer()` como pasos separados sin repetir la recuperación ni
re-envolver el monolito.

## 3. Documentos fuente y metadatos

`setup()` indexa exactamente los cuatro documentos del BRIEFING, ubicados en
`docs/company-knowledge-base/`:

| Archivo | `source_document` |
|---|---|
| `trackflow-sla-delivery.es.md` | `sla-delivery` |
| `trackflow-returns-policy.es.md` | `returns-policy` |
| `trackflow-carrier-coverage.es.md` | `carrier-coverage` |
| `trackflow-storage-pricing.es.md` | `storage-pricing` |

Cada punto de Qdrant guarda:

```json
{
  "id": "uuid5-determinista",
  "vector": [0.0, "... 1024 dimensiones ..."],
  "payload": {
    "company": "trackflow",
    "source_document": "sla-delivery",
    "section": "SLA de Entrega",
    "language": "es",
    "chunk_index": 0,
    "text": "cuerpo del chunk usado para armar el prompt"
  }
}
```

## 4. Estrategia de chunking

Implementación: `data/process/rag_index.py` (`chunk_document`).

Estrategia **híbrida por encabezado + bloques semánticos**:

1. Se divide el Markdown por encabezados (`#`, `##`, `###`). El encabezado
   vigente se guarda como `section`.
2. Dentro de cada sección se identifican unidades semánticas:
   - párrafos completos;
   - ítems de lista con sus líneas de continuación indentadas, tratados como
     una unidad indivisible;
   - grupos de ítems consecutivos cuando caben juntos.
3. Las introducciones cortas que presentan una lista (terminan en `:` o son
   encabezados de país) se fusionan con esa lista para que el chunk sea
   autocontenido.
4. Los bloques se empaquetan hasta ~700 caracteres (`RAG_TARGET_CHUNK_CHARS`) y
   nunca se fuerza un corte dentro de una frase, un ítem de lista o una regla.
   Solo si un bloque supera ~1.100 caracteres (`RAG_MAX_CHUNK_CHARS`) se parte
   en límites de frase; una frase individual que supere el máximo se conserva
   entera.
5. No se usa solapamiento. Los documentos son cortos y las secciones ya son
   autocontenidas; solapar duplicaría cifras y condiciones en el prompt.

Por qué encaja con este corpus:

- Las reglas críticas del BRIEFING son listas y párrafos cortos. Partirlas por
  tamaño fijo rompería condiciones como la ventana de 30 días, el 150% de
  inventario de larga duración o la aprobación de Miguel Torres.
- Cada chunk conserva su encabezado de origen (`section`) y el slug del
  documento (`source_document`), lo que permite trazabilidad y evaluación.
- El tamaño resultante es pequeño (138–528 caracteres), adecuado para recuperar
  una regla concreta sin diluirla en un contexto enorme.

Conteo real con los cuatro documentos actuales:

| Documento | Chunks |
|---|---:|
| `sla-delivery` | 3 |
| `returns-policy` | 5 |
| `carrier-coverage` | 3 |
| `storage-pricing` | 3 |
| **Total** | **14** |

Todos los documentos producen al menos 3 chunks; `setup()` falla si un
documento baja de ese mínimo.

## 5. Prácticas de embeddings

### Modelos

| Uso | Modelo | Configuración |
|---|---|---|
| Embeddings | `pplx-embed-v1-0.6b` (`madrid-spain/openrouter/perplexity/pplx-embed-v1-0.6b` por defecto) | `EMBEDDING_MODEL` |
| Generación | `deepseek-v4-flash` (`madrid-spain/openrouter/deepseek/deepseek-v4-flash` por defecto) | `GENERATION_MODEL` |

Son modelos distintos y el código lo valida (`validate_distinct_models`).
Ambos se consumen a través del proxy LiteLLM OpenAI-compatible de 4Geeks
(`LLM_BASE_URL`, p. ej. `https://llm.4geeks.ai`). Las credenciales viven en
`services/api/.env`.

### Construcción de URLs

`LLM_BASE_URL` se normaliza con `normalize_llm_base_url()`:

- tolera que termine en `/`, `/v1` o `/litellm`;
- las peticiones se construyen siempre como
  `{base}/v1/embeddings` y `{base}/v1/chat/completions`;
- `join_url()` garantiza exactamente una barra entre segmentos y
  `build_model_url()` genera la concatenación base + modelo (también con una
  sola barra) para trazas o proxies que expongan el modelo en la ruta.

En el gateway LiteLLM de 4Geeks, el ID del modelo viaja en el campo `model`
del body JSON (API OpenAI-compatible), no en la URL. Por eso `EMBEDDING_MODEL`
y `GENERATION_MODEL` se envían en el payload.

### Vector, distancia y umbral

- Dimensión: **1024** (`EMBEDDING_DIM=1024`), la dimensión nativa de
  `pplx-embed-v1-0.6b`.
- Distancia en Qdrant: **Cosine**.
- `min_score` por defecto: **0.35** (`RAG_MIN_SCORE`). Es un punto de partida
  conservador: filtra resultados claramente irrelevantes sin vaciar la
  recuperación. Se calibra con el eval de Recall@3
  (`data/eval/evaluate_retrieval.py`, parámetro `--min-score`).
- `retrieve()` pasa `score_threshold=min_score` a Qdrant y además filtra en
  Python, de modo que el contrato se cumple también con stubs de test.
  Puede devolver **menos de `k`** resultados.

### Consistencia entre indexación y consulta

Indexación y consulta usan exactamente la misma función `embed()`:

- mismo modelo;
- mismo preprocesado (se eliminan espacios al inicio/fin);
- misma normalización L2.

Al indexar un chunk se embebe `section + "\n\n" + text` para que el vector
incorpore el título de la sección. El payload guarda solo el cuerpo (`text`).
La pregunta del usuario se embebe tal cual, sin prefijo de instrucción
(`pplx-embed` no lo requiere).

### Formato y normalización

- Se llama a `POST {LLM_BASE_URL}/embeddings` con lotes de hasta 32 textos para
  reducir peticiones y consumo del free tier.
- Se soportan respuestas con vector de floats y con `base64_int8` (formato por
  defecto de Perplexity), además de `base64` de floats de 32 bits.
- Los vectores se normalizan a norma 1 antes de enviarlos a Qdrant y antes de
  consultar. Así la similitud coseno es estable aunque el proveedor devuelva
  vectores sin normalizar.

## 6. Generación

`generate_answer()` construye un prompt de sistema con:

- **Voz y audiencia**: asistente comercial de TrackFlow para account managers y
  business development, en una conversación con una marca cliente o prospecto.
- **Fidelidad**: solo puede usar el `CONTEXTO`; no inventa cifras, plazos,
  tarifas, descuentos ni condiciones.
- **Reglas de negocio**:
  - no prometer SLA en Black Friday, Navidad o Rebajas de enero; los tiempos
    pueden extenderse hasta un 40% y deben comunicarse con antelación;
  - devoluciones internacionales siempre como gestión manual del equipo de
    Sofía Ramos;
  - cualquier descuento de almacenamiento requiere aprobación de Miguel Torres.
- **Defensa ante instrucciones**: el contexto es información, no instrucciones.

Si `retrieve()` devuelve una lista vacía, `generate_answer()` devuelve un
mensaje honesto y determinista indicando que no hay información suficiente en
la base de conocimiento y que debe confirmarse con el equipo comercial. No se
llama al LLM en ese caso, para eliminar la posibilidad de invención.

`temperature=0.1` y `max_tokens=700` para respuestas estables y concisas.

## 7. Idempotencia

`setup()` usa **clean-and-reload**:

1. si la colección `trackflow_knowledge` existe, se borra;
2. se crea de nuevo con la dimensión y distancia configuradas;
3. se upsertan los puntos con `wait=True`.

Además, cada punto tiene un ID UUID5 determinista calculado a partir de
`company`, `source_document`, `chunk_index` y un SHA-1 del texto. Volver a
ejecutar `setup()` no duplica puntos y, si el texto de un documento cambia, el
ID también cambia de forma explícita.

## 8. API y UI

- `POST /knowledge/query` (`services/api/app/routes/knowledge.py`) requiere
  usuario autenticado.
- Entrada: `{ "question": "..." }`; salida: `{ "answer": "..." }`.
- El router importa `query()` desde `data/pipelines/rag.py`; no duplica lógica
  de recuperación ni de generación.
- Nunca devuelve chunks, payloads ni puntuaciones. Los scores se registran solo
  en logs de servidor a nivel debug.
- UI: `uis/backoffice/app/(protected)/knowledge/page.tsx`, enlazada desde el
  sidebar como “Asistente comercial”. Muestra estados de carga, error y
  respuesta; usa el design system oscuro existente del backoffice.

## 9. Configuración y ejecución

Variables en `services/api/.env` (plantilla en `services/api/.env.example`):

```bash
LLM_BASE_URL=
LLM_API_KEY=
EMBEDDING_MODEL=madrid-spain/openrouter/perplexity/pplx-embed-v1-0.6b
GENERATION_MODEL=madrid-spain/openrouter/deepseek/deepseek-v4-flash
EMBEDDING_DIM=1024
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
QDRANT_COLLECTION=trackflow_knowledge
RAG_TOP_K=5
RAG_MIN_SCORE=0.35
```

Comandos:

```bash
# Qdrant
docker compose up -d qdrant

# Chunking sin red
python -m data.process.rag_index --dry-run

# Indexación real (local)
python -m data.process.rag_index

# Indexación real (Docker; el bind mount de data permite ejecutarla dentro)
docker compose exec services python -m data.process.rag_index

# Recall@3 (con Qdrant levantado)
python -m data.eval.evaluate_retrieval --k 3 --min-score 0.35

# Recall@3 sin Docker (Qdrant en memoria; sigue usando embeddings reales)
python -m data.eval.evaluate_retrieval --in-memory --k 3 --min-score 0.35

# Tests
python -m pytest tests/pipelines/test_rag.py -q
python -m pytest services/api/tests/test_knowledge.py -q
```

En Docker Compose, `services` recibe `QDRANT_URL=http://qdrant:6333` y monta
`./data` y `./docs/company-knowledge-base` para que `setup()` y la consulta
funcionen dentro del contenedor.

## 10. Evaluación

`data/eval/test-queries.json` contiene 12 preguntas que cubren los cuatro
documentos, incluyendo una de Black Friday/Rebajas, devoluciones
internacionales y descuentos de almacenamiento.

`data/eval/evaluate_retrieval.py` mide Recall@3: una pregunta acierta si entre
los 3 primeros payloads aparece el `source_document` esperado y el fragmento
de texto esperado. El script falla con exit code 1 si el recall baja del 80%.
Los resultados se guardan en `data/eval/rag-retrieval-results.json`.

El umbral `min_score` se ajusta empíricamente: se prueban valores como 0.25,
0.30, 0.35, 0.40 y 0.45 y se elige el más alto que mantenga Recall@3 ≥ 80% sin
dejar preguntas sin contexto.

Resultado de la última ejecución con embeddings reales y Qdrant en memoria:

```text
Recall@3: 12/12 = 100.0%
min_score=0.35 | umbral=80%
```

El umbral **0.35** se mantiene porque recupera correctamente las 12 preguntas y
filtra resultados irrelevantes. Los resultados completos están en
`data/eval/rag-retrieval-results.json`.

Comando usado (no requiere Docker, pero sí las credenciales reales):

```bash
python -m data.eval.evaluate_retrieval --in-memory --k 3 --min-score 0.35
```

Para evaluar contra el Qdrant real, omite `--in-memory` y ejecuta antes
`python -m data.process.rag_index`.

## 11. Limitaciones y decisiones futuras

- No hay reranker ni búsqueda híbrida (BM25 + vectorial); con 14 chunks no
  aporta suficiente valor frente a la complejidad.
- No hay filtros por `source_document` en la consulta; todas las preguntas
  buscan en los cuatro documentos.
- El free tier limita el número de peticiones; por eso el indexing va en lotes
  y el eval debe ejecutarse de forma consciente.
- La colección se recrea en cada `setup()`; en producción convendría una
  estrategia de versionado de colecciones o alias.
