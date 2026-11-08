"""Policy Analyzer agents: Policy Analyst (KB2), Crop Production Analyst (KB1), communication, synthesis."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from agents import prompts
from agents.evidence import (
    format_evidence,
    sanitize_citations,
    sanitize_evidence,
    sanitize_report,
)
from agents.runtime import call_timeout, expired, timings_with
from agents.schemas import (
    AgentMessage,
    CommunicationReply,
    NeedsFindings,
    PolicyFindings,
    SynthesisReport,
)
from services.audit_service import write_audit
from services.config import settings
from services.llm_service import LLMServiceError, chat_json
from services.retrieval_service import search_kb1, search_kb2


def _merge_hits(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for group in groups:
        for hit in group:
            merged.setdefault(hit["citation"], hit)
    return list(merged.values())


def _sanitize_messages(messages: list[AgentMessage], hits: list[dict[str, Any]]) -> list[AgentMessage]:
    cleaned: list[AgentMessage] = []
    for message in messages:
        evidence, _ = sanitize_evidence(message.evidence, hits)
        citations, _ = sanitize_citations(message.citations, hits)
        cleaned.append(
            AgentMessage(
                sender=message.sender,
                recipient=message.recipient,
                intent=message.intent,
                claims=message.claims,
                questions=message.questions,
                evidence=evidence,
                citations=citations,
                notes=message.notes,
            )
        )
    return cleaned


async def policy_analyst_node(state: dict) -> dict:
    started = time.monotonic()
    query = (
        state["query"]
        + " crop production seed fertilizer extension advisory irrigation mechanization "
        "credit market climate government policy commitments implementation targets budgets "
        "institutions implementation report evaluation"
    )
    try:
        hits = await asyncio.to_thread(search_kb2, query, None, settings.gap_top_k)
    except Exception:
        return {
            "policy": PolicyFindings().model_dump(),
            "policy_hits": [],
            "error": "kb2_retrieval_error",
            "timings": timings_with(state, pa_ms=(time.monotonic() - started) * 1000),
        }

    if not hits or expired(state, minimum=3.0):
        return {
            "policy": PolicyFindings().model_dump(),
            "policy_hits": hits,
            "timings": timings_with(state, pa_ms=(time.monotonic() - started) * 1000),
        }

    user = (
        f"Policy analysis question: {state['query']}\n\n"
        f"KB2 policy/implementation evidence:\n{format_evidence(hits)}\n\n"
        "Extract commitments, institutions, targets, implementation evidence and policy gaps."
    )
    try:
        findings = await chat_json(
            prompts.PA_SYSTEM,
            user,
            PolicyFindings,
            max_tokens=settings.gap_max_output_tokens,
            timeout=call_timeout(state, 0.85),
        )
    except LLMServiceError:
        return {
            "policy": PolicyFindings().model_dump(),
            "policy_hits": hits,
            "error": "pa_llm_error",
            "timings": timings_with(state, pa_ms=(time.monotonic() - started) * 1000),
        }

    findings.citations, _ = sanitize_citations(findings.citations, hits)
    return {
        "policy": findings.model_dump(),
        "policy_hits": hits,
        "timings": timings_with(state, pa_ms=(time.monotonic() - started) * 1000),
    }


async def crop_production_analyst_node(state: dict) -> dict:
    started = time.monotonic()
    try:
        hits = await asyncio.to_thread(
            search_kb1,
            f"{state['query']} crop production farmer challenges technical requirements "
            "seed soil water pests extension services",
            None,
            settings.gap_top_k,
        )
    except Exception:
        return {
            "needs": NeedsFindings().model_dump(),
            "needs_hits": [],
            "error": "kb1_retrieval_error",
            "timings": timings_with(state, cpa_ms=(time.monotonic() - started) * 1000),
        }

    policy = state.get("policy") or {}
    if not hits or expired(state, minimum=3.0):
        return {
            "needs": NeedsFindings().model_dump(),
            "needs_hits": hits,
            "timings": timings_with(state, cpa_ms=(time.monotonic() - started) * 1000),
        }

    user = (
        f"Analysis question: {state['query']}\n\n"
        f"PA policy findings:\n{json.dumps(policy, ensure_ascii=False)}\n\n"
        f"KB1 agricultural evidence:\n{format_evidence(hits)}\n\n"
        "Identify practical challenges, farmer needs, technical requirements and coverage observations."
    )
    try:
        findings = await chat_json(
            prompts.CPA_SYSTEM,
            user,
            NeedsFindings,
            max_tokens=settings.gap_max_output_tokens,
            timeout=call_timeout(state, 0.85),
        )
    except LLMServiceError:
        return {
            "needs": NeedsFindings().model_dump(),
            "needs_hits": hits,
            "error": "cpa_llm_error",
            "timings": timings_with(state, cpa_ms=(time.monotonic() - started) * 1000),
        }

    findings.citations, _ = sanitize_citations(findings.citations, hits)
    return {
        "needs": findings.model_dump(),
        "needs_hits": hits,
        "timings": timings_with(state, cpa_ms=(time.monotonic() - started) * 1000),
    }


def _communication_context(state: dict, messages: list[dict[str, Any]]) -> str:
    return (
        f"Analysis question: {state['query']}\n\n"
        f"PA findings:\n{json.dumps(state.get('policy') or {}, ensure_ascii=False)}\n\n"
        f"CPA findings:\n{json.dumps(state.get('needs') or {}, ensure_ascii=False)}\n\n"
        f"Conversation so far:\n{json.dumps(messages[-8:], ensure_ascii=False)}"
    )


async def communication_node(state: dict) -> dict:
    """One structured exchange per round, alternating direction."""
    started = time.monotonic()
    rounds = int(state.get("rounds") or 0)
    value = state.get("max_rounds")
    max_rounds = settings.gap_max_rounds if value is None else int(value)
    messages = list(state.get("messages") or [])
    policy_hits = list(state.get("policy_hits") or [])
    needs_hits = list(state.get("needs_hits") or [])

    if rounds >= max_rounds or expired(state, minimum=5.0):
        return {"rounds": max_rounds}

    context = _communication_context(state, messages)
    cpa_to_pa = rounds % 2 == 0

    try:
        if cpa_to_pa:
            ask = await chat_json(
                prompts.CPA_COMMUNICATION_SYSTEM,
                context
                + "\n\nAsk PA whether the identified needs are covered by commitments, "
                "implementation evidence or budgets.",
                CommunicationReply,
                max_tokens=settings.gap_max_output_tokens,
                timeout=call_timeout(state, 0.6),
            )
            asked = _sanitize_messages(ask.messages, policy_hits + needs_hits)
            for message in asked:
                message.sender, message.recipient = "CPA", "PA"

            query = " ".join(
                message.questions[0] if message.questions else message.notes
                for message in asked
            ) or state["query"]
            extra = await asyncio.to_thread(search_kb2, query, None, settings.gap_top_k)
            policy_hits = _merge_hits(policy_hits, extra)

            reply_context = (
                context
                + f"\n\nCPA's questions:\n{json.dumps([m.model_dump() for m in asked], ensure_ascii=False)}"
                + f"\n\nKB2 evidence:\n{format_evidence(extra)}"
            )
            reply = await chat_json(
                prompts.PA_COMMUNICATION_SYSTEM,
                reply_context,
                CommunicationReply,
                max_tokens=settings.gap_max_output_tokens,
                timeout=call_timeout(state, 0.8),
            )
            answered = _sanitize_messages(reply.messages, policy_hits)
            for message in answered:
                message.sender, message.recipient = "PA", "CPA"
        else:
            ask = await chat_json(
                prompts.PA_COMMUNICATION_TO_CPA_SYSTEM,
                context
                + "\n\nAsk CPA whether policy assumptions match technical and farmer realities.",
                CommunicationReply,
                max_tokens=settings.gap_max_output_tokens,
                timeout=call_timeout(state, 0.6),
            )
            asked = _sanitize_messages(ask.messages, policy_hits + needs_hits)
            for message in asked:
                message.sender, message.recipient = "PA", "CPA"

            query = " ".join(
                message.questions[0] if message.questions else message.notes
                for message in asked
            ) or state["query"]
            extra = await asyncio.to_thread(search_kb1, query, None, settings.gap_top_k)
            needs_hits = _merge_hits(needs_hits, extra)

            reply_context = (
                context
                + f"\n\nPA's questions:\n{json.dumps([m.model_dump() for m in asked], ensure_ascii=False)}"
                + f"\n\nKB1 evidence:\n{format_evidence(extra)}"
            )
            reply = await chat_json(
                prompts.CPA_COMMUNICATION_TO_PA_SYSTEM,
                reply_context,
                CommunicationReply,
                max_tokens=settings.gap_max_output_tokens,
                timeout=call_timeout(state, 0.8),
            )
            answered = _sanitize_messages(reply.messages, needs_hits)
            for message in answered:
                message.sender, message.recipient = "CPA", "PA"
    except LLMServiceError:
        return {
            "rounds": max_rounds,
            "messages": messages,
            "policy_hits": policy_hits,
            "needs_hits": needs_hits,
            "error": "communication_error",
            "timings": timings_with(state, communication_ms=(time.monotonic() - started) * 1000),
        }

    messages.extend(message.model_dump() for message in asked)
    messages.extend(message.model_dump() for message in answered)
    return {
        "rounds": rounds + 1,
        "messages": messages,
        "policy_hits": policy_hits,
        "needs_hits": needs_hits,
        "timings": timings_with(state, communication_ms=(time.monotonic() - started) * 1000),
    }


async def synthesis_node(state: dict) -> dict:
    started = time.monotonic()
    policy_hits = list(state.get("policy_hits") or [])
    needs_hits = list(state.get("needs_hits") or [])
    messages = list(state.get("messages") or [])
    all_hits = _merge_hits(policy_hits, needs_hits)

    if not all_hits:
        report = SynthesisReport(
            summary=(
                "No relevant policy or agricultural documents were retrieved, so no gap can be "
                "established from this query."
            ),
            key_findings=[],
            limitations=[
                "This is a retrieval gap, not a policy finding. Add relevant documents to KB1/KB2 "
                "and re-run before drawing conclusions."
            ],
        )
    else:
        user = (
            f"Analysis question: {state['query']}\n\n"
            f"PA findings:\n{json.dumps(state.get('policy') or {}, ensure_ascii=False)}\n\n"
            f"CPA findings:\n{json.dumps(state.get('needs') or {}, ensure_ascii=False)}\n\n"
            f"Communication history:\n{json.dumps(messages, ensure_ascii=False)}\n\n"
            f"Retrieved evidence:\n{format_evidence(all_hits, max_chars=900)}\n\n"
            "Synthesise only evidence-backed findings in plain language. Zero gaps in a category "
            "is valid; do not fill categories or invent a gap. Every reported gap needs a citation."
        )
        try:
            report = await chat_json(
                prompts.SYNTHESIS_SYSTEM,
                user,
                SynthesisReport,
                max_tokens=settings.gap_max_output_tokens,
                timeout=call_timeout(state, 0.9),
            )
        except LLMServiceError:
            report = SynthesisReport(
                summary="Synthesis failed after both agents produced findings.",
                limitations=["LLM synthesis error; see agent findings and communication history."],
                citations=[],
            )

    report, dropped = sanitize_report(report, all_hits)

    # Never present an unsupported gap. Empty categories are intentional.
    removed = 0
    for section in (
        report.policy_coverage_gaps,
        report.implementation_gaps,
        report.institutional_gaps,
        report.evidence_gaps,
    ):
        kept = [gap for gap in section if gap.citations]
        removed += len(section) - len(kept)
        section[:] = kept
    if removed:
        report.limitations = list(report.limitations) + [
            f"{removed} unsupported gap(s) were removed because they had no citation."
        ]

    audit_record = {
        "query": state.get("query", ""),
        "agents_invoked": ["pa", "cpa", "communication", "synthesis"],
        "rounds": state.get("rounds", 0),
        "knowledge_bases": ["KB1", "KB2"],
        "retrieved_citations": [hit.get("citation") for hit in needs_hits],
        "policy_citations": [hit.get("citation") for hit in policy_hits],
        "policy_findings": state.get("policy") or {},
        "needs_findings": state.get("needs") or {},
        "communication": messages,
        "synthesis": report.model_dump(),
        "timings": state.get("timings") or {},
        "dropped_citations": dropped,
        "error": state.get("error"),
    }
    write_audit("policy_analysis", audit_record, state.get("audit_id"))

    return {
        "synthesis": report.model_dump(),
        "dropped_citations": dropped,
        "timings": timings_with(state, synthesis_ms=(time.monotonic() - started) * 1000),
    }
