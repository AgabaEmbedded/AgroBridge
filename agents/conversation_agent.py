"""Conversation-router node for the Question-Answer graph."""

from __future__ import annotations

from services.conversation import classify_turn


def conversation_node(state: dict) -> dict:
    turn = classify_turn(state.get("question", ""), state.get("history") or [])
    updates = {
        "intent": turn.intent,
        "crop": turn.crop,
        "direct_answer": turn.direct_answer,
    }
    if turn.cleaned_question and turn.cleaned_question != state.get("question", ""):
        updates["question"] = turn.cleaned_question
    return updates
