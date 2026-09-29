from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agents.state import ResearchState
from app.core.config import get_settings
from app.services.critic import build_review, persist_review
from app.services.citation_validator import CitationCheck, repair_report_citations, validate_report
from app.services.research_pipeline import run_live_research
from app.services.synthesis import persist_report, synthesize_report

settings = get_settings()


async def plan_research(state: ResearchState) -> dict[str, Any]:
    """Deterministic placeholder replaced by the planner LLM in Milestone 2."""
    query = state["query"]
    return {
        "plan": [
            {"id": "market", "question": f"Determine market size and growth for: {query}"},
            {"id": "companies", "question": "Identify major companies and market positions"},
            {"id": "strategy", "question": "Compare products, economics, and strategies"},
            {"id": "developments", "question": "Find recent material developments"},
            {"id": "risks", "question": "Evaluate risks, catalysts, and open questions"},
        ],
        "active_questions": [
            {"id": "market", "question": f"Determine market size and growth for: {query}"},
            {"id": "companies", "question": "Identify major companies and market positions"},
            {"id": "strategy", "question": "Compare products, economics, and strategies"},
            {"id": "developments", "question": "Find recent material developments"},
            {"id": "risks", "question": "Evaluate risks, catalysts, and open questions"},
        ],
        "iteration": 0,
        "status": "planned",
    }


async def request_approval(state: ResearchState) -> dict[str, Any]:
    decision = interrupt(
        {
            "type": "research_plan_approval",
            "run_id": state["run_id"],
            "query": state["query"],
            "plan": state["plan"],
            "budget_usd": state["budget_usd"],
            "message": "Approve this plan and budget before tool execution.",
        }
    )
    if decision.get("decision") != "approved":
        return {"approval": decision, "status": "cancelled"}
    return {"approval": decision, "status": "approved"}


async def mock_research(state: ResearchState) -> dict[str, Any]:
    """Produces traceable fake evidence without network or LLM costs."""
    evidence = []
    for item in state["active_questions"]:
        for source_index in range(2):
            for passage_index in range(2):
                evidence.append(
                    {
                        "id": (
                            f"mock-{state.get('iteration', 0)}-{item['id']}-"
                            f"{source_index}-{passage_index}"
                        ),
                        "question": item["question"],
                        "content": "Mock evidence generated to verify orchestration only.",
                        "source": f"https://mock-source-{source_index}.example/{item['id']}",
                        "source_quality": 0.9,
                    }
                )
    return {
        "evidence": evidence,
        "iteration": state.get("iteration", 0) + 1,
        "status": "researched",
    }


async def research_sources(state: ResearchState) -> dict[str, Any]:
    if settings.research_mode != "live":
        return await mock_research(state)
    evidence = await run_live_research(state["run_id"], state["query"], state["active_questions"])
    return {
        "evidence": evidence,
        "iteration": state.get("iteration", 0) + 1,
        "status": "researched" if evidence else "research_incomplete",
    }


async def evaluate_research(state: ResearchState) -> dict[str, Any]:
    result = build_review(
        state["plan"],
        state.get("evidence", []),
        state["iteration"],
        settings.research_max_iterations,
    )
    if settings.research_mode == "live":
        await persist_review(state["run_id"], state["iteration"], result)
    return {
        "coverage": result.coverage,
        "contradictions": result.contradictions,
        "gaps": result.gaps,
        "critic": result.critic,
        "status": "reviewed",
    }


async def prepare_followup(state: ResearchState) -> dict[str, Any]:
    active_questions = [
        {"id": gap["question_id"], "question": gap["question"]} for gap in state["gaps"]
    ]
    return {"active_questions": active_questions, "status": "followup_planned"}


async def request_additional_approval(state: ResearchState) -> dict[str, Any]:
    decision = interrupt(
        {
            "type": "additional_research_approval",
            "run_id": state["run_id"],
            "iteration": state["iteration"],
            "coverage_score": state["critic"]["coverage_score"],
            "missing_questions": state["critic"]["missing_questions"],
            "estimated_additional_searches": len(state["critic"]["follow_up_queries"]),
            "message": "Approve one final bounded research iteration.",
        }
    )
    return {
        "additional_approval": decision,
        "status": "additional_approved"
        if decision.get("decision") == "approved"
        else "additional_rejected",
    }


