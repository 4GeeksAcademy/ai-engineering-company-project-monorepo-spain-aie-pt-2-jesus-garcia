"""Interrupción, reanudación y cierre del grafo de aprobación."""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

from data.pipelines.rfp_approval import (
    resume_approval,
    start_approval_flow,
)
from data.pipelines.rfp_approval.contracts import (
    APPROVAL_APPROVED,
    APPROVAL_PENDING,
    TICKET_AWAITING,
    TICKET_FINISHED,
)

from rfp_approval_support import (
    InMemoryApprovalRepo,
    decision,
    fake_regenerate,
    pending_for,
    proposal_for_luna,
    proposal_for_modaviva,
)


def _repo(proposal: dict, intake: dict) -> InMemoryApprovalRepo:
    return InMemoryApprovalRepo(proposal=proposal, intake=intake)


def test_start_pauses_each_active_department():
    proposal, intake = proposal_for_modaviva()
    repo = _repo(proposal, intake)
    saver = InMemorySaver()

    summary = start_approval_flow(
        repo.ticket["ticket_id"],
        repo,
        checkpointer=saver,
        regenerate=fake_regenerate(),
    )

    assert summary["status"] == TICKET_AWAITING
    assert {packet["department_id"] for packet in summary["pending"]} == {
        "warehouse",
        "reverse",
    }
    for packet in summary["pending"]:
        assert packet["responsible"] in {"Ana Whitfield", "Sofía Ramos"}
        assert packet["section_markdown"]
        assert packet["deadline"] == "2026-08-28"
        assert packet["allowed_actions"] == [
            "approve",
            "reject",
            "request_changes",
        ]
        assert packet["interrupt_id"]
    assert repo.sections["warehouse"]["approval_status"] == APPROVAL_PENDING
    assert repo.sections["reverse"]["approval_status"] == APPROVAL_PENDING


def test_approve_b_while_a_remains_interrupted():
    proposal, intake = proposal_for_luna()
    repo = _repo(proposal, intake)
    saver = InMemorySaver()

    summary = start_approval_flow(
        repo.ticket["ticket_id"],
        repo,
        checkpointer=saver,
        regenerate=fake_regenerate(),
    )
    warehouse_pending = pending_for(repo, "warehouse")
    lastmile_pending = pending_for(repo, "lastmile")

    resume_approval(
        repo.ticket["ticket_id"],
        "lastmile",
        decision(
            action="approve",
            approver="Carlos Vega",
            interrupt_id=lastmile_pending["interrupt_id"],
            comment="Coste y SLA validados.",
        ),
        repo,
        checkpointer=saver,
        regenerate=fake_regenerate(),
    )

    assert repo.sections["lastmile"]["approval_status"] == APPROVAL_APPROVED
    assert repo.sections["warehouse"]["approval_status"] == APPROVAL_PENDING
    assert (
        repo.sections["warehouse"]["approval_interrupt_id"]
        == warehouse_pending["interrupt_id"]
    )
    assert repo.ticket["status"] == TICKET_AWAITING
    assert repo.sections["lastmile"]["approved_at"]

    agents = [event["node"] for event in repo.traces]
    assert "record_approval" in agents
    assert agents.count("prepare_approval") == 2

    resume_approval(
        repo.ticket["ticket_id"],
        "warehouse",
        decision(
            action="approve",
            approver="Ana Whitfield",
            interrupt_id=warehouse_pending["interrupt_id"],
        ),
        repo,
        checkpointer=saver,
        regenerate=fake_regenerate(),
    )
    assert repo.ticket["status"] == TICKET_FINISHED
    assert repo.final_document
    assert repo.final_document["currency"] == "USD"


