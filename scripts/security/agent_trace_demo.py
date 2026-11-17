"""Genera una traza real del agente (sin red ni LLM) para la evidencia NIST.

Ejecuta el grafo completo con un retriever y un generador deterministas, escribe
el JSON de traza en el directorio indicado y resume los campos que demuestran
trazabilidad: ruta decidida, nodos ejecutados, fuentes usadas, eventos de
guardrail y estado final.

Uso:

    services/api/venv/bin/python scripts/security/agent_trace_demo.py \
        --out docs/cybersecurity/nist-ai-security/evidence
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "services" / "api"
for path in (API_ROOT, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.agent.graph import compile_agent_graph  # noqa: E402
from app.agent.runner import run_agent  # noqa: E402
from app.agent.tracing import AgentTrace  # noqa: E402

CHUNKS = [
    {
        "company": "trackflow",
        "source_document": "sla-delivery",
        "section": "SLA de Entrega",
        "chunk_index": 0,
        "text": (
            "El envío estándar dentro del mismo país tarda de 3 a 5 días "
            "hábiles, con un 90 % de entregas a tiempo."
        ),
    }
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default="docs/cybersecurity/nist-ai-security/evidence",
        help="Directorio donde escribir la traza y el resumen",
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    graph = compile_agent_graph(
        retriever=lambda question: CHUNKS,
        generator=lambda question, context: (
            "El envío estándar dentro del mismo país tarda de 3 a 5 días "
            "hábiles, con un 90 % de entregas a tiempo (documento "
            "sla-delivery, sección SLA de Entrega)."
        ),
    )

    result = run_agent(
        "¿Cuál es el SLA estándar de un envío en España?",
        graph=graph,
        trace_dir=out_dir,
        run_id="nist-trace-demo",
        user={"id": "1", "email": "manager@example.com", "role": "manager"},
    )
    trace = AgentTrace.load(result.trace_path)

    print("TRAZA DEL AGENTE — evidencia de trazabilidad")
    print("=" * 90)
    print(f"run_id        : {trace.run_id}")
    print(f"estado        : {trace.status}")
    print(f"ruta          : {trace.route or '(sin classify)'}")
    print(f"nodos         : {' → '.join(trace.node_order)}")
    print(f"fuentes_used  : {', '.join(trace.sources_used) or '(ninguna)'}")
    print(f"guard_events  : {len(trace.guard_events)}")
    print(f"respuesta     : {trace.answer[:120]}")
    print(f"traza         : {trace.trace_path}")
    print("=" * 90)
    print("Cada nodo del JSON incluye input/output resumido, duración y timestamp;")
    print("los bloqueos del harness se guardan en `guard_events` (categoría y motivo).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
