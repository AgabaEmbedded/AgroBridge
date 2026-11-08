"""Optional LLM normaliser for noisy speech-to-text transcripts."""

from __future__ import annotations

import json
import re

from agents.schemas import CorrectedTranscript
from services.config import settings
from services.llm_service import chat_json


CORRECTION_SYSTEM ="""You are an expert Speech-to-Text (STT) Correction and Normalization Node for "AgroBridge", an AI voice assistant for smallholder farmers in Nigeria.

INPUT CONTEXT:
The incoming input is raw text generated from narrow-band telephonic audio (8kHz GSM). It contains severe phonetic misspellings, accent distortions (Nigerian English / Pidgin), audio dropouts, and domain-specific errors (agricultural terms, crop names, inputs, locations).

YOUR TASK:
Infer the caller's true intent and output ONLY the corrected, normalized version of what they meant to say. 

CORRECTION RULES:
1. Map phonetic variations and misspellings to their correct domain terms:
   - Crops: "meat/meiz/m e i zed e" -> maize, "cut over/cassaba" -> cassava, "young family/yam family" -> yam, "grounded nut" -> groundnut.
   - Inputs & Terms: "fat analyzer/fertilizer/fertiliser" -> fertilizer, "pesty side" -> pesticide, "N-P-K / npk" -> NPK fertilizer, "urea/uria" -> urea.
   - Locations: "nasa elastic/nasarawa" -> Nasarawa, "abuja sticks/abuja state" -> Abuja, "kaduna/carduna" -> Kaduna.
2. Preserve user intent completely: Do NOT answer the question or generate a response to the farmer. You are purely a transcription text refiner.
3. Keep the tone natural: Retain simple phrasing or light Pidgin structures if intended, but fix gibberish caused by STT misinterpretation.
4. Output format: Return strictly the corrected text. Do NOT add preamble, markdown, explanations, or quotes.

EXAMPLES:
- Input: "I want to point me what fat analyzer should I apply for meat as in m e i zed e in abuja sticks."
  Output: "I want to know what fertilizer I should apply for maize in Abuja."

- Input: "tell me about young family in nasa elastic."
  Output: "Tell me about yam farming in Nasarawa."
  """


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