def test_request_changes_regenerates_only_that_section_and_reinterrupts():
    proposal, intake = proposal_for_modaviva()
    repo = _repo(proposal, intake)
    saver = InMemorySaver()
    start_approval_flow(
        repo.ticket["ticket_id"],
        repo,
        checkpointer=saver,
        regenerate=fake_regenerate(),
    )
    pending = pending_for(repo, "warehouse")

    def mutate(section, feedback, round_no):
        assert "volumen" in feedback.lower()
        payload = dict(section["draft_payload"])
        payload["assumptions"] = list(payload.get("assumptions") or []) + [
            "Volumen pendiente de confirmar con el cliente."
        ]
        section["draft_payload"] = payload
        section["draft_content"] = (
            section["draft_content"] + "\n- Volumen pendiente de confirmar.\n"
        )
        return section

    summary = resume_approval(
        repo.ticket["ticket_id"],
        "warehouse",
        decision(
            action="request_changes",
            approver="Ana Whitfield",
            interrupt_id=pending["interrupt_id"],
            comment="No incluyas el volumen mensual: falta confirmarlo.",
        ),
        repo,
        checkpointer=saver,
        regenerate=fake_regenerate(mutate=mutate),
    )

    assert summary["status"] == TICKET_AWAITING
    assert {packet["department_id"] for packet in summary["pending"]} == {
        "warehouse",
        "reverse",
    }
    warehouse = repo.sections["warehouse"]
    assert warehouse["approval_status"] == APPROVAL_PENDING
    assert warehouse["approval_round"] == 1
    assert "Volumen pendiente de confirmar" in warehouse["draft_content"]
    assert repo.sections["reverse"]["approval_round"] == 0
    assert any(
        event["node"] == "regenerate_section" for event in repo.traces
    )


def test_resume_uses_persisted_checkpoint_without_restart(tmp_path):
    proposal, intake = proposal_for_modaviva()
    repo = _repo(proposal, intake)
    checkpoint = tmp_path / "checkpoints.db"

    with SqliteSaver.from_conn_string(str(checkpoint)) as saver:
        start_approval_flow(
            repo.ticket["ticket_id"],
            repo,
            checkpointer=saver,
            regenerate=fake_regenerate(),
        )
    warehouse = pending_for(repo, "warehouse")
    reverse = pending_for(repo, "reverse")

    with SqliteSaver.from_conn_string(str(checkpoint)) as saver:
        resume_approval(
            repo.ticket["ticket_id"],
            "warehouse",
            decision(
                action="approve",
                approver="Ana Whitfield",
                interrupt_id=warehouse["interrupt_id"],
            ),
            repo,
            checkpointer=saver,
            regenerate=fake_regenerate(),
        )
        resume_approval(
            repo.ticket["ticket_id"],
            "reverse",
            decision(
                action="approve",
                approver="Sofía Ramos",
                interrupt_id=reverse["interrupt_id"],
            ),
            repo,
            checkpointer=saver,
            regenerate=fake_regenerate(),
        )

    assert repo.ticket["status"] == TICKET_FINISHED
    load_events = [
        event for event in repo.traces if event["node"] == "load_proposal"
    ]
    assert len(load_events) == 1
    assert checkpoint.exists()


def test_concurrent_tickets_use_different_threads():
    proposal_a, intake_a = proposal_for_modaviva()
    proposal_b, intake_b = proposal_for_luna()
    repo_a = _repo(proposal_a, intake_a)
    repo_b = _repo(proposal_b, intake_b)
    saver = InMemorySaver()

    start_approval_flow(
        repo_a.ticket["ticket_id"],
        repo_a,
        checkpointer=saver,
        regenerate=fake_regenerate(),
    )
    start_approval_flow(
        repo_b.ticket["ticket_id"],
        repo_b,
        checkpointer=saver,
        regenerate=fake_regenerate(),
    )

    assert repo_a.ticket["approval_thread_id"] != repo_b.ticket["approval_thread_id"]
    assert repo_a.ticket["approval_thread_id"].startswith(
        f"rfp-{repo_a.ticket['ticket_id']}:run-1"
    )
    assert repo_b.ticket["approval_thread_id"].startswith(
        f"rfp-{repo_b.ticket['ticket_id']}:run-1"
    )

    pending_a = pending_for(repo_a, "warehouse")
    resume_approval(
        repo_a.ticket["ticket_id"],
        "warehouse",
        decision(
            action="approve",
            approver="Ana Whitfield",
            interrupt_id=pending_a["interrupt_id"],
        ),
        repo_a,
        checkpointer=saver,
        regenerate=fake_regenerate(),
    )

    assert repo_a.sections["warehouse"]["approval_status"] == APPROVAL_APPROVED
    assert repo_b.sections["warehouse"]["approval_status"] == APPROVAL_PENDING
    assert repo_b.sections["lastmile"]["approval_status"] == APPROVAL_PENDING
