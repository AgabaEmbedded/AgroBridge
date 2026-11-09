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
    clarification_attempts,
    is_correction,
    is_no,
    is_repeat_request,
    is_yes,
    last_assistant_asks_crop,
    last_assistant_message,
    likely_crop_from_short,
    pending_crop_request,
    short_topic_question,
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


def _clarification_state(
    previous: str,
    attempts: int,
    reply: str,
    *,
    crop: str | None = None,
    status: str = "AMBIGUOUS_INTENT",
    substitutions: list[str] | None = None,
) -> dict:
    return {
        "intent": "clarification",
        "crop": crop,
        "direct_answer": reply,
        "question": reply,
        "interpreted_question": None,
        "interpretation_status": status,
        "suspected_substitutions": substitutions or [],
        "topic": None,
        "objective": None,
        "pending_clarification": reply,
        "previous_clarification": previous,
        "clarification_attempts": attempts,
    }


def _short_answer_updates(question: str, history: list[dict[str, str]]) -> dict | None:
    """Handle yes/no, short topics and progressive crop clarification without RAG."""
    previous = last_assistant_message(history)
    if not previous:
        return None
    attempts = clarification_attempts(history)
    explicit_crop = detect_crop(question)
    crop_context = detect_crop(previous) or crop_from_history(history)

    if is_repeat_request(question):
        return None

    if last_assistant_asks_crop(history) and crop_context and is_yes(question):
        reply = (
            f"Good, {crop_context}. What would you like to know about your {crop_context}? "
            "For example, soil, planting, fertilizer, pests or harvest."
        )
        return {
            "intent": "crop_only",
            "crop": crop_context,
            "direct_answer": reply,
            "question": question,
            "interpreted_question": question,
            "interpretation_status": "CLEAR_INTENT",
            "suspected_substitutions": [],
            "topic": "crop confirmation",
            "objective": "continue the crop conversation",
            "clarification_attempts": attempts,
            "previous_clarification": previous,
        }

    if last_assistant_asks_crop(history) and crop_context and is_no(question) and not is_correction(question):
        reply = (
            "No problem. Which crop are you asking about: maize, rice, cassava, "
            "tomato or pepper?"
        )
        return _clarification_state(previous, attempts + 1, reply, crop=None)

    if last_assistant_asks_crop(history) and not explicit_crop:
        likely = likely_crop_from_short(question, history)
        if likely:
            reply = (
                f"Do you mean {likely}?"
                if attempts >= 2 or "i said" in question.lower() or "i mean" in question.lower()
                else f"Are you trying to say {likely}?"
            )
            substitutions = [f"{question.strip()} -> {likely}"]
            return _clarification_state(
                previous,
                attempts + 1,
                reply,
                crop=None,
                status="LIKELY_INTENT",
                substitutions=substitutions,
            )

    if last_assistant_asks_crop(history) and not explicit_crop:
        heard = question.strip() or "that"
        reply = (
            f"I heard {heard}. Are you asking about maize, rice, or cassava?"
            if attempts >= 2
            else "Are you planting maize, rice, or cassava, or another crop?"
        )
        return _clarification_state(previous, attempts + 1, reply, crop=None)

    if crop_context:
        topic_question = short_topic_question(question, crop_context)
        if topic_question:
            return {
                "intent": "crop_question",
                "crop": crop_context,
                "direct_answer": None,
                "question": topic_question,
                "interpreted_question": topic_question,
                "interpretation_status": "LIKELY_INTENT",
                "suspected_substitutions": [],
                "topic": question.strip().lower(),
                "objective": f"ask about {question.strip().lower()} for {crop_context}",
                "clarification_attempts": attempts,
                "previous_clarification": previous,
            }
    return None


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

    short = _short_answer_updates(question, history)
    if short:
        return short

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
