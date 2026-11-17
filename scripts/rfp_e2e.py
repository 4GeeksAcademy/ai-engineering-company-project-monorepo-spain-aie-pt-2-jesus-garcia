#!/usr/bin/env python
"""E2E reproducible de las Partes 1→3 del Hito 9.

Modo por defecto (``seeded``): usa el fixture determinista del handoff de la
Parte 1, ejecuta la Parte 2 con un LLM guionizado y la Parte 3 con
aprobaciones humanas simuladas. No necesita red ni claves.

Modo ``--live``: ejecuta la Parte 1 real sobre el PDF con ``LLM_API_KEY``
(``services/api/.env``), luego la Parte 2 y la Parte 3 con un LLM real.

Ejemplos:
    services/api/venv/bin/python scripts/rfp_e2e.py
    services/api/venv/bin/python scripts/rfp_e2e.py --live \
        --pdf docs/workflows/rfp-requests/trackflow-request-1.pdf
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES_API = ROOT / "services" / "api"
PIPELINES = ROOT / "tests" / "pipelines"
for path in (ROOT, SERVICES_API, PIPELINES):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Usa el LLM real y el PDF de la Parte 1 (requiere LLM_API_KEY).",
    )
    parser.add_argument(
        "--pdf",
        default="docs/workflows/rfp-requests/trackflow-request-1.pdf",
        help="PDF de la RFP para el modo --live.",
    )
    parser.add_argument(
        "--fixture",
        choices=["modaviva", "luna"],
        default="modaviva",
        help="Fixture de la Parte 1 en modo seeded.",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Conserva la BD, checkpoints y trazas temporales.",
    )
    parser.add_argument(
        "--pause-before-approvals",
        action="store_true",
        help="Deja el ticket esperando aprobación y sale (para revisar la UI).",
    )
    return parser.parse_args()


def _setup_env(args: argparse.Namespace) -> Path:
    from dotenv import load_dotenv

    load_dotenv(SERVICES_API / ".env")
    workdir = Path(tempfile.mkdtemp(prefix="rfp-e2e-"))
    os.environ["DATABASE_URL"] = f"sqlite:///{workdir / 'e2e.db'}"
    os.environ["RFP_APPROVAL_CHECKPOINT_DB"] = str(
        workdir / "checkpoints.db"
    )
    os.environ["RFP_APPROVAL_TRACE_DIR"] = str(workdir / "approval-traces")
    os.environ["RFP_TRACE_DIR"] = str(workdir / "intake-traces")
    os.environ["RFP_PROPOSAL_TRACE_DIR"] = str(workdir / "proposal-traces")
    os.environ["RFP_RAW_DIR"] = str(workdir / "raw")
    os.environ["RFP_APPROVAL_MAX_ROUNDS"] = "2"
    os.environ.setdefault("PREFECT_LOGGING_TO_API_ENABLED", "false")
    return workdir


def _build_seeded_ticket(session, fixture: str):
    from datetime import date

    from app.services.rfp_service import create_ticket
    from models import (
        RFP_HANDOFF_READY,
        RFP_STATUS_COMPLETE,
        RfpMetadata,
    )

    from rfp_proposal_support import luna_handoff, modaviva_handoff

    ticket = create_ticket(
        session,
        filename=f"{fixture}.pdf",
        pdf_path=Path("/does/not/exist.pdf"),
        file_sha256="0" * 64,
    )
    intake = (
        luna_handoff(ticket.id)
        if fixture == "luna"
        else modaviva_handoff(ticket.id)
    )
    ticket.status = RFP_STATUS_COMPLETE
    ticket.pipeline_stage = "completado"
    ticket.handoff_status = RFP_HANDOFF_READY
    ticket.handoff_payload = intake
    client = intake.get("client") or {}
    facts = intake.get("rfp_facts") or {}
    deadline = facts.get("deadline")
    session.add(ticket)
    session.add(
        RfpMetadata(
            ticket_id=ticket.id,
            client_name=client.get("name"),
            client_country=client.get("country"),
            currency=intake.get("currency") or client.get("currency"),
            language="es" if client.get("country") == "Spain" else "en",
            services_requested=list(intake.get("services_requested") or []),
            departments_needed=[
                item["department_id"]
                for item in intake.get("departments") or []
            ],
            monthly_volume=facts.get("monthly_volume"),
            deadline=date.fromisoformat(deadline) if deadline else None,
            budget_range=facts.get("budget_range"),
            extraction={
                "contact": client.get("contact") or {},
                "unknown_services": intake.get("unknown_services") or [],
                "missing_fields": [],
                "scope_notes": [],
            },
            readability_metrics=(intake.get("source") or {}).get(
                "readability_metrics"
            )
            or {},
            document_metadata=(intake.get("source") or {}).get(
                "document_metadata"
            )
            or {},
        )
    )
    session.commit()
    session.refresh(ticket)
    return ticket


def _build_live_ticket(session, pdf: Path):
    from app.services.rfp_service import (
        SqlRfpRepository,
        create_ticket,
        store_pdf_bytes,
    )
    from data.pipelines.rfp_intake.ingest import convert_pdf_to_markdown
    from data.pipelines.rfp_intake.llm import LlmClient
    from data.pipelines.rfp_intake.runner import run_rfp_intake

    content = pdf.read_bytes()
    ticket = create_ticket(
        session,
        filename=pdf.name,
        pdf_path=Path("/tmp/placeholder.pdf"),
        file_sha256="0" * 64,
    )
    stored, safe_name, digest = store_pdf_bytes(ticket.id, pdf.name, content)
    ticket.raw_pdf_path = str(stored)
    ticket.original_filename = safe_name
    ticket.file_sha256 = digest
    session.add(ticket)
    session.commit()
    session.refresh(ticket)
    repo = SqlRfpRepository(session)
    result = run_rfp_intake(
        ticket.id,
        repo,
        llm=LlmClient(),
        converter=convert_pdf_to_markdown,
    )
    session.refresh(ticket)
    if ticket.status != "analisis_completo":
        raise SystemExit(
            f"La Parte 1 no terminó en analisis_completo: {result.get('status')}"
        )
    return ticket


def _run_proposal(session, ticket, *, live: bool):
    from app.services.rfp_proposal_service import SqlRfpProposalRepository
    from data.pipelines.rfp_proposal import run_proposal_generation
    from data.pipelines.rfp_intake.llm import LlmClient

    from rfp_proposal_support import ScriptedProposalLlm, prose

    repo = SqlRfpProposalRepository(session)
    if live:
        llm = LlmClient()
    else:
        handoff = ticket.handoff_payload
        generators = {
            department["department_id"]: prose(
                aspects=[
                    aspect["aspect"] for aspect in department["key_aspects"]
                ]
            )
            for department in handoff["departments"]
        }
        llm = ScriptedProposalLlm(generators=generators)
    result = run_proposal_generation(ticket.id, repo, llm=llm, max_iterations=2)
    session.refresh(ticket)
    return result


def _run_approvals(session, ticket, *, pause: bool = False):
    from app.services.rfp_approval_service import (
        get_approvals,
        get_final_document,
        get_trace,
        resume_department,
        start_approvals,
    )
    from schemas import RfpApprovalDecisionRequest

    summary = start_approvals(session, ticket.id)
    print(
        f"[Parte 3] run={summary['run']} thread={summary['thread_id']} "
        f"pending={[item['department_id'] for item in summary['pending']]}"
    )
    if pause:
        trace = get_trace(session, ticket.id)
        print(
            f"[PAUSA] ticket={ticket.id} esperando aprobación. "
            f"Traza={len(trace.events)} eventos."
        )
        return None, trace
    # Aprobar primero el último departamento deja el resto pausado: se
    # demuestra que las ramas son independientes.
    pending = list(summary["pending"])
    order = list(reversed([item["department_id"] for item in pending]))
    for department_id in order:
        current = get_approvals(session, ticket.id)
        packet = next(
            item for item in current.pending if item.department_id == department_id
        )
        summary = resume_department(
            session,
            ticket.id,
            department_id,
            RfpApprovalDecisionRequest(
                action="approve",
                approver=packet.responsible,
                comment="Aprobación simulada E2E.",
                interrupt_id=packet.interrupt_id,
            ),
        )
        print(
            f"[Parte 3] aprobado {department_id} → {summary['status']} "
            f"(pendientes={len(summary['pending'])})"
        )
    document = get_final_document(session, ticket.id)
    trace = get_trace(session, ticket.id)
    print(
        f"[Parte 3] documento final: {document.contract_version} "
        f"{document.currency} {len(document.sections)} secciones, "
        f"{len(document.markdown)} chars"
    )
    print(
        "[Parte 3] aprobado por: "
        + ", ".join(item.get("approver") or "—" for item in document.approved_by)
    )
    print(
        f"[Traza] {len(trace.events)} eventos "
        f"(partes={sorted({event.part for event in trace.events})}), "
        f"arbitrajes={len(trace.arbitrations)}"
    )
    return document, trace


def main() -> int:
    args = _parse_args()
    workdir = _setup_env(args)

    from sqlmodel import Session, SQLModel

    from database import engine
    import models  # noqa: F401  (registra las tablas en SQLModel.metadata)

    if engine is None:
        raise SystemExit("DATABASE_URL no configurada.")
    SQLModel.metadata.create_all(engine)

    try:
        with Session(engine) as session:
            if args.live:
                pdf = (ROOT / args.pdf).resolve()
                if not pdf.exists():
                    raise SystemExit(f"No existe el PDF: {pdf}")
                ticket = _build_live_ticket(session, pdf)
                print(f"[Parte 1] ticket={ticket.id} status={ticket.status}")
            else:
                ticket = _build_seeded_ticket(session, args.fixture)
                print(
                    f"[Parte 1] fixture={args.fixture} ticket={ticket.id} "
                    f"handoff={ticket.handoff_payload.get('contract_version')}"
                )
            proposal = _run_proposal(session, ticket, live=args.live)
            print(
                f"[Parte 2] status={proposal.get('status')} "
                f"secciones={len((proposal.get('proposal_handoff') or {}).get('sections') or [])}"
            )
            document, _trace = _run_approvals(
                session, ticket, pause=args.pause_before_approvals
            )
            if args.pause_before_approvals:
                print(
                    f"[OK] Flujo pausado en esperando_aprobación. "
                    f"Artefactos en {workdir}"
                )
                return 0
            session.refresh(ticket)
            if ticket.status != "terminado":
                raise SystemExit(
                    f"El ticket no terminó en 'terminado': {ticket.status}"
                )
            if not document.markdown.strip():
                raise SystemExit("El documento final está vacío.")
        print(f"[OK] E2E completado. Artefactos en {workdir}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1
    finally:
        if not args.keep:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
