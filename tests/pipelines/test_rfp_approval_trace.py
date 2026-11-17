"""Trazabilidad: agente, input, output y timestamp por ejecución de nodo."""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver

from data.pipelines.rfp_approval import resume_approval, start_approval_flow

from rfp_approval_support import (
    InMemoryApprovalRepo,
    decision,
    fake_regenerate,
    pending_for,
    proposal_for_luna,
)


def test_every_node_records_agent_input_output_and_timestamp():
    proposal, intake = proposal_for_luna()
    repo = InMemoryApprovalRepo(proposal=proposal, intake=intake)
    saver = InMemorySaver()
    start_approval_flow(
        repo.ticket["ticket_id"],
        repo,
        checkpointer=saver,
        regenerate=fake_regenerate(),
    )
    lastmile = pending_for(repo, "lastmile")
    resume_approval(
        repo.ticket["ticket_id"],
        "lastmile",
        decision(
            action="approve",
            approver="Carlos Vega",
            interrupt_id=lastmile["interrupt_id"],
            comment="SLA y transportistas validados.",
        ),
        repo,
        checkpointer=saver,
        regenerate=fake_regenerate(),
    )

    assert repo.traces
    for event in repo.traces:
        assert event["event_id"]
        assert event["part"] == 3
        assert event["node"]
        assert event["agent"]
        assert event["timestamp"]
        assert isinstance(event["input"], dict)
        assert isinstance(event["output"], dict)
    assert len({event["event_id"] for event in repo.traces}) == len(repo.traces)

    nodes = [event["node"] for event in repo.traces]
    assert nodes[0] == "load_proposal"
    assert nodes.index("detect_conflicts") < nodes.index("prepare_approval")
    assert nodes.index("await_approval") < nodes.index("record_approval")

    human_agents = {
        event["agent"] for event in repo.traces if event["node"] == "record_approval"
    }
    assert human_agents == {"human:Carlos Vega"}


def test_approving_one_branch_leaves_the_other_without_await_event():
    proposal, intake = proposal_for_luna()
    repo = InMemoryApprovalRepo(proposal=proposal, intake=intake)
    saver = InMemorySaver()
    start_approval_flow(
        repo.ticket["ticket_id"],
        repo,
        checkpointer=saver,
        regenerate=fake_regenerate(),
    )
    lastmile = pending_for(repo, "lastmile")
    resume_approval(
        repo.ticket["ticket_id"],
        "lastmile",
        decision(
            action="approve",
            approver="Carlos Vega",
            interrupt_id=lastmile["interrupt_id"],
        ),
        repo,
        checkpointer=saver,
        regenerate=fake_regenerate(),
    )

    warehouse_events = [
        event for event in repo.traces if event.get("department_id") == "warehouse"
    ]
    lastmile_events = [
        event for event in repo.traces if event.get("department_id") == "lastmile"
    ]
    assert warehouse_events
    assert all(event["node"] != "await_approval" for event in warehouse_events)
    assert any(event["node"] == "await_approval" for event in lastmile_events)
    assert any(event["node"] == "record_approval" for event in lastmile_events)
