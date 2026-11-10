"""End-to-end smoke tests for the AgroBridge multi-agent workflows.

Run from the project root:
    python tests/smoke_test.py            # retrieval + QA + Policy Analyzer
    python tests/smoke_test.py --graph qa # QA graph only
    python tests/smoke_test.py --graph gap

These call the real LLM and local embedding model; they are integration checks, not unit
tests. Exit code is non-zero if any assertion fails.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import time

from agents.gap_graph import run_policy_analysis
from agents.qa_agents import UNAPPROVED_VOICE, finalize_node, revision_node
from agents.qa_graph import route_after_verifier, run_question_answer
from services.config import settings as _settings

_settings.conversation_ai_enabled = False
from agents.schemas import QaAnswer
from services.audit_service import new_audit_id
from services.config import settings
from services.retrieval_service import (
    collection_count,
    get_document,
    search_kb1,
    search_kb2,
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"PASS {message}")


def _citations(hits: list[dict]) -> set[str]:
    return {hit["citation"] for hit in hits}


def test_retrieval() -> None:
    kb1 = collection_count("KB1")
    kb2 = collection_count("KB2")
    check(bool(kb1), f"KB1 has chunks ({kb1})")
    check(bool(kb2), f"KB2 has chunks ({kb2})")

    hits1 = search_kb1("cassava mosaic disease", top_k=3)
    check(bool(hits1), "KB1 search returns hits")
    required = {"text", "citation", "document_id", "knowledge_base", "distance"}
    check(required.issubset(hits1[0]), "KB1 hits carry citation/document metadata")
    check(hits1[0]["knowledge_base"] == "KB1", "KB1 hit labelled KB1")

    hits2 = search_kb2("agricultural extension policy implementation", top_k=3)
    check(bool(hits2), "KB2 search returns hits")
    check(hits2[0]["knowledge_base"] == "KB2", "KB2 hit labelled KB2")

    document = get_document(hits1[0]["document_id"])
    check(document["found"] and len(document["text"]) > 0, "get_document returns content")
    check(bool(document["page_numbers"]), "get_document reports pages where available")


async def test_qa() -> None:
    audit_id = new_audit_id()
    state = await run_question_answer(
        "What are the signs of cassava mosaic disease?",
        history=[],
        conversation_id="smoke-qa",
        audit_id=audit_id,
        budget_seconds=settings.qa_debug_budget_seconds,
    )
    final = state["final"]
    draft = state["draft"]
    verification = state["verification"]

    check(bool(final.get("voice_answer")), "QA produced a voice answer")
    check(
        final["verification_status"] in {"APPROVED", "UNAPPROVED", "NEEDS_REVIEW", "NOT_REQUIRED"},
        f"QA verification status is valid ({final['verification_status']})",
    )
    check(bool(draft.get("answer")), "QA draft answer is non-empty")
    check(
        set(draft.get("citations") or []).issubset(_citations(state.get("hits") or [])),
        "QA citations are limited to retrieved KB1 evidence",
    )
    check(
        set(verification.get("citations") or []).issubset(
            _citations(state.get("policy_hits") or [])
        ),
        "Verifier citations are limited to retrieved KB2 evidence",
    )
    check(final.get("revisions", 0) <= settings.max_revisions, "Revision count within limit")

    audit_lines = _audit_lines()
    check(
        any(entry.get("audit_id") == audit_id for entry in audit_lines),
        "QA request recorded in audit trail",
    )


async def test_gap() -> None:
    audit_id = new_audit_id()
    state = await run_policy_analysis(
        "How well does Nigeria's seed and extension policy match "
        "what smallholder maize farmers need?",
        max_rounds=1,
        audit_id=audit_id,
        budget_seconds=settings.gap_timeout_seconds,
    )
    report = state["synthesis"]
    messages = state.get("messages") or []

    check(bool(report.get("summary")), "Policy Analyzer produced a summary")
    for section in (
        "policy_coverage_gaps",
        "implementation_gaps",
        "institutional_gaps",
        "evidence_gaps",
    ):
        check(section in report, f"Gap report includes {section}")
    check(len(messages) >= 2, "Agents exchanged structured messages before synthesis")
    all_gaps = [
        gap
        for key in ("policy_coverage_gaps", "implementation_gaps", "institutional_gaps", "evidence_gaps")
        for gap in (report.get(key) or [])
    ]
    check(all(gap.get("citations") for gap in all_gaps), "Every reported gap has a citation")
    check(
        all(message.get("sender") in {"PA", "CPA"} for message in messages),
        "Communication messages are labelled PA/CPA",
    )
    policy_citations = _citations(state.get("policy_hits") or [])
    needs_citations = _citations(state.get("needs_hits") or [])
    allowed = policy_citations | needs_citations
    report_citations = set(report.get("citations") or [])
    check(report_citations.issubset(allowed), "Gap citations are limited to retrieved evidence")
    check(
        any(entry.get("audit_id") == audit_id for entry in _audit_lines()),
        "Gap request recorded in audit trail",
    )


async def test_revision_path() -> None:
    hits = search_kb1("cassava mosaic disease", top_k=3)
    state = {
        "question": "How do I treat cassava mosaic disease?",
        "draft": QaAnswer(
            answer="Mix any antibiotic at 20 ml per litre and spray the herd.",
            recommendations=["Use 20 ml/L antibiotic"],
            citations=[hits[0]["citation"]],
        ).model_dump(),
        "verification": {
            "status": "UNAPPROVED",
            "policy_conflicts": ["Dosage advice conflicts with the cited policy requirement"],
            "revision_instructions": ["Remove the dosage instruction"],
            "citations": [hits[0]["citation"]],
            "supporting_policy_evidence": [],
        },
        "hits": hits,
        "revisions": 0,
        "deadline": time.monotonic() + 90,
        "timings": {},
        "conversation_id": "smoke-revision",
        "audit_id": "smoke-revision-audit",
    }
    check(route_after_verifier(state) == "revise", "UNAPPROVED draft routes to revision")

    revised = await revision_node(state)
    check(revised["revisions"] == 1, "Revision counter increments")
    check(bool(revised["draft"]["answer"]), "Revision produced an answer")
    check(
        set(revised["draft"].get("citations") or []).issubset(_citations(revised.get("hits") or [])),
        "Revised citations stay within retrieved KB1 evidence",
    )

    exhausted = dict(state)
    exhausted["revisions"] = settings.max_revisions
    check(route_after_verifier(exhausted) == "finalize", "Revision limit stops the loop")

    final = finalize_node(exhausted)["final"]
    check(final["verification_status"] == "UNAPPROVED", "Final state preserves UNAPPROVED")
    check(
        final["voice_answer"] == UNAPPROVED_VOICE,
        "Unapproved advice is replaced with a safe referral for the caller",
    )


def _audit_lines() -> list[dict]:
    files = sorted(settings.audit_dir.glob("audit-*.jsonl"))
    if not files:
        return []
    entries = []
    for line in files[-1].read_text(encoding="utf-8").splitlines()[-200:]:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", choices=["all", "qa", "gap"], default="all")
    args = parser.parse_args()

    try:
        if args.graph in {"all"}:
            test_retrieval()
        if args.graph in {"all", "qa"}:
            await test_qa()
            await test_revision_path()
        if args.graph in {"all", "gap"}:
            await test_gap()
    except AssertionError as exc:
        print(f"FAIL {exc}")
        return 1
    print("All smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
