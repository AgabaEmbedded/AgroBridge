"""Question-Answer orchestration graph.

Input -> AgroBridge Agent (KB1) -> Verifier (KB2) -> revision loop (max N) -> output.
A latency deadline is carried in state so the voice path never exceeds the telephony limit.
"""

from __future__ import annotations

import time

from langgraph.graph import END, START, StateGraph

from agents.conversation_agent import conversation_node
from agents.correction_agent import correction_node
from agents.qa_agents import agrobridge_node, finalize_node, revision_node, verifier_node
from agents.runtime import remaining
from agents.state import QAState
from services.config import settings

_compiled = None


def route_after_conversation(state: QAState) -> str:
    return "finalize" if state.get("direct_answer") else "agrobridge"


def route_after_verifier(state: QAState) -> str:
    verification = state.get("verification") or {}
    revisions = int(state.get("revisions") or 0)
    if (
        verification.get("status") == "UNAPPROVED"
        and revisions < settings.max_revisions
        and remaining(state) > 1.0
    ):
        return "revise"
    return "finalize"


def build_qa_graph():
    global _compiled
    if _compiled is None:
        graph = StateGraph(QAState)
        graph.add_node("correction", correction_node)
        graph.add_node("conversation", conversation_node)
        graph.add_node("agrobridge", agrobridge_node)
        graph.add_node("verifier", verifier_node)
        graph.add_node("revision", revision_node)
        graph.add_node("finalize", finalize_node)

        graph.add_edge(START, "correction")
        graph.add_edge("correction", "conversation")
        graph.add_conditional_edges(
            "conversation",
            route_after_conversation,
            {"agrobridge": "agrobridge", "finalize": "finalize"},
        )
        graph.add_edge("agrobridge", "verifier")
        graph.add_conditional_edges(
            "verifier",
            route_after_verifier,
            {"revise": "revision", "finalize": "finalize"},
        )
        graph.add_edge("revision", "verifier")
        graph.add_edge("finalize", END)
        _compiled = graph.compile()
    return _compiled


async def run_question_answer(
    question: str,
    history: list[dict[str, str]] | None = None,
    conversation_id: str | None = None,
    audit_id: str | None = None,
    budget_seconds: float | None = None,
    top_k: int | None = None,
) -> dict:
    budget = settings.qa_budget_seconds if budget_seconds is None else budget_seconds
    initial: QAState = {
        "question": question,
        "top_k": top_k,
        "history": history or [],
        "conversation_id": conversation_id,
        "audit_id": audit_id or "",
        "deadline": time.monotonic() + max(1.0, budget),
        "revisions": 0,
        "timings": {},
        "dropped_citations": [],
    }
    return await build_qa_graph().ainvoke(initial, {"recursion_limit": 12})
