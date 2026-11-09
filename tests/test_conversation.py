"""Conversation-routing tests for the Farmer Assistant (no LLM required)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.conversation_agent import _fallback_updates
from agents.qa_graph import run_question_answer
from services.config import settings
from services.conversation import classify_turn
from services.transcript_service import normalise_transcript


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"PASS {message}")


settings.conversation_ai_enabled = False


def test_classifier() -> None:
    greeting = classify_turn("good morning", [])
    check(greeting.intent == "greeting" and greeting.direct_answer, "greeting is handled directly")

    social = classify_turn("thank you", [])
    check(social.intent == "social", "social closing is handled directly")

    missing_crop = classify_turn("my leaves are yellow", [])
    check(
        missing_crop.intent == "general_crop_question" and not missing_crop.direct_answer,
        "missing crop still reaches the answer agent",
    )

    land = classify_turn("I am preparing land for farming, any help?", [])
    check(
        land.intent == "general_crop_question" and not land.direct_answer,
        "general farming question reaches the answer agent",
    )

    crop_only = classify_turn("I grow maize", [])
    check(crop_only.intent == "crop_only" and crop_only.crop == "maize", "crop-only reply asks a useful question")

    problem = classify_turn("my maize leaves are yellow", [])
    check(problem.intent == "crop_problem" and problem.crop == "maize", "crop problem routes to RAG")

    follow_up = classify_turn(
        "what fertilizer should I use?",
        [{"role": "user", "content": "my maize leaves are yellow"}, {"role": "assistant", "content": "..."}],
    )
    check(follow_up.crop == "maize" and not follow_up.direct_answer, "crop is remembered across turns")

    livestock = classify_turn("my cow has a fever", [])
    check(livestock.intent == "livestock" and livestock.direct_answer, "livestock is redirected")

    out = classify_turn("who won the football match?", [])
    check(out.intent == "out_of_scope" and out.direct_answer, "out-of-scope is declined")

    backchannel = classify_turn("do you hear me?", [])
    check(backchannel.intent == "clarification" and "hear" in (backchannel.direct_answer or "").lower(),
          "audio backchannel is conversational, not RAG")

    history = [
        {"role": "user", "content": "I am preparing land for farming, any help?"},
        {"role": "assistant", "content": "Good land preparation... Which crop are you preparing the land for?"},
    ]
    continuation = _fallback_updates("maize", history)
    check(
        continuation["intent"] == "crop_question"
        and continuation["crop"] == "maize"
        and "I am preparing land for farming, any help?" in continuation["question"]
        and "maize" in continuation["question"],
        "crop answer continues the previous question",
    )

    repeat = _fallback_updates("can you repeat the question?", history)
    check(
        repeat["direct_answer"] == "Good land preparation... Which crop are you preparing the land for?",
        "repeat request replays the previous assistant turn",
    )

    pending_filler = _fallback_updates("please", history)
    check(
        pending_filler["direct_answer"] == "Good land preparation... Which crop are you preparing the land for?",
        "filler while a crop question is pending re-asks the crop question",
    )

    generic = classify_turn("what is crop rotation?", [])
    check(generic.intent == "general_crop_question" and not generic.direct_answer, "generic crop question routes to RAG")

    check("rice" in normalise_transcript("I want to start a line"), "ASR normaliser repairs line→rice")
    check("maize" in normalise_transcript("Mead. Mead. Mead."), "ASR normaliser repairs mead→maize")
    check("fertilizer" in normalise_transcript("What what capitalize can I use?"), "ASR normaliser repairs capitalize→fertilizer")


async def test_noisy_graph() -> None:
    state = await run_question_answer("Mead. Mead. Mead.", history=[], audit_id="conv-noisy", budget_seconds=10)
    final = state["final"]
    check(final.get("intent") == "crop_only" and final.get("crop") == "maize", "noisy mead routes to maize")
    check(str(state.get("corrected_question", "")).lower().startswith("maize"), "noisy mead is corrected before routing")
    check(final.get("verification_status") == "NOT_REQUIRED", "noisy crop-only turn is direct")


async def test_graph_direct() -> None:
    for question, intent in [
        ("hello", "greeting"),
        ("my cow has a fever", "livestock"),
        ("can you hear me?", "clarification"),
        ("thank you", "social"),
    ]:
        state = await run_question_answer(question, history=[], audit_id=f"conv-{intent}", budget_seconds=10)
        final = state["final"]
        check(final["verification_status"] == "NOT_REQUIRED", f"{intent}: no verification required")
        check(bool(final["voice_answer"]), f"{intent}: direct answer returned")
        check(not (state.get("hits") or []), f"{intent}: no retrieval performed")
        check(final.get("intent") == intent, f"{intent}: intent recorded")


async def main() -> int:
    test_classifier()
    await test_graph_direct()
    await test_noisy_graph()
    print("All conversation tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
