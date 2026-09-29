from app.agents.graph import (
    build_research_graph,
    route_after_additional_approval,
    route_after_citation_validation,
    route_after_critic,
)
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command


async def test_graph_interrupts_and_resumes() -> None:
    graph = build_research_graph(MemorySaver())
    config = {"configurable": {"thread_id": "test-thread"}}
    initial = {
        "run_id": "test-run",
        "query": "Analyze the Indian electric vehicle market",
        "budget_usd": 2.0,
        "evidence": [],
    }

    interrupted = await graph.ainvoke(initial, config=config)
    assert "__interrupt__" in interrupted
    assert len(interrupted["plan"]) == 5

    completed = await graph.ainvoke(
        Command(resume={"decision": "approved", "note": "Proceed"}), config=config
    )
    assert completed["status"] == "completed"
    assert len(completed["evidence"]) == 20
    assert len(completed["report"]["sections"]) == 5
    assert completed["report"]["validation_status"] == "valid"
    assert completed["critic"]["decision"] == "complete"
    assert completed["critic"]["coverage_score"] >= 0.8


async def test_graph_can_reject_plan() -> None:
    graph = build_research_graph(MemorySaver())
    config = {"configurable": {"thread_id": "rejected-thread"}}
    await graph.ainvoke(
        {
            "run_id": "test-run",
            "query": "Analyze the Indian electric vehicle market",
            "budget_usd": 2.0,
            "evidence": [],
        },
        config=config,
    )
    rejected = await graph.ainvoke(
        Command(resume={"decision": "rejected", "note": "Change scope"}), config=config
    )
    assert rejected["status"] == "cancelled"
    assert "report" not in rejected


def test_critic_routes_to_followup_then_approval() -> None:
    assert (
        route_after_critic({"critic": {"decision": "continue"}, "iteration": 1})
        == "prepare_followup"
    )
    assert (
        route_after_critic({"critic": {"decision": "continue"}, "iteration": 2})
        == "request_additional_approval"
    )
    assert route_after_additional_approval({"status": "additional_approved"}) == "prepare_followup"
    assert route_after_additional_approval({"status": "additional_rejected"}) == (
        "synthesize_report"
    )


def test_invalid_citations_route_to_bounded_repair() -> None:
    assert route_after_citation_validation(
        {"citation_validation": {"valid": False}, "repair_attempts": 0}
    ) == "repair_citations"
    assert route_after_citation_validation(
        {"citation_validation": {"valid": False}, "repair_attempts": 2}
    ) == "persist_report"
    assert route_after_citation_validation(
        {"citation_validation": {"valid": True}, "repair_attempts": 0}
    ) == "persist_report"
