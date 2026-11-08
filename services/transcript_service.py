"""Optional LLM normaliser for noisy speech-to-text transcripts."""

from __future__ import annotations

import json
import re

from agents.schemas import CorrectedTranscript
from services.config import settings
from services.llm_service import chat_json

CORRECTION_SYSTEM = """You normalise noisy automatic-speech-recognition (ASR) transcripts from
Nigerian smallholder farmers. Correct obvious ASR errors, filler words, stutters and repetition
while preserving the caller's actual request and crop. Do not answer the question and do not add
facts. Common mis-hearings in this domain include "line" for rice, "mead" for maize, "family" for
farmer, "culture" for agriculture and "capitalize" for fertilizer; use phonetics and context, but do
not force a correction when the audio is genuinely ambiguous. If the transcript is already clear,
return it unchanged. Keep the corrected question under 40 words. Return JSON with corrected_text,
crop (or null), confidence and a short note."""


async def correct_transcript(question: str, history: list[dict[str, str]] | None) -> CorrectedTranscript:
    recent = [
        f"{message.get('role')}: {message.get('content')}"
        for message in (history or [])[-4:]
        if message.get("content")
    ]
    user = (
        f"Raw transcript: {question}\n\n"
        f"Recent conversation:\n" + ("\n".join(recent) if recent else "(none)")
    )
    return await chat_json(
        CORRECTION_SYSTEM,
        user,
        CorrectedTranscript,
        max_tokens=120,
        timeout=settings.transcript_correction_timeout,
        temperature=0,
    )


_DETERMINISTIC_RULES = (
    (r"\bstart a line\b", "start a rice farm"),
    (r"\bline for my culture\b", "rice farm for my agriculture"),
    (r"\bfor my culture\b", "for my agriculture"),
    (r"\bfamily in\b", "farmer in"),
    (r"\bcapitalize can i use\b", "fertilizer can i use"),
    (r"\bmead\b", "maize"),
)


def normalise_transcript(text: str) -> str:
    """Fast, phrase-scoped repairs for ASR errors observed in production calls."""
    result = text
    for pattern, replacement in _DETERMINISTIC_RULES:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    result = re.sub(r"\b(\w+)(?:\s+\1\b)+", r"\1", result, flags=re.IGNORECASE)
    return " ".join(result.split())


_KNOWN_ASR_MARKERS = re.compile(
    r"\b(line|mead|capitalize|family in|culture)\b", re.IGNORECASE
)
_REPEATED_WORD = re.compile(r"\b(\w+)(?:\s+\1)+\b", re.IGNORECASE)
_FILLERS = {"okay", "ok", "no", "yes", "please", "actually", "well", "so", "i", "also", "ask", "me"}


def needs_correction(text: str) -> bool:
    """Cheap gate so clean turns do not pay the correction LLM's latency."""
    lowered = text.lower()
    if _KNOWN_ASR_MARKERS.search(lowered) or _REPEATED_WORD.search(lowered):
        return True
    tokens = re.findall(r"[a-z]+", lowered)
    if not tokens:
        return False
    if len(tokens) <= 2 and all(token in _FILLERS for token in tokens):
        return False
    filler_ratio = sum(token in _FILLERS for token in tokens) / len(tokens)
    return len(tokens) <= 10 and filler_ratio >= 0.45
