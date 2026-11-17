"""Límites de revisión y rondas de arbitraje."""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from data.pipelines.rfp_approval import resume_approval, start_approval_flow
from data.pipelines.rfp_approval.contracts import (
    APPROVAL_APPROVED,
    APPROVAL_PENDING,
    ApprovalDecisionError,
)

from rfp_approval_support import (
    InMemoryApprovalRepo,
    decision,
    fake_regenerate,
    pending_for,
    proposal_for_modaviva,
)


def test_human_request_changes_hits_limit_and_only_allows_approve_or_reject():
    proposal, intake = proposal_for_modaviva()
    repo = InMemoryApprovalRepo(proposal=proposal, intake=intake)
    saver = InMemorySaver()
    start_approval_flow(
        repo.ticket["ticket_id"],
        repo,
        max_rounds=1,
        checkpointer=saver,
        regenerate=fake_regenerate(),
    )
    first = pending_for(repo, "warehouse")
    assert first["allowed_actions"] == [
        "approve",
        "reject",
        "request_changes",
    ]

    summary = resume_approval(
        repo.ticket["ticket_id"],
        "warehouse",
        decision(
            action="request_changes",
            approver="Ana Whitfield",
            interrupt_id=first["interrupt_id"],
            comment="Ajusta el resumen ejecutivo.",
        ),
        repo,
        max_rounds=1,
        checkpointer=saver,
        regenerate=fake_regenerate(),
    )
    assert summary["status"] == "esperando_aprobación"
    second = pending_for(repo, "warehouse")
    assert second["approval_round"] == 1
    assert second["allowed_actions"] == ["approve", "reject"]
    assert second["interrupt_id"] != first["interrupt_id"]

    with pytest.raises(ApprovalDecisionError) as exc:
        resume_approval(
            repo.ticket["ticket_id"],
            "warehouse",
            decision(
                action="request_changes",
                approver="Ana Whitfield",
                interrupt_id=second["interrupt_id"],
                comment="Otra vuelta más.",
            ),
            repo,
            max_rounds=1,
            checkpointer=saver,
            regenerate=fake_regenerate(),
        )
    assert "límite" in str(exc.value).lower()
    assert repo.sections["warehouse"]["approval_status"] == APPROVAL_PENDING
    assert repo.sections["warehouse"]["approval_round"] == 1

    summary = resume_approval(
        repo.ticket["ticket_id"],
        "warehouse",
        decision(
            action="approve",
            approver="Ana Whitfield",
            comment="Aprobado tras la revisión.",
            interrupt_id=second["interrupt_id"],
        ),
        repo,
        max_rounds=1,
        checkpointer=saver,
        regenerate=fake_regenerate(),
    )
    assert repo.sections["warehouse"]["approval_status"] == APPROVAL_APPROVED
    assert "warehouse" not in {
        item["department_id"] for item in summary["pending"]
    }
