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
        }
    if previous and pending and turn.intent == "clarification" and not turn.crop:
        return {
            "intent": "clarification",
            "crop": None,
            "direct_answer": previous,
            "question": question,
        }
    if turn.intent == "crop_only" and turn.crop and pending:
        return {
            "intent": "crop_question",
            "crop": turn.crop,
            "direct_answer": None,
            "question": f"{pending}\n\nCaller clarified: {turn.cleaned_question or question}",
            "corrected_question": f"{pending}\n\nCaller clarified: {turn.cleaned_question or question}",
        }
    return {
        "intent": turn.intent,
        "crop": turn.crop,
        "direct_answer": turn.direct_answer,
        "question": turn.cleaned_question or question,
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
    crop = detect_crop(decision.crop or "") or detect_crop(question) or crop_from_history(history)
    direct = (decision.direct_reply or "").strip() or None
    fallback = classify_turn(question, history)
    pending = pending_crop_request(history)
    previous = last_assistant_message(history)

    # Explicit "repeat that" is a replay of the last answer, not a new clarification.
    if previous and is_repeat_request(question):
        return {
            "intent": "clarification",
            "crop": crop,
            "direct_answer": previous,
            "question": question,
        }

    # A filler while a crop question is pending should re-ask that question.
    if previous and pending and fallback.intent == "clarification" and not crop:
        return {
            "intent": "clarification",
            "crop": None,
            "direct_answer": previous,
            "question": question,
        }

    # The answer agent may have asked "which crop?" on the previous turn. A short crop answer
    # continues that request; it is not a fresh crop-only turn.
    if pending and crop and fallback.intent == "crop_only":
        return {
            "intent": "crop_question",
            "crop": crop,
            "direct_answer": None,
            "question": f"{pending}\n\nCaller clarified: {question}",
            "corrected_question": f"{pending}\n\nCaller clarified: {question}",
        }

    if intent in {"greeting", "social", "livestock", "out_of_scope", "clarification"}:
        direct = direct or fallback.direct_answer or CLARIFY_REPLY
        return {
            "intent": intent,
            "crop": crop,
            "direct_answer": direct,
            "question": question,
        }

    if intent == "crop_only":
        if not crop:
            return {
                "intent": "greeting",
                "crop": None,
                "direct_answer": NO_CROP_REPLY,
                "question": question,
            }
        return {
            "intent": "crop_only",
            "crop": crop,
            "direct_answer": direct or CROP_ONLY_TEMPLATE.format(crop=crop),
            "question": question,
        }

    return {
        "intent": intent,
        "crop": crop,
        "direct_answer": None,
        "question": question,
    }
