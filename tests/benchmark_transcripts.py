"""A/B benchmark for noisy ASR transcripts.

Variants:
  baseline  - raw transcript
  prompt    - noisy-transcript instruction added to the answer system prompt
  correction- LLM normaliser before routing
  both      - normaliser + prompt instruction

Run from the project root: python tests/benchmark_transcripts.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.qa_graph import run_question_answer
from services.config import settings

CASES = [
    {
        "raw": "Okay. Good morning. Please, I also ask",
        "expect_intent": "greeting",
    },
    {
        "raw": "No.",
        "expect_intent": "clarification",
    },
    {
        "raw": "No. I I want to... actually, I want to start a line.",
        "expect_intent": "crop_question",
        "expect_crop": "rice",
        "keywords": ["rice"],
    },
    {
        "raw": (
            "No. I I want to... actually, I want to start a line for my culture. "
            "So how do I prepare? So that is it. Let's pay. I'm family in Lagos, Nigeria. Me."
        ),
        "expect_intent": "crop_question",
        "expect_crop": "rice",
        "keywords": ["rice", "prepare"],
        "expect_answer": True,
    },
    {
        "raw": "Mead. Mead. Mead.",
        "expect_intent": "crop_only",
        "expect_crop": "maize",
        "keywords": ["maize"],
    },
    {
        "raw": "What what capitalize can I use?",
        "expect_intent": "clarification",
        "keywords": ["fertilizer", "fertiliser"],
    },
    {
        "raw": "my maize leaves are turning yellow before harvest",
        "expect_intent": "crop_problem",
        "expect_crop": "maize",
        "keywords": ["maize", "yellow"],
        "expect_answer": True,
    },
]

DIRECT = {"greeting", "clarification", "social", "out_of_scope"}


def score_case(case: dict, state: dict) -> dict:
    final = state.get("final") or {}
    correction = state.get("correction") or {}
    corrected = str(correction.get("corrected_text") or correction.get("normalised_text") or "")
    answer = str(final.get("answer") or "")
    haystack = f"{corrected} {answer}".lower()
    intent = final.get("intent") or state.get("intent")
    crop = final.get("crop") or state.get("crop")

    expected_intent = case.get("expect_intent")
    if expected_intent in DIRECT:
        routing = intent == expected_intent
    elif case.get("expect_crop"):
        routing = crop == case["expect_crop"] and intent not in DIRECT
    else:
        routing = intent == expected_intent

    keywords = [item.lower() for item in case.get("keywords", [])]
    keyword = not keywords or any(item in haystack for item in keywords)

    citations = len(final.get("citations") or [])
    answered = (not case.get("expect_answer")) or citations > 0
    return {
        "routing": bool(routing),
        "keyword": bool(keyword),
        "grounded": bool(answered),
        "score": (int(routing) + int(keyword) + int(answered)) / 3,
    }


async def run_variant(name: str, correction: bool, hint: bool) -> dict:
    settings.transcript_correction_enabled = correction
    settings.noisy_transcript_hint = hint
    settings.verifier_enabled = False
    rows = []
    started = time.perf_counter()
    for index, case in enumerate(CASES):
        case_started = time.perf_counter()
        state = await run_question_answer(
            case["raw"],
            history=[],
            conversation_id=f"bench-{name}-{index}",
            audit_id=f"bench-{name}-{index}",
            budget_seconds=60,
        )
        final = state.get("final") or {}
        correction_result = state.get("correction") or {}
        rows.append(
            {
                "raw": case["raw"],
                "corrected": correction_result.get("corrected_text", ""),
                "intent": final.get("intent") or state.get("intent"),
                "crop": final.get("crop") or state.get("crop"),
                "status": final.get("verification_status"),
                "citations": len(final.get("citations") or []),
                "answer": (final.get("answer") or "")[:240],
                "correction_status": state.get("correction_status"),
                "seconds": round(time.perf_counter() - case_started, 2),
                **score_case(case, state),
            }
        )
    total = sum(row["score"] for row in rows) / len(rows)
    summary = {
        "variant": name,
        "correction": correction,
        "hint": hint,
        "mean_score": round(total, 3),
        "routing": sum(row["routing"] for row in rows),
        "keyword": sum(row["keyword"] for row in rows),
        "grounded": sum(row["grounded"] for row in rows),
        "avg_seconds": round((time.perf_counter() - started) / len(rows), 2),
        "rows": rows,
    }
    print(f"{name:<11} score={summary['mean_score']:.3f} routing={summary['routing']}/{len(rows)} "
          f"keyword={summary['keyword']}/{len(rows)} grounded={summary['grounded']}/{len(rows)} "
          f"avg={summary['avg_seconds']}s")
    return summary


async def main() -> int:
    variants = [
        ("baseline", False, False),
        ("prompt", False, True),
        ("correction", True, False),
        ("both", True, True),
    ]
    results = [await run_variant(*variant) for variant in variants]
    Path(".tmp").mkdir(exist_ok=True)
    Path(".tmp/autocorrect_benchmark.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("\nDetailed rows:")
    for result in results:
        print(f"\n## {result['variant']}")
        for row in result["rows"]:
            print(
                f"- {row['raw'][:45]!r} | corrected={row['corrected'][:60]!r} | "
                f"intent={row['intent']} crop={row['crop']} | "
                f"route={row['routing']} keyword={row['keyword']} grounded={row['grounded']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
