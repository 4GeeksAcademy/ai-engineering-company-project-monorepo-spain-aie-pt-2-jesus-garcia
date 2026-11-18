"""Validación de la respuesta humana antes de reanudar el grafo."""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from data.pipelines.rfp_approval import resume_approval, start_approval_flow
from data.pipelines.rfp_approval.contracts import (
    APPROVAL_PENDING,
    ApprovalDecisionError,
    ApprovalStateError,
)

from rfp_approval_support import (
    InMemoryApprovalRepo,
    decision,
    fake_regenerate,
    pending_for,
    proposal_for_modaviva,
)


def _started():
    proposal, intake = proposal_for_modaviva()
    repo = InMemoryApprovalRepo(proposal=proposal, intake=intake)
    saver = InMemorySaver()
    start_approval_flow(
        repo.ticket["ticket_id"],
        repo,
        checkpointer=saver,
        regenerate=fake_regenerate(),
    )
    return repo, saver


def test_rejects_wrong_approver():
    repo, saver = _started()
    pending = pending_for(repo, "warehouse")

    with pytest.raises(ApprovalDecisionError) as exc:
        resume_approval(
            repo.ticket["ticket_id"],
            "warehouse",
            decision(
                action="approve",
                approver="Carlos Vega",
                interrupt_id=pending["interrupt_id"],
            ),
            repo,
            checkpointer=saver,
            regenerate=fake_regenerate(),
        )

    assert "Ana Whitfield" in str(exc.value)
    assert repo.sections["warehouse"]["approval_status"] == APPROVAL_PENDING
    assert (
        repo.sections["warehouse"]["approval_interrupt_id"]
        == pending["interrupt_id"]
    )


def test_rejection_and_request_changes_require_comment():
    repo, saver = _started()
    pending = pending_for(repo, "warehouse")

    for action in ("reject", "request_changes"):
        with pytest.raises(ApprovalDecisionError) as exc:
            resume_approval(
                repo.ticket["ticket_id"],
                "warehouse",
                decision(
                    action=action,
                    approver="Ana Whitfield",
                    interrupt_id=pending["interrupt_id"],
                ),
                repo,
                checkpointer=saver,
                regenerate=fake_regenerate(),
            )
        assert "comentario" in str(exc.value).lower()


def test_rejects_stale_interrupt_id():
    repo, saver = _started()
    pending = pending_for(repo, "warehouse")

    with pytest.raises(ApprovalStateError) as exc:
        resume_approval(
            repo.ticket["ticket_id"],
            "warehouse",
            decision(
                action="approve",
                approver="Ana Whitfield",
                interrupt_id="interrupt-obsoleto",
            ),
            repo,
            checkpointer=saver,
            regenerate=fake_regenerate(),
        )

    assert "interrupt" in str(exc.value).lower()


def test_rejects_duplicate_decision():
    repo, saver = _started()
    pending = pending_for(repo, "warehouse")
    resume_approval(
        repo.ticket["ticket_id"],
        "warehouse",
        decision(
            action="approve",
            approver="Ana Whitfield",
            interrupt_id=pending["interrupt_id"],
        ),
        repo,
        checkpointer=saver,
        regenerate=fake_regenerate(),
    )

    with pytest.raises(ApprovalStateError) as exc:
        resume_approval(
            repo.ticket["ticket_id"],
            "warehouse",
            decision(
                action="approve",
                approver="Ana Whitfield",
                interrupt_id=pending["interrupt_id"],
            ),
            repo,
            checkpointer=saver,
            regenerate=fake_regenerate(),
        )

    assert "pendiente" in str(exc.value).lower()


def test_provisional_section_requires_explicit_acknowledgement():
    proposal, intake = proposal_for_modaviva()
    for section in proposal["sections"]:
        section["provisional"] = True
        section["review_reason"] = "Agotó iteraciones en la Parte 2."
    repo = InMemoryApprovalRepo(proposal=proposal, intake=intake)
    saver = InMemorySaver()
    start_approval_flow(
        repo.ticket["ticket_id"],
        repo,
        checkpointer=saver,
        regenerate=fake_regenerate(),
    )
    pending = pending_for(repo, "warehouse")
    assert pending["provisional"] is True

    with pytest.raises(ApprovalDecisionError) as exc:
        resume_approval(
            repo.ticket["ticket_id"],
            "warehouse",
            decision(
                action="approve",
                approver="Ana Whitfield",
                interrupt_id=pending["interrupt_id"],
            ),
            repo,
            checkpointer=saver,
            regenerate=fake_regenerate(),
        )
    assert "provisional" in str(exc.value).lower()

    summary = resume_approval(
        repo.ticket["ticket_id"],
        "warehouse",
        decision(
            action="approve",
            approver="Ana Whitfield",
            interrupt_id=pending["interrupt_id"],
            comment="Acepto el borrador provisional.",
            acknowledge_provisional=True,
        ),
        repo,
        checkpointer=saver,
        regenerate=fake_regenerate(),
    )
    assert summary["status"] == "esperando_aprobación"


def test_request_changes_clears_provisional_when_regeneration_passes():
    proposal, intake = proposal_for_modaviva()
    proposal["sections"][0]["provisional"] = True
    proposal["sections"][0]["review_reason"] = "Agotó iteraciones en la Parte 2."
    repo = InMemoryApprovalRepo(proposal=proposal, intake=intake)
    saver = InMemorySaver()
    start_approval_flow(
        repo.ticket["ticket_id"],
        repo,
        checkpointer=saver,
        regenerate=fake_regenerate(),
    )
    pending = pending_for(repo, "warehouse")
    assert pending["provisional"] is True

    resume_approval(
        repo.ticket["ticket_id"],
        "warehouse",
        decision(
            action="request_changes",
            approver="Ana Whitfield",
            interrupt_id=pending["interrupt_id"],
            comment="Revisa el resumen ejecutivo.",
        ),
        repo,
        checkpointer=saver,
        regenerate=fake_regenerate(),
    )

    refreshed = pending_for(repo, "warehouse")
    assert refreshed["provisional"] is False
    assert refreshed["approval_round"] == 1
