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
from agents.qa_agents import finalize_node, verification_required, verifier_node
from agents.schemas import ConversationDecision, QaAnswer
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


async def test_repeated_clarification() -> None:
    settings.conversation_ai_enabled = False
    history: list[dict[str, str]] = [
        {"role": "assistant", "content": "Which crop are you planting?"}
    ]

    first = await conversation_agent.conversation_node(
        _state("Me.", history)
    )
    check(first["direct_answer"] == "Are you trying to say maize?",
          "unclear crop answer offers a likely crop")
    history.extend(
        [
            {"role": "user", "content": "Me."},
            {"role": "assistant", "content": first["direct_answer"]},
        ]
    )

    second = await conversation_agent.conversation_node(
        _state("I said meat.", history)
    )
    check(second["direct_answer"] == "Do you mean maize?",
          "correction moves from likely crop to confirmation")
    history.extend(
        [
            {"role": "user", "content": "I said meat."},
            {"role": "assistant", "content": second["direct_answer"]},
        ]
    )

    corrected_no = await conversation_agent.conversation_node(
        _state(
            "No, I said meat.",
            [{"role": "assistant", "content": "Are you trying to say maize?"}],
        )
    )
    check(corrected_no["direct_answer"] == "Do you mean maize?",
          "a correction with 'No, I said' is treated as a crop correction")

    third = await conversation_agent.conversation_node(
        _state("Yes.", history)
    )
    check(third["crop"] == "maize" and third["intent"] == "crop_only",
          "confirmation sets the current crop")
    check("What would you like to know about your maize" in third["direct_answer"],
          "confirmation moves to the next question without re-asking the crop")
    history.extend(
        [
            {"role": "user", "content": "Yes."},
            {"role": "assistant", "content": third["direct_answer"]},
        ]
    )

    fourth = await conversation_agent.conversation_node(
        _state("Soil.", history)
    )
    check(fourth["intent"] == "crop_question" and fourth["crop"] == "maize",
          "short soil answer uses the confirmed crop")
    check(fourth["question"] == "What kind of soil does maize need?",
          "short soil answer becomes a maize soil question")


async def test_confirmation_sequence() -> None:
    settings.conversation_ai_enabled = False
    history = [{"role": "assistant", "content": "Are you planting maize?"}]
    confirmed = await conversation_agent.conversation_node(_state("Yes.", history))
    check(confirmed["crop"] == "maize" and confirmed["intent"] == "crop_only",
          "yes to a crop confirmation sets current crop")
    history.extend(
        [
            {"role": "user", "content": "Yes."},
            {"role": "assistant", "content": confirmed["direct_answer"]},
        ]
    )
    soil = await conversation_agent.conversation_node(_state("Soil.", history))
    check(soil["crop"] == "maize" and soil["question"] == "What kind of soil does maize need?",
          "a one-word soil reply uses the confirmed maize crop")


async def test_fast_path_and_verification() -> None:
    original = conversation_agent.classify_with_ai
    settings.conversation_ai_enabled = True

    async def should_not_run(question, history, timeout):
        raise AssertionError("clear crop turn should not call the AI router")

    conversation_agent.classify_with_ai = should_not_run
    try:
        clear = await conversation_agent.conversation_node(
            _state("My maize leaves are turning yellow.")
        )
        check(clear["intent"] == "crop_problem" and clear["crop"] == "maize",
              "clear crop question uses the deterministic fast path")
        greeting = await conversation_agent.conversation_node(_state("Hello."))
        check(greeting["intent"] == "greeting" and greeting["direct_answer"],
              "clear greeting uses the deterministic fast path")
    finally:
        conversation_agent.classify_with_ai = original
        settings.conversation_ai_enabled = False

    low = QaAnswer(answer="Maize grows best on well drained soil.", confidence="medium")
    high = QaAnswer(answer="Apply NPK fertilizer at the labelled rate.", confidence="medium")
    check(not verification_required("What soil does maize need?", low),
          "general soil guidance skips the model verifier")
    check(verification_required("What fertilizer should I use?", high),
          "fertilizer guidance still requires the model verifier")

    out = await verifier_node(
        {
            "question": "What soil does maize need?",
            "draft": low.model_dump(),
            "deadline": time.monotonic() + 10,
            "timings": {},
            "top_k": 4,
        }
    )
    check(out["verification"]["status"] == "NOT_REQUIRED",
          "low-risk answer returns NOT_REQUIRED without a verifier model call")

    final = finalize_node(
        {
            "question": "What soil does maize need?",
            "draft": low.model_dump(),
            "verification": out["verification"],
            "intent": "crop_question",
            "crop": "maize",
            "timings": {},
        }
    )["final"]
    check(final["verification_status"] == "NOT_REQUIRED"
          and final["voice_answer"] == low.answer,
          "low-risk final answer keeps the answer without a review caveat")


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
    asyncio.run(test_repeated_clarification())
    asyncio.run(test_confirmation_sequence())
    asyncio.run(test_fast_path_and_verification())
    asyncio.run(test_contextual_node())
    print("All transcript resilience tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
