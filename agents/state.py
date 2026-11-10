"""Typed state for the two independent orchestration graphs."""

from __future__ import annotations

from typing import Any, TypedDict


class QAState(TypedDict, total=False):
    question: str
    raw_question: str
    corrected_question: str
    correction: dict[str, Any]
    correction_status: str
    top_k: int | None
    intent: str
    crop: str | None
    direct_answer: str | None
    interpreted_question: str | None
    interpretation_status: str
    suspected_substitutions: list[str]
    topic: str | None
    objective: str | None
    retrieval_query: str
    pending_clarification: str | None
    previous_clarification: str | None
    clarification_attempts: int
    history: list[dict[str, str]]
    conversation_id: str | None
    audit_id: str
    deadline: float

    draft: dict[str, Any]
    verification: dict[str, Any]
    revisions: int
    final: dict[str, Any]
    hits: list[dict[str, Any]]
    policy_hits: list[dict[str, Any]]
    dropped_citations: list[str]
    timings: dict[str, float]
    error: str | None


class GapState(TypedDict, total=False):
    query: str
    audit_id: str
    deadline: float
    max_rounds: int

    policy: dict[str, Any]
    needs: dict[str, Any]
    messages: list[dict[str, Any]]
    rounds: int
    synthesis: dict[str, Any]
    policy_hits: list[dict[str, Any]]
    needs_hits: list[dict[str, Any]]
    dropped_citations: list[str]
    timings: dict[str, float]
    error: str | None
