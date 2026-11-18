"""Grafo dedicado ``rfp_intake`` (orchestrator-worker-synthesizer).

Flujo:
    validate_input → convert_pdf (PDF→Markdown + legibilidad) → classify
    classify --no es RFP--> descartado (END)
    classify --es RFP--> extract_metadata → orchestrate
    orchestrate --sin departamentos--> descartado (END)
    orchestrate --workers (Send)--> worker paralelo por departamento → synthesize
    synthesize --> analisis_completo

El grafo no conoce PostgreSQL: persiste a través de ``RfpRepository``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .classifier import classify_document
from .ingest import convert_pdf_to_markdown
from .llm import JsonLlm
from .metadata import extract_metadata
from .orchestrator import build_plan
from .readability import compute_readability
from .state import RfpIntakeState
from .synthesizer import build_handoff
from .worker import build_section

logger = logging.getLogger(__name__)

Converter = Callable[[Path, Path], dict]


def _markdown_path(pdf_path: str, known: str | None) -> str:
    if known:
        return known
    return str(Path(pdf_path).parent / "rfp.md")


def _event(stage: str, **extra) -> dict:
    return {"stage": stage, **extra}


def build_rfp_graph(
    *,
    repo,
    llm: JsonLlm,
    converter: Converter = convert_pdf_to_markdown,
):
    """Declara, conecta y compila el grafo. Las dependencias van por cierre."""

    def validate_input(state: RfpIntakeState) -> dict:
        ticket = repo.get_ticket(state["ticket_id"])
        pdf_path = ticket["raw_pdf_path"]
        if not pdf_path:
            raise ValueError(
                f"El ticket {state['ticket_id']} no tiene PDF asociado."
            )
        return {
            "rfp_id": ticket["rfp_id"],
            "pdf_path": pdf_path,
            "markdown_path": _markdown_path(pdf_path, ticket.get("markdown_path")),
            "status": "processing",
            "stage": "validando",
            "events": [_event("validate_input", pdf_path=pdf_path)],
        }

    def convert_pdf(state: RfpIntakeState) -> dict:
        repo.set_stage(state["ticket_id"], "convirtiendo")
        markdown_path = Path(state["markdown_path"])
        if markdown_path.exists() and markdown_path.stat().st_size > 0:
            markdown = markdown_path.read_text(encoding="utf-8")
            document_metadata = {"reused_markdown": True}
            source = "cache"
        else:
            conversion = converter(Path(state["pdf_path"]), markdown_path)
            markdown = conversion["markdown"]
            document_metadata = conversion["document_metadata"]
            source = "markitdown"
        readability = compute_readability(markdown)
        repo.save_conversion(
            state["ticket_id"],
            markdown_path=str(markdown_path),
            document_metadata=document_metadata,
            readability=readability,
        )
        repo.set_stage(state["ticket_id"], "markdown_listo")
        return {
            "markdown": markdown,
            "markdown_path": str(markdown_path),
            "document_metadata": document_metadata,
            "readability": readability,
            "stage": "markdown_listo",
            "events": [
                _event(
                    "convert_pdf",
                    source=source,
                    chars=len(markdown),
                    tokens=readability.get("estimated_llm_tokens"),
                )
            ],
        }

    def classify(state: RfpIntakeState) -> dict:
        repo.set_stage(state["ticket_id"], "clasificando")
        classification = classify_document(state["markdown"], llm)
        if not classification["is_rfp"]:
            repo.discard(
                state["ticket_id"],
                reason=classification["reason"],
                classification=classification,
            )
            return {
                "classification": classification,
                "is_rfp": False,
                "discard_reason": classification["reason"],
                "status": "discarded",
                "stage": "descartado",
                "events": [
                    _event(
                        "classify",
                        is_rfp=False,
                        confidence=classification["confidence"],
                        reason=classification["reason"],
                    )
                ],
            }
        return {
            "classification": classification,
            "is_rfp": True,
            "status": "processing",
            "stage": "clasificado",
            "events": [
                _event(
                    "classify",
                    is_rfp=True,
                    confidence=classification["confidence"],
                    services=classification["services_requested"],
                )
            ],
        }

    def extract_metadata_node(state: RfpIntakeState) -> dict:
        repo.set_stage(state["ticket_id"], "extrayendo_metadatos")
        metadata = extract_metadata(
            state["markdown"], state["classification"], llm
        )
        repo.save_metadata(
            state["ticket_id"],
            metadata=metadata,
            classification=state["classification"],
        )
        return {
            "metadata": metadata,
            "unknown_services": metadata.get("unknown_services", []),
            "stage": "metadatos_extraidos",
            "events": [
                _event(
                    "extract_metadata",
                    client=metadata.get("client_name"),
                    country=metadata.get("client_country"),
                    currency=metadata.get("currency"),
                    services=metadata.get("services_requested"),
                    monthly_volume=metadata.get("monthly_volume"),
                    missing_fields=metadata.get("missing_fields"),
                )
            ],
        }

    def orchestrate(state: RfpIntakeState) -> dict:
        repo.set_stage(state["ticket_id"], "orquestando")
        plan = build_plan(state["metadata"], state["markdown"], llm)
        if not plan:
            reason = (
                "La RFP no solicita ningún servicio del catálogo de TrackFlow "
                "(warehousing, last_mile, reverse_logistics)."
            )
            repo.discard(
                state["ticket_id"],
                reason=reason,
                classification=state["classification"],
            )
            return {
                "plan": [],
                "status": "discarded",
                "discard_reason": reason,
                "stage": "descartado",
                "events": [_event("orchestrate", departments=[], reason=reason)],
            }
        departments = [item["department_id"] for item in plan]
        repo.save_plan(state["ticket_id"], departments=departments)
        return {
            "plan": plan,
            "stage": "orquestado",
            "events": [_event("orchestrate", departments=departments)],
        }

    def worker(state: RfpIntakeState) -> dict:
        workstream = state["workstream"]
        department_id = workstream["department_id"]
        repo.set_stage(
            state["ticket_id"], f"analizando_{department_id}"
        )
        section = build_section(workstream, state["metadata"], llm)
        repo.save_section(state["ticket_id"], section=section)
        return {
            "sections": {department_id: section},
            "events": [
                _event(
                    "worker",
                    department_id=department_id,
                    aspects=len(section["key_aspects"]),
                    questions=len(section["open_questions"]),
                    unsupported=len(section.get("unsupported_claims", [])),
                )
            ],
        }

    def synthesize(state: RfpIntakeState) -> dict:
        repo.set_stage(state["ticket_id"], "sintetizando")
        handoff = build_handoff(
            ticket_id=state["ticket_id"],
            rfp_id=state["rfp_id"],
            metadata=state["metadata"],
            sections=state.get("sections", {}),
            classification=state["classification"],
            readability=state.get("readability", {}),
            document_metadata=state.get("document_metadata", {}),
            pdf_path=state["pdf_path"],
            markdown_path=state["markdown_path"],
            llm=llm,
        )
        repo.complete(state["ticket_id"], handoff=handoff)
        return {
            "handoff": handoff,
            "sales_summary": handoff["sales_summary"],
            "conflicts": handoff.get("conflicts", []),
            "status": "completed",
            "stage": "completado",
            "events": [
                _event(
                    "synthesize",
                    departments=[
                        item["department_id"] for item in handoff["departments"]
                    ],
                    questions=len(handoff["questions_to_ask"]),
                )
            ],
        }

    def route_after_classify(state: RfpIntakeState):
        return END if state.get("status") == "discarded" else "extract_metadata"

    def route_to_workers(state: RfpIntakeState):
        if state.get("status") == "discarded":
            return END
        return [
            Send(
                "worker",
                {
                    "ticket_id": state["ticket_id"],
                    "metadata": state["metadata"],
                    "workstream": workstream,
                },
            )
            for workstream in state.get("plan", [])
        ]

    builder = StateGraph(RfpIntakeState)
    builder.add_node("validate_input", validate_input)
    builder.add_node("convert_pdf", convert_pdf)
    builder.add_node("classify", classify)
    builder.add_node("extract_metadata", extract_metadata_node)
    builder.add_node("orchestrate", orchestrate)
    builder.add_node("worker", worker)
    builder.add_node("synthesize", synthesize)

    builder.add_edge(START, "validate_input")
    builder.add_edge("validate_input", "convert_pdf")
    builder.add_edge("convert_pdf", "classify")
    builder.add_conditional_edges(
        "classify",
        route_after_classify,
        {"extract_metadata": "extract_metadata", END: END},
    )
    builder.add_edge("extract_metadata", "orchestrate")
    builder.add_conditional_edges(
        "orchestrate",
        route_to_workers,
        ["worker", END],
    )
    builder.add_edge("worker", "synthesize")
    builder.add_edge("synthesize", END)

    return builder.compile()
