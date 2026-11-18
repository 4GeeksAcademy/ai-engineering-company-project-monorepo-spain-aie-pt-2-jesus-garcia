"""Graba traces reales del agente para los evals de anclaje.

Uso (requiere Qdrant con la colección indexada y credenciales en
``services/api/.env``):

    uv run python scripts/record_agent_traces.py
    uv run python scripts/record_agent_traces.py --only sla-standard

Los artefactos se escriben en ``tests/pipelines/fixtures/agent_traces/`` y se
commitean: los evals los leen sin hacer llamadas de red ni al LLM.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.api.app.agent.runner import run_agent  # noqa: E402
from services.api.app.agent.tracing import AgentTrace  # noqa: E402

DEFAULT_OUT = ROOT / "tests" / "pipelines" / "fixtures" / "agent_traces"

CASES: list[dict[str, Any]] = [
    {
        "id": "sla-standard",
        "question": "¿Cuál es el SLA de un envío estándar dentro del mismo país?",
        "expected_source_document": "sla-delivery",
        "expected_answer_contains": "3 a 5 días hábiles",
    },
    {
        "id": "sla-peak-demand",
        "question": "¿Se garantiza el SLA durante Black Friday o las Rebajas de enero?",
        "expected_source_document": "sla-delivery",
        "expected_answer_contains": "40%",
    },
    {
        "id": "returns-international",
        "question": "¿Cómo se gestionan las devoluciones internacionales?",
        "expected_source_document": "returns-policy",
        "expected_answer_contains": "gestión manual",
    },
    {
        "id": "storage-discount-approval",
        "question": "¿Quién aprueba un descuento de almacenamiento?",
        "expected_source_document": "storage-pricing",
        "expected_answer_contains": "Miguel Torres",
    },
]


def flat(text: str) -> str:
    """Normaliza espacios para comparar fragmentos (p. ej. ``40 %`` vs ``40%``)."""
    return re.sub(r"\s+", "", text or "").lower()


def record_case(case: dict[str, Any], out_dir: Path) -> bool:
    result = run_agent(
        case["question"],
        thread_id=case["id"],
        trace_dir=out_dir,
    )
    trace = AgentTrace.load(result.trace_path)
    sources = [source.get("source_document") for source in trace.retrieved_sources]

    answer_ok = flat(case["expected_answer_contains"]) in flat(trace.answer)
    source_ok = case["expected_source_document"] in sources

    print(
        f"[{case['id']}] status={trace.status} "
        f"nodes={' -> '.join(trace.node_order)} "
        f"answer_ok={answer_ok} source_ok={source_ok}"
    )
    print(f"  fuentes: {sources}")
    print(f"  respuesta: {trace.answer[:220]}...")

    if not (answer_ok and source_ok and trace.status == "ok"):
        print(f"  !! el caso {case['id']} no está anclado en la base de conocimiento")
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Graba traces reales del agente para los evals de anclaje."
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help="Directorio de fixtures (por defecto tests/pipelines/fixtures/agent_traces).",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        default=None,
        help="IDs concretos a grabar (por defecto, todos).",
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    selected = [case for case in CASES if not args.only or case["id"] in args.only]
    if not selected:
        print(f"No hay casos que coincidan con --only {args.only}")
        return 2

    results = [record_case(case, out_dir) for case in selected]

    # El índice es útil en runtime, pero los fixtures se identifican por ID.
    index = out_dir / "index.jsonl"
    if index.exists():
        index.unlink()

    if not all(results):
        return 1
    print(f"\n{len(results)} traces grabados en {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
