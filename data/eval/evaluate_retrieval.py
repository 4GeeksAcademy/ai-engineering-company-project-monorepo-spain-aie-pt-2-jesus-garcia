"""Evalúa Recall@k del retrieval RAG contra el archivo de preguntas de prueba."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from data.pipelines.rag import retrieve
from data.process.rag_config import DEFAULT_MIN_SCORE, RagError

EVAL_DIR = Path(__file__).resolve().parent
QUERIES_PATH = EVAL_DIR / "test-queries.json"
DEFAULT_OUTPUT = EVAL_DIR / "rag-retrieval-results.json"


def _normalize(value: str) -> str:
    return " ".join(value.lower().split())


def _matches(payload: dict, expected_source: str, expected_text: str) -> bool:
    return (
        payload.get("source_document") == expected_source
        and _normalize(expected_text) in _normalize(payload.get("text", ""))
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mide Recall@k de retrieve() contra data/eval/test-queries.json."
    )
    parser.add_argument("--k", type=int, default=None)
    parser.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    parser.add_argument("--threshold", type=float, default=0.8)
    parser.add_argument(
        "--in-memory",
        action="store_true",
        help=(
            "Indexa en un Qdrant en memoria antes de evaluar. Útil sin Docker, "
            "pero sigue necesitando LLM_BASE_URL/LLM_API_KEY para embeddings."
        ),
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if args.in_memory:
        from qdrant_client import QdrantClient

        from data.pipelines import rag as rag_module
        from data.process import rag_index

        client = QdrantClient(location=":memory:")
        rag_index.get_qdrant_client = lambda: client
        rag_module.get_qdrant_client = lambda: client
        stats = rag_index.setup(recreate=True)
        print(f"Índice en memoria: {stats['chunks']} chunks.")

    data = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))
    queries = data.get("queries", [])
    if not queries:
        print("No hay preguntas en test-queries.json", file=sys.stderr)
        return 2

    k = args.k or int(data.get("k", 3))
    results = []
    hits = 0
    try:
        for item in queries:
            payloads = retrieve(
                item["question"],
                k=k,
                min_score=args.min_score,
            )
            matched = next(
                (
                    payload
                    for payload in payloads
                    if _matches(
                        payload,
                        item["expected_source_document"],
                        item["expected_text_contains"],
                    )
                ),
                None,
            )
            hit = matched is not None
            hits += int(hit)
            results.append(
                {
                    "id": item["id"],
                    "question": item["question"],
                    "expected_source_document": item["expected_source_document"],
                    "expected_text_contains": item["expected_text_contains"],
                    "hit": hit,
                    "returned": [
                        {
                            "source_document": payload.get("source_document"),
                            "section": payload.get("section"),
                            "chunk_index": payload.get("chunk_index"),
                        }
                        for payload in payloads
                    ],
                }
            )
    except RagError as exc:
        print(f"No se pudo ejecutar el eval: {exc}", file=sys.stderr)
        return 2

    recall = hits / len(queries)
    report = {
        "company": data.get("company", "trackflow"),
        "collection": data.get("collection", "trackflow_knowledge"),
        "k": k,
        "min_score": args.min_score,
        "queries": len(queries),
        "hits": hits,
        "recall_at_k": recall,
        "threshold": args.threshold,
        "passed": recall >= args.threshold,
        "results": results,
    }
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Recall@{k}: {hits}/{len(queries)} = {recall:.1%}")
    print(f"min_score={args.min_score} | umbral={args.threshold:.0%}")
    for result in results:
        mark = "OK " if result["hit"] else "MISS"
        print(f"  [{mark}] {result['id']}: {result['question']}")
    print(f"Resultados guardados en {args.output}")

    return 0 if recall >= args.threshold else 1


if __name__ == "__main__":
    raise SystemExit(main())
