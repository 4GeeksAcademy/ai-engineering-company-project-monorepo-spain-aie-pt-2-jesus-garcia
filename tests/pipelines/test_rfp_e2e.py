"""E2E de las Partes 1→3 con estado sembrado y aprobaciones simuladas."""

from __future__ import annotations

import json

from langgraph.checkpoint.memory import InMemorySaver

from data.pipelines.rfp_approval import resume_approval, start_approval_flow
from data.pipelines.rfp_approval.contracts import (
    APPROVAL_APPROVED,
    TICKET_AWAITING,
    TICKET_FINISHED,
)

from rfp_approval_support import (
    InMemoryApprovalRepo,
    decision,
    fake_regenerate,
    pending_for,
)
from rfp_proposal_support import (
    InMemoryProposalRepo,
    ScriptedProposalLlm,
    modaviva_handoff,
    prose,
    run_proposal,
)


def test_rfp_e2e_from_intake_handoff_to_final_document(tmp_path, monkeypatch):
    monkeypatch.setenv("RFP_PROPOSAL_TRACE_DIR", str(tmp_path / "proposal-traces"))
    ticket_id = "e2e-modaviva"
    handoff = modaviva_handoff(ticket_id)

    # Parte 1 (estado sembrado): el handoff ya valida el contrato y los deptos.
    assert handoff["contract_version"].startswith("rfp-intake-v1")
    assert handoff["client"]["country"] == "Spain"
    assert handoff["currency"] == "EUR"
    assert {item["department_id"] for item in handoff["departments"]} == {
        "warehouse",
        "reverse",
    }
    assert all(
        item["department_id"] != "lastmile" for item in handoff["departments"]
    )

    # Parte 2: generación y evaluación con LLM guionizado.
    generators = {
        department["department_id"]: prose(
            aspects=[aspect["aspect"] for aspect in department["key_aspects"]]
        )
        for department in handoff["departments"]
    }
    part2_repo = InMemoryProposalRepo(handoff, ticket_id=ticket_id)
    part2_repo, part2_result = run_proposal(
        handoff,
        llm=ScriptedProposalLlm(generators=generators),
        repo=part2_repo,
        max_iterations=2,
    )
    proposal = part2_repo.proposal_handoff
    assert part2_result["status"] == TICKET_AWAITING
    assert proposal["contract_version"] == "rfp-proposal-v1"
    assert proposal["currency"] == "EUR"
    assert [section["department_id"] for section in proposal["sections"]] == [
        "warehouse",
        "reverse",
    ]
    assert all(
        section["evaluation_results"]["overall_pass"]
        for section in proposal["sections"]
    )

    # La Parte 3 consume exactamente el payload de la Parte 2.
    part3_repo = InMemoryApprovalRepo(
        proposal=proposal, intake=handoff, ticket_id=ticket_id
    )
    saver = InMemorySaver()
    started = start_approval_flow(
        ticket_id,
        part3_repo,
        checkpointer=saver,
        regenerate=fake_regenerate(),
    )
    assert started["status"] == TICKET_AWAITING
    assert {item["department_id"] for item in started["pending"]} == {
        "warehouse",
        "reverse",
    }

    # Aprobación en orden inverso: B no bloquea a A.
    reverse_pending = pending_for(part3_repo, "reverse")
    after_reverse = resume_approval(
        ticket_id,
        "reverse",
        decision(
            action="approve",
            approver="Sofía Ramos",
            interrupt_id=reverse_pending["interrupt_id"],
            comment="Proceso y 48 h validados.",
        ),
        part3_repo,
        checkpointer=saver,
        regenerate=fake_regenerate(),
    )
    assert after_reverse["status"] == TICKET_AWAITING
    assert part3_repo.sections["reverse"]["approval_status"] == APPROVAL_APPROVED
    assert part3_repo.sections["warehouse"]["approval_status"] == "pending_approval"

    warehouse_pending = pending_for(part3_repo, "warehouse")
    finalized = resume_approval(
        ticket_id,
        "warehouse",
        decision(
            action="approve",
            approver="Ana Whitfield",
            interrupt_id=warehouse_pending["interrupt_id"],
            comment="Capacidad y onboarding validados.",
        ),
        part3_repo,
        checkpointer=saver,
        regenerate=fake_regenerate(),
    )

    assert finalized["status"] == TICKET_FINISHED
    assert part3_repo.ticket["status"] == TICKET_FINISHED
    document = part3_repo.final_document
    assert document is not None
    assert document["contract_version"] == "rfp-final-v1"
    assert document["currency"] == "EUR"
    assert [section["department_id"] for section in document["sections"]] == [
        "warehouse",
        "reverse",
    ]
    assert {item["approver"] for item in document["approved_by"]} == {
        "Ana Whitfield",
        "Sofía Ramos",
    }
    for section in proposal["sections"]:
        title = section["draft_content"].splitlines()[0].lstrip("# ").strip()
        assert title in document["markdown"]
        assert "### " in document["markdown"]
    assert "Last Mile" not in document["markdown"]
    assert "48" in document["markdown"]
    assert "90" in document["markdown"]
    assert "2026-08-28" in document["markdown"]

    # Secuencia de estados sin saltos: Parte 2 → Parte 3.
    history = list(part2_repo.status_history) + [part3_repo.ticket["status"]]
    assert history.index("generando_borrador") < history.index("en_evaluación")
    assert history.index("en_evaluación") < history.index(TICKET_AWAITING)
    assert history[-1] == TICKET_FINISHED
    assert part3_repo.traces
    assert any(event["node"] == "final_gate" for event in part3_repo.traces)
    assert any(event["node"] == "generate_document" for event in part3_repo.traces)

    trace_file = tmp_path / "proposal-traces" / f"{ticket_id}.json"
    assert trace_file.exists()
    part2_trace = json.loads(trace_file.read_text(encoding="utf-8"))
    assert part2_trace["status"] == TICKET_AWAITING
