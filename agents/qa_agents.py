"""Question-Answer agents: AgroBridge answer, policy verifier, revision, finalisation."""

from __future__ import annotations

import asyncio
import time

from agents import prompts
from agents.evidence import format_evidence, sanitize_answer, sanitize_verification
from agents.runtime import call_timeout, expired, timings_with
from agents.schemas import (
    EvidenceItem,
    QaAnswer,
    QaDraft,
    VerificationResult,
    VerificationVerdict,
)
from services.audit_service import write_audit
from services.config import settings
from services.llm_service import LLMServiceError, chat_json
from services.retrieval_service import collection_count, search_kb1, search_kb2

NO_EVIDENCE_ANSWER = (
    "I could not find reliable guidance for that question in my current information. "
    "Which crop or animal is affected, and where are you farming?"
)
RETRIEVAL_FALLBACK = (
    "I am having trouble checking the agricultural information right now. "
    "Please try again shortly or contact your local agricultural extension officer."
)
LLM_FALLBACK = (
    "I am unable to check the guidance right now. Please try again shortly "
    "or contact your local agricultural extension officer."
)
UNAPPROVED_VOICE = (
    "I could not confirm that this advice meets current official guidance. "
    "Please contact your local agricultural extension officer or veterinarian before acting on it."
)
REVIEW_CAVEAT = " Please confirm this with your local agricultural extension officer."


def _history_text(history: list[dict[str, str]] | None, limit: int = 8) -> str:
    if not history:
        return ""
    lines = []
    for message in history[-limit:]:
        role = "farmer" if message.get("role") == "user" else "assistant"
        lines.append(f"{role}: {message.get('content', '')}")
    return "Earlier turns:\n" + "\n".join(lines) + "\n\n"


def _answer_with_evidence(draft: QaDraft, hits: list[dict]) -> QaAnswer:
    index = {hit["citation"]: hit for hit in hits}
    evidence = []
    for citation in draft.citations:
        hit = index.get(citation)
        if hit is None:
            continue
        evidence.append(
            EvidenceItem(
                citation=citation,
                quote=hit["text"][:200],
                document_name=hit.get("document_name"),
                page_number=hit.get("page_number"),
            )
        )
    return QaAnswer(
        answer=draft.answer,
        recommendations=draft.recommendations,
        supporting_evidence=evidence,
        citations=draft.citations,
        confidence=draft.confidence,
    )


def _verdict_with_evidence(verdict: VerificationVerdict, hits: list[dict]) -> VerificationResult:
    index = {hit["citation"]: hit for hit in hits}
    evidence = []
    for citation in verdict.citations:
        hit = index.get(citation)
        if hit is None:
            continue
        evidence.append(
            EvidenceItem(
                citation=citation,
                quote=hit["text"][:200],
                document_name=hit.get("document_name"),
                page_number=hit.get("page_number"),
            )
        )
    return VerificationResult(
        status=verdict.status,
        policy_conflicts=verdict.policy_conflicts,
        supporting_policy_evidence=evidence,
        citations=verdict.citations,
        revision_instructions=verdict.revision_instructions,
        reasoning_summary=verdict.reasoning_summary,
    )


def _verification(status: str, summary: str, **extra) -> dict:
    payload = {
        "status": status,
        "policy_conflicts": extra.get("policy_conflicts", []),
        "supporting_policy_evidence": extra.get("supporting_policy_evidence", []),
        "citations": extra.get("citations", []),
        "revision_instructions": extra.get("revision_instructions", []),
        "reasoning_summary": summary,
    }
    return payload


async def agrobridge_node(state: dict) -> dict:
    started = time.monotonic()
    question = state["question"]
    try:
        hits = await asyncio.to_thread(search_kb1, question, None, state.get("top_k") or settings.top_k)
    except Exception:
        draft = QaAnswer(answer=RETRIEVAL_FALLBACK, confidence="low")
        return {
            "error": "retrieval_error",
            "draft": draft.model_dump(),
            "hits": [],
            "timings": timings_with(state, agrobridge_ms=(time.monotonic() - started) * 1000),
        }

    useful = [hit for hit in hits if hit["distance"] <= settings.min_relevance_distance]
    if not useful:
        draft = QaAnswer(answer=NO_EVIDENCE_ANSWER, confidence="low")
        return {
            "error": None,
            "draft": draft.model_dump(),
            "hits": hits,
            "timings": timings_with(state, agrobridge_ms=(time.monotonic() - started) * 1000),
        }

    user = (
        f"{_history_text(state.get('history'))}"
        f"Farmer question: {question}\n\n"
        f"KB1 evidence:\n{format_evidence(useful)}\n\n"
        "Answer using only this evidence. Copy citation labels exactly."
    )
    try:
        draft = await chat_json(
            prompts.QA_ANSWER_SYSTEM,
            user,
            QaDraft,
            max_tokens=settings.qa_answer_max_tokens,
            timeout=call_timeout(state, 0.55),
        )
    except LLMServiceError:
        draft = QaAnswer(answer=LLM_FALLBACK, confidence="low")
        return {
            "error": "llm_error",
            "draft": draft.model_dump(),
            "hits": useful,
            "timings": timings_with(state, agrobridge_ms=(time.monotonic() - started) * 1000),
        }

    answer, dropped = sanitize_answer(_answer_with_evidence(draft, useful), useful)
    return {
        "error": None,
        "draft": answer.model_dump(),
        "hits": useful,
        "dropped_citations": dropped,
        "timings": timings_with(state, agrobridge_ms=(time.monotonic() - started) * 1000),
    }


