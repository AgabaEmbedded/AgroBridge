"""Optional transcript-correction node that runs before intent routing."""

from __future__ import annotations

from services.config import settings
from services.conversation import classify_turn
from services.llm_service import LLMServiceError
from services.transcript_service import correct_transcript, needs_correction, normalise_transcript


async def correction_node(state: dict) -> dict:
    raw = state.get("question", "")
    if not settings.transcript_correction_enabled:
        return {"raw_question": raw, "corrected_question": raw, "correction_status": "disabled"}

    normalised = normalise_transcript(raw)
    direct = classify_turn(normalised, state.get("history") or [])
    if direct.direct_answer:
        return {
            "raw_question": raw,
            "corrected_question": normalised,
            "question": normalised,
            "correction_status": "normalised" if normalised != raw else "skipped",
        }
    if not needs_correction(normalised):
        return {
            "raw_question": raw,
            "corrected_question": normalised,
            "question": normalised,
            "correction": {"normalised_text": normalised, "deterministic": normalised != raw},
            "correction_status": "normalised" if normalised != raw else "skipped",
        }

    try:
        result = await correct_transcript(normalised, state.get("history"))
    except LLMServiceError:
        return {
            "raw_question": raw,
            "corrected_question": normalised,
            "question": normalised,
            "correction_status": "failed_fallback",
            "correction": {
                "normalised_text": normalised,
                "deterministic": normalised != raw,
                "error": "correction_failed",
            },
        }

    corrected = (result.corrected_text or normalised).strip()
    return {
        "raw_question": raw,
        "corrected_question": corrected or normalised,
        "question": corrected or normalised,
        "correction": {**result.model_dump(), "normalised_text": normalised},
        "correction_status": "applied",
    }
