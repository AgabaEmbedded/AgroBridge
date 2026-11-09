"""Conversation-router node for the Question-Answer graph."""

from __future__ import annotations

from agents.runtime import remaining
from services.config import settings
from services.conversation import (
    CLARIFY_REPLY,
    CROP_ONLY_TEMPLATE,
    NO_CROP_REPLY,
    classify_turn,
    crop_from_history,
    detect_crop,
    is_repeat_request,
    last_assistant_message,
    pending_crop_request,
)
from services.conversation_ai import classify_with_ai
from services.llm_service import LLMServiceError


def _interpretation_fields(decision=None) -> dict:
    """Metadata carried into the answer agent and audit record."""
    if decision is None:
        return {
            "interpretation_status": "CLEAR_INTENT",
            "suspected_substitutions": [],
            "topic": None,
            "objective": None,
        }
    return {
        "interpretation_status": decision.interpretation_status,
        "suspected_substitutions": list(decision.suspected_substitutions or []),
        "topic": decision.topic,
        "objective": decision.objective,
    }


def _fallback_updates(question: str, history: list[dict[str, str]]) -> dict:
    turn = classify_turn(question, history)
    pending = pending_crop_request(history)
    previous = last_assistant_message(history)
    if previous and is_repeat_request(question):
        return {
            "intent": "clarification",
            "crop": turn.crop,
            "direct_answer": previous,
            "question": question,
            "interpreted_question": None,
            **_interpretation_fields(),
        }
    if previous and pending and turn.intent == "clarification" and not turn.crop:
        return {
            "intent": "clarification",
            "crop": None,
            "direct_answer": previous,
            "question": question,
            "interpreted_question": None,
            **_interpretation_fields(),
        }
    if turn.intent == "crop_only" and turn.crop and pending:
        clarified = f"{pending}\n\nCaller clarified: {turn.cleaned_question or question}"
        return {
            "intent": "crop_question",
            "crop": turn.crop,
            "direct_answer": None,
            "question": clarified,
            "corrected_question": clarified,
            "interpreted_question": clarified,
            **_interpretation_fields(),
        }
    return {
        "intent": turn.intent,
        "crop": turn.crop,
        "direct_answer": turn.direct_answer,
        "question": turn.cleaned_question or question,
        "interpreted_question": turn.cleaned_question or question,
        **_interpretation_fields(),
    }


async def conversation_node(state: dict) -> dict:
    question = state.get("question", "")
    history = state.get("history") or []

    if not settings.conversation_ai_enabled or remaining(state) < 1.2:
        return _fallback_updates(question, history)

    timeout = min(settings.conversation_ai_timeout, max(0.8, remaining(state) * 0.45))
    try:
        decision = await classify_with_ai(question, history, timeout)
    except LLMServiceError:
        return _fallback_updates(question, history)
    except Exception:
        return _fallback_updates(question, history)

    intent = decision.intent
    fallback = classify_turn(question, history)
    pending = pending_crop_request(history)
    previous = last_assistant_message(history)
    interpreted = (decision.interpreted_question or "").strip() or question
    crop = (
        detect_crop(decision.crop or "")
        or detect_crop(interpreted)
        or detect_crop(question)
        or crop_from_history(history)
    )
    direct = (decision.direct_reply or "").strip() or None
    clarification = (decision.clarification_question or "").strip() or None
    meta = _interpretation_fields(decision)

    # Explicit "repeat that" is a replay of the last answer, not a new clarification.
    if previous and is_repeat_request(question):
        return {
            "intent": "clarification",
            "crop": crop,
            "direct_answer": previous,
            "question": question,
            "interpreted_question": None,
            **meta,
        }

    # A filler while a crop question is pending should re-ask that question, but a
    # targeted clarification from the router takes precedence.
    if previous and pending and fallback.intent == "clarification" and not crop and not clarification:
        return {
            "intent": "clarification",
            "crop": None,
            "direct_answer": previous,
            "question": question,
            "interpreted_question": None,
            **meta,
        }

    # The answer agent may have asked "which crop?" on the previous turn. A short crop
    # answer continues that request; it is not a fresh crop-only turn.
    if pending and crop and (intent == "crop_only" or fallback.intent == "crop_only"):
        clarified = f"{pending}\n\nCaller clarified: {interpreted}"
        return {
            "intent": "crop_question",
            "crop": crop,
            "direct_answer": None,
            "question": clarified,
            "corrected_question": clarified,
            "interpreted_question": clarified,
            **meta,
        }

    # Do not run retrieval on a genuinely ambiguous or incomplete transcript.
    if decision.interpretation_status in {"AMBIGUOUS_INTENT", "INSUFFICIENT_INPUT"}:
        reply = clarification or direct or fallback.direct_answer or CLARIFY_REPLY
        return {
            "intent": intent,
            "crop": crop,
            "direct_answer": reply,
            "question": question,
            "interpreted_question": interpreted if interpreted != question else None,
            "pending_clarification": reply,
            **meta,
        }

    if intent in {"greeting", "social", "livestock", "out_of_scope", "clarification"}:
        direct = clarification or direct or fallback.direct_answer or CLARIFY_REPLY
        return {
            "intent": intent,
            "crop": crop,
            "direct_answer": direct,
            "question": question,
            "interpreted_question": None,
            **meta,
        }

    if intent == "crop_only":
        if not crop:
            return {
                "intent": "greeting",
                "crop": None,
                "direct_answer": NO_CROP_REPLY,
                "question": question,
                "interpreted_question": None,
                **meta,
            }
        return {
            "intent": "crop_only",
            "crop": crop,
            "direct_answer": direct or CROP_ONLY_TEMPLATE.format(crop=crop),
            "question": interpreted,
            "interpreted_question": interpreted,
            **meta,
        }

    return {
        "intent": intent,
        "crop": crop,
        "direct_answer": None,
        "question": interpreted,
        "interpreted_question": interpreted,
        **meta,
    }
