"""Gap-analysis orchestration graph.

Input -> GA1 (KB2) -> GA2 (KB1) -> structured communication rounds -> synthesis -> output.
Independent from the question-answer graph; shares only services.
"""

from __future__ import annotations

import time

from langgraph.graph import END, START, StateGraph

from agents.gap_agents import (
    communication_node,
    needs_analyst_node,
    policy_analyst_node,
    synthesis_node,
)
from agents.state import GapState
from services.config import settings

_compiled = None


def route_after_needs(state: GapState) -> str:
    max_rounds = int(state.get("max_rounds") or settings.gap_max_rounds)
    return "communicate" if max_rounds > 0 else "synthesize"


def route_after_communication(state: GapState) -> str:
    rounds = int(state.get("rounds") or 0)
    max_rounds = int(state.get("max_rounds") or settings.gap_max_rounds)
    return "communicate" if rounds < max_rounds else "synthesize"


def build_gap_graph():
    global _compiled
    if _compiled is None:
        graph = StateGraph(GapState)
        graph.add_node("ga1", policy_analyst_node)
        graph.add_node("ga2", needs_analyst_node)
        graph.add_node("communicate", communication_node)
        graph.add_node("synthesis", synthesis_node)

        graph.add_edge(START, "ga1")
        graph.add_edge("ga1", "ga2")
        graph.add_conditional_edges(
            "ga2",
            route_after_needs,
            {"communicate": "communicate", "synthesize": "synthesis"},
        )
        graph.add_conditional_edges(
            "communicate",
            route_after_communication,
            {"communicate": "communicate", "synthesize": "synthesis"},
        )
        graph.add_edge("synthesis", END)
        _compiled = graph.compile()
    return _compiled


async def run_gap_analysis(
    query: str,
    max_rounds: int | None = None,
    audit_id: str | None = None,
    budget_seconds: float | None = None,
) -> dict:
    budget = settings.gap_timeout_seconds if budget_seconds is None else budget_seconds
    rounds = settings.gap_max_rounds if max_rounds is None else max(0, min(max_rounds, 4))
    initial: GapState = {
        "query": query,
        "audit_id": audit_id or "",
        "deadline": time.monotonic() + max(5.0, budget),
        "max_rounds": rounds,
        "rounds": 0,
        "messages": [],
        "timings": {},
        "dropped_citations": [],
    }
    return await build_gap_graph().ainvoke(
        initial, {"recursion_limit": 8 + 4 * rounds}
    )