async def verifier_node(state: dict) -> dict:
    started = time.monotonic()
    question = state["question"]
    draft = QaAnswer.model_validate(state.get("draft") or {})

    if not settings.verifier_enabled:
        return {
            "verification": _verification("NEEDS_REVIEW", "Verifier disabled by configuration."),
            "timings": timings_with(state, verifier_ms=(time.monotonic() - started) * 1000),
        }

    if state.get("error") in {"retrieval_error", "llm_error"}:
        return {
            "verification": _verification(
                "NEEDS_REVIEW", "Answer generation failed; nothing to verify."
            ),
            "timings": timings_with(state, verifier_ms=(time.monotonic() - started) * 1000),
        }

    if draft.answer == NO_EVIDENCE_ANSWER:
        return {
            "verification": _verification(
                "NEEDS_REVIEW", "No KB1 evidence supported an answer, so no policy claim was made."
            ),
            "timings": timings_with(state, verifier_ms=(time.monotonic() - started) * 1000),
        }

    if collection_count("KB2") == 0:
        return {
            "verification": _verification(
                "NEEDS_REVIEW", "No policy documents are ingested in KB2."
            ),
            "timings": timings_with(state, verifier_ms=(time.monotonic() - started) * 1000),
        }

    if expired(state, minimum=1.0):
        return {
            "verification": _verification(
                "NEEDS_REVIEW", "Verification skipped: voice latency budget exhausted."
            ),
            "timings": timings_with(state, verifier_ms=(time.monotonic() - started) * 1000),
        }

    query = question + "\n" + " ".join(draft.recommendations)
    try:
        hits = await asyncio.to_thread(search_kb2, query, None, state.get("top_k") or settings.top_k)
    except Exception:
        return {
            "verification": _verification("NEEDS_REVIEW", "KB2 retrieval failed."),
            "timings": timings_with(state, verifier_ms=(time.monotonic() - started) * 1000),
        }

    if not hits:
        return {
            "verification": _verification(
                "NEEDS_REVIEW", "No applicable policy passages were retrieved from KB2."
            ),
            "timings": timings_with(state, verifier_ms=(time.monotonic() - started) * 1000),
        }

    user = (
        f"Farmer question: {question}\n\n"
        f"Proposed answer:\n{draft.answer}\n\n"
        f"Proposed recommendations:\n- " + "\n- ".join(draft.recommendations or ["(none listed)"]) + "\n\n"
        f"KB2 policy evidence:\n{format_evidence(hits)}\n\n"
        "Decide APPROVED / UNAPPROVED / NEEDS_REVIEW using only this evidence."
    )
    try:
        verdict = await chat_json(
            prompts.VERIFIER_SYSTEM,
            user,
            VerificationVerdict,
            max_tokens=settings.verifier_max_tokens,
            timeout=call_timeout(state, 0.9),
        )
    except LLMServiceError:
        return {
            "verification": _verification(
                "NEEDS_REVIEW", "Verification failed or timed out; answer is unverified."
            ),
            "policy_hits": hits,
            "timings": timings_with(state, verifier_ms=(time.monotonic() - started) * 1000),
        }

    result, dropped = sanitize_verification(_verdict_with_evidence(verdict, hits), hits)
    if result.status == "UNAPPROVED" and not result.policy_conflicts:
        result = VerificationResult(
            status="NEEDS_REVIEW",
            policy_conflicts=[],
            supporting_policy_evidence=result.supporting_policy_evidence,
            citations=result.citations,
            revision_instructions=[],
            reasoning_summary="Verifier reported a conflict without identifying it; treated as review.",
        )
    return {
        "verification": result.model_dump(),
        "policy_hits": hits,
        "dropped_citations": list(state.get("dropped_citations") or []) + dropped,
        "timings": timings_with(state, verifier_ms=(time.monotonic() - started) * 1000),
    }


