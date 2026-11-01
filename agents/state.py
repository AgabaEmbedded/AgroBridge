"""Typed state for the two independent orchestration graphs."""

from __future__ import annotations

from typing import Any, TypedDict


class QAState(TypedDict, total=False):
    question: str
    top_k: int | None
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
