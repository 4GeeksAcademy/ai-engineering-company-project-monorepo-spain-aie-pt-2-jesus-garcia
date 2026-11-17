"""Demo determinista del harness del agente de CX (sin red ni LLM).

Ejecuta el corpus de ``services/api/tests/fixtures/harness_corpus.json`` y
muestra la decisión de cada capa, varios casos de validación de salida y el
resumen de contadores que expone ``GET /agent/harness/stats``.

Uso::

    services/api/venv/bin/python scripts/demo_agent_harness.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "services" / "api"
for path in (API_ROOT, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.agent.harness.observability import metrics  # noqa: E402
from app.agent.harness.orders import (  # noqa: E402
    InMemoryOrderResolver,
    OrderOwner,
)
from app.agent.harness.output import validate_output  # noqa: E402
from app.agent.harness.runtime import screen_input  # noqa: E402

CORPUS_PATH = API_ROOT / "tests" / "fixtures" / "harness_corpus.json"


def _resolver(case: dict) -> InMemoryOrderResolver:
    if not case.get("order_owner_email"):
        return InMemoryOrderResolver()
    return InMemoryOrderResolver(
        {
            case["order_ref"]: OrderOwner(
                order_ref=case["order_ref"],
                owner_email=case["order_owner_email"],
                country=case.get("order_country", "US"),
            )
        }
    )


def _user(case: dict) -> dict | None:
    if not case.get("user_email"):
        return None
    return {"id": "1", "email": case["user_email"], "role": "user"}


def _print_corpus() -> int:
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    failures = 0
    print("INPUT GUARD — corpus determinista")
    print("-" * 100)
    for case in corpus:
        result = screen_input(
            case["text"],
            user=_user(case),
            order_resolver=_resolver(case),
            run_id="demo",
            session_id="demo-session",
        )
        expected = case["expected"]
        ok = (
            result.action == expected["action"]
            and result.category == expected["category"]
            and result.guard == expected["guard"]
        )
        if not ok:
            failures += 1
        status = "OK" if ok else "FAIL"
        print(
            f"{status:4} {case['id']:10} {result.action:10} "
            f"{str(result.category):10} {str(result.guard):26} "
            f"{(result.answer or '')[:48]}"
        )
    print()
    return failures


def _print_output_guard() -> None:
    print("OUTPUT GUARD — validación de respuestas")
    print("-" * 100)
    cases = [
        (
            "Respuesta limpia",
            "El envío estándar tarda de 3 a 5 días hábiles.",
            {},
        ),
        (
            "Fuga de system prompt",
            "Eres el agente de atención al cliente de primera línea de TrackFlow.",
            {},
        ),
        (
            "Tarifa negociada",
            "La tarifa negociada con UPS es 4,20 USD por kg.",
            {},
        ),
        (
            "Dirección de almacén",
            "El almacén está en Calle de los Almacenes 45, nave 7.",
            {},
        ),
        (
            "Pedido ajeno",
            "El pedido #45821 está entregado.",
            {"authorized_order_refs": ["1001"]},
        ),
        (
            "Mezcla de políticas",
            "Según la política de devoluciones de España, tienes 30 días.",
            {"required_country": "US"},
        ),
    ]
    for label, answer, kwargs in cases:
        decision = validate_output(
            answer,
            run_id="demo",
            session_id="demo-session",
            **kwargs,
        )
        print(
            f"{decision.action:8} {str(decision.reason):20} {label:26} "
            f"{decision.answer[:46]}"
        )
    print()


def _print_stats() -> None:
    snapshot = metrics.snapshot(session_id="demo-session")
    print("RESUMEN — GET /agent/harness/stats?session_id=demo-session")
    print("-" * 100)
    print(json.dumps(snapshot, ensure_ascii=False, indent=2)[:3_500])
    print()


def main() -> int:
    failures = _print_corpus()
    _print_output_guard()
    _print_stats()
    if failures:
        print(f"FALLARON {failures} casos del corpus.")
        return 1
    print("Todos los casos del corpus pasaron.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