async def revision_node(state: dict) -> dict:
    started = time.monotonic()
    revisions = int(state.get("revisions") or 0) + 1
    draft = QaAnswer.model_validate(state.get("draft") or {})
    verification = state.get("verification") or {}

    if expired(state, minimum=1.0):
        return {
            "revisions": revisions,
            "verification": _verification(
                "NEEDS_REVIEW",
                "Revision skipped: latency budget exhausted after an unapproved draft.",
            ),
            "timings": timings_with(state, revision_ms=(time.monotonic() - started) * 1000),
        }

    query = (
        state["question"]
        + " "
        + " ".join(verification.get("policy_conflicts") or [])
        + " "
        + " ".join(verification.get("revision_instructions") or [])
    )
    hits = list(state.get("hits") or [])
    try:
        extra = await asyncio.to_thread(search_kb1, query, None, state.get("top_k") or settings.top_k)
        merged = {hit["citation"]: hit for hit in hits}
        for hit in extra:
            if hit["distance"] <= settings.min_relevance_distance:
                merged.setdefault(hit["citation"], hit)
        hits = list(merged.values())
    except Exception:
        pass

    user = (
        f"Farmer question: {state['question']}\n\n"
        f"Current draft:\n{draft.answer}\n\n"
        f"Policy conflicts:\n- " + "\n- ".join(verification.get("policy_conflicts") or ["(none)"]) + "\n\n"
        f"Revision instructions:\n- " + "\n- ".join(verification.get("revision_instructions") or ["(none)"]) + "\n\n"
        f"KB1 evidence:\n{format_evidence(hits)}\n\n"
        "Revise the draft so it no longer conflicts with the cited requirements."
    )
    try:
        revised_draft = await chat_json(
            prompts.REVISION_SYSTEM,
            user,
            QaDraft,
            max_tokens=settings.qa_answer_max_tokens,
            timeout=call_timeout(state, 0.75),
        )
    except LLMServiceError:
        return {
            "revisions": revisions,
            "verification": _verification(
                "NEEDS_REVIEW", "Revision failed; the unapproved draft was not returned as approved."
            ),
            "timings": timings_with(state, revision_ms=(time.monotonic() - started) * 1000),
        }

    revised, dropped = sanitize_answer(_answer_with_evidence(revised_draft, hits), hits)
    return {
        "revisions": revisions,
        "draft": revised.model_dump(),
        "hits": hits,
        "dropped_citations": list(state.get("dropped_citations") or []) + dropped,
        "timings": timings_with(state, revision_ms=(time.monotonic() - started) * 1000),
    }


def finalize_node(state: dict) -> dict:
    draft = state.get("draft") or {}
    verification = state.get("verification") or {}
    status = verification.get("status") or "NEEDS_REVIEW"
    answer = str(draft.get("answer") or "").strip()

    if status == "APPROVED":
        voice_answer = answer
        note = "Verified against KB2 policy evidence."
    elif status == "UNAPPROVED":
        voice_answer = UNAPPROVED_VOICE
        note = "Unapproved after the revision limit; the farmer receives a safe referral instead."
    elif state.get("error") in {"retrieval_error", "llm_error"}:
        voice_answer = answer
        note = "Answer generation failed; fallback returned."
    else:
        voice_answer = answer + (REVIEW_CAVEAT if answer and REVIEW_CAVEAT.strip() not in answer else "")
        note = verification.get("reasoning_summary") or "Unverified; uncertainty communicated."

    final = {
        "answer": answer,
        "voice_answer": voice_answer.strip(),
        "verification_status": status,
        "citations": draft.get("citations") or [],
        "confidence": draft.get("confidence"),
        "revisions": int(state.get("revisions") or 0),
        "note": note,
        "error": state.get("error"),
    }

    audit_record = {
        "question": state.get("question", ""),
        "conversation_id": state.get("conversation_id"),
        "agents_invoked": ["agrobridge"]
        + (["verifier"] if settings.verifier_enabled else [])
        + (["revision"] * int(state.get("revisions") or 0)),
        "knowledge_bases": ["KB1", "KB2"] if state.get("policy_hits") else ["KB1"],
        "retrieved_citations": [hit.get("citation") for hit in state.get("hits") or []],
        "policy_citations": [hit.get("citation") for hit in state.get("policy_hits") or []],
        "draft": draft,
        "verification": verification,
        "revisions": int(state.get("revisions") or 0),
        "final": final,
        "timings": state.get("timings") or {},
        "dropped_citations": state.get("dropped_citations") or [],
    }
    write_audit("question_answer", audit_record, state.get("audit_id"))
    return {"final": final}
