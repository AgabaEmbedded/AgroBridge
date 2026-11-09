"""Offline regression tests for contextual interpretation and spoken-output safety."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents import conversation_agent
from agents.evidence import sanitize_spoken_text
from agents.schemas import ConversationDecision
from services.config import settings
from services.conversation import pending_crop_request
from services.transcript_service import normalise_transcript


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"PASS {message}")


def _state(question: str, history: list[dict[str, str]] | None = None) -> dict:
    return {
        "question": question,
        "history": history or [],
        "deadline": time.monotonic() + 10,
        "timings": {},
    }


def test_spoken_sanitizer() -> None:
    raw = "Rice starts with good land [KB1/Rice manual p.4 c.12]. See chunk 42."
    cleaned = sanitize_spoken_text(raw)
    check("KB1" not in cleaned and "p.4" not in cleaned and "chunk" not in cleaned,
          "internal retrieval metadata is removed from spoken text")
    check(cleaned.startswith("Rice starts with good land."), "spoken text keeps the natural answer")


def test_deterministic_repairs() -> None:
    check("prepare my land for planting" in normalise_transcript(
        "I want to prepare my lawn for planting this season."
    ), "lawn is repaired to land in a land-preparation phrase")
    check("kind of soil does maize" in normalise_transcript(
        "What kind of soy does maize need?"
    ), "soy is repaired to soil in a soil-question phrase")
    check("kind of soil does rice" in normalise_transcript(
        "What kind of side does rice need?"
    ), "side is repaired to soil in a soil-question phrase")


def test_pending_request_gate() -> None:
    greeting_history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "Which crop are you planning to plant?"},
    ]
    check(pending_crop_request(greeting_history) is None,
          "a greeting is not treated as a pending crop request")

    substantive = [
        {"role": "user", "content": "I want to prepare my land for planting."},
        {"role": "assistant", "content": "Which crop are you preparing the land for?"},
    ]
    check(pending_crop_request(substantive) == "I want to prepare my land for planting.",
          "a substantive request is retained for crop continuation")


async def test_contextual_node() -> None:
    original = conversation_agent.classify_with_ai
    settings.conversation_ai_enabled = True
    settings.conversation_ai_timeout = 2.0

    async def fake_classify(question, history, timeout):
        if "lawn" in question.lower():
            return ConversationDecision(
                intent="general_crop_question",
                interpreted_question="How do I prepare my land for planting this season?",
                topic="land preparation",
                objective="prepare land",
                interpretation_status="LIKELY_INTENT",
                suspected_substitutions=["lawn -> land"],
                confidence="medium",
            )
        if "beds" in question.lower():
            return ConversationDecision(
                intent="crop_problem",
                crop="rice",
                topic="pest",
                objective="diagnose a rice problem",
                interpretation_status="AMBIGUOUS_INTENT",
                clarification_question="Are birds, insects, or something else disturbing your rice?",
                confidence="low",
            )
        if question == "Rice.":
            return ConversationDecision(
                intent="crop_only",
                crop="rice",
                interpreted_question=None,
                confidence="high",
            )
        return ConversationDecision(intent="clarification", confidence="low")

    conversation_agent.classify_with_ai = fake_classify
    try:
        result = await conversation_agent.conversation_node(
            _state("I want to prepare my lawn for planting this season.")
        )
        check(result["interpreted_question"] == "How do I prepare my land for planting this season?",
              "likely ASR substitution is resolved before retrieval")
        check(result["interpretation_status"] == "LIKELY_INTENT"
              and result["suspected_substitutions"] == ["lawn -> land"],
              "interpretation metadata is retained")
        check(result["direct_answer"] is None, "likely intent proceeds to the answer agent")

        ambiguous = await conversation_agent.conversation_node(
            _state("My rice farm. Beds are disturbing it.")
        )
        check(ambiguous["direct_answer"] == "Are birds, insects, or something else disturbing your rice?",
              "ambiguous problem asks a targeted clarification")
        check(ambiguous["pending_clarification"] == ambiguous["direct_answer"],
              "clarification is recorded as pending")

        short = await conversation_agent.conversation_node(
            _state(
                "Rice.",
                [
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "Which crop are you planning to plant?"},
                ],
            )
        )
        check(short["intent"] == "crop_only" and short["crop"] == "rice",
              "short crop answer remains a crop-only turn")
        check("What would you like to know about your rice" in short["direct_answer"],
              "short crop answer asks what aspect the farmer wants")
    finally:
        conversation_agent.classify_with_ai = original
        settings.conversation_ai_enabled = False


def main() -> int:
    test_spoken_sanitizer()
    test_deterministic_repairs()
    test_pending_request_gate()
    asyncio.run(test_contextual_node())
    print("All transcript resilience tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
