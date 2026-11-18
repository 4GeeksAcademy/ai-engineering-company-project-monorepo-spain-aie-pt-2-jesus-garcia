"""Arbitraje determinista ante los triggers del BRIEFING §7."""

from __future__ import annotations

from data.pipelines.rfp_approval import start_approval_flow
from data.pipelines.rfp_approval.contracts import (
    APPROVAL_PENDING,
    APPROVAL_REJECTED,
    TICKET_AWAITING,
    TICKET_NEEDS_REVIEW,
)

from rfp_approval_support import (
    InMemoryApprovalRepo,
    fake_regenerate,
    proposal_for_luna,
    proposal_for_modaviva,
)


def test_currency_mismatch_is_rewritten_by_miguel_torres():
    proposal, intake = proposal_for_modaviva()
    warehouse = proposal["sections"][0]
    warehouse["draft_payload"]["currency"] = "USD"
    for row in warehouse["draft_payload"].get("pricing") or []:
        row["currency"] = "USD"
    warehouse["draft_content"] = warehouse["draft_content"].replace("EUR", "USD")
    repo = InMemoryApprovalRepo(proposal=proposal, intake=intake)

    summary = start_approval_flow(
        repo.ticket["ticket_id"],
        repo,
        checkpointer=None,
        regenerate=fake_regenerate(),
    )

    assert summary["status"] == TICKET_AWAITING
    assert {item["department_id"] for item in summary["pending"]} == {
        "warehouse",
        "reverse",
    }
    assert repo.arbitrations
    arbitration = repo.arbitrations[0]
    assert arbitration["conflict"]["trigger_id"] == "currency-mismatch"
    assert arbitration["conflict"]["arbitrator"] == "Miguel Torres"
    assert arbitration["resolution"]["action"] == "rewrite_currency"
    assert repo.sections["warehouse"]["draft_payload"]["currency"] == "EUR"
    assert all(
        row["currency"] == "EUR"
        for row in repo.sections["warehouse"]["draft_payload"]["pricing"]
    )
    assert "USD" not in repo.sections["warehouse"]["draft_content"]


def test_volume_vs_capacity_caps_volume_to_warehouse_capacity():
    proposal, intake = proposal_for_luna()
    warehouse = proposal["sections"][0]
    lastmile = proposal["sections"][1]
    warehouse["draft_payload"]["capacity"] = {
        **(warehouse["draft_payload"].get("capacity") or {}),
        "max_monthly_orders": 3_000,
    }
    lastmile["draft_payload"]["volume"] = {"monthly_orders": 5_000}
    repo = InMemoryApprovalRepo(proposal=proposal, intake=intake)

    summary = start_approval_flow(
        repo.ticket["ticket_id"],
        repo,
        regenerate=fake_regenerate(),
    )

    assert summary["status"] == TICKET_AWAITING
    assert repo.arbitrations
    arbitration = repo.arbitrations[0]
    assert arbitration["conflict"]["trigger_id"] == "volume-vs-capacity"
    assert arbitration["conflict"]["arbitrator"] == "Miguel Torres"
    assert arbitration["resolution"]["action"] == "cap_volume"
    assert repo.sections["warehouse"]["draft_payload"]["volume"]["monthly_orders"] == 3_000
    assert repo.sections["lastmile"]["draft_payload"]["volume"]["monthly_orders"] == 3_000
    assert "3.000" in repo.sections["lastmile"]["draft_content"] or "3000" in repo.sections["lastmile"]["draft_content"]


def test_returns_sla_breach_forces_request_changes_then_repairs():
    proposal, intake = proposal_for_modaviva()
    reverse = proposal["sections"][1]
    reverse["draft_payload"]["turnaround"]["minimum_hours"] = 24
    reverse["draft_payload"]["turnaround"]["committed_hours"] = 24
    reverse["draft_content"] = reverse["draft_content"].replace(
        "48 horas", "24 horas"
    )
    repo = InMemoryApprovalRepo(proposal=proposal, intake=intake)

    def repair(section, feedback, round_no):
        payload = dict(section["draft_payload"])
        turnaround = dict(payload.get("turnaround") or {})
        turnaround["minimum_hours"] = 48
        turnaround["committed_hours"] = None
        payload["turnaround"] = turnaround
        section["draft_payload"] = payload
        section["draft_content"] = (
            "# Tiempo de procesamiento\n\n"
            "El tiempo mínimo de procesamiento es de 48 horas.\n"
        )
        return section

    summary = start_approval_flow(
        repo.ticket["ticket_id"],
        repo,
        regenerate=fake_regenerate(mutate=repair),
    )

    assert summary["status"] == TICKET_AWAITING
    arbitration = next(
        item
        for item in repo.arbitrations
        if item["conflict"]["trigger_id"] == "returns-sla-breach"
    )
    assert arbitration["conflict"]["arbitrator"] == "Sofía Ramos"
    assert arbitration["resolution"]["action"] == "request_changes"
    assert arbitration["resolution"]["requires_regeneration"] == ["reverse"]
    assert repo.sections["reverse"]["approval_round"] == 1
    assert repo.sections["reverse"]["draft_payload"]["turnaround"][
        "minimum_hours"
    ] == 48
    assert repo.sections["reverse"]["approval_status"] == APPROVAL_PENDING


def test_returns_sla_breach_rejects_after_limit():
    proposal, intake = proposal_for_modaviva()
    reverse = proposal["sections"][1]
    reverse["draft_payload"]["turnaround"]["minimum_hours"] = 24
    reverse["draft_payload"]["turnaround"]["committed_hours"] = 24
    reverse["draft_content"] = reverse["draft_content"].replace(
        "48 horas", "24 horas"
    )
    repo = InMemoryApprovalRepo(proposal=proposal, intake=intake)

    summary = start_approval_flow(
        repo.ticket["ticket_id"],
        repo,
        max_rounds=1,
        regenerate=fake_regenerate(),
    )

    assert summary["status"] == TICKET_NEEDS_REVIEW
    assert repo.sections["reverse"]["approval_status"] == APPROVAL_REJECTED
    assert repo.sections["reverse"]["approval_round"] == 1
    assert repo.sections["reverse"]["approver"] == "Sofía Ramos"
    assert repo.ticket["status"] == TICKET_NEEDS_REVIEW
    assert repo.final_document is None


def test_no_conflict_does_not_invoke_arbitrator():
    proposal, intake = proposal_for_modaviva()
    repo = InMemoryApprovalRepo(proposal=proposal, intake=intake)

    start_approval_flow(
        repo.ticket["ticket_id"],
        repo,
        regenerate=fake_regenerate(),
    )

    assert repo.arbitrations == []