async def synthesize(state: ResearchState) -> dict[str, Any]:
    report = await synthesize_report(
        state["run_id"],
        state["query"],
        state.get("evidence", []),
        state.get("critic", {}),
        state.get("contradictions", []),
    )
    return {"report_draft": report, "repair_attempts": 0, "status": "synthesized"}


async def validate_citations(state: ResearchState) -> dict[str, Any]:
    result = validate_report(state["report_draft"], state.get("evidence", []))
    return {
        "citation_validation": {
            "valid": result.valid,
            "score": result.score,
            "issues": result.issues,
            "citations": result.citations,
        },
        "status": "citations_valid" if result.valid else "citations_invalid",
    }


async def repair_citations(state: ResearchState) -> dict[str, Any]:
    report = repair_report_citations(state["report_draft"], state.get("evidence", []))
    return {
        "report_draft": report,
        "repair_attempts": state.get("repair_attempts", 0) + 1,
        "status": "citations_repaired",
    }


async def finalize_report(state: ResearchState) -> dict[str, Any]:
    validation = state["citation_validation"]
    check = CitationCheck(
        valid=bool(validation["valid"]),
        score=float(validation["score"]),
        issues=list(validation["issues"]),
        citations=list(validation["citations"]),
    )
    if settings.research_mode == "live":
        report = await persist_report(
            state["run_id"], state["report_draft"], check, state.get("repair_attempts", 0)
        )
    else:
        report = {
            **state["report_draft"],
            "validation_status": "valid" if check.valid else "invalid",
            "validation_score": check.score,
            "repair_attempts": state.get("repair_attempts", 0),
        }
    return {"report": report, "status": "completed"}


def route_after_approval(state: ResearchState) -> str:
    return "research_sources" if state.get("status") == "approved" else END


def route_after_critic(state: ResearchState) -> str:
    if state["critic"]["decision"] != "continue":
        return "synthesize_report"
    if state["iteration"] >= settings.research_max_iterations - 1:
        return "request_additional_approval"
    return "prepare_followup"


def route_after_additional_approval(state: ResearchState) -> str:
    if state.get("status") == "additional_approved":
        return "prepare_followup"
    return "synthesize_report"


def route_after_citation_validation(state: ResearchState) -> str:
    if state["citation_validation"]["valid"]:
        return "persist_report"
    if state.get("repair_attempts", 0) >= settings.citation_max_repair_attempts:
        return "persist_report"
    return "repair_citations"


def build_research_graph(checkpointer: Any = None):
    builder = StateGraph(ResearchState)
    builder.add_node("plan_research", plan_research)
    builder.add_node("request_approval", request_approval)
    builder.add_node("research_sources", research_sources)
    builder.add_node("evaluate_research", evaluate_research)
    builder.add_node("prepare_followup", prepare_followup)
    builder.add_node("request_additional_approval", request_additional_approval)
    builder.add_node("synthesize_report", synthesize)
    builder.add_node("validate_citations", validate_citations)
    builder.add_node("repair_citations", repair_citations)
    builder.add_node("persist_report", finalize_report)
    builder.add_edge(START, "plan_research")
    builder.add_edge("plan_research", "request_approval")
    builder.add_conditional_edges("request_approval", route_after_approval)
    builder.add_edge("research_sources", "evaluate_research")
    builder.add_conditional_edges("evaluate_research", route_after_critic)
    builder.add_edge("prepare_followup", "research_sources")
    builder.add_conditional_edges("request_additional_approval", route_after_additional_approval)
    builder.add_edge("synthesize_report", "validate_citations")
    builder.add_conditional_edges("validate_citations", route_after_citation_validation)
    builder.add_edge("repair_citations", "validate_citations")
    builder.add_edge("persist_report", END)
    return builder.compile(checkpointer=checkpointer)
